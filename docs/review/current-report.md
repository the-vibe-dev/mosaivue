# Mosaivue: full review and improved b4 candidate

**Review date:** November 13, 2026. **Input:** `mosaivue-main (3).zip`, version 0.1.0b3. **Output:** 0.1.0b4 review candidate. The source, compiled interface, reports, evidence and installable build artifacts are delivered together. This is an unpublished candidate; the review did not operate a real appliance.

## 1. Decision and executive assessment

Mosaivue has a useful foundation for a local camera-wall appliance: a reusable camera registry, visual normalized layout editing, separate control-plane and renderer processes, independently rotating tiles, configuration history, encrypted password storage and a practical migration path from displaycameras. The supplied b3 integration and Pi observations provide meaningful progress beyond the earlier software-only review. The best next step is to qualify this strengthened single-appliance candidate and finish its state/recovery contracts before promising broader display support.

The most important problems in the supplied code were operational correctness, not a shortage of settings. A wall could be described as active while an older revision was actually running; manual Previous could try to activate the wrong preconnected source; a recoverable OMX process error or database read failure could permanently stop background work. Preview requests had no shared decoder budget. Restoring an older selected layout revision could make the next edit collide with existing history. The installer also had remaining editable-install and network-health edge cases.

Those paths are corrected in this candidate. The interface now differentiates saved, pending, applied, focused and unavailable states; supports explicit reapplication; preserves a saved revision when application fails; exposes honest backend capabilities; restores access to mobile editor drawers; and imports the JSON that it exports. Backend and installer changes add typed settings, atomic writes, bounded preview/probe work, resilient recovery, appropriate RPC deadlines and correct staged virtual-environment relocation.

The combined Python result is **358 passed, three skipped**, compared with **246 passed, one skipped** on the newly uploaded archive in the same environment. JavaScript tests increased from **20 to 35 passing cases**. Combined statement/branch coverage increased from **59.50% to 62.44%**. These are useful software improvements, but the remaining coverage gaps include substantial native-media and appliance behavior. The candidate is ready for controlled acceptance, not a claim of universal camera capacity or verified HDMI playback.

### What was preserved from your supplied archive

Only eight files differed from the previous delivered b3 source. The input already included the earlier review's integrity/security/onboarding fixes, plus your correction for null-only camera credential edits, exact Pydantic pin, checksum-pinned upstream Bullseye ARMv7 dependency wheels and API/renderer/AES-GCM preflight before stopping services. These changes remain in b4; they are not credited as new fixes from this pass.

Your supplied `BUILD-VERIFICATION.md` records 247 Python tests, 20 JavaScript tests and five Chromium workflows on another host. It also records a successful corrected Pi 3B+/Bullseye/OMX upgrade and reboot, initially 7/7 LIVE, 19 switches and zero restarts. Earlier failed installs restored the previous wall. A new observer started at 15:13 UTC on November 13; no completed soak was supplied. The Ubuntu VM demonstrated one real NVIDIA-decoded headless source with advancing frames, but physical output remained unqualified and the renderer was paused. ROCK Pi was unreachable. The original record is retained unchanged as `supplied-b3-build-verification.md`.

Those observations support b3 on those exact configurations. They do not automatically qualify the new b4 recovery, queue, settings or interface behavior. No new browser or physical-appliance pass is claimed here.

## 2. Review method and scope

This is the continuation of the earlier full review, starting from the newly uploaded integration archive. The bundle retains the earlier report and findings rather than counting its resolved issues again. This pass compared archive contents and modes, inspected backend/authentication/configuration/restore paths, reviewed renderer/controller/scheduler/RPC behavior, examined the operator interface and installer, and researched seven relevant competitors using their own documentation.

Backend, renderer and frontend work was reviewed in parallel, then integrated and tested together. Independent follow-up checks examined the installer changes and the preview pool's cancellation, cache and authorization behavior. The final source retains the same database schema. Reports identify implementation evidence separately from mocked tests, live browser interaction, privileged installation and hardware observations.

