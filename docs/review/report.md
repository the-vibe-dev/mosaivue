# Mosaivue: full product review and implementation report

**Report date:** November 13, 2026 (UTC)
**Reviewed input:** mosaivue-main (1).zip, package version 0.1.0b2
**Delivered candidate:** 0.1.0b3, source plus built distribution artifacts
**Decision:** suitable for controlled appliance qualification; release approval remains conditional on browser and hardware acceptance.

## 1. Executive assessment

Mosaivue already has a coherent purpose: turn inexpensive Raspberry Pi and Linux hardware into a manageable camera wall. Its strongest combination is reusable camera profiles, a visual layout editor, independent rotating tiles, phone control, local operation and an existing migration path from displaycameras. Those foundations are worth continuing.

The most serious problems in the supplied archive were correctness failures in ordinary workflows. Restoring a sanitized backup could delete working credentials. Saving camera edits could replace stream-profile IDs used by layouts. Shared rotation groups could interfere with one another, and rotating tiles could stop using their low-resolution substreams. Overnight schedules used the wrong weekday after midnight. Several controls accepted configuration the renderer did not implement. Those defects matter more to an appliance user than the length of its feature list.

This deliverable implements corrections across data integrity, rendering control, scheduling, authentication, installation and the browser interface. It also adds known-endpoint ONVIF Media1 onboarding, a schedules screen, uniform grid templates, camera/layout duplication and filtering, and configurable compositor frame rate. These additions address concrete setup and display-management gaps.

The revised tree is a review candidate, not a newly published stable release. Automated source and API verification is substantially stronger, but this session did not reproduce the archive's historical camera/HDMI site results on the new code. Browser execution was blocked before interaction assertions by the workspace's Unix-socket restriction. Both limitations are carried into the release decision instead of being counted as passing tests.

### What was actually reviewed

The review covered the provided archive rather than an assumed newer GitHub branch. It included the API and authentication paths, SQLite models and transaction boundaries, camera/profile storage, configuration backup/restore, layout and rotation control, scheduler, GStreamer and OMXPlayer adapters, renderer RPC, stream probing, diagnostics, TypeScript control interface, installers, release scripts and CI configuration.

The original archive contained 203 regular files. Its SHA-256 is:

cd43fe83ee8ae02f33877774d7dcc86f7be1af8aab123d39c9fac8804eb865d1

Competitor research used official repositories and vendor documentation available during the review. Their feature statements are documented claims, not independently measured comparative performance. The original software license and project identity are retained. No production appliance, camera account, GitHub repository or public release was changed.

## 2. Verification summary

| Check | Supplied archive | Updated candidate |
|---|---:|---:|
| Python tests, excluding browser suite | 74 passed | 245 passed, 1 environment skip |
| JavaScript tests | 3 tests in supplied suite | 20 passed |
| Python line-and-branch combined coverage | 47.58% | 59.39% |
| Python statement coverage | 51.33% | 61.98% |
| Python branch coverage | 31.66% | 49.26% |
| Strict TypeScript check and frontend build | Existing workflow inspected | Passed; built assets synchronized |
| Ruff across source, tests and scripts | 42 reported issues during review | Passed; added to CI |
| OpenAPI snapshot | Existing snapshot | Regenerated: 53 paths, version 0.1.0b3 |
| Shell syntax and installer helper regressions | Limited helper coverage | Passed |
| Bandit medium/high gate | Existing CI workflow | Passed with a documented ONVIF protocol exception |
| Runtime dependency audit | Existing CI workflow | No known vulnerabilities reported in 37 resolved dependencies checked |
| Real Unix-socket RPC integration | Not established | One test skipped: socket creation prohibited |
| Rendered Chromium workflows | Not established | Blocked before UI assertions |
| Real cameras, GStreamer/OMX and HDMI | Historical repository evidence only | Not executed in this session |

The 245 Python passes include real SQLite transactions, encrypted-backup round trips, concurrent initial setup, concurrent master-key publication, graph-reference validation and separate-connection event ordering. Controlled protocol fixtures verify ONVIF SOAP/authentication/error handling. Renderer tests verify controller contracts and backend command decisions.

