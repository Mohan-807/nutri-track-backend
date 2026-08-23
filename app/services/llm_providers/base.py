"""Shared contract every LLM provider implements.

The key type here is the **provider-neutral turn**. chat_service builds conversations only out of
these, and each provider translates them into its own wire format. That indirection is what makes
failover possible at all: Gemini's SDK objects can't be handed to an OpenAI-compatible endpoint,
so nothing provider-specific may ever leak into the conversation chat_service is holding.

    {"role": "user",      "text": str}
    {"role": "assistant", "text": str}
    {"role": "assistant", "tool_call": {"id": str, "name": str, "args": dict}}
    {"role": "tool",      "tool_call_id": str, "name": str, "result": dict}

Providers stream back neutral events, exactly one terminal event last:
    {"type": "chunk",         "text": str}                      — incremental text
    {"type": "function_call", "id": str, "name": str, "args": dict}  — terminal
    {"type": "done",          "text": str}                      — terminal
"""

from collections.abc import Iterator
from typing import Protocol


class LlmError(Exception):
    """Base for every provider failure. `retryable` is informational — surfaced in the message so
    the user knows whether trying again is likely to help."""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.message = message
        self.retryable = retryable


class LlmUnavailable(LlmError):
    """This provider can't serve the request right now — quota exhausted, overloaded, 5xx, a
    network failure, or a bad/missing API key. The orchestrator responds by failing over to the
    next configured provider, so this is the *only* error type that triggers a switch.

    `cooldown_seconds` says how long to stop trying this provider, and the distinction matters a
    lot in practice: an exhausted daily quota won't recover for hours, so retrying it on every
    message is pure waste — but a momentary "service overloaded" blip clears in seconds, and
    sidelining a healthy provider for minutes over one of those needlessly burns the other
    provider's quota (or fails outright when both are briefly down)."""

    def __init__(self, message: str, *, retryable: bool = False, cooldown_seconds: float = 30.0):
        super().__init__(message, retryable=retryable)
        self.cooldown_seconds = cooldown_seconds


class LlmBadRequest(LlmError):
    """The request itself is malformed (a 400 — e.g. a bad tool schema on our side). Deliberately
    NOT a failover trigger: every other provider would reject it identically, so switching would
    just burn a second quota to produce the same failure."""


class AllModelsExhausted(LlmError):
    """Every configured provider was unavailable."""

    def __init__(self, message: str = "All AI models are currently unavailable. Please try again later."):
        super().__init__(message, retryable=True)


class LlmProvider(Protocol):
    """Implemented by gemini.py and nvidia.py. `name` identifies the provider and `model` the exact
    model id — both are recorded on the assistant's ChatMessage row so it's always answerable after
    the fact which model produced a given reply."""

    name: str
    model: str

    def is_configured(self) -> bool:
        """False when this provider has no API key set, so it's skipped without a wasted round trip."""
        ...

    def stream_turn(
        self,
        turns: list[dict],
        *,
        system_instruction: str | None = None,
        tools: list[dict] | None = None,
    ) -> Iterator[dict]:
        ...
