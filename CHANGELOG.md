# Changelog

All notable changes follow a Keep a Changelog-style format. Version numbers use semantic versioning after the first stable release.

## Unreleased

### Fixed

- GStreamer rotation preconnects a sequential or reverse camera and switches only after decoded video arrives. A two-camera group keeps both source branches running between cuts, avoiding decoder teardown and a black tile on the tested ROCK Pi 4B+.
- An active GStreamer rotation source error now requests a switch to its warm alternate through the rotation controller. The bus callback keeps the renderer loop responsive instead of stopping an RTSP decoder there.
- Failed prepared and fixed GStreamer sources reset on a GStreamer worker thread, so a blocked RTSP shutdown cannot stall the shared video loop. If that reset does not produce frames, a fresh source branch is opened; the retired decoder, queue, and selector pad are then stopped and removed asynchronously instead of accumulating RTSP connections.
- If rotation feeds remain without frames, the tile reports STALLED while other live tiles continue. A blocked RTSP teardown can trigger a renderer restart after two minutes of stalled rotation, with a longer cooldown to limit wall interruptions.
- Rotation RTSP sources select only video tracks before SETUP. Cameras that advertise audio no longer open those unused RTP streams in the video-only renderer branch.
- Negotiation errors from a slot's black placeholder are excluded from camera failure handling, preventing false failovers and decoder resets.
- A stalled rotating tile selects its live placeholder while both RTSP feeds reconnect. Input selectors do not synchronize inactive camera pads to the active stream, so a standby decoder can keep consuming live frames between cuts. The compositor ignores input pads that have not produced a buffer and reserves latency for dynamically attached RTSP sources.
- The Rock Pi camera profiles that needed more RTSP jitter tolerance can use the `stable` latency preset.
- Installer release roots retain service-account traversal permissions when staged from a private temporary directory; the renderer starts before the web service so its runtime directory exists for both units.
- Inactive GStreamer selector pads keep accepting live standby buffers, and a camera that produces no first frame receives a targeted retry. Rotation recovery retries its own tile during startup before considering a renderer recycle.
- OMXPlayer waits for 30 seconds without a successful playback confirmation before restarting a player; a single transient D-Bus check failure no longer triggers a restart on an established tile.
- The web server starts serving requests before its hardware capability refresh finishes, reducing dashboard startup delay on the tested Pi 3B+.
- GStreamer RTSPS sources can use an app-scoped PEM CA file through `rtsp_tls_ca_file`, allowing private NVR certificates to be validated when the URL uses a matching hostname.

## [0.1.0b1] - 2026-10-07

### Added

- OMXPlayer selection for legacy Pi hardware in setup, dashboard, renderer API, and configuration.
- RTSPS camera URLs through camera storage, playback, probing, and previews.
- Supplied Mosaivue wordmark, PNG favicon, and coordinated light dashboard and editor styling.
- Featured-first templates for two through ten cameras and click-to-place tile editing with eight resize handles.
- Standalone curl installer with release checksums and a pinned Python 3.11 runtime for 32-bit Bullseye Pi OS.
- Beta scope, hardware evidence, and security boundaries in the public documentation.

### Fixed

- Layout creation, camera drag and drop, templates, and slot IDs on HTTP appliance pages.
- Preview aspect modes and an FFmpeg retry when GStreamer thumbnail capture fails.
- Legacy OMXPlayer aspect selection and rotation handoff. The next player is prepared offscreen below the current overlay, then positioned and raised for a cut. A failed preparation keeps the current camera visible.
- Planned rotation switches counted separately from recovery/manual restarts.
- The rotation timer prepares the next sequential camera during the interval; preload is bounded to one extra decoder.
- Backend-aware DRM messages, honest VLC availability, and a security audit that accepts the service-owned 0640 key while checking database permissions.
- Full product and system rename to Mosaivue, with test Pi database and credential-key migration and rollback.

## Initial implementation (internal) - 2026-10-02

### Added

- Persistent SQLite camera registry with encrypted credentials and multiple stream profiles.
- Normalized, revisioned layout model with fixed, manual, rotation, and empty slots.
- Responsive browser administration and full visual drag/resize layout editor.
- Independent rotation groups with sequential, reverse, random, and weighted selection.
- Single-compositor GStreamer renderer backend with per-stream branches, health states, placeholders, and reconnect handling.
- Isolated renderer process controlled over a local Unix socket.
- FastAPI REST API, OpenAPI, SSE status updates, login/setup flow, CSRF protection, and security headers.
- CLI, Textual TUI, display remote, schedules, focus/restore, backups, support bundles, diagnostics, benchmark, and optimize recommendation.
- `displaycameras` migration utility.
- Systemd units, installer, uninstaller, update helper, release and Debian packaging scripts.
- Unit, integration, renderer-contract, API, migration, backup, and frontend tests.

### Security

- AES-256-GCM credential storage with a locally generated 256-bit key.
- Scrypt password hashing and encrypted-backup key derivation.
- Secret redaction for logs, support bundles, API outputs, and default exports.
- Restricted systemd service accounts and filesystem write paths.

### Known qualification work at initial implementation

- Pi 4/5 physical DRM/KMS and stream-count performance data remains to be recorded using the included hardware test plan. Pi 3 OMXPlayer beta evidence is now in `docs/beta-release.md`.
- GStreamer element availability varies by distribution image and installed plugins; `mosaivue doctor` records the actual system.
