# Renderer

## Selected backend

The primary implementation is GStreamer through PyGObject. GStreamer was selected because it provides RTSP source management, RTP depayloading, decoder selection, queues, scaling, composition, and multiple Linux output sinks inside one managed native pipeline. Compositor pads directly expose position, size, alpha, and z-order, which maps to Mosaivue's normalized slot model.

On older Raspberry Pi images with OMXPlayer, Mosaivue can use the hardware overlay
backend instead. It runs one OMXPlayer process per slot and is selected by
`"renderer_backend": "omxplayer"` in `/etc/mosaivue/config.json`. `auto` prefers
OMXPlayer on Pi 1, 2, 3, and Zero when it is installed; other systems use
GStreamer. Changes to a slot's position or camera restart only that player.
OMXPlayer does not provide Mosaivue's crop, opacity, label overlay, or snapshot
features. `contain` maps to letterbox, `cover` to fill/crop, and `stretch` to
distorted fill. `native` uses letterbox because OMXPlayer has no original-pixel
mode in a fixed tile. It uses the HDMI mode already configured on the Pi.
For a rotation switch, the next OMXPlayer can start offscreen and below the
current camera's overlay. Once playback is confirmed, Mosaivue positions and
raises the new overlay, then stops the old player. This uses at most one extra
decoder. If preparation fails, the current camera remains visible.

The first-run setup and the Dashboard and Renderer pages offer the available
backends. Their choice is stored in `/var/lib/mosaivue/renderer-backend.json`,
which overrides `/etc/mosaivue/config.json`; `MOSAIVUE_RENDERER_BACKEND` has final
priority. A choice made in the web interface restarts only the renderer service.

## Pipeline topology

Conceptually:

```text
rtspsrc → depay/parser/decoder → queue → convert/scale/crop → selector ┐
placeholder source ────────────────────────────────────────────────────┤
                                                                      ├→ compositor → output sink
(other independent stream branches) ──────────────────────────────────┘
```

Each slot is represented by an independent branch. The compositor and output sink are shared. A failed source can switch to its placeholder, reconnect, and return without rebuilding unrelated branches.

## Sink selection

`auto` evaluates the Pi model and installed players before GStreamer plugins.
GStreamer sink candidates include KMS/DRM, GL, Wayland, X11, and framebuffer.
`mosaivue doctor` records available elements rather than assuming they exist.

Explicit configuration:

```json
{
  "renderer_backend": "gstreamer",
  "renderer_sink": "kmssink"
}
```

## Health and recovery

States are `CONNECTING`, `LIVE`, `DEGRADED`, `STALLED`, `RECONNECTING`, `OFFLINE`, and `DISABLED`.

The backend watches bus errors, decoded buffers, and last-frame time. Recovery escalates from source reconnect to branch recreation; full pipeline restart is a last resort. Backoff grows exponentially and resets after recovery.

Health reports `restart_count` for recovery or manual restarts and `switch_count`
for planned camera changes. These counters begin at zero when the renderer
service starts. OMXPlayer logs whether an automatic restart followed a player
exit or 30 seconds without confirmed playback.

## Latency presets

- `ultra-low`: smallest queue/jitter allowance and aggressive dropping.
- `low`: reliable LAN viewing default.
- `normal`: more jitter tolerance.
- `stable`: larger buffering for unreliable links.

Transport is `auto`, `tcp`, or `udp`; TCP is the default for generic surveillance cameras because it avoids visible RTP loss on typical LANs, while users can override it.

## Rotation

The controller replaces only the assigned rotation slot. Fixed slots retain
their branches. OMXPlayer `preconnect=next` prepares one next sequential or
reverse camera during the interval; `off` prepares it at switch time. Random
and weighted groups prepare at switch time because their next camera is not
predictable.

## Native backend decision

A custom FFmpeg/DRM/DMA-BUF renderer is not included because this environment cannot prove that the GStreamer implementation fails the functional or performance requirements. The abstraction preserves that option. A native component should be added only with benchmark evidence and must use current APIs.
