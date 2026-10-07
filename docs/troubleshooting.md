# Troubleshooting

## Start with diagnostics

```bash
mosaivue status
mosaivue doctor --json
mosaivue config validate --json
journalctl -u mosaivue-renderer.service --since '30 minutes ago'
```

## Web UI unavailable

Check `mosaivue-server.service`, the configured bind address/port, firewall, and whether the initial setup token still exists. The health endpoint is `/healthz`.

## Black display

Confirm the output connector and GStreamer sink in `mosaivue doctor`. Check service membership in `video` and `render`, access to `/dev/dri`, HDMI mode, and renderer logs. Temporarily select a GL/X11/Wayland sink only when that environment exists.

## One camera offline

Use **Test stream**, verify the profile URL from the appliance, try TCP transport, inspect the camera-specific log filter, and confirm credentials. Mosaivue keeps the tile in place and reconnects only that branch.

## High CPU

Add lower-resolution H.264 substreams, enable automatic profile selection, reduce output scaling, check whether hardware decoder elements were detected, and run `mosaivue benchmark`. Do not send 4K main streams to thumbnail tiles.

## Database locked

SQLite uses WAL and a busy timeout. Check disk health, free space, ownership, duplicate service processes, and long-running external access to `mosaivue.db`. Do not edit the live database with a GUI.

## Setup token lost

Before any administrator exists, stop the server and run a short Python command as root to call `generate_setup_token()`, or reinstall without deleting configuration. Once setup is complete, token login is disabled.
