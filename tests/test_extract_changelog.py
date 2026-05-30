"""Tests for scripts/extract_changelog.py — release-notes extraction."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "extract_changelog.py"
_spec = importlib.util.spec_from_file_location("extract_changelog", _SCRIPT)
extract_changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(extract_changelog)  # type: ignore[union-attr]


SAMPLE = """# Changelog

## [Unreleased]

## [0.10.1] — 2026-05-30

### Fixed

- Did a thing.

## [0.10.0] — 2026-05-28

### Added

- An earlier thing.

[0.10.1]: https://example.com/compare
"""


def test_extracts_named_version() -> None:
    body = extract_changelog.extract_section(SAMPLE, "0.10.1")
    assert "Did a thing." in body
    # Must not bleed into the previous version's section.
    assert "An earlier thing." not in body


def test_strips_leading_v() -> None:
    body = extract_changelog.extract_section(SAMPLE, "v0.10.1")
    assert "Did a thing." in body


def test_unknown_version_returns_none() -> None:
    assert extract_changelog.extract_section(SAMPLE, "9.9.9") is None


def test_body_excludes_heading_and_trailing_blanks() -> None:
    body = extract_changelog.extract_section(SAMPLE, "0.10.0")
    assert not body.startswith("## ")
    assert body == body.strip()
    assert "An earlier thing." in body


def test_real_changelog_has_current_version() -> None:
    """The repo's own CHANGELOG must contain the latest shipped section."""
    changelog = (_SCRIPT.parent.parent / "CHANGELOG.md").read_text(encoding="utf-8")
    body = extract_changelog.extract_section(changelog, "0.10.0")
    assert body is not None
    assert "connect --dry-run" in body
