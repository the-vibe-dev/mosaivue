# Mosaivue documentation

Start with the [README](../README.md) for the product overview and first camera wall.

## 0.1.0b5 candidate

Read the [installation guide](install.md) before changing an existing appliance. The [changelog](../CHANGELOG.md) explains the implemented fixes; [build verification](../BUILD-VERIFICATION.md) identifies completed checks and limits. This candidate has not been qualified on hardware.

| Topic | Guide |
|---|---|
| Candidate changes and future work | [Changelog](../CHANGELOG.md) and [roadmap](../ROADMAP.md) |
| Candidate install, upgrade and recovery | [Installation](install.md) |
| Completed verification and limits | [Build verification](../BUILD-VERIFICATION.md) |
| Earlier beta scope and hardware evidence | [Beta release notes](beta-release.md) |
| General installation requirements | [Installation](install.md) |
| RTSP URLs, profiles and known-endpoint ONVIF import | [Cameras](cameras.md) |
| Visual layout editor | [Layouts](layouts.md) |
| Independent rotation, Skip/Hold and scheduled-wall behavior | [Rotation](rotation.md) |
| Display backends and health | [Renderer](renderer.md) |
| Compositor FPS and hardware measurement | [Performance](performance.md) and [hardware test plan](hardware-test-plan.md) |
| Common failures | [Troubleshooting](troubleshooting.md) |
| API | [API guide](api.md) and [OpenAPI snapshot](openapi.json) |
| Credentials, configuration backups and installation boundaries | [Security design](security.md) and [reporting policy](../SECURITY.md) |
| Existing displaycameras sites | [Migration](migration-displaycameras.md) and [compatibility](compatibility.md) |
| Contributors | [Development](development.md), [architecture](architecture.md) and [brand assets](branding.md) |

The `adr/` directory records design decisions. The [release engineering report](release-engineering-report.md) records an earlier software build. Historical beta measurements remain attributed to their original builds; the candidate's changed runtime, browser and installer paths need fresh acceptance work.

Detailed review reports and appliance observations are retained locally under the Git-ignored `.private-reviews/` directory. Public product documentation and build verification are linked above.
