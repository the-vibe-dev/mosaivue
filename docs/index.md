# Mosaivue documentation

Start with the [README](../README.md) for the product overview and first camera wall.

## 0.1.0b4 review candidate — 2026-11-13

Read the [candidate installation/upgrade guide](review/current-upgrade.md) before changing an existing appliance. The [review report](review/current-report.md) explains the implemented fixes, competitor gaps and remaining work; the [validation record](review/current-validation.md) identifies the actual completed checks and environment limitations. Local candidate delivery does not publish a release or qualify new hardware.

| Topic | Guide |
|---|---|
| Candidate changes and future work | [Changelog](../CHANGELOG.md), [roadmap](../ROADMAP.md) and [review report](review/current-report.md) |
| Candidate install, upgrade and recovery | [Review candidate upgrade](review/current-upgrade.md) |
| Completed verification and limits | [Validation record](review/current-validation.md) |
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

The `adr/` directory records design decisions. The [release engineering report](release-engineering-report.md) records an earlier software build. Historical beta measurements remain attributed to their original builds; the candidate's changed runtime, browser and installer paths need the acceptance work identified in the review.

The [supplied b3 build and appliance record](review/supplied-b3-build-verification.md) is preserved unchanged. The earlier [b3 review](review/report.md) and its component appendices remain historical documents; use the current report for b4 behavior and results.
