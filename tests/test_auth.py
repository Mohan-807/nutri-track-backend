def test_signup_success(client):
    response = client.post("/auth/signup", json={"email": "new@example.com", "password": "pw123456"})
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "new@example.com"
    assert "token" in body


def test_signup_duplicate_email_rejected(client):
    client.post("/auth/signup", json={"email": "dup@example.com", "password": "pw123456"})
    response = client.post("/auth/signup", json={"email": "dup@example.com", "password": "pw123456"})
    assert response.status_code == 409


def test_signup_normalizes_email_case(client):
    client.post("/auth/signup", json={"email": "Mixed@Example.com", "password": "pw123456"})
    response = client.post("/auth/signup", json={"email": "mixed@example.com", "password": "pw123456"})
    assert response.status_code == 409


def test_login_success(client):
    client.post("/auth/signup", json={"email": "login@example.com", "password": "pw123456"})
    response = client.post("/auth/login", json={"email": "login@example.com", "password": "pw123456"})
    assert response.status_code == 200
    assert "token" in response.json()


def test_login_wrong_password(client):
    client.post("/auth/signup", json={"email": "wrongpw@example.com", "password": "pw123456"})
    response = client.post("/auth/login", json={"email": "wrongpw@example.com", "password": "nope1234"})
    assert response.status_code == 401


def test_login_unknown_email(client):
    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": "pw123456"})
    assert response.status_code == 401


def test_me_requires_a_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_rejects_garbage_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer garbage.token.value"})
    assert response.status_code == 401


def test_me_returns_current_user(client, auth_headers):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"