Finding priorities reflect impact on the user and release readiness. They are engineering priorities, not vulnerability severity scores. The review includes automated dependency and source checks, but is not a penetration test, license opinion or performance benchmark of competitors. No competitor code was copied. Repository links below support advertised features; they do not establish performance, security or maintenance quality.

## 3. Implemented corrections and why they matter

### A. Saved configuration versus the actual wall

The old Layouts page disabled Apply whenever the database marked a layout active. That was insufficient: the current saved revision could be newer than the renderer's applied revision. The same confusion affected the editor, dashboard and phone remote. The new shared display-state model compares layout ID and revision, treats missing renderer status as unknown, identifies a stale page when the renderer reports a newer revision, and labels temporary camera focus separately. A matching wall retains Reapply because camera and rotation settings can change independently of layout history.

Saving and applying are now separate outcomes. If saving succeeds but renderer application fails, the editor preserves the saved revision and shows a persistent explanation. Retrying applies that revision without creating another history entry. If saving fails, dirty work remains and no activation is attempted. Camera and rotation pages now explain that saved changes require applying or reapplying the affected wall. This is practical guidance, not an invented global pending flag: the backend does not yet track a single applied generation across every camera, profile, rotation and layout.

Pixel overrides were another hidden source of disagreement. Imported fixed-pixel geometry could silently take precedence over normalized canvas edits on the physical display. The inspector now explains the override and offers conversion to canvas placement. Deliberate geometry, template and duplicate-placement operations clear stale overrides; nongeometry edits retain them, and Undo restores the previous complete slot. The canvas remains a schematic editor rather than a frame-accurate rendering of every backend effect.

Below 900 pixels, the existing responsive CSS moved the camera library and tile inspector offscreen with no way to open them. Cameras/Tile toggles and close controls now expose both drawers, maintain expanded state and keep hidden drawers out of keyboard navigation. New browser-test source covers the phone-sized interaction, but this environment could not execute rendered-browser verification. A concrete layout validation response now displays its errors instead of a generic HTTP failure, and delayed renderer refreshes cannot replace a different page after navigation.

**Evidence:** `frontend/src/display-state.ts`, `editor.ts`, `pages.ts`, `api.ts`, `styles.css`; `frontend/tests/display-state.test.mjs`, `editor.test.mjs`, `api.test.mjs`; `tests/e2e/test_control_workflows.py`; detailed appendix `b4-frontend.md`.

### B. Truthful capabilities and usable configuration recovery

Renderer status and backend listings now report thirteen feature-support flags and readable limitations. Availability and implementation support are different: a missing local GStreamer plugin does not change which features that backend implements, and a supported feature is not evidence of hardware qualification. The browser presents a capability matrix and gates unsupported native sizing, OMX labels and physical-output controls while preserving legacy saved metadata.

GStreamer reports labels, manual crop when source dimensions are known, opacity and z-order. OMXPlayer reports opacity and z-order; changing OMX opacity restarts that player. Current physical backends report no tile audio, native pixel sizing, physical portrait rotation, multi-output lifecycle, per-tile background/borders, connector selection, refresh-rate enforcement or profile-controlled blanking. These gaps are visible rather than presented as working controls. Existing display-profile dimensions remain useful; a complete profile-to-layout assignment workflow in the interface is still open.

Backup now accepts sanitized JSON through the existing configuration-import API, alongside existing ZIP/encrypted archives. Merge remains the default; destructive replacement is explicit and confirmed. Size/shape checks occur before expensive reads, binary archive bytes and passphrase whitespace are preserved, and renderer warnings stay visible after a successful configuration import. This closes the confusing export-without-reimport experience without changing backup scope.

Restored layout history also receives a data-integrity correction. A valid export may select revision 1 while retaining draft revision 2. Allocating `current_revision + 1` then collided with existing history. Edits and history restores now allocate one greater than the highest stored revision, preserving every previous revision. Real database tests round-trip this case and verify revision 3.

