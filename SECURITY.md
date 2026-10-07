# Security policy

## Supported versions

Until the first stable release, only the newest tagged release candidate receives security fixes. After 1.0, the project intends to support the current minor release and the immediately previous minor release for critical fixes.

## Reporting a vulnerability

Do not open a public issue for a vulnerability that exposes camera credentials, authentication bypass, arbitrary command execution, filesystem access, SSRF into trusted networks, or video-feed disclosure.

Use GitHub private vulnerability reporting when enabled, or contact the security address listed in the repository profile. Include:

- affected version and install method;
- target platform and configuration;
- exact request, local command, or malformed input;
- proof of impact with secrets removed;
- whether the issue is reachable before authentication;
- suggested remediation, if known.

The project will acknowledge a complete report, reproduce it, coordinate a fix and release, and credit the reporter unless anonymity is requested.

## Deployment guidance

- Treat Mosaivue as a trusted-LAN appliance, not an Internet-facing service.
- Use a reverse proxy with TLS and access controls for remote access.
- Restrict firewall access to administration ports.
- Use separate read-only camera accounts where the camera/NVR supports them.
- Keep `/etc/mosaivue/master.key` and complete encrypted backups protected.
- Do not publish raw support bundles without inspecting them.
- Run `mosaivue security audit` after install and upgrades.

## Security design

See `docs/security.md` for authentication, CSRF, encryption, URL handling, process privileges, support-bundle redaction, and known trust boundaries.
