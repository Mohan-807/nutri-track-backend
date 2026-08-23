import pytest
from pydantic import ValidationError

from app.models.user import User
from app.services.tools.add_food_to_catalog import ADD_FOOD_TO_CATALOG
from app.services.tools.get_day_totals import GET_DAY_TOTALS
from app.services.tools.log_food_entry import LOG_FOOD_ENTRY
from app.services.tools.search_food import SEARCH_FOOD


@pytest.fixture()
def user(db_session):
    user = User(email="tool-test@example.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_search_food_finds_by_name(db_session, user, sample_food):
    result = SEARCH_FOOD.execute(db_session, user, {"query": "apple"})
    assert result["results"][0]["name"] == sample_food.name


def test_search_food_no_match_returns_empty_not_error(db_session, user, sample_food):
    result = SEARCH_FOOD.execute(db_session, user, {"query": "nonexistent-xyz"})
    assert result["results"] == []


def test_search_food_rejects_missing_query(db_session, user):
    with pytest.raises(ValidationError):
        SEARCH_FOOD.execute(db_session, user, {})


def test_add_food_to_catalog_creates_food(db_session, user):
    result = ADD_FOOD_TO_CATALOG.execute(
        db_session, user, {"name": "Test Smoothie", "servingLabel": "1 cup", "calories": 200}
    )
    assert result["food"]["name"] == "Test Smoothie"
    assert result["food"]["nutrients"]["calories"] == 200


def test_add_food_to_catalog_tags_as_ai_estimated(db_session, user):
    result = ADD_FOOD_TO_CATALOG.execute(
        db_session, user, {"name": "Mystery Bar", "servingLabel": "1 bar", "calories": 150}
    )
    assert result["food"]["category"] == "ai_estimated"


def test_add_food_to_catalog_rejects_implausible_calories(db_session, user):
    with pytest.raises(ValidationError):
        ADD_FOOD_TO_CATALOG.execute(
            db_session, user, {"name": "Suspicious", "servingLabel": "1 serving", "calories": 999_999}
        )


def test_add_food_to_catalog_rejects_negative_macro(db_session, user):
    with pytest.raises(ValidationError):
        ADD_FOOD_TO_CATALOG.execute(
            db_session,
            user,
            {"name": "Bad Data", "servingLabel": "1 serving", "calories": 100, "proteinG": -5},
        )


def test_log_food_entry_requires_quantity(db_session, user, sample_food):
    with pytest.raises(ValidationError):
        LOG_FOOD_ENTRY.execute(db_session, user, {"foodId": sample_food.id})


def test_log_food_entry_rejects_zero_quantity(db_session, user, sample_food):
    with pytest.raises(ValidationError):
        LOG_FOOD_ENTRY.execute(db_session, user, {"foodId": sample_food.id, "quantity": 0})


def test_log_food_entry_rejects_implausible_quantity(db_session, user, sample_food):
    with pytest.raises(ValidationError):
        LOG_FOOD_ENTRY.execute(db_session, user, {"foodId": sample_food.id, "quantity": 100_000})


def test_log_food_entry_logs_and_scales_nutrients(db_session, user, sample_food):
    result = LOG_FOOD_ENTRY.execute(db_session, user, {"foodId": sample_food.id, "quantity": 2})
    assert result["entry"]["quantity"] == 2
    assert result["entry"]["nutrients"]["calories"] == sample_food.calories * 2


def test_log_food_entry_unknown_food_returns_error_not_exception(db_session, user):
    result = LOG_FOOD_ENTRY.execute(db_session, user, {"foodId": 999_999, "quantity": 1})
    assert "error" in result


def test_get_day_totals_reflects_logged_entries(db_session, user, sample_food):
    LOG_FOOD_ENTRY.execute(db_session, user, {"foodId": sample_food.id, "quantity": 1})
    result = GET_DAY_TOTALS.execute(db_session, user, {})
    assert result["entryCount"] == 1
    assert result["totals"]["calories"] == sample_food.calories


def test_get_day_totals_scoped_to_user(db_session, sample_food):
    user1 = User(email="tool-u1@example.com", password_hash="x")
    user2 = User(email="tool-u2@example.com", password_hash="x")
    db_session.add_all([user1, user2])
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)

    LOG_FOOD_ENTRY.execute(db_session, user1, {"foodId": sample_food.id, "quantity": 1})

    assert GET_DAY_TOTALS.execute(db_session, user1, {})["entryCount"] == 1
    assert GET_DAY_TOTALS.execute(db_session, user2, {})["entryCount"] == 0
