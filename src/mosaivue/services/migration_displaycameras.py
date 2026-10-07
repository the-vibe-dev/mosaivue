from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..schemas import CameraCreate, LayoutCreate, LayoutData, Slot, StreamProfileIn

COMMON_PATHS = [
    Path("/etc/displaycameras/displaycameras.conf"),
    Path("/etc/displaycameras/layout.conf.default"),
]


@dataclass(slots=True)
class MigrationPlan:
    cameras: list[CameraCreate] = field(default_factory=list)
    layouts: list[LayoutCreate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "source_files": self.source_files,
            "cameras": len(self.cameras),
            "layouts": len(self.layouts),
            "warnings": self.warnings,
        }


def discover_files(extra: list[Path] | None = None) -> list[Path]:
    candidates = list(COMMON_PATHS)
    candidates.extend(sorted(Path("/etc/displaycameras").glob("layout.conf.*")))
    if extra:
        candidates.extend(extra)
    unique: list[Path] = []
    for path in candidates:
        if path.exists() and path not in unique:
            unique.append(path)
    return unique


def parse_shell_assignments(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    logical_lines: list[str] = []
    buffer = ""
    in_array = False
    depth = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        continued = line.endswith("\\")
        if continued:
            line = line[:-1].rstrip()
        if buffer:
            buffer += " " + line
        else:
            buffer = line
        depth += line.count("(") - line.count(")")
        in_array = depth > 0
        if not in_array and not continued:
            logical_lines.append(buffer.strip())
            buffer = ""
    if buffer:
        logical_lines.append(buffer)
    for line in logical_lines:
        match = re.match(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        raw_value = raw_value.strip()
        if raw_value.startswith("(") and raw_value.endswith(")"):
            try:
                result[key] = shlex.split(raw_value[1:-1], comments=True, posix=True)
            except ValueError:
                result[key] = re.findall(r"['\"]([^'\"]+)['\"]", raw_value)
        else:
            try:
                values = shlex.split(raw_value, comments=True, posix=True)
                result[key] = values[0] if values else ""
            except ValueError:
                result[key] = raw_value.strip("'\"")
    return result


def _find_array(data: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    for candidate in names:
        for key, value in data.items():
            if key.lower() == candidate.lower() and isinstance(value, list):
                return [str(item) for item in value]
    return []


def _parse_rect(value: str) -> tuple[int, int, int, int] | None:
    numbers = [int(item) for item in re.findall(r"-?\d+", value)]
    if len(numbers) < 4:
        return None
    x1, y1, x2, y2 = numbers[:4]
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2


def build_plan(paths: list[Path], *, default_width: int = 1920, default_height: int = 1080) -> MigrationPlan:
    plan = MigrationPlan(source_files=[str(path) for path in paths])
    merged: dict[str, Any] = {}
    layout_sources: list[tuple[Path, dict[str, Any]]] = []
    for path in paths:
        parsed = parse_shell_assignments(path.read_text(encoding="utf-8", errors="replace"))
        merged.update(parsed)
        if path.name.startswith("layout.conf"):
            layout_sources.append((path, parsed))

    names = _find_array(merged, ("camera_names", "cam_names", "names"))
    urls = _find_array(merged, ("camera_feeds", "camera_urls", "feeds", "urls"))
    if not urls:
        for key, value in merged.items():
            if isinstance(value, list) and any(str(item).startswith("rtsp") for item in value):
                urls = [str(item) for item in value]
                break
    if not names:
        names = [f"Camera {index + 1}" for index in range(len(urls))]
    if len(names) != len(urls):
        plan.warnings.append(
            f"Camera name count ({len(names)}) differs from URL count ({len(urls)}); generated names fill gaps"
        )
    for index, url in enumerate(urls):
        name = names[index] if index < len(names) else f"Camera {index + 1}"
        plan.cameras.append(
            CameraCreate(name=name, stream_profiles=[StreamProfileIn(name="Imported", url=url)])
        )

    if not layout_sources and paths:
        layout_sources = [(paths[0], merged)]
    camera_ids = [f"import-camera-{index}" for index in range(len(plan.cameras))]
    for source_path, data in layout_sources:
        rectangles = _find_array(data, ("window_positions", "positions", "rectangles", "windows"))
        if not rectangles:
            for key, value in data.items():
                if isinstance(value, list) and value and all(_parse_rect(str(item)) for item in value):
                    rectangles = [str(item) for item in value]
                    break
        resolution = str(data.get("resolution", data.get("RESOLUTION", "")))
        match = re.search(r"(\d{3,5})\D+(\d{3,5})", resolution)
        width, height = (int(match.group(1)), int(match.group(2))) if match else (default_width, default_height)
        slots: list[Slot] = []
        for index, raw_rect in enumerate(rectangles[: len(plan.cameras)]):
            rect = _parse_rect(raw_rect)
            if not rect:
                plan.warnings.append(f"Could not parse rectangle: {raw_rect}")
                continue
            x1, y1, x2, y2 = rect
            x = max(0.0, min(1.0, x1 / width))
            y = max(0.0, min(1.0, y1 / height))
            w = max(0.001, min(1.0 - x, (x2 - x1) / width))
            h = max(0.001, min(1.0 - y, (y2 - y1) / height))
            slots.append(
                Slot(
                    id=f"import-slot-{index}",
                    name=plan.cameras[index].name,
                    type="fixed",
                    camera_id=camera_ids[index],
                    x=x,
                    y=y,
                    width=w,
                    height=h,
                )
            )
        if slots:
            layout_name = source_path.name.removeprefix("layout.conf").strip(".-_") or "Default"
            plan.layouts.append(
                LayoutCreate(
                    name=f"Imported {layout_name.title()}",
                    description=f"Migrated from {source_path}",
                    data=LayoutData(slots=slots, output_width=width, output_height=height),
                )
            )
    if not plan.layouts and plan.cameras:
        plan.warnings.append("No recognizable displaycameras window rectangles were found")
    return plan
