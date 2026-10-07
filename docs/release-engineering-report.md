# Initial engineering report (2026-10-02)

This records the first software build. Current Pi 3 beta evidence, v0.1.0b1
changes, and remaining publication limits are in [beta release notes](beta-release.md).

## Architecture

Mosaivue comprises a FastAPI/SQLite control plane, native TypeScript browser application, Textual TUI, Typer CLI, isolated renderer daemon, and GStreamer and legacy OMXPlayer backends. Cameras, credentials, layouts, revisions, rotation groups, display profiles, schedules, sessions, settings, and audit records are persistent models.

## Renderer decision

GStreamer is the primary renderer because a single compositor pipeline can own independent RTSP branches and update pad geometry/source state without launching a player process per tile. The OMXPlayer adapter supports legacy Raspberry Pi images whose hardware overlay path performs better than the Bullseye GStreamer compositor. VLC and mpv are not Mosaivue backends.

## Hardware behavior

Capability detection records Pi model, CPU/RAM, kernel, DRM outputs, GStreamer elements, multimedia tools, and decoder candidates. Policy can choose lower profiles by tile size. This report predates the Pi 3B+ OMXPlayer site result; Pi 4/5 results remain unmeasured.

## Performance

The synthetic benchmark is implemented. The original build environment had no Pi hardware. See the beta notes for later site measurements and the hardware test plan for required evidence.

## Installation

`sudo ./install.sh` performs detection, dependencies, service account/directories, staged versioned install, virtual environment, key/token/database setup, systemd setup, capability smoke test, enable/start, and first-run output.

## Migration

`mosaivue migrate displaycameras --dry-run` parses common shell arrays and layout files, separates credentials, converts rectangles to normalized geometry, and reports warnings. Applying creates new records without changing original files.

## Known limitations

- Physical DRM/KMS and hardware-decoder qualification requires target hardware.
- OMXPlayer uses a bounded one-camera preconnect for sequential and reverse rotation groups. GStreamer preconnect and broader hardware qualification remain future work.
- Optional ONVIF, WebRTC preview, multi-monitor, MQTT, Home Assistant, and event focus are roadmap plugins, not fake v0.1 controls.
- Automatic update discovery requires the release repository/API to be configured for the published project.

## Security review

Authentication, CSRF, XSS/CSP, URL scheme validation, command invocation, credential encryption, key permissions, systemd privileges, backup/support-bundle leakage, session cookies, local RPC, and dependency inventory were reviewed. The release pass corrected a concurrent SQLite write-lock caused by session reads, aligned Server-Sent Events with the browser client, tightened the CSP while preserving the geometry editor, and fixed service-account access to the root-owned credential key/setup token without making either readable to ordinary users. Tests cover encryption, URL stripping, response/export redaction, CSRF, encrypted backups, concurrent authenticated reads, and event framing.

## Testing

The initial automated run completed 21 Python unit/integration/API/renderer tests and 2 frontend tests. TypeScript type checking and the production frontend build passed. A separate authenticated Chromium E2E test passed and verified login, dashboard loading, layout-editor sizing, slot selection, keyboard movement, and undo. Later beta checks are in [Build verification](../BUILD-VERIFICATION.md). Hardware failure testing remains separate so CI cannot claim a Pi/DRM pass.

## Repository readiness

The repository contains source, frontend, renderer, CLI/TUI, installer/uninstaller/update, systemd, migrations, tests, CI, packaging, docs, generated OpenAPI, SPDX dependency inventory, screenshots, samples, and community files. Before a public stable tag: run the target-hardware qualification matrix, select/sign the final release artifacts, and replace any repository coordinates only if the publication organization changes.
