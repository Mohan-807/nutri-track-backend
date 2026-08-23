from datetime import datetime

from pydantic import Field

from app.models.chat_message import ChatMessage
from app.schemas.common import CamelModel


class ChatMessageIn(CamelModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(CamelModel):
    reply: str


class ChatHistoryMessageOut(CamelModel):
    id: int
    role: str
    content: str
    created_at: datetime


class ChatHistoryOut(CamelModel):
    messages: list[ChatHistoryMessageOut]


def chat_message_to_out(message: ChatMessage) -> ChatHistoryMessageOut:
    return ChatHistoryMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )
