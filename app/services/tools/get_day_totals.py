from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy.orm import Session

from app.models.log_entry import LogEntry
from app.models.user import User
from app.schemas.common import CamelModel
from app.services.log_service import day_totals
from app.services.tools.base import ToolSpec


class GetDayTotalsArgs(CamelModel):
    date: date_type | None = None


def _execute(db: Session, current_user: User, args: dict) -> dict:
    parsed = GetDayTotalsArgs.model_validate(args)
    # UTC "today" as the fallback when the model doesn't supply a date — same simplification the
    # rest of this app already lives with (no per-user timezone handling exists anywhere yet).
    log_date = parsed.date or datetime.now(UTC).date()

    # Scoped to current_user.id, never a user id from the model — same ownership boundary as
    # every REST endpoint (e.g. GET /logs/{date}).
    entries = (
        db.query(LogEntry)
        .filter(LogEntry.user_id == current_user.id, LogEntry.log_date == log_date)
        .all()
    )
    return {"date": log_date.isoformat(), "entryCount": len(entries), "totals": day_totals(entries)}


GET_DAY_TOTALS = ToolSpec(
    name="get_day_totals",
    description=(
        "Get the user's actual logged nutrition totals for a date (defaults to today). Use "
        "this to answer questions like 'how am I doing today?' or to confirm real numbers "
        "after logging something — never state specific totals from memory or estimation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "ISO date YYYY-MM-DD; omit for today"},
        },
        "required": [],
    },
    execute=_execute,
)
