# Mosaivue frontend review and implementation

Scope: the supplied 0.1.0b2 archive, browser control plane, layout editor, forms, navigation, and browser-test coverage. Implementation lives in the shared source tree. This report is intended to be incorporated into the main report; hardware and competitor research are owned by the other reviewers.

## Results

The original UI was attractive and functionally broad, but several ordinary edits silently discarded configuration, and some backend capabilities had no usable UI. The most consequential fixes preserve camera profile identity and secrets, prevent loss of dirty layout changes, preserve rotation configuration, and make manual stream selection functional. Added practical workflows are ONVIF onboarding, schedules, camera duplication, layout duplication, and more useful camera filtering.

## Confirmed defects fixed

| Priority | Finding | Consequence and implementation |
|---|---|---|
| High | Camera edit reconstructed profile objects without `id`, `codec`, `fps`, or `bitrate`, and replaced priority with the table index. | Saving an otherwise unchanged camera could replace profile identifiers and break layouts/rotation entries that explicitly selected them. The browser now merges editable values into the original profile and preserves identifiers, metadata, and priority. The backend reviewer separately fixed in-place profile persistence/reference integrity. `frontend/src/pages.ts:188`, `forms.ts:4`. |
| High | Camera form trimmed passwords and sent an empty explicit password on creation. | Leading/trailing spaces in a real secret were altered, and an embedded URL password could be overridden by `password: ""`. Passwords are now read verbatim; empty values are omitted so stored/embedded credentials remain available. Explicit removal uses the existing `clear_credentials` contract. `pages.ts:188`, `forms.ts:9`. |
| High | Rotation editor recreated every entry with weight 1 and no profile, ordered by the alphabetically returned camera list, reset start position to zero, and discarded the synchronization-group field. | A simple rename changed playback order and selection semantics. The editor now preserves original order and fields, provides explicit up/down ordering, weights and stream-profile controls, and exposes the start position. The synchronization field is preserved for compatibility, without advertising actual synchronized playback. `pages.ts:391`, `forms.ts:25`. |
| High | Layout edits had no dirty-state tracking or leave guard. | Clicking Back to layouts, another route, browser Back, reload or close could discard work with no indication. The editor now shows Saved/Unsaved changes, guards internal and history navigation, installs the browser unload warning, and confirms explicit Revert. Save disables interaction while its request is pending. `editor.ts:63`, `router.ts:5`. |
| Medium | Manual stream selection offered only an automatic/manual switch, without a profile selector; replacing a camera retained an old camera's profile. | Users could not select the promised manual profile, or could save a profile reference belonging to another camera. The inspector now provides actual profiles, selects the camera's first profile on entering manual mode, and clears stale references when changing camera/type. `editor.ts:252`, `editor.ts:464`. |
| Medium | Locked tiles could still be deleted, changed through the inspector, moved during a mixed drag/align/distribute operation, or replaced with another camera. | Lock was only partially enforced. Those mutators now preserve locked tiles; geometry/property fields are disabled while locked. Applying a template requires unlocking first. Duplication is still permitted because it creates a separate copy. `editor.ts:332`, `editor.ts:580`. |
| Medium | Entering 100% for X/Y could collapse width/height to zero; a blank number field could write NaN. | Invalid geometry was serialized or rejected later by the API. Position edits now clamp against the existing width/height; size stays positive; non-finite input is ignored. `forms.ts:30`, `editor.ts:499`. |
| Medium | Dialog Close/Cancel buttons were submit controls inside required-field forms. | Empty/invalid forms could prevent Cancel/Close, and Enter could submit the wrong control. Shared dialogs and the password dialog now use explicit non-submit cancellation controls; only Save submits. Shared dialog callbacks report errors without unhandled rejection or loss of input. `ui.ts:94`, `app.ts` password dialog. |
| Medium | API error code tried `response.json()` then `response.text()` on the same already-consumed body. Validation arrays became `[object Object]`. | Proxy/plain-text errors could mask the real failure with a body-consumed exception; field validation was unhelpful. The response is now read once; validation messages include field paths; HTML failures use the HTTP status. `api.ts:13`. |
| Medium | All asynchronous route handlers wrote into the same live DOM node; a delayed dashboard refresh could replace another route. | Slow requests could paint the wrong screen after navigation. Each page now gets its own child root, so stale responses update detached content. Delayed dashboard/remote refreshes verify they still own the active page, and a late editor load cannot mount onto a detached target. `pages.ts:13`, `pages.ts:360`. |
| Low | Camera profile labels displayed width as progressive resolution (e.g. `1920p`). | Corrected to width × height. Probe resolution displays “Not reported” when dimensions are absent, rather than an empty multiplication sign. |
| Low | Preview completion could create an unreleased blob URL after a dialog/editor was destroyed. | Disconnected/destroyed previews are ignored and obsolete URLs are released. Download URLs are released after the browser can start consuming them. |
| Low | Dashboard retry used an inline `onclick`, conflicting with the app's script policy. | Replaced with a normal retry link. |

