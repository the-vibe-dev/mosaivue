# Mosaivue backend follow-up review

**Review date:** 13 November 2026
**Input:** the newly supplied 0.1.0b3 source archive
**Scope:** API/authentication, camera and layout data, configuration backup/restore, appliance settings, preview/probe resource use, and operational error handling.

## Result and evidence boundaries

This pass implemented four concrete improvements: typed compatible settings, reliable concurrent configuration writes, bounded/coalesced camera preview and test work, and safe layout revision allocation after restoring older current revisions. The database schema and existing successful camera/preview/probe response shapes remain unchanged.

The final focused backend verification completed with **119 passed, 1 skipped, 1 warning in 9.22 seconds**. Of these, **48 passing cases and one root-only conditional case are new in this pass**. Ruff passes on every backend file changed here. The skip requires real root privileges to test adoption of a different filesystem group; this workspace runs as uid 1000. The warning is the existing Starlette/httpx TestClient deprecation warning.

The supplied archive already contains the prior review's credential-preserving restore, graph validation, profile identity, authentication/session, setup/key publication, event ordering, error redaction and ONVIF onboarding corrections. Those are retained and regression-tested; they are not credited as new work. The user's supplied build-verification history, including reported Python/browser results and the Pi 3 upgrade/reboot observations, remains separate historical evidence. This pass does not replace that history with an assertion that nothing has ever been hardware-tested. Conversely, the new worker budget and settings changes were not exercised on a physical camera or Raspberry Pi here.

## New findings and corrections

| ID / priority | Evidence in the supplied b3 source | Impact | Correction and regression evidence |
|---|---|---|---|
| B2-01 / P2 | `src/mosaivue/config.py:31–34` inserted arbitrary JSON values into a dataclass; environment conversion at `69–81` was inconsistent. An invalid optional renderer override such as a list could raise an uncaught unhashable-type error. | A string `"false"` could keep previews or schedules enabled; invalid booleans, ports, session lifetime and backend names failed late or behaved differently depending on where they were configured. | `_normalize_setting`, `Settings.__post_init__` and the unified final load validation now normalize compatible legacy values and reject invalid known values with field-specific, value-free errors. Existing example configuration, booleans, ranges, hostname/IP input, environment precedence and malformed file/override roots have focused tests. Updated evidence: `config.py:16–138,193–235`; `tests/unit/test_config.py`. |
| B2-02 / P2 | `config.py:45–53,85–91` used a fixed `.tmp` name for all writers to each destination, and did not synchronize file data/directory replacement or consistently retain group ownership. | Concurrent backend selection or settings writes could contend on the same temporary file. A root-created replacement could become unreadable to the service group, or a later unprivileged replacement could fail when trying to preserve a root owner. | Unique same-directory temporary files, complete JSON serialization before replacement, `fsync` of the file and containing directory, 0640 permissions, regular-file destination checks and permitted ownership/group preservation. New files inherit the parent group where allowed. A service replacing a root-owned override in its own writable data directory keeps its own UID; protected `/etc` directory permissions remain authoritative. Forty concurrent settings saves and thirty-six backend selections leave complete parseable files and no temporary residue. Owner/group policy tests pass; the real cross-group root test is explicitly conditional. Updated evidence: `config.py:148–190`; `tests/unit/test_config.py`. |
| B2-03 / P2 | `api/routes_cameras.py:114–115,138–139` started a new `asyncio.to_thread` job for every test/thumbnail request. Individual media timeouts existed, but there was no shared appliance-process budget, duplicate coalescing or thumbnail cache. | Multiple clients could consume scarce CPU/decoder resources with identical or simultaneous captures. Simply adding a semaphore around a cancellable HTTP waiter would still release capacity while its capture thread continued running. | `StreamWorkPool` owns independent capture tasks, with a default of one active preview/probe, eight queued distinct jobs, a two-second queue timeout, same-request coalescing and a two-second JPEG cache bounded to 64 entries/8 MiB. Waiters use cancellation shielding; a disconnected caller does not release the capture's slot. Saturation returns 503 plus `Retry-After: 2`. Auth, the preview-enable setting and current camera/profile state are checked before cache access. Updated evidence: `services/stream_work.py:20–142`, `api/routes_cameras.py:25–40,125–178`, `api/app.py:57–60,73–77`. |
| B2-04 / P2 | `services/layouts.py:84` allocated `current_revision + 1`, while backup/import deliberately permits an older current revision with newer saved drafts. | After restoring a valid export with current revision 1 and an existing revision 2, the next edit or history restore tried to create revision 2 again. The API could misleadingly report a duplicate layout name from the uniqueness failure. | Allocate one greater than the largest existing revision, preserving every historical revision. Two real-database cases round-trip a backup whose selected current revision is older than its newest draft, then independently edit or restore history and verify a new revision 3. Updated evidence: `services/layouts.py:84–90`; `test_restored_current_revision_can_be_older_than_existing_drafts`. |

