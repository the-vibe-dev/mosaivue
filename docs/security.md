# Security design and boundaries

This describes the **0.1.0b4 review candidate**. Software regression tests cover the stated corrections; they do not constitute a complete penetration test or new hardware qualification.

## Authentication

Initial setup requires a locally generated one-time token. Setup is serialized so concurrent requests cannot create two initial administrators. Passwords use scrypt. Random session tokens are stored as SHA-256 hashes in SQLite and sent in HttpOnly, SameSite=Strict cookies. State-changing API operations require a per-session CSRF token, and login/setup attempts are rate limited in process.

Changing a password revokes other sessions while preserving the current session. Server-Sent Events authenticate at connection time and recheck the session before subsequent events/heartbeats, so expired, revoked or disabled accounts stop receiving updates. Mutation events are published after the database commit.

Full account management, viewer/operator roles and scoped revocable integration credentials remain roadmap work. The presence of an admin flag and an audit model does not provide those product workflows.

## Credential storage and URL secrets

Camera usernames/passwords are separated from RTSP userinfo. Passwords are encrypted with AES-256-GCM using a 256-bit key at `/etc/mosaivue/master.key`; the credential record ID is authenticated as associated data. Concurrent key creation publishes one complete key without replacing a key another service has just created.

Saved camera passwords are not returned by camera API responses. The saved username remains available to authenticated administrators; default exports omit it with the password.

**P1 remaining gap: complete stream-URI confidentiality.** Vendor bearer tokens embedded in opaque URL paths or query parameters remain in the stored URI and can appear in camera API output or configuration exports. Encrypting a camera password does not encrypt those URI components. Named sensitive query parameters are redacted in diagnostics, but arbitrary vendor path tokens cannot be identified reliably. Full-URI encryption or explicit modeling of every credential-bearing component remains required before promising protection of all stream secrets. Treat tokenized URLs and exports containing them as credentials.

The legacy OMXPlayer backend and FFmpeg thumbnail fallback pass the resolved stream URL as a process argument. Local process-inspection access may expose credentials. GStreamer holds the resolved URL in memory. Root and the dedicated service account can access sensitive runtime state and the master key; encryption at rest does not remove those exposures.

## Backup scope and restore

| Artifact | Scope |
|---|---|
| Default export / sanitized ZIP | Camera metadata and URLs, profiles, layouts/revisions, rotation groups, display profiles, schedules and database settings; camera username/password fields omitted. Opaque URI tokens may remain. |
| Credential-inclusive `.cwbackup` | The same configuration plus camera credentials, encrypted with an AES-GCM key derived from a passphrase using scrypt. |
| Protected appliance snapshot | A separately retained database/key/configuration/systemd/CA-file snapshot for installation recovery. This is not produced by the configuration-backup API. |

Configuration backups do not include web users/sessions, `/etc/mosaivue/config.json`, renderer-backend overrides, custom CA files, operating-system packages or arbitrary service customizations. Retain those separately when preparing appliance recovery.

Restore validates nested configuration and references before replacing data and rolls back failed imports. A sanitized merge preserves matching local credentials; a sanitized replacement cannot recover omitted passwords. Uploaded archives are bounded to 100 MiB, and the expanded configuration member is bounded to 32 MiB. Unexpected SQL/library exceptions are not echoed to the browser; safe validation messages omit secret input values.

API restore commits configuration before requesting renderer reapplication. It reports a warning if the configuration is saved but the wall cannot be applied. CLI import/restore requires an explicit layout application or renderer restart afterward. See the [candidate upgrade guide](review/upgrade.md).

## Network destinations and URL handling

Manual camera streams accept RTSP/RTSPS URLs with valid hosts/ports. Probe and preview endpoints require authentication and operate on saved cameras. Disabling `web_preview_enabled` prevents preview capture.

ONVIF onboarding accepts an explicit HTTP(S) device-service URL and requires administrator authentication plus CSRF. Inspection/import use Media1 service calls with bounded XML, profiles, response sizes and timeouts. Advertised service/stream hosts must match the supplied device host; redirects, HTTPS service downgrades and forwarding credentials to a different host are rejected. Hostname/IP aliases may require manual RTSP setup. WS-Discovery, Media2 and PTZ are not implemented.

The appliance can contact devices on its camera LAN. Restrict camera and ONVIF destination configuration to trusted administrators. Camera firmware, RTSP behavior and distribution multimedia libraries remain external dependencies.

## Browser and transport protections

The server applies a restrictive Content Security Policy, denies framing, prevents MIME sniffing and sends API responses with `Cache-Control: no-store`. Saved passwords are not retained in browser localStorage; preference/CSRF state has separate purposes.

LAN HTTP does not encrypt credentials or sessions in transit. Use an appropriately configured TLS reverse proxy for access across an untrusted network path and enable secure cookies when deploying HTTPS. The app-scoped `rtsp_tls_ca_file` setting supplies trust to the HDMI GStreamer renderer; it does not configure ONVIF HTTPS or guarantee identical discovery/preview trust behavior.

## Process and installation boundaries

Both API and renderer run as the dedicated `mosaivue` identity. Systemd limits writable paths, home access, kernel changes, privilege acquisition and related operations. The renderer declares video/render groups and explicit device access. The installer also places the shared service account in video/render groups, so separate API and renderer processes are not separate operating-system identities or a strong privilege boundary.

The candidate installer protects `/etc/mosaivue` as `root:mosaivue` with mode `0750`. Configuration, the master key and root-consumed installation/executable metadata use mode `0640`. The setup-token file alone is group-writable (`0660`) so the service can clear its existing inode when the directory prevents unlinking; an empty token cannot authorize setup.

Update/removal scripts check root-consumed metadata ownership and write permissions. Installer paths must be dedicated supported application locations, and privileged writes reject unsafe link entries. Use the **new local source installer** when upgrading an older installation with unsafe metadata permissions; the new updater intentionally rejects metadata it cannot trust. These checks do not establish that a previously compromised host is trustworthy.

The b4 staging copy explicitly assigns root ownership and strips group/other write and special permission bits while preserving executable/read/traverse access. This prevents a trusted checkout's original owner from remaining able to replace installed privileged helpers after installation. Initial source and custom Python interpreters must still be trusted. The real ownership-transfer regression requires root and rsync and is retained for privileged CI/appliance acceptance; it was not executed in this review environment.

## Logs, diagnostics and further work

Structured logs redact URL userinfo and named sensitive query values. Support bundles contain versions, hardware/display/codec information, sanitized camera configuration and recent logs. They can still disclose internal hostnames, addresses and opaque URL tokens; inspect the archive before sharing it.

Known settings now have typed, backwards-compatible validation; invalid values receive field-specific errors without echoing their contents. Atomic settings/renderer-selection writes preserve permitted owner/group access. The API bounds preview/probe decoding per process and checks authentication, camera state and preview policy before using its short image cache. These controls do not limit custom multiple-process deployments or the number of identical waiting HTTP clients.

A complete audit-log workflow, account roles, scoped integration tokens and full stream-URI encryption remain outstanding. Continue updating camera firmware, multimedia libraries and decoder drivers. The [current review](review/current-report.md), [validation record](review/current-validation.md) and [roadmap](../ROADMAP.md) distinguish completed work from remaining items.
