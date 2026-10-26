# Cameras and stream profiles

A camera is entered once and reused across layouts and rotation groups. Its stream profiles may represent main, medium, and low-resolution substreams.

## URL handling

Mosaivue accepts `rtsp://` and `rtsps://` URLs. Embedded userinfo is extracted during save, encrypted separately, and removed from the stored URL. API responses return the URL without credentials and expose only `has_password`.

Use a read-only camera/NVR account when possible.

## Profiles

For each profile, record known codec, width, height, FPS, bitrate, transport, and latency preset. In automatic mode the renderer chooses the smallest known source that is large enough for the tile. Manual mode uses the selected profile.

Example:

```text
Driveway
  Main    3840×2160 H.265
  Medium  1920×1080 H.264
  Low      640×360  H.264
```

A 320×180 tile should normally choose `Low`; fullscreen may choose `Main` or `Medium` according to available decode support and priority.

## Test stream

The test operation uses GStreamer discovery when available and reports connection result, response time, codec, dimensions, framerate, transport, selected decoder, approximate bitrate, and time to first frame. Preview captures are low-rate JPEGs and are separate from HDMI rendering.

## RTSPS certificate trust

RTSPS camera URLs must use the port and hostname supplied by the camera server.
If its certificate is signed by a private CA or is self-signed, put its PEM
certificate in a file readable by the `mosaivue` service account and set
`rtsp_tls_ca_file` in `/etc/mosaivue/config.json` to that absolute path. The
hostname in the URL must match the certificate. Mosaivue validates RTSPS
certificates; the CA file adds trust for a specific camera server without
turning validation off for other connections.
