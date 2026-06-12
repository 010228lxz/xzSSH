"""Connection event log — opt-in JSONL records of connect events.

Enabled by setting ``Config.event_log`` to a file path (``xzssh history
enable``); relative paths anchor to the config file's directory, so the
default value ``"xzssh.log"`` lands next to ``xzssh.json``. Each
``xzssh connect`` appends one JSON line::

    {"ts": "...", "alias": "db", "host_name": "...", "user": "...",
     "exit_code": 0, "duration": 12.3}

Design constraints:

- **Strictly opt-in and privacy-aware.** Nothing is written unless the
  field is set, and hosts tagged ``no-log`` are never recorded.
- **Best-effort.** A connect must never fail because the log couldn't
  be written; ``record_event`` returns a warning string instead of
  raising.
- **Disposable.** Reading skips corrupt lines instead of erroring —
  same posture as the tunnel state file.
- The file is kept ``0600``: it reveals when and where you connect.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from xzssh.model import Config, Host
from xzssh.platform import ensure_secure_file_permissions, resolve_path

# Hosts carrying this tag are never written to the event log.
NO_LOG_TAG = "no-log"

# What `xzssh history enable` stores by default: relative, so the log
# follows the config file (profiles included).
DEFAULT_EVENT_LOG = "xzssh.log"


def event_log_path(config: Config, config_path: Path) -> Optional[Path]:
    if not config.event_log:
        return None
    return resolve_path(config.event_log, config_path.parent)


def record_event(
    config: Config,
    config_path: Path,
    host: Host,
    exit_code: int,
    duration_seconds: float,
) -> Optional[str]:
    """Append one connect event. Returns a warning message on failure."""
    log_path = event_log_path(config, config_path)
    if log_path is None:
        return None
    if NO_LOG_TAG in host.tags:
        return None

    entry = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "alias": host.alias,
        "host_name": host.host_name,
        "user": host.user,
        "exit_code": exit_code,
        "duration": round(duration_seconds, 1),
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        is_new = not log_path.exists()
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if is_new:
            ensure_secure_file_permissions(log_path)
    except OSError as exc:
        return f"Could not write connection log {log_path}: {exc}"
    return None


def read_events(log_path: Path, limit: int) -> List[Dict[str, object]]:
    """The last *limit* events, newest first. Corrupt lines are skipped."""
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    events: List[Dict[str, object]] = []
    for line in reversed(lines):
        if len(events) >= limit:
            break
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and "alias" in entry:
            events.append(entry)
    return events
