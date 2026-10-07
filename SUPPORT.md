# Support

For operational problems, start with:

```bash
mosaivue status
mosaivue doctor --json
mosaivue config validate --json
mosaivue security audit --json
mosaivue support-bundle
```

Then inspect:

```bash
journalctl -u mosaivue-renderer.service --since '1 hour ago'
journalctl -u mosaivue-server.service --since '1 hour ago'
```

When opening an issue, include the Mosaivue version, Pi/CPU model, OS release, kernel, output resolution, renderer backend and sink, codec/profile used, stream count, exact reproduction steps, and sanitized logs. Use the matching issue template.

Do not include RTSP passwords, administrator cookies, the master key, camera account secrets, or unredacted configuration files.
