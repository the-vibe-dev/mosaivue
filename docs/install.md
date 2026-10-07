# Installation

## Requirements

- Raspberry Pi OS Lite, Debian, or Ubuntu; use a 64-bit image for the primary GStreamer path
- Python 3.11 or later; the installer supplies a pinned runtime on 32-bit Bullseye Pi OS
- systemd for appliance mode
- GStreamer core, RTSP/base/good/bad/libav plugins, and PyGObject
- an HDMI/DRM, Wayland, or X11 output supported by an installed sink

Legacy 32-bit Pi images can use OMXPlayer for HDMI hardware overlays when it is
installed by the operating system. Set
`"renderer_backend": "omxplayer"` in `/etc/mosaivue/config.json` before starting
`mosaivue-renderer.service`; `auto` selects it on Pi 1–3 and Zero when installed.
The setup token for the local administrator is in `/etc/mosaivue/setup-token`.
The first-run setup and Dashboard also offer available player choices. Web
choices are saved in `/var/lib/mosaivue/renderer-backend.json` and take priority
over the base config file.

## Curl install

After the first public release is published:

```bash
curl -fsSLo mosaivue-install.sh https://raw.githubusercontent.com/the-vibe-dev/mosaivue/main/install.sh && sudo bash mosaivue-install.sh
```

The bootstrap downloads the newest published Mosaivue release with a source-archive checksum and verifies it before installation. For private staging or an offline archive, use the local source install below.

## Native appliance install

```bash
tar -xzf mosaivue-0.1.0b1-source.tar.gz
cd mosaivue-0.1.0b1
sudo ./install.sh
```

The installer detects OS, architecture, Pi model, kernel, DRM connectors, installed multimedia tools, CPU, RAM, and codec/plugin availability. It creates the `mosaivue` service account, builds a virtual environment with access to system PyGObject, installs dependencies, initializes the database/key/token, installs hardened systemd units, runs a capability smoke test, and starts the services.

## Bind modes

- `--bind 127.0.0.1`: local/reverse-proxy-only.
- `--bind 0.0.0.0`: LAN administration; this is the appliance default and is printed explicitly.
- Edit `/etc/mosaivue/config.json` for a specific interface address.

Restart `mosaivue-server.service` after changing bind settings.

## Headless display

The renderer does not require a desktop. A GStreamer KMS sink needs `/dev/dri/card*` and suitable `video`/`render` group access. Legacy OMXPlayer uses Raspberry Pi VideoCore HDMI overlays and `/dev/vchiq`; absence of DRM connectors is expected on that path. VLC is not needed by either supported renderer.

```bash
id mosaivue
ls -l /dev/dri
mosaivue doctor --json
```

## First run

The one-time token is printed by the installer and stored in `/etc/mosaivue/setup-token`. It is deleted after a successful administrator setup. The saved administrator password is hashed with scrypt.

## Reverse proxy

HTTPS is optional on a trusted LAN but recommended elsewhere. Bind Mosaivue to localhost and proxy it through a TLS terminator. Preserve normal `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` headers. Restrict the proxy to trusted users and networks.

## Upgrade

```bash
sudo mosaivue update
```

The helper creates a backup, stages a versioned release, runs the installer, changes the `current` symlink after success, and retains the prior release for rollback. It can also install a local archive:

```bash
sudo /opt/mosaivue/current/installer/update.sh --archive ./mosaivue-0.2.0-source.tar.gz
```

## Rollback

The update prints the retained previous release path and saves a pre-update backup under `/var/lib/mosaivue/`. To return to a previous release with a compatible database schema, substitute that printed path:

```bash
PREVIOUS_RELEASE=/opt/mosaivue/releases/0.1.0b1
sudo ln -sfn "$PREVIOUS_RELEASE" /opt/mosaivue/current.rollback
sudo mv -Tf /opt/mosaivue/current.rollback /opt/mosaivue/current
sudo systemctl restart mosaivue-renderer.service mosaivue-server.service
curl -fsS --retry 60 --retry-delay 2 --retry-connrefused http://127.0.0.1:8080/healthz
```

Keep the pre-update backup if a future release changes the database schema.

## Uninstall

```bash
sudo mosaivue uninstall
```

The default removes services and application releases while preserving `/etc/mosaivue` and `/var/lib/mosaivue`. Those locations are only deleted after an explicit choice or `--purge`.