Those tests do not establish decoder compatibility, actual video latency, physical display behavior or sustained appliance capacity. The aggregate coverage is useful but still leaves significant untested runtime surface. In this run, the CLI and TUI were not covered by pytest, and the GStreamer implementation had approximately 40% combined coverage, substantially through controlled objects. A claim of comprehensive hardware verification would be inaccurate.

The browser attempts are recorded separately. The connected and cloud browsers could not reach the isolated local server. Running the repository's browser suite beside the server then failed during Chromium startup because its process-singleton Unix socket was prohibited. The observed result was one failed test and four fixture errors before application interaction. These are environment blockers, not passing UI checks and not evidence that the UI itself fails.

## 3. Architecture and engineering judgment

The architecture separates the web control plane from the display process. FastAPI serves the static TypeScript interface and stores configuration through SQLAlchemy/SQLite. A local Unix-socket protocol sends display commands to a renderer controller, which drives either GStreamer or OMXPlayer. This is a useful appliance boundary: a display failure can be restarted independently while administration remains available.

The key engineering weakness was consistency across these boundaries. Several paths correctly stored an object but failed to preserve its identity, apply it to the current display, publish it after commit, or report its actual effect. A configuration field existing in a database or form was sometimes treated as proof of a supported capability. The changes emphasize identity preservation, explicit state transitions, rollback boundaries and truthful feedback.

Continue with this architecture. A wholesale framework rewrite would add risk without resolving the important appliance gaps. Expand the test seams around the existing controller, reduce oversized frontend page functions gradually, and introduce new display capabilities behind explicit backend contracts.

## 4. Data integrity and recovery corrections

### 4.1 Sanitized merge no longer erases stored passwords

The original importer deleted an existing camera's credential before deciding whether the incoming export contained a password. A normal sanitized export intentionally omits secrets, so merging it back could disable a working camera.

The importer now distinguishes sanitized merge from credential-inclusive restoration. A sanitized merge preserves the local credential. A credential-inclusive backup supplies a replacement secret, which is encrypted through the existing AES-GCM store. A sanitized replacement cannot recover a secret that is not in the backup; cameras requiring credentials still need those re-entered.

Evidence: services/backup.py, services/backup_validation.py and tests/unit/test_configuration_integrity.py. The regressions verify the recovered password by real decryption, not merely by checking that a credential row exists.

### 4.2 Stream-profile identity survives edits and restoration

A routine camera edit originally cleared all profiles and recreated them. The browser also omitted profile IDs and metadata from its edit payload. Layouts and rotation entries that selected a specific profile could therefore point to a deleted ID after an otherwise harmless change.

The service now updates profiles in place, matches older clients by profile name when IDs are omitted, supports safe name swaps, and rejects unknown or foreign profile identities. The browser preserves IDs, priorities, codec, FPS and bitrate information. Explicit profile selection is remapped throughout restored layouts and rotation entries. Removing an object used by a current configuration produces an actionable conflict.

Evidence: services/cameras.py, services/layouts.py, frontend/src/forms.ts, and the configuration-integrity and camera/layout service suites. Historical revisions are retained, but a historical revision that references deleted resources must pass current validation before it can be activated.

### 4.3 Restore validates the complete configuration before mutation

The supplied validator checked the top-level format and a few list types. It did not establish that nested geometry, profile ownership, schedule targets, display references or current revisions formed a usable configuration.

The new validation pass checks the complete exported graph against the API schemas and explicit cross-reference rules. It validates section structure and uniqueness, supported layout schema version, pixel overrides, current revisions and active-layout constraints. The import executes inside an explicit transaction/savepoint so a late failure restores the earlier database state without committing the caller's transaction.

Revision rows are flushed in the correct order before replacement. The export's selected current revision is retained instead of automatically selecting the highest draft revision. Merge preserves the existing active wall and normalizes the active selection; replacement follows the export's active selection. Real-database tests cover invalid replacement, late reference conflict, rollback and revision collisions.

### 4.4 Configuration success is separated from display success

API import/restore commits before asking the renderer to apply the active wall. Its response now distinguishes saved configuration from renderer application. If the renderer cannot apply the result, or there is no active layout to show, the UI presents a persistent warning and an action to open renderer controls.

