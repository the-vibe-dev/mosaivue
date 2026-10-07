# Architecture

## Goals

Mosaivue is an appliance, not a collection of player processes. The architecture separates persistent configuration and administration from the latency-sensitive renderer while keeping all data local.

## Process model

```text
Browser / CLI / TUI
        │
        ▼
mosaivue-server.service
FastAPI + auth + SQLite + scheduling + backup
        │ Unix-domain JSON RPC
        ▼
mosaivue-renderer.service
RendererController + GStreamer or OMXPlayer backend
        │
        ▼
GStreamer compositor or legacy Pi HDMI hardware overlays
```

The API remains available if the renderer crashes. Systemd restarts the renderer independently. The renderer reads active configuration through the same SQLAlchemy model and accepts a small, local-only RPC command set.

## Domain model

- **Camera**: reusable object with metadata, tags, one credential reference, and one or more stream profiles.
- **StreamProfile**: RTSP URL without userinfo, transport, known codec/resolution/FPS/bitrate, latency preset, and priority.
- **Layout**: reusable display arrangement with an active current revision.
- **LayoutRevision**: immutable JSON snapshot of normalized geometry and slot behavior.
- **Slot**: fixed camera, manual camera, rotation group, or empty region.
- **RotationGroup**: camera entries, interval, ordering mode, preload policy, and failure behavior.
- **DisplayProfile**: connector, resolution, refresh, rotation, and blanking policy.
- **Schedule**: day/time rule that activates a layout.

## Configuration changes

The browser edits a draft in memory. Saving creates a new revision. Applying validates references and capabilities, sends the chosen revision to the renderer, and only marks it active after the renderer accepts it. Geometry/source diffs are calculated per slot:

- removed slot → remove one branch;
- new slot → add one branch;
- source changed → replace one branch;
- geometry changed → update compositor pad properties;
- crop/aspect changed → update one branch;
- z-order changed → update one compositor pad.

Unchanged slots are not intentionally restarted.

## Persistence

SQLite runs in WAL mode with foreign keys and a 30-second busy timeout. Schema migrations are managed with Alembic for packaged upgrades. Configuration exports use a documented JSON format. Complete backups wrap that document in an AES-GCM encrypted archive when credentials are included.

## Security boundaries

- The browser never receives a saved RTSP password.
- The database stores encrypted secrets; the master key is a separate root-owned mode-0640 file restricted to the dedicated `mosaivue` group.
- The renderer receives a resolved URL in process memory over a root-owned/local Unix socket, not a command line.
- The web process and renderer run as an unprivileged service account.
- Only the renderer receives video/render group access and explicit device access in systemd.

## Extensibility

Renderer backends implement `RendererBackend`. Discovery and event integrations are intended as plugins but are not required for v0.1. The API uses versioned routes. Slot types retain fields needed for future image, web, clock, status, and event overlay sources without making those placeholders part of production behavior.
