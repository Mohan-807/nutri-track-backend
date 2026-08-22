from app.models.food import Food
from tests.conftest import signup_and_login

TODAY = "2026-08-17"


def test_create_entry_scales_server_side(client, auth_headers, sample_food):
    response = client.post(
        f"/logs/{TODAY}",
        json={"foodId": sample_food.id, "quantity": 2},
        headers=auth_headers,
    )
    assert response.status_code == 201
    nutrients = response.json()["nutrients"]
    assert nutrients["calories"] == 190  # 95 * 2
    assert nutrients["proteinG"] == 1.0  # 0.5 * 2
    assert nutrients["fiberG"] == 8.8  # 4.4 * 2


def test_client_submitted_nutrients_are_ignored(client, auth_headers, sample_food):
    """A client cannot influence stored nutrients by stuffing extra fields into the request —
    the schema only accepts foodId/quantity, so a bogus "nutrients" payload is silently dropped
    and the server always recomputes from the Food row itself."""
    response = client.post(
        f"/logs/{TODAY}",
        json={
            "foodId": sample_food.id,
            "quantity": 1,
            "nutrients": {"calories": 999999, "proteinG": 999999},
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["nutrients"]["calories"] == 95


def test_create_entry_missing_food_is_404(client, auth_headers):
    response = client.post(f"/logs/{TODAY}", json={"foodId": 999999, "quantity": 1}, headers=auth_headers)
    assert response.status_code == 404


def test_day_log_totals_sum_across_entries(client, auth_headers, sample_food, db_session):
    other = Food(
        name="Test Banana",
        aliases=[],
        category="fruit",
        serving_label="1 medium",
        serving_grams=118,
        calories=105,
        protein_g=1.3,
        carbs_g=27,
        fat_g=0.4,
        fiber_g=3.1,
        sugar_g=14,
        sodium_mg=1,
    )
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    client.post(f"/logs/{TODAY}", json={"foodId": sample_food.id, "quantity": 1}, headers=auth_headers)
    client.post(f"/logs/{TODAY}", json={"foodId": other.id, "quantity": 1}, headers=auth_headers)

    response = client.get(f"/logs/{TODAY}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["entries"]) == 2
    assert body["totals"]["calories"] == 200  # 95 + 105


def test_empty_day_has_zero_totals(client, auth_headers):
    response = client.get(f"/logs/{TODAY}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["entries"] == []
    assert response.json()["totals"]["calories"] == 0


def test_delete_entry_removes_it_from_day_log(client, auth_headers, sample_food):
    created = client.post(
        f"/logs/{TODAY}", json={"foodId": sample_food.id, "quantity": 1}, headers=auth_headers
    ).json()

    delete_response = client.delete(f"/logs/{TODAY}/{created['id']}", headers=auth_headers)
    assert delete_response.status_code == 204

    day_log = client.get(f"/logs/{TODAY}", headers=auth_headers).json()
    assert day_log["entries"] == []


def test_patch_rescales_quantity(client, auth_headers, sample_food):
    created = client.post(
        f"/logs/{TODAY}", json={"foodId": sample_food.id, "quantity": 1}, headers=auth_headers
    ).json()
    assert created["nutrients"]["calories"] == 95

    updated = client.patch(
        f"/logs/{TODAY}/{created['id']}", json={"quantity": 3}, headers=auth_headers
    ).json()
    assert updated["quantity"] == 3
    assert updated["nutrients"]["calories"] == 285  # 95 * 3


def test_patch_rescale_still_works_after_food_deleted(client, auth_headers, sample_food, db_session):
    created = client.post(
        f"/logs/{TODAY}", json={"foodId": sample_food.id, "quantity": 2}, headers=auth_headers
    ).json()

    # Simulate the referenced food being removed from the catalog entirely.
    db_session.delete(db_session.get(Food, sample_food.id))
    db_session.commit()

    updated = client.patch(
        f"/logs/{TODAY}/{created['id']}", json={"quantity": 4}, headers=auth_headers
    ).json()
    assert updated["foodId"] is None  # ondelete=SET NULL
    assert updated["nutrients"]["calories"] == 380  # stored 190 at qty=2, ratio 4/2=2 -> 380


def test_logged_dates_reflects_only_dates_with_entries(client, auth_headers, sample_food):
    client.post(f"/logs/{TODAY}", json={"foodId": sample_food.id, "quantity": 1}, headers=auth_headers)
    response = client.get("/logs/dates", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["dates"] == [TODAY]


def test_cross_user_isolation(client, auth_headers, sample_food):
    created = client.post(
        f"/logs/{TODAY}", json={"foodId": sample_food.id, "quantity": 1}, headers=auth_headers
    ).json()

    other_user_auth = signup_and_login(client, email="other@example.com", password="pw123456")
    other_headers = {"Authorization": f"Bearer {other_user_auth['token']}"}

    read_response = client.get(f"/logs/{TODAY}", headers=other_headers)
    assert read_response.json()["entries"] == []  # user A's entry isn't visible to user B

    delete_response = client.delete(f"/logs/{TODAY}/{created['id']}", headers=other_headers)
    assert delete_response.status_code == 404
