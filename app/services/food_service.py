from sqlalchemy.orm import Session

from app.models.food import Food
from app.schemas.food import FoodCreateIn


def _normalize(value: str) -> str:
    return value.strip().lower()


def rank_foods(foods: list[Food], query: str | None) -> list[Food]:
    """Ported 1:1 from frontend/src/utils/foodFilter.js: prefix matches on name/alias rank above
    substring matches; an empty query returns every food, unranked."""
    normalized_query = _normalize(query or "")
    if not normalized_query:
        return foods

    scored: list[tuple[int, Food]] = []
    for food in foods:
        names = [_normalize(food.name), *(_normalize(alias) for alias in food.aliases or [])]
        is_prefix_match = any(name.startswith(normalized_query) for name in names)
        is_substring_match = any(normalized_query in name for name in names)
        if is_prefix_match:
            scored.append((0, food))
        elif is_substring_match:
            scored.append((1, food))

    scored.sort(key=lambda pair: pair[0])
    return [food for _, food in scored]


def create_food(db: Session, data: FoodCreateIn, *, created_by_user_id: int, category: str = "custom") -> Food:
    """Mirrors foodCatalogStore.addFood's defaults: category="custom", aliases=[]. The chat
    AI's add_food_to_catalog tool overrides `category` to "ai_estimated" — the manual Add Food
    dialog's values were entered by the person eating the food; the AI's are a guess from its
    own knowledge, and the two shouldn't be indistinguishable in a catalog every user searches."""
    food = Food(
        name=data.name.strip(),
        aliases=[],
        category=category,
        serving_label=data.serving_label.strip(),
        serving_grams=data.serving_grams,
        calories=data.calories,
        protein_g=data.protein_g,
        carbs_g=data.carbs_g,
        fat_g=data.fat_g,
        fiber_g=data.fiber_g,
        sugar_g=data.sugar_g,
        sodium_mg=data.sodium_mg,
        created_by_user_id=created_by_user_id,
    )
    db.add(food)
    db.commit()
    db.refresh(food)
    return food
