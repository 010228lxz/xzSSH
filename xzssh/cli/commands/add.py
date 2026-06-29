from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Optional

from xzssh.cli.helpers import (
    load_config_if_exists,
    parse_local_forward_arg,
    parse_option_arg,
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
    from_alias = getattr(args, "from_alias", None)

    with status("Preparing to add host"):
        config = load_config_if_exists(config_path)
    if config is None:
        config = Config(hosts=[])

    source: Optional[Host] = None
    if from_alias:
        source = next((h for h in config.hosts if h.alias == from_alias), None)
        if source is None:
            print_error(f"--from: source host not found: {from_alias}")
            return 1
        if not args.alias:
            print_error("--from requires a new --alias for the cloned host.")
            return 2
    elif not args.alias or not args.host_name:
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

    options: Dict[str, str] = {}
    for raw in getattr(args, "option", []) or []:
        try:
            opt_key, opt_value = parse_option_arg(raw)
        except ValueError as exc:
            print_error(str(exc))
            return 2
        options[opt_key] = opt_value

    # When cloning (--from), an unset scalar / empty list inherits the
    # source host's value; an explicit flag always wins. last_used is
    # never copied — the clone hasn't been connected to.
    def scalar(provided, attr):
        if provided is not None:
            return provided
        return getattr(source, attr) if source else None

    def listf(provided, parsed, attr):
        if provided:
            return parsed
        return list(getattr(source, attr)) if source else list(parsed)

    new_host = Host(
        alias=args.alias,
        host_name=scalar(args.host_name, "host_name"),
        user=scalar(args.user, "user"),
        port=scalar(args.port, "port"),
        identity_file=scalar(args.identity_file, "identity_file"),
        proxy_jump=scalar(getattr(args, "proxy_jump", None), "proxy_jump"),
        forward_agent=scalar(getattr(args, "forward_agent", None), "forward_agent"),
        compression=scalar(getattr(args, "compression", None), "compression"),
        server_alive_interval=scalar(
            getattr(args, "server_alive_interval", None), "server_alive_interval"
        ),
        identities_only=scalar(
            getattr(args, "identities_only", None), "identities_only"
        ),
        strict_host_key_checking=scalar(
            getattr(args, "strict_host_key_checking", None),
            "strict_host_key_checking",
        ),
        user_known_hosts_file=scalar(
            getattr(args, "user_known_hosts_file", None), "user_known_hosts_file"
        ),
        local_forwards=listf(args.local_forward, local_forwards, "local_forwards"),
        remote_forwards=listf(
            getattr(args, "remote_forward", []) or [], remote_forwards,
            "remote_forwards",
        ),
        dynamic_forwards=listf(
            getattr(args, "dynamic_forward", []) or [],
            list(getattr(args, "dynamic_forward", []) or []),
            "dynamic_forwards",
        ),
        tags=listf(args.tag, args.tag, "tags"),
        options=options if options else (dict(source.options) if source else {}),
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
