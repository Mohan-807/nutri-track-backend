import logging
from collections.abc import Iterator

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import get_settings
from app.services.llm_providers.base import LlmBadRequest, LlmUnavailable

logger = logging.getLogger(__name__)

# A quota/credentials failure won't clear for hours; a transient blip uses the shorter default.
LONG_COOLDOWN_SECONDS = 900.0

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Lazily built and cached so importing this module never requires an API key.

    The SDK's *default* retry policy (5 attempts, retrying 429s among other codes) is deliberately
    overridden: retrying a 429 doesn't help — Gemini's own response says to wait far longer than a
    chat request should block — and each retry spends another unit of a scarce free-tier quota.
    Only transient 5xx gets a couple of quick retries; a 429 surfaces immediately so the
    orchestrator can fail over to another provider instead of waiting."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.gemini_timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(
                    attempts=2, initial_delay=1.0, max_delay=5.0, http_status_codes=[500, 502, 503, 504]
                ),
            ),
        )
    return _client


def _to_gemini_contents(turns: list[dict]) -> list:
    """Neutral turns -> Gemini's `contents`. Gemini's role vocabulary is user/model (not
    user/assistant), and a tool result travels as a role="user" turn wrapping a function_response
    part rather than a dedicated "tool" role."""
    contents: list = []
    for turn in turns:
        role = turn["role"]
        if role == "user":
            contents.append({"role": "user", "parts": [{"text": turn["text"]}]})
        elif role == "assistant" and "tool_call" in turn:
            call = turn["tool_call"]
            contents.append(
                types.Content(
                    role="model",
                    parts=[types.Part(function_call=types.FunctionCall(name=call["name"], args=call["args"]))],
                )
            )
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": turn["text"]}]})
        elif role == "tool":
            contents.append(
                {"role": "user", "parts": [{"function_response": {"name": turn["name"], "response": turn["result"]}}]}
            )
    return contents


def _build_config(system_instruction: str | None, tools: list[dict] | None) -> types.GenerateContentConfig | None:
    kwargs: dict = {}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if tools:
        kwargs["tools"] = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=t["name"], description=t["description"], parameters_json_schema=t["parameters"]
                    )
                    for t in tools
                ]
            )
        ]
        # Gemini may only *request* a call; chat_service decides whether it actually runs.
        kwargs["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(disable=True)
    return types.GenerateContentConfig(**kwargs) if kwargs else None


class GeminiProvider:
    name = "gemini"

    @property
    def model(self) -> str:
        return get_settings().gemini_model

    def is_configured(self) -> bool:
        return bool(get_settings().gemini_api_key)

    def stream_turn(
        self, turns: list[dict], *, system_instruction: str | None = None, tools: list[dict] | None = None
    ) -> Iterator[dict]:
        settings = get_settings()
        contents = _to_gemini_contents(turns)
        config = _build_config(system_instruction, tools)

        text = ""
        call: dict | None = None
        usage = None

        try:
            stream = _get_client().models.generate_content_stream(
                model=settings.gemini_model, contents=contents, config=config
            )
            for chunk in stream:
                if chunk.usage_metadata is not None:
                    usage = chunk.usage_metadata
                if not chunk.candidates or chunk.candidates[0].content is None:
                    continue
                for part in chunk.candidates[0].content.parts:
                    if part.function_call:
                        call = {
                            "id": part.function_call.id or f"call_{part.function_call.name}",
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args or {}),
                        }
                    elif part.text:
                        text += part.text
                        yield {"type": "chunk", "text": part.text}
        except genai_errors.APIError as exc:
            if exc.code == 400:
                raise LlmBadRequest("The AI service rejected that request.") from exc
            if exc.code in (429, 401, 403):
                # Exhausted daily quota or bad credentials — neither self-heals in seconds, so
                # stop asking for a while instead of paying a failed round trip per message.
                raise LlmUnavailable(
                    f"Gemini unavailable (HTTP {exc.code}).", retryable=True, cooldown_seconds=LONG_COOLDOWN_SECONDS
                ) from exc
            raise LlmUnavailable(f"Gemini unavailable (HTTP {exc.code}).", retryable=True) from exc
        except Exception as exc:
            raise LlmUnavailable("Could not reach Gemini.", retryable=True) from exc

        if usage is not None:
            logger.info(
                "gemini/%s used %s prompt + %s response = %s total tokens",
                settings.gemini_model,
                usage.prompt_token_count,
                usage.candidates_token_count,
                usage.total_token_count,
            )

        if call is not None:
            yield {"type": "function_call", **call}
        else:
            yield {"type": "done", "text": text}
