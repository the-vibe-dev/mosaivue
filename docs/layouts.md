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

Saving creates a revision. Applying validates references and sends the revision to the renderer without rebooting. Unchanged branches stay running. If activation fails, the database does not discard the last active layout.

## Aspect modes

- `contain`: preserve aspect ratio and letterbox.
- `cover`: preserve ratio and crop.
- `stretch`: fill the rectangle.
- `native`: minimize scaling where practical.
