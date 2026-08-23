from datetime import date, datetime

from pydantic import Field

from app.models.chat_message import ChatMessage
from app.schemas.common import CamelModel


class ChatMessageIn(CamelModel):
    message: str = Field(min_length=1, max_length=4000)
    # The sender's local calendar date (frontend's dateUtils.todayKey()) — the backend has no
    # stored per-user timezone, so without this, a tool defaulting to "today" (log_food_entry,
    # get_day_totals) would use UTC's date, which disagrees with the user's actual day for hours
    # around midnight. Optional so older/other clients that omit it just fall back to UTC.
    client_date: date | None = None


class ChatMessageOut(CamelModel):
    reply: str


class ChatHistoryMessageOut(CamelModel):
    id: int
    role: str
    content: str
    created_at: datetime
    # Only populated on assistant messages (and null on rows written before multi-provider
    # support), so the UI can show which model produced a given reply.
    provider: str | None = None
    model: str | None = None


class ChatHistoryOut(CamelModel):
    messages: list[ChatHistoryMessageOut]


def chat_message_to_out(message: ChatMessage) -> ChatHistoryMessageOut:
    return ChatHistoryMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        provider=message.provider,
        model=message.model,
    )
