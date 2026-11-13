# Installing and upgrading the 0.1.0b3 review candidate

**Candidate date: 2026-11-13.** This guide applies to the supplied local source. The online bootstrap/update helper selects a published GitHub release, which may still be older. This package does not publish a release or change an existing appliance by itself.

No database schema migration was introduced by this review. The installer still runs the project's existing migration process. Changed software, browser flows, camera interoperability and recovery behavior require acceptance on the target appliance; passing software tests is not a completed physical installation trial.

## Choose the artifact

| Artifact | Intended use |
|---|---|
| `mosaivue-0.1.0b3-source.tar.gz` | Recommended candidate installation/upgrade path for supported Pi, ROCK Pi and Linux appliances. Includes the installer and prebuilt web assets. |
| Python wheel, version `0.1.0b3` | Python package installation; does not provide GStreamer, OMXPlayer, drivers or service provisioning by itself. |
| `mosaivue_0.1.0~b3_amd64.deb` | Supplied amd64 Debian artifact. The `~b3` spelling gives correct Debian prerelease ordering. It is not an ARM/Pi package. |

The source archive is not an offline dependency mirror. Installation normally requires package/network access and a supported systemd host. Existing supported-platform requirements remain in [installation](../install.md). Included web assets can be served without Node; Node/TypeScript are needed to rebuild them.

## Before changing an existing wall

Choose a window in which the display may be interrupted. Keep the previous source/release, current layout IDs, settings, service overrides and any custom CA files available.

Create a credential-inclusive configuration backup while the existing application is usable:

```bash
sudo -u mosaivue mosaivue backup --include-credentials --output /var/lib/mosaivue/pre-b3.cwbackup
```

The command prompts for the encryption passphrase. Preserve the file and passphrase separately. This is a **configuration backup**: it includes camera credentials, registry/profiles, layouts/revisions, groups, display profiles, schedules and database settings. It does not include web users/sessions, `/etc/mosaivue/config.json`, renderer override files, custom CA files, operating-system packages or arbitrary systemd customizations. A sanitized replacement cannot restore omitted passwords; a sanitized merge preserves existing matching credentials.

For a matching database/key/settings snapshot, stop both services before copying their state. One example for the default paths is:

```bash
mosaivue_snapshot="/root/mosaivue-before-b3-$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 0700 "$mosaivue_snapshot"
sudo systemctl stop mosaivue-server.service mosaivue-renderer.service
sudo tar -C / -czf "$mosaivue_snapshot/appliance-state.tar.gz" etc/mosaivue var/lib/mosaivue
sudo systemctl start mosaivue-renderer.service mosaivue-server.service
```

That root-only archive contains the key and credential database together. Retain custom systemd units/drop-ins and CA files outside those directories separately. Preserve the existing release target and the actual install prefix as well. The installer also records a pre-install snapshot and prints its location; keep that record if recovery is needed.

## Install the supplied source

From the folder containing the source archive and its checksum:

```bash
sha256sum -c mosaivue-0.1.0b3-source.tar.gz.sha256
tar -xzf mosaivue-0.1.0b3-source.tar.gz
cd mosaivue-0.1.0b3
sudo ./install.sh --non-interactive
```

Running `install.sh` from this complete source tree invokes its local installer. Use the same dedicated prefix as the existing installation when it differs from `/opt/mosaivue`, for example `--prefix /opt/mosaivue-lab`. Do not point the installer at an unrelated shared directory. Existing configuration is retained; the default LAN bind applies when creating a new configuration. Review the effective bind printed by the installer.

For an older installation with service-writable configuration metadata, use this **new source installer**. The new updater can deliberately reject unsafe saved metadata rather than consume it. The installer repairs the configuration-directory policy and validates entries before root-level writes.

`--no-start` installs without starting the services; on an upgrade it can leave the previous services stopped. Use it only when prepared to complete the manual startup/checks. `--skip-packages` assumes the operating-system dependencies are already present.

## Verify the candidate on the appliance

For the default install prefix:

```bash
sudo /opt/mosaivue/current/.venv/bin/python -c 'import mosaivue; print(mosaivue.__version__)'
sudo systemctl status mosaivue-renderer.service mosaivue-server.service --no-pager
sudo -u mosaivue mosaivue doctor --json
sudo -u mosaivue mosaivue security audit
sudo -u mosaivue mosaivue renderer status --json
```

The Python version should be `0.1.0b3`. Review diagnostics in the context of the selected backend, drivers and network. Open the UI, log in, explicitly apply a known layout and verify advancing images on the physical display. Check that camera profile selections and saved credentials still work.

The expected installer permission policy is `/etc/mosaivue` as `root:mosaivue` mode `0750`; config/key/root-consumed metadata mode `0640`; and the setup-token file, when present, mode `0660`. The token may remain as an empty consumed file because the service cannot unlink directory entries. Do not restore the old group-writable directory merely to remove that file.

Test camera failure/recovery, two independent rotation slots, Skip/Hold, focus/restore, profile edits and an overnight schedule. A currently active schedule can reassert its wall on the approximately 30-second watcher interval after a manual layout change; fullscreen focus pauses that behavior. When all schedule windows end, the last wall remains visible.

The GStreamer output remains **5 FPS by default**. `MOSAIVUE_OUTPUT_FPS` accepts 1–60; qualify any higher setting under real load using [performance guidance](../performance.md). Existing hardware results are historical and do not establish the changed candidate's performance.

## Applying changes and restoring configuration

Reapply the active layout after changing camera URLs, credentials, enabled state, transport, profiles or group behavior. Saving configuration alone does not refresh every fixed renderer branch. A legacy `placeholder` group setting behaves as Hold; select supported Skip/Hold behavior when reviewing the group. Synchronized group switching remains unimplemented.

API restore saves configuration before requesting renderer reapplication. Read its result: `renderer_applied=false` means the configuration was saved but the output still needs attention. If no active layout is selected, restart the renderer to clear old output and then choose a layout.

After CLI import/restore, explicitly apply a layout or restart the renderer:

```bash
sudo -u mosaivue mosaivue layout list
sudo -u mosaivue mosaivue layout activate LAYOUT_ID
```

Replace `LAYOUT_ID` with the intended saved layout. A renderer restart is an alternative when it should load the saved active wall. ONVIF import adds a camera/profile registry entry; it does not automatically place it into a wall. Add it to a layout, save/apply and verify the camera on the appliance.

## Recovery and acceptance limits

On an installation failure after switching/stopping services or changing state, the installer attempts to restore its retained previous release/database/configuration snapshot and prior service state. Preserve the printed snapshot path and logs. This is implemented recovery behavior with software-level checks; it still requires representative systemd-host failure testing.

For manual recovery, stop both services and use the retained release target together with its matching database, master key and settings. Keep custom CA/service files with that recovery set, retain the protected root-owned metadata policy, then check startup and playback before returning the wall to service. A database/key mismatch makes encrypted camera secrets unusable. Avoid combining unrelated snapshots or deleting the previous release before acceptance.

See the [review report](report.md) and [validation record](validation.md) for completed checks and outstanding browser, installer, camera and display testing. Local installation of this candidate is separate from publishing a release or asserting a new supported hardware/stream-count result.
