from __future__ import annotations

import shlex
from pathlib import Path
from typing import List, Optional, Tuple

from xzssh.model import Host


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

    return hosts, warnings


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
