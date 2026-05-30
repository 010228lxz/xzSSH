#!/usr/bin/env python3
"""Print the CHANGELOG.md section for a given version.

Used by the release workflow to populate a GitHub Release's body with
just that version's notes (rather than the whole changelog or nothing).

Usage:
    python scripts/extract_changelog.py v0.10.1
    python scripts/extract_changelog.py 0.10.1 --changelog CHANGELOG.md

Prints the body of the matching ``## [VERSION] ...`` section (everything
up to the next ``## `` heading) to stdout. Exits non-zero if no matching
section is found, so the caller can fall back to a default.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional


def extract_section(changelog: str, version: str) -> Optional[str]:
    """Return the notes body for *version*, or None if not present.

    Matches a heading of the form ``## [<version>]`` (the trailing text
    after the bracket — a date, etc. — is ignored). The returned body
    excludes the heading line itself and the following section's heading.
    """
    version = version.lstrip("v").strip()
    marker = f"## [{version}]"

    lines = changelog.splitlines()
    out: List[str] = []
    capturing = False
    for line in lines:
        if line.startswith("## "):
            if capturing:
                # Reached the next section — stop.
                break
            if line.startswith(marker):
                capturing = True
                continue
        elif capturing:
            out.append(line)

    if not capturing:
        return None

    # Trim leading/trailing blank lines for a tidy release body.
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Version or tag, e.g. v0.10.1 or 0.10.1")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to the changelog file (default: CHANGELOG.md)",
    )
    args = parser.parse_args(argv)

    path = Path(args.changelog)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {path}: {exc}", file=sys.stderr)
        return 2

    section = extract_section(text, args.version)
    if section is None:
        print(
            f"error: no changelog section for version '{args.version}'",
            file=sys.stderr,
        )
        return 1

    print(section)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
