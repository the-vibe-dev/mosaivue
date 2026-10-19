# Public beta candidate: v0.1.0b1

This document records what is ready to stage privately and what remains unqualified before making the repository or a release public. The planned release tag is `v0.1.0b1`; the Python package version is `0.1.0b1`.

## Tested path

- Raspberry Pi 3B+, 32-bit Raspberry Pi OS Bullseye, OMXPlayer hardware overlays, 1920×1080 HDMI output.
- Seven simultaneous live camera tiles at one test site, including an RTSPS stream from a UniFi system. This does not establish a general seven-stream capacity for other codecs, bitrates, or camera mixes.
- Camera import from displaycameras, admin setup, camera previews, visual layout editing, renderer selection, service restart, and rollback were exercised on that site.
- The two-camera rotation tile now prepares its next OMXPlayer offscreen and cuts using D-Bus positioning and layer controls. On the test Pi, more than 20 switches completed with zero recovery restarts; physical-display continuity still needs viewer confirmation.
- A ROCK Pi 4B+ on Debian 12 arm64 with Rockchip MPP and `kmssink` passed a 15-second, four-source local H.264 RTSP test at 1280×720. All four branches remained LIVE with zero restarts, and a source replacement succeeded while the other branches continued. One real camera also ran at 1920×1080 with increasing frames and zero restarts. This is an initial hardware smoke test, not a long-run or real-camera capacity result.
- The ROCK Pi 4B+ later ran the imported seven-tile 1920×1080 wall with its two-camera GStreamer rotation. The rotation branches stayed connected between cuts; the site viewer confirmed that both cameras appeared on HDMI. The two rotating UniFi profiles used `stable` RTSP latency. Later source errors exposed blocking recovery and a standby source that did not reconnect; both paths now reset sources without blocking the shared video loop. Longer running time remains to be tested.
- Python unit, integration, API, and renderer tests plus frontend build, tests, and Chromium checks are part of the staging gate. The dated results are in [Build verification](../BUILD-VERIFICATION.md).

## Limits to state in a public beta

- Physical output and hardware decoder performance on Raspberry Pi 4 and Pi 5 remain unqualified.
- ROCK Pi 4B+ has a short KMS/MPP smoke result and a brief seven-tile real-camera run with viewer confirmation of both rotation cameras. Longer real-camera, boot, and rotation-timing tests remain. The site's camera gateway produced inconsistent frames at low RTSP latency; `stable` was needed for the rotating sources.
- Legacy OMXPlayer lacks exact crop, opacity, label overlay, snapshot, and native pixel-size behavior. It uses letterbox for the `native` aspect choice.
- OMXPlayer `preconnect=next` uses one bounded extra decoder for sequential or reverse groups. Random and weighted groups prepare at switch time. There is no `all` preload mode.
- LAN HTTP, local access to the `mosaivue` service account, and legacy OMXPlayer process arguments are trust boundaries. See [security design](security.md).
- The beta has no universal stream-count or latency guarantee. Record camera codec, resolution, frame rate, decoder, sink, CPU, and temperature for each hardware claim.

## Private staging and publication gate

1. Keep the staging repository private while reviewing source, screenshots, license inventory, generated OpenAPI, and built archives for site credentials or private deployment files.
2. Confirm the Python package version, Git tag, changelog, source archive name, and GitHub prerelease flag agree.
3. Run CI, frontend browser checks, `scripts/check_release.py`, and a clean source-archive install test. Repeat the hardware matrix before broader platform claims.
4. Review the [security policy](../SECURITY.md) and [third-party notices](../THIRD_PARTY_NOTICES.md), especially the external OMXPlayer and FFmpeg dependencies.
5. Publish a public repository or prerelease only after the staged commit and artifacts have been reviewed. The release workflow creates a prerelease for beta tags; staging a branch does not create a tag or release.

The new Mosaivue repository is staged privately first. Its CI must pass before public publication; local checks and Pi results are recorded in [Build verification](../BUILD-VERIFICATION.md).

## Feedback to request from beta users

Ask for board model, OS and kernel, display mode, renderer backend, codec/profile mix, `mosaivue doctor --json`, and sanitized logs. Never request camera passwords, complete backups, or raw RTSP URLs in a public issue.
