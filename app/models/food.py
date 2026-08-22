from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Generic JSON everywhere (works on SQLite too), JSONB specifically when the dialect is
# Postgres — deliberately not postgresql.ARRAY(String), which SQLite can't represent at all.
ALIASES_TYPE = JSON().with_variant(postgresql.JSONB, "postgresql")


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(ALIASES_TYPE, nullable=False, default=list)
    category: Mapped[str] = mapped_column(String(30), index=True, nullable=False, default="custom")
    serving_label: Mapped[str] = mapped_column(String(60), nullable=False)
    serving_grams: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sugar_g: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    sodium_mg: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    # Null for seeded catalog foods; set to the submitter's user id for manually-added foods.
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
