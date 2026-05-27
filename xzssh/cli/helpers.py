from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List, Optional

from xzssh.cli.ui import print_error
from xzssh.model import Config, Host, LocalForward
from xzssh.parser import ConfigParseError, load_config
from xzssh.platform import ensure_secure_file_permissions, resolve_path


def load_config_or_error(config_path: Path) -> Optional[Config]:
    config = load_config_if_exists(config_path)
    if config is None:
        print_error(f"Config file not found: {config_path}")
        return None
    return config


def load_config_if_exists(config_path: Path) -> Optional[Config]:
    if not config_path.exists():
        return None
    try:
        return load_config(config_path)
    except ConfigParseError as exc:
        print_error(str(exc))
        return None


def parse_local_forward_arg(raw: str) -> LocalForward:
    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise ValueError(
            "Invalid --local-forward value. Expected local_port:remote_host:remote_port"
        )
    local_port_str, remote_host, remote_port_str = parts
    if not remote_host:
        raise ValueError(
            "Invalid --local-forward value. remote_host must be non-empty"
        )
    try:
        local_port = int(local_port_str)
        remote_port = int(remote_port_str)
    except ValueError as exc:
        raise ValueError("LocalForward ports must be integers") from exc

    return LocalForward(
        local_port=local_port,
        remote_host=remote_host,
        remote_port=remote_port,
    )


def write_config(config_path: Path, config: Config) -> None:
    """Persist a Config atomically with restrictive permissions.

    Writes to a sibling ``.tmp`` file, applies POSIX 0600 (or Windows ACL
    equivalent), then ``os.replace``\\s into place — so a crash mid-write
    cannot leave the live config truncated. The JSON source contains host
    metadata and identity-file paths and is treated as secret.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n"

    tmp_path = config_path.with_name(config_path.name + ".tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        # Apply restrictive perms BEFORE moving into place so there's no
        # window where the live file exists with default perms.
        ensure_secure_file_permissions(tmp_path)
        os.replace(tmp_path, config_path)
    except OSError:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def resolve_key_path(path_value: str, source_path: Path) -> Path:
    return resolve_path(path_value, source_path.parent)


def filter_hosts_by_tags(hosts: List[Host], tags: List[str]) -> List[Host]:
    """Return hosts that have at least one of the given tags (OR semantics).

    When *tags* is empty every host is returned unchanged, preserving the
    default "show everything" behaviour.
    """
    if not tags:
        return hosts
    tag_set = set(tags)
    return [h for h in hosts if tag_set & set(h.tags)]


def build_ssh_command(
    host: Host, extra_options: Optional[List[str]] = None
) -> List[str]:
    """Build the ``ssh`` argv for connecting to *host*.

    Centralised so ``connect``, ``test``, and future commands like ``which``
    all share one source of truth. ``extra_options`` is appended verbatim
    before the connection target (useful for ``-o BatchMode=yes`` and
    similar overrides).
    """
    args: List[str] = ["ssh"]
    if host.port:
        args.extend(["-p", str(host.port)])
    if host.identity_file:
        args.extend(["-i", host.identity_file])
    if host.proxy_jump:
        args.extend(["-J", host.proxy_jump])
    if extra_options:
        args.extend(extra_options)
    target = host.host_name
    if host.user:
        target = f"{host.user}@{target}"
    args.append(target)
    return args
