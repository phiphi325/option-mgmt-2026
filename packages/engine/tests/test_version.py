"""Smoke test: __version__ is a non-empty SemVer-shaped string."""

from __future__ import annotations

import re

from engine.version import __version__


def test_version_is_string() -> None:
    assert isinstance(__version__, str)
    assert __version__


def test_version_is_semver_shaped() -> None:
    # MAJOR.MINOR.PATCH (no pre-release suffixes for now).
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__), f"non-SemVer __version__: {__version__!r}"
