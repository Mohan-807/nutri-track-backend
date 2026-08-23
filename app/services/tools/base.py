from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from app.models.user import User


@dataclass(frozen=True)
class ToolSpec:
    """One registerable tool. `parameters` is a plain JSON schema (what the LLM sees). `execute`
    is responsible for validating its own `args` dict (via its own pydantic model — see each
    tool module) before doing anything else; a validation failure raises pydantic's
    ValidationError, which the generic dispatcher in chat_service.py catches for every tool the
    same way, so no tool needs its own try/except for bad arguments. `execute` always receives
    the real authenticated `User` from the current request, never a user id supplied by the
    model — that's what makes cross-user access structurally impossible, not just checked-for.

    `today` is the user's local calendar date (see chat_service.py's send_message_stream and
    ChatMessageIn.client_date) — passed explicitly as a parameter rather than read from
    request-scoped/thread-local state, because a streamed response's generator can genuinely
    resume on a different threadpool worker thread between yields (observed directly: a
    ContextVar set at the start of the generator was not reliably visible by the time a tool ran
    later in the same request). Tools that don't need a date (search_food,
    add_food_to_catalog) simply ignore it; it defaults to None so direct calls (unit tests)
    don't need to pass one."""

    name: str
    description: str
    parameters: dict
    execute: Callable[[Session, User, dict, date | None], dict]
