"""Probe local GStreamer decoders and persist the choices used by the wall."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    temporary.replace(path)
    return report


def load_decoder_policy(path: Path = DECODER_POLICY_PATH) -> dict[str, Any]:
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
        if report.get("schema_version") == 1 and isinstance(report.get("codecs"), dict):
            return report
    except (OSError, ValueError, AttributeError):
        pass
    return {"schema_version": 1, "codecs": {}}
