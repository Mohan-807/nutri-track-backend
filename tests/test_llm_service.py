import pytest
from google.genai import errors as genai_errors

from app.services import llm_service
from app.services.llm_service import LlmError

_SAMPLE_CONTENTS = [{"role": "user", "parts": [{"text": "hi"}]}]


class _FakeModels:
    def __init__(self, exc):
        self._exc = exc

    def generate_content_stream(self, **kwargs):
        raise self._exc


class _FakeClient:
    def __init__(self, exc):
        self.models = _FakeModels(exc)


def _patch_client(monkeypatch, exc):
    monkeypatch.setattr(llm_service, "_get_client", lambda: _FakeClient(exc))


def test_stream_turn_classifies_rate_limit_as_retryable(monkeypatch):
    _patch_client(monkeypatch, genai_errors.ClientError(429, {"error": {"message": "quota", "status": "RESOURCE_EXHAUSTED"}}))

    with pytest.raises(LlmError) as exc_info:
        list(llm_service.stream_turn(_SAMPLE_CONTENTS))

    assert exc_info.value.retryable is True
    assert "rate-limited" in exc_info.value.message


def test_stream_turn_classifies_server_error_as_retryable(monkeypatch):
    _patch_client(monkeypatch, genai_errors.ServerError(503, {"error": {"message": "unavailable"}}))

    with pytest.raises(LlmError) as exc_info:
        list(llm_service.stream_turn(_SAMPLE_CONTENTS))

    assert exc_info.value.retryable is True


def test_stream_turn_classifies_bad_request_as_not_retryable(monkeypatch):
    _patch_client(monkeypatch, genai_errors.ClientError(400, {"error": {"message": "bad request"}}))

    with pytest.raises(LlmError) as exc_info:
        list(llm_service.stream_turn(_SAMPLE_CONTENTS))

    assert exc_info.value.retryable is False


def test_stream_turn_classifies_network_error_as_retryable(monkeypatch):
    _patch_client(monkeypatch, ConnectionError("network down"))

    with pytest.raises(LlmError) as exc_info:
        list(llm_service.stream_turn(_SAMPLE_CONTENTS))

    assert exc_info.value.retryable is True
