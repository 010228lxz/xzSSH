"""Drift detection between the JSON source of truth and an OpenSSH file.

Pure comparison logic — no I/O, no printing. The CLI feeds it two host
lists (the JSON config's and the one parsed from ``~/.ssh/config``) and
gets back a structured report it can render or act on.

Only ssh-representable fields participate: JSON-side metadata that
cannot appear in an ``ssh_config`` (``tags``, ``last_used``) is neither
compared nor ever overwritten by a file-wins resolution.

Normalizations applied before comparing, to avoid false drift:

- ``identity_file`` is resolved on both sides (the generator writes
  absolute paths; hand edits and the JSON may use ``~`` or
  source-relative paths).
- An unset ``Port`` equals an explicit 22 — removing a redundant
  ``Port 22`` line is not drift.
- Forward lists compare order-insensitively.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from xzssh.model import Host
from xzssh.platform import resolve_path


# Host attributes a file-wins resolution may copy onto the JSON host.
SYNCED_SCALAR_FIELDS = (
    "host_name",
    "user",
    "port",
    "identity_file",
    "proxy_jump",
    "forward_agent",
    "compression",
    "server_alive_interval",
    "identities_only",
    "strict_host_key_checking",
    "user_known_hosts_file",
)
SYNCED_LIST_FIELDS = ("local_forwards", "remote_forwards", "dynamic_forwards")


@dataclass
class FieldChange:
    field: str  # Host attribute name
    json_value: object
    file_value: object


@dataclass
class HostDrift:
    alias: str
    kind: str  # "added" (file only) | "removed" (JSON only) | "changed"
    json_host: Optional[Host] = None
    file_host: Optional[Host] = None
    changes: List[FieldChange] = field(default_factory=list)


@dataclass
class DriftReport:
    drifts: List[HostDrift] = field(default_factory=list)
    # Constructs the file has but the model can't represent
    # (Match / Include / wildcard patterns) — these don't count as
    # drift, but a json-wins regeneration would wipe them.
    warnings: List[str] = field(default_factory=list)

    @property
    def in_sync(self) -> bool:
        return not self.drifts


def comparable_host_dict(host: Host, base_dir: Optional[Path]) -> Dict[str, object]:
    """The normalized, comparison-ready view of a host."""
    return {
        "host_name": host.host_name,
        "user": host.user,
        "port": host.port if host.port is not None else 22,
        "identity_file": (
            str(resolve_path(host.identity_file, base_dir))
            if host.identity_file
            else None
        ),
        "proxy_jump": host.proxy_jump,
        "forward_agent": host.forward_agent,
        "compression": host.compression,
        "server_alive_interval": host.server_alive_interval,
        "identities_only": host.identities_only,
        "strict_host_key_checking": host.strict_host_key_checking,
        "user_known_hosts_file": host.user_known_hosts_file,
        "local_forwards": sorted(
            (lf.local_port, lf.remote_host, lf.remote_port)
            for lf in host.local_forwards
        ),
        "remote_forwards": sorted(
            (rf.remote_port, rf.local_host, rf.local_port)
            for rf in host.remote_forwards
        ),
        "dynamic_forwards": sorted(host.dynamic_forwards),
    }


def compare_hosts(
    json_hosts: List[Host],
    file_hosts: List[Host],
    json_base_dir: Optional[Path],
    file_base_dir: Optional[Path],
    parse_warnings: Optional[List[str]] = None,
) -> DriftReport:
    report = DriftReport(warnings=list(parse_warnings or []))

    json_by_alias = {h.alias: h for h in json_hosts}
    file_by_alias: Dict[str, Host] = {}
    for host in file_hosts:
        if host.alias in file_by_alias:
            report.warnings.append(
                f"Duplicate 'Host {host.alias}' in file; the last "
                "definition wins for comparison"
            )
        file_by_alias[host.alias] = host

    for alias in sorted(set(json_by_alias) | set(file_by_alias)):
        json_host = json_by_alias.get(alias)
        file_host = file_by_alias.get(alias)

        if json_host is None:
            report.drifts.append(
                HostDrift(alias=alias, kind="added", file_host=file_host)
            )
            continue
        if file_host is None:
            report.drifts.append(
                HostDrift(alias=alias, kind="removed", json_host=json_host)
            )
            continue

        json_view = comparable_host_dict(json_host, json_base_dir)
        file_view = comparable_host_dict(file_host, file_base_dir)
        changes = [
            FieldChange(field=key, json_value=json_view[key], file_value=file_view[key])
            for key in json_view
            if json_view[key] != file_view[key]
        ]
        if changes:
            report.drifts.append(
                HostDrift(
                    alias=alias,
                    kind="changed",
                    json_host=json_host,
                    file_host=file_host,
                    changes=changes,
                )
            )

    return report


def apply_file_version(drift: HostDrift) -> None:
    """Mutate the JSON-side host to match the file for a 'changed' drift.

    Only the fields that actually differ are copied (raw values, not
    the normalized comparison views), so JSON-side conventions like a
    ``~``-relative identity_file survive when that field didn't drift.
    Tags and last_used are never touched.
    """
    assert drift.kind == "changed" and drift.json_host and drift.file_host
    for change in drift.changes:
        value = getattr(drift.file_host, change.field)
        if change.field in SYNCED_LIST_FIELDS:
            value = list(value)
        setattr(drift.json_host, change.field, value)
