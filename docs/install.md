# Installation

## Requirements

- Debian 12 or newer, Raspberry Pi OS 12 or newer, or Ubuntu 24.04 or newer, on ARM64 or AMD64. The legacy Raspberry Pi OS 11 ARMHF/OMXPlayer path is also supported when OMXPlayer is already installed.
- A systemd installation with `sudo`, internet access for OS and Python packages, and enough free space for multimedia packages and a staged copy of the application. The download command needs `curl`; the installer installs Python 3.11+, GStreamer, PyGObject, and its other OS dependencies.
- A connected display and an available DRM/KMS, Wayland, or X11 sink for local video. Web setup can be completed without a display, but the renderer needs a usable output to show a wall.
- For NVIDIA GPU passthrough on Ubuntu, install Ubuntu's NVIDIA driver and an Xorg display before selecting `ximagesink`. The installer supplies the X11 GStreamer plugin (`gstreamer1.0-x`) but does not install a vendor GPU driver. Confirm an active output mode with `DISPLAY=:0 xrandr --query` and inspect the physical monitor; a virtual X screen can run while no monitor receives a picture.
- Camera RTSP/RTSPS URLs and credentials for first-run setup. They are entered in the web UI and are not needed to install the software.

Legacy 32-bit Pi images can use OMXPlayer for HDMI hardware overlays when it is
installed by the operating system. Set
`"renderer_backend": "omxplayer"` in `/etc/mosaivue/config.json` before starting
`mosaivue-renderer.service`; `auto` selects it on Pi 1–3 and Zero when installed.
The setup token for the local administrator is in `/etc/mosaivue/setup-token`.
The first-run setup and Dashboard also offer available player choices. Web
choices are saved in `/var/lib/mosaivue/renderer-backend.json` and take priority
over the base config file.

## Curl install

After a public beta release is published, run this on the target device:

```bash
sudo apt-get update && sudo apt-get install -y curl ca-certificates && curl -fsSLo mosaivue-install.sh https://raw.githubusercontent.com/the-vibe-dev/mosaivue/main/install.sh && sudo bash mosaivue-install.sh
```

The command installs the download prerequisites first. The bootstrap then supplies Python if the image lacks it, downloads the newest published Mosaivue source release, verifies its SHA-256 checksum, installs the remaining dependencies, and starts the appliance. It prints the local setup URL and one-time administrator token. Anonymous downloads require a public release; for private staging or an offline archive, use the local source install below.

## Native appliance install

```bash
tar -xzf mosaivue-0.1.0b1-source.tar.gz
cd mosaivue-0.1.0b1
sudo ./install.sh
```

The installer detects OS, architecture, Pi model, kernel, DRM connectors, installed multimedia tools, CPU, RAM, and codec/plugin availability. It creates the `mosaivue` service account, builds a virtual environment with access to system PyGObject, installs dependencies, initializes the database/key/token, installs hardened systemd units, probes video decoders, runs a capability smoke test, and starts the services. Re-running the command stages a separate release and preserves a database and key snapshot before migration.

The decoder probe runs as the `mosaivue` service account. The installer also grants detected NVIDIA device nodes to the sandboxed renderer; DRM and V4L2 device classes and Rockchip MPP devices are covered by their service rules. For H.264, H.265, and JPEG, it enumerates installed GStreamer decoders and tests each with a short synthetic stream. A working hardware decoder is preferred for fixed tiles; a working software decoder is preferred for rotating tiles because long-running hardware decoder switching stalled on the tested ROCK Pi and NVIDIA walls. The installer saves the choices and probe results in `/var/lib/mosaivue/decoder-policy.json`; `mosaivue doctor --json` includes them. Stream health reports the decoder actually selected by GStreamer. The probe tests basic decode and device access; it cannot guarantee that every camera profile or long-running rotation will work. Re-run the installer after changing GPU drivers or GStreamer plugins to refresh the policy and device rules. If no candidate passes, GStreamer retains automatic decoder selection for that codec.

On Rockchip systems with an MPP decoder, KMS sink, and the required GStreamer
plugins, the installer also normalizes rotating cameras to 640×360 I420 at 15
fps. This fixed selector format prevented the mixed-resolution rotation failure
on the tested ROCK Pi 4B+. The default is intended for 16:9 camera groups. For
another aspect ratio, install with `--rotation-normalize WIDTHxHEIGHT` using
even dimensions within 160×90–1920×1080. `--rotation-normalize off` disables
normalization. `auto` is the default and retains an existing valid target on
upgrade. The installer manages
`/etc/systemd/system/mosaivue-renderer.service.d/normalize-rotation.conf`,
includes it in the pre-install snapshot, and restores it if installation fails.
Other platforms default to off. Verify the displayed camera crops after setup.

On AMD64 Debian 12+ or Ubuntu 24.04+, the release `.deb` can be installed with `sudo apt install ./mosaivue_<version>_amd64.deb`. The package uses the same installer and keeps OS package dependencies in its metadata. ARM devices use the source bootstrap above. The 32-bit Bullseye/OMXPlayer path needs that bootstrap because its OS does not provide Python 3.11 as a Debian package.

## Bind modes

- `--bind 127.0.0.1`: local/reverse-proxy-only.
- `--bind 0.0.0.0`: LAN administration; this is the appliance default and is printed explicitly.
- Edit `/etc/mosaivue/config.json` for a specific interface address.

