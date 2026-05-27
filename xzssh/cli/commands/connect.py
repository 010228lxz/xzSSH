from __future__ import annotations

import argparse
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import questionary

from xzssh.cli.helpers import (
    build_ssh_command,
    filter_hosts_by_tags,
    load_config_or_error,
    write_config,
)
from xzssh.cli.ui import print_error, print_info


def run(
    args: argparse.Namespace,
    config_path: Path,
    suggest_ports: bool,
    tags: Optional[List[str]] = None,
) -> int:
    tags = list(tags or [])
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    alias = args.alias
    if not alias:
        # Tags only narrow the fuzzy-search candidates; they are ignored when
        # the caller already provided an explicit alias.
        candidates = filter_hosts_by_tags(config.hosts, tags)
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

    print_info(
        f"Connecting to [bold]{alias}[/bold] "
        f"({host.user or 'default'}@{host.host_name})..."
    )

    ssh_args = build_ssh_command(host)

    returncode = 0
    try:
        returncode = subprocess.run(ssh_args).returncode
    except KeyboardInterrupt:
        returncode = 130

    # OpenSSH returns 255 for connection-setup failure. Any other code means
    # we did successfully connect (even if the remote shell exited non-zero).
    if returncode != 255:
        host.last_used = datetime.now().isoformat()
        write_config(config_path, config)

    return returncode
