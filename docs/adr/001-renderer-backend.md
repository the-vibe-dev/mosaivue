# ADR 001: GStreamer as the primary renderer

- Status: Accepted
- Date: 2026-10-02

## Context

Mosaivue needs multiple RTSP sources, independent reconnect, arbitrary geometry, dynamic source replacement, low latency, and direct Linux display output without relying on deprecated OMXPlayer/OpenMAX APIs.

## Decision

Use a `RendererBackend` abstraction and ship GStreamer as the production backend. Build one compositor pipeline with independently managed source branches and select an available DRM/KMS, GL, Wayland, or X11 sink. Keep native FFmpeg/DRM and other player backends possible but do not advertise an unimplemented backend.

## Consequences

GStreamer and PyGObject become platform dependencies. Element names and hardware acceleration vary by distribution, so capability detection and hardware qualification are mandatory. Python orchestrates native elements rather than decoding frames itself.