**Evidence:** `renderer/base.py`, `gstreamer.py`, `omxplayer.py`, `controller.py`; `frontend/src/display.ts`, `backup.ts`; `services/layouts.py`; `tests/unit/test_layout_service.py`; component appendices.

### C. Renderer and background-task resilience

Manual Previous/Next previously reused the automatic preconnection path even when the prepared standby was the next camera and the operator requested the previous camera. It could also arrive before a standby frame existed. With preconnection enabled, manual operations now prepare the exact requested source and wait for readiness before switching. A readiness-poll timeout releases the standby and preserves the current camera and cursor. The readiness poll is bounded to eight seconds after preparation returns; preparation itself can take additional time. This does not make whole-layout activation a first-frame transaction.

OMXPlayer's single monitor thread could terminate when a restart failed to spawn a process, removing recovery for every tile. Per-player failures are now isolated. Retry deadlines grow exponentially up to 60 seconds, playback confirmation resets backoff, and one failed tile does not stop checks of healthy players. The monitor's three-second poll affects actual timing. OMX Playing confirmation still does not prove that frames are advancing, so frozen-video detection remains a separate requirement.

Schedule and rotation database reads previously had failure paths outside their protection blocks. Temporary read errors now retry instead of silently ending those loops. Malformed persisted schedules are skipped so a later valid schedule can still apply. The daemon supervises its essential RPC and scheduler tasks: unexpected completion triggers cleanup and process failure so the service manager can detect the problem. Normal shutdown drains tasks. Actual systemd recovery was not exercised here.

Potentially long apply/focus/restore/restart/Previous/Next RPC mutations now have a 60-second response budget, while connection and status defaults remain ten seconds. This avoids some false UI timeouts without pretending to cancel a mutation transactionally when a client disconnects. Some backend calls can still block the event loop, and worker-thread cancellation cannot stop work already running. A future serialized operation queue needs identities, ownership, progress and measured deadlines.

Capability JSON writes now use complete temporary files and atomic replacement so readers do not see truncated reports. Schedule regressions also pin the appliance-local timezone contract across daylight-saving transitions. An equal start/end window is a local calendar day, which can span 23 or 25 elapsed hours. Schedules still have no per-schedule timezone, override duration or automatic end-of-window fallback.

**Evidence:** `renderer/controller.py`, `daemon.py`, `rpc.py`, `omxplayer.py`; `services/schedules.py`, `capabilities.py`; `tests/renderer/test_daemon_resilience.py`, backend/controller/RPC regressions, schedule/capability tests; `b4-renderer.md`.

### D. Settings, preview resource use and installation

Settings now validate known fields consistently, preserve file/renderer-selection/environment precedence, normalize legacy boolean strings and report invalid values without echoing their contents. Unknown keys warn and remain compatible with newer configuration files. Invalid primary configuration fails clearly; an invalid optional saved renderer override warns and falls back. Atomic settings writes use unique temporary files, synchronized replacement and permitted ownership/group preservation, avoiding concurrent-writer collisions and service-unreadable root writes. The real cross-group root case remains an explicit skipped test here.

The API now shares a bounded pool between preview capture and stream tests: one active job by default, eight queued distinct jobs and a two-second queue timeout. Identical in-flight work coalesces. Successful JPEGs have a two-second internal cache, bounded to 64 entries and 8 MiB; browser responses remain `no-store`. Saturation returns HTTP 503 with `Retry-After: 2`. Authentication, current camera/profile state and preview policy are checked before cache access. Keys use a process-private keyed digest incorporating the resolved source and configuration, so plaintext credentials are not cache keys.

Cancellation ownership matters: a disconnected HTTP caller cannot free a decoder slot while its thread still runs. Independent shielded producers hold capacity until completion; shutdown drains them. These are per-process limits for the standard one-worker deployment, not an appliance-wide governor over custom API workers, CLI commands or HDMI rendering. Identical waiting HTTP callers are not count-limited, and shutdown still depends on underlying media timeouts. Defaults should be measured on the real Pi before increasing concurrency.

