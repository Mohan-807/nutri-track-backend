from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base for every request/response schema: JSON keys are camelCase (heightCm) to match the
    frontend's existing field names, while Python/DB stay snake_case (height_cm)."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # also accept snake_case bodies, not just camelCase
        from_attributes=True,
    )


class NutrientsOut(CamelModel):
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    sugar_g: float
    sodium_mg: float


class TargetsOut(CamelModel):
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
    sugar_max_g: int
    sodium_max_mg: int
