from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Schema version this code reads and writes. Bumping it requires
# registering a migration in xzssh/parser/migrations.py — see the
# contract documented there. Never lower it, never re-use a number.
CURRENT_SCHEMA_VERSION = 1


@dataclass
class LocalForward:
    local_port: int
    remote_host: str
    remote_port: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "local_port": self.local_port,
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
        }


@dataclass
class RemoteForward:
    """An ``ssh -R`` rule: open ``remote_port`` on the server, forward it to
    ``local_host:local_port`` on the client side. Mirror of LocalForward."""

    remote_port: int
    local_host: str
    local_port: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "remote_port": self.remote_port,
            "local_host": self.local_host,
            "local_port": self.local_port,
        }


@dataclass
class Host:
    alias: str
    host_name: str
    user: Optional[str] = None
    port: Optional[int] = None
    identity_file: Optional[str] = None
    proxy_jump: Optional[str] = None
    # Scalar SSH options. Bools are tri-state: None = unset (emit nothing),
    # True/False = explicit yes/no.
    forward_agent: Optional[bool] = None
    compression: Optional[bool] = None
    server_alive_interval: Optional[int] = None
    identities_only: Optional[bool] = None
    strict_host_key_checking: Optional[str] = None
    user_known_hosts_file: Optional[str] = None
    local_forwards: List[LocalForward] = field(default_factory=list)
    remote_forwards: List[RemoteForward] = field(default_factory=list)
    dynamic_forwards: List[int] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    last_used: Optional[str] = None
    # Escape hatch: free-form ssh_config directives rendered verbatim
    # after the typed fields (e.g. {"ControlMaster": "auto"}). Lets users
    # set any directive xzSSH doesn't model first-class without a code
    # change. Insertion order is preserved for deterministic output; the
    # managed typed fields render first, so they win on a duplicate.
    options: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "alias": self.alias,
            "host_name": self.host_name,
            "local_forwards": [lf.to_dict() for lf in self.local_forwards],
            "remote_forwards": [rf.to_dict() for rf in self.remote_forwards],
            "dynamic_forwards": list(self.dynamic_forwards),
            "options": dict(self.options),
            "tags": list(self.tags),
        }
        if self.user is not None:
            data["user"] = self.user
        if self.port is not None:
            data["port"] = self.port
        if self.identity_file is not None:
            data["identity_file"] = self.identity_file
        if self.proxy_jump is not None:
            data["proxy_jump"] = self.proxy_jump
        if self.forward_agent is not None:
            data["forward_agent"] = self.forward_agent
        if self.compression is not None:
            data["compression"] = self.compression
        if self.server_alive_interval is not None:
            data["server_alive_interval"] = self.server_alive_interval
        if self.identities_only is not None:
            data["identities_only"] = self.identities_only
        if self.strict_host_key_checking is not None:
            data["strict_host_key_checking"] = self.strict_host_key_checking
        if self.user_known_hosts_file is not None:
            data["user_known_hosts_file"] = self.user_known_hosts_file
        if self.last_used is not None:
            data["last_used"] = self.last_used
        return data


@dataclass
class Config:
    version: int = CURRENT_SCHEMA_VERSION
    hosts: List[Host] = field(default_factory=list)
    keys: Dict[str, str] = field(default_factory=dict)
    # At-rest encryption opt-in: "gpg" or "age" (None = plaintext). The
    # field travels inside the (decrypted) JSON, so the choice survives
    # round-trips; write_config envelopes the file whenever it is set.
    encryption: Optional[str] = None
    # Connection event log opt-in: path to a JSONL file (relative paths
    # anchor to the config file's directory, like identity_file). None =
    # disabled. Privacy-sensitive, so strictly opt-in; hosts tagged
    # "no-log" are never recorded.
    event_log: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "version": self.version,
            "hosts": [host.to_dict() for host in self.hosts],
            "keys": dict(self.keys),
        }
        if self.encryption is not None:
            data["encryption"] = self.encryption
        if self.event_log is not None:
            data["event_log"] = self.event_log
        return data
