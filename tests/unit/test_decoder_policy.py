from __future__ import annotations

from mosaivue.services.decoder_policy import candidate_kind, choose_decoders


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