CLI import/restore remains a configuration operation and now prints an explicit instruction to apply a layout or restart the renderer. This is a deliberate visible boundary. A future revision/reload contract should apply ordinary camera changes predictably without unexpectedly canceling a user's focused view.

### 4.5 Backups are bounded and their scope is explicit

Backup uploads are bounded to 100 MiB plus one byte for overflow detection. Expanded configuration is limited to 32 MiB, with archive-entry/member checks. Wrong-passphrase and damaged-archive cases receive useful errors. Expected validation messages exclude input values; unexpected SQL/library exceptions use a generic response rather than exposing credential-bearing parameters.

These are configuration backups, including camera credentials when selected. They are not full appliance recovery images. They do not include web users/sessions, all files under /etc, renderer override files, custom certificate authorities, OS packages or administrator systemd overrides. Documentation now states that scope clearly. An encrypted configuration backup plus a protected copy of appliance settings remains necessary for a complete operational recovery plan.

## 5. Renderer and scheduling corrections

### 5.1 Independent tiles keep independent rotation state

Rotation position was stored by group even though the controller ran a loop per slot. Two tiles using one group could advance each other's position. Cursors now belong to individual slots.

Automatic stream selection is also repeated on every rotation and preconnection. Previously a tile could start on a small substream and later switch to a camera's main profile, changing decode load during ordinary operation. Explicit profile ownership is validated, disabled/missing cameras are skipped, and a disabled group stops advancing.

Skip and Hold now have distinct failure behavior: both preserve the currently visible stream if the next switch fails; Skip advances toward another entry on the next attempt, while Hold retries the failed entry. True synchronized rotation and rendered failure placeholders remain unimplemented. The UI no longer offers an unsupported placeholder mode as a normal new selection.

Evidence: renderer/controller.py, services/rotations.py, tests/renderer/test_controller_regressions.py and tests/unit/test_rotation_service.py.

### 5.2 Synchronous layout failure restores the previous wall

The original apply path mutated streams incrementally. An error after removing an old stream or adding only part of a new layout could leave a damaged wall while the configuration still appeared active.

The controller now resolves requested sources before mutation, retains prior stream specifications and output dimensions, and restores them after synchronous backend rejection. Existing focus/rotation state is retained until the operation succeeds.

This is a specific rollback guarantee. A pipeline can still accept configuration and fail asynchronously before its first decoded frame. That case relies on recovery logic; the patch does not certify every new wall as visually ready before activation. A stronger readiness transaction is a remaining architectural task.

### 5.3 Focus and runtime geometry behave consistently

An invalid focus request no longer cancels an existing rotation before checking the camera. First-use focus starts playback. Source replacements consider transport, latency and source dimensions rather than only an ID and URL.

Normalized geometry and pixel overrides are clipped to the actual output. A tile near the bottom/right edge retains at least one pixel, and an override saved for a larger output cannot overflow a smaller display. Schema validation rejects malformed override structures and incompatible explicit bounds before rendering.

### 5.4 Overnight schedules use the starting day

A Monday 22:00-06:00 schedule now covers Monday evening and Tuesday morning. The end boundary is exclusive, avoiding overlap at a shared transition minute. Equal start/end times represent a full 24-hour window. Priority ties resolve deterministically.

The scheduler compares the desired wall with the controller's actual active layout, rather than an obsolete cached selection, so manual changes do not permanently confuse scheduling. The new browser screen exposes create, edit, enable/disable and delete operations.

Schedules still use the appliance's local timezone. A matching schedule can override a manual layout selection on the next 30-second scheduler tick; focus pauses that scheduling behavior. There is no complete timezone-management/DST product contract or automatic fallback wall after all windows finish. The screen and documentation explain that the last wall remains visible unless another schedule or operator changes it.

Evidence: services/schedules.py, renderer/daemon.py and tests/unit/test_schedules.py.

### 5.5 Backend controls and failure attribution were corrected

GStreamer error routing previously matched slot IDs as substrings in element names. Similar IDs could attribute one camera's failure to another. It now follows actual element ownership/ancestry, including prepared branches.

