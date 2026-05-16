from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from xzssh.cli.helpers import (
    load_config_if_exists,
    parse_local_forward_arg,
    write_config,
)
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_success,
    print_warnings,
    prompt_host_details,
    status,
)
from xzssh.model import Config, Host, LocalForward
from xzssh.validator import validate_config


def run(args: argparse.Namespace, config_path: Path) -> int:
    if not args.alias or not args.host_name:
        details = prompt_host_details()
        if not details:
            print_error("Host addition cancelled.")
            return 1
        args.alias = details["alias"]
        args.host_name = details["host_name"]
        args.user = details["user"]
        args.port = details["port"]
        args.identity_file = details["identity_file"]
        args.tag = details.get("tags", [])

    with status("Preparing to add host"):
        config = load_config_if_exists(config_path)
    if config is None:
        config = Config(version=1, hosts=[])

    local_forwards: List[LocalForward] = []
    for raw in args.local_forward:
        try:
            local_forwards.append(parse_local_forward_arg(raw))
        except ValueError as exc:
            print_error(str(exc))
            return 2

    new_host = Host(
        alias=args.alias,
        host_name=args.host_name,
        user=args.user,
        port=args.port,
        identity_file=args.identity_file,
        local_forwards=local_forwards,
        tags=args.tag,
    )

    replaced = False
    for idx, host in enumerate(config.hosts):
        if host.alias == new_host.alias:
            if not args.replace:
                print_error(
                    f"Host alias already exists: {new_host.alias}. "
                    "Use --replace to overwrite."
                )
                return 1
            config.hosts[idx] = new_host
            replaced = True
            break

    if not replaced:
        config.hosts.append(new_host)

    with status("Validating new configuration"):
        result = validate_config(
            config, suggest_ports=args.suggest_ports, source_path=config_path
        )
    if result.errors:
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    with status("Persisting changes"):
        write_config(config_path, config)
    print_success(f"Host '{args.alias}' has been added to the configuration.")
    return 0
