from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
class Host:
    alias: str
    host_name: str
    user: Optional[str] = None
    port: Optional[int] = None
    identity_file: Optional[str] = None
    proxy_jump: Optional[str] = None
    local_forwards: List[LocalForward] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    last_used: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "alias": self.alias,
            "host_name": self.host_name,
            "local_forwards": [lf.to_dict() for lf in self.local_forwards],
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
        if self.last_used is not None:
            data["last_used"] = self.last_used
        return data


@dataclass
class Config:
    version: int = 1
    hosts: List[Host] = field(default_factory=list)
    keys: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "version": self.version,
            "hosts": [host.to_dict() for host in self.hosts],
            "keys": dict(self.keys),
        }