OMXPlayer now honors TCP/UDP/auto transport selection, initial opacity/layer, dynamic position and layer commands, and appropriate restart fallbacks. These are tested command/control contracts; actual OMX firmware and D-Bus behavior still require physical qualification.

Renderer RPC framing supports messages up to 1 MiB and reports malformed responses, timeouts and unavailable services consistently. Rotation/focus tasks are canceled and joined during shutdown. The real Unix-socket integration test is included, with the environment skip explicitly recorded.

### 5.6 Compositor FPS is configurable without changing the default

The old GStreamer output caps hard-coded five frames per second. MOSAIVUE_OUTPUT_FPS now accepts an integer from 1 through 60. Unset retains 5, preserving the existing low-resource behavior.

This controls compositor output FPS, not camera capture FPS, source bitrate or monitor refresh. A requested value of 30 is not proof that a Pi or GPU can sustain it. Higher values need measured CPU, memory, temperature, dropped-frame and fixed-tile-continuity results before being recommended per platform.

## 6. Security, API and installation corrections

### 6.1 Authentication and key publication

Changing an administrator password revokes other sessions while retaining the current session. Initial setup uses a SQLite immediate transaction so concurrent requests cannot both create the first administrator. Concurrent key initialization now publishes one complete key atomically, avoiding competing services encrypting data with different keys. Malformed token input is rejected without unexpected encoding exceptions.

Server-Sent Events no longer keep an authentication database session open for an entire connection. A fresh, short session check runs before each event or heartbeat. Revoked, expired or disabled accounts stop receiving events. Mutation events are published after commit so a refresh from another database connection sees the changed object.

The web and renderer services still share one operating-system account; separate processes and renderer device policy are not a strong identity-isolation boundary. These improvements do not create a full multi-user access-control system. The existing administrator flag and AuditLog model do not constitute a complete system for operator/viewer roles, account management, scoped integration credentials and an audit-log workflow. The ONVIF endpoints enforce administrator access; that does not supply the missing role-management surface.

### 6.2 Probe and preview results are truthful

The preview-disable setting is enforced before capture begins. Saved transport preferences propagate to discovery and thumbnail capture. Discovery must succeed and find usable video before the API reports success.

Discovery duration is retained as response_time_ms. It is no longer called time-to-first-frame; that field is null with an explanation when decoded first-frame latency was not measured. This prevents optimistic but unsupported performance data from entering diagnostics or the interface.

IPv6 RTSP authorities preserve brackets and ports through credential extraction/reinjection. URL validation rejects malformed hosts, ports and control characters. Diagnostic redaction covers embedded userinfo and named sensitive query parameters. Opaque vendor bearer tokens in URL paths remain a known confidentiality gap: encrypting only the password field does not encrypt the entire URI.

### 6.3 Installer metadata is protected from the service account

The original /etc/mosaivue directory allowed group writes even though it contained metadata later consumed by root-level update/removal scripts. The candidate makes the directory root-owned with mode 0750. The one-time setup token alone is group-writable so the service can consume it by clearing its existing inode.

The updater and uninstaller validate metadata ownership and write permissions. The installer checks configuration-directory entries for symlinks and hard links before privileged writes, repeats the checks after locking the directory, and atomically replaces root-consumed installation/executable metadata.

An older installation with unsafe metadata must be upgraded using the new source installer to repair that state. The new updater deliberately reports the condition instead of trusting a service-writable executable path. These are installation-boundary corrections, not a claim that an already compromised appliance can be made trustworthy by running an update.

### 6.4 Installation/removal prefixes are constrained

Prefixes must be dedicated application paths in supported locations and may not contain whitespace or shell/systemd substitution characters. A nonempty target must already identify a Mosaivue installation; unrelated shared directories are rejected. Removal verifies the installation marker before deleting application files and removes only installer-owned systemd drop-ins.

Helper tests exercise invalid/root/shared paths, writable metadata and linked configuration entries. Shell syntax checks pass. The full root/systemd installation, rollback and uninstall sequence was not executed here; it still belongs in disposable-host acceptance.

### 6.5 Release tooling is more verifiable

