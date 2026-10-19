from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..models import Camera, DisplayProfile, Layout, LayoutRevision, RotationGroup
from ..security import CredentialCipher
from ..services.cameras import CameraService
from .base import Rect, RendererBackend, StreamSpec
from .geometry import choose_stream_profile, normalized_to_pixels

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RotationCursor:
    index: int = 0
    direction: int = 1


class RendererController:
    def __init__(
        self,
        backend: RendererBackend,
        session_factory: sessionmaker[Session],
        cipher: CredentialCipher,
        *,
        output_width: int = 1920,
        output_height: int = 1080,
    ) -> None:
        self.backend = backend
        self.session_factory = session_factory
        self.cipher = cipher
        self.output_width = output_width
        self.output_height = output_height
        self.active_layout_id: str | None = None
        self.active_revision: int | None = None
        self.current_specs: dict[str, StreamSpec] = {}
        self.rotation_tasks: dict[str, asyncio.Task[None]] = {}
        self.rotation_cursors: dict[str, RotationCursor] = defaultdict(RotationCursor)
        self.rotation_paused: set[str] = set()
        self.rotation_failures: dict[str, int] = {}
        self.focused = False
        self.focus_restore_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def apply_layout(self, layout_id: str, revision: int | None = None) -> dict[str, Any]:
        async with self._lock:
            with self.session_factory() as db:
                layout = db.get(Layout, layout_id)
                if layout is None:
                    raise KeyError("Layout not found")
                revision_number = revision or layout.current_revision
                layout_revision = db.scalar(
                    select(LayoutRevision).where(
                        LayoutRevision.layout_id == layout_id,
                        LayoutRevision.revision == revision_number,
                    )
                )
                if layout_revision is None:
                    raise KeyError("Layout revision not found")
                profile = db.get(DisplayProfile, layout.display_profile_id) if layout.display_profile_id else None
                target_width = profile.width if profile else layout_revision.data.get("output_width")
                target_height = profile.height if profile else layout_revision.data.get("output_height")
                target_width = int(target_width or self.output_width)
                target_height = int(target_height or self.output_height)
                if (target_width, target_height) != (self.output_width, self.output_height):
                    self.backend.set_output_size(target_width, target_height)
                    self.output_width, self.output_height = target_width, target_height
                desired, rotation_slots = self._specs_for_layout(db, layout_revision.data)

            self._cancel_focus_restore()
            self._cancel_rotations()
            self._apply_diff(desired)
            if desired:
                self.backend.start_playback()
            self.active_layout_id = layout_id
            self.active_revision = revision_number
            self.focused = False
            for slot_id, group_id in rotation_slots.items():
                self.rotation_tasks[slot_id] = asyncio.create_task(
                    self._rotation_loop(slot_id, group_id), name=f"rotation-{slot_id}"
                )
            return self.status()

    def _specs_for_layout(
        self, db: Session, data: dict[str, Any]
    ) -> tuple[dict[str, StreamSpec], dict[str, str]]:
        camera_service = CameraService(db, self.cipher)
        desired: dict[str, StreamSpec] = {}
        rotations: dict[str, str] = {}
        for raw_slot in data.get("slots", []):
            if not raw_slot.get("enabled", True) or raw_slot.get("type") == "empty":
                continue
            rect = normalized_to_pixels(raw_slot, self.output_width, self.output_height)
            if raw_slot.get("type") == "rotation":
                group_id = raw_slot.get("rotation_group_id")
                group = db.get(RotationGroup, group_id)
                if not group or not group.enabled or not group.camera_entries:
                    continue
                cursor = self.rotation_cursors[group.id]
                cursor.index = min(group.start_position, len(group.camera_entries) - 1)
                entry = group.camera_entries[cursor.index]
                rotations[raw_slot["id"]] = group.id
                camera_id = entry["camera_id"]
                preferred_profile = entry.get("stream_profile_id") or raw_slot.get("stream_profile_id")
            else:
                camera_id = raw_slot.get("selected_camera_id") or raw_slot.get("camera_id")
                preferred_profile = raw_slot.get("stream_profile_id")
            camera = db.get(Camera, camera_id)
            if not camera or not camera.enabled:
                continue
            profiles = [
                {
                    "id": item.id,
                    "priority": item.priority,
                    "width": item.width,
                    "height": item.height,
                }
                for item in camera.stream_profiles
            ]
            profile_meta = choose_stream_profile(
                profiles,
                rect,
                mode=raw_slot.get("stream_selection", "automatic"),
                preferred_id=preferred_profile,
            )
            camera, profile, url = camera_service.resolve_stream_url(camera.id, profile_meta["id"])
            desired[raw_slot["id"]] = StreamSpec(
                slot_id=raw_slot["id"],
                camera_id=camera.id,
                camera_name=camera.name,
                url=url,
                rect=rect,
                aspect_mode=raw_slot.get("aspect_mode", "cover"),
                z_index=int(raw_slot.get("z_index", 0)),
                opacity=float(raw_slot.get("opacity", 1.0)),
                label=(
                    None
                    if raw_slot.get("title_position", "bottom-left") == "none"
                    else (raw_slot.get("label") or camera.name)
                ),
                title_position=raw_slot.get("title_position", "bottom-left"),
                muted=bool(raw_slot.get("muted", True)),
                transport=profile.transport,
                latency_profile=profile.latency_profile,
                stream_profile_id=profile.id,
                source_width=profile.width,
                source_height=profile.height,
                crop=raw_slot.get("crop") or {},
                is_rotation=raw_slot.get("type") == "rotation",
            )
        return desired, rotations

    def _apply_diff(self, desired: dict[str, StreamSpec]) -> None:
        for slot_id in set(self.current_specs) - set(desired):
            self.backend.remove_stream(slot_id)
            self.current_specs.pop(slot_id, None)
        for slot_id, spec in desired.items():
            current = self.current_specs.get(slot_id)
            if current is None:
                self.backend.add_stream(spec)
            elif (
                current.camera_id != spec.camera_id
                or current.stream_profile_id != spec.stream_profile_id
                or current.url != spec.url
                or current.is_rotation != spec.is_rotation
            ):
                self.backend.replace_stream(slot_id, spec)
            else:
                if current.rect != spec.rect:
                    self.backend.resize_stream(slot_id, spec.rect)
                if current.aspect_mode != spec.aspect_mode or current.crop != spec.crop:
                    self.backend.set_crop_mode(slot_id, spec.aspect_mode, spec.crop)
                if current.opacity != spec.opacity:
                    self.backend.set_opacity(slot_id, spec.opacity)
                if current.label != spec.label or current.title_position != spec.title_position:
                    self.backend.set_label(slot_id, spec.label, spec.title_position)
                if current.z_index != spec.z_index:
                    self.backend.set_z_order(slot_id, spec.z_index)
            self.current_specs[slot_id] = spec

    async def _rotation_loop(self, slot_id: str, group_id: str) -> None:
        previous_switch_seconds = 0.0
        try:
            while True:
                with self.session_factory() as db:
                    group = db.get(RotationGroup, group_id)
                    interval = group.interval_seconds if group else 15
                preparing_started = asyncio.get_running_loop().time()
                if group_id not in self.rotation_paused:
                    try:
                        await self.rotate(slot_id, direction=1, prepare_only=True)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        LOGGER.exception("Could not preconnect the next rotation camera", extra={"slot_id": slot_id})
                preparing_seconds = asyncio.get_running_loop().time() - preparing_started
                # The interval is the time between camera changes. A switch
                # and includes time spent preparing the next decoder.
                await asyncio.sleep(max(1.0, interval - previous_switch_seconds - preparing_seconds))
                if group_id in self.rotation_paused:
                    await asyncio.to_thread(self.backend.cancel_prepared, slot_id)
                    previous_switch_seconds = 0.0
                    continue
                started = asyncio.get_running_loop().time()
                try:
                    await self.rotate(slot_id, direction=1)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    self.rotation_failures[slot_id] = self.rotation_failures.get(slot_id, 0) + 1
                    LOGGER.exception(
                        "Rotation step failed; the group will retry on its next interval",
                        extra={"slot_id": slot_id, "rotation_group_id": group_id},
                    )
                finally:
                    previous_switch_seconds = asyncio.get_running_loop().time() - started
        except asyncio.CancelledError:
            raise

    async def rotate(self, slot_id: str, *, direction: int = 1, prepare_only: bool = False) -> dict[str, Any]:
        async with self._lock:
            current = self.current_specs.get(slot_id)
            if current is None:
                raise KeyError("Rotation slot not found")
            with self.session_factory() as db:
                group_id = None
                raw: dict[str, Any] | None = None
                if self.active_layout_id and self.active_revision:
                    revision = db.scalar(
                        select(LayoutRevision).where(
                            LayoutRevision.layout_id == self.active_layout_id,
                            LayoutRevision.revision == self.active_revision,
                        )
                    )
                    if revision:
                        raw = next(
                            (item for item in revision.data.get("slots", []) if item.get("id") == slot_id),
                            None,
                        )
                        group_id = raw.get("rotation_group_id") if raw else None
                group = db.get(RotationGroup, group_id) if group_id else None
                if not group or not group.camera_entries:
                    raise ValueError("Rotation group is empty or unavailable")
                if prepare_only and (group.preconnect == "off" or group.order_mode in {"random", "weighted"}):
                    return self.status()
                cursor = self.rotation_cursors[group.id]
                previous_index = cursor.index
                entries = list(group.camera_entries)
                if group.order_mode == "random":
                    next_entry = random.choice(entries)
                elif group.order_mode == "weighted":
                    next_entry = random.choices(
                        entries, weights=[max(1, int(item.get("weight", 1))) for item in entries], k=1
                    )[0]
                else:
                    step = -direction if group.order_mode == "reverse" else direction
                    next_index = (cursor.index + step) % len(entries)
                    if not prepare_only:
                        cursor.index = next_index
                    next_entry = entries[next_index]
                service = CameraService(db, self.cipher)
                camera, profile, url = service.resolve_stream_url(
                    next_entry["camera_id"], next_entry.get("stream_profile_id")
                )
                replacement = StreamSpec(
                    slot_id=slot_id,
                    camera_id=camera.id,
                    camera_name=camera.name,
                    url=url,
                    rect=current.rect,
                    aspect_mode=current.aspect_mode,
                    z_index=current.z_index,
                    opacity=current.opacity,
                    label=(
                        None
                        if (raw or {}).get("title_position", current.title_position) == "none"
                        else ((raw or {}).get("label") or camera.name)
                    ),
                    title_position=(raw or {}).get("title_position", current.title_position),
                    muted=current.muted,
                    transport=profile.transport,
                    latency_profile=profile.latency_profile,
                    stream_profile_id=profile.id,
                    source_width=profile.width,
                    source_height=profile.height,
                    crop=current.crop,
                    is_rotation=True,
                )
            if prepare_only:
                await asyncio.to_thread(self.backend.prepare_stream, slot_id, replacement)
                return self.status()
            try:
                switch = (
                    self.backend.activate_prepared_stream
                    if group.preconnect != "off" and group.order_mode not in {"random", "weighted"}
                    else self.backend.replace_stream
                )
                await asyncio.to_thread(switch, slot_id, replacement)
            except Exception:
                cursor.index = previous_index
                raise
            self.current_specs[slot_id] = replacement
            self.rotation_failures.pop(slot_id, None)
            return self.status()

    async def focus_camera(
        self,
        camera_id: str,
        stream_profile_id: str | None = None,
        aspect_mode: str = "cover",
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
            self._cancel_focus_restore()
            self._cancel_rotations()
            with self.session_factory() as db:
                service = CameraService(db, self.cipher)
                camera, profile, url = service.resolve_stream_url(camera_id, stream_profile_id)
                spec = StreamSpec(
                    slot_id="__focus__",
                    camera_id=camera.id,
                    camera_name=camera.name,
                    url=url,
                    rect=Rect(0, 0, self.output_width, self.output_height),
                    aspect_mode=aspect_mode,
                    label=camera.name,
                    title_position="bottom-left",
                    transport=profile.transport,
                    latency_profile=profile.latency_profile,
                    stream_profile_id=profile.id,
                )
            self._apply_diff({"__focus__": spec})
            self.focused = True
            if duration_seconds:
                self.focus_restore_task = asyncio.create_task(
                    self._restore_focus_after(duration_seconds),
                    name="focus-auto-restore",
                )
            return self.status()

    async def _restore_focus_after(self, duration_seconds: int) -> None:
        try:
            await asyncio.sleep(duration_seconds)
            if self.focused and self.active_layout_id:
                await self.apply_layout(self.active_layout_id, self.active_revision)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Unable to restore the layout after temporary focus")
        finally:
            if self.focus_restore_task is asyncio.current_task():
                self.focus_restore_task = None

    async def restore_layout(self) -> dict[str, Any]:
        if not self.active_layout_id:
            raise ValueError("No active layout to restore")
        self._cancel_focus_restore()
        return await self.apply_layout(self.active_layout_id, self.active_revision)

    def pause_rotation(self, group_id: str) -> None:
        self.rotation_paused.add(group_id)

    def resume_rotation(self, group_id: str) -> None:
        self.rotation_paused.discard(group_id)

    def restart_stream(self, slot_id: str) -> dict[str, Any]:
        self.backend.restart_stream(slot_id)
        return self.status()

    def status(self) -> dict[str, Any]:
        status = self.backend.health()
        for slot_id, failures in self.rotation_failures.items():
            stream = status.get("streams", {}).get(slot_id)
            if stream and stream.get("state") == "LIVE" and failures >= 2:
                stream["state"] = "DEGRADED"
                stream["detail"] = f"Rotation stalled: {failures} scheduled changes missed; active camera is still playing"
        status.update(
            {
                "active_layout_id": self.active_layout_id,
                "active_revision": self.active_revision,
                "focused": self.focused,
                "focus_auto_restore": bool(self.focus_restore_task),
                "rotation_slots": list(self.rotation_tasks),
                "rotation_paused": list(self.rotation_paused),
            }
        )
        return status

    def _cancel_focus_restore(self) -> None:
        task = self.focus_restore_task
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        self.focus_restore_task = None

    def _cancel_rotations(self) -> None:
        for slot_id in self.rotation_tasks:
            self.backend.cancel_prepared(slot_id)
        for task in self.rotation_tasks.values():
            task.cancel()
        self.rotation_tasks.clear()
        self.rotation_failures.clear()

    async def shutdown(self) -> None:
        self._cancel_focus_restore()
        self._cancel_rotations()
        self.backend.shutdown()
