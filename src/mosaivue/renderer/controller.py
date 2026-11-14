from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from copy import deepcopy
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
MANUAL_ROTATION_READY_TIMEOUT = 8.0


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
        self._capabilities = backend.capabilities().to_dict()
        self.session_factory = session_factory
        self.cipher = cipher
        self.output_width = output_width
        self.output_height = output_height
        self.active_layout_id: str | None = None
        self.active_revision: int | None = None
        self.active_revision_id: str | None = None
        self.current_specs: dict[str, StreamSpec] = {}
        self.rotation_tasks: dict[str, asyncio.Task[None]] = {}
        self.rotation_cursors: dict[str, RotationCursor] = defaultdict(RotationCursor)
        self.rotation_paused: set[str] = set()
        self.rotation_failures: dict[str, int] = {}
        self.focused = False
        self.focus_restore_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def apply_layout(
        self, layout_id: str, revision: int | None = None, *, revision_id: str | None = None,
    ) -> dict[str, Any]:
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
                if revision_id is not None and layout_revision.id != revision_id:
                    raise ValueError("Layout revision identity changed; reload the saved layout before applying")
                selected_revision_id = layout_revision.id
                profile = db.get(DisplayProfile, layout.display_profile_id) if layout.display_profile_id else None
                target_width = profile.width if profile else layout_revision.data.get("output_width")
                target_height = profile.height if profile else layout_revision.data.get("output_height")
                target_width = int(target_width or self.output_width)
                target_height = int(target_height or self.output_height)
                desired, rotation_slots, cursors = self._specs_for_layout(
                    db, layout_revision.data, target_width, target_height
                )

            self._apply_transaction(desired, target_width, target_height)
            self._cancel_focus_restore()
            self._cancel_rotations()
            self.rotation_cursors = defaultdict(RotationCursor, cursors)
            self.active_layout_id = layout_id
            self.active_revision = revision_number
            self.active_revision_id = selected_revision_id
            self.focused = False
            for slot_id, group_id in rotation_slots.items():
                self.rotation_tasks[slot_id] = asyncio.create_task(
                    self._rotation_loop(slot_id, group_id), name=f"rotation-{slot_id}"
                )
            return self.status()

    def _specs_for_layout(
        self, db: Session, data: dict[str, Any], width: int, height: int
    ) -> tuple[dict[str, StreamSpec], dict[str, str], dict[str, RotationCursor]]:
        camera_service = CameraService(db, self.cipher)
        desired: dict[str, StreamSpec] = {}
        rotations: dict[str, str] = {}
        cursors: dict[str, RotationCursor] = {}
        for raw_slot in data.get("slots", []):
            if not raw_slot.get("enabled", True) or raw_slot.get("type") == "empty":
                continue
            rect = normalized_to_pixels(raw_slot, width, height)
            if raw_slot.get("type") == "rotation":
                group_id = raw_slot.get("rotation_group_id")
                group = db.get(RotationGroup, group_id)
                if not group or not group.enabled or not group.camera_entries:
                    continue
                start = min(group.start_position, len(group.camera_entries) - 1)
                available: list[int] = []
                for offset in range(len(group.camera_entries)):
                    step = -1 if group.order_mode == "reverse" else 1
                    index = (start + offset * step) % len(group.camera_entries)
                    candidate = db.get(Camera, group.camera_entries[index]["camera_id"])
                    if candidate is not None and candidate.enabled and candidate.stream_profiles:
                        available.append(index)
                if not available:
                    continue
                cursor = RotationCursor(index=available[0])
                cursors[raw_slot["id"]] = cursor
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
        return desired, rotations, cursors

    def _apply_transaction(
        self, desired: dict[str, StreamSpec], width: int, height: int
    ) -> None:
        """Restore the previous wall if a synchronous backend update fails.

        Live decoders may fail after accepting a spec; their normal health and
        recovery path handles that. This rollback covers rejected configuration
        and backend exceptions, not asynchronous first-frame qualification.
        """
        previous = deepcopy(self.current_specs)
        previous_size = (self.output_width, self.output_height)
        try:
            if (width, height) != previous_size:
                self.backend.set_output_size(width, height)
            self._apply_diff(desired)
            if desired:
                self.backend.start_playback()
        except Exception:
            LOGGER.exception("Layout update failed; restoring the previous wall")
            try:
                # An add/replace operation can raise after partially creating a
                # branch, so clean up every potentially touched slot first.
                for slot_id in set(previous) | set(desired):
                    self.backend.remove_stream(slot_id)
                self.backend.set_output_size(*previous_size)
                self.current_specs.clear()
                self._apply_diff(previous)
                if previous:
                    self.backend.start_playback()
            except Exception as rollback_error:
                LOGGER.exception("Previous wall could not be restored")
                raise RuntimeError("Layout update failed and rollback failed; restart the renderer") from rollback_error
            raise
        self.output_width, self.output_height = width, height

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
                or current.transport != spec.transport
                or current.latency_profile != spec.latency_profile
                or current.source_width != spec.source_width
                or current.source_height != spec.source_height
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
                try:
                    with self.session_factory() as db:
                        group = db.get(RotationGroup, group_id)
                        interval = group.interval_seconds if group else 15
                except Exception:
                    self.rotation_failures[slot_id] = self.rotation_failures.get(slot_id, 0) + 1
                    LOGGER.exception(
                        "Could not read rotation configuration; retrying in five seconds",
                        extra={"slot_id": slot_id, "rotation_group_id": group_id},
                    )
                    await asyncio.sleep(5)
                    continue
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

    async def rotate(
        self, slot_id: str, *, direction: int = 1, prepare_only: bool = False,
        manual: bool = False,
    ) -> dict[str, Any]:
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
                        if self.active_revision_id is not None and revision.id != self.active_revision_id:
                            raise ValueError("Applied layout revision was replaced; reapply the saved layout")
                        raw = next(
                            (item for item in revision.data.get("slots", []) if item.get("id") == slot_id),
                            None,
                        )
                        group_id = raw.get("rotation_group_id") if raw else None
                group = db.get(RotationGroup, group_id) if group_id else None
                if not group or not group.camera_entries:
                    raise ValueError("Rotation group is empty or unavailable")
                if not group.enabled:
                    await asyncio.to_thread(self.backend.cancel_prepared, slot_id)
                    return self.status()
                if prepare_only and (group.preconnect == "off" or group.order_mode in {"random", "weighted"}):
                    return self.status()
                cursor = self.rotation_cursors[slot_id]
                previous_index = cursor.index
                entries = list(group.camera_entries)
                available: list[int] = []
                for index, entry in enumerate(entries):
                    camera = db.get(Camera, entry["camera_id"])
                    if camera is not None and camera.enabled and camera.stream_profiles:
                        available.append(index)
                if not available:
                    raise ValueError("Rotation group has no enabled cameras with stream profiles")
                if group.order_mode == "random":
                    next_index = random.choice(available)
                elif group.order_mode == "weighted":
                    next_index = random.choices(
                        available,
                        weights=[max(1, int(entries[index].get("weight", 1))) for index in available],
                        k=1,
                    )[0]
                else:
                    step = -direction if group.order_mode == "reverse" else direction
                    next_index = next(
                        candidate for offset in range(1, len(entries) + 1)
                        if (candidate := (cursor.index + offset * step) % len(entries)) in available
                    )
                next_entry = entries[next_index]
                service = CameraService(db, self.cipher)
                camera = service.get(next_entry["camera_id"])
                profile_meta = choose_stream_profile(
                    [
                        {"id": profile.id, "priority": profile.priority,
                         "width": profile.width, "height": profile.height}
                        for profile in camera.stream_profiles
                    ],
                    current.rect,
                    mode=(raw or {}).get("stream_selection", "automatic"),
                    preferred_id=next_entry.get("stream_profile_id") or (raw or {}).get("stream_profile_id"),
                )
                camera, profile, url = service.resolve_stream_url(
                    next_entry["camera_id"], profile_meta["id"]
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
            if (
                replacement.camera_id == current.camera_id
                and replacement.stream_profile_id == current.stream_profile_id
                and replacement.url == current.url
                and replacement.transport == current.transport
                and replacement.latency_profile == current.latency_profile
            ):
                if not prepare_only:
                    cursor.index = next_index
                return self.status()
            if prepare_only:
                await asyncio.to_thread(self.backend.prepare_stream, slot_id, replacement)
                return self.status()
            try:
                if manual and group.preconnect != "off":
                    # Previous may target a different camera than the automatic
                    # next standby. Prepare exactly the requested source and
                    # retain the current video until the backend confirms it.
                    await self._prepare_manual_rotation(slot_id, replacement)
                    switch = self.backend.activate_prepared_stream
                else:
                    switch = (
                        self.backend.activate_prepared_stream
                        if group.preconnect != "off" and group.order_mode not in {"random", "weighted"}
                        else self.backend.replace_stream
                    )
                await asyncio.to_thread(switch, slot_id, replacement)
            except Exception:
                # A failed next camera must not permanently block the rest of a
                # skip-mode sequence. Keep the current video, but try the entry
                # after the failed camera next time. Hold mode retries it.
                cursor.index = (
                    next_index if group.failure_behavior == "skip" and not manual else previous_index
                )
                raise
            cursor.index = next_index
            self.current_specs[slot_id] = replacement
            self.rotation_failures.pop(slot_id, None)
            return self.status()

    async def _prepare_manual_rotation(self, slot_id: str, spec: StreamSpec) -> None:
        await asyncio.to_thread(self.backend.prepare_stream, slot_id, spec)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + MANUAL_ROTATION_READY_TIMEOUT
        while not await asyncio.to_thread(self.backend.prepared_stream_ready, slot_id, spec):
            remaining = deadline - loop.time()
            if remaining <= 0:
                await asyncio.to_thread(self.backend.cancel_prepared, slot_id)
                raise RuntimeError("Requested camera did not become ready; the current camera was kept")
            await asyncio.sleep(min(0.1, remaining))

    async def focus_camera(
        self,
        camera_id: str,
        stream_profile_id: str | None = None,
        aspect_mode: str = "cover",
        duration_seconds: int | None = None,
    ) -> dict[str, Any]:
        async with self._lock:
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
                    source_width=profile.width,
                    source_height=profile.height,
                )
            self._apply_transaction({"__focus__": spec}, self.output_width, self.output_height)
            self._cancel_focus_restore()
            self._cancel_rotations()
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
                await self.apply_layout(
                    self.active_layout_id, self.active_revision, revision_id=self.active_revision_id,
                )
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
        return await self.apply_layout(
            self.active_layout_id, self.active_revision, revision_id=self.active_revision_id,
        )

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
                "active_revision_id": self.active_revision_id,
                "focused": self.focused,
                "focus_auto_restore": bool(self.focus_restore_task),
                "rotation_slots": list(self.rotation_tasks),
                "rotation_paused": list(self.rotation_paused),
                "capabilities": deepcopy(self._capabilities),
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
            try:
                self.backend.cancel_prepared(slot_id)
            except Exception:
                LOGGER.exception("Could not release prepared rotation source", extra={"slot_id": slot_id})
        for task in self.rotation_tasks.values():
            task.cancel()
        self.rotation_tasks.clear()
        self.rotation_failures.clear()

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self.rotation_tasks.values())
            if self.focus_restore_task:
                tasks.append(self.focus_restore_task)
            self._cancel_focus_restore()
            self._cancel_rotations()
            self.backend.shutdown()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
