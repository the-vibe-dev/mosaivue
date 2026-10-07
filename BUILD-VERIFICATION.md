# Build verification — Mosaivue 0.1.0b1

Verification performed on 2026-10-07 (America/New_York) for the Mosaivue private beta staging candidate.

## Completed checks

- Python unit, frontend-static, renderer, and integration suite: **30 passed**.
- Frontend TypeScript type check, production build, and Node test suite: **passed** (3 Node tests).
- Python bytecode compilation, shell syntax checks, and `scripts/check_release.py`: **passed**.
- Generated OpenAPI snapshot: **51 paths**, version **0.1.0b1**.
- Source archive `mosaivue-0.1.0b1-source.tar.gz` built from the staged Git file set; its SHA-256 sidecar verified.
- The Pi installer built and installed a Mosaivue wheel with Python 3.11 on 32-bit Bullseye. A pinned SQLAlchemy wheel and target-built cffi avoided binary incompatibilities.
- Gitleaks directory scan: **no findings**.
- Authenticated Chromium checks on the Pi loaded the supplied logo, the OMX-specific display message, rotation cards without a transition setting, and the corrected security audit, with no page errors.
- Local Chromium editor checks placed a camera by click, displayed eight resize handles, resized a tile, replaced its camera, and reflowed a seven-tile template down to five.

## Hardware evidence and remaining qualification

One Raspberry Pi 3B+ running 32-bit Bullseye is running Mosaivue with seven live camera tiles through OMXPlayer at 1920×1080. The rotating tile completed at least 21 switches with zero recovery restarts. The migrated key, config, and database have expected owner and mode checks; the audit passes with a LAN HTTP advisory. The previous services remain installed and rollback was exercised during migration. Physical-display cut continuity awaits viewer confirmation.

Physical DRM/KMS output and hardware decoding through GStreamer on Pi 4, Pi 5, and ROCK Pi 4+ remain unqualified. Run the [hardware test plan](docs/hardware-test-plan.md) before making device-specific capacity claims.

## GitHub Actions status

The fresh Mosaivue repository is staged privately first. Its CI must pass before a public beta tag or release is published.
