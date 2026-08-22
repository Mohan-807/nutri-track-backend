from app.models.food import Food


def _seed(db_session, name, aliases=None):
    food = Food(
        name=name,
        aliases=aliases or [],
        category="fruit",
        serving_label="1 unit",
        serving_grams=100,
        calories=50,
        protein_g=1,
        carbs_g=10,
        fat_g=0,
        fiber_g=1,
        sugar_g=5,
        sodium_mg=1,
    )
    db_session.add(food)
    db_session.commit()
    db_session.refresh(food)
    return food


def test_empty_query_returns_everything(client, auth_headers, db_session):
    _seed(db_session, "Apple")
    _seed(db_session, "Banana")
    response = client.get("/foods", headers=auth_headers)
    assert response.status_code == 200
    names = {food["name"] for food in response.json()["results"]}
    assert names == {"Apple", "Banana"}


def test_prefix_match_ranks_above_substring_match(client, auth_headers, db_session):
    # "pineapple" contains "apple" as a substring but doesn't start with it — mirrors the
    # frontend's real apple/pineapple example verified during manual testing.
    _seed(db_session, "Pineapple")
    _seed(db_session, "Apple")

    response = client.get("/foods", params={"query": "apple"}, headers=auth_headers)
    assert response.status_code == 200
    names = [food["name"] for food in response.json()["results"]]
    assert names == ["Apple", "Pineapple"]


def test_alias_match(client, auth_headers, db_session):
    _seed(db_session, "Bell Pepper", aliases=["capsicum"])
    response = client.get("/foods", params={"query": "capsicum"}, headers=auth_headers)
    assert [food["name"] for food in response.json()["results"]] == ["Bell Pepper"]


def test_no_match_returns_empty_results(client, auth_headers, db_session):
    _seed(db_session, "Apple")
    response = client.get("/foods", params={"query": "xyz-nonexistent"}, headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_get_food_by_id(client, auth_headers, sample_food):
    response = client.get(f"/foods/{sample_food.id}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["name"] == "Test Apple"


def test_get_food_missing_is_404(client, auth_headers):
    response = client.get("/foods/999999", headers=auth_headers)
    assert response.status_code == 404


def test_create_food_applies_defaults(client, auth_headers):
    response = client.post(
        "/foods",
        json={"name": "Homemade Granola", "servingLabel": "1 cup (150g)", "calories": 220},
        headers=auth_headers,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["category"] == "custom"
    assert body["aliases"] == []
    assert body["nutrients"]["proteinG"] == 0
    assert body["nutrients"]["sodiumMg"] == 0


def test_create_food_with_full_nutrients(client, auth_headers):
    response = client.post(
        "/foods",
        json={
            "name": "Protein Pancakes",
            "servingLabel": "2 pancakes (120g)",
            "calories": 280,
            "proteinG": 22,
            "carbsG": 30,
            "fatG": 8,
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    nutrients = response.json()["nutrients"]
    assert nutrients["proteinG"] == 22
    assert nutrients["carbsG"] == 30
    assert nutrients["fatG"] == 8


def test_create_food_requires_name_serving_calories(client, auth_headers):
    response = client.post("/foods", json={"name": "Missing Fields"}, headers=auth_headers)
    assert response.status_code == 422
