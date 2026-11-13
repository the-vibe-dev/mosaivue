import json
import os
import stat

import pytest

from mosaivue.services import capabilities


def test_capability_report_is_replaced_as_complete_json(tmp_path, monkeypatch):
    path = tmp_path / "capabilities.json"
    old = {"generated_at": "old"}
    report = {"generated_at": "new", "gstreamer": {"plugins": {"compositor": False}}}
    path.write_text(json.dumps(old))
    monkeypatch.setattr(capabilities, "detect_capabilities", lambda: report)
    replace = os.replace
    replacements = []

    def verified_replace(source, destination):
        assert json.loads(path.read_text()) == old
        assert json.loads(source.read_text()) == report
        assert stat.S_IMODE(source.stat().st_mode) == 0o640
        replacements.append(destination)
        replace(source, destination)

    monkeypatch.setattr(capabilities.os, "replace", verified_replace)
    assert capabilities.write_capabilities(path) == report
    assert json.loads(path.read_text()) == report
    assert replacements == [path]
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize("stage", ["serialize", "replace"])
def test_failed_report_refresh_preserves_previous_report_and_cleans_temporary_file(tmp_path, monkeypatch, stage):
    path = tmp_path / "capabilities.json"
    old = '{"generated_at":"last-complete-report"}\n'
    path.write_text(old)
    report = {"invalid": object()} if stage == "serialize" else {"generated_at": "new"}
    monkeypatch.setattr(capabilities, "detect_capabilities", lambda: report)

    def failed_replace(*_):
        raise OSError("Device temporarily unavailable")

    if stage == "replace":
        monkeypatch.setattr(capabilities.os, "replace", failed_replace)
    with pytest.raises((TypeError, OSError)):
        capabilities.write_capabilities(path)
    assert path.read_text() == old
    assert list(tmp_path.iterdir()) == [path]