Restart `mosaivue-server.service` after changing bind settings.

## Headless display

The renderer does not require a desktop. A GStreamer KMS sink needs `/dev/dri/card*` and suitable `video`/`render` group access. Legacy OMXPlayer uses Raspberry Pi VideoCore HDMI overlays and `/dev/vchiq`; absence of DRM connectors is expected on that path. VLC is not needed by either supported renderer.

On a ROCK Pi 4B+ with the Rockchip MPP plugin, the installer adds access to
`/dev/mpp_service`, `/dev/rga`, and the video-owned DMA heaps. Select
`gstreamer` with the `kmssink` sink. If GDM or another desktop compositor owns
the HDMI connector, stop its display-manager service before starting the
Mosaivue renderer; a local desktop cannot share DRM master with `kmssink`.

On the tested Debian 12 arm64 image, `mppvideodec` and `kmssink` were available.
After configuring the backend, a short local H.264/KMS test can check the
renderer without camera credentials or database changes:

```bash
sudo apt-get install -y gir1.2-gst-rtsp-server-1.0
sudo systemctl stop mosaivue-renderer.service
sudo -u mosaivue /opt/mosaivue/current/.venv/bin/python \
  /opt/mosaivue/current/scripts/rockpi-smoke.py --streams 4 --seconds 15
sudo systemctl start mosaivue-renderer.service
```

The smoke test uses four local 640×360 H.264 sources, 1280×720 KMS output,
and two prepared source switches. A pass does not establish the capacity or
reliability of a particular camera network. Confirm the monitor image and
test the intended camera mix and rotation interval separately.
If a camera probes successfully in FFmpeg but GStreamer receives few frames,
try that camera profile's `stable` latency preset before changing the wall.

```bash
id mosaivue
ls -l /dev/dri
mosaivue doctor --json
```

On an NVIDIA passthrough VM whose Xorg service started before the HDMI monitor
was connected, `xrandr` may show the connector as connected without an active
mode. Assign the monitor's supported mode after hotplugging it:

```bash
DISPLAY=:0 xrandr --query
DISPLAY=:0 xrandr --fb 1920x1080 --output HDMI-0 --mode 1920x1080 --rate 60 --primary --pos 0x0
```

Use the output name and mode reported by the first command. A bare
`xrandr --auto` while every connector is disconnected can shrink the virtual
screen to 8×8. On the tested NVIDIA driver, Xorg reported the connected HDMI
output and displayed the wall even while the kernel DRM status file still
reported `disconnected`; verify the active Xorg mode and the actual monitor.

For a dedicated camera wall, disable Xorg's idle screen blanking and DPMS
timeouts in the Xorg configuration used by that display. Otherwise Xorg may
turn off HDMI after ten minutes while Mosaivue continues decoding:

```text
Section "ServerFlags"
    Option "BlankTime" "0"
    Option "StandbyTime" "0"
    Option "SuspendTime" "0"
    Option "OffTime" "0"
EndSection
```

Restart Xorg and the renderer after changing the file. `DISPLAY=:0 xset q`
should then report a zero screen-saver timeout, zero DPMS timeouts, and
`Monitor is On`.

## First run

The one-time token is printed by the installer and stored in `/etc/mosaivue/setup-token`. It is deleted after a successful administrator setup. The saved administrator password is hashed with scrypt.

## Reverse proxy

HTTPS is optional on a trusted LAN but recommended elsewhere. Bind Mosaivue to localhost and proxy it through a TLS terminator. Preserve normal `Host`, `X-Forwarded-For`, and `X-Forwarded-Proto` headers. Restrict the proxy to trusted users and networks.

## Upgrade

```bash
sudo mosaivue update
```

The helper stages a versioned release and calls the same installer. Before database migration, it saves a consistent SQLite snapshot, the encryption key, and the decoder policy under `/var/backups/mosaivue-install-*` with root-only directory access. A failed migration or startup restores the database, key, config, decoder policy, previous release link, and previously running services. The previous release remains installed. To install a local archive:

```bash
sudo /opt/mosaivue/current/installer/update.sh --archive ./mosaivue-0.2.0-source.tar.gz
```

## Rollback

The update prints the retained previous release path and the pre-update snapshot under `/var/backups/mosaivue-install-*`. For a manual rollback when the database schema is still compatible, substitute the printed previous release path:

```bash
PREVIOUS_RELEASE=/opt/mosaivue/releases/0.1.0b1
sudo ln -sfn "$PREVIOUS_RELEASE" /opt/mosaivue/current.rollback
sudo mv -Tf /opt/mosaivue/current.rollback /opt/mosaivue/current
sudo systemctl restart mosaivue-renderer.service mosaivue-server.service
curl -fsS --retry 60 --retry-delay 2 --retry-connrefused http://127.0.0.1:8080/healthz
```

For a schema-changing release, restore its matching SQLite snapshot and master key together while both services are stopped before starting the older release. Keep the protected snapshot until the update has run long enough to confirm it is healthy.

## Uninstall

```bash
sudo mosaivue uninstall
```

The default removes services and application releases while preserving `/etc/mosaivue` and `/var/lib/mosaivue`. Those locations are only deleted after an explicit choice or `--purge`.
