from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

from xzssh.cli.ui import print_error, print_notice, print_warning
from xzssh.crypto import encrypt
from xzssh.model import Config, Host, LocalForward, RemoteForward
from xzssh.parser import ConfigParseError, load_config_versioned
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
        config, source_version = load_config_versioned(config_path)
    except ConfigParseError as exc:
        print_error(str(exc))
        return None
    if source_version != config.version:
        _persist_migrated_config(config_path, config, source_version)
    return config


def _persist_migrated_config(
    config_path: Path, config: Config, source_version: int
) -> None:
    """One-time write-back after an in-memory schema migration.

    The original file is copied to ``.bak`` before the upgraded form is
    written. On any failure the command keeps running with the migrated
    in-memory config — migrations are idempotent by contract, so the
    upgrade simply re-runs on the next load.
    """
    backup = config_path.with_name(config_path.name + ".bak")
    try:
        shutil.copy2(config_path, backup)
        write_config(config_path, config)
    except OSError as exc:
        print_warning(
            f"Config schema was migrated in memory but the upgrade could "
            f"not be saved: {exc}"
        )
        return
    print_notice(
        f"Config schema upgraded v{source_version} → v{config.version}; "
        f"previous file saved to {backup}"
    )


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


def parse_remote_forward_arg(raw: str) -> RemoteForward:
    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise ValueError(
            "Invalid --remote-forward value. Expected remote_port:local_host:local_port"
        )
    remote_port_str, local_host, local_port_str = parts
    if not local_host:
        raise ValueError(
            "Invalid --remote-forward value. local_host must be non-empty"
        )
    try:
        remote_port = int(remote_port_str)
        local_port = int(local_port_str)
    except ValueError as exc:
        raise ValueError("RemoteForward ports must be integers") from exc

    return RemoteForward(
        remote_port=remote_port,
        local_host=local_host,
        local_port=local_port,
    )


def write_config(config_path: Path, config: Config) -> None:
    """Persist a Config atomically with restrictive permissions.

    Writes to a sibling ``.tmp`` file, applies POSIX 0600 (or Windows ACL
    equivalent), then ``os.replace``\\s into place — so a crash mid-write
    cannot leave the live config truncated. The JSON source contains host
    metadata and identity-file paths and is treated as secret.

    When ``config.encryption`` is set the payload is run through the
    gpg/age envelope first (prompting for the passphrase); a failed or
    cancelled prompt raises ``EnvelopeError`` **before** anything is
    touched on disk, and ``main`` reports it as a clean error.
    """
    payload_text = json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n"
    if config.encryption:
        payload = encrypt(payload_text, config.encryption)
    else:
        payload = payload_text.encode("utf-8")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = config_path.with_name(config_path.name + ".tmp")
    try:
        tmp_path.write_bytes(payload)
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
    # Scalar ssh options become `-o Key=value`. Forwards are deliberately
    # NOT injected here — they belong in the generated config, not in an
    # interactive connect/which/test command line.
    for key, value in _scalar_ssh_options(host):
        args.extend(["-o", f"{key}={value}"])
    if extra_options:
        args.extend(extra_options)
    target = host.host_name
    if host.user:
        target = f"{host.user}@{target}"
    args.append(target)
    return args


def _scalar_ssh_options(host: Host):
    """Yield (ssh_option, value) pairs for the host's scalar SSH settings."""
    if host.forward_agent is not None:
        yield "ForwardAgent", "yes" if host.forward_agent else "no"
    if host.compression is not None:
        yield "Compression", "yes" if host.compression else "no"
    if host.server_alive_interval is not None:
        yield "ServerAliveInterval", str(host.server_alive_interval)
    if host.identities_only is not None:
        yield "IdentitiesOnly", "yes" if host.identities_only else "no"
    if host.strict_host_key_checking is not None:
        yield "StrictHostKeyChecking", host.strict_host_key_checking
    if host.user_known_hosts_file is not None:
        yield "UserKnownHostsFile", host.user_known_hosts_file
