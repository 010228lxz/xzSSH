from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import shlex
import sys

from xzssh.cli.helpers import (
    build_ssh_copy_id_command,
    load_config_if_exists,
    load_config_or_error,
    resolve_key_path,
    write_config,
)
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_info,
    print_key_table,
    print_step,
    print_success,
    print_warnings,
    status,
)
from xzssh.model import Config
from xzssh.platform import Platform, detect_platform, ssh_dir
from xzssh.validator import validate_config


def run(args: argparse.Namespace, config_path: Path) -> int:
    if args.key_command == "add":
        return _add(args, config_path)
    if args.key_command == "list":
        return _list(args, config_path)
    if args.key_command == "add-agent":
        return _add_agent(args, config_path)
    if args.key_command == "gen":
        return _gen(args, config_path)
    if args.key_command == "copy-id":
        return _copy_id(args, config_path)
    print_error("Unknown key command")
    return 2


def _add(args: argparse.Namespace, config_path: Path) -> int:
    with status(f"Adding key reference '{args.name}'"):
        config = load_config_if_exists(config_path)
    if config is None:
        config = Config(hosts=[], keys={})

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

    keychain = getattr(args, "keychain", False)
    if keychain and detect_platform() != Platform.MACOS:
        print_error(
            "--keychain stores the passphrase in Apple's Keychain and is "
            "only available on macOS."
        )
        return 2

    ssh_add_cmd = ["ssh-add"]
    if keychain:
        # Monterey+ spelling; the pre-Monterey -K flag is long deprecated.
        ssh_add_cmd.append("--apple-use-keychain")
    ssh_add_cmd.append(str(key_path))

    with status(f"Adding '{args.name}' to ssh-agent"):
        result = subprocess.run(
            ssh_add_cmd,
            capture_output=True,
            text=True,
        )
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print_error(result.stderr.rstrip())
    if result.returncode == 0:
        if keychain:
            print_success(
                f"Key '{args.name}' is now managed by the agent; its "
                "passphrase is stored in the macOS Keychain (subsequent "
                "loads won't prompt)."
            )
        else:
            print_success(f"Key '{args.name}' is now managed by the agent.")
    return result.returncode


def _gen(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_if_exists(config_path)
    if config is None:
        config = Config(hosts=[], keys={})

    register = not args.no_register
    if register and args.name in config.keys and not args.replace:
        print_error(
            f"Key name already registered: {args.name}. "
            "Use --replace to overwrite."
        )
        return 1

    # Default to ~/.ssh/<name>; an explicit path is taken relative to the
    # cwd (the file is created now, so it must resolve to a real location).
    if args.path:
        key_path = Path(args.path).expanduser()
    else:
        key_path = ssh_dir() / args.name

    if key_path.exists() and not args.replace:
        print_error(
            f"Key file already exists: {key_path}. "
            "Use --replace to overwrite."
        )
        return 1
    if args.replace:
        # ssh-keygen would prompt "Overwrite (y/n)?" on an existing file;
        # clearing both halves first keeps the run non-interactive.
        for stale in (key_path, key_path.with_name(key_path.name + ".pub")):
            try:
                stale.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                print_error(f"Could not remove existing key {stale}: {exc}")
                return 1

    key_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ssh-keygen", "-t", args.type, "-f", str(key_path)]
    if args.bits is not None:
        cmd.extend(["-b", str(args.bits)])
    elif args.type == "rsa":
        cmd.extend(["-b", "4096"])
    if args.comment is not None:
        cmd.extend(["-C", args.comment])
    if args.no_passphrase:
        cmd.extend(["-N", ""])

    print_step(f"Generating {args.type} key at {key_path}")
    try:
        # Not captured: ssh-keygen prompts on the TTY for the passphrase
        # (unless --no-passphrase).
        result = subprocess.run(cmd)
    except FileNotFoundError:
        print_error(
            "ssh-keygen not found. Install OpenSSH client tools and retry."
        )
        return 1
    if result.returncode != 0:
        print_error("ssh-keygen failed; key not created.")
        return result.returncode

    if register:
        config.keys[args.name] = str(key_path)
        with status("Registering key"):
            write_config(config_path, config)
        print_success(
            f"Key '{args.name}' created at {key_path} and registered."
        )
    else:
        print_success(f"Key created at {key_path} (not registered).")
    print_info(
        "Install it on a host with "
        f"[accent]xzssh key copy-id <alias> --key {args.name}[/accent]."
    )
    return 0


def _copy_id(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    host = next((h for h in config.hosts if h.alias == args.alias), None)
    if host is None:
        print_error(f"Host not found: {args.alias}")
        return 1

    # Precedence: explicit --key > the host's identity_file > none (let
    # ssh-copy-id fall back to agent/default identities).
    identity_file = None
    if args.key:
        if args.key not in config.keys:
            print_error(f"Key not found: {args.key}")
            return 1
        resolved = resolve_key_path(config.keys[args.key], config_path)
        if not resolved.exists():
            print_error(f"Key file not found: {resolved}")
            return 1
        identity_file = str(resolved)
    elif host.identity_file:
        identity_file = str(resolve_key_path(host.identity_file, config_path))

    cmd = build_ssh_copy_id_command(host, identity_file)

    if args.dry_run:
        print_info(
            f"--dry-run: would install a key on [bold]{args.alias}[/bold]. "
            "Nothing was copied."
        )
        sys.stdout.write(shlex.join(cmd) + "\n")
        return 0

    print_step(f"Installing public key on {args.alias}")
    try:
        # Interactive: ssh-copy-id prompts for the remote password.
        result = subprocess.run(cmd)
    except FileNotFoundError:
        print_error(
            "ssh-copy-id not found. It ships with OpenSSH on macOS/Linux; "
            "on Windows install it or copy the key manually."
        )
        return 1
    if result.returncode == 0:
        print_success(
            f"Public key installed on '{args.alias}'. "
            f"Connect with [accent]xzssh connect {args.alias}[/accent]."
        )
    return result.returncode
