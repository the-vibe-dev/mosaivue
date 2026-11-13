"""Validate a complete portable configuration before touching the live database."""
from __future__ import annotations

import copy
import json
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from ..schemas import (
    CameraCreate,
    DisplayProfileIn,
    LayoutCreate,
    LayoutData,
    RotationGroupIn,
    ScheduleIn,
)

MAX_SECTION_ITEMS = 10_000


class BackupValidationError(ValueError):
    """A deliberately input-free explanation suitable for an API response."""



def _section(document: dict[str, Any], key: str) -> list[dict[str, Any]]:
    values = document.get(key, [])
    if not isinstance(values, list) or len(values) > MAX_SECTION_ITEMS:
        raise ValueError(f"Invalid or oversized {key} section")
    ids: set[str] = set()
    names: set[str] = set()
    for raw in values:
        if not isinstance(raw, dict):
            raise ValueError(f"Each {key} entry must be an object")
        identifier = raw.get("id")
        if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
            raise ValueError(f"Every {key} entry requires a valid ID")
        name = raw.get("name")
        if not isinstance(name, str):
            raise ValueError(f"Every {key} entry requires a name")
        if identifier in ids or name in names:
            raise ValueError(f"Duplicate ID or name in {key}")
        ids.add(identifier)
        names.add(name)
    return values


def normalized_export(document: dict[str, Any], format_version: int = 1) -> dict[str, Any]:
    if not isinstance(document, dict) or document.get("format") != "mosaivue-configuration":
        raise BackupValidationError("Not a Mosaivue configuration export")
    if isinstance(document.get("format_version"), bool) or document.get("format_version") != format_version:
        raise BackupValidationError("Unsupported export version; expected version 1")
    # Reject non-JSON and non-finite values even for direct Python service callers.
    try:
        json.dumps(document, allow_nan=False)
        result = copy.deepcopy(document)
        _validate_sections(result)
    except ValidationError as exc:
        errors = [
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False, include_url=False)
        ]
        raise BackupValidationError("Invalid configuration: " + "; ".join(errors)) from exc
    except (ValueError, TypeError) as exc:
        if isinstance(exc, TypeError):
            raise BackupValidationError("Configuration contains invalid JSON values") from exc
        raise BackupValidationError(str(exc)) from exc
    return result


def _validate_sections(result: dict[str, Any]) -> None:
    for key in ("cameras", "display_profiles", "rotation_groups", "layouts", "schedules"):
        result[key] = _section(result, key)
    settings = result.setdefault("settings", {})
    if not isinstance(settings, dict) or any(
        not isinstance(key, str) or not key or len(key) > 255 for key in settings
    ):
        raise ValueError("Invalid settings section")
    included = result.get("credentials_included", False)
    if not isinstance(included, bool):
        raise ValueError("credentials_included must be a boolean")

    camera_ids = {raw["id"] for raw in result["cameras"]}
    profile_owners: dict[str, str] = {}
    for raw in result["cameras"]:
        credentials = raw.get("credential") or {}
        if not isinstance(credentials, dict) or not isinstance(credentials.get("included", False), bool):
            raise ValueError("Invalid camera credential section")
        if credentials.get("included") and not included:
            raise ValueError("Credential contents do not match the export declaration")
        payload = CameraCreate.model_validate({
            **raw,
            "username": credentials.get("username") if credentials.get("included") else None,
            "password": credentials.get("password") if credentials.get("included") else None,
        })
        values = payload.model_dump(mode="json", exclude={"username", "password"})
        raw.update(values)
        raw["credential"] = credentials
        for stream in raw["stream_profiles"]:
            identifier = stream.get("id")
            if not isinstance(identifier, str) or not identifier or len(identifier) > 128:
                raise ValueError("Every exported stream profile requires a valid ID")
            if identifier in profile_owners:
                raise ValueError("Stream profile IDs must be unique throughout the export")
            profile_owners[identifier] = raw["id"]
            parts = urlsplit(stream["url"])
            if parts.username is not None or parts.password is not None:
                raise ValueError("Import stream credentials in the credential section, not inside URLs")

    display_ids = {raw["id"] for raw in result["display_profiles"]}
    for raw in result["display_profiles"]:
        raw.update(DisplayProfileIn.model_validate(raw).model_dump(mode="json"))
    rotation_ids = {raw["id"] for raw in result["rotation_groups"]}
    for raw in result["rotation_groups"]:
        raw.update(RotationGroupIn.model_validate(raw).model_dump(mode="json"))
        for entry in raw["camera_entries"]:
            _check_camera(entry["camera_id"], entry.get("stream_profile_id"), camera_ids, profile_owners)

    active_count = 0
    layout_ids = {raw["id"] for raw in result["layouts"]}
    for raw in result["layouts"]:
        revisions = raw.get("revisions")
        if not isinstance(revisions, list) or not revisions or len(revisions) > 1_000:
            raise ValueError("Each layout requires a nonempty revision list (maximum 1000)")
        numbers: set[int] = set()
        for revision in revisions:
            if not isinstance(revision, dict):
                raise ValueError("Invalid layout revision")
            number = revision.get("revision")
            if not isinstance(number, int) or isinstance(number, bool) or number < 1 or number in numbers:
                raise ValueError("Layout revision numbers must be unique positive integers")
            numbers.add(number)
            if revision.get("status", "draft") not in {"draft", "active", "archived"}:
                raise ValueError("Invalid layout revision status")
            revision["data"] = LayoutData.model_validate(revision.get("data")).model_dump(mode="json")
        current = raw.get("current_revision", max(numbers))
        if not isinstance(current, int) or isinstance(current, bool) or current not in numbers:
            raise ValueError("Layout current_revision does not identify an exported revision")
        raw["current_revision"] = current
        current_data = next(revision["data"] for revision in revisions if revision["revision"] == current)
        payload = LayoutCreate.model_validate({**raw, "data": current_data})
        raw["description"] = payload.description
        raw["display_profile_id"] = payload.display_profile_id
        if payload.display_profile_id is not None and payload.display_profile_id not in display_ids:
            raise ValueError("Layout references a missing display profile")
        if not isinstance(raw.get("active", False), bool):
            raise ValueError("Layout active flag must be a boolean")
        active_count += int(raw.get("active", False))
        # Old revisions may legitimately reference cameras removed since they were
        # saved. Current revisions and rotation groups must always be actionable.
        for slot in current_data["slots"]:
            if slot["type"] in {"fixed", "manual"}:
                camera_id = (slot.get("selected_camera_id") or slot.get("camera_id")) if slot["type"] == "manual" else slot.get("camera_id")
                _check_camera(camera_id, slot.get("stream_profile_id"), camera_ids, profile_owners)
            elif slot["type"] == "rotation" and slot.get("rotation_group_id") not in rotation_ids:
                raise ValueError("Layout references a missing rotation group")
    if active_count > 1:
        raise ValueError("An export cannot contain more than one active layout")
    for raw in result["schedules"]:
        raw.update(ScheduleIn.model_validate(raw).model_dump(mode="json"))
        if raw["layout_id"] not in layout_ids:
            raise ValueError("Schedule references a missing layout")


def _check_camera(
    camera_id: str | None,
    profile_id: str | None,
    camera_ids: set[str],
    profile_owners: dict[str, str],
) -> None:
    if camera_id not in camera_ids:
        raise ValueError("Layout or rotation entry references a missing camera")
    if profile_id is not None and profile_owners.get(profile_id) != camera_id:
        raise ValueError("Selected stream profile does not belong to its camera")
