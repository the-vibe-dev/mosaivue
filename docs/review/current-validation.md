# Current validation: 0.1.0b4

Date: November 13, 2026. This record describes the candidate built from `mosaivue-main (3).zip`. The prior `validation.md` and unchanged `supplied-b3-build-verification.md` are historical evidence for earlier code and environments.

## Software checks

| Check | Observed result |
|---|---|
| Uploaded b3 Python baseline | 246 passed, 1 skipped, 1 upstream warning in 17.85 seconds. Browser tests excluded. |
| Final combined b4 Python suite | 358 passed, 3 skipped, 1 upstream warning. Browser tests excluded. |
| Combined statement/branch coverage | 59.4965% baseline; 62.4433% candidate, an increase of 2.9468 percentage points. |
| Candidate statement / branch coverage | 65.0180% / 52.5434%; 4,325 of 6,652 statements and 909 of 1,730 branches. |
| Frontend | Strict TypeScript/build passed; 35 JavaScript tests passed versus 20 supplied. No new frontend dependency. |
| Packaged static assets | 36 compiled files synchronized and byte-checked. |
| Python frontend/E2E selection | 1 static-asset test passed; 8 browser scenarios skipped without a configured E2E server. |
| Ruff and byte compilation | Source, tests/scripts as applicable, and packaging passed. |
| Shell checks | 13 shell files passed syntax checks; nonprivileged rotation/path helper suites passed. |
| Installer regressions | 21 passed, 1 real root/rsync ownership case skipped; included in the combined count. |
| Bullseye manifest | Six filenames, upstream URLs and SHA256 values matched official PyPI metadata. No ARM execution. |
| Runtime dependency audit | 37 installed runtime Python distributions checked; no known advisories returned, none skipped. |
| Bandit | 46 low-severity patterns, zero medium/high. Raw output and triage retained. |

Full test logs/XML and coverage JSON are included in the bundle. Coverage is execution under this suite, not a probability of correctness or proof of native-media behavior.

## Explicit limits

Three Python cases are skipped: a real AF_UNIX RPC roundtrip (socket creation is prohibited); a real different-group settings write requiring root; and actual rsync ownership transfer requiring root/rsync. This workspace runs as uid 1000 and does not provide rsync. Writable-ancestor and unsafe release-entry rejection use real files. The successful ancestor policy case uses controlled root metadata because this workspace remaps even system directory ownership.

The warning is the existing Starlette/httpx TestClient deprecation. AF_UNIX creation was rechecked and returned `PermissionError: Operation not permitted`; no fresh Chromium launch was attempted after that prerequisite failure. Eight browser workflows remain available, including three new scenarios. No b4 rendered interaction, visual, screenshot or console-error pass is claimed. Historical screenshots are retained. The supplied b3 five-browser-test pass remains attributed to the other host and older code.

No root/systemd install, ARM execution, real camera, physical HDMI, hotplug, hardware decoder load or new soak was performed here. The root bootstrap integration script was not executed. Supplied Pi b3 rollback/upgrade/reboot evidence does not qualify the changed b4 paths.

### Local integration after the supplied review

On the connected development host, the complete non-browser Python suite passed **359 tests with two environment/privilege skips**; the Unix-socket case ran here. All **35 JavaScript tests**, TypeScript/build, synchronized static assets, Ruff, compilation, installer helpers and release check passed. A disposable seeded server and Chromium passed all **eight browser workflows** after the fixture was changed to reuse one authenticated context; creating a new login for every scenario exceeded the production rate limit. Desktop and phone screenshots were inspected. A mobile inspector stacking issue was fixed and a browser hit-test regression added. The only recorded console error was the expected unauthenticated `/auth/me` 401 before login; no page exception was observed.

These local checks do not qualify b4 camera playback or appliance installation. PTZ/presets remain unimplemented, and no PTZ camera is available for a physical compatibility test. Do not report PTZ support or a PTZ hardware pass from ONVIF Media1 import tests.

### Controlled appliance rollout after local integration

The later [b4 live rollout](b4-live-rollout.md) records installer upgrades on the Pi 3, Ubuntu VM and ROCK Pi; Pi and ROCK Pi cold-start recovery after reboot; and seven-stream Ubuntu HDMI and ROCK Pi KMS output with advancing decoded frames. The ROCK Pi's first KMS trial failed and was rolled back before the corrected fullscreen build. Final 24-hour observations are **in progress** on the same patched b4 source archive. Ubuntu's overnight unattended package upgrade restarted Xorg and Mosaivue services; the wall recovered, and a restart-aware physical observation was started separately. PTZ hardware remains untested. These hardware results do not retroactively change the supplied review's environment-limited claims above.

## Scanner interpretation

The dependency audit is a point-in-time check of the installed Python runtime graph. Future resolver selections, other architectures, OS/media packages, GPU drivers and camera firmware are outside it. The SPDX-style inventory records installed distribution metadata with `NOASSERTION` fields; it is not a complete OS dependency lock or license clearance.

Bandit reports expected subprocess/PATH patterns, assertions, non-security rotation randomness, empty credential placeholders and an XML import. Inbound ONVIF parsing uses defusedxml with DTD/entities/external access forbidden. The scanner review identified an installed-helper ownership boundary, corrected in b4 with explicit root-owned staging, permission normalization, protected ancestors and safe release-directory checks. Real privileged acceptance remains pending. OMXPlayer and FFmpeg preview process arguments can expose resolved stream URLs to local process inspection. See `b4-static-analysis-triage.md`; zero high/medium results is not security certification.

## Distribution checks

The bundle includes a source archive, universal Python wheel and **amd64** Debian package, with checksums and package inspection evidence. Source/wheel version is `0.1.0b4`; Debian is `0.1.0~b4`. ARM devices use source installation. Extracted-wheel import, CLI and ASGI/static smoke checks do not execute privileged package scripts or physical rendering.

The patch is generated against this exact uploaded archive, applied to a fresh copy, and compared against delivered source hashes and executable modes. ZIP CRC and the per-file SHA256 manifest are checked from the finished ZIP. Build environments, private runtime files and credentials are excluded. This verifies coherence, not identical reproducibility across all systems.

## Reproduction

```bash
python -m pytest --ignore=tests/e2e --cov=mosaivue --cov-report=json -q
ruff check src tests scripts packaging
python -m compileall -q src scripts packaging
bash scripts/test-installer-rotation.sh
bash scripts/test-installer-paths.sh
python scripts/check_release.py
cd frontend
npm ci --ignore-scripts
npm run typecheck
npm run build
npm test
```

Run the normal CI E2E workflow against an isolated seeded server, then follow `b4-acceptance-checklist.md` on the actual appliance. The in-memory renderer cannot establish hardware behavior.
