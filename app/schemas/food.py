from pydantic import Field

from app.models.food import Food
from app.schemas.common import CamelModel, NutrientsOut


class FoodCreateIn(CamelModel):
    """Mirrors AddCustomFoodDialog.jsx: name/servingLabel/calories required, everything else
    optional and defaults to 0 — the manual equivalent of what a future AI would submit."""

    name: str = Field(min_length=1, max_length=120)
    serving_label: str = Field(min_length=1, max_length=60)
    serving_grams: float = Field(default=0, ge=0)
    calories: float = Field(ge=0)
    protein_g: float = Field(default=0, ge=0)
    carbs_g: float = Field(default=0, ge=0)
    fat_g: float = Field(default=0, ge=0)
    fiber_g: float = Field(default=0, ge=0)
    sugar_g: float = Field(default=0, ge=0)
    sodium_mg: float = Field(default=0, ge=0)


class FoodOut(CamelModel):
    id: int
    name: str
    aliases: list[str]
    category: str
    serving_label: str
    serving_grams: float
    nutrients: NutrientsOut


class FoodListOut(CamelModel):
    results: list[FoodOut]


def food_to_out(food: Food) -> FoodOut:
    return FoodOut(
        id=food.id,
        name=food.name,
        aliases=food.aliases or [],
        category=food.category,
        serving_label=food.serving_label,
        serving_grams=food.serving_grams,
        nutrients=NutrientsOut(
            calories=food.calories,
            protein_g=food.protein_g,
            carbs_g=food.carbs_g,
            fat_g=food.fat_g,
            fiber_g=food.fiber_g,
            sugar_g=food.sugar_g,
            sodium_mg=food.sodium_mg,
        ),
    )