## Added usable capabilities

1. **ONVIF Media1 onboarding.** Cameras now has Import ONVIF. The modal takes a device service endpoint, camera name, and optional ONVIF credentials; Inspect profiles calls `/api/v1/onvif/profiles`; the user selects profiles; Import calls `/api/v1/onvif/import`. Warnings and codec/resolution metadata are visible. Changing endpoint/credentials requires a fresh inspection. Secret values stay in the dialog's in-memory state; they are not written to browser storage. This is endpoint-based onboarding, not multicast discovery, PTZ, or a Media2 implementation. Root owns the service, API, and protocol fixtures.
2. **Schedules screen.** Added navigation and complete create/edit/enable/disable/delete actions against existing `/schedules`. Supports selected start days, overnight windows, priorities, and equal-time 24-hour windows, with explicit appliance-timezone wording and overlap/last-layout behavior. The renderer reviewer fixed matching semantics separately.
3. **Camera duplication.** Uses the existing duplicate endpoint, including its deliberate disabled copy. The success message tells the operator to edit its address before enabling.
4. **Camera filters.** Query matches every supplied word across name, host, location, vendor, model, description and tags. Enabled/disabled filters, a live result count, a no-results message, and retained filter values after editing reduce friction with larger camera lists.
5. **Layout duplication.** Creates a separately named draft from the original geometry and configuration, regenerates tile IDs, and retains camera references/display profile. Existing layouts remain unchanged.
6. **Rotation controls.** Resume is available alongside Pause. Entry reordering, per-camera weights and stream profiles, and start position are accessible without API/CLI work. The legacy placeholder option is marked unavailable for selection and described as hold-compatible when already present, because a rendered failure placeholder remains unimplemented.

## Validation completed by this reviewer

- `npm ci --ignore-scripts`: succeeded (one TypeScript development dependency).
- `npm run build`: succeeded with strict TypeScript compilation.
- `npm test`: **20 passed**, increased from the original 3 tests. New cases verify profile identity/metadata, password whitespace/omission, camera filtering, rotation order/weights/profiles, on-canvas geometry, locked mutation behavior, dirty undo state, manual profile selection and stale-profile clearing, field-specific API errors, plain-text proxy failures, and CSRF preservation.
- `python -m ruff check tests/e2e/test_control_workflows.py`: passed.
- `python -m pytest -q tests/frontend tests/e2e`: **1 passed, 5 skipped**. The five browser workflows require `MOSAIVUE_E2E_URL`; they were not executed in this reviewer's environment. This is not a browser-pass claim.
- Compiled files were copied into `src/mosaivue/static` after the final build. The package can serve the updated UI without a Node installation at runtime.

Added four browser regression scenarios in `tests/e2e/test_control_workflows.py`, alongside the existing editor smoke test. They are intended for a disposable seeded appliance, and cover:

- Empty camera-name form can Cancel; saving a camera preserves profile IDs and probe metadata; no-results filtering renders correctly.
- An initially disabled overnight schedule can be created, edited, inspected through the API, and deleted.
- Dirty layout navigation can be canceled, then explicitly discarded.
- Empty ONVIF dialog can Cancel; mobile navigation reaches Schedules without JavaScript page errors.

The root reviewer owns actual rendered browser QA and should replace the skipped status with observed results only if run. The frontend testing and Browser skills were read; this reviewer deliberately did not start a separate browser session to avoid competing with root QA.

## Suggested browser acceptance sequence

