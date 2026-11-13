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

No Pi, ROCK Pi, Ubuntu HDMI, real decoder, privileged install/rollback or long-duration soak was run for this integrated candidate.

## Historical site evidence

The detailed Pi, ROCK Pi and Ubuntu site observations supplied in this file with 0.1.0b2 are preserved verbatim under a context notice in [historical-build-verification.md](docs/review/historical-build-verification.md). They were not repeated here and do not qualify modified 0.1.0b3 code.