Source staging now works without rsync on a development host and rejects credential/database runtime artifacts, including force-tracked sensitive files. Development/build output is excluded while compiled frontend assets remain included. The Git workflow stages the tracked file set, so new implementation files must be committed before producing a release from a Git checkout. The delivered archive path includes the new modules.

Ruff now runs in CI. Its exceptions are limited to intentional environment-before-import test setup and supported FastAPI/Typer metadata factories. Python/frontend versions and the OpenAPI snapshot match the 0.1.0b3 candidate. The existing license and third-party notice files are retained, and the runtime dependency/license inventory is regenerated. The medium/high Bandit gate passes. Its SHA-1 exception is limited to the protocol-required ONVIF UsernameToken operation; inbound XML uses defusedxml with DTDs, entities and external references forbidden. pip-audit reported no known vulnerabilities in the 37 resolved runtime dependencies checked. These are scoped automated checks, not a security certification. Debian packaging now maps the Python prerelease to 0.1.0~b3 so it sorts before a future stable 0.1.0; the Python/source version remains 0.1.0b3. Focused tests check the mapping and actual dpkg ordering.

## 7. Usability and competitive additions

### ONVIF Media1 import from a known endpoint

The Cameras screen provides a two-step Import ONVIF workflow. Enter the camera's HTTP(S) device-service URL and credentials, inspect supported video profiles, select profiles, and import them as a normal camera. The service uses GetCapabilities, GetProfiles and GetStreamUri with WS-Security UsernameToken and supported HTTP authentication. Metadata includes codec, dimensions, FPS and bitrate.

Inspection does not return stream URIs or passwords. Import resolves URIs server-side, honors a consistently advertised streaming credential when it differs from the ONVIF management account, and stores credentials through the existing encrypted store. Duplicate profile names are made unique. Response sizes, profile counts, timeouts, XML declarations, redirects and malformed authentication are bounded or rejected with safe errors. The protocol follows the ONVIF Media1 and device WSDLs. [C8]

This is not multicast discovery, PTZ control, full ONVIF conformance or Media2 support. Advertised service/stream hosts must match the supplied host, with literal IPv6 normalization; a hostname-to-IP alias can require using the advertised address or manual RTSP setup. HTTPS service downgrade and credential forwarding to another host are rejected. Real-camera interoperability remains unqualified.

### Schedules and more practical wall creation

The schedule screen removes the need for API calls to manage timed walls. Uniform 2x2, 3x3 and 4x4 grids complement the existing featured-camera layouts. Camera and layout duplication, richer search/status filters, result counts and no-results feedback reduce repeated setup work.

The editor now exposes actual manual stream choices, clears stale profile references when a camera changes, preserves locked tiles across mutation paths, and prevents zero/NaN geometry. Dirty state is visible, with navigation/reload/discard guards and appropriate save-state behavior. Rotation editing preserves order, weights, profiles and start position, and Resume accompanies Pause.

Shared dialogs can cancel even when required inputs are invalid. API validation errors identify fields rather than showing object strings. Slow route responses no longer replace a newer screen, and obsolete preview results do not retain blob URLs. Sanitized JSON exports now become downloadable JSON Blobs; encrypted backup bytes are preserved. The final review caught and corrected the mismatch between parsed API JSON and the browser download helper.

These changes have strict TypeScript and focused JavaScript regression coverage. Rendered desktop/mobile interaction remains a release condition because Chromium could not launch in this workspace.

## 8. Competitor findings and remaining differentiation

| Product | Relevant documented capability | Practical implication |
|---|---|---|
| displaycameras [C1] | OMX grids, monitored playback and feed rotation; legacy-platform warnings | Preserve a reliable migration path and make editing/recovery easier. |
| Rpisurv [C2] | Watchdogs, screen cycling, refreshed images and dual HDMI | Whole-wall playlists, images and actual multi-output operation remain gaps. |
| OpenSurv [C3] | Dual monitors, independent cycling, portrait screens and automatic reflow | A direct benchmark for the next display features, not just more database fields. |
| OpenSurvPro [C4] | Project claims a dashboard, GUI editor and remote controls | A browser editor alone is no longer sufficient differentiation; verify reliability and onboarding. |
| tinyCam Monitor [C5] | Android viewer with ONVIF, PTZ/presets and broad protocols | Extend onboarding and camera control after qualifying the new importer. |
| UniFi Protect Viewport [C6] | Dedicated Protect-to-HDMI appliance with PoE | Compete on appliance convenience and predictability while keeping generic streams/hardware choice. |
| Frigate [C7] | Browser live viewing using jsmpeg/MSE/WebRTC and go2rtc | Optional local browser viewing is a sensible integration; full NVR duplication is a separate scope. |

