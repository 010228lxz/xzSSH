"""``xzssh known-hosts remove <alias>`` — drop a host's cached host key.

After a server is rebuilt, ssh refuses to connect with the loud
``REMOTE HOST IDENTIFICATION HAS CHANGED`` warning. This wraps
``ssh-keygen -R`` so you don't have to retype the hostname (and remember
the ``[host]:port`` bracket form for non-default ports). The host's
``UserKnownHostsFile`` is honoured when set; otherwise ssh-keygen edits
the default ``~/.ssh/known_hosts``.
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from xzssh.cli.helpers import load_config_or_error
from xzssh.cli.ui import print_error, print_info, print_step, print_success
from xzssh.model import Host
from xzssh.platform import resolve_path


def run(args: argparse.Namespace, config_path: Path) -> int:
    if args.known_hosts_command == "remove":
        return _remove(args, config_path)
    print_error("Unknown known-hosts command")
    return 2


def _known_hosts_target(host: Host) -> str:
    """The key ssh stores for *host* — bracketed when the port isn't 22."""
    if host.port and host.port != 22:
        return f"[{host.host_name}]:{host.port}"
    return host.host_name


def _remove(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    host = next((h for h in config.hosts if h.alias == args.alias), None)
    if host is None:
        print_error(f"Host not found: {args.alias}")
        return 1

    target = _known_hosts_target(host)
    cmd = ["ssh-keygen", "-R", target]
    if host.user_known_hosts_file:
        kh = resolve_path(host.user_known_hosts_file, config_path.parent)
        cmd.extend(["-f", str(kh)])

    if getattr(args, "dry_run", False):
        print_info(
            f"--dry-run: would remove the host key for [bold]{args.alias}[/bold] "
            f"({target}). Nothing was changed."
        )
        sys.stdout.write(shlex.join(cmd) + "\n")
        return 0

    print_step(f"Removing cached host key for {args.alias} ({target})")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        print_error(
            "ssh-keygen not found. Install OpenSSH client tools and retry."
        )
        return 1
    # ssh-keygen prints "Host ... not found in ..." on stderr when there was
    # nothing to remove; that's still exit 0 and a fine outcome to report.
    if result.returncode == 0:
        print_success(
            f"Cleared cached host key(s) for '{args.alias}' ({target}). "
            f"The next connection will re-verify and store the new key."
        )
    else:
        if result.stderr:
            print_error(result.stderr.rstrip())
    return result.returncode
