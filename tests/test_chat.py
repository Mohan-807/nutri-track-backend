from app.routers import chat as chat_router


def test_chat_requires_auth(client):
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_chat_returns_llm_reply(client, auth_headers, monkeypatch):
    # Never call the real Gemini API from tests — non-deterministic output, network-dependent,
    # and burns free-tier quota. Patches the name as imported into chat_router's own namespace,
    # which is what send_message() actually calls.
    monkeypatch.setattr(chat_router, "generate_reply", lambda message: f"echo: {message}")
    response = client.post("/chat", json={"message": "hello"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"reply": "echo: hello"}


def test_chat_rejects_empty_message(client, auth_headers):
    response = client.post("/chat", json={"message": ""}, headers=auth_headers)
    assert response.status_code == 422
