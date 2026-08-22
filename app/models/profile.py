from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Profile(Base):
    """One row per user (enforced by the unique constraint on user_id). gender/activity_level/
    goal are plain strings validated via Pydantic Literal at the API boundary, not native
    Postgres ENUM columns — keeps the same model portable to SQLite for tests."""

    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    activity_level: Mapped[str] = mapped_column(String(20), nullable=False)
    goal: Mapped[str] = mapped_column(String(10), nullable=False)
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    bmi: Mapped[float] = mapped_column(Float, nullable=False)
    bmr: Mapped[int] = mapped_column(Integer, nullable=False)
    tdee: Mapped[int] = mapped_column(Integer, nullable=False)

    # Flattened here (queryable, simple migrations); nested back into a `targets` object only
    # at the Pydantic response layer (see schemas/profile.py).
    calories_target: Mapped[int] = mapped_column(Integer, nullable=False)
    protein_g_target: Mapped[int] = mapped_column(Integer, nullable=False)
    carbs_g_target: Mapped[int] = mapped_column(Integer, nullable=False)
    fat_g_target: Mapped[int] = mapped_column(Integer, nullable=False)
    fiber_g_target: Mapped[int] = mapped_column(Integer, nullable=False)
    sugar_max_g_target: Mapped[int] = mapped_column(Integer, nullable=False)
    sodium_max_mg_target: Mapped[int] = mapped_column(Integer, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="profile")  # noqa: F821
