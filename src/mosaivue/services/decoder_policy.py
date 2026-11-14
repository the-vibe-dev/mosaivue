"""Probe local GStreamer decoders and persist the choices used by the wall."""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..constants import DECODER_POLICY_PATH

CODEC_CAPS = {
    "h264": "video/x-h264",
    "h265": "video/x-h265",
    "jpeg": "image/jpeg",
}
CODEC_ENCODERS = {"h264": "x264enc", "h265": "x265enc", "jpeg": "jpegenc"}
SOFTWARE_DECODERS = {
    "h264": ("avdec_h264", "openh264dec"),
    "h265": ("avdec_h265", "libde265dec"),
    "jpeg": ("jpegdec", "avdec_mjpeg"),
}
HARDWARE_PREFIXES = ("mpp", "nv", "v4l2", "omx", "va", "vulkan", "qsv", "msdk", "d3d")
_ELEMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,127}")


def codec_from_caps(caps: Any) -> str | None:
    if not caps or not caps.get_size():
        return None
    name = caps.get_structure(0).get_name()
    return next((codec for codec, media_type in CODEC_CAPS.items() if name == media_type), None)


def video_decoder_factory(factory: Any) -> bool:
    klass = (factory.get_metadata("klass") or "").casefold().split("/")
    return "decoder" in klass and ("video" in klass or "image" in klass)


def candidate_kind(codec: str, name: str, klass: str) -> str:
    if name in SOFTWARE_DECODERS[codec]:
        return "software"
    if "hardware" in klass.casefold().split("/") or name.startswith(HARDWARE_PREFIXES):
        return "hardware"
    return "unknown"


def preferred_software_decoder(codec: str, available: set[str]) -> str | None:
    return next((name for name in SOFTWARE_DECODERS.get(codec, ()) if name in available), None)


def _probe_command(codec: str, decoder: str) -> list[str]:
    encoder = {
        "h264": ["x264enc", "speed-preset=ultrafast", "tune=zerolatency", "!", "h264parse"],
        "h265": ["x265enc", "speed-preset=ultrafast", "!", "h265parse"],
        "jpeg": ["jpegenc"],
    }[codec]
    return [
        "gst-launch-1.0", "-q", "videotestsrc", "num-buffers=16", "!",
        "video/x-raw,format=I420,width=640,height=360,framerate=15/1", "!",
        *encoder, "!", decoder, "!", "fakesink", "sync=false",
    ]


