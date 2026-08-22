"""Mirrors frontend/src/constants/activityLevels.js and goals.js exactly — keep these two
files in sync if the frontend's numbers ever change."""

from typing import Literal

Gender = Literal["male", "female", "other"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
Goal = Literal["lose", "maintain", "gain"]

ACTIVITY_MULTIPLIERS: dict[str, float] = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}

# calorie_adjustment: added to TDEE. protein_per_kg: g of protein per kg bodyweight.
# fat_pct: fraction of daily calories from fat.
GOAL_CONFIG: dict[str, dict[str, float]] = {
    "lose": {"calorie_adjustment": -500, "protein_per_kg": 2.0, "fat_pct": 0.25},
    "maintain": {"calorie_adjustment": 0, "protein_per_kg": 1.6, "fat_pct": 0.30},
    "gain": {"calorie_adjustment": 300, "protein_per_kg": 1.8, "fat_pct": 0.25},
}

MIN_CALORIES = 1200
SODIUM_MAX_MG = 2300
