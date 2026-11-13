from __future__ import annotations

import hashlib
import logging
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import threading
import time
from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit

from .base import (
    HealthState,
    Rect,
    RendererBackend,
    RendererCapabilities,
    StreamHealth,
    StreamSpec,
    feature_flags,
)

LOGGER = logging.getLogger(__name__)
HANDOFF_SETTLE_SECONDS = 2.5


@dataclass
class _Player:
    spec: StreamSpec
    process: subprocess.Popen[bytes]
    health: StreamHealth
    started: float
    dbus_name: str
    visible: bool = True
    retry_at: float = 0.0


class OmxPlayerRenderer(RendererBackend):
    """Legacy Raspberry Pi hardware overlay renderer, one player per tile."""

    def __init__(self) -> None:
        self.width = 1920
        self.height = 1080
        self._players: dict[str, _Player] = {}
        self._prepared: dict[str, _Player] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None
        self._started: float | None = None

    @classmethod
    def detect(cls) -> RendererCapabilities:
        player = shutil.which("omxplayer")
        return RendererCapabilities(
            name="omxplayer",
            available=bool(player and os.path.exists("/dev/vchiq")),
            reason=None if player and os.path.exists("/dev/vchiq") else "OMXPlayer and /dev/vchiq are required",
            sinks=["HDMI hardware overlay"] if player else [],
            decoders=["OpenMAX H.264"] if player else [],
            dynamic_geometry=True,
            dynamic_source_replace=True,
            per_stream_recovery=True,
            snapshots=False,
            hardware_decode=True,
            feature_support=feature_flags("opacity", "z_order"),
            limitations=[
                "Tile labels and manual crop are not rendered.",
                "Opacity changes restart the affected player.",
                "Native size uses letterbox behavior.",
                "Playback health confirms player status, not video-frame advancement.",
                "Audio, portrait output, monitor selection, display refresh control, and blanking control are not implemented.",
                "Per-tile backgrounds and borders are not rendered.",
            ],
        )

    def capabilities(self) -> RendererCapabilities:
        return self.detect()

    def initialize(self, *, width: int, height: int, sink: str = "auto") -> None:
        if not self.detect().available:
            raise RuntimeError("OMXPlayer is unavailable")
        self.set_output_size(width, height)
        if self._monitor is None or not self._monitor.is_alive():
            self._stop.clear()
            self._started = time.monotonic()
            self._monitor = threading.Thread(target=self._watch, daemon=True, name="mosaivue-omx-monitor")
            self._monitor.start()

    def set_output_size(self, width: int, height: int) -> None:
        if width < 1 or height < 1:
            raise ValueError("Output dimensions must be positive")
        self.width, self.height = width, height

    @staticmethod
    def _name(slot_id: str) -> str:
        return "Mosaivue_" + hashlib.sha256(slot_id.encode()).hexdigest()[:16]

    @classmethod
    def _player_args(
        cls, spec: StreamSpec, *, dbus_name: str | None = None, alpha: int | None = None,
        layer: int | None = None,
    ) -> list[str]:
        rect = spec.rect
        window = f"{rect.x} {rect.y} {rect.x + rect.width} {rect.y + rect.height}"
        # OMXPlayer has no native-size mode for a fixed window. Letterbox keeps
        # the original proportions for that legacy option.
        aspect = {"cover": "fill", "contain": "letterbox", "stretch": "stretch", "native": "letterbox"}.get(
            spec.aspect_mode, "fill"
        )
        args = [
            "/usr/bin/omxplayer", "--no-keys", "--no-osd",
            "--aspect-mode", aspect, "--win", window,
        ]
        args.extend(["--alpha", str(alpha if alpha is not None else round(spec.opacity * 255))])
        args.extend(["--layer", str(layer if layer is not None else spec.z_index * 10)])
        # RTSPS selects TLS in libavformat; forcing RTSP-over-TCP can override it.
        if urlsplit(spec.url).scheme.lower() == "rtsp" and spec.transport in {"tcp", "udp"}:
            args.extend(["--avdict", f"rtsp_transport:{spec.transport}"])
        args.extend([
            spec.url, "--live", "-n", "-1", "--timeout", "30",
            "--dbus_name", "org.mpris.MediaPlayer2.omxplayer." + (dbus_name or cls._name(spec.slot_id)),
        ])
        return args

    def _start(
        self, spec: StreamSpec, *, restart_count: int = 0, switch_count: int = 0,
        last_restart_reason: str | None = None, dbus_name: str | None = None,
        alpha: int | None = None, layer: int | None = None,
    ) -> _Player:
        name = dbus_name or self._name(spec.slot_id)
        args = self._player_args(spec, dbus_name=name, alpha=alpha, layer=layer)
        env = dict(os.environ, USER="mosaivue", NOREFRESH="1")
        process = subprocess.Popen(
            args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, env=env, start_new_session=True,
        )
        health = StreamHealth(
            slot_id=spec.slot_id, camera_id=spec.camera_id,
            state=HealthState.connecting, restart_count=restart_count,
            switch_count=switch_count, last_restart_reason=last_restart_reason,
        )
        return _Player(spec, process, health, time.monotonic(), name)

    @staticmethod
    def _stop_player(player: _Player) -> None:
        if player.process.poll() is None:
            try:
                os.killpg(player.process.pid, signal.SIGTERM)
                player.process.wait(timeout=3)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                with suppress(ProcessLookupError):
                    os.killpg(player.process.pid, signal.SIGKILL)
                player.process.wait(timeout=3)

    def add_stream(self, spec: StreamSpec) -> None:
        with self._lock:
            if spec.slot_id in self._players:
                raise ValueError(f"Slot {spec.slot_id} already exists")
            self._players[spec.slot_id] = self._start(spec)
        # OMX's firmware startup is less reliable when seven players race for it.
        time.sleep(1)

    def remove_stream(self, slot_id: str) -> None:
        with self._lock:
            self.cancel_prepared(slot_id)
            player = self._players.pop(slot_id, None)
            if player:
                self._stop_player(player)

    def replace_stream(self, slot_id: str, spec: StreamSpec) -> None:
        with self._lock:
            switch_started = time.monotonic()
            previous = self._players.get(slot_id)
            restarts = previous.health.restart_count if previous else 0
            switches = previous.health.switch_count if previous else 0
            reason = previous.health.last_restart_reason if previous else None
            camera_changed = bool(previous and previous.spec.camera_id != spec.camera_id)
            if camera_changed:
                switches += 1
            if previous and previous.visible and camera_changed:
                candidate = self._prepared.pop(slot_id, None)
                preconnected = candidate is not None
                try:
                    if candidate is None or candidate.spec.camera_id != spec.camera_id or candidate.spec.url != spec.url or candidate.process.poll() is not None:
                        if candidate is not None:
                            self._stop_player(candidate)
                        self.prepare_stream(slot_id, spec)
                        candidate = self._prepared.pop(slot_id)
                    if not self._set_video_pos(candidate, spec.rect):
                        raise RuntimeError("OMXPlayer could not position the prepared video")
                    # The new surface remains below the current one until the
                    # decoder is positioned and has had a display refresh.
                    time.sleep(0.12)
                    if candidate.process.poll() is not None or not self._set_layer(candidate, spec.z_index * 10 + 2):
                        raise RuntimeError("OMXPlayer prepared video stopped before cutover")
                    candidate.spec = spec
                    candidate.health.restart_count = restarts
                    candidate.health.switch_count = switches
                    candidate.health.last_restart_reason = reason
                    candidate.health.detail = "Playback confirmed by OMXPlayer"
                    candidate.health.last_frame_monotonic = time.monotonic()
                    self._stop_player(previous)
                    self._players[slot_id] = candidate
                    self._set_layer(candidate, spec.z_index * 10)
                    LOGGER.info(
                        "OMXPlayer cut slot %s in %.0f ms; preconnected=%s",
                        slot_id, (time.monotonic() - switch_started) * 1000, preconnected,
                    )
                    return
                except (OSError, subprocess.TimeoutExpired, RuntimeError) as exc:
                    if candidate is not None:
                        self._stop_player(candidate)
                    LOGGER.warning("OMXPlayer kept current camera for slot %s: %s", slot_id, exc)
                    raise RuntimeError(f"Next camera was not ready for slot {slot_id}") from exc
            if previous:
                self._stop_player(previous)
            self._players[slot_id] = self._start(
                spec, restart_count=restarts, switch_count=switches, last_restart_reason=reason
            )

    def prepare_stream(self, slot_id: str, spec: StreamSpec) -> None:
        with self._lock:
            existing = self._prepared.get(slot_id)
            if existing and existing.spec.camera_id == spec.camera_id and existing.spec.url == spec.url and existing.process.poll() is None:
                return
            self.cancel_prepared(slot_id)
            # The Pi 3 has limited decoder capacity. Keep at most one extra
            # decoder for all rotation tiles.
            for other_slot in list(self._prepared):
                self.cancel_prepared(other_slot)
            parked = replace(spec, rect=Rect(self.width + 32, 0, spec.rect.width, spec.rect.height))
            player = self._start(
                parked, dbus_name=self._name(f"{slot_id}:{time.monotonic_ns()}"),
                layer=spec.z_index * 10 - 1,
            )
            try:
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and player.process.poll() is None:
                    if self._playback_status(player):
                        time.sleep(HANDOFF_SETTLE_SECONDS)
                        if player.process.poll() is None and self._playback_status(player):
                            player.spec = spec
                            player.health.state = HealthState.live
                            player.health.detail = "Prepared for a cut"
                            self._prepared[slot_id] = player
                            return
                    time.sleep(0.15)
                raise RuntimeError("Prepared camera did not reach playback")
            except BaseException:
                self._stop_player(player)
                raise

    def cancel_prepared(self, slot_id: str) -> None:
        with self._lock:
            player = self._prepared.pop(slot_id, None)
            if player is not None:
                self._stop_player(player)

    def _send_video_command(self, player: _Player, method: str, *args: str) -> bool:
        try:
            result = subprocess.run(
                ["dbus-send", "--print-reply=literal", "--session", "--reply-timeout=1000",
                 "--dest=org.mpris.MediaPlayer2.omxplayer." + player.dbus_name,
                 "/org/mpris/MediaPlayer2", f"org.mpris.MediaPlayer2.Player.{method}", *args],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2,
                env=self._bus_env(), check=False,
            )
            return result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _set_video_pos(self, player: _Player, rect: Rect) -> bool:
        position = f"{rect.x} {rect.y} {rect.x + rect.width} {rect.y + rect.height}"
        return self._send_video_command(player, "VideoPos", "objpath:/not/used", f"string:{position}")

    def _set_layer(self, player: _Player, layer: int) -> bool:
        return self._send_video_command(player, "SetLayer", f"int64:{layer}")

    def move_stream(self, slot_id: str, rect: Rect) -> None:
        self.resize_stream(slot_id, rect)

    def resize_stream(self, slot_id: str, rect: Rect) -> None:
        with self._lock:
            player = self._players[slot_id]
            if self._set_video_pos(player, rect):
                player.spec.rect = rect
            else:
                self.replace_stream(slot_id, replace(player.spec, rect=rect))

    def set_crop_mode(self, slot_id: str, aspect_mode: str, crop: dict[str, float] | None = None) -> None:
        with self._lock:
            player = self._players[slot_id]
            player.spec.aspect_mode = aspect_mode
            player.spec.crop = crop or {}
            self.replace_stream(slot_id, player.spec)

    def set_visibility(self, slot_id: str, visible: bool) -> None:
        with self._lock:
            player = self._players[slot_id]
            if visible == player.visible:
                return
            player.visible = visible
            if visible:
                self._players[slot_id] = self._start(
                    player.spec, restart_count=player.health.restart_count,
                    switch_count=player.health.switch_count,
                    last_restart_reason=player.health.last_restart_reason,
                )
            else:
                self._stop_player(player)
                player.health.state = HealthState.disabled

    def set_opacity(self, slot_id: str, opacity: float) -> None:
        with self._lock:
            player = self._players[slot_id]
            opacity = max(0.0, min(1.0, opacity))
            # --alpha is honored by OMXPlayer at process startup. A controlled
            # replacement is portable across legacy builds with different
            # D-Bus interfaces.
            self.replace_stream(slot_id, replace(player.spec, opacity=opacity))

    def set_label(self, slot_id: str, label: str | None, title_position: str) -> None:
        self._players[slot_id].spec.label = label
        self._players[slot_id].spec.title_position = title_position

    def set_z_order(self, slot_id: str, z_index: int) -> None:
        with self._lock:
            player = self._players[slot_id]
            if self._set_layer(player, z_index * 10):
                player.spec.z_index = z_index
            else:
                self.replace_stream(slot_id, replace(player.spec, z_index=z_index))

    def snapshot(self, slot_id: str | None = None) -> bytes | None:
        return None

    @staticmethod
    def _bus_env() -> dict[str, str]:
        path = os.path.join(tempfile.gettempdir(), "omxplayerdbus.mosaivue")
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid() or details.st_mode & 0o022:
                raise OSError("OMXPlayer D-Bus address file has an unexpected owner or type")
            with os.fdopen(descriptor, encoding="utf-8", closefd=False) as handle:
                address = handle.read(4096).strip()
        finally:
            os.close(descriptor)
        if not address:
            raise OSError("OMXPlayer D-Bus address file is empty")
        return dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address)

    def _playback_status(self, player: _Player) -> bool:
        try:
            result = subprocess.run(
                ["dbus-send", "--print-reply=literal", "--session", "--reply-timeout=500",
                 "--dest=org.mpris.MediaPlayer2.omxplayer." + player.dbus_name,
                 "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties.PlaybackStatus"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2,
                env=self._bus_env(), check=False,
            )
            return result.returncode == 0 and b"Playing" in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _watch(self) -> None:
        while not self._stop.wait(3):
            with self._lock:
                for slot_id, player in list(self._players.items()):
                    if not player.visible:
                        continue
                    try:
                        now = time.monotonic()
                        if player.process.poll() is not None:
                            if now >= player.retry_at:
                                self._recover_player(slot_id, player, "Player exited", now)
                            continue
                        if self._playback_status(player):
                            player.health.state = HealthState.live
                            player.health.detail = "Playback confirmed by OMXPlayer"
                            player.health.last_frame_monotonic = now
                            player.health.reconnect_backoff_seconds = 1.0
                            player.retry_at = 0.0
                        elif (
                            now - (player.health.last_frame_monotonic or player.started) > 30
                            and now >= player.retry_at
                        ):
                            self._recover_player(
                                slot_id, player, "Playback unconfirmed for 30 seconds", now
                            )
                    except Exception as exc:
                        # One unexpected player failure must not terminate the
                        # shared monitor and disable recovery for healthy tiles.
                        player.health.state = HealthState.offline
                        player.health.detail = "Player monitor failed; recovery will retry"
                        player.retry_at = time.monotonic() + 3
                        LOGGER.warning(
                            "OMXPlayer monitor failed for slot %s (%s)", slot_id, type(exc).__name__
                        )

    def _recover_player(self, slot_id: str, player: _Player, reason: str, now: float) -> None:
        delay = min(60.0, max(1.0, player.health.reconnect_backoff_seconds))
        player.retry_at = now + delay
        player.health.reconnect_backoff_seconds = min(60.0, delay * 2)
        player.health.restart_count += 1
        player.health.last_restart_reason = reason
        player.health.state = HealthState.reconnecting
        player.health.detail = "Restarting player"
        try:
            self._stop_player(player)
            replacement = self._start(
                player.spec, restart_count=player.health.restart_count,
                switch_count=player.health.switch_count, last_restart_reason=reason,
            )
            replacement.retry_at = player.retry_at
            replacement.health.reconnect_backoff_seconds = player.health.reconnect_backoff_seconds
            self._players[slot_id] = replacement
        except Exception as exc:
            player.health.state = HealthState.offline
            player.health.detail = f"Player restart failed; retrying in {delay:g} seconds"
            LOGGER.warning(
                "OMXPlayer restart failed for slot %s (%s)", slot_id, type(exc).__name__
            )

    def health(self) -> dict[str, Any]:
        with self._lock:
            return {
                "backend": "omxplayer", "state": "STOPPED" if self._stop.is_set() else "RUNNING",
                "sink": "HDMI hardware overlay",
                "output": {"width": self.width, "height": self.height},
                "uptime_seconds": time.monotonic() - self._started if self._started else 0,
                "streams": {key: player.health.to_dict() for key, player in self._players.items()},
            }

    def restart_stream(self, slot_id: str) -> None:
        with self._lock:
            player = self._players[slot_id]
            self._stop_player(player)
            self._players[slot_id] = self._start(
                player.spec, restart_count=player.health.restart_count + 1,
                switch_count=player.health.switch_count,
                last_restart_reason="Manual restart",
            )

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            for slot_id in list(self._prepared):
                self.cancel_prepared(slot_id)
            for player in self._players.values():
                self._stop_player(player)
            self._players.clear()
        if self._monitor is not None and self._monitor is not threading.current_thread():
            self._monitor.join(timeout=5)
            if not self._monitor.is_alive():
                self._monitor = None
