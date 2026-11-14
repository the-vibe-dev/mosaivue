# Build verification - 0.1.0b5 review candidate

The supplied b5 candidate was reviewed on November 13, 2026 (America/New_York); execution logs use UTC. Detailed review reports and prior appliance evidence are retained locally in the ignored `.private-reviews/` directory.

## Current software result

- Exact-upload baseline: 362 Python passes, 3 environment-dependent skips.
- Supplied candidate: 442 Python passes, 3 environment-dependent skips, 1 existing Starlette/HTTPX deprecation warning.
- Combined statement/branch coverage: 63.11% to 65.10%.
- Frontend: 53 JavaScript passes, strict TypeScript/production build passed, 38 static files synchronized and byte-verified.
- Supplied review environment: 1 static frontend/E2E pass and 10 browser skips; the static pass is included in its combined count.
- Ruff, byte compilation, 13 shell syntax checks and both nonprivileged installer helper suites passed.
- Installed runtime graph: 37 Python distributions audited with no known advisories returned. Bandit retained 0 high, 1 reviewed medium and 46 low patterns.
- Source, wheel and amd64 Debian artifacts are included with checksums and package inspection/smoke evidence. Exact-input patch application and ZIP manifest verification are recorded in the delivered validation directory.

## Local integration checks after applying the archive

- The integrated non-browser Python suite passed **443 tests with 2 privilege skips**. This host permits the Unix-socket test skipped by the supplied review. The existing Starlette/HTTPX deprecation warning remained.
- TypeScript typecheck, production frontend build and all **53 JavaScript tests** passed. A disposable seeded server and Chromium passed all **10 browser workflows**. A separate desktop and 390-pixel mobile editor check loaded the page, selected a tile, found no page exceptions or unexpected HTTP errors, and found no horizontal document overflow. The expected unauthenticated `/auth/me` 401 occurred before login.
- Ruff, Python byte compilation, release check, installer rotation/path/bootstrap helpers and shell syntax checks passed.
- Fresh source and amd64 Debian packages were built from the integrated tree; both SHA-256 sidecars verified. The source package excluded the local review archive and previous review history. Public Markdown links were checked after moving `docs/review/` into the Git-ignored `.private-reviews/` directory; none were missing.

## What these results do not establish

No b5 root/systemd install, ARM/native-media execution, real camera, physical HDMI, hotplug or long-run observation occurred here. The local browser run exercised a disposable test backend, not physical playback. Real different-group and root/rsync ownership cases remain skipped. Product screenshots in `docs/images/` are historical; the local editor QA screenshots are outside the repository.

The supplied b4 record includes eight browser workflows, Pi 3 post-reboot 7/7 LIVE, Ubuntu physical 7/7 advancing streams, and ROCK Pi fullscreen 7/7 with one cold-start restart. Those are meaningful results for that exact b4 source. No completed final-source 24h observation was included, and all controlled upgrades used `--skip-packages`. PTZ remains unimplemented and physical PTZ hardware was unavailable.

See the [installation guide](docs/install.md), [hardware test plan](docs/hardware-test-plan.md), and [changelog](CHANGELOG.md). The supplied review did not publish or deploy this candidate.
