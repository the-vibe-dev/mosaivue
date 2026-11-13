# Mosaivue second-pass renderer and runtime review

Date: 2026-11-13. Baseline: the newly supplied 0.1.0b3 source archive. Updated implementation: the current source tree prepared for 0.1.0b4. Scope: renderer controller, GStreamer/OMXPlayer contracts, local RPC, scheduling, runtime capability reporting, and focused tests. The earlier review in `docs/review/renderer.md` was read before this pass; its resolved findings are not counted again here.

## Outcome

This pass fixes remaining runtime failure paths and makes the implemented display controls explicit. Manual GStreamer rotation can now prepare the camera actually requested by Previous/Next, an OMXPlayer spawn error no longer kills recovery for every tile, and temporary database failures no longer permanently disable scheduling or a rotation timer. Essential daemon tasks are supervised. Capability reports are written atomically, and the UI receives a conservative feature map with explicit limitations.

Focused verification: **130 passed, 1 skipped**, plus a clean Ruff check. These are source, in-memory, and mocked backend tests. They do not certify physical video output or new hardware behavior.

## New findings and implemented corrections

| Priority | Baseline defect and effect | Change and evidence |
|---|---|---|
| High reliability | Manual Previous/Next used the same preconnected activation path as automatic rotation. Previous commonly requested a different camera from the prepared Next branch; an immediate Next could also arrive before any prepared frame. GStreamer rejected the request instead of preparing the requested camera. | RPC manual commands explicitly select the manual path. With preconnection enabled, the controller prepares the exact camera/profile/URL, waits for backend readiness, and activates only after confirmation. A readiness timeout releases the standby and keeps the current camera/cursor. Automatic skip/hold behavior remains unchanged. `src/mosaivue/renderer/controller.py:286,396,425`; `renderer/gstreamer.py:968`; `renderer/daemon.py:122`. Tests exercise a Next standby followed by Previous, timeout under both failure policies, and preconnection disabled. |
| High reliability | OMXPlayer automatic restart called process creation without isolating exceptions. A missing executable or resource failure could terminate the one monitor thread shared by every tile. Repeated immediate exits also lacked exponential retry limits. | Per-player recovery handles restart errors, retains an OFFLINE state and retry detail, and schedules exponential delays from 1 to 60 seconds. The existing monitor polls every 3 seconds, so these are minimum retry deadlines, not promises of exact retry frequency. Confirmed Playing resets the delay. One bad tile cannot stop polling a healthy tile. Exception types are logged without copying exception command arguments or credential-bearing URLs. `renderer/omxplayer.py:371,406`. Tests inject repeated spawn failures, verify deadlines and continued healthy polling, and verify successful playback resets backoff. |
| High reliability | The schedule watcher's database query was outside its exception handler. A transient read failure permanently ended the task. The per-slot rotation loop had the same problem when reading group configuration. | The watcher retries opening/querying/applying at its next normal 30-second poll. A rotation configuration-read failure increments the visible failure count and retries after five seconds. Cancellation still propagates. `renderer/daemon.py:28`; `renderer/controller.py:242`. Tests cover session-open, query, and apply failures, rotation read recovery, cancellation, focus, and scheduling disabled. |
| High operability | The daemon created RPC/scheduler tasks and then only waited for a stop signal. An essential background task could die while the process remained alive, preventing the service manager from recognizing failure. | The daemon waits for a stop signal or the first essential task to finish. Unexpected task return, cancellation, or exception raises an error after cleanup; the service manager can then restart the process. Normal requested shutdown joins tasks and closes the server/controller. `renderer/daemon.py:52,133`. Tests cover every essential-task completion mode and normal stop. Actual systemd restart behavior was not executed here. |
| Medium correctness | A malformed persisted schedule could raise during matching and suppress later valid schedules. This can affect old/corrupt rows even though new API inputs are validated. | Invalid stored schedule time/day data is logged by schedule ID and skipped, allowing the next valid priority candidate. Normal window semantics are unchanged. `src/mosaivue/services/schedules.py:37`. Tests cover invalid hour, malformed time, and invalid day data ahead of a valid lower-priority row. |
| Medium operability | Every RPC operation shared a ten-second response timeout. OMX preparation and handoff, or a larger wall update, can exceed that budget and leave the UI reporting failure while work continues. | Connection, status, write, and close deadlines remain ten seconds by default. Six potentially long mutations receive a separate 60-second response budget: apply, focus, restore, stream restart, next, previous. `renderer/rpc.py:16,26,47`. In-memory stream tests prove the longer mutation budget and unchanged short connection deadline. This is an acknowledgement timeout, not transactional cancellation or an asynchronous operation queue. |
| Medium product clarity | Existing capability detection reported general backend mechanics but did not tell clients which layout/display controls were actually implemented. Saved labels, native sizing, audio, portrait, and output preferences could imply behavior absent on the selected backend. | Backend listings and runtime status expose `feature_support` plus readable `limitations`. The controller caches its capability report and returns a defensive copy, avoiding detection on every status poll. Unavailable backends retain their implementation map separately from `available=false`. GStreamer with no display sink now supplies a meaningful unavailability reason. `renderer/base.py:10,92`; `renderer/gstreamer.py:195`; `renderer/omxplayer.py:57`; `renderer/controller.py:41,516`. The frontend agent consumes this contract. |
| Medium reliability | Hardware capability refresh wrote the target JSON file directly. Concurrent readers could encounter truncated JSON, and a failed write could destroy the previous complete report. | Serialize to a unique temporary file in the same directory, flush/fsync, set mode 0640, and replace atomically. Failure preserves the last report and removes the temporary file. `src/mosaivue/services/capabilities.py:241`. Tests inspect the old and replacement files at cutover and inject serialization/replacement errors. This does not claim full power-loss durability of the containing directory. |

