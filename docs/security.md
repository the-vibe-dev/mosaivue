# Security design

## Authentication

Initial setup requires a one-time token generated locally. Passwords are hashed with scrypt. Sessions use random opaque tokens stored as SHA-256 hashes in SQLite and sent in HttpOnly, SameSite=Strict cookies. State-changing requests require a per-session CSRF token. Login attempts are rate limited in process.

## Credential storage

RTSP credentials are separated from stream metadata. Passwords are encrypted with AES-256-GCM using a random 256-bit key stored at `/etc/mosaivue/master.key`. The credential record ID is authenticated as associated data, preventing ciphertext from being silently moved between records.

Passwords are never returned after saving. Usernames are omitted from sanitized exports. Complete credential backups require a passphrase and are encrypted with a key derived by scrypt.

The legacy OMXPlayer backend passes the resolved RTSP or RTSPS URL to the
external player as a process argument. That URL may contain camera credentials
and may be visible to local users with process-inspection access. Treat local
shell access as trusted, use read-only camera accounts, and avoid sharing the
appliance with untrusted local users. GStreamer holds the resolved URL in its
process memory. Encryption at rest does not remove these runtime exposures.

## URL and SSRF boundary

The camera API accepts only RTSP/RTSPS schemes. Probe and preview endpoints require authentication and operate only on saved camera records. There is no generic unauthenticated URL fetch endpoint. Operators should still treat the appliance as privileged on the camera LAN and restrict who can add cameras.

## Browser defenses

The server sets a restrictive Content Security Policy, denies framing, disables MIME sniffing, applies no-store to API responses, and authenticates SSE connections. Saved secrets are not stored in browser localStorage; only theme preference is persistent and CSRF state is session-scoped.

## Process privileges

The API and renderer run as `mosaivue`, not root. Only the renderer receives video/render groups and explicit DRM/video device access. Systemd restricts writable paths, home access, kernel tunables/modules, control groups, setuid, and new privileges.

## Logging and support bundles

Structured logging passes messages through URL/secret redaction. Diagnostic bundles include versions, hardware, sanitized configuration, display and codec data, pipeline state, and recent logs. Automated tests assert credential exclusion. Always inspect an archive before publishing it.

## Known boundaries

- LAN HTTP does not protect against a hostile network path; use TLS through a reverse proxy outside a trusted network.
- A local root user or the dedicated `mosaivue` service account can read the master key and process memory.
- Camera firmware, RTSP server behavior, and distribution multimedia plugins are outside the Mosaivue trust boundary.
- Hardware decode paths and GStreamer plugins require ongoing upstream security updates.
