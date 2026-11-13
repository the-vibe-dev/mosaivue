import runpy
import shutil
import subprocess
from pathlib import Path

import pytest

debian_version = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "packaging" / "debian_version.py")
)["debian_version"]


@pytest.mark.parametrize("version,expected", [
    ("0.1.0", "0.1.0"),
    ("0.1.0a1", "0.1.0~a1"),
    ("0.1.0b3", "0.1.0~b3"),
    ("0.1.0rc2", "0.1.0~rc2"),
    ("0.1.0.dev1", "0.1.0~~dev1"),
    ("0.1.0b3.dev2", "0.1.0~b3~~dev2"),
])
def test_canonical_version_mapping(version, expected):
    assert debian_version(version) == expected


@pytest.mark.parametrize("version", [
    "0.1.0.post1", "0.1.0+local", "1!0.1.0", "0.1.0beta3", "0.1.0b", "01.2.3", "",
])
def test_unsupported_versions_are_rejected_instead_of_misordered(version):
    with pytest.raises(ValueError, match="Unsupported package version"):
        debian_version(version)


@pytest.mark.skipif(shutil.which("dpkg") is None, reason="Debian comparison tool is unavailable")
def test_debian_orders_development_and_prereleases_before_stable():
    versions = [
        "0.1.0.dev1", "0.1.0.dev2", "0.1.0a1.dev1", "0.1.0a1", "0.1.0a2",
        "0.1.0b1", "0.1.0b3.dev1", "0.1.0b3", "0.1.0rc1", "0.1.0", "0.1.1.dev1",
    ]
    for older, newer in zip(versions, versions[1:], strict=False):
        result = subprocess.run(
            ["dpkg", "--compare-versions", debian_version(older), "lt", debian_version(newer)],
            check=False,
        )
        assert result.returncode == 0, (older, newer)
