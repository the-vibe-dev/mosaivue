# Mosaivue roadmap

## Completed in b5

Atomic guarded layout saves, UUID-aware activation/restore, metadata revision tokens, recoverable reload/save-copy conflicts, complete display-profile assignment/editing, profile-aware schematics and explicit referenced-profile deletion are implemented. Decoder policy now uses serialized atomic writes, exact verified-choice retention, retryable source-bound persistence and retention after installer probe failure. The sampler/analyzer separates source/output runs and rotating counters. See the [changelog](CHANGELOG.md) and [build verification](BUILD-VERIFICATION.md); detailed review findings are retained locally outside Git.

Earlier onboarding, schedules, templates, configuration integrity, typed settings, bounded previews, mobile controls, renderer recovery and installer corrections remain included. Supplied b4 evidence now includes eight browser workflows, Pi 3 reboot recovery, and visually confirmed Ubuntu/ROCK Pi output. The final-source 24h observations had no completed result in the upload. These observations support b4, not automatic b5 qualification.

## P1: qualify and complete the single appliance

- Run the ten candidate browser workflows and inspect desktop/mobile/keyboard/focus behavior.
- Complete privileged clean full installation, failed-update recovery, owner/group checks and candidate reboot acceptance; the supplied controlled upgrades all skipped package installation.
- Repeat real output, camera/codec mix, source interruption, fallback persistence and preview-load checks; retain exact-source 24h and 72h observations. Pi 4/5 output and broader camera coverage remain unqualified.
- Add controller-owned desired/applied configuration generations across mutable cameras, profiles, groups and layout metadata. Current revision tokens protect layout edits but do not freeze the entire wall.
- Define full-wall first-frame acceptance, bounded operation identity/progress, last-known-good recovery and retention of a displayed snapshot beyond ordinary history pruning.
- Encrypt complete secret-bearing URIs with compatible migration/API/export/backup behavior; address runtime subprocess exposure separately.
- Add an inspectable versioned appliance recovery manifest and test restoration with matching database, key, settings, trust material and service overrides.

## P2: display and camera completeness

- Implement connector ownership and per-output lifecycle before dual output, physical portrait, mode/refresh and blanking enforcement. Shared profile assignment is complete; these physical capabilities remain separate.
- Complete synchronized rotation, whole-wall playlists, deliberate offline reflow/placeholders and image content without disturbing fixed feeds.
- Qualify Media1 across vendors; then add scoped WS-Discovery, Media2 and PTZ/presets. PTZ is unimplemented and requires a physical compatibility target.
- Add optional authenticated local MSE/WebRTC viewing through a relay, with upstream connection/resource budgets, idle cleanup and browser/codec validation.
- Resolve audio, native sizing, borders, OMX labels/crop and snapshots according to demonstrated need and backend feasibility.

## P2: shared use and operations

- Complete account administration, viewer/operator/admin permissions and scoped revocable integration credentials.
- Add bounded secret-free audit/health history and useful outage/recovery alerts. The new observation helper is a starting point, not a monitoring service.
- Preserve dirty drafts through session reauthentication; finish canvas keyboard, screen-reader, touch and focus behavior.
- Qualify repeatable OS/media/driver dependency sets and sign published releases. A Python runtime inventory is not a complete cross-platform lock or license clearance.

## P3: integrations and fleet

Home Assistant, MQTT, event actions, CEC, Stream Deck and GPIO should follow scoped authorization and stable operation ownership. Fleet health/configuration must preserve each wall's operation during controller outages. A custom native renderer needs measured evidence that the existing design cannot satisfy a defined requirement.

## Stable release gate

Publish measured compatibility and recovery records, complete the [hardware test plan](docs/hardware-test-plan.md), and review security, licensing, accessibility and internationalization. This source update remains an unpublished candidate.
