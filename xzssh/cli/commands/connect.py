from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import questionary

from xzssh.cli.eventlog import record_event
from xzssh.cli.helpers import (
    build_ssh_command,
    filter_hosts_by_tags,
    load_config_or_error,
    write_config,
)
from xzssh.cli.ui import print_error, print_info, print_warning


def run(
    args: argparse.Namespace,
    config_path: Path,
    suggest_ports: bool,
    tags: Optional[List[str]] = None,
    match_all: bool = False,
) -> int:
    tags = list(tags or [])
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    alias = args.alias
    if not alias:
        # Tags only narrow the fuzzy-search candidates; they are ignored when
        # the caller already provided an explicit alias.
        candidates = filter_hosts_by_tags(config.hosts, tags, match_all)
        if not candidates:
            if tags:
                print_error(f"No hosts match tag(s): {', '.join(tags)}")
            else:
                print_error("No hosts configured.")
            return 1

        meta_info = {
            h.alias: f"{h.host_name} ({h.user or 'default'})"
            for h in candidates
        }
        alias = questionary.autocomplete(
            "Search and connect to host:",
            choices=[
                h.alias
                for h in sorted(
                    candidates, key=lambda x: (x.last_used or ""), reverse=True
                )
            ],
            meta_information=meta_info,
            ignore_case=True,
        ).ask()

        if not alias:
            print_error("No host selected.")
            return 1

    host = next((h for h in config.hosts if h.alias == alias), None)
    if not host:
        print_error(f"Host not found: {alias}")
        return 1

    ssh_args = build_ssh_command(host)

    # getattr (not args.dry_run): the interactive menus call run() with a
    # hand-built Namespace that has no dry_run attribute.
    if getattr(args, "dry_run", False):
        print_info(
            f"--dry-run: would connect to [bold]{alias}[/bold] "
            f"({host.user or 'default'}@{host.host_name}). No connection made."
        )
        # The command on its own clean line, bypassing rich so it isn't wrapped.
        sys.stdout.write(shlex.join(ssh_args) + "\n")
        return 0

    print_info(
        f"Connecting to [bold]{alias}[/bold] "
        f"({host.user or 'default'}@{host.host_name})..."
    )

    returncode = 0
    started = time.monotonic()
    try:
        returncode = subprocess.run(ssh_args).returncode
    except KeyboardInterrupt:
        returncode = 130
    duration = time.monotonic() - started

    # Failed connects are logged too — exit codes are the point of the
    # history view. Logging is best-effort and must never fail the connect.
    log_warning = record_event(config, config_path, host, returncode, duration)
    if log_warning:
        print_warning(log_warning)

    # OpenSSH returns 255 for connection-setup failure. Any other code means
    # we did successfully connect (even if the remote shell exited non-zero).
    if returncode != 255:
        host.last_used = datetime.now().isoformat()
        write_config(config_path, config)

    return returncode
