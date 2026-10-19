# Changelog

All notable changes follow a Keep a Changelog-style format. Version numbers use semantic versioning after the first stable release.

## Unreleased

### Fixed

- GStreamer rotation preconnects a sequential or reverse camera and switches only after decoded video arrives. A two-camera group keeps both source branches running between cuts, avoiding decoder teardown and a black tile on the tested ROCK Pi 4B+.
- An active GStreamer rotation source error now requests a switch to its warm alternate through the rotation controller. The bus callback keeps the renderer loop responsive instead of stopping an RTSP decoder there.
- Failed prepared and fixed GStreamer sources reset on a GStreamer worker thread, so a blocked RTSP shutdown cannot stall the shared video loop. A stale prepared source is retried before the next rotation cut.
- The Rock Pi camera profiles that needed more RTSP jitter tolerance can use the `stable` latency preset.

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
