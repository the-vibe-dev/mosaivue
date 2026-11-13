#!/usr/bin/env python3
"""Map the project's canonical PEP 440 release versions to Debian ordering."""

from __future__ import annotations

import re
import sys

_NUMBER = r"(?:0|[1-9][0-9]*)"
_VERSION = re.compile(
    rf"(?P<release>{_NUMBER}(?:\.{_NUMBER})*)"
    rf"(?P<pre>(?:a|b|rc){_NUMBER})?"
    rf"(?:\.dev(?P<dev>{_NUMBER}))?"
)


def debian_version(python_version: str) -> str:
    """Support stable, a/b/rc prereleases, and their optional .dev releases.

    Debian sorts '~' before an empty suffix. A development release needs a
    second '~' so that e.g. 1.0.dev1 also sorts before 1.0a1. Reject other
    PEP 440 forms rather than silently misordering epochs/local/post versions.
    """
    match = _VERSION.fullmatch(python_version)
    if match is None:
        raise ValueError(
            "Unsupported package version: use canonical numeric releases with "
            "optional aN, bN, rcN and/or .devN suffixes"
        )
    result = match["release"]
    if match["pre"]:
        result += "~" + match["pre"]
    if match["dev"] is not None:
        result += "~~dev" + match["dev"]
    return result


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: debian_version.py PYTHON_VERSION")
    try:
        print(debian_version(sys.argv[1]))
    except ValueError as error:
        raise SystemExit(str(error)) from error
