from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from mosaivue import config
from mosaivue.config import (
    Settings,
    SettingsError,
    load_settings,
    save_renderer_backend,
    save_settings,
)


@pytest.fixture()
def settings_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RENDERER_BACKEND_OVERRIDE_PATH", tmp_path / "renderer-backend.json")
    for name in tuple(config.os.environ):
        if name in {"MOSAIVUE_BIND", "MOSAIVUE_PORT", "MOSAIVUE_RENDERER_BACKEND", "MOSAIVUE_SECURE_COOKIES", "MOSAIVUE_PREVIEW_CONCURRENCY", "MOSAIVUE_PREVIEW_CACHE_TTL_SECONDS"}:
            monkeypatch.delenv(name)
    return tmp_path / "config.json"


def test_existing_configuration_example_remains_supported():
    path = Path(__file__).resolve().parents[2] / "examples/config.json"
    settings = Settings.from_mapping(json.loads(path.read_text()))
    assert settings.port == 8080
    assert settings.web_preview_enabled is True
    assert settings.update_checks_enabled is False
    assert settings.profile == "balanced"


def test_legacy_string_booleans_are_normalized_not_truthy():
    settings = Settings.from_mapping({"web_preview_enabled": "false", "secure_cookies": "true", "schedule_enabled": "OFF", "update_checks_enabled": 0})
    assert settings.web_preview_enabled is False
    assert settings.secure_cookies is True
    assert settings.schedule_enabled is False
    assert settings.update_checks_enabled is False


@pytest.mark.parametrize("document,field", [
    ({"port": 0}, "port"), ({"port": 65536}, "port"), ({"port": True}, "port"),
    ({"port": 8080.5}, "port"), ({"session_hours": -1}, "session_hours"),
    ({"renderer_backend": "unknown"}, "renderer_backend"), ({"secure_cookies": "maybe"}, "secure_cookies"),
    ({"web_preview_enabled": []}, "web_preview_enabled"), ({"profile": "unknown"}, "profile"),
    ({"renderer_sink": "kmssink ; command"}, "renderer_sink"), ({"bind": "http://0.0.0.0:8080"}, "bind"),
    ({"rtsp_tls_ca_file": "relative.pem"}, "rtsp_tls_ca_file"),
])
def test_invalid_settings_fail_with_field_specific_safe_messages(document, field):
    with pytest.raises(SettingsError, match=field):
        Settings.from_mapping(document)


def test_file_override_environment_precedence_and_canonical_types(settings_paths, monkeypatch):
    settings_paths.write_text(json.dumps({"port": "8000", "secure_cookies": "false", "renderer_backend": "gstreamer"}))
    config.RENDERER_BACKEND_OVERRIDE_PATH.write_text('{"renderer_backend":"omxplayer"}')
    assert load_settings(settings_paths).renderer_backend == "omxplayer"
    monkeypatch.setenv("MOSAIVUE_RENDERER_BACKEND", "gstreamer")
    monkeypatch.setenv("MOSAIVUE_PORT", "8081")
    monkeypatch.setenv("MOSAIVUE_SECURE_COOKIES", "YES")
    settings = load_settings(settings_paths)
    assert settings.renderer_backend == "gstreamer"
    assert settings.port == 8081 and isinstance(settings.port, int)
    assert settings.secure_cookies is True
    monkeypatch.setenv("MOSAIVUE_SECURE_COOKIES", "not-a-boolean")
    with pytest.raises(SettingsError, match="secure_cookies"):
        load_settings(settings_paths)


def test_invalid_optional_renderer_override_does_not_break_valid_main_config(settings_paths):
    settings_paths.write_text('{"renderer_backend":"gstreamer"}')
    config.RENDERER_BACKEND_OVERRIDE_PATH.write_text('{"renderer_backend":[]}')
    with pytest.warns(UserWarning, match="invalid saved renderer"):
        assert load_settings(settings_paths).renderer_backend == "gstreamer"


