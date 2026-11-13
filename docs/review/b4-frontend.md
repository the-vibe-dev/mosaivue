# Mosaivue 0.1.0b4 candidate — frontend follow-up review

Date: 2026-11-13. Reviewed the newly supplied 0.1.0b3 source and prior review documents, then implemented bounded improvements for the 0.1.0b4 candidate. Scope was the administration UI, layout editor, frontend tests, browser-test source, and compiled static assets. This is an incremental review of the supplied b3 changes, not a claim that the earlier b2 review was repeated from scratch.

## Result

The most consequential remaining UI defect was a false equivalence between a layout being marked active in the database and its newest saved revision being applied by the renderer. An operator could save a draft for the active wall, leave the editor, see it described as active/on display, and find the Apply button disabled. Camera and rotation edits also lacked a clear route to reapply their settings. The candidate now distinguishes saved revisions, renderer-reported revisions, temporary camera focus, and unavailable status; an already applied layout remains explicitly reapplicable.

Unsupported physical-player features are now exposed as a capability matrix and gated in the relevant controls. This changes the honesty and usability of the UI; it does not implement missing playback capabilities. JSON configuration exports can now be imported through the UI, and the mobile layout editor has controls to open its previously inaccessible camera and inspector drawers.

## Confirmed findings and changes

| ID | Priority | Finding | Change and evidence |
|---|---|---|---|
| FE2-01 | P1 | Layouts disabled Apply whenever `layout.active` was true, even if `current_revision` was newer than `renderer.active_revision`. | `display-state.ts` compares reported layout ID and revision. `pages.ts` now shows Saved changes pending and an enabled Apply saved changes action. A matching applied revision offers Reapply. Missing status remains unknown, and a renderer newer than the loaded page is identified as a stale view. Six focused state/capability tests include revision mismatch, focus, unknown and stale state. |
| FE2-02 | P1 | Editor, Dashboard and Remote described the saved active layout as displayed without accounting for a different applied revision or temporary camera focus. | The shared revision model drives all four surfaces. The dashboard no longer presents geometry from a newer saved revision as the running wall, or shows a wall preview while a camera is focused. Remote distinguishes Restore previous wall from applying the latest saved revision, and explains that schedules can replace a manual choice. |
| FE2-03 | P1 | A successful draft save followed by failed application produced a generic error. Retrying Save & apply created another unnecessary revision. | Editor save and apply outcomes are tracked separately. A persistent error states that the revision is saved but application failed; the saved baseline remains clean, and retry sends only the activation request. A failed save retains dirty work and never activates. Two runtime unit tests simulate these request sequences and inspect preserved content, request counts, error state and final renderer revision. |
| FE2-04 | P1 | Camera and rotation save success messages implied completion without explaining that running stream specifications might still use prior settings. | Cameras and Rotation groups now have persistent explanatory text linking to Layouts; save messages explicitly call for applying/reapplying the affected wall. Layouts explains that reapplication restarts streams and ends focus. This deliberately does not invent a cross-session pending flag for camera/group changes: there is no authoritative applied-generation contract for those objects. |
| FE2-05 | P1 | UI controls offered native-size playback, labels on OMXPlayer, connector selection, display rotation, refresh-rate changes and per-profile blanking control without evidence those features worked. | The renderer reviewer added `capabilities.feature_support` and `limitations` to status and backend listings. Frontend types and `display-state.ts` consume those fields. Renderer shows thirteen implementation capabilities for each backend with explicit Supported / Not supported / Not reported states and backend limitations. Editor gates native-size selection and label controls. Display profile creation gates unsupported output, rotation, refresh and blanking controls while leaving working dimensions editable. Existing saved values remain visible/preserved. `display.ts` contains the focused display-profile workflow. |
| FE2-06 | P1 | Imported `pixel_override` could silently override normalized drag, numeric, template, alignment and duplication edits on the physical display. | The inspector identifies fixed-pixel placement and explains that the canvas shows relative geometry. An explicit Use canvas placement action clears the override. Deliberate geometry operations, templates and copied placement clear stale overrides; nongeometry edits retain them. Undo restores the full saved override. The focused geometry/template regression verifies this behavior. Locked tiles remain protected. |
| FE2-07 | P1 | Below 900px, CSS moved the camera library and inspector offscreen but the editor had no controls to open them. | Added Cameras/Tile toggle buttons with expanded state and controlled-region identifiers, close actions, visible drawer states, and a responsive toolbar. Hidden drawers are not keyboard-visible. Drawers are positioned within the workspace so the status banner does not obscure them. A browser scenario now checks opening and closing both drawers at 390×844. This scenario is not claimed as executed here. |
| FE2-08 | P2 | Backup offered a sanitized JSON download but the restore picker accepted only ZIP/CWBACKUP and always sent multipart archives. | Added a bounded JSON import path through existing `/backup/import`; archive bytes still go unchanged to `/backup/restore`. JSON size is checked before reading (32 MiB), top-level shape must be an object, and archive size is bounded to 100 MiB. Merge is the default; replacement states what it removes and requires an explicit confirmation. JSON imports preserve renderer warnings in the same persistent result panel. Four unit tests cover JSON content/mode, binary bytes and exact passphrase, invalid/oversized input, and renderer warnings. |
| FE2-09 | P2 | Layout-service errors use `{detail:{errors:[...],warnings:[...]}}`, which the shared API formatter reduced to a generic HTTP error. | `apiErrorMessage` now displays the service's concrete validation errors. A regression verifies multiple layout validation messages. Existing Pydantic-array, text, HTML-proxy and CSRF tests continue to pass. |
| FE2-10 | P2 | A delayed renderer-player refresh could call `rendererPage()` after the user navigated elsewhere. | The delayed refresh now checks both the route and the connected render target, matching the earlier Dashboard guard. |

