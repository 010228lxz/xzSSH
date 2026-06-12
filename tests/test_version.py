"""The banner version must track pyproject.toml — see xzssh/__init__.py."""
from __future__ import annotations

import re
from pathlib import Path

import xzssh
from xzssh.cli import ui

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _pyproject_version() -> str:
    # No tomllib on Python 3.9/3.10, so a targeted regex on the [project]
    # table's version line keeps this dependency-free.
    match = re.search(
        r'^version\s*=\s*"([^"]+)"',
        _PYPROJECT.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match, "pyproject.toml has no version line"
    return match.group(1)


def test_banner_version_matches_pyproject():
    expected = _pyproject_version()
    with ui.console.capture() as capture:
        ui.print_banner()
    output = capture.get()
    assert f"v{expected}" in output, (
        f"banner shows a different version than pyproject.toml ({expected}); "
        f"xzssh.__version__ is {xzssh.__version__} — if that is stale, "
        "re-run `pip install -e .`"
    )
    assert "v0.1.0" not in output  # the once-hardcoded banner version


def test_nuitka_fallback_constant_matches_pyproject():
    # The onefile release binaries may lack package metadata; the fallback
    # constant is what they display, so it must never drift from pyproject.
    assert xzssh._FALLBACK_VERSION == _pyproject_version()
