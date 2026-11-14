from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def samples():
    first = {
        "time_utc": "2026-11-14T00:00:00+00:00", "host": "wall", "run_id": "b5-reboot-1", "source_id": "source-digest",
        "renderer_service": {"state": "active", "pid": "10", "restarts": "0"},
        "web_service": {"state": "active", "pid": "11", "restarts": "0"}, "web_healthy": True,
        "renderer": {"state": "RUNNING", "version": "0.1.0b5", "backend": "gstreamer", "sink": "ximagesink", "uptime_seconds": 20,
                     "streams": {"fixed": {"camera_id": "a", "state": "LIVE", "frames": 300, "cuts": 0, "restarts": 0,
                                           "last_frame_age_seconds": 0.2}}},
    }
    last = copy.deepcopy(first)
    last["time_utc"] = "2026-11-14T00:01:00+00:00"
    last["renderer"]["uptime_seconds"] = 80
    last["renderer"]["streams"]["fixed"]["frames"] = 1500
    return [first, last]


def result(rows, **options):
    return script("analyze-soak").analyze(rows, min_hours=1 / 60, expected_streams=1, **options)


def test_advancing_live_frames_complete_only_the_sample_window():
    report = result(samples())
    assert report["runs"][0]["status"] == "sample_window_complete"
    assert report["runs"][0]["comparable_frame_intervals"] == 1
    assert "not hardware qualification" in report["limitation"]


def test_rotation_counter_reset_is_a_discontinuity_not_a_stall():
    rows = samples()
    rows[1]["renderer"]["streams"]["fixed"].update(camera_id="b", cuts=1, frames=12)
    run = result(rows)["runs"][0]
    assert run["status"] == "sample_window_complete"
    assert run["counter_discontinuities"] == 1
    assert run["comparable_frame_intervals"] == 0


def test_unchanged_feed_without_frame_progress_is_flagged():
    rows = samples()
    rows[1]["renderer"]["streams"]["fixed"].update(frames=300, last_frame_age_seconds=60)
    run = result(rows)["runs"][0]
    assert run["status"] == "review_required"
    assert any("did not advance" in issue for issue in run["issues"])
    assert any("last frame exceeds" in issue for issue in run["issues"])


def test_omx_live_state_does_not_claim_decoded_frame_proof():
    rows = samples()
    for row in rows:
        row["renderer"]["backend"] = "omxplayer"
        row["renderer"]["streams"]["fixed"].update(frames=0, last_frame_age_seconds=None)
    run = result(rows)["runs"][0]
    assert run["status"] == "sample_window_complete"
    assert run["comparable_frame_intervals"] == 0
    assert "no decoded-frame proof" in run["frame_evidence"]


def test_host_source_and_back_to_prior_source_do_not_merge_soak_windows():
    rows = samples()
    third = copy.deepcopy(rows[1])
    third["time_utc"] = "2026-11-14T00:02:00+00:00"
    rows[1]["source_id"] = "different-build"
    other_host = copy.deepcopy(third)
    other_host["host"] = "other-wall"
    report = result([*rows, third, other_host])
    assert len(report["runs"]) == 4
    assert all(run["status"] == "incomplete" for run in report["runs"])


def test_headless_to_physical_output_starts_a_new_sample_window():
    rows = samples()
    rows[0]["renderer"]["sink"] = "fakesink"
    report = result(rows)
    assert [run["sink"] for run in report["runs"]] == ["fakesink", "ximagesink"]
    assert all(run["status"] == "incomplete" for run in report["runs"])


def test_gaps_duplicate_times_service_restart_and_short_runs_are_not_accepted():
    rows = samples()
    rows[1]["time_utc"] = "2026-11-14T00:03:00+00:00"
    rows[1]["renderer_service"]["restarts"] = "1"
    rows[1]["renderer"]["uptime_seconds"] = 10
    report = result(rows)
    assert report["runs"][0]["gaps"] == 1
    assert report["runs"][0]["status"] == "review_required"
    assert any("uptime reset" in issue for issue in report["runs"][0]["issues"])
    duplicate = result([rows[0], rows[0]])["runs"][0]
    assert any("duplicate or out-of-order" in issue for issue in duplicate["issues"])
    assert result([rows[0]])["runs"][0]["status"] == "incomplete"


def test_legacy_unlabelled_or_missing_frame_data_is_incomplete():
    rows = samples()
    for row in rows:
        row.pop("run_id")
        row.pop("source_id")
        row["renderer"].pop("version")
        row["renderer"]["streams"]["fixed"].pop("last_frame_age_seconds")
    run = result(rows)["runs"][0]
    assert run["status"] == "incomplete"
    assert len(run["incomplete_reasons"]) == 2


def test_malformed_log_and_timestamp_are_reported_without_echoing_contents(tmp_path):
    path = tmp_path / "health.jsonl"
    path.write_text('{"private":broken}\n[]\n' + json.dumps(samples()[0]) + "\n")
    helper = script("analyze-soak")
    rows, errors = helper.read_samples([path])
    assert len(rows) == 1 and len(errors) == 2
    assert "private" not in str(errors)
    rows.append({"time_utc": "not-a-date"})
    assert len(result(rows)["input_errors"]) == 1


@pytest.mark.parametrize("threshold", [0, -1, float("nan"), float("inf")])
def test_invalid_time_threshold_cannot_produce_a_complete_window(threshold):
    with pytest.raises(ValueError, match="positive"):
        script("analyze-soak").analyze(samples(), min_hours=threshold)


def test_sampler_uses_installed_cli_override_and_records_version_without_source_uri(monkeypatch):
    helper = script("overnight-sample")
    monkeypatch.setattr(helper.os, "geteuid", lambda: 1000)
    calls = []
    def fake_command(*args, **kwargs):
        calls.append(args)
        raw = {"version": "0.1.0b5", "renderer": {"state": "RUNNING", "streams": {
            "one": {"camera_id": "camera-1", "state": "LIVE", "decoded_frames": 15, "source_uri": "private", "switch_count": 2}
        }}}
        return subprocess.CompletedProcess(args, 0, json.dumps(raw))
    monkeypatch.setattr(helper, "command", fake_command)
    observed = helper.renderer_status("/custom/bin/mosaivue")
    assert calls[0][0] == "/custom/bin/mosaivue"
    assert observed["version"] == "0.1.0b5"
    assert observed["streams"]["one"]["camera_id"] == "camera-1"
    assert "private" not in json.dumps(observed)


def test_sampler_handles_unavailable_renderer_and_empty_gpu_output(monkeypatch):
    helper = script("overnight-sample")
    monkeypatch.setattr(helper, "command", lambda *a, **k: subprocess.CompletedProcess(a, 0, '{"renderer":null}'))
    assert helper.renderer_status()["error"] == "invalid status response"
    monkeypatch.setattr(helper.shutil, "which", lambda value: "/bin/tool")
    monkeypatch.setattr(helper, "command", lambda *a, **k: subprocess.CompletedProcess(a, 0, ""))
    assert helper.gpu_status() == {"state": "unavailable"}
