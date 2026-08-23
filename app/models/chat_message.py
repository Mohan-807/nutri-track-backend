from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ChatMessage(Base):
    """One row per turn. No separate Conversation table — the app has a single implicit thread
    per user (mirrors the frontend's threadsByUser shape), so user_id is enough to scope
    history; a multi-conversation model isn't needed yet."""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_user_created", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Which AI actually produced this reply. Nullable because they're only meaningful on
    # role="assistant" rows (a user's own message has no model), and because rows written before
    # multi-provider support existed have no value to backfill with. Recorded per message rather
    # than as one global "current model" setting: with automatic failover the answer differs from
    # message to message, so a single mutable row would be wrong the moment a switch happened —
    # and it could never explain which model produced a reply you're looking at in history.
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="chat_messages")  # noqa: F821
