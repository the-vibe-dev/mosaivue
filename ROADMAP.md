# Mosaivue roadmap

## Completed in the b4 review candidate - November 13, 2026

Typed compatible settings, atomic settings/capability files, bounded/coalesced previews and probes, revision-aware saved/applied/focused status, explicit Reapply, save/apply recovery, capability-aware controls, JSON reimport, mobile editor drawers and fixed-pixel conversion guidance are implemented. Manual standby selection, OMX/task/database recovery, RPC budgets, restored revision allocation and installer staging/ABI/health/ownership boundaries are corrected. See [the current review](docs/review/current-report.md) and [changelog](CHANGELOG.md).

Earlier ONVIF Media1 onboarding, schedules, duplication/filtering/templates and configuration/security corrections are retained. Supplied b3 browser and Pi observations remain evidence for that build. Candidate software evidence does not publish b4 or qualify its changed physical runtime.

## P1: qualify and complete the single appliance

- Run all eight browser workflows and inspect desktop/mobile/keyboard/focus behavior.
- Complete privileged clean install, failed-update recovery, ownership/permissions, upgrade and reboot acceptance on target hosts; retain matching database/key/settings snapshots.
- Qualify actual HDMI, codecs/decoders, camera mixes, standby failures, concurrent previews and 24/72-hour operation. Pi 4/5 output, Ubuntu physical output and new ROCK Pi work remain gaps.
- Add controller-owned desired/applied configuration generations across cameras/profiles/groups/layouts and optimistic editor conflict handling.
- Define decoded-frame acceptance, last-known-good full-layout recovery and serialized operation ownership/progress. An accepted command or running OMX process does not prove advancing video.
- Encrypt complete secret-bearing URIs with migration and compatible backup/export semantics.
- Add a versioned appliance-settings recovery manifest and inspectable restore plan. Current configuration archives exclude OS/service provisioning, accounts and custom trust/configuration files.

## P2: display and camera completeness

- Implement connector ownership, per-output lifecycle/active layouts, physical portrait and mode/blanking enforcement. Capability reporting already makes the gaps visible.
- Finish display-profile assignment in the UI, synchronized rotation, whole-wall playlists, real group-level placeholders and image tiles.
- Qualify ONVIF Media1 across vendors, then add scoped WS-Discovery, Media2 and PTZ/presets separately.
- Add optional local MSE/WebRTC viewing through restreaming with upstream-connection, authentication, idle cleanup and decoder budgets.
- Resolve audio, native sizing, borders, OMX labels/crop and renderer snapshots by feasibility and demand.

## P2: shared use and observability

- Provide account management, viewer/operator/admin permissions and scoped revocable integration credentials.
- Record bounded secret-free audit history, last-frame age, outage/recovery reasons and useful metrics.
- Preserve dirty editing through session reauthentication; complete canvas keyboard/screen-reader access and focus stability.
- Develop Home Assistant/MQTT/event-triggered actions after scoped credentials and operation ownership.
- Introduce fleet configuration/health after single-appliance reliability; each wall should operate through controller outages.

## Stable-release requirements

Publish measured compatibility/qualification and recovery records; review security, licensing, accessibility and internationalization; supply signed releases and a compatibility policy. A runtime Python inventory is not a complete OS/media lock or external license clearance.

HDMI CEC, Stream Deck, GPIO, motion/doorbell rules and native DMA-BUF rendering remain later candidates. A custom renderer should require measured evidence that the existing architecture cannot meet an established requirement.
