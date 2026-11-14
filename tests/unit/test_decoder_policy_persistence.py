import fcntl
import json
import os
import stat
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from mosaivue.services import decoder_policy as policy


def sample_policy():
    return {"schema_version": 1, "codecs": {
        codec: {
            "fixed": hardware, "rotation": software,
            "candidates": [
                {"name": hardware, "kind": "hardware", "probe": "passed"},
                {"name": software, "kind": "software", "probe": "passed"},
            ],
        }
        for codec, hardware, software in [
            ("h264", "nvh264dec", "avdec_h264"),
            ("h265", "nvh265dec", "avdec_h265"),
        ]
    }}


def test_reprobe_retains_exact_verified_secondary_software_decoder(tmp_path, monkeypatch):
    path = tmp_path / "decoder-policy.json"
    previous = sample_policy()
    entry = previous["codecs"]["h264"]
    entry["fixed"] = "openh264dec"
    entry["fixed_source"] = "runtime_verified_software"
    entry["runtime_verified_slots"] = 7
    entry["runtime_verified_sink"] = "ximagesink"
    entry["candidates"].append({"name": "openh264dec", "kind": "software", "probe": "passed"})
    path.write_text(json.dumps(previous))
    fresh = deepcopy(previous)
    fresh["codecs"]["h264"] = {**entry, "fixed": "nvh264dec"}
    fresh["codecs"]["h264"].pop("fixed_source")
    monkeypatch.setattr(policy, "detect_decoder_policy", lambda: fresh)
    report = policy.write_decoder_policy(path)
    assert report["codecs"]["h264"]["fixed"] == "openh264dec"
    assert report["codecs"]["h264"]["runtime_verified_slots"] == 7
    assert report["codecs"]["h264"]["runtime_verified_sink"] == "ximagesink"
    assert policy.persist_fixed_decoder_fallback("h264", "openh264dec", path)
    assert json.loads(path.read_text())["codecs"]["h264"]["runtime_verified_slots"] == 7


@pytest.mark.parametrize("probe", ["failed", "unprobed", "removed"])
def test_reprobe_drops_verified_choice_when_that_exact_decoder_no_longer_passes(probe):
    previous = sample_policy()
    previous["codecs"]["h264"].update(fixed="avdec_h264", fixed_source="runtime_verified_software")
    fresh = sample_policy()
    software = fresh["codecs"]["h264"]["candidates"][1]
    if probe == "removed":
        fresh["codecs"]["h264"]["candidates"].remove(software)
    else:
        software["probe"] = probe
    policy.retain_verified_fallbacks(fresh, previous)
    assert fresh["codecs"]["h264"]["fixed"] == "nvh264dec"
    assert "fixed_source" not in fresh["codecs"]["h264"]