## Important behavior decisions

“Applied” means the renderer accepted the revision; it is not a claim that the first decoded frame or the physical HDMI output has been verified. The UI directs the operator to stream health for playback evidence. The existing backend acceptance/readiness limitations remain separate.

Camera focus retains the renderer's wall ID/revision for restoration. The UI therefore labels focus separately and explains that Restore previous wall returns to that revision, whereas applying a layout loads its latest saved revision. Reapply is intentionally enabled even when the layout revision matches because camera or rotation settings can have changed independently.

Unavailable capability data remains unknown. Player availability is independent from implemented feature support. Unsupported saved settings are retained for compatibility; controls no longer invite new choices that the running player reports it cannot implement. The display profile table labels stored metadata rather than suggesting that every stored value is physically enforced.

The editor remains a schematic editing preview. For fixed-pixel imports, the inspector explicitly distinguishes the saved fixed-pixel placement from the relative canvas geometry before geometry edits replace it. For a player without label support, on-canvas labels are described as editing aids. A fully pixel-faithful preview of every renderer behavior is still outside this change.

Configuration backup wording now describes configuration scope rather than a whole-appliance backup. OS files, user accounts and installation settings need a separate system backup. Existing encrypted download handling and exact credential whitespace are preserved.

## Validation performed here

| Check | Observed result |
|---|---|
| `npm ci --ignore-scripts` | Passed; installed the existing TypeScript development dependency. No new frontend dependency added. |
| `npm run typecheck` | Passed with strict TypeScript settings. |
| `npm run build` | Passed for `mosaivue-frontend@0.1.0-beta.4`. |
| `npm test` | **35 passed, 0 failed, 0 skipped**, increased from 20 in the supplied frontend suite. This is Node runtime testing with browser-API substitutes where needed, not a rendered-browser claim. |
| `python -m ruff check tests/e2e/test_control_workflows.py` | Passed. |
| `python -m pytest -q tests/frontend tests/e2e` | **1 passed, 8 skipped**. The static-asset smoke test passed. The eight browser tests were environment-gated because `MOSAIVUE_E2E_URL` was not configured. |
| Built assets | Copied `frontend/dist` into `src/mosaivue/static`; **36 files byte-verified** against the build output. |
| Rendered browser QA | **Not executed in this candidate review.** Root rechecked the AF_UNIX prerequisite and received `PermissionError: Operation not permitted`. No repeat Chromium launch was attempted after that prerequisite failure. |
| Hardware/HDMI tests | Not performed by this reviewer. Supplied b3 browser/Pi evidence must remain clearly attributed to that prior environment and version. |

