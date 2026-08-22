from datetime import date as date_type

from sqlalchemy.orm import Session

from app.models.food import Food
from app.models.log_entry import LogEntry
from app.services.nutrient_calc import round_half_up

NUTRIENT_FIELDS = ["calories", "protein_g", "carbs_g", "fat_g", "fiber_g", "sugar_g", "sodium_mg"]


def _round1(value: float) -> float:
    return round_half_up(value * 10) / 10


def create_entry(
    db: Session, *, user_id: int, log_date: date_type, food: Food, quantity: float
) -> LogEntry:
    """Server computes and scales every nutrient from the referenced Food row — a client can
    only submit foodId + quantity, never nutrient numbers directly (the deliberate upgrade over
    the old frontend mock, which had to trust the client since there was no server)."""
    entry = LogEntry(
        user_id=user_id,
        food_id=food.id,
        log_date=log_date,
        name=food.name,
        serving_label=food.serving_label,
        serving_grams=food.serving_grams,
        quantity=quantity,
        calories=_round1(food.calories * quantity),
        protein_g=_round1(food.protein_g * quantity),
        carbs_g=_round1(food.carbs_g * quantity),
        fat_g=_round1(food.fat_g * quantity),
        fiber_g=_round1(food.fiber_g * quantity),
        sugar_g=_round1(food.sugar_g * quantity),
        sodium_mg=_round1(food.sodium_mg * quantity),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def rescale_entry(entry: LogEntry, new_quantity: float) -> LogEntry:
    """Derives each nutrient's per-unit value from the entry's own currently-stored numbers
    (not a live join back to Food, which may have been deleted since — food_id is nullable) and
    reapplies the new quantity. Still fully server-computed, never client-submitted."""
    ratio = (new_quantity / entry.quantity) if entry.quantity else 0
    for field in NUTRIENT_FIELDS:
        setattr(entry, field, _round1(getattr(entry, field) * ratio))
    entry.quantity = new_quantity
    return entry


def day_totals(entries: list[LogEntry]) -> dict[str, float]:
    totals = dict.fromkeys(NUTRIENT_FIELDS, 0.0)
    for entry in entries:
        for field in NUTRIENT_FIELDS:
            totals[field] += getattr(entry, field)
    return {field: _round1(value) for field, value in totals.items()}
