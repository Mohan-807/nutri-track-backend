import logging
import time
from collections.abc import Iterator

from app.config import get_settings
from app.services.llm_providers.base import (
    AllModelsExhausted,
    LlmBadRequest,
    LlmError,
    LlmProvider,
    LlmUnavailable,
)
from app.services.llm_providers.gemini import GeminiProvider
from app.services.llm_providers.nvidia import NvidiaProvider

logger = logging.getLogger(__name__)

__all__ = ["AllModelsExhausted", "LlmBadRequest", "LlmError", "LlmUnavailable", "stream_turn"]

_PROVIDERS: dict[str, LlmProvider] = {p.name: p for p in (GeminiProvider(), NvidiaProvider())}

# After a provider reports itself unavailable, skip it for a while instead of paying a failed
# round trip on every subsequent message. The duration comes from the failure itself
# (LlmUnavailable.cooldown_seconds): long for an exhausted quota or bad credentials, short for a
# transient overload — sidelining a provider that recovered seconds ago would needlessly spend the
# other provider's quota, or fail the request outright when both are momentarily down.
_unavailable_until: dict[str, float] = {}


def _ordered_providers() -> list[LlmProvider]:
    """Priority order comes from LLM_PROVIDER_ORDER (comma-separated). Unknown names are logged and
    skipped rather than raising, so a typo degrades to "fewer providers" instead of a dead app."""
    providers = []
    for name in get_settings().llm_provider_order_list:
        provider = _PROVIDERS.get(name)
        if provider is None:
            logger.warning("Unknown LLM provider %r in LLM_PROVIDER_ORDER — skipping", name)
            continue
        providers.append(provider)
    return providers


def _reset_cooldowns_for_tests() -> None:
    _unavailable_until.clear()


def stream_turn(
    turns: list[dict],
    *,
    system_instruction: str | None = None,
    tools: list[dict] | None = None,
) -> Iterator[dict]:
    """Runs one model turn against the first available provider, failing over on unavailability.

    Yields the neutral events documented in llm_providers/base.py, plus one extra event emitted
    before any content so the caller knows which model actually served the request:
        {"type": "provider", "provider": str, "model": str}

    Failover only happens *before the first token reaches the caller*. Once text has been streamed
    out, switching providers would make a second model restart the answer mid-sentence and the user
    would see two spliced replies — so a mid-stream failure is surfaced as an error instead. This is
    the main reason a provider's own retry logic is disabled: a clean, immediate failure here is
    more useful than a slow internal retry that succeeds after we've already emitted something.
    """
    providers = _ordered_providers()
    if not providers:
        raise AllModelsExhausted("No AI providers are configured.")

    now = time.monotonic()
    attempted = False
    last_error: LlmError | None = None

    for provider in providers:
        if not provider.is_configured():
            logger.debug("Skipping %s — no API key configured", provider.name)
            continue
        if _unavailable_until.get(provider.name, 0.0) > now:
            logger.info("Skipping %s — in cooldown for another %.0fs", provider.name, _unavailable_until[provider.name] - now)
            continue

        attempted = True
        emitted = False
        try:
            yield {"type": "provider", "provider": provider.name, "model": provider.model}
            for event in provider.stream_turn(turns, system_instruction=system_instruction, tools=tools):
                emitted = True
                yield event
            _unavailable_until.pop(provider.name, None)  # served a request — clear any old cooldown
            return
        except LlmUnavailable as exc:
            last_error = exc
            _unavailable_until[provider.name] = time.monotonic() + exc.cooldown_seconds
            if emitted:
                logger.warning("%s failed mid-stream — cannot fail over cleanly: %s", provider.name, exc.message)
                raise
            logger.warning("%s unavailable, trying next provider: %s", provider.name, exc.message)
            continue
        except LlmBadRequest:
            raise  # every provider would reject it identically — don't burn a second quota

    if not attempted:
        raise AllModelsExhausted(
            "All AI models are currently unavailable (quota exhausted or unreachable). Please try again later."
        )
    raise AllModelsExhausted(
        "All AI models are currently unavailable (quota exhausted or unreachable). Please try again later."
    ) from last_error
