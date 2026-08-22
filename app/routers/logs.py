from datetime import date as date_type

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from app.dependencies import CurrentUser, DbSession
from app.models.food import Food
from app.models.log_entry import LogEntry
from app.schemas.common import NutrientsOut
from app.schemas.log import (
    DayLogOut,
    LogEntryCreateIn,
    LogEntryOut,
    LogEntryUpdateIn,
    LoggedDatesOut,
    entry_to_out,
)
from app.services.log_service import create_entry, day_totals, rescale_entry

router = APIRouter(prefix="/logs", tags=["logs"])


def _get_owned_entry(db: Session, user_id: int, log_date: date_type, entry_id: int) -> LogEntry:
    entry = db.get(LogEntry, entry_id)
    if entry is None or entry.user_id != user_id or entry.log_date != log_date:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Log entry not found.")
    return entry


# Registered before "/{log_date}" — Starlette matches routes in registration order, so this
# literal path must come first or "/logs/dates" would be swallowed by the dynamic date route.
@router.get("/dates", response_model=LoggedDatesOut)
def list_logged_dates(current_user: CurrentUser, db: DbSession) -> LoggedDatesOut:
    rows = (
        db.query(LogEntry.log_date)
        .filter(LogEntry.user_id == current_user.id)
        .distinct()
        .order_by(LogEntry.log_date)
        .all()
    )
    return LoggedDatesOut(dates=[row[0] for row in rows])


@router.get("/{log_date}", response_model=DayLogOut)
def get_day_log(log_date: date_type, current_user: CurrentUser, db: DbSession) -> DayLogOut:
    entries = (
        db.query(LogEntry)
        .filter(LogEntry.user_id == current_user.id, LogEntry.log_date == log_date)
        .order_by(LogEntry.logged_at)
        .all()
    )
    totals = day_totals(entries)
    return DayLogOut(date=log_date, entries=[entry_to_out(e) for e in entries], totals=NutrientsOut(**totals))


@router.post("/{log_date}", response_model=LogEntryOut, status_code=status.HTTP_201_CREATED)
def add_log_entry(
    log_date: date_type, data: LogEntryCreateIn, current_user: CurrentUser, db: DbSession
) -> LogEntryOut:
    food = db.get(Food, data.food_id)
    if food is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Food not found.")

    entry = create_entry(db, user_id=current_user.id, log_date=log_date, food=food, quantity=data.quantity)
    return entry_to_out(entry)


@router.patch("/{log_date}/{entry_id}", response_model=LogEntryOut)
def update_log_entry(
    log_date: date_type,
    entry_id: int,
    data: LogEntryUpdateIn,
    current_user: CurrentUser,
    db: DbSession,
) -> LogEntryOut:
    entry = _get_owned_entry(db, current_user.id, log_date, entry_id)
    rescale_entry(entry, data.quantity)
    db.commit()
    db.refresh(entry)
    return entry_to_out(entry)


@router.delete("/{log_date}/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log_entry(
    log_date: date_type, entry_id: int, current_user: CurrentUser, db: DbSession
) -> None:
    entry = _get_owned_entry(db, current_user.id, log_date, entry_id)
    db.delete(entry)
    db.commit()