Priorities express engineering/user impact, not CVSS scores or a claim of a complete penetration test.

## Settings compatibility and operations

The `Settings` dataclass and mapping API remain available. JSON must be an object. Unknown keys are ignored with a visible warning, preserving the ability to read files from newer versions; they are not silently treated as implemented features. Invalid optional renderer-override files are ignored with a warning, while an invalid primary configuration fails with an actionable error. Effective precedence remains primary configuration, saved renderer selection, then environment.

| Setting | Accepted range/type | Default / operational note |
|---|---|---|
| Boolean fields | Boolean values; integer 0/1; case-insensitive true/false, yes/no, on/off, 1/0 strings | Legacy string values are normalized, not used for Python truthiness. |
| `port` | Integer 1–65535, including decimal integer strings | 8080. Booleans and fractional numbers are rejected. |
| `session_hours` | Integer 1–8760 | 12. |
| `preview_concurrency` | Integer 1–4 | 1 shared active HTTP preview/probe job per API application instance. |
| `preview_cache_ttl_seconds` | Integer 0–30 | 2; zero disables image caching. |
| `bind` | IPv4, IPv6 or a bounded hostname without scheme/port | Existing default remains 127.0.0.1. |
| `renderer_backend` | auto, gstreamer, omxplayer, or test | The existing renderer factory still separately requires explicit permission to use the test backend. |
| `renderer_sink` | `auto` or a valid GStreamer element name | Does not assume every platform uses kmssink. |
| `log_level` | Standard Python level names, with WARN/FATAL aliases normalized | INFO. |
| `profile` | balanced, performance, quality, low-latency, custom | Remains an advisory label, not proof that a tuning preset was applied. |
| Optional text fields | Null/empty or bounded text without control characters | `rtsp_tls_ca_file`, when present, must be an absolute path; validation does not claim the certificate exists or is trusted. |

Additional supported environment overrides are `MOSAIVUE_SESSION_HOURS`, `MOSAIVUE_WEB_PREVIEW_ENABLED`, `MOSAIVUE_UPDATE_CHECKS_ENABLED`, `MOSAIVUE_SCHEDULE_ENABLED`, `MOSAIVUE_PREVIEW_CONCURRENCY`, and `MOSAIVUE_PREVIEW_CACHE_TTL_SECONDS`. Existing environment names remain supported.

Restart the API to apply a changed preview worker count/cache TTL. `web_preview_enabled` is checked on each preview request. Known invalid configuration values that were previously accepted silently may now prevent startup; correct the named field before restarting the appliance. A malformed optional saved backend override continues to fall back to valid primary/environment settings.

## Preview and probe behavior

Cache keys are process-private keyed digests covering the resolved credential-bearing URL, encrypted credential generation, camera/profile identity and update times, complete profile metadata, transport and requested width. Plaintext URI/password strings are not stored in cache keys or logged by this coordinator. Credential/transport/profile changes select a different key; disabling or deleting a camera cannot be bypassed by an already warm cache. Actual capture work necessarily holds its stream URI transiently while connecting.

Successful JPEG responses remain `image/jpeg` with `Cache-Control: no-store` for browsers. The short cache is internal to the API process. Failed captures are not cached; oversized cache entries are returned to the requester without being retained. Probe results are coalesced only while the same probe is running and are not cached afterward, so repeated completed tests remain fresh. Discovery duration remains distinct from decoded time-to-first-frame; no new latency claim is made.