The build command also performs TypeScript compilation. The final text-only state-label adjustment was included in the last successful build and static copy; all runtime behavior tests passed in the immediately preceding suite.

The frontend testing skill was read. Root owns browser qualification to avoid competing sessions. Since the current browser prerequisite is blocked, page identity, visual layout, console health, screenshots and rendered interactions are unverified here. No screenshot or responsive-pass claim is made from source inspection or unit tests.

## Browser scenarios added or adjusted

The flow under test is: Layouts → newer saved revision → Apply saved changes → renderer reports that revision → enabled Reapply. The added browser test intercepts the renderer/activation APIs with a deterministic state; it validates the UI contract without asserting real HDMI playback.

The second flow is Backup → choose JSON → merge → validated import result with `renderer_applied=false` → persistent display warning. The import API is intercepted so the test cannot replace appliance configuration.

The third flow is Display → New profile → unsupported fields disabled and dimensions editable → Layout editor → unsupported labels/native option disabled → 390×844 viewport → open/close Tile and Cameras drawers. Renderer capabilities are deterministic fixtures.

The existing dirty-navigation test now changes tile geometry instead of labels, since labels are correctly unavailable on the OMXPlayer backend. The five existing browser workflows remain present; the suite now contains eight browser tests in total.

## Remaining frontend/product gaps

1. **Candidate browser qualification is still required.** Run all eight workflows in a disposable seeded environment with a usable browser, then manually inspect desktop and phone layouts, focus/keyboard navigation, canvas sizing, modal scrolling and browser errors. The new mobile drawer and status-banner layout particularly need screenshots before release qualification.
2. **Global pending configuration state remains a backend contract gap.** The UI can compare layout revisions authoritatively. It cannot prove which version of every camera/profile/rotation setting is currently in memory across other users, schedules, restarts or reconnects. A controller-owned applied configuration generation/fingerprint would support a precise global pending indicator.
3. **Readiness is separate from acceptance.** The renderer's successful activation response still needs a stronger first-frame/health acceptance policy for a production-grade “verified live” result. This UI intentionally avoids claiming verified physical playback.
4. **Display profile association is still not a complete UI workflow.** Profiles can be created and their stored dimensions inspected; selecting a profile for a layout is currently an API/configuration workflow. Output connector, multi-output, rotation, refresh and blanking controls remain underlying renderer/OS work despite clearer capability reporting.
5. **Accessibility and editing focus need a full pass.** The custom canvas lacks a comprehensive keyboard selection/announcement model, and complete inspector rerenders can lose focus. Drawer access is fixed, but screen-reader and touch-device qualification remains necessary.
6. **Session expiry and simultaneous editing are unresolved.** The editor guards unsaved navigation, but seamless reauthentication preserving a dirty editor and server-side optimistic concurrency/version conflicts remain future work.
7. **Preview progress and partial results can improve.** Backend now bounds/coalesces decoder work. The UI preserves busy/error detail and retry actions, but does not yet provide a consolidated queue/progress view for many thumbnail requests.
8. **Live browser video, PTZ/Media2/network discovery, synchronized rotation, true failure placeholders, roles/audit history and multi-appliance management remain larger product gaps.** The changes here should not be described as implementing those capabilities.

## Changed frontend surfaces

New focused modules: `frontend/src/display-state.ts`, `display.ts`, `backup.ts`. Updated `api.ts`, `editor.ts`, `forms.ts`, `pages.ts`, `styles.css`, `types.ts`. New tests: `frontend/tests/display-state.test.mjs`, `backup.test.mjs`; additional cases in `api.test.mjs`, `editor.test.mjs`; expanded `tests/e2e/test_control_workflows.py`. Compiled output is synchronized to `src/mosaivue/static`.
