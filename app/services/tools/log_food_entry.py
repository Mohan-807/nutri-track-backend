from datetime import UTC, datetime
from datetime import date as date_type

from pydantic import Field
from sqlalchemy.orm import Session

from app.models.food import Food
from app.models.user import User
from app.schemas.common import CamelModel
from app.schemas.log import entry_to_out
from app.services.log_service import create_entry
from app.services.tools.base import ToolSpec


class LogFoodEntryArgs(CamelModel):
    food_id: int
    # Required, not defaulted — this is the enforcement mechanism for "ask the user for the
    # quantity if they didn't give one": the model structurally cannot call this tool without a
    # quantity, so the system prompt's instruction to ask instead of guessing has teeth.
    # Upper-bounded deliberately tighter than the manual endpoint's LogEntryCreateIn (which has
    # no ceiling) — this value can come from a model's guess, not just a person typing into a
    # quantity stepper, so it gets its own defense-in-depth bound against a wild/hallucinated
    # number (e.g. mistaking grams for servings).
    quantity: float = Field(gt=0, le=1000)
    date: date_type | None = Field(default=None, description="Defaults to today if omitted")


def _execute(db: Session, current_user: User, args: dict, today: date_type | None = None) -> dict:
    parsed = LogFoodEntryArgs.model_validate(args)

    food = db.get(Food, parsed.food_id)
    if food is None:
        # Not an exception — a wrong/stale food id is a normal recoverable case the model should
        # react to (re-run search_food, or add_food_to_catalog), not a request-ending failure.
        return {"error": f"No food with id {parsed.food_id} exists. Search for it again first."}

    # `today` (the user's local calendar date, passed in by chat_service from the client's own
    # report) as the fallback when the model doesn't supply a date — falling back to UTC "today"
    # instead disagreed with the user's actual day for hours around midnight and silently
    # misfiled a real logged food under the wrong date. `today` is None only for direct calls
    # (unit tests) that don't go through chat_service.
    log_date = parsed.date or today or datetime.now(UTC).date()
    entry = create_entry(db, user_id=current_user.id, log_date=log_date, food=food, quantity=parsed.quantity)
    return {"entry": entry_to_out(entry).model_dump(mode="json", by_alias=True)}


LOG_FOOD_ENTRY = ToolSpec(
    name="log_food_entry",
    description=(
        "Log a quantity of a food to the user's nutrition log for a given date, updating their "
        "daily totals. The food must already exist — call search_food (and add_food_to_catalog "
        "if needed) first to get its id. If the user hasn't said how much they ate, ask them — "
        "never guess a quantity. `quantity` is in SERVINGS of that food's own servingGrams, not "
        "grams: if the user said 50g and the matched food's servingGrams is 158, quantity is "
        "50/158 ≈ 0.32 — compute this instead of adding a new food sized to exactly 50g."
    ),
    parameters={
        "type": "object",
        "properties": {
            "foodId": {"type": "integer", "description": "id from a prior search_food or add_food_to_catalog result"},
            "quantity": {
                "type": "number",
                "description": "Servings of the food's own servingGrams — e.g. requestedGrams / servingGrams, not a raw gram amount",
            },
            "date": {"type": "string", "description": "ISO date YYYY-MM-DD; omit for today"},
        },
        "required": ["foodId", "quantity"],
    },
    execute=_execute,
)
