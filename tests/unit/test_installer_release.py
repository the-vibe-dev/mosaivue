from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import tomllib
import venv
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("minor", [11, 12, 13, 14, 15])
def test_bullseye_wheels_match_selected_cpython_abi(minor):
    planner = load_script("bullseye_wheel_plan")
    crypto, core = planner.wheel_plan((3, minor))
    assert "cp311-abi3-" in crypto["filename"]
    assert f"cp3{minor}-cp3{minor}-" in core["filename"]
    assert "manylinux_2_17_armv7l" in core["filename"]
    assert all(len(wheel["sha256"]) == 64 for wheel in (crypto, core))


@pytest.mark.parametrize("version,options", [
    ((3, 10), {}), ((3, 16), {}), ((3, 12), {"implementation": "pypy"}),
    ((3, 13), {"free_threaded": True}),
])
def test_bullseye_unknown_abis_fail_before_install(version, options):
    with pytest.raises(ValueError, match="No pinned Bullseye"):
        load_script("bullseye_wheel_plan").wheel_plan(version, **options)


def test_bullseye_manifest_matches_project_dependency_pin():
    manifest = json.loads((ROOT / "installer/bullseye-wheels.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert f"pydantic=={manifest['pydantic']}" in project["dependencies"]


@pytest.mark.parametrize("bind,expected", [
    ("0.0.0.0", "127.0.0.1"), ("::", "[::1]"), ("::1", "[::1]"),
    ("2001:db8::10", "[2001:db8::10]"), ("192.0.2.8", "192.0.2.8"),
])
def test_installer_health_probe_matches_bind_address_family(bind, expected):
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; cw_health_host "$2"', "test", str(ROOT / "installer/lib.sh"), bind],
        check=True, capture_output=True, text=True,
    )
    assert result.stdout.strip() == expected


def test_editable_release_still_imports_after_staging_directory_is_renamed(tmp_path):
    final = tmp_path / "release"
    stage = tmp_path / "release.new"
    environment = stage / ".venv"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
    package = stage / "src/review_relocation_sample"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 'relocated-successfully'\n")
    site = next((environment / "lib").glob("python*/site-packages"))
    (site / "editable_sample.pth").write_text(str(stage / "src") + "\n")
    metadata = site / "sample-1.0.dist-info"
    metadata.mkdir()
    (metadata / "direct_url.json").write_text(json.dumps({"url": stage.as_uri(), "dir_info": {"editable": True}}))
    entry = environment / "bin/sample-cli"
    entry.write_text(f"#!{environment}/bin/python\nfrom review_relocation_sample import VALUE\nprint(VALUE)\n")
    entry.chmod(0o755)
    assert subprocess.check_output([str(entry)], text=True).strip() == "relocated-successfully"

    shutil.move(str(stage), final)
    with pytest.raises(FileNotFoundError):
        subprocess.run([str(final / ".venv/bin/sample-cli")], check=True, capture_output=True)
    repaired = load_script("relocate_venv").relocate_venv(final)
    assert repaired >= 3
    assert subprocess.check_output([str(final / ".venv/bin/sample-cli")], text=True).strip() == "relocated-successfully"
    assert subprocess.check_output(
        [str(final / ".venv/bin/python"), "-I", "-c", "from review_relocation_sample import VALUE; print(VALUE)"], text=True,
    ).strip() == "relocated-successfully"
    assert os.access(final / ".venv/bin/sample-cli", os.X_OK)
    result_meta = json.loads(next((final / ".venv/lib").glob("python*/site-packages/sample-1.0.dist-info/direct_url.json")).read_text())
    assert result_meta["url"] == final.as_uri()
    assert load_script("relocate_venv").relocate_venv(final) == 0


def test_relocation_ignores_binary_symlinks_and_similar_prefixes(tmp_path):
    release = tmp_path / "release"
    binary_dir = release / ".venv/bin"
    binary_dir.mkdir(parents=True)
    external = tmp_path / "outside"
    original = f"{release}.new/src\n".encode()
    external.write_bytes(original)
    (binary_dir / "link").symlink_to(external)
    binary = b"\x7fELF\x00" + original
    (binary_dir / "binary").write_bytes(binary)
    unrelated = f"{release}.newer/bin/python\n"
    (binary_dir / "unrelated").write_text(unrelated)
    assert load_script("relocate_venv").relocate_venv(release) == 0
    assert external.read_bytes() == original
    assert (binary_dir / "binary").read_bytes() == binary
    assert (binary_dir / "unrelated").read_text() == unrelated


@pytest.mark.skipif(os.geteuid() != 0 or shutil.which("rsync") is None, reason="Requires root and rsync for installed-release ownership")
def test_installed_source_does_not_retain_checkout_owner_or_writable_modes(tmp_path):
    source = tmp_path / "checkout"
    source.mkdir(mode=0o700)
    helper = source / "installer/update.sh"
    helper.parent.mkdir()
    helper.write_text("#!/bin/sh\nexit 0\n")
    data = source / "pyproject.toml"
    data.write_text('[project]\nname = "mosaivue"\n')
    external = tmp_path / "external-helper"
    external.write_text("outside the installed tree")
    (source / "unsafe-link").symlink_to(external)
    ignored = source / ".venv/private"
    ignored.parent.mkdir()
    ignored.write_text("not source")
    for path in [source, helper.parent, helper, data]:
        os.chown(path, 12345, 12345)
    source.chmod(0o2777)
    helper.parent.chmod(0o2777)
    helper.chmod(0o6777)
    data.chmod(0o666)
    destination = tmp_path / "release.new"
    destination.mkdir()
    subprocess.run(
        ["bash", "-c", 'source "$1"; cw_stage_source "$2" "$3"', "test",
         str(ROOT / "installer/lib.sh"), str(source), str(destination)],
        check=True, capture_output=True, text=True,
    )
    assert not (destination / ".venv").exists()
    assert not (destination / "unsafe-link").exists()
    for path in [destination, destination / "installer", destination / "installer/update.sh", destination / "pyproject.toml"]:
        observed = path.stat()
        assert (observed.st_uid, observed.st_gid) == (0, 0)
        assert stat.S_IMODE(observed.st_mode) == (0o644 if path.name == "pyproject.toml" else 0o755)
    assert helper.stat().st_uid == 12345
    assert stat.S_IMODE(helper.stat().st_mode) == 0o6777


def test_installer_rejects_replaceable_ancestor_directory(tmp_path):
    # Even root-owned application files are replaceable through a writable parent.
    tmp_path.chmod(0o777)
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; cw_assert_prefix_ancestors "$2"', "test",
         str(ROOT / "installer/lib.sh"), str(tmp_path / "mosaivue")],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "root-owned and not group/other writable" in result.stderr


def test_installer_accepts_simulated_root_owned_ancestor_metadata():
    # This workspace remaps even / and /opt away from UID 0. Exercise the
    # acceptance branch with controlled metadata; the real transfer test above
    # remains explicitly conditional on privileged execution.
    subprocess.run(
        ["bash", "-c", 'stat() { printf "0 755\\n"; }; source "$1"; cw_assert_prefix_ancestors /opt/mosaivue', "test",
         str(ROOT / "installer/lib.sh")],
        check=True, capture_output=True, text=True,
    )


@pytest.mark.parametrize("entry_kind", ["symlink", "file"])
def test_installer_rejects_unsafe_release_directory_before_privileged_writes(tmp_path, entry_kind):
    prefix = tmp_path / "mosaivue"
    prefix.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    sentinel = external / "unchanged"
    sentinel.write_text("retain")
    if entry_kind == "symlink":
        (prefix / "releases").symlink_to(external, target_is_directory=True)
    else:
        (prefix / "releases").write_text("not a directory")
    result = subprocess.run(
        ["bash", "-c", 'source "$1"; cw_assert_release_directory "$2"', "test",
         str(ROOT / "installer/lib.sh"), str(prefix)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "real directory" in result.stderr
    assert sentinel.read_text() == "retain"
