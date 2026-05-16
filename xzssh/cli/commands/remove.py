from __future__ import annotations

import argparse
from pathlib import Path

import questionary

from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_info,
    print_success,
    print_warnings,
    status,
)
from xzssh.validator import validate_config


def run(args: argparse.Namespace, config_path: Path) -> int:
    with status("Updating configuration"):
        config = load_config_or_error(config_path)
    if config is None:
        return 1

    if args.all:
        if not questionary.confirm("Are you sure you want to remove ALL hosts?").ask():
            print_info("Operation cancelled.")
            return 0
        config.hosts = []
        print_success("All hosts removed.")
    else:
        if not args.alias:
            print_error("No host alias provided for removal.")
            return 1

        initial_count = len(config.hosts)
        config.hosts = [host for host in config.hosts if host.alias not in args.alias]
        removed_count = initial_count - len(config.hosts)

        if removed_count == 0:
            print_error(f"No hosts found with alias: {', '.join(args.alias)}")
            return 1

        print_success(f"Removed {removed_count} host(s).")

    with status("Validating updated configuration"):
        result = validate_config(
            config,
            suggest_ports=getattr(args, "suggest_ports", False),
            source_path=config_path,
        )
    if result.errors:
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    with status("Saving changes"):
        write_config(config_path, config)
    return 0
