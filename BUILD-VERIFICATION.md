# Build verification: 0.1.0b4 review candidate

Reviewed November 13, 2026 from the newly uploaded b3 archive. This candidate is unpublished and has not been deployed by this review. No database migration was added.

- Python: **358 passed, 3 explicit environment/privilege skips**, one existing upstream warning. Browser tests excluded.
- Combined statement/branch coverage: **62.44%**, versus **59.50%** on this uploaded b3 baseline.
- Frontend: strict TypeScript/build passed, **35 JavaScript tests passed**, 36 compiled static files synchronized.
- Ruff, byte compilation, 13 shell syntax checks and both nonprivileged installer helper suites passed. Installer focused suite:21 passed/1 root-rsync skip, included in the Python total.
- Runtime Python advisory lookup:37 distributions, no known advisories returned. Bandit:46 low patterns,0 high/medium; triage retained, including an implemented installed-helper ownership correction.
- Source, wheel and amd64 Debian builds with checksums and package smoke evidence are included in the handoff. A build is not a privileged installation pass.
- Browser rendering, real AF_UNIX integration, privileged ownership/install/rollback, ARM binaries and changed b4 camera/physical output remain unqualified here.

Read [current validation](docs/review/current-validation.md), [the report](docs/review/current-report.md), and [upgrade guidance](docs/review/current-upgrade.md). The exact supplied b3 verification file is preserved at [supplied b3 evidence](docs/review/supplied-b3-build-verification.md), including external browser success and Pi rollback/upgrade/reboot observations, incomplete Ubuntu HDMI, unreachable ROCK Pi and no completed supplied soak. Those results are not reclassified as b4 passes.

## Local integration after handoff

The 328-file bundle manifest passed and its patch applied to the committed b3 tree. The patched tree matched the delivered b4 source byte for byte before local test and documentation corrections.

- Python: **359 passed, 2 environment/privilege skips**, one upstream Starlette/httpx warning. This host permits the Unix-socket case skipped in the review environment.
- Frontend: **35 JavaScript tests**, strict TypeScript, build, static-asset synchronization, Ruff, compilation, installer helper checks and release check passed.
- Browser: **8 workflows passed** against a disposable seeded local server. The test fixture now reuses an authenticated context so setup plus browser tests do not exceed the production login rate limit. Desktop dashboard and mobile layout controls rendered and responded. One expected pre-login `/auth/me` 401 appeared in the console; no page exception was observed.
- A mobile stacking defect discovered during visual inspection was corrected: the selected canvas tile no longer covers the inspector drawer. The browser suite includes a hit-test regression for the overlap.
- Source tarball and amd64 Debian package builds succeeded from the integrated tree; both generated SHA-256 manifests verified. No privileged install was attempted.
- PTZ is **not implemented in b4** and no PTZ camera is available for physical protocol testing. Keep PTZ and presets out of supported-feature claims until implementation and vendor-camera acceptance are complete.

No b4 build has been installed on the Pi 3, Ubuntu VM or ROCK Pi. Their b3 observation remains separate from this candidate's software checks.
