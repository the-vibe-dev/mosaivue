# Performance and qualification

Mosaivue intentionally does not publish invented stream limits. Decoder availability differs across Pi generations, codecs, OS images, camera profiles, and sinks.

## Synthetic benchmark

```bash
mosaivue benchmark --streams 6 --width 1920 --height 1080 --duration 30 --json
```

The benchmark composes generated sources, measures process CPU and memory, counts delivered frames and drops where available, and records the selected backend/sink. It tests composition overhead without camera/network variables.

## Camera benchmark

Use real saved cameras during hardware qualification. Record:

- platform, RAM, OS, kernel, firmware, GStreamer version;
- output connector, resolution, refresh, and sink;
- stream count, codec, source resolution/FPS/bitrate;
- decoder element chosen;
- CPU, memory, temperature, FPS, drops;
- first-frame time, reconnect time, source replacement latency, rotation latency;
- whether fixed branches remained uninterrupted.

## Profiles

`performance`, `balanced`, `quality`, `low-latency`, and `custom` are policy presets, not hard promises. Automatic source selection should be paired with appropriate substreams.

## Results

One Pi 3B+ beta site running 32-bit Bullseye and OMXPlayer maintained seven
live camera tiles at a 1920×1080 HDMI output. A two-camera rotation handoff
was measured at about 1.7 seconds to the new player's confirmed playback,
while the old image remained visible. This site result does not predict a
general stream limit: camera codecs, profiles, bitrates, and Pi firmware may
differ. The build environment itself has no Pi display device. Use the
[hardware test plan](hardware-test-plan.md) and record measured Pi 4, Pi 5,
GStreamer, and ROCK Pi 4+ results before making broader claims.
