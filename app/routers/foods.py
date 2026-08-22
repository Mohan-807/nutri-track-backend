from fastapi import APIRouter, HTTPException, status

from app.dependencies import CurrentUser, DbSession
from app.models.food import Food
from app.schemas.food import FoodCreateIn, FoodListOut, FoodOut, food_to_out
from app.services.food_service import create_food, rank_foods

router = APIRouter(prefix="/foods", tags=["foods"])


@router.get("", response_model=FoodListOut)
def list_foods(current_user: CurrentUser, db: DbSession, query: str | None = None) -> FoodListOut:
    foods = db.query(Food).all()
    ranked = rank_foods(foods, query)
    return FoodListOut(results=[food_to_out(food) for food in ranked])


@router.get("/{food_id}", response_model=FoodOut)
def get_food(food_id: int, current_user: CurrentUser, db: DbSession) -> FoodOut:
    food = db.get(Food, food_id)
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Food not found.")
    return food_to_out(food)


@router.post("", response_model=FoodOut, status_code=status.HTTP_201_CREATED)
def create_food_endpoint(data: FoodCreateIn, current_user: CurrentUser, db: DbSession) -> FoodOut:
    food = create_food(db, data, created_by_user_id=current_user.id)
    return food_to_out(food)