OMX monitor lifecycle also now permits reinitialization after a stopped/dead thread, joins the monitor on shutdown, and reports STOPPED after shutdown. Its existing hardware launch, positioning, codec, transport, and handoff configuration is retained.

## Additive capability API contract

`GET /api/v1/renderer/backends` returns the existing list shape with two additional fields on each backend. `GET /api/v1/renderer/status` includes a `capabilities` object containing the same serialized `RendererCapabilities` fields. No route behavior was rewritten in this pass.

| `feature_support` key | GStreamer | OMXPlayer | Meaning / limitation |
|---|---|---|---|
| `labels` | true | false | GStreamer title overlays; OMX title data is metadata only. |
| `manual_crop` | true | false | GStreamer crop needs known source dimensions. |
| `opacity` | true | true | OMX opacity changes restart that player. |
| `z_order` | true | true | Existing compositor/overlay implementation. |
| `audio` | false | false | No implemented tile unmute output. |
| `native_size` | false | false | Existing native choice falls back to contain/letterbox behavior. |
| `portrait` | false | false | No implemented physical output rotation. |
| `multiple_outputs` | false | false | One output architecture. |
| `background` | false | false | No configurable per-tile background rendering. |
| `borders` | false | false | No per-tile border rendering. |
| `output_selection` | false | false | Display profile connector name is metadata only. |
| `refresh_rate` | false | false | Display profile refresh rate does not set the monitor mode. |
| `prevent_blanking` | false | false | Display profile preference is not enforced by these renderers. |

Flags describe implemented software behavior, **not hardware qualification**, current plugin availability, or measured capacity. The in-memory test backend reports the GStreamer-like logical controls and explicitly states that it has no physical video output. Existing `snapshots=false` remains unchanged. Camera-probe preview images are separate from renderer snapshots.

During focus, `active_layout_id` and `active_revision` continue identifying the wall to restore; `focused=true` identifies the temporary view. A regression test now pins this contract. Editing camera/group settings still requires explicit layout reapplication to reconcile the active wall; this pass does not invent a global revision across all configuration objects.

## Schedule and readiness details

Schedule times use the appliance's local timezone. Equal start/end denotes a complete **local calendar-day window** anchored on the selected start day. It can span 23 or 25 elapsed hours at a daylight-saving transition, so documentation should avoid describing this unconditionally as exactly 24 elapsed hours. Tests cover both repeated local fall-back hours and a 23-hour spring-forward day. No per-schedule timezone was added.

