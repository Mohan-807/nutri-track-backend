from pydantic import Field
from sqlalchemy.orm import Session

from app.models.food import Food
from app.models.user import User
from app.schemas.common import CamelModel
from app.schemas.food import food_to_out
from app.services.food_service import rank_foods
from app.services.tools.base import ToolSpec

MAX_RESULTS = 5


class SearchFoodArgs(CamelModel):
    query: str = Field(min_length=1, max_length=120)


def _execute(db: Session, current_user: User, args: dict) -> dict:
    parsed = SearchFoodArgs.model_validate(args)
    # Read-only, no ownership filter — mirrors GET /foods, which lets every user search the
    # whole shared catalog (their own custom foods included), not just their own.
    foods = db.query(Food).all()
    ranked = rank_foods(foods, parsed.query)[:MAX_RESULTS]
    return {"results": [food_to_out(food).model_dump(mode="json", by_alias=True) for food in ranked]}


SEARCH_FOOD = ToolSpec(
    name="search_food",
    description=(
        "Search the existing food catalog by name. Always call this first whenever the user "
        "mentions eating or logging a food, before assuming it needs to be added — reusing an "
        "existing catalog entry is strongly preferred over re-estimating nutrition from "
        "scratch. Returns up to 5 ranked matches, each with an id and its nutrition per serving."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Food name to search for, e.g. 'apple' or 'grilled chicken'"},
        },
        "required": ["query"],
    },
    execute=_execute,
)
