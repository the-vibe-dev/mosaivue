# Development

## Backend

```bash
python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

`--system-site-packages` lets the virtual environment import distribution PyGObject bindings. Unit/API tests do not require a physical display. The in-memory renderer is only enabled in explicit test mode.

## Frontend

The frontend is dependency-light TypeScript compiled to native ES modules. It intentionally avoids a large runtime framework on low-power appliances while preserving typed modules and reusable components.

```bash
cd frontend
npm run typecheck
npm test
npm run build
cd ..
rm -rf src/mosaivue/static
cp -a frontend/dist src/mosaivue/static
```

## Local server

```bash
./scripts/dev.sh
```

The development script stores data under `.dev/`. It does not start a production renderer. Run the test backend or renderer daemon separately when exercising RPC.

## Test categories

- `tests/unit`: schemas, security, services, geometry, backup, migration.
- `tests/integration`: authenticated API and static application.
- `tests/renderer`: backend contract and diff behavior.
- `frontend/tests`: code-native UI helpers.
- hardware tests: manual/automated scripts described in `docs/hardware-test-plan.md`.

## Release checklist

```bash
python -m compileall -q src
pytest
cd frontend && npm run typecheck && npm test && npm run build && cd ..
python scripts/check_release.py
packaging/build-release.sh
```
