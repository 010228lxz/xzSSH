from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from xzssh.cli.helpers import (
    load_config_if_exists,
    load_config_or_error,
    resolve_key_path,
    write_config,
)
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_key_table,
    print_step,
    print_success,
    print_warnings,
    status,
)
from xzssh.model import Config
from xzssh.validator import validate_config


def run(args: argparse.Namespace, config_path: Path) -> int:
    if args.key_command == "add":
        return _add(args, config_path)
    if args.key_command == "list":
        return _list(args, config_path)
    if args.key_command == "add-agent":
        return _add_agent(args, config_path)
    print_error("Unknown key command")
    return 2


def _add(args: argparse.Namespace, config_path: Path) -> int:
    with status(f"Adding key reference '{args.name}'"):
        config = load_config_if_exists(config_path)
    if config is None:
        config = Config(version=1, hosts=[], keys={})

    if args.name in config.keys and not args.replace:
        print_error(
            f"Key name already exists: {args.name}. Use --replace to overwrite."
        )
        return 1

    config.keys[args.name] = args.path

    with status("Validating key path and permissions"):
        result = validate_config(
            config, suggest_ports=args.suggest_ports, source_path=config_path
        )
    if result.errors:
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    with status("Updating key store"):
        write_config(config_path, config)
    print_success(f"Key '{args.name}' has been registered.")
    return 0


def _list(args: argparse.Namespace, config_path: Path) -> int:
    with status("Scanning key store"):
        config = load_config_or_error(config_path)
    if config is None:
        return 1

    with status("Verifying key health"):
        result = validate_config(
            config, suggest_ports=args.suggest_ports, source_path=config_path
        )
    if result.errors:
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    print_step(f"Found {len(config.keys)} registered key(s)")
    print_key_table(config.keys)
    return 0


def _add_agent(args: argparse.Namespace, config_path: Path) -> int:
    with status(f"Locating key '{args.name}'"):
        config = load_config_or_error(config_path)
    if config is None:
        return 1

    if args.name not in config.keys:
        print_error(f"Key not found: {args.name}")
        return 1

    key_path = resolve_key_path(config.keys[args.name], config_path)
    if not key_path.exists():
        print_error(f"Key file not found: {key_path}")
        return 1

    with status(f"Adding '{args.name}' to ssh-agent"):
        result = subprocess.run(
            ["ssh-add", str(key_path)],
            capture_output=True,
            text=True,
        )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print_error(result.stderr.rstrip())
    if result.returncode == 0:
        print_success(f"Key '{args.name}' is now managed by the agent.")
    return result.returncode