def test_concurrent_fallback_updates_preserve_both_codecs(tmp_path, monkeypatch):
    path = tmp_path / "decoder-policy.json"
    path.write_text(json.dumps(sample_policy()))
    start = threading.Barrier(2)
    save = policy._save_decoder_policy

    def delayed_save(report, path):
        # Force competing read/modify/write operations to overlap if a writer
        # fails to take the cross-process lock before reading its snapshot.
        time.sleep(0.02)
        save(report, path)

    def update(codec):
        start.wait(timeout=2)
        return policy.persist_fixed_decoder_fallback(codec, f"avdec_{codec}", path)

    monkeypatch.setattr(policy, "_save_decoder_policy", delayed_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        jobs = [workers.submit(update, codec) for codec in ("h264", "h265")]
        assert all(job.result(timeout=3) for job in jobs)
    report = json.loads(path.read_text())
    assert report["codecs"]["h264"]["fixed"] == "avdec_h264"
    assert report["codecs"]["h265"]["fixed"] == "avdec_h265"
    assert not list(tmp_path.glob("*.tmp"))


def test_slow_reprobe_does_not_block_runtime_write_and_merges_its_result(tmp_path, monkeypatch):
    path = tmp_path / "decoder-policy.json"
    path.write_text(json.dumps(sample_policy()))
    entered = threading.Event()
    finish_probe = threading.Event()

    def probe():
        entered.set()
        assert finish_probe.wait(timeout=3)
        return sample_policy()

    monkeypatch.setattr(policy, "detect_decoder_policy", probe)
    with ThreadPoolExecutor(max_workers=1) as workers:
        job = workers.submit(policy.write_decoder_policy, path)
        try:
            assert entered.wait(timeout=2)
            assert policy.persist_fixed_decoder_fallback("h264", "avdec_h264", path)
        finally:
            finish_probe.set()
        report = job.result(timeout=3)
    assert report["codecs"]["h264"]["fixed"] == "avdec_h264"
    assert report["codecs"]["h264"]["fixed_source"] == "runtime_verified_software"


@pytest.mark.parametrize("stage", ["probe", "serialize", "replace"])
def test_failed_reprobe_preserves_last_complete_policy(tmp_path, monkeypatch, stage):
    path = tmp_path / "decoder-policy.json"
    before = json.dumps(sample_policy())
    path.write_text(before)

    def probe():
        if stage == "probe":
            raise OSError("Temporary probe failure")
        report = sample_policy()
        if stage == "serialize":
            report["unserializable"] = object()
        return report

    def replace(*_):
        raise OSError("Temporary filesystem failure")

    monkeypatch.setattr(policy, "detect_decoder_policy", probe)
    if stage == "replace":
        monkeypatch.setattr(policy.os, "replace", replace)
    with pytest.raises((OSError, TypeError)):
        policy.write_decoder_policy(path)
    assert path.read_text() == before
    assert not list(tmp_path.glob("*.tmp"))


def test_policy_and_lock_preserve_owner_group_and_service_access(tmp_path, monkeypatch):
    path = tmp_path / "decoder-policy.json"
    path.write_text(json.dumps(sample_policy()))
    previous = path.stat()
    monkeypatch.setattr(policy, "detect_decoder_policy", sample_policy)
    policy.write_decoder_policy(path)
    lock = tmp_path / ".decoder-policy.json.lock"
    for candidate, mode in [(path, 0o640), (lock, 0o660)]:
        details = candidate.stat()
        assert (details.st_uid, details.st_gid) == (previous.st_uid, previous.st_gid)
        assert stat.S_IMODE(details.st_mode) == mode


def test_new_policy_and_lock_inherit_parent_service_group(tmp_path, monkeypatch):
    path = tmp_path / "decoder-policy.json"
    ownership = []
    fchown = os.fchown

    def record(descriptor, uid, gid):
        ownership.append((uid, gid))
        fchown(descriptor, uid, gid)

    monkeypatch.setattr(policy.os, "fchown", record)
    monkeypatch.setattr(policy, "detect_decoder_policy", sample_policy)
    policy.write_decoder_policy(path)
    expected = (tmp_path.stat().st_uid, tmp_path.stat().st_gid)
    assert ownership == [expected, expected]


def test_busy_policy_lock_has_bounded_wait(tmp_path):
    path = tmp_path / "decoder-policy.json"
    lock = tmp_path / ".decoder-policy.json.lock"
    with lock.open("w") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX)
        with pytest.raises(TimeoutError, match="busy"), policy._policy_lock(path, timeout=0):
            pytest.fail("Acquired a lock held by another descriptor")


@pytest.mark.parametrize("kind", ["symlink", "hardlink"])
def test_policy_lock_refuses_linked_files(tmp_path, kind):
    path = tmp_path / "decoder-policy.json"
    unrelated = tmp_path / "unrelated"
    unrelated.write_text("untouched")
    mode = unrelated.stat().st_mode
    lock = tmp_path / ".decoder-policy.json.lock"
    if kind == "symlink":
        lock.symlink_to(unrelated)
    else:
        lock.hardlink_to(unrelated)
    with pytest.raises(OSError), policy._policy_lock(path):
        pytest.fail("Accepted a linked lock file")
    assert unrelated.read_text() == "untouched"
    assert unrelated.stat().st_mode == mode


def test_malformed_policy_fragments_do_not_break_valid_decoder_selection(tmp_path):
    path = tmp_path / "decoder-policy.json"
    report = sample_policy()
    report["codecs"].update(jpeg=None, unknown={"fixed": "unsafe"})
    report["codecs"]["h264"]["candidates"].extend([
        None, 3, {"name": "broken", "kind": [], "probe": "passed"},
        {"name": "broken", "kind": "software", "probe": []},
    ])
    report["codecs"]["h265"]["fixed"] = ["nvh265dec"]
    path.write_text(json.dumps(report))
    loaded = policy.load_decoder_policy(path)
    assert set(loaded["codecs"]) == {"h264", "h265"}
    assert loaded["codecs"]["h265"]["fixed"] is None
    assert policy.working_software_decoder("h264", loaded["codecs"]["h264"]) == "avdec_h264"


def test_new_decoder_does_not_inherit_previous_full_wall_verification(tmp_path):
    path = tmp_path / "decoder-policy.json"
    report = sample_policy()
    report["codecs"]["h264"].update(
        fixed="openh264dec", fixed_source="runtime_verified_software",
        runtime_verified_slots=7, runtime_verified_sink="ximagesink", runtime_verified_at="old",
    )
    path.write_text(json.dumps(report))
    assert policy.persist_fixed_decoder_fallback("h264", "avdec_h264", path)
    saved = json.loads(path.read_text())["codecs"]["h264"]
    assert saved["runtime_verified_slots"] == 1
    assert saved["runtime_verified_at"] != "old"
    assert "runtime_verified_sink" not in saved
