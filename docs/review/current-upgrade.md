# Install and qualify the b4 candidate

This guide covers the delivered **0.1.0b4** source. The online bootstrap follows published releases and may install an older version. This review has not published or deployed b4. No database migration was added; settings validation, runtime behavior and the interface have changed.

## Prepare recovery and configuration

Use a controlled maintenance window. Retain the previous release and matching database/master-key/settings snapshot. Configuration exports, including encrypted credential-inclusive archives, are not complete appliance recovery images. Preserve `/etc/mosaivue/config.json`, `/etc/mosaivue/master.key`, installation metadata, `/var/lib/mosaivue/mosaivue.db`, renderer selection, decoder policy, custom CA files and systemd overrides together. Handle snapshots as secrets.

Record the current wall, profiles, decoder choices, monitor mode, frame advancement and services. Confirm a dedicated prefix with protected root-owned parents. The new installer rejects unsafe ancestors and a symlink/non-directory releases entry, assigns installed source to root, strips group/other write and special permission bits, and retains executable/read/traverse access. Initial source and custom Python interpreters must still be trusted; this cannot make a previously compromised host trustworthy.

Known settings are now validated consistently. Legacy boolean strings remain accepted; invalid values receive field-specific errors. Unknown keys warn and are ignored. Use the candidate's `mosaivue config validate` workflow and correct errors before service restart. Defaults remain one active preview/probe and a two-second internal JPEG cache. `preview_concurrency` accepts 1-4; `preview_cache_ttl_seconds` accepts 0-30, with zero disabling caching. Restart the API after changing these. Leave concurrency at one until the real workload is measured.

## Install the included source

```bash
sha256sum -c mosaivue-0.1.0b4-source.tar.gz.sha256
tar -xzf mosaivue-0.1.0b4-source.tar.gz
cd mosaivue-0.1.0b4
sudo bash installer/install-local.sh
```

Retain an established custom prefix and intentional bind configuration if applicable. `--bind 127.0.0.1` limits access to loopback/reverse-proxy administration; normal installation explicitly binds to the LAN. Local health checks now match IPv4/IPv6 and bypass HTTP proxies. The amd64 Debian package is an alternative on appropriate amd64 Debian/Ubuntu targets; it invokes the same installer and was built, not root-installed, here.

Bullseye retains the supplied upstream checksum-pinned wheels and API/renderer/AES-GCM preflight. pydantic-core now follows the actual standard CPython 3.11-3.15 ABI; unsupported/free-threaded interpreters fail preflight. This is selection support, not qualification of all those interpreters. Keep the proven appliance interpreter unless a change has a specific purpose and acceptance plan.

Editable `--dev` installs now repair paths after staging rename. Installed source stays root-owned. Edit a trusted development checkout and reinstall; do not weaken installed helper permissions for convenience.

## Immediate acceptance

1. Check versions, HTTP health, logs and both services, then inspect the physical monitor and advancing video. HTTP health alone is insufficient.
2. Save a changed active layout without applying; confirm pending state, apply it and verify the reported revision. Reapply after camera/group edits. Exercise failed application after successful saving and retry without an extra revision.
3. Test Previous with Next already prepared, immediate Next, an unreachable target, OMX spawn failure and transient database interruption. Verify fixed-tile continuity and recovery counters.
4. Exercise concurrent previews, disabled previews, credentials/profile changes and retryable 503 responses. Inspect capabilities and unsupported controls; the matrix does not implement multi-output or portrait.
5. Test JSON merge/replacement and backup restore on a disposable copy first. Configuration import and successful renderer application are separate outcomes.
6. Verify release/ancestor ownership and permissions, run the root/rsync regression in isolated privileged CI, and rehearse a failed upgrade/rollback.
7. Complete all eight browser scenarios, mobile/keyboard/focus checks, reboot and the fault/soak plan in `b4-acceptance-checklist.md`.

## Recover if necessary

The installer retains the previous release and pre-install snapshot and attempts recovery on failure. Preserve its printed paths and logs. If manual recovery is required, stop writes, restore the matching database/key/settings/service snapshot and previous release together, then verify service access, credentials and actual video. Do not pair a database with an unrelated master key or treat configuration import as OS recovery. See `../security.md` for the full storage and backup boundaries.
