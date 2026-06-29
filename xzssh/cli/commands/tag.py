"""``xzssh tag add/rm`` — manage a host's tags without an ``edit`` round-trip.

Tags have no validation constraints (the validator never rejects them),
so these handlers mutate the host's ``tags`` list and write straight
back through ``write_config`` — no full re-validation needed. Adds are
idempotent (a tag the host already has is reported, not duplicated);
removes report any tag the host didn't have.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import print_error, print_success, print_warning, status
from xzssh.model import Host


def run(args: argparse.Namespace, config_path: Path) -> int:
    if args.tag_command == "add":
        return _add(args, config_path)
    if args.tag_command == "rm":
        return _rm(args, config_path)
    print_error("Unknown tag command")
    return 2


def _find_host(config, alias: str) -> Optional[Host]:
    return next((h for h in config.hosts if h.alias == alias), None)


def _add(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1
    host = _find_host(config, args.alias)
    if host is None:
        print_error(f"Host not found: {args.alias}")
        return 1

    added = [t for t in args.tags if t not in host.tags]
    already = [t for t in args.tags if t in host.tags]
    if already:
        print_warning(
            f"Host '{args.alias}' already has: {', '.join(already)}"
        )
    if not added:
        return 0

    host.tags.extend(added)
    with status("Updating tags"):
        write_config(config_path, config)
    print_success(f"Added to '{args.alias}': {', '.join(added)}")
    return 0


def _rm(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1
    host = _find_host(config, args.alias)
    if host is None:
        print_error(f"Host not found: {args.alias}")
        return 1

    removed = [t for t in args.tags if t in host.tags]
    missing = [t for t in args.tags if t not in host.tags]
    if missing:
        print_warning(
            f"Host '{args.alias}' has no tag(s): {', '.join(missing)}"
        )
    if not removed:
        return 0

    host.tags = [t for t in host.tags if t not in removed]
    with status("Updating tags"):
        write_config(config_path, config)
    print_success(f"Removed from '{args.alias}': {', '.join(removed)}")
    return 0
