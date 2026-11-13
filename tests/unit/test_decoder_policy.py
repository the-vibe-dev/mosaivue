from __future__ import annotations

import json

from mosaivue.services import decoder_policy
from mosaivue.services.decoder_policy import (
    candidate_kind,
    choose_decoders,
    persist_fixed_decoder_fallback,
    retain_verified_fallbacks,
    working_software_decoder,
)


def test_installer_prefers_working_hardware_for_fixed_and_software_for_rotation() -> None:
    candidates = [
        {"name": "broken-hardware", "kind": "hardware", "probe": "failed"},
        {"name": "nvh264dec", "kind": "hardware", "probe": "passed"},
        {"name": "avdec_h264", "kind": "software", "probe": "passed"},
    ]
    assert choose_decoders(candidates) == {
        "fixed": "nvh264dec", "rotation": "avdec_h264"
    }
    candidates[1]["probe"] = "failed"
    assert choose_decoders(candidates) == {
        "fixed": "avdec_h264", "rotation": "avdec_h264"
    }


def test_rockchip_decoder_is_hardware_even_without_hardware_metadata() -> None:
    assert candidate_kind("h264", "mppvideodec", "Decoder/Video") == "hardware"
    assert candidate_kind("h264", "nvh264dec", "Codec/Decoder/Video/Hardware") == "hardware"
    assert candidate_kind("h264", "avdec_h264", "Codec/Decoder/Video") == "software"


def test_runtime_verified_software_survives_installer_reprobe(tmp_path, monkeypatch) -> None:
    path = tmp_path / "decoder-policy.json"
    candidates = [
        {"name": "nvh264dec", "kind": "hardware", "probe": "passed"},
        {"name": "avdec_h264", "kind": "software", "probe": "passed"},
    ]
    previous = {"schema_version": 1, "codecs": {"h264": {
        "fixed": "avdec_h264", "fixed_source": "runtime_verified_software",
        "runtime_verified_sink": "ximagesink", "runtime_verified_slots": 7,
        "rotation": "avdec_h264", "candidates": candidates,
    }}}
    path.write_text(json.dumps(previous))
    fresh = {"schema_version": 1, "codecs": {"h264": {
        "fixed": "nvh264dec", "rotation": "avdec_h264", "candidates": candidates,
    }}}
    monkeypatch.setattr(decoder_policy, "detect_decoder_policy", lambda: fresh)

    result = decoder_policy.write_decoder_policy(path)

    assert result["codecs"]["h264"]["fixed"] == "avdec_h264"
    assert result["codecs"]["h264"]["fixed_source"] == "runtime_verified_software"
    assert result["codecs"]["h264"]["runtime_verified_sink"] == "ximagesink"
    assert result["codecs"]["h264"]["runtime_verified_slots"] == 7
    assert path.stat().st_mode & 0o777 == 0o640
    assert json.loads(path.read_text()) == result


def test_only_probed_software_can_be_persisted(tmp_path) -> None:
    path = tmp_path / "decoder-policy.json"
    report = {"schema_version": 1, "codecs": {"h264": {
        "fixed": "nvh264dec", "rotation": "avdec_h264",
        "candidates": [
            {"name": "nvh264dec", "kind": "hardware", "probe": "passed"},
            {"name": "avdec_h264", "kind": "software", "probe": "passed"},
        ],
    }}}
    path.write_text(json.dumps(report))
    assert working_software_decoder("h264", report["codecs"]["h264"]) == "avdec_h264"
    assert not persist_fixed_decoder_fallback("h264", "nvh264dec", path)
    assert persist_fixed_decoder_fallback("h264", "avdec_h264", path)
    updated = json.loads(path.read_text())
    assert updated["codecs"]["h264"]["fixed"] == "avdec_h264"
    assert updated["codecs"]["h264"]["fixed_source"] == "runtime_verified_software"

    failed = {"schema_version": 1, "codecs": {"h264": {
        "fixed": "nvh264dec", "rotation": "avdec_h264",
        "candidates": [{"name": "avdec_h264", "kind": "software", "probe": "failed"}],
    }}}
    retain_verified_fallbacks(failed, updated)
    assert failed["codecs"]["h264"]["fixed"] == "nvh264dec"
