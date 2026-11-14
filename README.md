![Mosaivue logo](frontend/src/brand/mosaivue-logo.png)

# Mosaivue

**The flexibility of displaycameras without the painful configuration.**

Mosaivue is a local-first camera-monitor appliance for Raspberry Pi and Linux. It stores cameras once, lets you place them on a visual canvas, applies layout changes to an HDMI display without rebooting, and rotates selected tiles without disturbing fixed cameras.

Mosaivue is designed for Raspberry Pi OS Lite and does not require a desktop session. The control plane, camera credentials, layouts, health data, and previews stay on the appliance. There is no required cloud account, analytics service, or telemetry.

> **Candidate source: 0.1.0b5.** This update adds guarded layout editing and activation, display-profile assignment/editing, reliable decoder-preference persistence, and observation analysis. See the [changelog](CHANGELOG.md), [build verification](BUILD-VERIFICATION.md), and [installation guide](docs/install.md). The earlier b4 appliance observations do not qualify the changed b5 runtime.

> **Published baseline (0.1.0b2):** v0.1.0b2 is the first public beta. In a 23-hour sample window, the tested Pi 3B+, ROCK Pi 4B+, and Ubuntu GPU walls each kept seven of seven tiles LIVE with one renderer process and advancing rotation. The ROCK Pi's installer-managed 640×360 normalization kept its two 16:9 rotating feeds on matching caps through more than 5,500 cuts; one fixed tile recovered from a cold-start retry. These are site results, not stream-count guarantees. Other camera aspect ratios and Raspberry Pi 4/5 physical output remain unqualified. See [beta notes](docs/beta-release.md).

Mosaivue is a work-in-progress open-source project. TideCore is not currently selling it as a software product, subscription or commercial package. The existing Apache-2.0 permissions and notices remain in effect.

## Release and source status

