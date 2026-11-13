# Performance and qualification

Mosaivue has no universal camera-count guarantee. Decoder availability and load depend on the board, OS, codec, source dimensions/FPS/bitrate, output, sink, rotations and browser preview activity. The **0.1.0b3 review candidate** has software regression coverage; its changed runtime paths require hardware qualification.

## GStreamer compositor frame rate

`MOSAIVUE_OUTPUT_FPS` configures GStreamer's compositor output caps:

| Value | Behavior |
|---|---|
| Unset | Retain the existing **5 FPS** default. |
| Integer **1–60** | Request that compositor output rate. |
| Other value | Reject it with a configuration error. |

This is distinct from camera capture FPS, source bitrate and the HDMI monitor's refresh rate. Selecting 30 FPS is a request, not evidence that a particular Pi/GPU can sustain 30 decoded/composed frames per second. OMXPlayer output is not controlled by this GStreamer setting.

For a systemd-managed appliance, open a renderer override:

```bash
sudo systemctl edit mosaivue-renderer.service
```

An example override is:

```ini
[Service]
Environment="MOSAIVUE_OUTPUT_FPS=15"
```

Then reload and restart during a suitable interruption window:

```bash
sudo systemctl daemon-reload
sudo systemctl restart mosaivue-renderer.service
sudo -u mosaivue mosaivue renderer status --json
```

Inspect the GStreamer status `output.fps` and measure real playback/resource behavior. The example is a way to test a value, not a recommended rate for every platform. Removing this environment assignment restores the 5 FPS default. Preserve custom service overrides separately when backing up the appliance.

## Source profiles and resource use

Provide lower-resolution substreams so small tiles need not decode full-resolution sources. Automatic selection uses profile metadata; it does not transcode cameras or guarantee codec support. Focus and rotation can change which sources/decoders are active. Preloading adds work beyond the visible tiles.

The stored `profile` label (`balanced`, `performance`, `quality`, `low-latency` or `custom`) is not evidence that a complete tuning preset has been applied. Verify actual source selection, decoder, sink, latency setting and compositor rate. Optimization recommendations are advisory.

JPEG previews use a separate capture path and can add decoder/CPU load. The candidate does not provide an appliance-wide preview queue or cache; include simultaneous preview activity in capacity testing on smaller boards.

## Synthetic benchmark

```bash
sudo -u mosaivue mosaivue benchmark --streams 6 --width 1920 --height 1080 --duration 30 --json
```

The benchmark composes generated video sources and reports the available process/frame measurements. It measures a synthetic pipeline without camera authentication, RTSP networking, camera codecs or the full recovery workload. Its result does not establish that the same number of real cameras will run reliably, or that the configured wall frame rate is sustained.

## Camera and hardware acceptance record

Record the exact board, RAM, OS image, kernel/firmware, GStreamer/OMX version, decoder elements, output connector/resolution/refresh, sink and compositor rate. For each stream, include codec, dimensions, FPS, bitrate, profile, transport and latency preset.

Measure CPU, memory, temperature, advancing decoded frames, delivered FPS/drops where observable, decoded first-frame time, reconnect time, source replacement/rotation latency and fixed-tile continuity. **Test stream** reports discovery response time; its unmeasured first-frame field is null. Do not substitute a process-running or LIVE status for observed frame advancement.

Qualification should include cold boot, mixed aspect ratios, small/edge tiles, two independent rotation slots sharing a group, Skip/Hold failures, camera and network loss/recovery, HDMI changes, focus/timed restore and schedules across midnight. Reapply a layout after changing camera/group configuration before assessing the result. See the [hardware test plan](hardware-test-plan.md).

A 24-hour initial run followed by a longer 72-hour candidate soak is a proposed acceptance target, not a completed result. Preserve resource trends, interruptions and exact configuration with the findings.

## Historical evidence and candidate limits

Earlier site results for Pi 3B+/OMXPlayer, ROCK Pi 4B+/GStreamer and Ubuntu are described in the [beta notes](beta-release.md). They remain evidence for those earlier builds and source mixes. This review did not run the new candidate on a physical Pi, ROCK Pi, GPU display or live private camera; Pi 4/5 output and broader stream mixes remain unqualified.

The [review report](review/report.md) separates software verification from outstanding browser, installer and hardware acceptance. Use its [validation record](review/validation.md) for the actual completed checks and environment limitations.
