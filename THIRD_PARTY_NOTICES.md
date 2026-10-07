# Third-party notices

Mosaivue is distributed under Apache-2.0. It dynamically uses operating-system and Python/JavaScript dependencies under their own licenses. The list below is an engineering inventory, not a substitute for the license files shipped by each dependency.

| Component | Typical license | Role |
|---|---|---|
| FastAPI | MIT | HTTP API and OpenAPI |
| Starlette | BSD-3-Clause | ASGI framework used by FastAPI |
| Uvicorn | BSD-3-Clause | ASGI server |
| SQLAlchemy | MIT | ORM and SQLite access |
| Alembic | MIT | Database migrations |
| Pydantic | MIT | Validation and schemas |
| Typer | MIT | CLI |
| Rich | MIT | CLI rendering |
| Textual | MIT | Terminal UI |
| cryptography | Apache-2.0 OR BSD-3-Clause | AES-GCM and cryptographic primitives |
| psutil | BSD-3-Clause | System metrics |
| PyYAML | MIT | Optional YAML import/export support |
| GStreamer and plugins | LGPL-2.1-or-later, with plugin-specific exceptions/licenses | RTSP, decode, composition, and output |
| PyGObject | LGPL-2.1-or-later | Python GObject/GStreamer bindings |
| FFmpeg | LGPL-2.1-or-later or GPL depending on the distribution build | Probe/fallback multimedia tooling |
| TypeScript | Apache-2.0 | Frontend compiler; not a runtime dependency |

The installer uses the Linux distribution's packages for GStreamer, PyGObject, FFmpeg, and DRM libraries. Their exact feature set and licensing depend on the selected distribution and package build.

Run `python scripts/license_inventory.py --output dependency-licenses.json` in the release virtual environment to generate a version-specific inventory from installed package metadata. Review GStreamer plugin and FFmpeg build flags for the target distribution before redistributing an appliance image.
