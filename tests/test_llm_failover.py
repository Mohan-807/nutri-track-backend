"""Failover behaviour of the provider orchestrator. No real API calls: fake providers stand in for
Gemini/NVIDIA so every branch (switch, cooldown, mid-stream failure, all-exhausted) is exercised
deterministically."""

import pytest

from app.services import llm_service
from app.services.llm_providers.base import AllModelsExhausted, LlmBadRequest, LlmUnavailable

TURNS = [{"role": "user", "text": "hi"}]


class FakeProvider:
    def __init__(self, name, *, model="m", configured=True, fail=None, fail_after_chunk=False, text="ok"):
        self.name = name
        self.model = model
        self._configured = configured
        self._fail = fail
        self._fail_after_chunk = fail_after_chunk
        self._text = text
        self.calls = 0

    def is_configured(self):
        return self._configured

    def stream_turn(self, turns, *, system_instruction=None, tools=None):
        self.calls += 1
        if self._fail_after_chunk:
            yield {"type": "chunk", "text": "partial"}
            raise self._fail
        if self._fail is not None:
            raise self._fail
        yield {"type": "chunk", "text": self._text}
        yield {"type": "done", "text": self._text}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    llm_service._reset_cooldowns_for_tests()
    yield
    llm_service._reset_cooldowns_for_tests()


def _install(monkeypatch, *providers):
    monkeypatch.setattr(llm_service, "_PROVIDERS", {p.name: p for p in providers})
    monkeypatch.setattr(llm_service, "_ordered_providers", lambda: list(providers))


def test_uses_first_provider_when_healthy(monkeypatch):
    primary = FakeProvider("gemini", text="from-primary")
    backup = FakeProvider("nvidia")
    _install(monkeypatch, primary, backup)

    events = list(llm_service.stream_turn(TURNS))

    assert events[0] == {"type": "provider", "provider": "gemini", "model": "m"}
    assert events[-1] == {"type": "done", "text": "from-primary"}
    assert backup.calls == 0  # backup never touched while the primary works


def test_fails_over_when_primary_unavailable(monkeypatch):
    primary = FakeProvider("gemini", fail=LlmUnavailable("quota gone"))
    backup = FakeProvider("nvidia", model="nemotron", text="from-backup")
    _install(monkeypatch, primary, backup)

    events = list(llm_service.stream_turn(TURNS))

    # The caller is told which model actually served the request — the failed one is not announced
    # as the answer's source.
    assert {"type": "provider", "provider": "nvidia", "model": "nemotron"} in events
    assert events[-1] == {"type": "done", "text": "from-backup"}
    assert primary.calls == 1 and backup.calls == 1


def test_skips_unconfigured_provider_without_calling_it(monkeypatch):
    primary = FakeProvider("gemini", configured=False)
    backup = FakeProvider("nvidia", text="from-backup")
    _install(monkeypatch, primary, backup)

    events = list(llm_service.stream_turn(TURNS))

    assert events[-1] == {"type": "done", "text": "from-backup"}
    assert primary.calls == 0


def test_all_providers_unavailable_raises_exhausted(monkeypatch):
    _install(
        monkeypatch,
        FakeProvider("gemini", fail=LlmUnavailable("quota")),
        FakeProvider("nvidia", fail=LlmUnavailable("overloaded")),
    )

    with pytest.raises(AllModelsExhausted) as exc_info:
        list(llm_service.stream_turn(TURNS))

    assert "All AI models are currently unavailable" in exc_info.value.message


def test_no_configured_providers_raises_exhausted(monkeypatch):
    _install(monkeypatch, FakeProvider("gemini", configured=False), FakeProvider("nvidia", configured=False))

    with pytest.raises(AllModelsExhausted):
        list(llm_service.stream_turn(TURNS))


def test_bad_request_does_not_fail_over(monkeypatch):
    # A malformed request would be rejected identically by every provider, so failing over would
    # just burn a second quota for the same error.
    primary = FakeProvider("gemini", fail=LlmBadRequest("bad tool schema"))
    backup = FakeProvider("nvidia")
    _install(monkeypatch, primary, backup)

    with pytest.raises(LlmBadRequest):
        list(llm_service.stream_turn(TURNS))
    assert backup.calls == 0


def test_mid_stream_failure_does_not_fail_over(monkeypatch):
    # Text already reached the client; restarting on another provider would splice two different
    # answers together, so this surfaces as an error instead.
    primary = FakeProvider("gemini", fail=LlmUnavailable("dropped"), fail_after_chunk=True)
    backup = FakeProvider("nvidia")
    _install(monkeypatch, primary, backup)

    with pytest.raises(LlmUnavailable):
        list(llm_service.stream_turn(TURNS))
    assert backup.calls == 0


def test_failed_provider_is_skipped_while_in_cooldown(monkeypatch):
    primary = FakeProvider("gemini", fail=LlmUnavailable("quota"))
    backup = FakeProvider("nvidia", text="from-backup")
    _install(monkeypatch, primary, backup)

    list(llm_service.stream_turn(TURNS))
    list(llm_service.stream_turn(TURNS))

    # Second request goes straight to the backup rather than paying another failed round trip.
    assert primary.calls == 1
    assert backup.calls == 2


def test_cooldown_expires_and_primary_is_retried(monkeypatch):
    primary = FakeProvider("gemini", fail=LlmUnavailable("blip", cooldown_seconds=0.0))
    backup = FakeProvider("nvidia")
    _install(monkeypatch, primary, backup)

    list(llm_service.stream_turn(TURNS))
    list(llm_service.stream_turn(TURNS))

    assert primary.calls == 2  # cooldown lapsed, so the preferred provider gets another chance


def test_cooldown_length_comes_from_the_failure(monkeypatch):
    """A transient blip must not sideline a provider as long as an exhausted quota does — the
    provider that recovers in seconds should be retried in seconds."""
    quota_dead = FakeProvider("gemini", fail=LlmUnavailable("quota", cooldown_seconds=900.0))
    blipped = FakeProvider("nvidia", fail=LlmUnavailable("overloaded", cooldown_seconds=0.0))
    _install(monkeypatch, quota_dead, blipped)

    with pytest.raises(AllModelsExhausted):
        list(llm_service.stream_turn(TURNS))
    with pytest.raises(AllModelsExhausted):
        list(llm_service.stream_turn(TURNS))

    assert quota_dead.calls == 1  # long cooldown: not retried
    assert blipped.calls == 2  # short cooldown: retried immediately
