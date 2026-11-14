# Changelog

All notable changes follow a Keep a Changelog-style format. Version numbers use semantic versioning after the first stable release.

## [0.1.0b4] - 2026-11-13 - follow-up review candidate

Built from the newly supplied b3 archive. No database migration was added. Python/source version is `0.1.0b4`; frontend is `0.1.0-beta.4`; Debian is `0.1.0~b4`. This candidate has not been deployed or published by this review. Supplied b3 integration/appliance evidence is retained unchanged in `docs/review/supplied-b3-build-verification.md`.

### Added and improved

- Typed compatible settings and per-process preview/probe concurrency, duplicate coalescing, retryable saturation and bounded short JPEG caching.
- Renderer feature/limitation reporting and matching UI capability matrix; unsupported physical controls are disabled while existing metadata is preserved.
- Saved/applied/focused/unknown layout states, explicit Reapply, and save-success/apply-failure recovery without duplicate revisions.
- JSON configuration reimport, concrete layout validation errors, fixed-pixel conversion guidance and accessible mobile editor drawer controls.
- Current review, competitor research, prioritized findings, acceptance checklist and updated operating documentation.

### Fixed

- The phone-sized Tile inspector now stacks above selected canvas tiles, so its controls remain usable.
- The ROCK Pi KMS sink now requests a fullscreen video plane at each renderer start, filling the connected mode without disabling aspect preservation. A fixed GStreamer tile with no first frame can retry a locally probed software decoder; successful real-frame fallback is saved and retained across installer re-probes.
- Manual Previous/Next prepares the actual requested standby and preserves the current source/cursor on readiness failure.
- OMX spawn failures no longer kill shared recovery; scheduler/rotation database failures retry; essential daemon tasks are supervised.
- Long renderer mutations have a separate response budget; capability/settings JSON replacement is atomic.
- Restored layouts whose current revision is older than saved drafts allocate the next unused revision.
- Installed releases use explicit root ownership, protected ancestors and safe release-directory entries, removing lingering source-owner authority over privileged helpers.
- Editable virtual environments survive staging rename; Bullseye wheels follow the selected CPython ABI; IPv6/local proxy health checks use the intended local endpoint.
- Documentation distinguishes encrypted passwords from visible usernames and opaque URI-token risks, and separates accepted revisions from verified physical playback.

### Evidence and open work

- Current Python suite: 358 passed, three environment/privilege skips; JavaScript: 35 passed. Current combined statement/branch coverage is 62.44% versus 59.50% on the uploaded archive.
- Browser interaction and b4 physical/privileged installation acceptance remain unexecuted here. See [current validation](docs/review/current-validation.md) for exact scope and [the roadmap](ROADMAP.md) for unresolved capability and architecture gaps.

## [0.1.0b3] - 2026-11-13 — review candidate

This is a locally delivered review candidate. It has not been published automatically or qualified as a new hardware release. No database schema migration was added by this review. Python/source version is `0.1.0b3`; Debian prerelease version is `0.1.0~b3`.

### Added

- Known-endpoint ONVIF Media1 profile inspection/import with administrator authentication, bounded SOAP exchanges and credential-safe profile metadata. WS-Discovery, Media2 and PTZ are outside this implementation.
- Browser schedules management, camera/layout duplication and filtering, and uniform 2×2, 3×3 and 4×4 starting grids.
- `MOSAIVUE_OUTPUT_FPS` for GStreamer compositor output: integer 1–60, with the existing 5 FPS default retained. This does not change camera capture FPS or monitor refresh.
- Review report, competitor/gap analysis, regression evidence and candidate upgrade guidance in `docs/review/`.

### Fixed