The strongest immediate positioning is an approachable local HDMI camera wall for reused hardware and mixed RTSP/RTSPS sources. The candidate reduces important setup, schedule and reliability gaps, but it does not reach complete feature parity with all products above.

Direct display gaps include real multi-monitor routing, portrait output, whole-layout playlists, refreshed image tiles and optional camera-failure reflow. Camera-control gaps include network discovery, Media2, PTZ/presets and event-triggered focus. Management gaps include health history, metrics/alerts, scoped integration access and multi-appliance control. Those are specific implementation projects with their own test and resource costs.

Frigate-style recording, detection, event search and storage management should remain integrations or a later product decision. Adding them now would substantially enlarge the system and compete with the user's existing NVR. That is an engineering recommendation based on Mosaivue's present purpose, not a claim that those features lack value.

## 9. Prioritized implementation roadmap

### P0: qualify this candidate and make capability claims exact

1. Run the included browser workflows on a host that can launch Chromium. Exercise desktop and 390x844 mobile navigation, invalid-form cancellation, camera edits, dirty-layout handling, schedules, rotation controls and ONVIF inspection/import. Capture console errors and screenshots.
2. Run appliance acceptance on the existing Pi 3B+/OMX, ROCK Pi/GStreamer and Ubuntu systems. Test cold boot, network loss, stopped/stalled cameras, two rotating slots, manual profile changes, repeated layout activation, focus/restore and long-duration operation. Add Pi 4/5 measurements before support/capacity claims.
3. Test clean source installation, upgrade from 0.1.0b2, failure rollback, sanitized and encrypted restores, and conservative removal on disposable systemd hosts. Check ownership and the consumed-token behavior.
4. Finish capability-aware UI/API reporting. Display fields for portrait/output targeting, synchronized rotation, placeholders, audio and backend-specific presentation must either have a demonstrated effect or be clearly unavailable.
5. Add decoded first-frame readiness to activation. Synchronous rollback is useful, but it is not sufficient for a visually proven last-known-good wall.
6. Add a visible pending-change/apply contract for edited cameras and rotation timing. Avoid silently canceling focus to reload every database change.

### P1: close the strongest direct display gaps

Implement physical outputs separately from layouts, beginning with one verified GStreamer platform. Bind each output to a real connector, support orientation, persist reconnect behavior, then add per-output playlists with dwell time, pause/next/previous and schedule selection. Acceptance requires two different visible walls and an actual portrait result.

Expand ONVIF onboarding in bounded steps: explicit WS-Discovery, Media2, then PTZ presets. Keep manual URLs available and collect a reproducible compatibility matrix across camera vendors/authentication variants. Add image tiles with cached refresh and optional failure reflow only after the multi-output lifecycle is stable.

Introduce a preview queue/cache and resource budgets so multiple browser previews cannot starve a low-power HDMI wall. Add typed application settings with backwards-compatible validation, and versioned backup sections for appliance settings with a restore preview. Encrypt full stream URIs, or explicitly model sensitive path components, before promising protection for opaque vendor bearer tokens. Keep the regenerated dependency/license inventory and existing Bandit/pip-audit CI current, and add a reproducible release dependency lock. The resolved runtime snapshot passed the advisory lookup in this review, but that does not cover operating-system video components, future resolutions, unknown vulnerabilities or every target platform.

### P2: improve observability and shared deployments

Add bounded health history, last-frame timestamps, outage duration, recovery reasons and metrics export. Separate actual decoded-frame health from a merely running OMX process. Use the existing audit model to record actor/resource/action without secrets and with bounded retention.

Add account management, viewer/operator/admin roles and scoped revocable automation tokens. Home Assistant/MQTT/event-triggered focus should use those capabilities rather than a shared administrator browser session. Add optional local MSE/WebRTC viewing through a restreamer, ensuring it does not unnecessarily duplicate upstream camera connections.

