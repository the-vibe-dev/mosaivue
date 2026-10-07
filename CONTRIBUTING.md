# Contributing to Mosaivue

Thank you for helping build a reliable, local-first camera wall.

## Ground rules

- Preserve local-first operation. Do not add telemetry, cloud accounts, or unrelated external calls.
- Never log or return RTSP passwords, master keys, session tokens, password hashes, or unredacted URLs.
- Keep the core Apache-2.0 compatible. Do not copy GPL code into the core. A GPL legacy component must be isolated and clearly licensed.
- Avoid fake implementations. Production controls must perform real operations; mocks belong only in tests.
- Prefer incremental renderer changes that do not restart unaffected streams.
- Keep normalized geometry as the persisted source of truth. Pixel overrides are an explicit advanced option.

## Development setup

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e '.[dev]'
cd frontend
npm run build
cd ..
cp -a frontend/dist src/mosaivue/static
pytest
```

Install GStreamer, PyGObject, and FFmpeg from the operating system. See `docs/development.md`.

## Pull requests

A pull request should include:

1. The problem and operational impact.
2. The implementation and any architectural tradeoff.
3. Tests for success, failure, and credential redaction where applicable.
4. Hardware evidence for renderer changes, including platform, OS, output mode, codecs, stream count, CPU, memory, FPS, and switch latency.
5. Documentation updates for user-visible behavior.
6. A licensing note for new dependencies or reused source.

Run before submission:

```bash
pytest
cd frontend && npm run typecheck && npm test && npm run build
python -m compileall -q src
python scripts/check_release.py
```

## Architecture decisions

Material changes to renderer topology, storage, security boundaries, coordinate semantics, process separation, or licensing require an ADR under `docs/adr/`.

## Commit style

Use focused commits with an imperative subject, for example:

```text
renderer: reconnect one stalled branch without rebuilding compositor
web: preserve multi-selection during exact geometry edits
security: redact embedded credentials from probe errors
```

## Hardware reports

Use the camera/renderer/performance issue templates. Sanitized support bundles are produced with:

```bash
mosaivue support-bundle
```

Inspect the archive before attaching it. It is designed not to include secrets, but operators remain responsible for the data they publish.
