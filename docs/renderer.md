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
Input selectors do not synchronize inactive pads to the active stream. This
lets standby RTSP decoders keep consuming frames when the displayed source's
clock pauses; source queues drop old buffers when downstream is slower.
Selector input pads return `OK` while inactive so that a camera does not
receive a `NOT_LINKED` flow result merely because another camera is visible.
Fixed and rotating slots both select only the video track before RTSP setup.
The first layout is linked before the pipeline enters `PLAYING`. This is
required for reliable startup with `kmssink` on the tested ROCK Pi 4B+.
At installation, Mosaivue probes the installed H.264, H.265, and JPEG decoders
as the service account and saves its per-codec choices in
`/var/lib/mosaivue/decoder-policy.json`. Fixed tiles prefer a working hardware
decoder. Rotating tiles prefer a working software decoder; this avoided the
long-running rotation stalls observed with Rockchip MPP and NVIDIA hardware
decode on the tested walls. GStreamer is instructed to use the saved decoder,
and each stream reports the decoder it actually loaded. A software rotation
decoder can increase CPU use. `MOSAIVUE_ROTATION_SOFTWARE_DECODE=1` remains an
emergency override if an older installation has no saved policy. A new install
selects software rotation automatically when its probe passes.

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
After two missed scheduled cuts, a rotating tile reports `DEGRADED` even if
its currently displayed camera still decodes. The detail names the missed
changes; a successful cut clears it.

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

GStreamer also honors `preconnect=next`. It waits for a decoded frame before
activating the prepared selector pad. In a two-camera group, both source
branches stay connected and the selector alternates between them, so a cut
does not tear down the previous decoder. This uses one extra decoder for that
rotation slot. If the candidate has not produced a recent frame, the current
camera stays selected and the controller retries at the next interval.
When the active branch fails, the GStreamer bus asks the controller to select
the warm alternate. RTSP teardown in the bus callback can block the shared
video loop, so a rotation branch is kept in place if its alternate is not yet
ready; the controller retries when fresh frames arrive.
Failed prepared and fixed sources reset on a GStreamer worker thread. Their
existing selector branches remain in the pipeline while RTSP reconnects, so
the other tiles continue to render. A rotation candidate is never selected
until it has produced a recent decoded frame.
If a source reset blocks or remains without frames, the renderer opens a new
source branch and ignores late messages from the retired branch. It stops the
old source and queue on a worker thread, then releases their selector pad and
removes them from the pipeline. At most two branches may be pending retirement
per slot; recovery retries once they have been released.
If both pending retirements remain blocked, the renderer keeps other live tiles
visible. A rotation tile stalled for two minutes can trigger a whole-renderer
restart, limited by a longer cooldown. A wall with no recently decoded tiles
can also restart after its shorter cooldown.
If repeated RTSP `not-negotiated` errors keep a rotation tile unhealthy for two
minutes, the same longer-cooldown restart applies even when sporadic frames
keep resetting its no-frame timer. A quiet minute resets the error streak.
For a mixed-resolution rotation group, `MOSAIVUE_ROTATION_NORMALIZE=640x360`
converts each decoded rotation branch to 640×360 I420 at 15 fps before the
input selector. This avoids changing the selector's raw caps at each cut. Set
the dimensions to the lower-resolution camera's native aspect ratio when all
group members share that ratio; a different target aspect can alter the
appearance of `cover` and `contain`. The installer selects 640×360 on Rockchip
systems with an MPP decoder, KMS sink, and normalization plugins. Existing
installer targets are retained on upgrade. Use `--rotation-normalize off` to
disable it or `--rotation-normalize WIDTHxHEIGHT` to choose a target matching
the camera group's aspect ratio. Renderer status reports the target and the
actual active, prepared, and selector caps. On a negotiation error, the
renderer logs those caps at most once per minute without camera URLs.
The black placeholder has its own source branch. Its negotiation messages are
ignored by camera recovery, since a placeholder error does not establish that
the RTSP camera failed.
If both rotation sources stop producing frames, the slot reports STALLED. The
renderer selects the live placeholder so its input selector continues advancing
while the prepared source reconnects. It gives the prepared source fifteen
seconds to recover. If other tiles are still live, they keep running while the
rotation slot is stalled. If the whole wall stops decoding, systemd may restart
the renderer after the cooldown check. The compositor ignores pads that have
not yet produced a buffer and reserves latency for RTSP inputs added later.
On ROCK Pi, `scripts/rockpi-smoke.py --streams 2 --seconds 15 --sink fakesink --recovery`
exercises both recovery paths with local test streams while the normal HDMI
wall stays running.

RTSPS streams use the system TLS trust database by default. For a camera server
with a private certificate authority, set `rtsp_tls_ca_file` in
`/etc/mosaivue/config.json` to an absolute path containing PEM-encoded trusted
certificate anchors readable by the `mosaivue` service account. GStreamer then
uses that CA file for RTSPS sources while retaining certificate validation.
The file supplies the trust anchors for all GStreamer RTSPS sources on that
appliance, so include every required camera-server authority in it.
The RTSPS URL hostname must match the certificate's name. Restart the renderer
after changing the CA file or this setting.

## Native backend decision

A custom FFmpeg/DRM/DMA-BUF renderer is not included because this environment cannot prove that the GStreamer implementation fails the functional or performance requirements. The abstraction preserves that option. A native component should be added only with benchmark evidence and must use current APIs.
