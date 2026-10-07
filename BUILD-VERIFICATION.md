# Build verification — Mosaivue 0.1.0b1

Verification performed on 2026-10-07 (America/New_York) for the Mosaivue private beta staging candidate.

## Completed checks

- Python unit, frontend-static, renderer, and integration suite: **30 passed**.
- Frontend TypeScript type check, production build, and Node test suite: **passed** (3 Node tests).
- Python bytecode compilation, shell syntax checks, and `scripts/check_release.py`: **passed**.
- Generated OpenAPI snapshot: **51 paths**, version **0.1.0b1**.
- Source archive `mosaivue-0.1.0b1-source.tar.gz` built from the staged Git file set and its SHA-256 sidecar verified. The Pi deployment archive was `6ebdc9e7ad4f60cf84e9d8b9455d795eabda8083c2919fb55e002d5051ca4a6f`; the installer restart fix was then copied into the installed release and committed to private staging.
- The Pi installer built and installed a Mosaivue wheel with Python 3.11 on 32-bit Bullseye. A pinned SQLAlchemy wheel and target-built cffi avoided binary incompatibilities.
- Gitleaks directory scan: **no findings**.
- Authenticated Chromium checks on the Pi loaded the supplied logo, the OMX-specific display message, rotation cards without a transition setting, and the corrected security audit, with no page errors.
- Local Chromium editor checks placed a camera by click, displayed eight resize handles, resized a tile, replaced its camera, and reflowed a seven-tile template down to five.

## Hardware evidence and remaining qualification

One Raspberry Pi 3B+ running 32-bit Bullseye is running Mosaivue with seven live camera tiles through OMXPlayer at 1920×1080. After restarting into the final runtime, the rotating tile completed seven observed cuts with zero recovery restarts; each logged a preconnected cut of 250–325 ms and no rotation errors. The migrated key, config, and database have expected owner and mode checks; the audit passes with a LAN HTTP advisory. The previous services and the previous Mosaivue release remain installed, and rollback was exercised during migration. Physical-display cut continuity awaits viewer confirmation.

Physical DRM/KMS output and hardware decoding through GStreamer on Pi 4, Pi 5, and ROCK Pi 4+ remain unqualified. Run the [hardware test plan](docs/hardware-test-plan.md) before making device-specific capacity claims.

## GitHub Actions status

The fresh Mosaivue repository is staged privately at `the-vibe-dev/mosaivue`. Its first CI run failed before any runner was assigned: backend and frontend jobs have zero steps and no logs. Recent runs in the previous repository have the same signature. This is an Actions runner/account issue to resolve before a public beta tag or release is published; it is not a passing CI result.
