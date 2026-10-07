from __future__ import annotations

from pathlib import Path

from mosaivue.services.migration_displaycameras import build_plan, parse_shell_assignments


def test_shell_parser_handles_multiline_arrays() -> None:
    parsed = parse_shell_assignments(
        '''
        camera_names=("Front Door" "Garage")
        camera_feeds=(
          "rtsp://viewer:pass@192.0.2.20/front"
          "rtsp://viewer:pass@192.0.2.21/garage"
        )
        windows=("0,0,960,1080" "960,0,1920,1080")
        '''
    )
    assert parsed["camera_names"] == ["Front Door", "Garage"]
    assert len(parsed["camera_feeds"]) == 2


def test_migration_normalizes_absolute_rectangles(tmp_path: Path) -> None:
    config = tmp_path / "layout.conf.1080p"
    config.write_text(
        '''camera_names=("Front" "Garage")
        camera_feeds=("rtsp://a:b@192.0.2.20/front" "rtsp://a:b@192.0.2.21/garage")
        windows=("0,0,960,1080" "960,0,1920,1080")
        resolution="1920x1080"
        ''',
        encoding="utf-8",
    )
    plan = build_plan([config])
    assert len(plan.cameras) == 2
    assert len(plan.layouts) == 1
    slots = plan.layouts[0].data.slots
    assert slots[0].width == .5
    assert slots[1].x == .5


def test_migration_handles_displaycameras_named_windows_and_continuations(tmp_path: Path) -> None:
    config = tmp_path / "layout.conf.default"
    config.write_text(
        '''windows=(left right)
        window_positions=(
          # Left tile
          "0 0 960 1080" \\
          # Right tile
          "960 0 1920 1080" \\
        )
        camera_names=(Front Garage)
        camera_feeds=( \\
          "rtsp://192.0.2.20/front" \\
          "rtsp://192.0.2.21/garage" \\
        )
        ''',
        encoding="utf-8",
    )
    plan = build_plan([config])
    assert len(plan.cameras) == 2
    assert len(plan.layouts) == 1
    assert len(plan.layouts[0].data.slots) == 2
    assert plan.warnings == []
