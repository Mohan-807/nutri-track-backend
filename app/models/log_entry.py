from datetime import date as date_type
from datetime import datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LogEntry(Base):
    __tablename__ = "log_entries"
    __table_args__ = (Index("ix_log_entries_user_date", "user_id", "log_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Nullable + ondelete=SET NULL: an entry survives the referenced food being edited/deleted,
    # since name/serving_label/nutrients below are a snapshot taken at log time, not a live join.
    food_id: Mapped[int | None] = mapped_column(
        ForeignKey("foods.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Local calendar date ('YYYY-MM-DD'), never a UTC-shiftable DateTime — mirrors the frontend's
    # dateUtils.js warning about avoiding Date#toISOString() for this exact reason.
    log_date: Mapped[date_type] = mapped_column(Date, nullable=False)

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    serving_label: Mapped[str] = mapped_column(String(60), nullable=False)
    serving_grams: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[float] = mapped_column(Float, nullable=False)

    # Server-computed and pre-scaled by quantity at write time — never trusted from the client.
    calories: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, nullable=False)
    carbs_g: Mapped[float] = mapped_column(Float, nullable=False)
    fat_g: Mapped[float] = mapped_column(Float, nullable=False)
    fiber_g: Mapped[float] = mapped_column(Float, nullable=False)
    sugar_g: Mapped[float] = mapped_column(Float, nullable=False)
    sodium_mg: Mapped[float] = mapped_column(Float, nullable=False)

    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="log_entries")  # noqa: F821
