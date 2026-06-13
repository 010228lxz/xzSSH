#!/usr/bin/env python3
"""Verify the project's version markers agree (and optionally match a tag).

``pyproject.toml``'s ``version`` and ``xzssh._FALLBACK_VERSION`` (what the
Nuitka onefile binaries display when package metadata is missing) must be
identical; given a tag argument, both must also equal the tag.

Usage:
    python scripts/check_version.py            # internal consistency only
    python scripts/check_version.py v0.15.0    # also match the release tag

Reads both files textually (no tomllib, no imports of xzssh) so it runs
on any Python before dependencies are installed. Exits non-zero with a
message on mismatch.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _extract(path: Path, pattern: str, label: str) -> str:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        sys.exit(f"error: could not find {label} in {path}")
    return match.group(1)


def main(argv: list[str] | None = None) -> int:
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument("tag", nargs="?", help="release tag to match, e.g. v0.15.0")
    args = arg_parser.parse_args(argv)

    pyproject_version = _extract(
        ROOT / "pyproject.toml", r'^version\s*=\s*"([^"]+)"', "version"
    )
    fallback_version = _extract(
        ROOT / "xzssh" / "__init__.py",
        r'^_FALLBACK_VERSION\s*=\s*"([^"]+)"',
        "_FALLBACK_VERSION",
    )

    if pyproject_version != fallback_version:
        sys.exit(
            f"error: pyproject.toml version ({pyproject_version}) != "
            f"xzssh._FALLBACK_VERSION ({fallback_version})"
        )

    if args.tag is not None:
        tag_version = args.tag.lstrip("v").strip()
        if tag_version != pyproject_version:
            sys.exit(
                f"error: tag {args.tag} does not match project version "
                f"({pyproject_version})"
            )

    print(f"version check OK: {pyproject_version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