Three installer defects are fixed. Editable `--dev` installs now repair `.pth`, executable and direct-URL metadata paths after the staged release is renamed. Local health probes use IPv6 loopback for an IPv6 wildcard and bracket explicit IPv6 addresses; they also bypass HTTP proxies. Bullseye's checksum-pinned pydantic-core selection follows the actual standard CPython 3.11-3.15 ABI instead of always choosing cp311. Unsupported implementations/free-threaded variants fail preflight before service interruption. The supplied cryptography wheel and import/AES-GCM preflight remain intact. Wheel filenames, URLs and SHA256 values were checked against official PyPI metadata; no ARM binaries were executed here.

A final source-analysis follow-up found that `rsync -a` could leave installed update/uninstall helpers owned by the original checkout user. Staging now explicitly assigns root ownership, removes group/other write and special permission bits, and ignores unsafe external links. The installer validates protected prefix ancestors, locks the dedicated prefix, and rejects a symlink or non-directory releases entry before creating/changing that container. Real filesystem tests exercise unsafe ancestors/entries; actual owner transfer remains a named root/rsync skip. Initial source/interpreter trust and privileged appliance acceptance remain required.

**Evidence:** `config.py`, `services/stream_work.py`, `api/routes_cameras.py`, `api/app.py`; `installer/install-local.sh`, `installer/lib.sh`, `installer/bullseye-wheels.json`; `scripts/relocate_venv.py`, `bullseye_wheel_plan.py`; configuration/pool/API tests and 21 installer-release regressions.

## 4. Competitors and the gaps worth filling

The relevant comparison is broader than Raspberry Pi scripts, but Mosaivue should retain a clear camera-wall purpose. The following are documented feature comparisons, checked November 13, 2026. No head-to-head latency, reliability, security or capacity test was performed.

| Competitor | Documented strength | Implication for Mosaivue |
|---|---|---|
| displaycameras [S1] | Offscreen OMX feeds, window rotation, screen-sized stepping and configurable blanking. | Preserve migration quality and fixed-tile continuity. Complete synchronized groups and real group-level failure behavior before claiming full behavioral parity. |
| Rpisurv [S2] | Automatic layout/reflow, watchdog recovery, screen cycling per display and image streams. | Whole-wall playlists, deliberate offline reflow and image tiles are meaningful additions after core recovery is qualified. |
| OpenSurv [S3] | Dual monitors, independently cycled screens, vertical rotation and image content. | Multi-output and physical portrait support are clear competitive gaps requiring output ownership and per-output lifecycle design. |
| OpenSurvPro [S4] | Advertises a web dashboard, remote management, drag/drop configuration editor, dual monitors and portrait screens. | A web editor alone is not a unique advantage. Differentiate through safe revisions, understandable recovery, configuration integrity and measured operation. Its performance claims were not independently verified. |
| Frigate/go2rtc [S5, S6] | Browser MSE/WebRTC viewing, camera setup integration and RTSP relay to reduce upstream connections. | Add optional local restream/browser viewing with connection budgeting. Treat NVR recording/detection as a separate product scope rather than silently expanding this appliance. |
| tinyCam Monitor [S7] | Its compatibility documentation includes ONVIF Profile S, PTZ and presets. The support page is dated July 2023. | Known-endpoint Media1 onboarding is useful but incomplete. Add vendor-tested discovery, Media2 and PTZ/preset controls separately. Do not infer current model counts from that older page. |
| UniFi Protect Viewport [S8] | Dedicated PoE appliance with a UniFi Protect application requirement. | Installation and recovery simplicity are useful benchmarks. Mosaivue's generic RTSP configuration can remain valuable across mixed sources; ecosystem/stream compatibility must still be tested. |