- The 32-bit Bullseye installer selects verified upstream ARMv7 `cryptography` and `pydantic-core` wheels and imports the web/renderer entry points before stopping existing services; this avoids piwheels binaries that require unavailable `libssl.so.3` or glibc 2.34.
- Camera edits with no saved credentials no longer create an encrypted empty password; the API reports a username-only camera as having no password.
- Sanitized configuration merges retain local camera credentials; restoration remaps selected stream-profile references, preserves the exported current revision, avoids revision uniqueness collisions and retains a single active wall.
- Nested import validation and SQLite transaction handling reject invalid graphs and roll back failed imports. API restore separates saved configuration from successful renderer application; CLI restore/import prints the required reapply instruction.
- Camera/profile edits preserve stable identities and metadata. Referenced cameras/profiles/groups cannot be removed from current configurations without resolving their references.
- Manual-slot/profile/display validation, pixel-override validation and output clipping, IPv6 credential round trips and malformed stream URL handling.
- Password changes revoke other sessions; simultaneous setup creates one initial administrator; concurrent key initialization publishes one complete key. SSE revalidates sessions and mutations publish events after database commit.
- Duplicate-name updates return conflicts, preview-disable settings take effect, and stream tests honor configured transport and require successful discovery with usable video.
- Discovery time is no longer reported as decoded first-frame time. Unmeasured first-frame/decoder fields remain unavailable rather than implying a measurement.
- Independent rotation-slot cursors, selected entry profiles, disabled source/group handling and distinct Skip/Hold retry behavior. Failed synchronous layout/focus changes preserve previous controller state where recoverable.
- Overnight schedule starting-day/end-boundary behavior and reapplication of an active scheduled wall after a manual change. Focus pauses schedule application; expiry does not select an automatic fallback wall.
- GStreamer source-failure attribution by element ownership, OMXPlayer transport/control contracts, and renderer RPC framing/error/shutdown handling.
- Form validation/cancel paths, profile-edit data preservation, dirty-layout handling and persistent restore-result warnings in the browser interface.
- A rotating GStreamer tile with blocked RTSP branch teardown continues recovery despite sporadic decoded frames and can recycle its renderer after two minutes of blockage while STALLED.

### Security and installation

- Protect `/etc/mosaivue` as root-owned `0750`; keep root-consumed metadata non-writable by the service account. The setup token alone is group-writable for consumption without directory writes.
- Validate root-consumed metadata, dedicated install/removal prefixes and link entries before privileged writes; retain previous release/state for the installer's failure-recovery path.
- Bound backup reads and expanded configuration size. Safe restore/import validation errors omit sensitive inputs; unexpected exceptions do not echo SQL parameters.
- Redact URL userinfo and named sensitive query parameters from diagnostics. Full-URI encryption for opaque vendor bearer tokens remains outstanding.
- Correct Debian prerelease ordering and checksum filenames; retain source/wheel version compatibility.

### Qualification and known boundaries

- The [validation record](docs/review/validation.md) distinguishes completed software checks from browser, systemd installer and physical camera/display trials still required.
- Existing site hardware evidence applies to earlier builds and does not automatically qualify this candidate.
- Group-level `placeholder` failure policy and synchronized rotation remain unimplemented; legacy placeholder settings behave as Hold.
- Configuration backups exclude appliance settings, custom trust files, web accounts/sessions and OS/service provisioning. Reapply active layouts after camera/group edits and CLI configuration import/restore.

## [0.1.0b2] - 2026-11-02

### Changed

- First public beta release following private `0.1.0b1` staging, with public installation instructions and updated package metadata. Renderer and installer behavior is unchanged from the private beta.

## [0.1.0b1] - 2026-11-02

### Added

- OMXPlayer selection for legacy Pi hardware in setup, dashboard, renderer API, and configuration.
- RTSPS camera URLs through camera storage, playback, probing, and previews.
- Supplied Mosaivue wordmark, PNG favicon, and coordinated light dashboard and editor styling.
- Featured-first templates for two through ten cameras and click-to-place tile editing with eight resize handles.
- Standalone curl installer with release checksums and a pinned Python 3.11 runtime for 32-bit Bullseye Pi OS.
- Beta scope, hardware evidence, and security boundaries in the public documentation.

### Fixed

- Debian release checksum files now use the package filename, so verification works after downloading assets from GitHub.
- The Rockchip installer now enables tested fixed caps for rotating GStreamer cameras when MPP/KMS and normalization plugins are present, with an explicit aspect-ratio target option and rollback of the systemd setting. Camera probing reads codec caps on GStreamer bindings that do not expose `DiscovererVideoInfo.get_codec()`.

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

- Layout creation, camera drag and drop, templates, and slot IDs on HTTP appliance pages.
- Preview aspect modes and an FFmpeg retry when GStreamer thumbnail capture fails.
- Legacy OMXPlayer aspect selection and rotation handoff. The next player is prepared offscreen below the current overlay, then positioned and raised for a cut. A failed preparation keeps the current camera visible.
- Planned rotation switches counted separately from recovery/manual restarts.
- The rotation timer prepares the next sequential camera during the interval; preload is bounded to one extra decoder.
- Backend-aware DRM messages, honest VLC availability, and a security audit that accepts the service-owned 0640 key while checking database permissions.
- Full product and system rename to Mosaivue, with test Pi database and credential-key migration and rollback.

### Security

- Update the minimum `cryptography` version to 50.0.2 so installer builds can receive patched OpenSSL and cryptography fixes. Require HTTPS for update checks, verify OMXPlayer's D-Bus address file owner and mode, and restrict the renderer RPC socket to the service account.

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
