# Build verification: 0.1.0b3 review candidate

The supplied candidate was reviewed and packaged on November 13, 2026 (UTC). It is an unpublished review build. The first section records the archive review; the local integration results follow.

## Supplied review results

- Python suite excluding browser tests: **245 passed, one environment skip**, one upstream deprecation warning.
- Combined Python statement/branch coverage: **59.39%**, up from 47.58% on the supplied archive.
- Strict TypeScript, frontend build, source/test/script Ruff checks, byte compilation and installer helper checks passed. Final JavaScript test count and distribution checks are recorded with the delivery evidence.
- Updated wheel, source archive and amd64 Debian package are included in the review bundle. A built package is not a verified root installation.
- Real Unix-socket integration is blocked by this environment; the corresponding test is retained with an explicit environment skip.
- Chromium could not start in the review environment because Unix-socket creation was prohibited. Browser interaction checks were unverified there.
- No camera, physical display, hardware decoder, clean target installation or long-duration appliance qualification was performed for this candidate.

See [the complete validation record](docs/review/validation.md), [the review report](docs/review/report.md), and [upgrade instructions](docs/review/upgrade.md). The handoff bundle includes test/build logs, package checksums, an issue register and the original-to-candidate patch.

## Local integration after handoff

The reviewed source was applied to the Mosaivue repository on November 13, 2026. The archive's 303-file checksum manifest passed, and the applied patch matched its complete source tree byte for byte before one additional camera credential fix.

- Python: **247 passed**, one upstream Starlette/httpx deprecation warning (`pytest -q --ignore=tests/e2e`).
- JavaScript: **20 passed** after rebuilding `frontend/dist`; TypeScript, frontend build, Ruff, byte compilation, release check and both installer helper suites passed. The rebuilt frontend assets match `src/mosaivue/static`.
- Browser: **5 passed** against an isolated local test-backend server with seeded demo cameras and Chromium. Desktop dashboard and mobile schedules rendered; the tested navigation produced no page errors. This qualifies those control workflows only, not video playback.
- The browser run found that editing a camera without credentials could create an encrypted empty password. The camera service now ignores a null-only credential edit and reports an empty password accurately. A focused unit regression and the camera-edit browser workflow pass.

At the time of that local integration check, no Pi, ROCK Pi, Ubuntu HDMI, real decoder, privileged install/rollback or long-duration soak had been run for this integrated candidate.

## Appliance qualification started November 13, 2026

The source archive built from commit `6b206cd` was verified by SHA-256 on each installed device before use. It contains the reviewed b3 changes plus the camera credential fix and Bullseye installer corrections.

- **Pi 3B+ / 32-bit Bullseye / OMXPlayer:** An upgrade from 0.1.0b1 exposed two incompatible piwheels native binaries. The installer restored the previous release after each failed attempt; the old wall returned to 7/7 LIVE and HTTP health passed. The corrected installer selects checksum-pinned upstream ARMv7 `cryptography` and `pydantic-core` wheels and imports the web and renderer entry points before stopping services. The subsequent privileged upgrade completed. Initial b3 checks showed 7/7 LIVE, ten rotation switches, zero restarts, both services active and HTTP health passing. A 24-hour observer is recording; no completed soak result is claimed yet.
- **Ubuntu GPU VM / GStreamer:** The final source commit installed successfully with rollback snapshots retained. The VM's address changed after its host move. One legacy camera hostname failed DNS; its endpoint was changed to the same reachable UniFi host used by the other cameras, and its probe succeeded. A real camera using NVIDIA decoding and a headless sink stayed LIVE and advanced from 88 to 568 frames in 25 seconds. The passed-through NVIDIA GPU still reports its physical HDMI/DP connectors disconnected; the full X11 wall remains unstable and physical HDMI qualification has not started. A separate observer records its preconnection state.
- **ROCK Pi:** The former `.180` gateway and the ROCK Pi are unreachable from the test network. No b3 install or soak has started there.

The Pi 3 privileged installer and rollback behavior now has direct appliance evidence. The Ubuntu physical display, ROCK Pi installation, and 24-hour results remain pending.

## Historical site evidence

The detailed Pi, ROCK Pi and Ubuntu site observations supplied in this file with 0.1.0b2 are preserved verbatim under a context notice in [historical-build-verification.md](docs/review/historical-build-verification.md). They were not repeated here and do not qualify modified 0.1.0b3 code.
