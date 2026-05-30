from __future__ import annotations

import shlex
from pathlib import Path
from typing import List, Optional, Tuple

from xzssh.model import Host, LocalForward, RemoteForward


def parse_openssh_config(path: Path) -> Tuple[List[Host], List[str]]:
    """Best-effort parser for an OpenSSH ``ssh_config`` file.

    Returns ``(hosts, warnings)``. Constructs we deliberately don't follow —
    ``Include`` directives, ``Match`` blocks, and wildcard host patterns —
    are surfaced as warnings so the caller can show them; everything else
    we can't recognize is silently skipped per OpenSSH's own forgiving
    parser semantics.
    """
    content = path.read_text(encoding="utf-8")

    hosts: List[Host] = []
    warnings: List[str] = []
    current_hosts: List[Host] = []
    in_match_block = False

    for line_no, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        key, value = _split_directive(line)
        if key is None:
            continue

        key_lower = key.lower()

        if key_lower == "host":
            in_match_block = False
            current_hosts = []
            for alias in _split_tokens(value):
                if "*" in alias or "?" in alias or "!" in alias:
                    warnings.append(
                        f"Line {line_no}: skipped wildcard host pattern '{alias}'"
                    )
                    continue
                host = Host(alias=alias, host_name=alias)
                hosts.append(host)
                current_hosts.append(host)
            continue

        if key_lower == "match":
            in_match_block = True
            current_hosts = []
            warnings.append(
                f"Line {line_no}: 'Match' block skipped; directives inside "
                "are not imported"
            )
            continue

        if key_lower == "include":
            warnings.append(
                f"Line {line_no}: 'Include {value}' is not followed; "
                "run import on those files separately if needed"
            )
            continue

        if in_match_block or not current_hosts:
            continue

        for host in current_hosts:
            if key_lower == "hostname":
                host.host_name = value
            elif key_lower == "user":
                host.user = value
            elif key_lower == "port":
                try:
                    host.port = int(value)
                except ValueError:
                    warnings.append(
                        f"Line {line_no}: invalid Port '{value}' for host "
                        f"'{host.alias}'; skipped"
                    )
            elif key_lower == "identityfile":
                host.identity_file = value
            elif key_lower == "proxyjump":
                # OpenSSH allows comma-separated chains (`ProxyJump a,b,c`).
                # We only model a single bastion for now; preserve the raw
                # value so the user can edit it post-import.
                host.proxy_jump = value
            elif key_lower == "forwardagent":
                host.forward_agent = _parse_yes_no(value)
            elif key_lower == "compression":
                host.compression = _parse_yes_no(value)
            elif key_lower == "serveraliveinterval":
                try:
                    host.server_alive_interval = int(value)
                except ValueError:
                    warnings.append(
                        f"Line {line_no}: invalid ServerAliveInterval "
                        f"'{value}' for host '{host.alias}'; skipped"
                    )
            elif key_lower == "identitiesonly":
                host.identities_only = _parse_yes_no(value)
            elif key_lower == "stricthostkeychecking":
                host.strict_host_key_checking = value
            elif key_lower == "userknownhostsfile":
                host.user_known_hosts_file = value
            elif key_lower == "localforward":
                lf = _parse_local_forward_line(value)
                if lf is not None:
                    host.local_forwards.append(lf)
                else:
                    warnings.append(
                        f"Line {line_no}: could not parse LocalForward "
                        f"'{value}' for host '{host.alias}'; skipped"
                    )
            elif key_lower == "remoteforward":
                rf = _parse_remote_forward_line(value)
                if rf is not None:
                    host.remote_forwards.append(rf)
                else:
                    warnings.append(
                        f"Line {line_no}: could not parse RemoteForward "
                        f"'{value}' for host '{host.alias}'; skipped"
                    )
            elif key_lower == "dynamicforward":
                port = _parse_dynamic_forward_line(value)
                if port is not None:
                    host.dynamic_forwards.append(port)
                else:
                    warnings.append(
                        f"Line {line_no}: could not parse DynamicForward "
                        f"'{value}' for host '{host.alias}'; skipped"
                    )

    return hosts, warnings


def _parse_yes_no(value: str) -> Optional[bool]:
    """Map an ssh_config ``yes``/``no`` token to a bool; ``None`` if neither."""
    lowered = value.strip().lower()
    if lowered == "yes":
        return True
    if lowered == "no":
        return False
    return None


def _parse_local_forward_line(value: str) -> Optional[LocalForward]:
    # `LocalForward [bind:]port host:hostport`
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        local_port = int(parts[0].rsplit(":", 1)[-1])
        remote_host, remote_port_str = parts[1].rsplit(":", 1)
        remote_port = int(remote_port_str)
    except (ValueError, IndexError):
        return None
    if not remote_host:
        return None
    return LocalForward(local_port=local_port, remote_host=remote_host, remote_port=remote_port)


def _parse_remote_forward_line(value: str) -> Optional[RemoteForward]:
    # `RemoteForward [bind:]port host:hostport`
    parts = value.split()
    if len(parts) != 2:
        return None
    try:
        remote_port = int(parts[0].rsplit(":", 1)[-1])
        local_host, local_port_str = parts[1].rsplit(":", 1)
        local_port = int(local_port_str)
    except (ValueError, IndexError):
        return None
    if not local_host:
        return None
    return RemoteForward(remote_port=remote_port, local_host=local_host, local_port=local_port)


def _parse_dynamic_forward_line(value: str) -> Optional[int]:
    # `DynamicForward [bind:]port`
    token = value.split()[0] if value.split() else ""
    try:
        return int(token.rsplit(":", 1)[-1])
    except (ValueError, IndexError):
        return None


def _split_directive(line: str) -> Tuple[Optional[str], str]:
    # ssh_config(5): "key value" or "key=value" — first whitespace or '='
    # separates the keyword from its argument.
    for i, ch in enumerate(line):
        if ch in " \t=":
            key = line[:i].strip()
            value = line[i:].lstrip(" \t=").rstrip()
            return (key or None), _strip_quotes(value)
    return None, ""


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _split_tokens(value: str) -> List[str]:
    try:
        return shlex.split(value)
    except ValueError:
        return value.split()
