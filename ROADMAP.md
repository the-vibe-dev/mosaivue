# Roadmap

## 0.1 release qualification

- Complete the Pi 3, Pi 4, and Pi 5 hardware matrix.
- Record H.264/H.265 behavior for 4, 6, and 9 streams at 360p, 720p, and 1080p where practical.
- Validate `kmssink`, `glimagesink`, Wayland, and X11 selection on current Raspberry Pi OS.
- Test HDMI disconnect/reconnect, resolution changes, network loss, frozen RTP timestamps, renderer crashes, and power interruption during save.
- Validate a real `displaycameras` migration from multiple layout files.
- Complete an external security and license review.

## 0.2

- ONVIF discovery plugin and credential-safe import.
- Optional WebRTC preview service.
- GStreamer preconnect and broader rotation-order prediction where hardware capacity permits.
- Multi-display foundations and per-output active layouts.
- MQTT and Home Assistant integration plugin.
- Event-driven temporary focus rules.

## 1.0

- Published, reproducible Pi 4/5 qualification results.
- Signed release artifacts and documented rollback support.
- Stable plugin API and compatibility policy.
- Accessibility and internationalization review.

## Later

- Multi-monitor layouts, picture-in-picture, HDMI CEC, Stream Deck, GPIO, motion and doorbell event integrations, custom overlay slots, and optional native DMA-BUF renderer only if benchmarks justify it.