The inference from this comparison is to prioritize dependable daily operation before collecting more visible toggles. This pass closes state clarity, recovery, import usability and resource-budget gaps. It does not implement multi-monitor, portrait, PTZ, browser live video, recording or a fleet controller. Those additions need explicit architectural work and validation; capability flags are not substitutes for their implementation.

## 5. Remaining work, in priority order

**P1 - Qualify the changed candidate.** Execute all eight browser workflows in an isolated seeded environment; inspect desktop and phone layouts, keyboard/focus behavior and console errors. On appliances, repeat clean install, failed-update rollback, upgrade/reboot and source/output acceptance. Exercise manual Previous with a prepared Next source, dead cameras, spawn failure, transient database errors, schedule changes, long RPC operations and simultaneous previews. Observe actual HDMI and advancing frames, then a 24-hour initial and 72-hour extended soak. Pi 4/5, Ubuntu physical output and the unavailable ROCK Pi remain specific gaps, not assumed successes.

**P1 - Protect the entire stream secret.** Password fields are encrypted, but usernames remain available to authenticated administrators and opaque vendor bearer tokens can remain inside stored/exported URLs. Design complete-URI encryption or explicit secret-bearing components, migration, redacted API/export representations and backward-compatible encrypted backup semantics. OMXPlayer and FFmpeg preview command-line exposure remain a separate local process boundary. Documentation was corrected now; the storage migration is still required.

**P1 - Make application and recovery authoritative.** Introduce a controller-owned configuration generation or fingerprint spanning camera/profile/group/layout settings. Compare desired and applied generations across schedules, focus, restarts and concurrent operators. Add optimistic edit conflicts so a second editor cannot silently overwrite the first. Define decoded-frame acceptance, a bounded failure policy and operation ownership for full-wall changes. Current synchronous rollback and manual standby readiness are useful but incomplete parts of that contract.

**P1 - Extend recovery beyond configuration export.** Current archives exclude appliance settings, saved renderer selection, custom trust files, users/sessions, systemd changes and OS packages. Add a versioned recovery manifest with an inspectable restore plan, compatibility checks and deliberate handling of machine-specific paths and secrets. Verify that database and master key belong together. Keep the current configuration format stable and exercise a restore rehearsal before describing it as complete appliance backup.

**P2 - Finish display and rotation features.** Implement per-output active layout/state and connector ownership before dual-monitor support; then physical portrait, mode/blanking enforcement and a UI profile-assignment workflow. Define synchronized group cuts, whole-wall playlists, real group-level placeholders and optional image tiles. Unsupported metadata currently remains stored for compatibility. Audio, native pixel sizing, borders and OMX label/crop support need separate feasibility and acceptance decisions.

**P2 - Expand camera and browser workflows deliberately.** Build WS-Discovery with explicit network scope, Media2 and PTZ/presets against a vendor compatibility matrix. Add optional MSE/WebRTC viewing through a locally controlled restreamer; measure camera connection counts, source selection, codec/browser compatibility, authentication, idle cleanup and resource limits. Keep manual RTSP entry available when vendor discovery fails.

**P2 - Support shared operations.** Add viewer/operator/admin permissions, account management, revocable scoped integration tokens and a bounded secret-free audit trail. A database admin flag and unused audit model are not finished user workflows. Health history should retain last-frame age, outage/recovery reasons and useful resource measurements; process-running status alone is insufficient. Fleet management should follow a stable single-appliance model, with each wall continuing through controller loss.

**P2 - Finish accessibility and session resilience.** Mobile drawers are accessible again, but the custom canvas still needs keyboard selection/announcements, focus preservation through inspector renders and screen-reader/touch testing. Session-expiry recovery should preserve unsaved editor work during reauthentication. Broader localization, theme and presentation refinements follow those interaction guarantees.

## 6. Validation, artifacts and release boundaries

