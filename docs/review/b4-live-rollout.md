# 0.1.0b4 controlled appliance rollout — November 13, 2026

This is an **in-progress observation**, not a completed 24-hour stability result or a release qualification. The initial Pi 3 and Ubuntu observations used source commit `affb95f` (source tarball SHA-256 `245fbd5107823581f42fcf89acfe1e5a51e592274e2ac9b924c1c671d72769d1`). The final Pi 3, Ubuntu and ROCK Pi observations all use the identical patched source archive from commit `f2579dc` (SHA-256 `b2a92160a10a8efe688ce319c049dc7b09a2215a3a705282b1f1948e8e18d43b`). All target archives were checksum-verified. Earlier observations and final windows remain separate.

Each appliance retains its prior release and a root-only snapshot with a SQLite-consistent database, configuration, state, systemd units and a guarded rollback script. Snapshot database integrity and script syntax passed. The ROCK Pi rollback was exercised after a failed first KMS trial. It exposed a snapshot-script defect: the restored database was root-owned and the services could not open it. Ownership was repaired, HTTP and 7/7 video recovered, and the corrected rollback script was installed in all three snapshots. The product installer's own snapshots remain available as well.

## Pi 3B+ / 32-bit Bullseye / OMXPlayer

The local source installer succeeded using the established Python 3.11.17 runtime, checksum-pinned ARM wheels and already-installed OS dependencies (`--skip-packages`). Native imports, encryption round trip, migration, decoder probe, service startup, HTTP health and configuration validation passed. The active seven-slot wall reached 7/7 LIVE with zero restarts and advancing rotation. A paused-group manual Next and Previous returned to the initial camera, with both switched states LIVE.

A controlled b4 reboot completed at **17:55:05 UTC**. Wi-Fi returned at the same address; both rfkill units remained masked. The web and renderer services started, and all seven streams returned LIVE with zero restarts. The initial postboot observer's first healthy sample was **17:56:54 UTC**; it stopped before 24 hours for source alignment. OMXPlayer's LIVE state is playback confirmation; the adapter does not measure decoded-frame advancement independently. Physical image quality still needs a person at the display.

After the ROCK Pi screen correction, the Pi 3 was upgraded to the same patched source. The prior b4 release and a matching root-only state snapshot remain available. A second controlled reboot returned Wi-Fi and both services, with rfkill units still masked, 7/7 OMX slots LIVE, zero restarts and rotation advancing. The final 24-hour observer's first healthy sample was **November 14 at 00:16:53 UTC**. Its earliest completion is **November 15 at 00:16:53 UTC**. Earlier Pi samples are retained but do not count toward this final-source window.

## Ubuntu / NVIDIA / GStreamer

The same source installer succeeded on Ubuntu with already-installed OS dependencies and `--no-start`. HTTP health and configuration validation passed. A temporary `fakesink` override ran the seven-slot wall while the monitor was absent. NVIDIA later reported its HDMI output and EDID through XRandR, though the proprietary driver's DRM sysfs connector still reported disconnected. The local HDMI watcher was corrected to use the NVIDIA X provider for physical connection detection.

An initial headless attempt exposed an appliance configuration error: the rotating SE camera used `unifi.local`, which the VM could not resolve. This caused rotation source failures and a renderer recycle. After backing up the b4 database, only that camera URL's hostname was changed to the reachable UniFi IP used by the Pi; its stream path was preserved. The repeat headless run reached 7/7 LIVE with advancing frames, rotation and zero restarts. Manual Next and Previous returned to the initial camera with both switched states LIVE. The headless observer stopped at HDMI handoff before 24 hours. Its 15 flagged one-minute samples were measurement errors: the rotating tile reset its decoded-frame counter on a successful switch while all seven slots remained LIVE and restart counts stayed at zero. The local observer now accounts for that counter reset.

The first physical `ximagesink` run stalled five fixed tiles with NVIDIA hardware decoding selected. A protected policy backup was retained; selecting the already-probed H.264 software decoder restored 7/7 LIVE, all seven frame counters advancing, rotation and zero restarts. The policy records that this choice was verified on the seven-slot physical wall. Follow-up source commit `61d5ee3` retains a verified software choice across installer re-probes and can fall back per slot after a hardware decoder produces no first frame. The initial physical run used the earlier source with the verified policy file.

The Ubuntu appliance was then upgraded to the same patched source as the ROCK Pi. Its installer re-probed the decoders and **retained `avdec_h264`** from the verified policy. The connected `ximagesink` wall returned to 7/7 LIVE with all seven frames advancing and zero restarts. The previous b4 release and a matching root-only snapshot remain available. The final physical observer's first healthy sample was **November 14 at 00:06:59 UTC**; its earliest completion is **November 15 at 00:06:59 UTC**. The earlier physical run is retained separately.

The watcher removed `fakesink` and started the initial **physical** observation at **23:30:29 UTC**. The user confirmed seven visible tiles and normal rotation on the monitor. Headless results are not counted as physical HDMI acceptance.

## ROCK Pi 4B+ / Debian 12 arm64 / GStreamer KMS

The ROCK Pi returned online with b1, HDMI connected, 7/7 LIVE streams and advancing frames. Its CRTC was already 1920×1080, but the wall's KMS video plane was centered at **1920×810+0+135**. An initial b4 change disabled `kmssink` aspect preservation; a controlled scanout test showed this Rockchip driver then removed the video plane. The appliance was rolled back to b1, including its configuration and database, before another trial.

A second controlled KMS test showed that `kmssink fullscreen=true` produces a **1920×1080+0+0** plane with aspect preservation retained. Commit `f2579dc` applies that setting at every renderer start. The patched source installed successfully, and a controlled reboot at **23:55:58 UTC** returned to a full 1920×1080 plane, 7/7 LIVE streams, advancing frames and working manual Next/Previous. The user confirmed that the wall fills the monitor. One stream restart was recorded during cold start; whether it grows is under observation. The full-plane observer's first healthy sample was **23:58:41 UTC**, with an earliest 24-hour completion of **November 14 at 23:58:41 UTC**. It checks the KMS plane geometry as well as frame advancement.

## Pending

- Complete the final-source Pi postboot, Ubuntu physical HDMI and ROCK Pi postboot 24-hour windows and review per-slot restarts, rotation switches, frame advancement and ROCK Pi plane geometry. The windows overlap; each platform still needs its own completed result.
- PTZ and presets are unimplemented in b4 and untested on a physical PTZ camera.
- The controlled rollout used `--skip-packages`; a clean one-click install remains separate release acceptance work. The ROCK Pi manual rollback was exercised; other rollback paths remain unexercised.

The detailed sample logs, watcher events, guarded rollback locations and operator commands are retained in the private rollout workspace. No camera URL or credential is recorded in the periodic samples.
