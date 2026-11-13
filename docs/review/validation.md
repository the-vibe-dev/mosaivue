# Validation record: 0.1.0b3 review candidate

This record distinguishes automated software verification from browser, system-installation, and physical video qualification. The reviewed input was `mosaivue-main (1).zip`, SHA-256 `cd43fe83ee8ae02f33877774d7dcc86f7be1af8aab123d39c9fac8804eb865d1`. The supplied package version was 0.1.0b2. Results below apply to the review candidate, with final distribution checks recorded in the bundle's `validation/build-validation.md`.

## Automated results

| Check | Result | Scope and limitation |
|---|---|---|
| Python pytest, excluding `tests/e2e` | **245 passed, 1 skipped, 1 warning** | API, SQLite, encryption, configuration, controller and backend contracts; no physical video qualification. |
| JavaScript Node tests | **20 passed**; see `validation/frontend-tests.log` | Browser-independent form/API/geometry/navigation contracts; not a substitute for rendered UI tests. |
| TypeScript strict check | Passed | `npm run typecheck`. |
| Frontend build | Passed | Built assets copied to `src/mosaivue/static`; Node is not required to serve them. |
| Ruff | Passed | Entire `src/mosaivue`, `tests`, and `scripts` trees. |
| Python byte compilation | Passed | `src/mosaivue` compiles under Python 3.12.14. This does not qualify all supported Python versions. |
| Shell syntax | Passed | Installer, packaging and shell helper scripts. |
| Installer path/metadata helper tests | Passed | Rejection of unsafe/shared prefixes, unrelated directories and linked configuration files; metadata checks. Root-only success cases are conditional and were not executed as root here. |
| Installer release-rotation helper | Passed | Release/current/previous helper behavior, not a complete privileged install. |
| OpenAPI snapshot | Regenerated | 53 paths, package version 0.1.0b3. |
| Bandit medium/high gate | Passed | The existing `-ll` CI threshold; the ONVIF wire-protocol SHA-1 operation has a narrowly documented B324 exception. Inbound XML uses defusedxml with DTD/entity/external references forbidden. |
| Runtime dependency audit | No known vulnerabilities reported | `pip-audit` checked all 37 pinned runtime dependencies in the observed build environment, with no skipped packages. This excludes OS packages and future dependency resolutions. |
| Runtime dependency/license inventory | Regenerated | 37 installed dependencies plus the Mosaivue package; declared metadata is not a legal license conclusion. |
| Distribution build and inventory | See build record | Wheel, source archive, and amd64 Debian artifact built; these are not offline dependency bundles. |

The final Python run took 14.85 seconds. Its single warning is the upstream Starlette/httpx deprecation notice. One real Unix-domain socket round-trip test skipped because this execution environment prohibits `AF_UNIX` creation. Protocol framing, malformed-response, timeout, and large-message tests ran using controlled stream readers/writers.

### Coverage comparison

The same coverage configuration enables branch measurement for both trees. These percentages describe exercised Python code, not correctness or platform compatibility.

| Measure | Original archive | Updated candidate |
|---|---:|---:|
| Covered statements / total | 2,809 / 5,472 | 3,922 / 6,328 |
| Statement coverage | 51.33% | 61.98% |
| Covered branches / total | 409 / 1,292 | 796 / 1,616 |
| Branch coverage | 31.66% | 49.26% |
| Combined statement/branch coverage | 47.58% | 59.39% |

The baseline run had 74 passing Python tests. New coverage includes real database rollback after late restore failure, preservation/remapping of stream-profile IDs, actual decryption of restored credentials, concurrent initial setup, concurrent master-key publication, commit-before-event behavior, session revocation during event streaming, ONVIF protocol/authentication failures, independent tile rotation, schedules across midnight, geometry boundaries, and synchronous renderer rollback. The CLI and TUI remain unexercised by this pytest run; GStreamer has roughly 40% combined coverage and substantial controlled-object testing.

## Reproduce the software checks