1. On desktop, open Cameras; verify host/vendor search and enabled filter; open Add camera and press Cancel with required fields empty.
2. Edit a camera with main/sub profiles; save a name-only edit; verify IDs, codec/FPS/bitrate and an existing manual-profile layout survive.
3. Open Import ONVIF; inspect the supplied deterministic ONVIF fixture; select streams; import; verify a standard camera appears. Retry wrong endpoint/credentials and confirm a usable error without discarding typed input.
4. Open a seeded layout; choose a tile and manual profile; change label; click Back to layouts and dismiss the discard prompt; verify canvas remains. Repeat and accept. Check browser Back as well.
5. Use a mixed locked/unlocked selection; drag, delete, align and inspect without mutating the locked tile. Enter X/Y=100 and a blank size without producing invalid geometry.
6. Edit a preexisting rotation group with nonalphabetic order, weights, explicit profiles and nonzero start; change only its name and verify those values persist. Confirm Pause/Resume success and error states.
7. Create/edit/disable/delete an overnight schedule; confirm the supplied Monday start day is shown as continuing into Tuesday.
8. Repeat the essential navigation and dialogs at 390×844 and inspect clipping, modal scrolling and keyboard focus. Inspect browser console errors and screenshot the new screens.

## Remaining product/frontend gaps

- The browser is an administration/remote surface with JPEG previews; it is not a full browser live-video wall. Multi-stream WebRTC/HLS viewing is a separate service/transport and resource-budget project.
- No ONVIF network discovery, Media2, PTZ or audio control UI is included. Media1 compatibility needs real-device tests with cameras that use different ONVIF accounts, authentication variants and firmware.
- The layout editor remains a custom mouse/touch visual canvas. Keyboard operations exist, but a full accessibility audit, keyboard selection model, accessible geometry announcements, focus management during complete rerenders, and screen-reader testing remain advisable.
- Named reusable templates and edge-to-edge snapping presets remain useful follow-up work. Uniform 2×2, 3×3 and 4×4 templates were added in the final implementation pass.
- Session expiry presently surfaces an API error; preserving a dirty editor through a seamless reauthentication dialog remains an improvement.
- The UI still has long template functions in `pages.ts`. New ONVIF/schedules/form logic was split into modules, but broader component extraction should follow real interaction tests, not a cosmetic rewrite.
- No controller-side multi-user optimistic concurrency contract was added by this reviewer; two administrators editing the same object still need explicit conflict/version behavior from the backend.
- True synchronized rotation groups and visual placeholder failure mode remain backend gaps. The UI preserves compatibility fields and no longer invites selecting unsupported placeholder behavior.
- Hardware-facing preview, rotation, schedule activation, display profile and focus behavior require on-device qualification even if the UI/API tests pass.

## Final integration additions

- Added equal-sized 2×2, 3×3 and 4×4 grid templates in both the layout creation dialog and editor, alongside the featured-camera templates. They reuse the existing camera/slot preservation, locked-tile guard, extra-tile confirmation, and undo history. Two new JavaScript tests verify exact tile counts, positive/in-bounds dimensions, complete coverage, no pairwise overlap and rejection of unsupported sizes. Final JavaScript total: **20 passed**.
- Backup restore now shows a persistent result panel and warning toast when configuration restoration succeeds but `renderer_applied` is false or `renderer_warning` is present. The operator can open Renderer directly; the UI no longer presents incomplete display application as an unqualified success. Selecting the same backup file again also works.
- Root reported rendered-browser execution **blocked**: local Chromium's process-singleton socket creation fails with EPERM because AF_UNIX sockets are prohibited, and extension/cloud browsers cannot reach the private test server. Neither the browser workflows nor physical playback are claimed as passed.

### Final download regression fix

The sanitized JSON export endpoint returns `application/json`, so the shared API helper parsed it into an object. The download helper previously treated that object as a Blob and would pass it to `URL.createObjectURL`, which rejects it. The helper now serializes JSON into an `application/json` Blob while leaving binary backup responses untouched. Two new focused tests verify actual JSON content, exact encrypted-backup fixture bytes, filenames, authenticated POST/CSRF options, and delayed object-URL cleanup. Strict typecheck/build passed and the final JavaScript suite has **20 passing tests**. This is runtime unit verification using browser-API substitutes, not a rendered-browser pass.

The edge-of-screen renderer geometry issue was also fixed separately in `renderer/geometry.py` and `tests/unit/test_geometry.py`: normalized and pixel-override origins/sizes are clamped to the physical output with positive dimensions. Eleven focused geometry tests passed.
