#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import tomllib
from importlib import metadata
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def spdx_id(name: str) -> str:
    return "SPDXRef-Package-" + re.sub(r"[^A-Za-z0-9.-]+", "-", name).strip("-")


def declared_license(distribution: metadata.Distribution) -> str:
    meta = distribution.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression.strip()
    license_text = (meta.get("License") or "").strip()
    if license_text and "\n" not in license_text and len(license_text) < 120:
        return license_text
    classifiers = meta.get_all("Classifier") or []
    values = [item.split(" :: ")[-1] for item in classifiers if item.startswith("License ::")]
    return " AND ".join(sorted(set(values))) if values else "NOASSERTION"


def package_record(distribution: metadata.Distribution) -> dict[str, Any]:
    name = distribution.metadata.get("Name") or distribution.name
    return {
        "SPDXID": spdx_id(name),
        "name": name,
        "versionInfo": distribution.version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": declared_license(distribution),
        "copyrightText": "NOASSERTION",
        "homepage": distribution.metadata.get("Home-page") or distribution.metadata.get("Project-URL"),
    }


def runtime_dependency_graph() -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    direct = [Requirement(item) for item in project.get("dependencies", [])]
    queue: list[tuple[str, str]] = [("Mosaivue", req.name) for req in direct]
    seen: set[str] = set()
    packages: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    missing: list[str] = []

    while queue:
        parent, requested_name = queue.pop(0)
        key = canonicalize_name(requested_name)
        relationships.append(
            {
                "spdxElementId": spdx_id(parent),
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdx_id(requested_name),
            }
        )
        if key in seen:
            continue
        seen.add(key)
        try:
            distribution = metadata.distribution(requested_name)
        except metadata.PackageNotFoundError:
            missing.append(requested_name)
            packages.append(
                {
                    "SPDXID": spdx_id(requested_name),
                    "name": requested_name,
                    "versionInfo": "NOT-IN-BUILD-ENVIRONMENT",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "licenseConcluded": "NOASSERTION",
                    "licenseDeclared": "NOASSERTION",
                    "copyrightText": "NOASSERTION",
                }
            )
            continue

        packages.append(package_record(distribution))
        parent_name = distribution.metadata.get("Name") or requested_name
        for raw in distribution.requires or []:
            try:
                requirement = Requirement(raw)
            except Exception:
                continue
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            queue.append((parent_name, requirement.name))

    packages.sort(key=lambda item: str(item["name"]).casefold())
    unique_relationships = {
        (item["spdxElementId"], item["relationshipType"], item["relatedSpdxElement"]): item
        for item in relationships
    }
    return packages, sorted(unique_relationships.values(), key=lambda item: tuple(item.values())), sorted(set(missing))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packaging/dependency-licenses.spdx.json"),
    )
    args = parser.parse_args()
    packages, relationships, missing = runtime_dependency_graph()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    mosaivue = {
        "SPDXID": spdx_id("Mosaivue"),
        "name": "mosaivue",
        "versionInfo": version,
        "downloadLocation": "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "Apache-2.0",
        "licenseDeclared": "Apache-2.0",
        "copyrightText": "See NOTICE",
    }
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "Mosaivue Python runtime dependency inventory",
        "documentNamespace": f"https://github.com/the-vibe-dev/mosaivue/spdx/{version}",
        "creationInfo": {
            "creators": ["Tool: mosaivue-license-inventory"],
            "licenseListVersion": "3.25",
        },
        "packages": [mosaivue, *packages],
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": spdx_id("Mosaivue"),
            },
            *relationships,
        ],
        "annotations": [
            {
                "annotationType": "OTHER",
                "annotator": "Tool: mosaivue-license-inventory",
                "annotationDate": "1970-01-01T00:00:00Z",
                "comment": (
                    "Generated from pyproject runtime requirements and installed distribution metadata. "
                    "Review operating-system GStreamer/FFmpeg components and frontend build tools separately."
                ),
            }
        ],
        "missingFromBuildEnvironment": missing,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