Run these commands from the project root in a disposable development environment with Python 3.11+ and Node installed. The review used Python 3.12.14. Installing dependencies can require network access. Exact installed Python distributions are included as `validation/python-environment.txt` in the handoff bundle.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q --ignore=tests/e2e --cov=mosaivue --cov-report=term --cov-report=json:coverage.json
ruff check src/mosaivue tests scripts
python -m compileall -q src/mosaivue
bash scripts/test-installer-paths.sh
bash scripts/test-installer-rotation.sh
python scripts/check_release.py
cd frontend
npm ci
npm test
npm run typecheck
npm run build
cd ..
rm -rf src/mosaivue/static
cp -a frontend/dist src/mosaivue/static
```

The frontend build process writes `frontend/dist`. Use the project's synchronization workflow when editing source so the served `src/mosaivue/static` files match it. The supplied candidate already contains synchronized assets. The release copier stages from tracked files when run in a Git checkout: commit new source files before creating a release. Its archive fallback handles this project's current ignore patterns; it is not a complete parser for arbitrary Git ignore semantics.

## Browser tests: blocked, not passed

The repository contains browser interaction tests under `tests/e2e`. Connected and cloud browser attempts could not reach the development server across execution namespaces. A second attempt launched the server and Chromium within one execution context. Chromium then failed at startup:

```text
process_singleton_posix.cc: socket() failed: Operation not permitted
```

The recorded pytest outcome was **one failure and four fixture errors, all before application interaction assertions**. The application workflows were therefore not evaluated. `validation/browser-tests-blocked.log` preserves the startup failure; it is not a report of five passing or skipped browser scenarios. A temporary in-memory renderer was used only to prepare a browser test environment. It is not included as production code, and no observation from it is presented as physical rendering evidence.

On a host that permits Chromium and local sockets, point the browser suite at an isolated test appliance using the documented `MOSAIVUE_E2E_URL` and test-credential variables. Inspect `tests/e2e/test_control_workflows.py` before running: the workflows create, edit and delete temporary configuration. Use a disposable test database, not a production wall. Review current UI coverage and add any missing acceptance scenarios for ONVIF, schedules, desktop and 390x844 mobile screens. Capture browser console errors and screenshots on that host.

## System installation and hardware: not executed

Building a `.deb` checks package construction and metadata. It does not verify installation scripts under root, a real systemd boot, an upgrade from 0.1.0b2, removal, or rollback on a clean target. The installer helper tests cover important path/ownership contracts, but no complete privileged installation was run in this review environment.

No live cameras, GStreamer decode pipelines, OMXPlayer firmware, audio/video synchronization, physical HDMI/DRM outputs, GPU drivers, thermal limits, multi-monitor behavior, or sustained stream capacities were tested here. Historical appliance observations from the supplied source have been preserved in [historical-build-verification.md](historical-build-verification.md) and are explicitly not evidence that this modified candidate passed the same conditions.

Before publishing this candidate as stable, complete the hardware/release acceptance plan in [report.md](report.md), including cold boot, profile changes, camera and network outages, two rotating tiles sharing a group, focus/restore, overnight schedules, restore, upgrade/rollback, and recorded 24-hour then 72-hour soak targets. Those durations are recommendations, not completed measurements.

## What this review does not establish

The source review and regression work do not constitute an exhaustive penetration test, formal protocol certification, accessibility conformance audit, cross-browser matrix, performance benchmark, or guarantee that all possible defects have been removed. Dependency ranges still require ongoing maintenance and a reproducible release lock. The existing Bandit medium/high gate and an advisory lookup for all 37 resolved runtime dependencies passed; this does not cover operating-system video components, unknown advisories, future package resolutions, every target Python/platform combination, or all low-severity static-analysis observations. The regenerated inventory and audit JSON are included in the handoff evidence. The competitor matrix compares documented capabilities, not measured competing products.

The report's fixed/open statuses and test evidence are intended to make the remaining work concrete. They should not be converted into broad platform or security claims without the corresponding acceptance records.
