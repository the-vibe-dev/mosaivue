# ADR 003: Normalized persisted geometry

- Status: Accepted
- Date: 2026-10-02

## Context

Absolute displaycameras rectangles are difficult to author and do not adapt to a new monitor resolution.

## Decision

Persist `x`, `y`, `width`, and `height` in the inclusive 0–1 display coordinate space. Convert to pixels at render time. Retain an optional explicit pixel override for advanced users.

## Consequences

Layouts are responsive across 1080p, 1440p, and 4K. Rounding must be deterministic and clamped at display edges. The editor can still expose exact normalized percentages and pixel previews.
