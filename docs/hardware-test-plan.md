# Hardware test plan

Run the legacy OMXPlayer path on a supported Pi 3 image and the GStreamer path
on Pi 4 and Pi 5 with current 64-bit Raspberry Pi OS Lite. The ROCK Pi 4B+
has passed the short synthetic GStreamer test in [beta notes](beta-release.md);
long-run and real-camera tests are still needed. The one-site Pi 3B+ result
also does not replace this matrix.

## Baseline

1. Fresh OS image and all updates.
2. Native Mosaivue install.
3. Record `mosaivue doctor --json`.
4. Confirm boot-to-camera-display without desktop/login cursor/blanking.
5. Confirm web and TUI setup.
6. Confirm the logo, SVG/ICO favicon, and installed-app icons load on desktop
   and mobile browsers.

## Matrix

For H.264 and H.265 where supported, test 4, 6, and 9 sources at 360p, 720p, and 1080p. Use both synthetic sources and real RTSP cameras. Stop combinations that overheat or clearly exceed hardware capacity.

## Dynamic behavior

- move and resize one slot while watching uninterrupted slots;
- replace one source;
- rotate one slot every 10 seconds for 30 minutes;
- run independent 10-second and 30-second groups;
- focus one camera and restore;
- disconnect one camera and reconnect it;
- freeze a stream without closing TCP;
- disconnect/reconnect Ethernet;
- kill renderer process;
- disconnect/reconnect HDMI;
- change resolution;
- reboot during normal operation;
- interrupt a draft save/import/upgrade.

## Acceptance evidence

Capture logs, metrics, exact versions, monitor mode, first-frame and switch timings, restart counts, and a video or screen capture proving unaffected slots remain live during one-slot changes.
