from datetime import date

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


def _execute(db: Session, current_user: User, args: dict, today: date | None = None) -> dict:
    # `today` (the user's local date) is part of every tool's uniform call signature (see
    # ToolSpec in base.py) but unused here — a search has no date-dependent behavior.
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
        "mentions eating or logging a food, before assuming it needs to be added. Search with "
        "the core food word (e.g. 'rice', not 'cooked white rice grams') — a broader query "
        "surfaces more candidates. Each result includes servingGrams: if a result's food is a "
        "match for what the user described (even a different preparation, like 'cooked rice' "
        "vs a result named 'White Rice'), reuse it via log_food_entry with quantity computed as "
        "requestedGrams / result.servingGrams — do NOT call add_food_to_catalog just because the "
        "requested amount or wording differs from an existing entry."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The core food name only, e.g. 'apple' or 'chicken' — not the full phrase the user said"},
        },
        "required": ["query"],
    },
    execute=_execute,
)
