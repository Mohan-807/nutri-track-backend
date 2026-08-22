from datetime import date, datetime

from pydantic import Field

from app.models.log_entry import LogEntry
from app.schemas.common import CamelModel, NutrientsOut


class LogEntryCreateIn(CamelModel):
    food_id: int
    quantity: float = Field(gt=0)


class LogEntryUpdateIn(CamelModel):
    quantity: float = Field(gt=0)


class LogEntryOut(CamelModel):
    id: int
    food_id: int | None
    name: str
    serving_label: str
    serving_grams: float
    quantity: float
    nutrients: NutrientsOut
    logged_at: datetime


class DayLogOut(CamelModel):
    date: date
    entries: list[LogEntryOut]
    totals: NutrientsOut


class LoggedDatesOut(CamelModel):
    dates: list[date]


def entry_to_out(entry: LogEntry) -> LogEntryOut:
    return LogEntryOut(
        id=entry.id,
        food_id=entry.food_id,
        name=entry.name,
        serving_label=entry.serving_label,
        serving_grams=entry.serving_grams,
        quantity=entry.quantity,
        nutrients=NutrientsOut(
            calories=entry.calories,
            protein_g=entry.protein_g,
            carbs_g=entry.carbs_g,
            fat_g=entry.fat_g,
            fiber_g=entry.fiber_g,
            sugar_g=entry.sugar_g,
            sodium_mg=entry.sodium_mg,
        ),
        logged_at=entry.logged_at,
    )
