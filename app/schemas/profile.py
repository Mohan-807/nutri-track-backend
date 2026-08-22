from datetime import datetime

from pydantic import Field

from app.constants import ActivityLevel, Gender, Goal
from app.models.profile import Profile
from app.schemas.common import CamelModel, TargetsOut


class ProfileIn(CamelModel):
    """Shared shape for both onboarding (create) and update — the frontend's own
    completeOnboarding/updateProfile draw from the same form fields."""

    height_cm: float = Field(gt=0)
    weight_kg: float = Field(gt=0)
    age: int = Field(gt=0, lt=150)
    gender: Gender
    activity_level: ActivityLevel
    goal: Goal


class ProfileOut(CamelModel):
    height_cm: float
    weight_kg: float
    age: int
    gender: str
    activity_level: str
    goal: str
    onboarding_completed: bool
    bmi: float
    bmr: int
    tdee: int
    targets: TargetsOut
    updated_at: datetime


def profile_to_out(profile: Profile) -> ProfileOut:
    """DB columns are flat (calories_target, protein_g_target, ...); nested into `targets` only
    at this response-mapping layer."""
    return ProfileOut(
        height_cm=profile.height_cm,
        weight_kg=profile.weight_kg,
        age=profile.age,
        gender=profile.gender,
        activity_level=profile.activity_level,
        goal=profile.goal,
        onboarding_completed=profile.onboarding_completed,
        bmi=profile.bmi,
        bmr=profile.bmr,
        tdee=profile.tdee,
        targets=TargetsOut(
            calories=profile.calories_target,
            protein_g=profile.protein_g_target,
            carbs_g=profile.carbs_g_target,
            fat_g=profile.fat_g_target,
            fiber_g=profile.fiber_g_target,
            sugar_max_g=profile.sugar_max_g_target,
            sodium_max_mg=profile.sodium_max_mg_target,
        ),
        updated_at=profile.updated_at,
    )
