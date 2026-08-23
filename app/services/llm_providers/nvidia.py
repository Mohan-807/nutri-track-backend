import json
import logging
from collections.abc import Iterator

import openai
from openai import OpenAI

from app.config import get_settings
from app.services.llm_providers.base import LlmBadRequest, LlmUnavailable

logger = logging.getLogger(__name__)

# A quota/credentials failure won't clear for hours; a transient blip uses the shorter default.
LONG_COOLDOWN_SECONDS = 900.0

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """NVIDIA NIM exposes an OpenAI-compatible API, so the official `openai` SDK drives it — only
    base_url and the key differ. max_retries=0: retrying here would hide a transient failure that
    the orchestrator would rather handle by failing over to a different provider immediately."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = OpenAI(
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
            timeout=settings.nvidia_timeout_seconds,
            max_retries=0,
        )
    return _client


def _to_openai_messages(turns: list[dict], system_instruction: str | None) -> list[dict]:
    """Neutral turns -> OpenAI chat messages. Two shape differences from Gemini worth noting:
    the system prompt is an ordinary first message (not a separate config field), and a tool result
    is its own role="tool" message that must reference the originating call by tool_call_id."""
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})

    for turn in turns:
        role = turn["role"]
        if role == "user":
            messages.append({"role": "user", "content": turn["text"]})
        elif role == "assistant" and "tool_call" in turn:
            call = turn["tool_call"]
            messages.append(
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": call["id"],
                            "type": "function",
                            "function": {"name": call["name"], "arguments": json.dumps(call["args"])},
                        }
                    ],
                }
            )
        elif role == "assistant":
            messages.append({"role": "assistant", "content": turn["text"]})
        elif role == "tool":
            messages.append(
                {"role": "tool", "tool_call_id": turn["tool_call_id"], "content": json.dumps(turn["result"])}
            )
    return messages


class NvidiaProvider:
    name = "nvidia"

    @property
    def model(self) -> str:
        return get_settings().nvidia_model

    def is_configured(self) -> bool:
        return bool(get_settings().nvidia_api_key)

    def stream_turn(
        self, turns: list[dict], *, system_instruction: str | None = None, tools: list[dict] | None = None
    ) -> Iterator[dict]:
        settings = get_settings()
        messages = _to_openai_messages(turns, system_instruction)
        request: dict = {
            "model": settings.nvidia_model,
            "messages": messages,
            "max_tokens": settings.nvidia_max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            request["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]},
                }
                for t in tools
            ]

        text = ""
        call_id: str | None = None
        call_name: str | None = None
        call_args = ""  # streamed as JSON string fragments that must be concatenated, then parsed
        usage = None

        try:
            for chunk in _get_client().chat.completions.create(**request):
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # This model emits chain-of-thought as `reasoning_content`. It is intentionally
                # dropped: it's the model's private scratchpad, not an answer, and streaming it
                # would show the user reasoning that may contradict the final reply.
                for tool_call in delta.tool_calls or []:
                    if tool_call.function is None:
                        continue
                    if tool_call.id:
                        call_id = tool_call.id
                    if tool_call.function.name:
                        call_name = tool_call.function.name
                    if tool_call.function.arguments:
                        call_args += tool_call.function.arguments
                if delta.content:
                    text += delta.content
                    yield {"type": "chunk", "text": delta.content}
        except openai.BadRequestError as exc:
            raise LlmBadRequest("The AI service rejected that request.") from exc
        except (openai.RateLimitError, openai.AuthenticationError, openai.PermissionDeniedError) as exc:
            # Quota or credentials — won't self-heal quickly, so back off for a long while.
            raise LlmUnavailable(
                f"{self.name} unavailable (quota or credentials).",
                retryable=True,
                cooldown_seconds=LONG_COOLDOWN_SECONDS,
            ) from exc
        except openai.APIError as exc:
            # NVIDIA's "Service temporarily overloaded", 5xx, timeouts — observed to clear within
            # seconds, so this keeps the default short cooldown rather than sidelining a provider
            # that is actually healthy.
            raise LlmUnavailable(f"{self.name} unavailable ({type(exc).__name__}).", retryable=True) from exc
        except Exception as exc:
            raise LlmUnavailable(f"Could not reach {self.name}.", retryable=True) from exc

        if usage is not None:
            logger.info(
                "nvidia/%s used %s prompt + %s response = %s total tokens",
                settings.nvidia_model,
                usage.prompt_tokens,
                usage.completion_tokens,
                usage.total_tokens,
            )

        if call_name is not None:
            try:
                args = json.loads(call_args) if call_args.strip() else {}
            except json.JSONDecodeError:
                # A truncated/malformed argument blob is the model's fault, not the request's —
                # hand it back as an empty-arg call so the tool's own pydantic validation produces
                # a proper "invalid arguments" tool result the model can react to.
                logger.warning("nvidia returned unparseable tool arguments: %r", call_args)
                args = {}
            yield {"type": "function_call", "id": call_id or f"call_{call_name}", "name": call_name, "args": args}
        else:
            yield {"type": "done", "text": text}
