# 0.1.0b4 controlled appliance rollout — November 13, 2026

This is an **in-progress observation**, not a completed 24-hour stability result or a release qualification. The deployed source is commit `affb95f6522d62e6f16685535ab7835df6c68e16`; the source tarball SHA-256 is `245fbd5107823581f42fcf89acfe1e5a51e592274e2ac9b924c1c671d72769d1`. Both target archives were checksum-verified. Each appliance retains its prior b3 release and a root-only snapshot with a SQLite-consistent database, configuration, state, systemd units and a guarded rollback script. Snapshot database integrity and rollback-script syntax passed. The rollback scripts have **not** been executed against b4; the installer also saved its own pre-migration snapshots.

## Pi 3B+ / 32-bit Bullseye / OMXPlayer

The local source installer succeeded using the established Python 3.11.17 runtime, checksum-pinned ARM wheels and already-installed OS dependencies (`--skip-packages`). Native imports, encryption round trip, migration, decoder probe, service startup, HTTP health and configuration validation passed. The active seven-slot wall reached 7/7 LIVE with zero restarts and advancing rotation. A paused-group manual Next and Previous returned to the initial camera, with both switched states LIVE.

A controlled b4 reboot completed at **17:55:05 UTC**. Wi-Fi returned at the same address; both rfkill units remained masked. The web and renderer services started, and all seven streams returned LIVE with zero restarts. The fresh postboot 24-hour observer's first healthy sample was **17:56:54 UTC**. Its earliest completion is **November 14 at 17:56:54 UTC**. OMXPlayer's LIVE state is playback confirmation; the adapter does not measure decoded-frame advancement independently. Physical image quality still needs a person at the display.

## Ubuntu / NVIDIA / GStreamer

The same source installer succeeded on Ubuntu with already-installed OS dependencies and `--no-start`. HTTP health and configuration validation passed. Every passed-through NVIDIA display connector was disconnected, so physical HDMI output is **untested**. The renderer is disabled at boot until a monitor is connected.

A temporary `fakesink` service override runs the full seven-slot wall headlessly. An initial attempt exposed an appliance configuration error: the rotating SE camera used `unifi.local`, which the VM could not resolve. This caused rotation source failures and a renderer recycle. After backing up the b4 database, only that camera URL's hostname was changed to the same reachable UniFi IP used by the Pi; its stream path was preserved. The repeat run reached 7/7 LIVE, all seven decoded-frame counters advanced across two samples, rotation switched, and restart count was zero. Manual Next and Previous also returned to the initial camera with both switched states LIVE.

The Ubuntu headless observer's first healthy sample was **17:51:07 UTC**; its earliest 24-hour completion is **November 14 at 17:51:07 UTC** if no display is attached first. A separate HDMI watcher waits for a stable connector, stops the headless observer, removes the `fakesink` override, enables and restarts the configured `ximagesink` renderer, then starts a fresh **physical** 24-hour observer only after seven streams are LIVE and all seven frame counters advance. The headless result cannot be counted as HDMI acceptance.

## Pending

- Complete each uninterrupted observation window and review per-slot restarts, rotation switches and frame advancement. The Pi postboot and Ubuntu headless windows overlap; they are distinct platform results.
- Attach a monitor to the Ubuntu passed-through GPU and complete the separate physical-output check and soak.
- The ROCK Pi remains powered down/unreachable, so b4 has not been deployed or tested there.
- PTZ and presets are unimplemented in b4 and untested on a physical PTZ camera.
- The controlled rollout used `--skip-packages`; a clean one-click install and a deliberate failure/rollback rehearsal remain separate release acceptance work.

The detailed sample logs, watcher events, guarded rollback locations and operator commands are retained in the private rollout workspace. No camera URL or credential is recorded in the periodic samples.
