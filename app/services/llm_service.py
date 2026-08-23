import logging
from collections.abc import Iterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import get_settings

logger = logging.getLogger(__name__)


class LlmError(Exception):
    """Provider-agnostic failure — chat_service (and everything upstream) catches this one type
    and never needs to know Gemini's own exception classes. `retryable` is informational (surfaced
    in the message so the user knows whether trying again is likely to help); nothing in this app
    automatically retries on it — see chat_service.py's send_message_stream for why."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily built and cached (mirrors get_settings()'s own @lru_cache pattern) so importing
    this module never requires a real API key — only calling stream_turn() does.

    Production hardening (Step 11):
    - Explicit timeout, so a hung upstream request can't tie up a backend thread forever
      (FastAPI runs this module's sync calls in a threadpool with a finite number of workers).
    - The SDK's *default* retry policy (5 attempts, exponential backoff, retrying 429s among
      other codes) is deliberately overridden: retrying a 429 doesn't help — Gemini's own
      response says how many seconds/minutes to wait, far longer than a synchronous chat
      request should block for — and every retry spends another unit of an already scarce
      free-tier daily quota. Only transient server-side failures (5xx) get a couple of quick
      retries; 429s are excluded and surface immediately as an LlmError instead."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.gemini_timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=2,
                    initial_delay=1.0,
                    max_delay=5.0,
                    http_status_codes=[500, 502, 503, 504],
                ),
            ),
        )
    return _client


def _build_config(system_instruction: str | None, tools: list[dict] | None) -> types.GenerateContentConfig | None:
    config_kwargs: dict = {}
    if system_instruction:
        config_kwargs["system_instruction"] = system_instruction
    if tools:
        config_kwargs["tools"] = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool["name"],
                        description=tool["description"],
                        parameters_json_schema=tool["parameters"],
                    )
                    for tool in tools
                ]
            )
        ]
        # Gemini must only ever *request* a call via a function_call part, never execute
        # anything itself — chat_service is what decides whether a requested tool actually runs.
        config_kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
    return types.GenerateContentConfig(**config_kwargs) if config_kwargs else None


def stream_turn(
    contents: list,
    *,
    system_instruction: str | None = None,
    tools: list[dict] | None = None,
) -> Iterator[dict]:
    """The only function in the codebase that talks to Gemini directly — everything upstream of
    it (chat_service, the tool registry) never touches the SDK, so swapping providers later
    means rewriting this module's internals only.

    Streams one model turn as plain-dict events chat_service (and eventually the SSE endpoint)
    can consume without knowing anything about the SDK:
      {"type": "chunk", "text": "..."}                        — a piece of text as it arrives
      {"type": "function_call", "name", "args", "content"}    — terminal; no chunks follow
      {"type": "done", "content", "text"}                     — terminal; final text is ready
    Exactly one terminal event is always yielded last. `content` is an opaque token — the caller
    appends it back into a future `contents` list verbatim but never inspects or constructs one
    itself. Function-call arguments are treated as arriving whole in one chunk (true for the
    simple JSON-schema tools this app declares); true incremental function-call streaming
    (Gemini's partial_args/will_continue) isn't handled.
    """
    settings = get_settings()
    config = _build_config(system_instruction, tools)

    accumulated_text = ""
    function_call: dict | None = None
    usage = None

    try:
        stream = _get_client().models.generate_content_stream(
            model=settings.gemini_model, contents=contents, config=config
        )
        for chunk in stream:
            if chunk.usage_metadata is not None:
                usage = chunk.usage_metadata  # present on the final chunk; earlier ones overwrite harmlessly
            if not chunk.candidates or chunk.candidates[0].content is None:
                continue
            for part in chunk.candidates[0].content.parts:
                if part.function_call:
                    function_call = {"name": part.function_call.name, "args": dict(part.function_call.args or {})}
                elif part.text:
                    accumulated_text += part.text
                    yield {"type": "chunk", "text": part.text}
    except genai_errors.APIError as exc:
        # Classified by status code so the user gets an accurate, actionable message instead of
        # a generic failure — a rate limit and a malformed request are not the same problem.
        if exc.code == 429:
            raise LlmError(
                "The AI is rate-limited right now (free-tier quota). Please wait a bit and try again.",
                retryable=True,
            ) from exc
        if exc.code and exc.code >= 500:
            raise LlmError("The AI service is temporarily unavailable. Please try again shortly.", retryable=True) from exc
        raise LlmError("The AI service couldn't process that request.", retryable=False) from exc
    except Exception as exc:
        # Not a Gemini API error at all — a network failure, timeout, or an interruption
        # mid-stream (the connection can drop after some chunks already arrived and were
        # yielded; the caller still sees whatever text was already sent, then this failure).
        raise LlmError(
            "Could not reach the AI service. Please check your connection and try again.", retryable=True
        ) from exc

    # Token usage tracking / cost visibility (Step 11) — one line per Gemini call, cheap enough
    # to always log at INFO. This app makes no attempt at deeper cost aggregation/billing
    # (dashboards, per-user spend limits) — logging is proportional to its actual scale.
    if usage is not None:
        logger.info(
            "Gemini call used %s prompt + %s response = %s total tokens (model=%s)",
            usage.prompt_token_count,
            usage.candidates_token_count,
            usage.total_token_count,
            settings.gemini_model,
        )

    if function_call is not None:
        content = types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name=function_call["name"], args=function_call["args"]))],
        )
        yield {"type": "function_call", "name": function_call["name"], "args": function_call["args"], "content": content}
    else:
        text = accumulated_text or "Sorry, I couldn't come up with a response to that."
        content = types.Content(role="model", parts=[types.Part(text=text)])
        yield {"type": "done", "content": content, "text": text}


def function_response_turn(name: str, response: dict) -> dict:
    """Builds the turn chat_service appends to `contents` after executing a tool — the one place
    that knows Gemini expects a tool's result back as a role="user" turn wrapping a
    function_response part."""
    return {"role": "user", "parts": [{"function_response": {"name": name, "response": response}}]}