The new manual readiness poll waits up to eight seconds after `prepare_stream` returns. Backend preparation itself can take time; this is not a promise that the entire command finishes within eight seconds. GStreamer readiness requires the requested camera/profile/URL and a decoded frame no older than eight seconds. Its activation method still performs its own readiness check. OMX preparation already waits for player playback confirmation and retains its existing synchronous readiness behavior. With preconnection disabled, the original direct replacement path is retained. Random/weighted selection still chooses from those policies; Previous does not represent a playback-history stack in those modes.

## Verification record

From the project root, using the shared review virtual environment:

```sh
python -m pytest tests/renderer tests/unit/test_schedules.py tests/unit/test_capability_report.py -q
ruff check src/mosaivue/renderer src/mosaivue/services/schedules.py src/mosaivue/services/capabilities.py tests/renderer tests/unit/test_schedules.py tests/unit/test_capability_report.py
```

Results: **130 passed, 1 skipped in 1.06 seconds**; **Ruff passed**. There are 43 additional parametrized test cases across the focused set. The skip is the real Unix-socket roundtrip: this execution environment prohibits socket creation. Real asyncio readers and controlled writers still exercise framing, timeout, and protocol behavior. The log is retained as `renderer-tests-v2.log` outside the source tree. This focused result is not a substitute for the root agent's final combined suite/build validation.

New test modules: `tests/renderer/test_daemon_resilience.py`, `tests/unit/test_capability_report.py`. Expanded modules: `tests/renderer/test_controller_regressions.py`, `tests/renderer/test_backend_regressions.py`, `tests/renderer/test_rpc.py`, `tests/unit/test_schedules.py`.

The supplied `BUILD-VERIFICATION.md` reports 247 Python tests, five browser tests, and initial Pi 3 upgrade/reboot results showing 7/7 sources at source commit `6b206cd`. Those are **user-supplied historical results for the supplied build**. They were not executed in this review environment and do not qualify the new runtime changes.

## Remaining gaps and acceptance priorities

1. **Requalify the modified runtime on hardware.** Verify manual Previous with a prepared Next branch, immediate Next before standby frames arrive, an unavailable target, OMX spawn/resource failure, long player outage, and a database read interruption. Check fixed-tile continuity, counters, actual recovery cadence, and both normal shutdown and service-manager restart. Repeat existing seven-camera cold-boot/upgrade/reboot acceptance before a 24–72 hour soak on Pi 3/OMX and representative GStreamer targets.
2. **Full-layout asynchronous acceptance remains open.** Existing layout rollback handles synchronous rejection. It does not prove that every newly accepted branch will yield decoded frames. Manual rotation readiness is a bounded improvement, not a universal last-known-good activation transaction.
3. **Event-loop latency and cancellation ownership remain architectural work.** Some backend operations still block the controller event loop, and cancelling an `asyncio.to_thread` await does not stop work already running in its worker. A future serialized operation queue needs explicit operation identities, cancellation ownership, and measured progress/deadlines. The longer mutation RPC response budget does not solve these concerns.
4. **OMX liveness remains playback-state confirmation.** Playing status does not demonstrate actual frame or pixel advancement. The new monitor resilience should not be marketed as frozen-video detection. GStreamer escalation can still deliberately recycle the entire renderer after sustained failures, affecting healthy tiles.
5. **Physical multi-monitor, portrait, and missing presentation features remain future implementation.** Capability flags and UI constraints make these gaps visible; they do not implement connector routing, independent outputs, monitor mode control, blanking control, audio, borders, native pixel sizing, OMX labels/crop, or renderer snapshots.
6. **Schedule product behavior remains limited.** There is no per-schedule timezone, explicit override duration, or automatic end-of-window fallback. The existing current-wall retention remains; an all-day lower-priority schedule can express a default wall. Synchronized rotation groups and complete placeholder failure policy remain separate gaps.

No changes were made to installer, packaging, version files, API routes, or release documentation in this scoped renderer implementation pass.
