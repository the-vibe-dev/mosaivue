# Migrating from displaycameras

Mosaivue searches:

```text
/etc/displaycameras/displaycameras.conf
/etc/displaycameras/layout.conf.default
/etc/displaycameras/layout.conf.*
```

The parser understands common shell variable and array forms. It looks for camera name arrays, RTSP URL arrays, window rectangles, and resolution hints. Credentials embedded in imported URLs are separated and encrypted during creation.

Always dry-run first:

```bash
mosaivue migrate displaycameras --dry-run --json
```

Review camera/layout counts and warnings, then apply without `--dry-run`. The importer does not modify or delete original files.

Absolute rectangles are divided by the associated output resolution and clamped into normalized geometry. Unrecognized rotation syntax is reported rather than silently guessed.
