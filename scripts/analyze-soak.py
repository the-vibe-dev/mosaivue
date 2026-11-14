#!/usr/bin/env python3
"""Summarize sampled appliance health without treating rotation resets as frozen video.

This validates observation coverage, not physical picture quality or hardware qualification.
Only stdlib is used so the helper also runs on an appliance's Python 3.9 interpreter.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path


def number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_samples(paths: list[Path]) -> tuple[list[dict], list[str]]:
    records, errors = [], []
    for path in paths:
        try:
            with path.open(encoding="utf-8") as stream:
                for line_no, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        if not isinstance(record, dict):
                            raise ValueError("object required")
                        records.append(record)
                    except ValueError:
                        errors.append(f"{path.name}:{line_no}: invalid JSON object")
        except (OSError, UnicodeError):
            errors.append(f"{path.name}: cannot read UTF-8 samples")
    return records, errors


def analyze(
    records: list[dict], *, min_hours: float = 24, max_gap: float = 90,
    max_frame_age: float = 30, expected_streams: int | None = None,
) -> dict:
    if any(not number(value) or value <= 0 for value in (min_hours, max_gap, max_frame_age)):
        raise ValueError("Time thresholds must be positive")
    if expected_streams is not None and expected_streams < 1:
        raise ValueError("Expected streams must be positive")
    runs, current, errors = [], {}, []
    for index, row in enumerate(records, 1):
        try:
            stamp = datetime.fromisoformat(row["time_utc"].replace("Z", "+00:00"))
            host, renderer = row["host"], row["renderer"]
            if stamp.tzinfo is None or not isinstance(host, str) or not host or not isinstance(renderer, dict):
                raise ValueError("missing identity")
            identity = (host, row.get("run_id"), row.get("source_id"), renderer.get("version"), renderer.get("backend"), renderer.get("sink"))
            if any(value is not None and not isinstance(value, str) for value in identity):
                raise ValueError("invalid identity")
        except (KeyError, TypeError, ValueError, AttributeError):
            errors.append(f"Sample {index}: missing/invalid timestamp, host or renderer")
            continue
        previous_run = current.get(host)
        if previous_run is None or previous_run["identity"] != identity:
            run = {"identity": identity, "rows": [], "issues": [], "discontinuities": 0, "comparable_frame_intervals": 0}
            runs.append(run)
            current[host] = run
        else:
            run = previous_run
        run["rows"].append((stamp, row))

    summaries = []
    for run in runs:
        identity, rows, issues = run["identity"], run["rows"], run["issues"]
        host, label, source, version, backend, sink = identity
        previous = None
        unknown_frames = 0
        observed_gaps = 0
        for stamp, row in rows:
            renderer = row["renderer"]
            streams = renderer.get("streams")
            prefix = stamp.isoformat()
            def issue(message: str, collection: list = issues, timestamp: str = prefix) -> None:
                collection.append(f"{timestamp}: {message}")
            for service_name in ("renderer_service", "web_service"):
                service = row.get(service_name)
                if not isinstance(service, dict) or service.get("state") != "active":
                    issue(f"{service_name} is not confirmed active")
            if row.get("web_healthy") is not True:
                issue("web health is not confirmed healthy")
            if renderer.get("error") or renderer.get("state") not in ("RUNNING", "running"):
                issue("renderer is not confirmed running")
            if not isinstance(streams, dict) or not streams:
                issue("no stream health records")
                streams = {}
            if expected_streams is not None and len(streams) != expected_streams:
                issue(f"expected {expected_streams} streams, observed {len(streams)}")
            for slot, stream in streams.items():
                if not isinstance(stream, dict) or stream.get("state") != "LIVE":
                    issue(f"slot {slot} is not LIVE")
                    continue
                age = stream.get("last_frame_age_seconds")
                if backend == "gstreamer":
                    if number(age) and age >= 0:
                        if age > max_frame_age:
                            issue(f"slot {slot} last frame exceeds {max_frame_age:g}s")
                    else:
                        unknown_frames += 1
            if previous is not None:
                prior_stamp, prior = previous
                elapsed = (stamp - prior_stamp).total_seconds()
                if elapsed <= 0:
                    issue("duplicate or out-of-order timestamp")
                if elapsed > max_gap:
                    observed_gaps += 1
                    issue(f"sample gap {elapsed:g}s exceeds {max_gap:g}s")
                prior_renderer = prior["renderer"]
                context_changed = any(renderer.get(key) != prior_renderer.get(key) for key in (
                    "active_layout_id", "active_revision", "active_revision_id",
                ))
                uptime, old_uptime = renderer.get("uptime_seconds"), prior_renderer.get("uptime_seconds")
                if number(uptime) and number(old_uptime) and uptime < old_uptime:
                    issue("renderer uptime reset")
                    context_changed = True
                for service_name in ("renderer_service", "web_service"):
                    service, old_service = row.get(service_name, {}), prior.get(service_name, {})
                    if isinstance(service, dict) and isinstance(old_service, dict):
                        for key in ("pid", "started", "restarts"):
                            if key in service and key in old_service and service[key] != old_service[key]:
                                issue(f"{service_name} {key} changed")
                                context_changed = True
                old_streams = prior_renderer.get("streams", {})
                if not isinstance(old_streams, dict):
                    old_streams = {}
                if set(streams) != set(old_streams):
                    issue("stream membership changed")
                    context_changed = True
                for slot, stream in streams.items():
                    old = old_streams.get(slot)
                    if not isinstance(stream, dict) or not isinstance(old, dict):
                        continue
                    if stream.get("restarts") != old.get("restarts"):
                        issue(f"slot {slot} restart counter changed")
                    changed = context_changed or any(stream.get(key) != old.get(key) for key in ("camera_id", "cuts", "restarts"))
                    frames, old_frames = stream.get("frames"), old.get("frames")
                    if changed:
                        run["discontinuities"] += 1
                    elif (backend == "gstreamer" and elapsed > 0 and number(frames) and number(old_frames)
                          and stream.get("state") == old.get("state") == "LIVE"):
                        run["comparable_frame_intervals"] += 1
                        if frames <= old_frames:
                            issue(f"slot {slot} frame counter did not advance without a recorded switch/restart")
            previous = (stamp, row)
        duration = max(0.0, (rows[-1][0] - rows[0][0]).total_seconds())
        incomplete = []
        if duration < min_hours * 3600:
            incomplete.append(f"observed {duration / 3600:.3f}h; required {min_hours:g}h")
        if not label or not source or not version:
            incomplete.append("run label, exact source identity or software version is missing")
        if backend not in {"gstreamer", "omxplayer"}:
            incomplete.append("physical backend is not identified")
        if backend == "gstreamer" and not sink:
            incomplete.append("GStreamer output sink is not identified")
        if unknown_frames:
            incomplete.append(f"{unknown_frames} GStreamer stream samples lack valid frame-age evidence")
        summaries.append({
            "host": host, "run_id": label, "source_id": source, "version": version, "backend": backend, "sink": sink,
            "first_sample": rows[0][0].isoformat(), "last_sample": rows[-1][0].isoformat(),
            "samples": len(rows), "duration_hours": round(duration / 3600, 4), "gaps": observed_gaps,
            "counter_discontinuities": run["discontinuities"],
            "comparable_frame_intervals": run["comparable_frame_intervals"],
            "status": "review_required" if issues else ("incomplete" if incomplete else "sample_window_complete"),
            "issues": issues, "incomplete_reasons": incomplete,
            "frame_evidence": "playback state only; no decoded-frame proof" if backend == "omxplayer" else "reported frame ages and available counters; not visual proof",
        })
    return {
        "schema_version": 1, "runs": summaries, "input_errors": errors,
        "limitation": "Sample-window completion is not hardware qualification. Observe physical output and run controlled outage, reboot, rollback and clean-install checks separately. Source identity is operator supplied.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="JSONL logs in capture order")
    parser.add_argument("--min-hours", type=float, default=24)
    parser.add_argument("--max-gap-seconds", type=float, default=90)
    parser.add_argument("--max-frame-age-seconds", type=float, default=30)
    parser.add_argument("--expected-streams", type=int)
    args = parser.parse_args()
    rows, errors = read_samples(args.paths)
    try:
        report = analyze(rows, min_hours=args.min_hours, max_gap=args.max_gap_seconds,
                         max_frame_age=args.max_frame_age_seconds, expected_streams=args.expected_streams)
    except ValueError as exc:
        parser.error(str(exc))
    report["input_errors"] = errors + report["input_errors"]
    print(json.dumps(report, indent=2, allow_nan=False))
    return int(bool(report["input_errors"]) or not report["runs"] or any(run["status"] != "sample_window_complete" for run in report["runs"]))


if __name__ == "__main__":
    raise SystemExit(main())