The pool closes to new work at application shutdown and drains active synchronous work before clearing its image cache. The media implementation's existing timeouts remain responsible for finishing actual GStreamer/FFmpeg work. The budget does not constrain the independent HDMI renderer, ONVIF HTTP inspection, diagnostic benchmarks, or manually launched CLI processes. Deploying multiple API worker processes would create one pool per process; the standard single-process service receives the documented aggregate limit. Identical HTTP callers can join a shared job without consuming additional decode slots; their HTTP waiter/connection count is not capped by this pool. Apply normal reverse-proxy/server connection limits if broader authenticated traffic requires them. Load tests on the target Pi are still needed before choosing a concurrency above one.

The integration checks demonstrate cache reuse, password/credential-clearing invalidation, transport/codec/profile/width changes, enabled-camera and global-preview gates, per-request session authentication, unchanged successful response shape, fresh probes, and retryable 503 responses. Thread/event-based unit checks establish maximum concurrent producers, queue saturation/timeouts, cancellation ownership, coalescing, TTL expiry, cache count/byte eviction, failure recovery and shutdown draining. They use controlled producers, not a physical decoder.

## Important remaining gaps

1. **Full URI confidentiality remains P1 work.** Saved password fields are encrypted; usernames remain available to authenticated administrators. Arbitrary bearer secrets in vendor-specific RTSP paths/query strings remain part of stored/exported URLs. The new digest cache keys do not change that storage model. Encrypt the complete URI with a migration and backward-compatible backup semantics before claiming all stream secrets are encrypted.
2. **Backups still cover application configuration, not a complete appliance recovery image.** Accounts/sessions, appliance config files, renderer override, custom CA trust, systemd/OS changes and installed packages are outside the archive contract. Configuration restore and renderer reapplication remain distinct outcomes. A versioned settings/recovery manifest and restore rehearsal are useful next work.
3. **Account roles, service tokens and audit history are incomplete.** The admin flag is not a complete viewer/operator/admin product surface; ordinary mutations do not provide an operator-facing immutable audit trail. Add explicit authorization rules and secret-free activity retention before shared-team or unattended integration claims.
4. **Saved camera/group changes and applied output need an explicit runtime revision contract.** The frontend branch improves reapply guidance and layout revision visibility. A database-only `pending_changes` flag was deliberately not added because schedules, focus, restarts and renderer failure can make it inaccurate. Concurrent editor conflict handling/optimistic revision checks also remain future work.
5. **Device trust and media interoperability still require real qualification.** Custom RTSP CA behavior across probes/previews, ONVIF device interoperability, TLS failures, UDP transports, codec support, actual time-to-first-frame, long-run CPU/temperature and decoder recovery should be exercised on representative devices. Existing user-supplied Pi evidence remains useful but does not qualify this new queue/cache policy.
6. **Root ownership integration has a named verification limit.** The new permission policy is unit-tested and ordinary real filesystem writes are tested under uid 1000. The different-group root-created-file test is present for privileged CI/appliance execution and skipped here. No full privileged installation was run by this reviewer.

## Verification record

```text
python -m pytest -q \
  tests/unit/test_config.py tests/unit/test_stream_work.py \
  tests/unit/test_backup.py tests/unit/test_configuration_integrity.py \
  tests/unit/test_camera_service.py tests/unit/test_layout_service.py \
  tests/unit/test_schemas.py tests/unit/test_security.py \
  tests/unit/test_stream_probe.py tests/unit/test_diagnostics.py \
  tests/integration/test_api.py tests/integration/test_review_regressions.py \
  tests/integration/test_stream_work_api.py --tb=short

119 passed, 1 skipped, 1 warning in 9.22s
```

Ruff passed on the nine changed/new backend source and test files. The root review performs the final repository-wide tests, frontend/browser checks, scanner gates, versioning and packaging after this source freeze.

### Changed files in this backend pass

- `src/mosaivue/config.py`
- `src/mosaivue/services/stream_work.py` (new)
- `src/mosaivue/services/layouts.py`
- `src/mosaivue/api/routes_cameras.py`
- `src/mosaivue/api/app.py`
- `tests/unit/test_config.py` (new)
- `tests/unit/test_stream_work.py` (new)
- `tests/unit/test_layout_service.py`
- `tests/integration/test_stream_work_api.py` (new)
