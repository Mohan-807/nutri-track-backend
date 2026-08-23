import json
from collections.abc import Iterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.dependencies import CurrentUser, DbSession
from app.schemas.chat import ChatHistoryOut, ChatMessageIn, chat_message_to_out
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("", response_model=ChatHistoryOut)
def get_history(current_user: CurrentUser, db: DbSession) -> ChatHistoryOut:
    messages = chat_service.get_history(db, current_user.id)
    return ChatHistoryOut(messages=[chat_message_to_out(m) for m in messages])


def _sse_encode(events: Iterator[dict]) -> Iterator[str]:
    """Standard SSE wire format: `event: <type>` names the event for EventSource-style listeners,
    `data: <json>` carries the payload; the blank line terminates each event. chat_service never
    knows this encoding exists — it only ever yields plain dicts."""
    for event in events:
        yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


@router.post("")
def send_message(data: ChatMessageIn, current_user: CurrentUser, db: DbSession) -> StreamingResponse:
    """Streams the reply as Server-Sent Events instead of one JSON blob — see
    chat_service.send_message_stream's docstring for the event types (chunk/tool_call/
    tool_result/done/error). No tools skipped, no history skipped: this is the same
    conversation-aware, tool-using pipeline as before, just delivered incrementally."""
    events = chat_service.send_message_stream(db, current_user.id, data.message)
    return StreamingResponse(_sse_encode(events), media_type="text/event-stream")
