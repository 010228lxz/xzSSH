"""Tunnel state — records of detached ``ssh -N`` processes.

``xzssh tunnel start --detach`` spawns ssh in its own session and exits;
this module remembers what was spawned so ``tunnel list`` / ``tunnel
stop`` can find it later. The state is disposable runtime data, not
configuration, so it lives in the *state* directory, not config:

- POSIX: ``$XDG_STATE_HOME/xzssh/tunnels.json`` (default
  ``~/.local/state/xzssh/tunnels.json``)
- Windows: ``%LOCALAPPDATA%\\xzssh\\tunnels.json``
- ``$XZSSH_TUNNELS_FILE`` overrides outright (test hermeticity).

A record is only ever advisory — the source of truth for "is the
tunnel up" is the pid, checked via ``xzssh.platform.process.pid_alive``.
Dead records are pruned on ``tunnel list``.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from xzssh.platform import (
    Platform,
    detect_platform,
    ensure_secure_file_permissions,
)


@dataclass
class TunnelRecord:
    alias: str
    pid: int
    started_at: str
    forwards: List[str] = field(default_factory=list)
    log_file: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "alias": self.alias,
            "pid": self.pid,
            "started_at": self.started_at,
            "forwards": list(self.forwards),
        }
        if self.log_file is not None:
            data["log_file"] = self.log_file
        return data


def state_path() -> Path:
    override = os.environ.get("XZSSH_TUNNELS_FILE")
    if override:
        return Path(override).expanduser()
    if detect_platform() == Platform.WINDOWS:
        base = os.environ.get("LOCALAPPDATA")
        base_path = (
            Path(base) if base else Path.home() / "AppData" / "Local"
        )
    else:
        base = os.environ.get("XDG_STATE_HOME")
        base_path = (
            Path(base).expanduser() if base else Path.home() / ".local" / "state"
        )
    return base_path / "xzssh" / "tunnels.json"


def load_state(path: Path) -> List[TunnelRecord]:
    """Read tunnel records; missing or corrupt state is just empty.

    State is disposable — a corrupt file must never block ``tunnel``
    commands, the worst case is forgetting about an orphaned ssh.
    """
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []

    records: List[TunnelRecord] = []
    for entry in data.get("tunnels", []):
        if not isinstance(entry, dict):
            continue
        alias = entry.get("alias")
        pid = entry.get("pid")
        if not isinstance(alias, str) or not isinstance(pid, int):
            continue
        forwards = entry.get("forwards", [])
        records.append(
            TunnelRecord(
                alias=alias,
                pid=pid,
                started_at=str(entry.get("started_at", "")),
                forwards=[str(f) for f in forwards]
                if isinstance(forwards, list)
                else [],
                log_file=entry.get("log_file"),
            )
        )
    return records


def save_state(path: Path, records: List[TunnelRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {"tunnels": [r.to_dict() for r in records]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        ensure_secure_file_permissions(tmp_path)
        os.replace(tmp_path, path)
    except OSError:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