| Track | Status | Documentation |
| --- | --- | --- |
| v0.1.0b2 | Released public beta | [Versioned README](https://github.com/the-vibe-dev/mosaivue/blob/v0.1.0b2/README.md) and the pinned archive install below. |
| main / 0.1.0b5 | Development candidate | This README and BUILD-VERIFICATION.md describe candidate behavior; this is not a published b5 release. |

## Features in the b5 development candidate

- Persistent camera registry with stable multiple RTSP profiles per camera, plus ONVIF Media1 profile import from a known device-service endpoint
- Camera passwords encrypted at rest with AES-256-GCM and omitted from camera API responses. Usernames remain available to authenticated administrators; sanitized exports omit username/password fields. Opaque secrets inside stream URLs are a separate unresolved boundary. The legacy OMXPlayer backend passes a resolved stream URL to its local player process; see [security boundaries](docs/security.md).
- Reusable layouts stored in normalized coordinates, with optional pixel overrides
- Drag, resize, multi-select, align, distribute, duplicate, lock, undo, redo, copy, paste, grid snap, and exact geometry in the browser editor
- Fixed, manual/selectable, empty, and independently rotating slots
- Sequential, reverse, random, and weighted rotation groups
- Automatic source-profile selection so small tiles can use camera substreams
- GStreamer compositor with isolated per-stream branches and an OMXPlayer option for legacy Pi hardware
- Per-stream health, reconnect backoff, placeholder fallback, and independent stream restart
- Layout revision history, guarded concurrent editing with reload/save-copy recovery, synchronous activation rollback, and saved/applied revision identity with explicit reapplication
- Shared display-profile creation/editing and assignment, custom layout dimensions, and profile-aware schematic previews
- Focus/fullscreen camera mode with restore
- Browser-managed overnight/day schedules, phone-friendly display remote, and session-scoped Server-Sent Events
- FastAPI REST API and OpenAPI documentation
- CLI and Textual TUI
- Raspberry Pi/Linux capability detection, diagnostics, benchmark, optimizer recommendations, and sanitized support bundles
- Sanitized configuration export plus passphrase-encrypted configuration backups including camera credentials (not full operating-system images)
- `displaycameras` configuration migration with dry-run reporting
- Idempotent installer, conservative uninstaller, update helper, systemd hardening, source releases, and Debian packaging scripts
- Unit, integration, API, renderer-contract, migration, backup, and frontend tests
- Typed appliance settings, bounded/coalesced preview and probe work, short internal JPEG caching, and an explicit backend capability matrix

Browse the [documentation index](docs/index.md) for installation, camera setup, layouts, rendering, security, and beta qualification.

## Screenshots

These three images match the files in the released **v0.1.0b2** source tag, verified by byte comparison on November 14, 2026. They illustrate b2 and were not regenerated as b5 browser evidence.

### Appliance dashboard

![Mosaivue dashboard showing the active camera wall and system health](docs/images/dashboard.png)

### Drag-and-resize layout editor

![Mosaivue layout editor with saved cameras, freeform display canvas, and tile inspector](docs/images/layout-editor.png)

### Phone display remote

![Mosaivue phone remote for changing layouts and focusing a camera](docs/images/remote-mobile.png)

Screenshot labels: **released v0.1.0b2**, not b5 screenshots. Regenerate and label the exact source version before using new images as release evidence.

Regenerate these from a demo or test appliance with:

```bash
MOSAIVUE_SCREENSHOT_USER=demo \
MOSAIVUE_SCREENSHOT_PASSWORD='your-local-password' \
MOSAIVUE_SCREENSHOT_URL=http://127.0.0.1:8080 \
./scripts/capture-screenshots.sh
```

## Supported targets

| Platform | Intended support | Notes |
|---|---|---|
| Raspberry Pi 5, 64-bit Raspberry Pi OS Lite | Primary | DRM/KMS or GL/Wayland sink selected from detected capabilities |
| Raspberry Pi 4, 64-bit Raspberry Pi OS Lite | Primary | Prefer H.264 substreams where that best matches available decode support |
| Raspberry Pi 3B+ with Bullseye 32-bit and OMXPlayer | Tested beta path | One site ran seven live feeds at 1920×1080 for over 12 days; other camera mixes need measurement |
| ROCK Pi 4B+ | Tested beta path | Debian 12 arm64, Rockchip MPP, `kmssink`: one seven-tile 1920×1080 wall completed a 23-hour sampled run with a 16:9 rotating pair; other camera mixes need qualification |
| Debian/Ubuntu ARM64 | Supported | Hardware decode depends on board and installed GStreamer plugins |
| Debian/Ubuntu x86_64 | Supported | Useful for development and Intel/AMD appliance builds |

Mosaivue never hard-codes a stream-count promise. Run `mosaivue benchmark` and follow `docs/performance.md` on the actual appliance.

## Clean installation

For the released **v0.1.0b2 public beta**, download the versioned source archive, check its checksum, inspect it and install on a supported test appliance:

```bash
curl -fLO https://github.com/the-vibe-dev/mosaivue/releases/download/v0.1.0b2/mosaivue-0.1.0b2-source.tar.gz
curl -fLO https://github.com/the-vibe-dev/mosaivue/releases/download/v0.1.0b2/mosaivue-0.1.0b2-source.tar.gz.sha256
sha256sum -c mosaivue-0.1.0b2-source.tar.gz.sha256
tar -xzf mosaivue-0.1.0b2-source.tar.gz
cd mosaivue-0.1.0b2
sudo bash installer/install-local.sh
```

These fixed URLs install b2, even when `main` changes. The published checksum detects a mismatched download; it is not a separate signing or trust authority. Read the scripts before running them with `sudo`. The automatic installer supports Debian and Raspberry Pi OS 12+, Ubuntu 24.04+, and legacy 32-bit Raspberry Pi OS 11 with an existing OMXPlayer installation. It needs `sudo`, internet access for packages, and a systemd host. See [installation requirements and rollback](docs/install.md).

To evaluate the **0.1.0b5 development candidate** from a separately obtained b5 source archive:

```bash
tar -xzf mosaivue-0.1.0b5-source.tar.gz
cd mosaivue-0.1.0b5
sudo bash installer/install-local.sh
```

Useful options:

```bash
sudo ./install.sh --non-interactive
sudo ./install.sh --no-start
sudo ./install.sh --bind 127.0.0.1
sudo ./install.sh --dev
```

The normal appliance install explicitly binds the web server to the LAN (`0.0.0.0`) and prints that decision. Use `--bind 127.0.0.1` for reverse-proxy-only or local administration.

The installer prints the detected display, renderer report, web URL, and one-time setup token. Open the URL, enter the token, and create the first administrator.

```text
Mosaivue installed successfully.

  Web setup:    http://192.168.1.50:8080
  Setup token:  MV-XXXXXX-XXXXXX-XXXXXX
  Terminal UI:  sudo -u mosaivue mosaivue tui
  Diagnostics:  mosaivue doctor
```

The standalone bootstrap can select a newer published release and is intentionally not the reproducible b2 path above. Use the local b5 source instructions only when you deliberately want the development candidate; b2 hardware observations do not qualify b5.

The bootstrap script can be inspected before the `sudo bash` step. It downloads the newest public release archive and checks its SHA-256 checksum before installing.

## First camera wall

1. Open **Cameras**, select **Add camera**, and enter an RTSP or RTSPS URL.
2. Use **Test stream** to inspect connection time, codec, resolution, transport, decoder selection, and time to first frame.
3. Add lower-resolution substreams when the camera exposes them.
4. Open **Layouts**, create a layout, and drag saved cameras onto the canvas.
5. Resize or position the tiles, choose `contain`, `cover`, or `stretch`, then select **Save & Apply**. The editor disables controls that the selected backend reports as unsupported; `native` pixel sizing is not implemented by the current physical backends.
6. Create a **Rotation group**, choose its cameras and interval, and assign it to one slot. Fixed slots remain in place while that slot rotates.

## Migrate displaycameras

Preview the import first:

```bash
sudo mosaivue migrate displaycameras --dry-run
```

Apply it after reviewing warnings:

```bash
sudo mosaivue migrate displaycameras
```

Custom paths can be supplied more than once:

```bash
sudo mosaivue migrate displaycameras \
  --source /etc/displaycameras/displaycameras.conf \
  --source /etc/displaycameras/layout.conf.1920x1080
```

The migration reads camera arrays, RTSP URLs, rectangles, and resolution hints; creates reusable cameras; converts pixels to normalized geometry; and leaves the original files untouched.

## CLI examples

```bash
mosaivue status
mosaivue doctor --json
mosaivue camera list
mosaivue camera add --name Driveway --url 'rtsp://192.168.1.20/stream'
mosaivue camera edit CAMERA_ID --name "Front Door"
mosaivue camera test CAMERA_ID
mosaivue layout create --name Night
mosaivue layout list
mosaivue layout export LAYOUT_ID night-layout.json
mosaivue layout import night-layout.json --name "Night Copy"
mosaivue layout activate LAYOUT_ID
mosaivue rotation stop GROUP_ID
mosaivue renderer status --json
mosaivue benchmark --streams 6 --width 1920 --height 1080
mosaivue backup --output mosaivue-sanitized.zip
mosaivue backup --include-credentials --output mosaivue-complete.cwbackup
mosaivue support-bundle
mosaivue config validate
mosaivue security audit
mosaivue tui
```

## Services and logs

```bash
systemctl status mosaivue-renderer.service mosaivue-server.service
journalctl -u mosaivue-renderer.service -f
journalctl -u mosaivue-server.service --since '1 hour ago'
```

The renderer and API are separate processes. A renderer crash does not remove the web control plane, and systemd restarts it independently.

## Configuration and data

| Path | Purpose |
|---|---|
| `/etc/mosaivue/config.json` | Non-secret application settings |
| `/etc/mosaivue/master.key` | Local credential-encryption key, mode `0640` and readable only by root and the dedicated `mosaivue` group |
| `/etc/mosaivue/setup-token` | One-time setup token; consumed after use (removed where permitted; otherwise emptied) |
| `/etc/mosaivue/install-prefix` | Installation root used by update and uninstall helpers |
| `/var/lib/mosaivue/mosaivue.db` | SQLite configuration database |
| `/var/lib/mosaivue/capabilities.json` | Last hardware/renderer capability report |
| `/run/mosaivue/renderer.sock` | Local renderer RPC socket |
| `/var/log/mosaivue/` | Installer/diagnostic logs; runtime logging uses journald |

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cd frontend && npm run build && cd ..
cp -a frontend/dist/. src/mosaivue/static/
pytest
./scripts/dev.sh
```

GObject introspection and GStreamer are installed through the operating system. On Debian/Raspberry Pi OS, use a virtual environment created with `--system-site-packages` so PyGObject can use the distribution GStreamer bindings.

## Hardware qualification

The project includes a synthetic compositor benchmark and a [hardware test plan](docs/hardware-test-plan.md). A Pi 3B+ OMXPlayer wall and a ROCK Pi 4B+ GStreamer/KMS wall have site-specific results. The automated build environment has no physical display. Raspberry Pi 4 and Pi 5 still need measured output and decode results before hardware claims.

## Security and privacy

- The web UI requires initial setup and authentication.
- Sessions use HttpOnly, SameSite cookies; state-changing requests require CSRF tokens.
- Passwords use scrypt; RTSP secrets use AES-256-GCM with per-record authenticated context.
- RTSP passwords are not returned to the browser after saving.
- Support bundles and default exports are sanitized and covered by automated redaction tests.
- The backend accepts RTSP/RTSPS URLs only and does not expose a generic unauthenticated URL fetcher.
- OMXPlayer receives the resolved camera URL as a process argument. Limit local shell access to trusted operators and use read-only camera accounts.
- No telemetry or cloud account is present.

See `SECURITY.md` and `docs/security.md` before exposing Mosaivue beyond a trusted LAN. HTTPS is expected at a reverse proxy for untrusted networks.

## Uninstall

```bash
sudo mosaivue uninstall
```

Application files are removed, while configuration and the database are preserved unless you explicitly choose to delete them. Non-interactive purge is available as `sudo ./uninstall.sh --purge`.

## Support and contributions

For reproducible setup or behavior problems, use [GitHub Issues](https://github.com/the-vibe-dev/mosaivue/issues). Include the exact release/commit, OS, renderer and sanitized diagnostics; do not publish camera credentials. Report sensitive issues using [SECURITY.md](SECURITY.md). Read [CONTRIBUTING.md](CONTRIBUTING.md) before proposing code, documentation or hardware reports. Community support has no guaranteed response time.

## License

Mosaivue core is licensed under Apache-2.0. No source from OMXPlayer is included. A future OMXPlayer-derived legacy component must remain isolated and separately GPL-licensed. See `NOTICE` and `THIRD_PARTY_NOTICES.md`.
