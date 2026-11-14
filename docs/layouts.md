# Layouts

Layouts persist normalized geometry so the same arrangement can adapt to 1080p, 1440p, or 4K.

```json
{
  "x": 0.0,
  "y": 0.0,
  "width": 0.5,
  "height": 1.0
}
```

At runtime those values are converted to the selected output's pixels. Advanced users may add a pixel override.

## Slot types

- `fixed`: always shows one camera.
- `manual`: shows a selected saved camera and can be switched without editing files.
- `rotation`: cycles one independent rotation group.
- `empty`: reserves a background region.

## Editor controls

The browser editor supports camera drag/drop, move, resize, grid and edge snapping, exact coordinates, multi-selection, alignment, distribution, duplication, deletion, lock, source/profile/aspect settings, and keyboard copy/paste/undo/redo.

Saving creates a revision. Applying validates references and sends the revision to the renderer without rebooting. Unchanged branches stay running where supported. Synchronous activation failure attempts to retain the previous wall; successful acceptance alone does not verify decoded frames or physical output.

Layouts, Editor, Dashboard and Remote distinguish the saved revision from the renderer-reported revision. **Saved changes pending** offers **Apply saved changes**; a matching revision retains **Reapply** because camera/group settings can change independently. Missing renderer status remains unknown. Focus is a temporary view; restoring it returns to the prior wall revision, while applying a layout selects its newest saved revision. If saving succeeds and application fails, the editor keeps the saved revision and retries only application.

Fixed pixel overrides take precedence over relative geometry on the physical display. The inspector identifies this condition and offers **Use canvas placement**. Deliberate geometry/template/copy operations clear the old override; nongeometry edits preserve it, and Undo restores it. On smaller screens, use **Cameras** and **Tile** to open the library and inspector drawers.

## Aspect modes

- `contain`: preserve aspect ratio and letterbox.
- `cover`: preserve ratio and crop.
- `stretch`: fill the rectangle.
- `native`: stored for compatibility, but currently falls back to contain/letterbox in physical backends. The editor disables it when unsupported.

## Concurrent editing and display profiles (b5)

The editor sends the revision number and revision UUID it loaded when saving, restoring history or applying. A stale operation returns HTTP 409; local changes remain available for explicit reload or Save as copy. Name, description and profile-association saves also advance history. Legacy API callers can omit the guards but retain last-writer-wins behavior.

A layout can use a shared display profile or custom dimensions. The profile's width/height take precedence over LayoutData dimensions, matching the renderer. The editor, layout list, dashboard and remote use that order for schematic previews. Shared profiles can be created and edited on the Display page; unsupported physical metadata is preserved. Profile deletion is blocked while layouts reference it. Shared profile edits require deliberate reapplication of affected walls and do not create a new revision for every layout.

Apply pins the requested geometry revision and row identity. A newer draft saved during application remains pending. The profile association and referenced camera/group/profile contents are still mutable, so this is not a complete configuration snapshot. Historical restore retains current layout name, description and profile association. A renderer-accepted request followed by an import/deletion race is reported explicitly; reload and inspect the actual wall before another apply.
