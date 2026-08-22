from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.models.profile import Profile
from app.schemas.profile import ProfileIn, ProfileOut, profile_to_out
from app.services.nutrient_calc import calculate_daily_targets

router = APIRouter(prefix="/profile", tags=["profile"])


def _apply_targets(profile: Profile, data: ProfileIn) -> None:
    """Shared by onboarding and update — both recompute bmi/bmr/tdee/targets from scratch,
    mirroring the frontend's buildProfile(), which has no distinction beyond onboarding_completed."""
    targets = calculate_daily_targets(
        weight_kg=data.weight_kg,
        height_cm=data.height_cm,
        age=data.age,
        gender=data.gender,
        activity_level=data.activity_level,
        goal=data.goal,
    )
    profile.height_cm = data.height_cm
    profile.weight_kg = data.weight_kg
    profile.age = data.age
    profile.gender = data.gender
    profile.activity_level = data.activity_level
    profile.goal = data.goal
    profile.bmi = targets.bmi
    profile.bmr = targets.bmr
    profile.tdee = targets.tdee
    profile.calories_target = targets.calories
    profile.protein_g_target = targets.protein_g
    profile.carbs_g_target = targets.carbs_g
    profile.fat_g_target = targets.fat_g
    profile.fiber_g_target = targets.fiber_g
    profile.sugar_max_g_target = targets.sugar_max_g
    profile.sodium_max_mg_target = targets.sodium_max_mg


@router.get("/me", response_model=ProfileOut)
def get_profile(current_user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet — complete onboarding first.")
    return profile_to_out(profile)


@router.post("/onboarding", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def complete_onboarding(data: ProfileIn, current_user: CurrentUser, db: DbSession) -> ProfileOut:
    existing = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Profile already exists — use PUT /profile/me to update."
        )

    profile = Profile(user_id=current_user.id, onboarding_completed=True)
    _apply_targets(profile, data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile_to_out(profile)


@router.put("/me", response_model=ProfileOut)
def update_profile(data: ProfileIn, current_user: CurrentUser, db: DbSession) -> ProfileOut:
    profile = db.query(Profile).filter(Profile.user_id == current_user.id).first()
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No profile yet — complete onboarding first.")

    _apply_targets(profile, data)
    db.commit()
    db.refresh(profile)
    return profile_to_out(profile)
