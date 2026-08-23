from collections.abc import Callable
from dataclasses import dataclass

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
    model — that's what makes cross-user access structurally impossible, not just checked-for."""

    name: str
    description: str
    parameters: dict
    execute: Callable[[Session, User, dict], dict]
