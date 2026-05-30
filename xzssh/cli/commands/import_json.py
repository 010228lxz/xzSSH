"""``xzssh import-json <file>`` — restore the config from a JSON snapshot.

Distinct from ``xzssh import`` (which reads an OpenSSH ``ssh_config``).
This reads an xzSSH JSON export produced by ``xzssh export``.

Two modes:

- ``--merge`` (default): add hosts/keys from the snapshot that aren't
  already present. On an alias collision the **existing** host wins —
  the import never silently clobbers what you have.
- ``--replace``: replace the whole config with the snapshot. The current
  ``xzssh.json`` is copied to ``xzssh.json.bak`` first, mirroring the
  safety posture of ``generate``.

The snapshot is parsed and **semantically validated before anything is
written**; a bad file aborts with the existing config untouched.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from xzssh.cli.helpers import load_config_if_exists, write_config
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_info,
    print_success,
    print_warnings,
    status,
)
from xzssh.model import Config
from xzssh.parser import ConfigParseError, load_config
from xzssh.validator import validate_config


def run(args: argparse.Namespace, config_path: Path) -> int:
    source = Path(args.file)
    if not source.exists():
        print_error(f"Snapshot file not found: {source}")
        return 1

    # Parse + validate the incoming snapshot BEFORE touching the live config.
    try:
        incoming = load_config(source)
    except ConfigParseError as exc:
        print_error(f"Invalid snapshot: {exc}")
        return 1

    result = validate_config(incoming, source_path=source)
    if result.errors:
        print_error("Snapshot failed validation; nothing was imported:")
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    replace = getattr(args, "replace", False)

    if replace:
        return _do_replace(incoming, config_path)
    return _do_merge(incoming, config_path)


def _do_replace(incoming: Config, config_path: Path) -> int:
    # Back up the existing source-of-truth before overwriting it.
    if config_path.exists():
        backup = config_path.with_name(config_path.name + ".bak")
        try:
            shutil.copy2(config_path, backup)
            print_info(f"Backed up existing config to {backup}")
        except OSError as exc:
            print_error(f"Could not back up existing config: {exc}")
            return 1

    with status("Replacing configuration"):
        write_config(config_path, incoming)
    print_success(
        f"Replaced config with snapshot: {len(incoming.hosts)} host(s)."
    )
    return 0


def _do_merge(incoming: Config, config_path: Path) -> int:
    existing = load_config_if_exists(config_path) or Config(version=1, hosts=[])

    existing_aliases = {h.alias for h in existing.hosts}
    added = 0
    skipped = 0
    for host in incoming.hosts:
        if host.alias in existing_aliases:
            skipped += 1
            continue
        existing.hosts.append(host)
        existing_aliases.add(host.alias)
        added += 1

    # Keys merge the same way: existing names win.
    for name, path_value in incoming.keys.items():
        if name not in existing.keys:
            existing.keys[name] = path_value

    with status("Merging snapshot into configuration"):
        write_config(config_path, existing)

    print_success(
        f"Merge complete: {added} host(s) added, {skipped} skipped "
        "(existing aliases kept)."
    )
    return 0
