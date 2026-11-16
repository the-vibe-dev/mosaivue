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

## Controlled appliance rollout after integration

The final b5 source archive was rebuilt from committed source `daef72f` after an earlier staging package omitted newly added files. The complete archive SHA-256 is `d9d41f433565343b43b4de17b9ca9c21c7cf767b932fef689a28a84bb4274ec8`; all three target transfers were checksum-verified. The first Ubuntu trial on the incomplete archive had stalled video and was rolled back to a healthy b4 wall. A repeat trial recovered; the exact cause of that first playback failure is unconfirmed. Only the complete archive is used in the final b5 observations.

- **Pi 3B+ / Bullseye armhf / OMXPlayer:** Source upgrade, 7/7 LIVE, zero restarts, rotation and manual Next/Previous passed. A controlled reboot returned Wi-Fi, masked rfkill units, HTTP and 7/7 playback. Its final b4 source had previously completed 24 hours with 1,441 healthy samples, zero restarts and a maximum 81.5-second sample gap.
- **ROCK Pi 4B+ / Debian arm64 / GStreamer KMS:** Source upgrade, seven advancing streams, rotation and manual Next/Previous passed. A controlled reboot returned HTTP and a 1920×1080+0+0 KMS plane with seven advancing streams. One stream needed a postboot cold-start retry and has not grown in the initial observation. The previous b4 record reached 24 hours with no failed health samples, but its final sampling gap was 94 seconds, above a strict 90-second threshold.
- **Ubuntu / NVIDIA / GStreamer X11:** Source upgrade retained the verified software H.264 decoder. Seven physical-output frame counters advance with HDMI-0 connected at 1920×1080, zero stream restarts in the final observation and HTTP/static-asset health. Its previous b4 observation was interrupted by host maintenance and two guest reboots, so it did not complete an uninterrupted b4 window.

All three b5 installs used `--skip-packages` and retained root-only rollback snapshots. OMX LIVE does not independently prove decoded-frame advancement. Physical b5 picture quality has not yet been reconfirmed by a person at the displays.

## First b5 overnight audit — November 16, 2026 UTC

- **Pi 3:** 1,443/1,443 healthy samples over 24.033 hours, maximum 73.4-second gap, zero renderer or stream restarts and 5,765 rotation switches. This is a complete 24-hour sampled OMX playback result. A later one-slot status during the operator's remote-layout test was an intentional layout change, not a renderer restart.
- **ROCK Pi:** 1,440/1,440 healthy samples over 23.984 hours, maximum 63.2-second gap, seven advancing streams, full 1920×1080+0+0 plane, and its one postboot cold-start restart unchanged. The observer ended about one minute short of a strict 24-hour first-to-last sample span. A fresh observer runs 24.05 hours to close that gap.
- **Ubuntu:** 1,440 samples over 23.983 hours with no renderer or per-stream restarts, but **23 samples across 12 episodes had the rotating tile DEGRADED**, leaving 6/7 slots LIVE. The longest episode lasted four one-minute samples. Fixed tiles stayed LIVE; decoded frames usually continued while switching paused. Renderer logs recorded prepared RTSP `Could not write to resource` errors and failed rotation steps. The last 945 automated samples were healthy, and the current wall is 7/7 with advancing frames. A fresh 24.05-hour observer is tracking recurrence. The exact cause of the RTSP interruptions is unproven.

## What these results do not establish

The local browser run exercised a disposable test backend; its results do not prove physical playback. A clean full-package install, actual hotplug, real different-group and root/rsync ownership cases, and uninterrupted 24-hour Ubuntu/ROCK Pi plus extended b5 observations remain open. Product screenshots in `docs/images/` are historical; the local editor QA screenshots are outside the repository.

The supplied b4 record includes eight browser workflows, Pi 3 post-reboot 7/7 LIVE, Ubuntu physical 7/7 advancing streams, and ROCK Pi fullscreen 7/7 with one cold-start restart. Those are meaningful results for that exact b4 source. The later Pi 3 b4 soak completed as recorded above; earlier partial runs cannot be merged with it. PTZ remains unimplemented and physical PTZ hardware was unavailable.

See the [installation guide](docs/install.md), [hardware test plan](docs/hardware-test-plan.md), and [changelog](CHANGELOG.md). This controlled deployment does not publish a b5 release.
