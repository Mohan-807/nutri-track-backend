"""Ported 1:1 from frontend/src/utils/nutrientTargets.js + bmiCalculator.js. Keep the two in
sync if the frontend's formulas ever change."""

import math
from dataclasses import dataclass

from app.constants import ACTIVITY_MULTIPLIERS, GOAL_CONFIG, MIN_CALORIES, SODIUM_MAX_MG


def round_half_up(value: float) -> int:
    """Matches JS's Math.round (always rounds .5 away from zero / up), unlike Python's built-in
    round() which rounds half-to-even — needed so results stay numerically identical to the
    frontend's. Safe here because every value in this domain (weight, height, calories, ...) is
    non-negative."""
    return math.floor(value + 0.5)


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    if not weight_kg or not height_cm:
        return 0.0
    height_m = height_cm / 100
    return round_half_up((weight_kg / (height_m * height_m)) * 10) / 10


def calculate_bmr(weight_kg: float, height_cm: float, age: int, gender: str) -> int:
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    if gender == "male":
        return round_half_up(base + 5)
    if gender == "female":
        return round_half_up(base - 161)
    return round_half_up(base - 78)  # documented midpoint for gender == "other"


def calculate_tdee(bmr: int, activity_level: str) -> int:
    multiplier = ACTIVITY_MULTIPLIERS.get(activity_level, 1.2)
    return round_half_up(bmr * multiplier)


@dataclass
class DailyTargets:
    bmi: float
    bmr: int
    tdee: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    sugar_max_g: int
    sodium_max_mg: int


def calculate_daily_targets(
    *,
    weight_kg: float,
    height_cm: float,
    age: int,
    gender: str,
    activity_level: str,
    goal: str,
) -> DailyTargets:
    bmr = calculate_bmr(weight_kg, height_cm, age, gender)
    tdee = calculate_tdee(bmr, activity_level)
    bmi = calculate_bmi(weight_kg, height_cm)
    goal_config = GOAL_CONFIG.get(goal, GOAL_CONFIG["maintain"])

    calories = max(round_half_up(tdee + goal_config["calorie_adjustment"]), MIN_CALORIES)
    protein_g = round_half_up(goal_config["protein_per_kg"] * weight_kg)
    fat_g = round_half_up((calories * goal_config["fat_pct"]) / 9)
    carbs_g = max(round_half_up((calories - protein_g * 4 - fat_g * 9) / 4), 0)

    fiber_g = round_half_up((calories / 1000) * 14)  # IOM guideline: ~14g fiber per 1000 kcal
    sugar_max_g = round_half_up((calories * 0.10) / 4)  # WHO guideline: <=10% of kcal from sugar

    return DailyTargets(
        bmi=bmi,
        bmr=bmr,
        tdee=tdee,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
        fiber_g=fiber_g,
        sugar_max_g=sugar_max_g,
        sodium_max_mg=SODIUM_MAX_MG,
    )
