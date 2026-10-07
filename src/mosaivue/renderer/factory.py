from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..config import Settings
from .base import RendererBackend
from .gstreamer import GStreamerRenderer
from .omxplayer import OmxPlayerRenderer


def available_backends(settings: Settings | None = None) -> list[dict[str, Any]]:
    settings = settings or Settings()
    result = [GStreamerRenderer.detect().to_dict(), OmxPlayerRenderer.detect().to_dict()]
    if settings.allow_test_backend or os.environ.get("MOSAIVUE_TESTING") == "1":
        from .testing import TestRenderer

        result.append(TestRenderer().capabilities().to_dict())
    return result


def create_backend(settings: Settings) -> RendererBackend:
    requested = settings.renderer_backend
    omx = OmxPlayerRenderer.detect()
    if requested == "omxplayer" and omx.available:
        return OmxPlayerRenderer()
    if requested == "auto" and omx.available:
        try:
            model = Path("/proc/device-tree/model").read_bytes().decode(errors="replace")
        except OSError:
            model = ""
        if any(f"Raspberry Pi {generation}" in model for generation in ("1", "2", "3", "Zero")):
            return OmxPlayerRenderer()
    capabilities = GStreamerRenderer.detect()
    if requested in {"auto", "gstreamer"} and capabilities.available:
        return GStreamerRenderer()
    if requested == "test" and (settings.allow_test_backend or os.environ.get("MOSAIVUE_TESTING") == "1"):
        from .testing import TestRenderer

        return TestRenderer()
    if requested == "auto":
        raise RuntimeError(
            "No production renderer is available. Install GStreamer core/good/bad/ugly/libav plugins and python3-gi."
        )
    raise RuntimeError(f"Renderer backend {requested!r} is not available on this system")
