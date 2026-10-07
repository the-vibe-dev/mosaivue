# API

Interactive OpenAPI documentation is served at `/api/docs`; the live schema is `/api/openapi.json`. A generated release snapshot is stored in `docs/openapi.json`.

The versioned base path is `/api/v1`.

Core resources:

```text
/auth
/status and /system
/cameras
/layouts
/rotation-groups
/display
/renderer
/schedules
/logs
/backup
/update
/events
```

Authentication uses the `mosaivue_session` cookie. State-changing browser/API requests must also send `X-CSRF-Token`, returned by login/setup and `/auth/me`.

Examples after obtaining a session and CSRF token:

```bash
curl -b cookies.txt http://mosaivue.local:8080/api/v1/layouts
curl -b cookies.txt -H "X-CSRF-Token: $CSRF" \
  -X POST http://mosaivue.local:8080/api/v1/layouts/LAYOUT_ID/activate
curl -b cookies.txt -H "X-CSRF-Token: $CSRF" \
  -H 'Content-Type: application/json' \
  -d '{"camera_id":"CAMERA_ID","aspect_mode":"cover"}' \
  http://mosaivue.local:8080/api/v1/renderer/focus
curl -b cookies.txt -H "X-CSRF-Token: $CSRF" \
  -X POST http://mosaivue.local:8080/api/v1/renderer/restore
```

`/events` is an authenticated Server-Sent Events stream for renderer state, camera health, layout activation, and rotation changes.
