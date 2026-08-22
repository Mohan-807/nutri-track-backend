from pydantic import Field

from app.schemas.common import CamelModel


class ChatMessageIn(CamelModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatMessageOut(CamelModel):
    reply: str