def probe_decoder(codec: str, decoder: str, *, timeout: int = 12) -> str:
    if not shutil.which("gst-launch-1.0"):
        return "unprobed"
    try:
        completed = subprocess.run(
            _probe_command(codec, decoder), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, timeout=timeout, check=False,
            env={**os.environ, "GST_DEBUG": "0", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return "failed"
    return "passed" if completed.returncode == 0 else "failed"


def choose_decoders(candidates: list[dict[str, Any]]) -> dict[str, str | None]:
    passed = [item for item in candidates if item["probe"] == "passed"]
    hardware = next((item["name"] for item in passed if item["kind"] == "hardware"), None)
    software = next((item["name"] for item in passed if item["kind"] == "software"), None)
    return {"fixed": hardware or software, "rotation": software or hardware}


def working_software_decoder(codec: str, entry: dict[str, Any]) -> str | None:
    """Return a software decoder that passed the local probe for this codec."""
    passed = {
        candidate.get("name")
        for candidate in entry.get("candidates", [])
        if candidate.get("kind") == "software" and candidate.get("probe") == "passed"
    }
    return preferred_software_decoder(codec, passed)


def software_decoder_passed(codec: str, entry: dict[str, Any], decoder: str | None) -> bool:
    """Check the exact choice, even when another software decoder ranks first."""
    return decoder in SOFTWARE_DECODERS.get(codec, ()) and any(
        candidate.get("name") == decoder
        and candidate.get("kind") == "software"
        and candidate.get("probe") == "passed"
        for candidate in entry.get("candidates", [])
    )


def retain_verified_fallbacks(report: dict[str, Any], previous: dict[str, Any]) -> None:
    """Keep runtime-proven software choices across installer re-probes."""
    for codec, entry in report.get("codecs", {}).items():
        old = previous.get("codecs", {}).get(codec, {})
        if old.get("fixed_source") != "runtime_verified_software":
            continue
        software = old.get("fixed")
        if software_decoder_passed(codec, entry, software):
            entry["fixed"] = software
            entry["fixed_source"] = "runtime_verified_software"
            for key in ("runtime_verified_sink", "runtime_verified_slots", "runtime_verified_at"):
                if key in old:
                    entry[key] = old[key]


def _policy_ownership(path: Path) -> tuple[int, int]:
    try:
        previous = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        previous = path.parent.stat()
    owner = previous.st_uid if os.geteuid() in {0, previous.st_uid} else -1
    return owner, previous.st_gid


@contextmanager
def _policy_lock(path: Path, *, timeout: float = 2.0) -> Iterator[None]:
    """Serialize short policy updates across the renderer and reprobe processes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW, 0o660)
    try:
        details = os.fstat(descriptor)
        if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
            raise OSError("Decoder policy lock must be a regular file without hard links")
        if os.geteuid() in {0, details.st_uid}:
            os.fchown(descriptor, *_policy_ownership(path))
            os.fchmod(descriptor, 0o660)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Decoder policy is busy; retry the update") from None
                time.sleep(0.01)
        yield
    finally:
        # Keep the lock inode stable: unlinking it would let another writer
        # acquire a different inode while a current waiter holds this one.
        os.close(descriptor)


def _save_decoder_policy(report: dict[str, Any], path: Path) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.",
            suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fchown(handle.fileno(), *_policy_ownership(path))
            os.fchmod(handle.fileno(), 0o640)
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def detect_decoder_policy() -> dict[str, Any]:
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
    except (ImportError, ValueError):
        return {"schema_version": 1, "generated_at": datetime.now(UTC).isoformat(), "codecs": {}}

    factories = Gst.ElementFactory.list_get_elements(
        Gst.ELEMENT_FACTORY_TYPE_DECODER, Gst.Rank.MARGINAL
    )
    codecs: dict[str, Any] = {}
    for codec, media_type in CODEC_CAPS.items():
        matches = Gst.ElementFactory.list_filter(
            factories, Gst.Caps.from_string(media_type), Gst.PadDirection.SINK, False
        )
        candidates = [
            {
                "name": factory.get_name(),
                "rank": int(factory.get_rank()),
                "kind": candidate_kind(
                    codec, factory.get_name(), factory.get_metadata("klass") or ""
                ),
            }
            for factory in matches
            if video_decoder_factory(factory)
        ]
        for candidate in candidates:
            candidate["probe"] = (
                probe_decoder(codec, candidate["name"])
                if Gst.ElementFactory.find(CODEC_ENCODERS[codec])
                else "unprobed"
            )
        codecs[codec] = {**choose_decoders(candidates), "candidates": candidates}
    return {"schema_version": 1, "generated_at": datetime.now(UTC).isoformat(), "codecs": codecs}


def write_decoder_policy(path: Path = DECODER_POLICY_PATH) -> dict[str, Any]:
    report = detect_decoder_policy()
    # Probes can take minutes. Only lock the final merge/write so runtime
    # verification completed during a probe is retained in the new report.
    with _policy_lock(path):
        retain_verified_fallbacks(report, load_decoder_policy(path))
        _save_decoder_policy(report, path)
    return report


def persist_fixed_decoder_fallback(
    codec: str, decoder: str, path: Path = DECODER_POLICY_PATH
) -> bool:
    """Persist a decoder only after a real fixed camera produces frames with it."""
    with _policy_lock(path):
        report = load_decoder_policy(path)
        entry = report.get("codecs", {}).get(codec)
        if not isinstance(entry, dict) or not software_decoder_passed(codec, entry, decoder):
            return False
        if entry.get("fixed") == decoder and entry.get("fixed_source") == "runtime_verified_software":
            return True
        # Evidence about a previous decoder must not be attributed to this
        # new one. Automatic persistence proves one source produced frames.
        for key in ("runtime_verified_sink", "runtime_verified_slots", "runtime_verified_at"):
            entry.pop(key, None)
        entry["fixed"] = decoder
        entry["fixed_source"] = "runtime_verified_software"
        entry["runtime_verified_slots"] = 1
        entry["runtime_verified_at"] = datetime.now(UTC).isoformat()
        _save_decoder_policy(report, path)
        return True


def load_decoder_policy(path: Path = DECODER_POLICY_PATH) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema_version") == 1 and isinstance(report.get("codecs"), dict):
            valid_codecs = {}
            for codec, entry in report["codecs"].items():
                if codec not in CODEC_CAPS or not isinstance(entry, dict):
                    continue
                candidates = entry.get("candidates", [])
                if not isinstance(candidates, list):
                    continue
                entry["candidates"] = [
                    item for item in candidates
                    if isinstance(item, dict)
                    and isinstance(item.get("name"), str)
                    and _ELEMENT_NAME.fullmatch(item["name"])
                    and isinstance(item.get("kind"), str)
                    and item.get("kind") in {"hardware", "software", "unknown"}
                    and isinstance(item.get("probe"), str)
                    and item.get("probe") in {"passed", "failed", "unprobed"}
                ]
                for purpose in ("fixed", "rotation"):
                    selected = entry.get(purpose)
                    if not isinstance(selected, str) or not _ELEMENT_NAME.fullmatch(selected):
                        entry[purpose] = None
                valid_codecs[codec] = entry
            report["codecs"] = valid_codecs
            return report
    except (OSError, UnicodeError, ValueError, AttributeError):
        pass
    return {"schema_version": 1, "codecs": {}}
