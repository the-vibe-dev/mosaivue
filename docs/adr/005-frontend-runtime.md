# ADR 005: Dependency-light TypeScript browser application

- Status: Accepted
- Date: 2026-10-02

## Context

The specification suggests React/Vite but allows technically superior maintained choices. Mosaivue runs on low-power, often offline appliances and needs a long-lived editor UI without requiring a JavaScript package ecosystem at runtime.

## Decision

Use modular TypeScript compiled to native ES modules with no frontend runtime dependency. Implement reusable rendering, routing, dialogs, API state, and the editor as focused modules. The release ships prebuilt static assets.

## Consequences

The bundle is small and starts quickly on Pi hardware. The code must maintain its own component discipline and DOM lifecycle rather than relying on a virtual DOM. TypeScript compile and browser E2E tests are required for changes.
