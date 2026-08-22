ONBOARDING_BODY = {
    "heightCm": 175,
    "weightKg": 70,
    "age": 28,
    "gender": "male",
    "activityLevel": "moderate",
    "goal": "lose",
}


def test_get_profile_before_onboarding_is_404(client, auth_headers):
    response = client.get("/profile/me", headers=auth_headers)
    assert response.status_code == 404


def test_onboarding_computes_correct_targets(client, auth_headers):
    response = client.post("/profile/onboarding", json=ONBOARDING_BODY, headers=auth_headers)
    assert response.status_code == 201
    body = response.json()

    assert body["onboardingCompleted"] is True
    assert body["bmi"] == 22.9
    assert body["bmr"] == 1659
    assert body["tdee"] == 2571
    assert body["targets"] == {
        "calories": 2071,
        "proteinG": 140,
        "carbsG": 247,
        "fatG": 58,
        "fiberG": 29,
        "sugarMaxG": 52,
        "sodiumMaxMg": 2300,
    }


def test_double_onboarding_rejected(client, auth_headers):
    client.post("/profile/onboarding", json=ONBOARDING_BODY, headers=auth_headers)
    response = client.post("/profile/onboarding", json=ONBOARDING_BODY, headers=auth_headers)
    assert response.status_code == 409


def test_get_profile_after_onboarding(client, auth_headers):
    client.post("/profile/onboarding", json=ONBOARDING_BODY, headers=auth_headers)
    response = client.get("/profile/me", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["goal"] == "lose"


def test_update_recomputes_targets(client, auth_headers):
    client.post("/profile/onboarding", json=ONBOARDING_BODY, headers=auth_headers)

    updated = {**ONBOARDING_BODY, "goal": "gain"}
    response = client.put("/profile/me", json=updated, headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["goal"] == "gain"
    assert body["targets"]["calories"] == 2871  # tdee(2571) + gain adjustment(+300)


def test_update_before_onboarding_is_404(client, auth_headers):
    response = client.put("/profile/me", json=ONBOARDING_BODY, headers=auth_headers)
    assert response.status_code == 404


def test_profile_requires_auth(client):
    response = client.get("/profile/me")
    assert response.status_code == 401
