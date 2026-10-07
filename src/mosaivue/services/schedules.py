from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Schedule


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":", 1)
    return time(int(hours), int(minutes))


def schedule_matches(schedule: Schedule, moment: datetime) -> bool:
    if not schedule.enabled or moment.weekday() not in schedule.days:
        return False
    current = moment.time().replace(second=0, microsecond=0)
    start = _parse_time(schedule.start_time)
    end = _parse_time(schedule.end_time)
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def select_scheduled_layout(db: Session, moment: datetime) -> str | None:
    schedules = list(
        db.scalars(
            select(Schedule).where(Schedule.enabled.is_(True)).order_by(Schedule.priority.desc())
        )
    )
    for schedule in schedules:
        if schedule_matches(schedule, moment):
            return schedule.layout_id
    return None
