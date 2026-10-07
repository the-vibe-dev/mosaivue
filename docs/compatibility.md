# displaycameras compatibility

| displaycameras feature | Mosaivue equivalent |
|---|---|
| RTSP stream arrays | Persistent Camera Registry and Stream Profiles |
| Manual pixel coordinates | Visual Layout Editor and normalized geometry |
| `layout.conf` | Revisioned Layout objects |
| Resolution-specific layouts | Responsive geometry plus Display Profiles |
| Camera rotation | Independent Rotation Groups and optional page scheduling |
| `seq_step` | Group/page sequencing through slots and layouts |
| Watchdog | Per-stream health manager and branch reconnect |
| OMXPlayer DBus | Versioned renderer abstraction and local RPC |
| systemd startup | Separate hardened renderer/server systemd services |
| Shell configuration | Web UI, TUI, CLI, documented JSON import/export |

Pixel overrides remain available for advanced users. Migration leaves old configuration untouched.
