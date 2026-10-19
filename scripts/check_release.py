#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "README.md",
    "docs/index.md",
    "docs/beta-release.md",
    "docs/branding.md",
    "BUILD-VERIFICATION.md",
    "LICENSE",
    "NOTICE",
    "THIRD_PARTY_NOTICES.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "ROADMAP.md",
    "install.sh",
    "installer/install-local.sh",
    "uninstall.sh",
    "systemd/mosaivue-server.service",
    "systemd/mosaivue-renderer.service",
    "systemd/mosaivue-rockchip-devices.conf",
    "scripts/rockpi-smoke.py",
    "src/mosaivue/api/app.py",
    "src/mosaivue/renderer/gstreamer.py",
    "src/mosaivue/static/index.html",
    "src/mosaivue/static/assets/app.js",
    "src/mosaivue/static/assets/styles.css",
    "src/mosaivue/static/brand/mosaivue-logo.png",
    "src/mosaivue/static/brand/mosaivue-icon.png",
    "docs/openapi.json",
    "docs/images/dashboard.png",
    "docs/images/layout-editor.png",
    "docs/images/remote-mobile.png",
    "packaging/dependency-licenses.spdx.json",
    "frontend/src/editor.ts",
    "frontend/src/brand/mosaivue-logo.png",
    "frontend/src/brand/mosaivue-icon.png",
    "tests/integration/test_api.py",
]

FORBIDDEN_SOURCE_PATTERNS = {
    "TODO/FIXME marker": re.compile(r"\b(?:TODO|FIXME|XXX)\b", re.IGNORECASE),
    "placeholder API response": re.compile(r"placeholder[_ -]?response", re.IGNORECASE),
    "hardcoded RTSP password": re.compile(r"rtsp(?:s)?://[^\s:'\"]+:[^@\s'\"]+@", re.IGNORECASE),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-only", action="store_true")
    args = parser.parse_args()
    errors: list[str] = []
    required = [p for p in REQUIRED if not args.frontend_only or p.startswith(("frontend/", "src/mosaivue/static/"))]
    for item in required:
        path = ROOT / item
        if not path.exists() or (path.is_file() and path.stat().st_size == 0):
            errors.append(f"missing or empty: {item}")

    project_version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    source_version = re.search(r'^__version__ = "([^"]+)"$', (ROOT / "src/mosaivue/version.py").read_text(), re.M)
    if source_version is None or source_version.group(1) != project_version:
        errors.append("Python package and source versions differ")
    frontend_version = json.loads((ROOT / "frontend/package.json").read_text())["version"]
    if frontend_version != re.sub(r"b(\d+)$", r"-beta.\1", project_version):
        errors.append("Frontend and Python beta versions differ")
    for private_path in (".pi", ".env", "rollout", "mosaivue.db"):
        if (ROOT / private_path).exists():
            errors.append(f"private runtime artifact in release tree: {private_path}")

    scan_roots = [ROOT / "frontend" / "src"] if args.frontend_only else [ROOT / "src" / "mosaivue", ROOT / "frontend" / "src"]
    for scan_root in scan_roots:
        for path in scan_root.rglob("*"):
            if not path.is_file() or path.suffix not in {".py", ".ts", ".js"}:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for label, pattern in FORBIDDEN_SOURCE_PATTERNS.items():
                for match in pattern.finditer(text):
                    # Test fixtures and documented redaction examples are allowed outside production source.
                    errors.append(f"{label}: {path.relative_to(ROOT)}:{text.count(chr(10), 0, match.start()) + 1}")

    static_app = ROOT / "src/mosaivue/static/assets/app.js"
    static_css = ROOT / "src/mosaivue/static/assets/styles.css"
    if static_app.exists() and static_app.stat().st_size < 10_000:
        errors.append("built app.js is unexpectedly small")
    if static_css.exists() and static_css.stat().st_size < 20_000:
        errors.append("built styles.css is unexpectedly small")

    for source in [ROOT / "frontend" / "index.html", *(ROOT / "frontend" / "src").glob("*.ts")]:
        for asset in re.findall(r"/brand/([A-Za-z0-9._-]+)", source.read_text(encoding="utf-8")):
            if not (ROOT / "frontend" / "src" / "brand" / asset).is_file():
                errors.append(f"missing brand asset {asset} referenced by {source.relative_to(ROOT)}")

    if errors:
        print("Release check failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print("Release check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
