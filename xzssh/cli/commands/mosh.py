"""``xzssh mosh <alias>`` — connect with mosh using a host's settings.

mosh bootstraps over ssh, so the host's connection options (port,
identity, ProxyJump, scalar + free-form ``-o`` options) are handed to
mosh via ``--ssh="ssh …"``; the resolved ``[user@]host`` is mosh's
positional target. Forwards are deliberately left out — they belong to
``connect``/``tunnel`` and the generated config, not an interactive mosh
session. Unlike ``connect``, mosh does not stamp ``last_used`` or write
to the event log (it's a thin transport wrapper).
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from xzssh.cli.helpers import build_ssh_command, load_config_or_error
from xzssh.cli.ui import print_error, print_info


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    host = next((h for h in config.hosts if h.alias == args.alias), None)
    if host is None:
        print_error(f"Host not found: {args.alias}")
        return 1

    # Reuse the single source of truth for ssh argv, then split off the
    # target: build_ssh_command returns ["ssh", <opts...>, <[user@]host>].
    ssh_argv = build_ssh_command(host)
    target = ssh_argv[-1]
    ssh_opts = ssh_argv[1:-1]

    cmd = ["mosh"]
    if ssh_opts:
        cmd.append("--ssh=" + shlex.join(["ssh"] + ssh_opts))
    cmd.append(target)

    if getattr(args, "dry_run", False):
        print_info(
            f"--dry-run: would mosh to [bold]{args.alias}[/bold] "
            f"({host.user or 'default'}@{host.host_name}). No connection made."
        )
        sys.stdout.write(shlex.join(cmd) + "\n")
        return 0

    print_info(
        f"Connecting with mosh to [bold]{args.alias}[/bold] "
        f"({host.user or 'default'}@{host.host_name})..."
    )
    try:
        return subprocess.run(cmd).returncode
    except FileNotFoundError:
        print_error(
            "mosh not found on PATH. Install it (e.g. `brew install mosh`) "
            "and ensure the server has mosh-server too."
        )
        return 127
    except KeyboardInterrupt:
        return 130
