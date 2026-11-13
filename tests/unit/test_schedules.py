from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from mosaivue.models import Layout, Schedule
from mosaivue.services.schedules import schedule_matches, select_scheduled_layout


def scheduled(*, days=None, start="22:00", end="06:00", enabled=True):
    return Schedule(
        name="Night", layout_id="wall", days=[0] if days is None else days,
        start_time=start, end_time=end, enabled=enabled,
    )


@pytest.mark.parametrize("moment,expected", [
    ("2026-11-09T05:00:00", False),  # Monday before its start.
    ("2026-11-09T21:59:59", False),
    ("2026-11-09T22:00:00", True),
    ("2026-11-10T05:59:59", True),  # Tuesday belongs to Monday's window.
    ("2026-11-10T06:00:00", False),
    ("2026-11-10T22:00:00", False),
])
def test_overnight_schedule_uses_start_day(moment, expected):
    assert schedule_matches(scheduled(), datetime.fromisoformat(moment)) is expected


def test_sunday_window_wraps_into_monday():
    assert schedule_matches(scheduled(days=[6]), datetime(2026, 11, 9, 5, 30))


def test_equal_times_mean_full_day_from_selected_start():
    schedule = scheduled(start="08:00", end="08:00")
    assert not schedule_matches(schedule, datetime(2026, 11, 9, 7, 59))
    assert schedule_matches(schedule, datetime(2026, 11, 9, 8))
    assert schedule_matches(schedule, datetime(2026, 11, 10, 7, 59))
    assert not schedule_matches(schedule, datetime(2026, 11, 10, 8))


def test_adjacent_windows_do_not_overlap_at_end():
    morning = scheduled(start="08:00", end="12:00")
    afternoon = scheduled(start="12:00", end="17:00")
    moment = datetime(2026, 11, 9, 12)
    assert not schedule_matches(morning, moment)
    assert schedule_matches(afternoon, moment)
    afternoon.enabled = False
    assert not schedule_matches(afternoon, moment)


def test_schedule_selection_honors_priority_and_deterministic_ties(db):
    first = Layout(name="First")
    second = Layout(name="Second")
    db.add_all([first, second])
    db.flush()
    db.add_all([
        Schedule(id="b", name="Later", layout_id=second.id, days=[0], start_time="00:00", end_time="00:00", priority=2, created_at=datetime(2026, 1, 2)),
        Schedule(id="a", name="Earlier", layout_id=first.id, days=[0], start_time="00:00", end_time="00:00", priority=2, created_at=datetime(2026, 1, 1)),
    ])
    db.flush()
    assert select_scheduled_layout(db, datetime(2026, 11, 9, 15)) == first.id
    db.get(Schedule, "b").priority = 3
    db.flush()
    assert select_scheduled_layout(db, datetime(2026, 11, 9, 15)) == second.id


@pytest.mark.parametrize("invalid", [{"start_time": "25:00"}, {"start_time": "broken"}, {"days": None}])
def test_invalid_stored_schedule_does_not_suppress_valid_lower_priority_schedule(db, caplog, invalid):
    wall = Layout(name="Valid wall")
    db.add(wall)
    db.flush()
    malformed = Schedule(
        name="Legacy invalid schedule", layout_id=wall.id, days=[0],
        start_time="00:00", end_time="00:00", priority=10,
    )
    for key, value in invalid.items():
        setattr(malformed, key, value)
    valid = Schedule(
        name="Valid schedule", layout_id=wall.id, days=[0],
        start_time="00:00", end_time="00:00", priority=1,
    )
    db.add_all([malformed, valid])
    db.flush()
    assert select_scheduled_layout(db, datetime(2026, 11, 9, 15)) == wall.id
    assert "Skipping invalid stored schedule" in caplog.text


@pytest.mark.parametrize("fold", [0, 1])
def test_overnight_schedule_matches_both_repeated_local_clock_hours(fold):
    moment = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=fold)
    saturday_night = scheduled(days=[5], start="22:00", end="06:00")
    assert schedule_matches(saturday_night, moment)


def test_equal_times_follow_local_day_across_spring_clock_change():
    timezone = ZoneInfo("America/New_York")
    sunday = scheduled(days=[6], start="00:00", end="00:00")
    start = datetime(2026, 3, 8, tzinfo=timezone)
    end = datetime(2026, 3, 9, tzinfo=timezone)
    assert (end.timestamp() - start.timestamp()) / 3600 == 23
    assert schedule_matches(sunday, start)
    assert schedule_matches(sunday, datetime(2026, 3, 8, 23, 59, tzinfo=timezone))
    assert not schedule_matches(sunday, end)
