"""``xzssh which <alias>`` — print the resolved ssh command without running it.

A debug aid for verifying how an alias expands — ProxyJump, IdentityFile,
port, and user resolution — without opening a session. The output is a
single, copy-pasteable command line, so ``$(xzssh which db)`` works in a
shell.

Prints nothing but the command to stdout (no banner, no decoration) so
the output stays machine-consumable. Errors go to stderr.
"""
from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from xzssh.cli.helpers import build_ssh_command, load_config_or_error
from xzssh.cli.ui import console, print_error


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    alias = getattr(args, "alias", None)
    if not alias:
        print_error("No alias provided.")
        return 2

    host = next((h for h in config.hosts if h.alias == alias), None)
    if host is None:
        print_error(f"Host not found: {alias}")
        return 1

    ssh_args = build_ssh_command(host)
    # shlex.join quotes anything that would otherwise break a shell paste
    # (spaces in paths, etc.). Print raw — no rich markup — so redirection
    # captures exactly the command and nothing else.
    console.print(shlex.join(ssh_args), markup=False, highlight=False)
    return 0
