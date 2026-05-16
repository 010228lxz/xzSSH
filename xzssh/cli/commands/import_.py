from __future__ import annotations

import argparse
from pathlib import Path

from xzssh.cli.helpers import load_config_if_exists, write_config
from xzssh.cli.ui import (
    print_error,
    print_info,
    print_success,
    print_warnings,
    status,
)
from xzssh.model import Config
from xzssh.parser import parse_openssh_config
from xzssh.platform import resolve_path


def run(args: argparse.Namespace, config_path: Path) -> int:
    ssh_config_path = Path(args.file) if args.file else Path.home() / ".ssh" / "config"
    ssh_config_path = resolve_path(str(ssh_config_path), None)

    if not ssh_config_path.exists():
        if args.file:
            print_error(f"File not found: {ssh_config_path}")
        else:
            print_error("Default SSH config not found at ~/.ssh/config")
        return 1

    print_info(f"Importing hosts from {ssh_config_path}...")

    try:
        hosts_found, warnings = parse_openssh_config(ssh_config_path)
    except OSError as exc:
        print_error(f"Failed to read SSH config: {exc}")
        return 1

    if warnings:
        print_warnings(warnings)

    if not hosts_found:
        print_info("No valid hosts found to import.")
        return 0

    with status("Updating xzSSH configuration"):
        config = load_config_if_exists(config_path) or Config(version=1, hosts=[])

        added = 0
        skipped = 0
        for h in hosts_found:
            existing = next((ex for ex in config.hosts if ex.alias == h.alias), None)
            if existing:
                if args.overwrite:
                    config.hosts = [ex for ex in config.hosts if ex.alias != h.alias]
                    config.hosts.append(h)
                    added += 1
                else:
                    skipped += 1
            else:
                config.hosts.append(h)
                added += 1

    write_config(config_path, config)
    print_success(f"Import complete: {added} added, {skipped} skipped.")
    return 0
