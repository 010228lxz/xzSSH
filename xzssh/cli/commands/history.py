"""``xzssh history`` — recent connections, from the opt-in event log.

- ``history`` — show the last connections (default 50, ``--limit N``),
  newest first, with timestamps, exit codes, and durations.
- ``history enable [--file PATH]`` — opt in: sets ``Config.event_log``
  (default ``"xzssh.log"``, i.e. next to the config file).
- ``history disable`` — stop logging; the existing log file is kept.
- ``history clear`` — delete the log file (logging state unchanged).

The log only ever gains entries from ``xzssh connect``; hosts tagged
``no-log`` are never recorded.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from xzssh.cli.eventlog import (
    DEFAULT_EVENT_LOG,
    NO_LOG_TAG,
    event_log_path,
    read_events,
)
from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import (
    print_error,
    print_history_table,
    print_info,
    print_success,
)


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    command = getattr(args, "history_command", None)
    if command == "enable":
        return _enable(args, config, config_path)
    if command == "disable":
        return _disable(config, config_path)
    if command == "clear":
        return _clear(config, config_path)
    if command is None:
        return _view(args, config, config_path)
    print_error(f"Unknown history command: {command}")
    return 2


def _view(args: argparse.Namespace, config, config_path: Path) -> int:
    log_path = event_log_path(config, config_path)
    if log_path is None:
        print_info(
            "Connection logging is disabled. Opt in with "
            "`xzssh history enable` (hosts tagged "
            f"'{NO_LOG_TAG}' are never recorded)."
        )
        return 0

    events = read_events(log_path, limit=args.limit)
    if not events:
        print_info(
            f"No connections recorded yet (log: {log_path}). "
            "They will appear here after `xzssh connect`."
        )
        return 0

    print_history_table(events)
    return 0


def _enable(args: argparse.Namespace, config, config_path: Path) -> int:
    value = args.file or DEFAULT_EVENT_LOG
    config.event_log = value
    write_config(config_path, config)

    resolved = event_log_path(config, config_path)
    print_success(f"Connection logging enabled → {resolved}")
    print_info(
        f"Tag a host '{NO_LOG_TAG}' to keep it out of the log. "
        "Disable anytime with `xzssh history disable`."
    )
    return 0


def _disable(config, config_path: Path) -> int:
    if config.event_log is None:
        print_info("Connection logging is already disabled.")
        return 0
    log_path = event_log_path(config, config_path)
    config.event_log = None
    write_config(config_path, config)
    print_success(
        f"Connection logging disabled. The existing log ({log_path}) was "
        "kept — remove it with `xzssh history clear` if you don't want it."
    )
    return 0


def _clear(config, config_path: Path) -> int:
    log_path = event_log_path(config, config_path)
    if log_path is None:
        print_info("Connection logging is disabled; nothing to clear.")
        return 0
    try:
        log_path.unlink()
    except FileNotFoundError:
        print_info("No log file to clear.")
        return 0
    except OSError as exc:
        print_error(f"Could not remove {log_path}: {exc}")
        return 1
    print_success(f"Cleared connection log {log_path}.")
    return 0
