# Independent pass and final disposition

This appendix preserves findings from an intermediate independent review. The list below records their final status in the delivered candidate; the original observations following it describe the code before correction.

| Finding | Final disposition |
|---|---|
| Linked configuration entries during installer repair | Fixed: reject directory/file symlinks and nonregular/hardlinked files, repeat after locking directory, atomically replace root metadata. |
| Unrelated nonempty installation prefix | Fixed: require a dedicated empty path or recognizable prior Mosaivue installation. |
| Different embedded RTSP credentials | Fixed: use consistent advertised streaming credentials; reject conflicting per-profile credentials. |
| Unsupported Digest negotiation raises 500 | Fixed: translate unsupported/malformed HTTP authentication at the transport boundary to a sanitized ONVIF error. |
| Equivalent IPv6 spellings | Fixed: normalize literal addresses. Hostname-to-IP aliases remain deliberately restricted and documented. |
| Git source staging omits untracked additions | Documented: commit new files before building from a Git checkout; the delivered archive fallback includes all intended source. |
| Force-tracked `.env.*`/SQLite runtime files | Fixed: apply a common rejection guard to tracked and archive source. |
| Generic Git ignore parser | Scope clarified: supports this project's existing patterns, not arbitrary Git ignore syntax. |
| Final scanner check for new ONVIF code | Hardened XML parser via defusedxml; narrowly scoped protocol-required SHA-1 exception. Bandit medium/high gate passes. |

These dispositions have regression/source evidence in the main report and validation record. They are not proof of a full privileged installation or physical-camera qualification.

---

# Independent review: ONVIF onboarding and installer/release changes

Read-only review of the root reviewer's new code, performed after the initial frontend implementation. No reviewed production files were modified by this pass. One focused HTTPX MockTransport reproduction was run; the physical installer was not executed.

## Concrete findings for correction or explicit limitation

1. **Installer repair can still follow pre-existing symlinks (high priority).** `cw_read_root_metadata` rejects a writable old `/etc/mosaivue` directory and instructs the operator to rerun the new source installer. However, `install-local.sh` only applies `install -d -o root ... /etc/mosaivue` before later writes/chown/chmod of known entries. It does not reject a symlinked configuration directory or a symlink already planted in that formerly service-writable directory. The later shell redirects into `install-prefix`/`python-bin` follow symlinks, as do several ownership/mode changes. Thus the documented repair route retains a path from old service-writable entries to privileged filesystem mutation. Reject the directory and known-file symlinks before migration; preferably replace installer metadata with root-owned temporary files and atomic renames. This was communicated to root immediately.

2. **A whitelisted prefix is not necessarily a dedicated prefix (medium/high data-loss risk).** The new path guard accepts existing locations such as `/usr/local/lib64`, `/srv/www`, or `/opt/another-application`; installation then adds the Mosaivue `releases`/`current` markers. Those markers satisfy uninstall's subsequent identity check, after which recursive removal deletes all prior contents of the prefix. The clean default path is fine. Refuse a nonempty existing prefix unless it is already a recognized Mosaivue installation; a short blacklist of known shared directory names does not establish dedicated ownership.

3. **ONVIF credentials override embedded RTSP credentials (medium correctness).** `camera_payload` supplies `connection.username` and `connection.password` as explicit `CameraCreate` credentials. `CameraService._clean_profiles` only adopts credentials embedded in stream URIs when the corresponding explicit value is absent. A device using distinct ONVIF and RTSP users, and returning an RTSP URI with its stream credentials, is therefore imported with the wrong credentials. Choose consistent embedded RTSP credentials when advertised, reject incompatible per-profile credentials with a useful message, or explicitly ask for separate stream credentials. The existing comment implies the embedded credentials will be used, but the explicit values override them.

4. **Unsupported HTTP Digest negotiation leaks an implementation failure as HTTP 500 (medium reliability).** A fixture returning `WWW-Authenticate: Digest realm="camera", nonce="abcd", qop="auth-int", algorithm=MD5` reproduced `NotImplementedError: Digest auth-int support is not yet implemented`. `_request` catches only `httpx.TimeoutException` and `httpx.HTTPError`; HTTPX's unsupported-auth exception escapes both. Return a sanitized unsupported-auth error for these negotiation failures and cover the case with a focused fixture. Other malformed/unsupported digest parameters can raise `ValueError`/`KeyError`; catch only around the transport/auth boundary, not arbitrary application logic.

5. **Exact host matching intentionally narrows camera interoperability.** A user enters `http://camera.local/onvif/device_service`, while the same camera advertises `http://192.168.1.20/onvif/media_service`; `_same_device_url` rejects it. Equivalent compressed/uncompressed IPv6 addresses are also unequal strings. The rejection avoids forwarding credentials to a device-advertised arbitrary host and should not simply be removed. Normalizing IP literals is safe; DNS/alias support needs a deliberate address-validation policy. Until then, document that the entered endpoint should use the same literal host the device advertises and retain the useful manual-address/manual-RTSP fallback message.

## Source-copy review

- The archive/non-Git path excludes the actual current `.gitignore` patterns correctly. A focused check confirmed that node_modules, frontend/dist, `.pi`, and `.env.example` are excluded, while `src/mosaivue/static`, documentation images, and the new ONVIF module remain included.
- Destination-within-source rejection prevents self-recursive staging. Files are validated before copying. Actual production callers stage into fresh temporary directories, which avoids stale destination-file problems.
- In a Git checkout, `git ls-files` includes tracked edits but omits new untracked source/static modules. This is conventional for a committed release workflow, but an uncommitted development build can silently package old tracked files that import absent new modules. Either require a clean/fully staged tree, include nonignored untracked files intentionally, or explicitly state that release creation requires committing new files. The current final ZIP is built from the archive tree, so this is not evidence that its files are missing.
- The additional tracked-file private-artifact check catches `.env`, `.key`, `.pem`, `.db`, `.cwbackup`, `.pi` and `rollout`, but not force-tracked `.env.production`, `*.sqlite` or `*.sqlite3`. Those are excluded in the archive path by `.gitignore`; a common guard for both routes would improve the packaging claim. No such sensitive tracked file was observed in the supplied tree.
- The fallback `.gitignore` interpretation does not implement negation/anchoring semantics in full, but the present ignore file has no negations or anchored patterns requiring those semantics. Do not claim a general gitignore parser.

## Checks that looked correct

- SOAP 1.2 envelope and Media1 operation/body namespaces are consistent; WS-Security digest uses nonce + Created + password and escapes credentials through XML construction.
- Profile metadata, kbps-to-bps conversion, profile selection order, and omitted raw stream URIs in inspection responses are sensible.
- Duplicate/nonvideo profiles are skipped; count and response-size limits are explicit; XML DTD/entity declarations including null-padded UTF-16/32 forms are blocked.
- Redirects are not followed; media-service HTTPS downgrades and cross-host advertisements are rejected with credential-free errors.
- Root-owned/non-writable metadata reads are a substantial improvement for updater/uninstaller paths once the migration repair issue above is addressed.
- These protocol fixtures establish control-flow and wire-format behavior, not physical-camera interoperability. Real-device ONVIF authentication/clock/certificate tests remain necessary.