Central fleet configuration and health should follow reliable single-appliance behavior. Local walls must remain usable when the fleet controller or network is unavailable.

## 10. Hardware and release acceptance

A useful acceptance record should identify the exact board, OS image, kernel, firmware, GStreamer/OMX version, sink/connector, codecs, source dimensions/FPS/bitrate, chosen profiles and compositor rate. Preserve the distinction between successful API commands, running processes and advancing decoded frames.

Suggested scenarios:

- Cold boot into a saved wall; API remains reachable while decoder discovery completes.
- Repeated 4/6/9-source scenarios only where the device can support the chosen source mix; no universal stream-count claim.
- Two independent rotation slots sharing a group, with disabled/offline cameras and both Skip/Hold behavior.
- Changed stream transport and profile metadata followed by explicit reapplication.
- Mixed aspect ratios, very small tiles, old pixel overrides and output-size changes.
- Network loss/recovery, stopped streams, stalled frame delivery and a renderer restart.
- Focus without an active layout, invalid focus, timed restore and schedules crossing midnight.
- Sanitized merge retaining working credentials; encrypted replacement retaining selected profiles.
- Update failure recovery with matching database/key/settings snapshot; uninstall preserving configuration by default.
- At least a 24-hour initial soak and a longer 72-hour candidate soak, with recorded resource trends and interruption counts.

The durations are recommended acceptance targets, not completed results. Existing hardware evidence in the repository is historical evidence for the earlier build. It does not automatically qualify modified code.

## 11. Build, upgrade and handoff

The ZIP includes the complete modified source, prebuilt frontend assets, tests, report, issue register, patch, validation evidence, and distribution artifacts. Node is required only to rebuild the frontend, not to serve the included assets. Python and the appropriate system video dependencies are still required on an appliance. The bundle is not an offline mirror of operating-system/Python dependencies.

Use the source installer for Pi/ROCK Pi or a normal source installation. The Debian artifact is built for amd64 and is not a Pi package. The wheel is a Python package; it does not supply GStreamer, OMXPlayer, hardware drivers or service provisioning by itself.

Before upgrading an existing wall, retain an encrypted configuration backup and protected copies of current appliance settings. Use the new local source installer, especially when repairing the older configuration-directory permissions. After upgrade, check service startup, run diagnostics, apply a known layout and perform the acceptance scenarios. No database schema migration was introduced by this review.

The online bootstrap continues to download the newest published release, which may still be older than 0.1.0b3. Installing this candidate from its local source is distinct from publishing a release. See upgrade.md and validation.md for exact commands and limitations.

## 12. Sources and evidence map

Code evidence is included in the source tree and the focused review appendices: backend.md, renderer.md and frontend.md. Regression tests are the primary evidence for implemented behavior. findings.csv records fixed work, additions and remaining items. Validation logs and the generated OpenAPI snapshot accompany the package.

- [C1] displaycameras official repository: https://github.com/Anonymousdog/displaycameras
- [C2] Rpisurv official repository: https://github.com/SvenVD/rpisurv
- [C3] OpenSurv official repository: https://github.com/OpenSurv/OpenSurv
- [C4] OpenSurvPro project repository: https://github.com/BigTonyTones/OpenSurvPro
- [C5] tinyCam official compatibility page: https://www.tinycammonitor.com/support.html ; historical changelog: https://www.tinycammonitor.com/changelog.html . The compatibility page is dated July 2023; no current model-count or release-version claim is made.
- [C6] Ubiquiti official product/specifications: https://store.ui.com/us/en/products/ufp-viewport ; https://techspecs.ui.com/unifi/physical-security/ufp-viewport
- [C7] Frigate official live-view documentation: https://docs.frigate.video/configuration/live/
- [C8] ONVIF official Media1/device service definitions: https://www.onvif.org/ver10/media/wsdl/media.wsdl ; https://www.onvif.org/ver10/device/wsdl/devicemgmt.wsdl

All engineering priorities are product-impact judgments. They are not CVSS ratings, externally validated vulnerability disclosures or a declaration that every security property has been audited.