@pytest.mark.parametrize("payload", ['[]', 'null', '"text"', '{not-json'])
def test_invalid_configuration_roots_have_actionable_errors(settings_paths, payload):
    settings_paths.write_text(payload)
    with pytest.raises(SettingsError, match="configuration"):
        load_settings(settings_paths)


def test_unknown_future_keys_are_compatible_but_visible():
    with pytest.warns(UserWarning, match="future_extension"):
        settings = Settings.from_mapping({"port": 9000, "future_extension": {"value": "secret-is-not-logged"}})
    assert settings.port == 9000


def test_invalid_mutated_settings_do_not_replace_working_file(settings_paths):
    save_settings(Settings(port=9000), settings_paths)
    before = settings_paths.read_bytes()
    changed = Settings()
    changed.port = "must-not-be-echoed"
    with pytest.raises(SettingsError) as failure:
        save_settings(changed, settings_paths)
    assert "must-not-be-echoed" not in str(failure.value)
    assert settings_paths.read_bytes() == before


def test_concurrent_settings_writes_are_complete_and_leave_no_temporary_files(settings_paths):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda port: save_settings(Settings(port=port), settings_paths), range(9000, 9040)))
    assert 9000 <= load_settings(settings_paths).port < 9040
    assert settings_paths.stat().st_mode & 0o777 == 0o640
    assert not list(settings_paths.parent.glob('.config.json.*'))


def test_concurrent_renderer_selection_writes_remain_valid(settings_paths):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(save_renderer_backend, ["auto", "gstreamer", "omxplayer"] * 12))
    assert json.loads(config.RENDERER_BACKEND_OVERRIDE_PATH.read_text())["renderer_backend"] in config.RENDERER_BACKENDS
    assert not list(settings_paths.parent.glob('.renderer-backend.json.*'))


def test_replacing_settings_preserves_owner_and_group(settings_paths):
    save_settings(Settings(), settings_paths)
    before = settings_paths.stat()
    save_settings(Settings(port=9001), settings_paths)
    after = settings_paths.stat()
    assert (after.st_uid, after.st_gid) == (before.st_uid, before.st_gid)


def test_new_settings_explicitly_inherit_the_parent_group(settings_paths, monkeypatch):
    ownership = []
    real_fchown = config.os.fchown

    def record_fchown(descriptor, uid, gid):
        ownership.append((uid, gid))
        real_fchown(descriptor, uid, gid)

    monkeypatch.setattr(config.os, "fchown", record_fchown)
    save_settings(Settings(), settings_paths)
    assert ownership == [(-1, settings_paths.parent.stat().st_gid)]
    assert settings_paths.stat().st_gid == settings_paths.parent.stat().st_gid


def test_service_can_replace_a_root_owned_override_in_its_writable_directory(settings_paths, monkeypatch):
    save_renderer_backend("auto")
    original_lstat = Path.lstat
    ownership = []

    def root_owned_metadata(path):
        previous = original_lstat(path)
        if path == config.RENDERER_BACKEND_OVERRIDE_PATH:
            return SimpleNamespace(st_uid=0, st_gid=os.getegid(), st_mode=previous.st_mode)
        return previous

    monkeypatch.setattr(Path, "lstat", root_owned_metadata)
    monkeypatch.setattr(config.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(config.os, "fchown", lambda descriptor, uid, gid: ownership.append((uid, gid)))
    save_renderer_backend("gstreamer")
    assert ownership == [(-1, os.getegid())]
    assert json.loads(config.RENDERER_BACKEND_OVERRIDE_PATH.read_text())["renderer_backend"] == "gstreamer"


@pytest.mark.skipif(os.geteuid() != 0, reason="Requires root to exercise a different real directory group")
def test_root_created_configuration_uses_the_service_directory_group(settings_paths):
    service_gid = 65534 if os.getegid() != 65534 else 1
    os.chown(settings_paths.parent, -1, service_gid)
    save_settings(Settings(), settings_paths)
    assert settings_paths.stat().st_gid == service_gid
    assert settings_paths.stat().st_mode & 0o777 == 0o640


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "0.0.0.0", "localhost", "camera-wall.example"])
def test_valid_listener_addresses_are_retained(host):
    assert Settings(bind=host).bind == host