| Check | Result and scope |
|---|---|
| Uploaded b3 baseline in this environment | 246 passed, one Unix-socket skip; 59.50% combined coverage. |
| Final b4 Python suite, browser tests excluded | 358 passed, three skips, one upstream TestClient warning; 62.44% combined coverage. Statement coverage 65.02%; branch coverage 52.54%. |
| Frontend | Strict TypeScript/build passed; 35 JavaScript tests passed; 36 compiled files synchronized and checked. |
| Browser test source | Eight scenarios retained/expanded; not executed as browser interactions here. Unix-socket creation is prohibited. |
| Source/style and installers | Ruff and byte compilation passed; 13 shell syntax checks, both nonprivileged helper suites and 21 installer-release regressions passed. |
| Dependency audit | 37 installed runtime Python packages checked; no known advisories returned at the audit time. OS/media packages and other versions are outside that result. |
| Bandit | Zero high/medium results and 46 low-severity patterns retained with triage, including the separately corrected installed-helper ownership boundary. This is not a zero-finding security certification. |
| Build products | Source archive, universal Python wheel and amd64 Debian package are included, with checksums and structural verification evidence. A built package is not a privileged installation pass. |

The three Python skips are real AF_UNIX socket creation, a different-group settings ownership case, and actual root/rsync installed-source ownership transfer. The single warning is the existing Starlette/httpx TestClient deprecation. The runtime dependency inventory records the versions actually installed for this review; it is not a complete reproducible lock for every supported architecture or the multimedia operating-system stack.

The archive includes full source with prebuilt static assets, the current report in PDF/Markdown, component reviews, a prioritized finding register, acceptance and upgrade guidance, original supplied b3 evidence, tests/audit/build records, a current-input-to-b4 patch and a SHA256 manifest. Temporary environments, node_modules, databases, keys and appliance credentials are excluded. Existing screenshots are historical assets; they were not regenerated or presented as b4 browser evidence.

Use the local candidate source installer rather than the online bootstrap, which follows published releases. Back up the matching database/key/settings and service overrides, validate the candidate configuration, install during a controlled interruption window, then verify application health and the actual wall. There is no schema migration, but the stricter settings contract can reveal previously accepted invalid values. The upgrade guide and acceptance checklist specify the required checks. The candidate has not been pushed, published or installed onto your systems by this review.

## 7. Sources and detailed evidence

All external pages below were checked November 13, 2026. Feature descriptions are attributed to their maintainers. Recommendations and priorities are review judgments based on those features and the supplied code.

- **[S1] displaycameras:** https://github.com/Anonymousdog/displaycameras
- **[S2] Rpisurv:** https://github.com/SvenVD/rpisurv
- **[S3] OpenSurv:** https://github.com/OpenSurv/OpenSurv
- **[S4] OpenSurvPro:** https://github.com/BigTonyTones/OpenSurvPro
- **[S5] Frigate live viewing:** https://docs.frigate.video/configuration/live/
- **[S6] Frigate go2rtc:** https://docs.frigate.video/configuration/go2rtc/
- **[S7] tinyCam compatibility:** https://www.tinycammonitor.com/support.html
- **[S8] UniFi Protect Viewport:** https://techspecs.ui.com/unifi/physical-security/ufp-viewport
- **[S9] PyPI pydantic-core 2.50.4 metadata:** https://pypi.org/pypi/pydantic_core/2.50.4/json
- **[S10] PyPI cryptography 50.0.2 metadata:** https://pypi.org/pypi/cryptography/50.0.2/json

Local evidence: `b4-backend.md`, `b4-frontend.md`, `b4-renderer.md`, `b4-acceptance-checklist.md`, `current-validation.md`, `current-upgrade.md`, `current-findings.csv` and `supplied-b3-build-verification.md`. Earlier `report.md`, `findings.csv` and component appendices describe the prior review and remain available for the complete review history. Input SHA256: `788067a99fa8199fc3032e648b27a7d5204bb949540394ad74fdca4d8de22d1b`.
