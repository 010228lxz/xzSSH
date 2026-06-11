from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from xzssh.cli.helpers import (
    load_config_if_exists,
    parse_local_forward_arg,
    parse_remote_forward_arg,
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
from xzssh.model import Config, Host, LocalForward, RemoteForward
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
        args.proxy_jump = details.get("proxy_jump")
        args.tag = details.get("tags", [])

    with status("Preparing to add host"):
        config = load_config_if_exists(config_path)
    if config is None:
        config = Config(hosts=[])

    local_forwards: List[LocalForward] = []
    for raw in args.local_forward:
        try:
            local_forwards.append(parse_local_forward_arg(raw))
        except ValueError as exc:
            print_error(str(exc))
            return 2

    remote_forwards: List[RemoteForward] = []
    for raw in getattr(args, "remote_forward", []) or []:
        try:
            remote_forwards.append(parse_remote_forward_arg(raw))
        except ValueError as exc:
            print_error(str(exc))
            return 2

    new_host = Host(
        alias=args.alias,
        host_name=args.host_name,
        user=args.user,
        port=args.port,
        identity_file=args.identity_file,
        proxy_jump=getattr(args, "proxy_jump", None),
        forward_agent=getattr(args, "forward_agent", None),
        compression=getattr(args, "compression", None),
        server_alive_interval=getattr(args, "server_alive_interval", None),
        identities_only=getattr(args, "identities_only", None),
        strict_host_key_checking=getattr(args, "strict_host_key_checking", None),
        user_known_hosts_file=getattr(args, "user_known_hosts_file", None),
        local_forwards=local_forwards,
        remote_forwards=remote_forwards,
        dynamic_forwards=list(getattr(args, "dynamic_forward", []) or []),
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
