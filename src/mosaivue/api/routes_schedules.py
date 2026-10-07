from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..models import Layout, Schedule
from ..schemas import ScheduleIn
from .dependencies import Auth, CSRF, DB

router = APIRouter(prefix="/schedules", tags=["schedules"])


def serialize(item: Schedule) -> dict[str, object]:
    return {
        "id": item.id,
        "name": item.name,
        "enabled": item.enabled,
        "layout_id": item.layout_id,
        "days": item.days,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "priority": item.priority,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("")
def list_schedules(db: DB, _: Auth) -> list[dict[str, object]]:
    return [serialize(item) for item in db.scalars(select(Schedule).order_by(Schedule.priority.desc()))]


@router.post("", status_code=201)
async def create_schedule(payload: ScheduleIn, request: Request, db: DB, _: CSRF) -> dict[str, object]:
    if db.get(Layout, payload.layout_id) is None:
        raise HTTPException(status_code=422, detail="Layout not found")
    item = Schedule(**payload.model_dump())
    db.add(item)
    try:
        db.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="A schedule with this name already exists") from exc
    result = serialize(item)
    await request.app.state.events.publish("schedule.changed", result)
    return result


@router.put("/{schedule_id}")
async def update_schedule(
    schedule_id: str, payload: ScheduleIn, request: Request, db: DB, _: CSRF
) -> dict[str, object]:
    item = db.get(Schedule, schedule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if db.get(Layout, payload.layout_id) is None:
        raise HTTPException(status_code=422, detail="Layout not found")
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    result = serialize(item)
    await request.app.state.events.publish("schedule.changed", result)
    return result


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: str, db: DB, _: CSRF) -> Response:
    item = db.get(Schedule, schedule_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Schedule not found")
    db.delete(item)
    return Response(status_code=204)
