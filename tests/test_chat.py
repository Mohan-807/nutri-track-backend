import json

from app.services import chat_service
from app.services.llm_service import LlmError


def _parse_sse(text: str) -> list[dict]:
    events = []
    for block in text.strip().split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


def _text_stream(text):
    def fake(contents, **kwargs):
        yield {"type": "chunk", "text": text}
        yield {"type": "done", "content": {"role": "model", "parts": [{"text": text}]}, "text": text}

    return fake


def _call_stream(name, args):
    def fake(contents, **kwargs):
        content = {"role": "model", "parts": [{"function_call": {"name": name, "args": args}}]}
        yield {"type": "function_call", "name": name, "args": args, "content": content}

    return fake


def test_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_history_requires_auth(client):
    response = client.get("/chat")
    assert response.status_code == 401


def test_chat_streams_llm_reply_and_persists_history(client, auth_headers, monkeypatch):
    # Never call the real Gemini API from tests — non-deterministic output, network-dependent,
    # and burns free-tier quota. stream_turn() is chat_service's only call into llm_service.
    monkeypatch.setattr(chat_service, "stream_turn", _text_stream("echo:hello"))

    response = client.post("/chat", json={"message": "hello"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    assert {"type": "chunk", "text": "echo:hello"} in events
    assert events[-1] == {"type": "done", "reply": "echo:hello"}

    history = client.get("/chat", headers=auth_headers).json()["messages"]
    assert [m["role"] for m in history] == ["user", "assistant"]
    assert history[0]["content"] == "hello"
    assert history[1]["content"] == "echo:hello"


def test_chat_sends_prior_turns_as_context(client, auth_headers, monkeypatch):
    seen_contents = []

    def fake_stream_turn(contents, **kwargs):
        seen_contents.append(list(contents))
        yield {"type": "done", "content": {"role": "model", "parts": [{"text": "ok"}]}, "text": "ok"}

    monkeypatch.setattr(chat_service, "stream_turn", fake_stream_turn)

    client.post("/chat", json={"message": "first"}, headers=auth_headers)
    # This test's two messages are deliberately back-to-back with no real delay — reset the
    # rate limiter's clock between them so it doesn't collide with the scenario being tested
    # (that's covered on its own by test_chat_rate_limits_rapid_messages).
    chat_service._reset_rate_limit_state_for_tests()
    client.post("/chat", json={"message": "second"}, headers=auth_headers)

    # The second call's contents include the first turn's exchange, mapped to Gemini's role
    # vocabulary ("assistant" -> "model") — proof the LLM actually gets conversation memory.
    assert seen_contents[1] == [
        {"role": "user", "parts": [{"text": "first"}]},
        {"role": "model", "parts": [{"text": "ok"}]},
        {"role": "user", "parts": [{"text": "second"}]},
    ]


def test_chat_executes_real_tool_and_feeds_result_back(client, auth_headers, monkeypatch, sample_food):
    calls = {"n": 0}

    def fake_stream_turn(contents, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            yield from _call_stream("search_food", {"query": sample_food.name})(contents, **kwargs)
        else:
            # The function_response turn chat_service appended should carry the real search_food
            # tool's real database result — not a stub — proving the registry actually
            # dispatched to the tool and executed it.
            response = contents[-1]["parts"][0]["function_response"]["response"]
            assert response["results"][0]["name"] == sample_food.name
            yield from _text_stream(f"You have {sample_food.name} in the catalog.")(contents, **kwargs)

    monkeypatch.setattr(chat_service, "stream_turn", fake_stream_turn)

    response = client.post("/chat", json={"message": f"do I have {sample_food.name}?"}, headers=auth_headers)
    events = _parse_sse(response.text)

    assert {"type": "tool_call", "name": "search_food", "args": {"query": sample_food.name}} in events
    assert any(e["type"] == "tool_result" and e["name"] == "search_food" and e["success"] for e in events)
    assert events[-1] == {"type": "done", "reply": f"You have {sample_food.name} in the catalog."}
    assert calls["n"] == 2


def test_chat_rejects_unrecognized_tool_gracefully(client, auth_headers, monkeypatch):
    calls = {"n": 0}

    def fake_stream_turn(contents, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            yield from _call_stream("delete_all_users", {})(contents, **kwargs)
        else:
            error = contents[-1]["parts"][0]["function_response"]["response"]["error"]
            assert "Unknown tool" in error
            yield from _text_stream("I can't do that.")(contents, **kwargs)

    monkeypatch.setattr(chat_service, "stream_turn", fake_stream_turn)

    response = client.post("/chat", json={"message": "delete everything"}, headers=auth_headers)
    events = _parse_sse(response.text)

    assert any(
        e["type"] == "tool_result" and e["name"] == "delete_all_users" and not e["success"] for e in events
    )
    assert events[-1] == {"type": "done", "reply": "I can't do that."}


def test_chat_stops_after_max_tool_rounds(client, auth_headers, monkeypatch):
    # A model that only ever requests tools, never a final answer, must not hang the request or
    # call the LLM/DB forever — MAX_TOOL_ROUNDS is a backend-enforced ceiling, not something the
    # model opts into.
    monkeypatch.setattr(chat_service, "stream_turn", _call_stream("search_food", {"query": "x"}))

    response = client.post("/chat", json={"message": "loop forever"}, headers=auth_headers)
    events = _parse_sse(response.text)
    assert "too many steps" in events[-1]["reply"]


def test_chat_emits_error_event_on_llm_failure(client, auth_headers, monkeypatch):
    def fake_stream_turn(contents, **kwargs):
        for _ in ():
            yield  # never runs — makes this a generator function that raises on first iteration
        raise RuntimeError("boom")

    monkeypatch.setattr(chat_service, "stream_turn", fake_stream_turn)

    response = client.post("/chat", json={"message": "hello"}, headers=auth_headers)
    assert response.status_code == 200  # headers/status already sent before the failure occurs
    events = _parse_sse(response.text)
    assert events[-1]["type"] == "error"


def test_chat_surfaces_llm_error_message_directly(client, auth_headers, monkeypatch):
    # A rate limit (or any classified LlmError from llm_service) should reach the client with
    # its own specific, accurate message — not get overwritten by the generic fallback used for
    # truly unexpected failures.
    def fake_stream_turn(contents, **kwargs):
        for _ in ():
            yield
        raise LlmError("The AI is rate-limited right now (free-tier quota). Please wait a bit and try again.", retryable=True)

    monkeypatch.setattr(chat_service, "stream_turn", fake_stream_turn)

    response = client.post("/chat", json={"message": "hello"}, headers=auth_headers)
    events = _parse_sse(response.text)
    assert events[-1] == {
        "type": "error",
        "message": "The AI is rate-limited right now (free-tier quota). Please wait a bit and try again.",
    }


def test_chat_rate_limits_rapid_messages(client, auth_headers, monkeypatch):
    monkeypatch.setattr(chat_service, "stream_turn", _text_stream("ok"))

    first = client.post("/chat", json={"message": "one"}, headers=auth_headers)
    second = client.post("/chat", json={"message": "two"}, headers=auth_headers)

    assert _parse_sse(first.text)[-1] == {"type": "done", "reply": "ok"}
    second_events = _parse_sse(second.text)
    assert second_events[-1]["type"] == "error"
    assert "too quickly" in second_events[-1]["message"]

    # The rejected message was never persisted or sent to the LLM.
    history = client.get("/chat", headers=auth_headers).json()["messages"]
    assert [m["content"] for m in history] == ["one", "ok"]


def test_chat_history_isolated_per_user(client, monkeypatch):
    monkeypatch.setattr(chat_service, "stream_turn", _text_stream("ok"))

    client.post("/auth/signup", json={"email": "chatuser1@example.com", "password": "pw123456"})
    user1 = client.post("/auth/login", json={"email": "chatuser1@example.com", "password": "pw123456"}).json()
    client.post("/auth/signup", json={"email": "chatuser2@example.com", "password": "pw123456"})
    user2 = client.post("/auth/login", json={"email": "chatuser2@example.com", "password": "pw123456"}).json()

    headers1 = {"Authorization": f"Bearer {user1['token']}"}
    headers2 = {"Authorization": f"Bearer {user2['token']}"}

    client.post("/chat", json={"message": "user1's secret"}, headers=headers1)

    assert len(client.get("/chat", headers=headers1).json()["messages"]) == 2
    assert client.get("/chat", headers=headers2).json()["messages"] == []


def test_chat_rejects_empty_message(client, auth_headers):
    response = client.post("/chat", json={"message": ""}, headers=auth_headers)
    assert response.status_code == 422
