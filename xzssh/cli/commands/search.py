"""``xzssh search <query>`` — find hosts matching a free-text query.

`connect` has fuzzy search baked into its prompt, but there's no way to
search outside the connect flow. This command does a case-insensitive
substring match across the fields a user is likely to remember — alias,
hostname, user, tags, and the ProxyJump bastion — and prints the matches
as a table.

Exit codes mirror ``grep``: ``0`` when at least one host matches, ``1``
when nothing matches (so `xzssh search foo && ...` is scriptable).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from xzssh.cli.helpers import load_config_or_error
from xzssh.cli.ui import print_host_table, print_info, print_step
from xzssh.model import Host


def _matches(host: Host, needle: str) -> bool:
    """True if *needle* (already lowercased) appears in any searchable field."""
    haystacks: List[str] = [
        host.alias,
        host.host_name,
        host.user or "",
        host.proxy_jump or "",
        *host.tags,
    ]
    return any(needle in field.lower() for field in haystacks)


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    query = (getattr(args, "query", None) or "").strip()
    if not query:
        print_info("No search query provided.")
        return 1

    needle = query.lower()
    matches = [h for h in config.hosts if _matches(h, needle)]

    if not matches:
        print_info(f"No hosts match '{query}'.")
        return 1

    print_step(f"Found {len(matches)} host(s) matching '{query}'")
    print_host_table(matches)
    return 0
