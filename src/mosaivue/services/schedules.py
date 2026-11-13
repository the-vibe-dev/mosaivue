from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Schedule


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":", 1)
    return time(int(hours), int(minutes))


def schedule_matches(schedule: Schedule, moment: datetime) -> bool:
    if not schedule.enabled:
        return False
    current = moment.time().replace(second=0, microsecond=0)
    start = _parse_time(schedule.start_time)
    end = _parse_time(schedule.end_time)
    # Days belong to the start of a window. Monday 22:00–06:00 includes
    # Tuesday 05:00, not Monday 05:00. End times are exclusive so adjacent
    # windows do not overlap for an extra minute. Equal times mean 24 hours.
    if start < end:
        return moment.weekday() in schedule.days and start <= current < end
    if current >= start:
        return moment.weekday() in schedule.days
    if current < end or start == end:
        return (moment.weekday() - 1) % 7 in schedule.days
    return False


def select_scheduled_layout(db: Session, moment: datetime) -> str | None:
    schedules = list(
        db.scalars(
            select(Schedule).where(Schedule.enabled.is_(True)).order_by(
                Schedule.priority.desc(), Schedule.created_at.asc(), Schedule.id.asc()
            )
        )
    )
    for schedule in schedules:
        if schedule_matches(schedule, moment):
            return schedule.layout_id
    return None
