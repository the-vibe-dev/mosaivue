# Public beta candidate: v0.1.0b1

This document records what is ready to stage privately and what remains unqualified before making the repository or a release public. The planned release tag is `v0.1.0b1`; the Python package version is `0.1.0b1`.

## Tested path

- Raspberry Pi 3B+, 32-bit Raspberry Pi OS Bullseye, OMXPlayer hardware overlays, 1920×1080 HDMI output.
- Seven simultaneous live camera tiles at one test site, including an RTSPS stream from a UniFi system. This does not establish a general seven-stream capacity for other codecs, bitrates, or camera mixes.
- Camera import from displaycameras, admin setup, camera previews, visual layout editing, renderer selection, service restart, and rollback were exercised on that site.
- The two-camera rotation tile now prepares its next OMXPlayer offscreen and cuts using D-Bus positioning and layer controls. On the test Pi, more than 20 switches completed with zero recovery restarts; physical-display continuity still needs viewer confirmation.
- Python unit, integration, API, and renderer tests plus frontend build, tests, and Chromium checks are part of the staging gate. The dated results are in [Build verification](../BUILD-VERIFICATION.md).

## Limits to state in a public beta

- The GStreamer renderer is implemented and tested in software, but physical output and hardware decoder performance have not been qualified on Pi 4, Pi 5, or ROCK Pi 4+.
- The ROCK Pi 4+ is an experimental candidate. It should select GStreamer; the OS image must provide a usable sink, decoder plugins, and device access. Run `mosaivue doctor --json` and a camera test on the board before claiming support.
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
