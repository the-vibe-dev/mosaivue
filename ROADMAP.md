# Roadmap

## 0.1.0b3 review candidate — 2026-11-13

Implemented in the candidate: known-endpoint ONVIF Media1 inspection/import, a schedules screen, camera/layout duplication and filtering, uniform layout grids, configurable GStreamer compositor FPS, and corrections to restore integrity, profile identity, renderer control, scheduling, authentication and installation boundaries. See the [changelog](CHANGELOG.md) and [review report](docs/review/report.md) for the exact scope.

These are candidate implementations with software evidence. Publishing a release, qualifying physical appliances and completing browser/installer acceptance remain separate work.

## Next: qualify and finish the single-appliance experience

- Run the supplied browser workflows on a host that can launch Chromium, covering desktop and mobile behavior, validation/cancel paths, dirty layouts, rotation, schedules and ONVIF import.
- Complete install, failed-update recovery and uninstall trials on representative supported systemd hosts; retain and verify matching database/key/settings snapshots.
- Run Pi 3/4/5, ROCK Pi and Linux GPU camera/output qualification. Record codecs, actual decode paths, compositor rates, source mixes and long-duration results rather than a universal stream limit.
- Test network/HDMI loss, stalled frame delivery, cold startup, mixed aspect ratios, focus/restore and camera changes during an active wall.
- Expose pending camera/group changes and a clear apply action, then define a reliable runtime reload contract.
- Finish capability-aware reporting for output targeting/portrait, audio, synchronized rotation and group-level failure placeholders. Stored fields must not be presented as working features before their runtime behavior is implemented and qualified.
- Validate application settings with a typed, backwards-compatible contract; add preview concurrency/cache limits.
- Add a versioned appliance-settings backup section and restore preview. Current backups cover application configuration and optional camera credentials, not a full appliance recovery image.
- Encrypt credential-bearing URI components or complete stream URIs, including vendor tokens in opaque paths.

## Next integration and camera-control work

- Qualify the existing ONVIF Media1 importer across vendors and authentication variants.
- Add explicit WS-Discovery, then Media2 and PTZ/presets as separately tested capabilities. Keep manual RTSP setup available.
- Develop multi-output lifecycle support and per-output active layouts before promising multi-monitor or synchronized display behavior.
- Add optional local MSE/WebRTC viewing through a restreaming path that avoids unnecessary duplicate upstream connections.
- Add scoped, revocable integration credentials before expanding Home Assistant/MQTT and event-triggered focus automation.

## Shared deployments and observability

- Add account management and distinct viewer/operator/admin roles.
- Populate a bounded, secret-free audit trail with actor, resource and action.
- Record health history, last-frame age, outage duration, recovery reasons and metrics export. Distinguish decoded-frame health from a running player process.
- Introduce fleet configuration/health only after single-appliance operation is reliable; a wall should continue working when a controller is unavailable.

## Stable-release requirements

- Publish reproducible qualification records and camera/backend compatibility results, including Pi 4/5.
- Complete external security/license, accessibility and internationalization reviews.
- Provide signed release artifacts, an exercised rollback procedure and a stable compatibility policy.
- Define a supported plugin API before relying on third-party integrations for core operation.

## Later candidates

HDMI CEC, Stream Deck, GPIO, motion/doorbell rules, image/overlay tiles and optional native DMA-BUF rendering are candidates for measured follow-up work. Their inclusion depends on user demand, runtime feasibility and qualification results; this roadmap is not a claim that they already ship.
