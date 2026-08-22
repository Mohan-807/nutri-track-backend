from fastapi import APIRouter

from app.dependencies import CurrentUser
from app.schemas.chat import ChatMessageIn, ChatMessageOut
from app.services.llm_service import generate_reply

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatMessageOut)
def send_message(data: ChatMessageIn, current_user: CurrentUser) -> ChatMessageOut:
    """Smallest possible LLM connection: one message in, one Gemini response out. Still behind
    the same auth as every other endpoint (CurrentUser), but deliberately no conversation
    history, no tools, and no persistence yet — those are later, separate steps."""
    reply = generate_reply(data.message)
    return ChatMessageOut(reply=reply)
