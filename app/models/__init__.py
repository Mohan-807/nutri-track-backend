"""Importing every model here ensures Base.metadata sees all four tables (needed by both
Base.metadata.create_all() in tests and Alembic's autogenerate) and that the string-based
relationship forward references (e.g. "Profile", "LogEntry") resolve correctly."""

from app.models.food import Food
from app.models.log_entry import LogEntry
from app.models.profile import Profile
from app.models.user import User

__all__ = ["Food", "LogEntry", "Profile", "User"]
