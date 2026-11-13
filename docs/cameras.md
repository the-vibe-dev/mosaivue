# Cameras and stream profiles

A camera is entered once and reused across layouts and rotation groups. Its profiles can represent main, medium and low-resolution substreams. This guide describes the **0.1.0b3 review candidate**.

## Manual RTSP setup

Open **Cameras → Add camera**, name the camera and enter at least one `rtsp://` or `rtsps://` URL. IPv6 addresses must be bracketed, for example `rtsps://[2001:db8::10]:7441/live`. Missing hosts, invalid ports and control characters are rejected.

Embedded username/password fields are separated from the URL on save. The password is encrypted; the username remains available to authenticated administrators. Camera responses return the URL without userinfo, the saved username and `has_password`, never the saved password. A vendor's bearer token embedded in a path or query remains part of the URL; see [security boundaries](security.md#credential-storage-and-url-secrets).

Use a camera/NVR account with only the access required to view the selected streams. All profiles of one camera share one credential record; conflicting embedded credentials must be resolved before saving.

## Import from a known ONVIF endpoint

The candidate adds **ONVIF Media1 profile onboarding**:

1. Enable ONVIF on the camera if required by its vendor, and obtain its device-service URL and credentials.
2. Open **Cameras → Import ONVIF**. Enter the complete HTTP(S) device-service URL, such as `http://192.0.2.10/onvif/device_service`, and the credentials in their separate fields.
3. Select **Inspect profiles**. Review the reported codec, dimensions, frame rate, bitrate and any skipped-profile warnings.
4. Name the camera, select the profiles you want, and choose **Import selected profiles**.
5. Test the imported streams and apply a layout on the actual appliance.

Inspection uses `GetCapabilities` and `GetProfiles`; import resolves each selected URI through `GetStreamUri`. Inspection returns profile metadata without stream URIs or passwords. Import stores streaming credentials through the normal encrypted credential store. If the camera advertises a consistent streaming credential distinct from its management account, that credential is used.

This workflow requires administrator authentication and CSRF protection. It supports WS-Security UsernameToken and the implemented HTTP Digest/Basic challenge paths, with bounded responses, timeouts and a maximum of 32 advertised profiles. Camera time synchronization can affect authentication. Redirects are rejected; use the final device-service URL.

**Scope:** enter a known device endpoint. Multicast WS-Discovery, Media2, PTZ control and full ONVIF conformance are not implemented. Advertised service and stream hosts must match the supplied host; a hostname/IP alias can require using the advertised address or manual RTSP setup. An HTTPS device endpoint cannot downgrade its advertised media service to HTTP. Real-camera interoperability for this candidate remains to be qualified.

## Profile selection and editing

Record known codec, dimensions, FPS, bitrate, transport and latency preset for each profile. Automatic tile selection uses known dimensions to choose the smallest adequate source, or the largest available source if none is large enough. It does not change camera settings or guarantee that the selected codec can be decoded by the appliance. Manual selection uses the chosen profile. A fullscreen focus request can specify a profile; otherwise it uses the camera's default profile priority.

For example, a camera might expose a 3840×2160 H.265 main stream and a 640×360 H.264 substream. Small tiles can use the substream while a larger view uses a higher-resolution source, subject to measured decoder capacity.

Editing a profile preserves its identity and metadata. Removing a profile or camera still referenced by a current layout or rotation group returns a conflict; remove those references first. Leaving the password field unchanged preserves the saved secret; use the explicit credential-clearing option to remove it.

**Reapply the active layout after editing camera URLs, credentials, transport, profiles or enablement.** Saving configuration does not automatically rebuild existing fixed renderer branches. Verify the displayed result after reapplication.

## Test stream and previews

**Test stream** uses GStreamer discovery. Success requires a successful discovery result and a usable video stream. Available results include discovery response time, codec caps, dimensions, framerate, bitrate and requested transport.

Discovery duration is not a decoded first-frame measurement. `time_to_first_frame_ms` is null when it was not measured, and `decoder_selected` may also be unavailable. Measure actual first-frame and recovery latency during [hardware qualification](performance.md).

Browser previews are individual JPEG captures, separate from HDMI playback. Saved transport preferences are passed to discovery and preview capture. Setting `web_preview_enabled` to `false` in the appliance configuration disables the preview endpoint before a capture is started. A preview can still behave differently from the active renderer because it uses a separate decoding path.

## RTSPS certificate trust

Use the port, stream path and hostname provided by the camera/NVR. For a private or self-signed CA, the HDMI GStreamer renderer can use a service-readable PEM trust file configured through `rtsp_tls_ca_file` in `/etc/mosaivue/config.json`. The URL hostname must match the certificate. Include the needed authorities for each secure server used by that renderer.

This renderer setting does not configure ONVIF HTTPS trust or guarantee that discovery/preview tools use the same trust configuration. Test each path separately. Custom CA files are not included in configuration backups and must be retained separately for appliance recovery.
