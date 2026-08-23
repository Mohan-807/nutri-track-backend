from pydantic import Field
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.food import FoodCreateIn, food_to_out
from app.services.food_service import create_food
from app.services.tools.base import ToolSpec

# Plausibility bounds for AI-*estimated* nutrition data. The model is never trusted blindly here:
# these catch an obviously-wrong guess (a typo'd extra zero, a unit mix-up) before it lands in a
# shared catalog that every user's search_food and manual Add Food page will draw from.
MAX_CALORIES_PER_SERVING = 5000
MAX_MACRO_GRAMS_PER_SERVING = 1000
MAX_SODIUM_MG_PER_SERVING = 50000


class AddFoodToCatalogArgs(FoodCreateIn):
    """Reuses FoodCreateIn's fields/aliases as-is (name/servingLabel/calories required, macros
    optional, defaulting to 0) but tightens the calorie/macro ranges specifically for
    AI-estimated values — a human filling out the manual Add Food form is trusted with the
    looser bounds FoodCreateIn already enforces; an LLM guessing from its own knowledge isn't."""

    calories: float = Field(ge=0, le=MAX_CALORIES_PER_SERVING)
    protein_g: float = Field(default=0, ge=0, le=MAX_MACRO_GRAMS_PER_SERVING)
    carbs_g: float = Field(default=0, ge=0, le=MAX_MACRO_GRAMS_PER_SERVING)
    fat_g: float = Field(default=0, ge=0, le=MAX_MACRO_GRAMS_PER_SERVING)
    fiber_g: float = Field(default=0, ge=0, le=MAX_MACRO_GRAMS_PER_SERVING)
    sugar_g: float = Field(default=0, ge=0, le=MAX_MACRO_GRAMS_PER_SERVING)
    sodium_mg: float = Field(default=0, ge=0, le=MAX_SODIUM_MG_PER_SERVING)


def _execute(db: Session, current_user: User, args: dict) -> dict:
    parsed = AddFoodToCatalogArgs.model_validate(args)
    # Tagged distinctly from manually-entered foods (category="custom") — this is a model's
    # guess at nutrition facts, not something the eater looked up or measured, and it's about to
    # join a catalog every other user's search_food/Add Food page also draws from.
    food = create_food(db, parsed, created_by_user_id=current_user.id, category="ai_estimated")
    return {"food": food_to_out(food).model_dump(mode="json", by_alias=True)}


ADD_FOOD_TO_CATALOG = ToolSpec(
    name="add_food_to_catalog",
    description=(
        "Add a new food to the catalog. Only call this after search_food has already been "
        "called and returned no good match — never skip straight to this. Estimate typical "
        "nutrition values for one reasonable serving using your own knowledge; the backend "
        "validates the numbers are plausible before saving them, and the food becomes "
        "immediately available to log via log_food_entry."
    ),
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "servingLabel": {"type": "string", "description": "e.g. '1 medium (182g)' or '1 cup'"},
            "calories": {"type": "number", "description": "Calories per one serving"},
            "proteinG": {"type": "number"},
            "carbsG": {"type": "number"},
            "fatG": {"type": "number"},
            "fiberG": {"type": "number"},
            "sugarG": {"type": "number"},
            "sodiumMg": {"type": "number"},
        },
        "required": ["name", "servingLabel", "calories"],
    },
    execute=_execute,
)
