"""Tests for the connection event log and ``xzssh history``.

ssh is never spawned — connect's subprocess.run is monkeypatched. The
log is strictly opt-in, best-effort, and respects the no-log tag.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import xzssh.cli.commands.connect as connect_cmd
from xzssh.cli.main import main


posix_only = pytest.mark.skipif(
    os.name != "posix", reason="POSIX permission semantics"
)


def _seed(config_path: Path, alias: str = "db", *extra: str) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", alias, "--host-name", f"{alias}.example.com",
         "--user", "alice", *extra]
    )


def _connect(config_path: Path, alias: str, monkeypatch, exit_code: int = 0) -> int:
    monkeypatch.setattr(
        connect_cmd.subprocess,
        "run",
        lambda args, **kw: SimpleNamespace(returncode=exit_code),
    )
    return main(["connect", alias, "--config", str(config_path)])


def _log_lines(config_dir: Path) -> list:
    log = config_dir / "xzssh.log"
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# opt-in plumbing
# ---------------------------------------------------------------------------

def test_logging_is_off_by_default(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    assert _connect(config_path, "db", monkeypatch) == 0
    assert _log_lines(tmp_path) == []


def test_enable_sets_field_and_default_path(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)

    rc = main(["history", "enable", "--config", str(config_path)])
    assert rc == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    # Relative by default, so the log follows the config file.
    assert data["event_log"] == "xzssh.log"


def test_enable_custom_file(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    custom = tmp_path / "logs" / "events.jsonl"

    main(["history", "enable", "--file", str(custom), "--config", str(config_path)])
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["event_log"] == str(custom)


def test_disable_keeps_log_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])
    _connect(config_path, "db", monkeypatch)
    assert len(_log_lines(tmp_path)) == 1

    rc = main(["history", "disable", "--config", str(config_path)])
    assert rc == 0
    assert "event_log" not in json.loads(config_path.read_text(encoding="utf-8"))
    # File kept; no further entries.
    _connect(config_path, "db", monkeypatch)
    assert len(_log_lines(tmp_path)) == 1


def test_clear_removes_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])
    _connect(config_path, "db", monkeypatch)

    rc = main(["history", "clear", "--config", str(config_path)])
    assert rc == 0
    assert not (tmp_path / "xzssh.log").exists()


# ---------------------------------------------------------------------------
# what gets recorded
# ---------------------------------------------------------------------------

def test_connect_appends_event(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])

    assert _connect(config_path, "db", monkeypatch) == 0

    (entry,) = _log_lines(tmp_path)
    assert entry["alias"] == "db"
    assert entry["host_name"] == "db.example.com"
    assert entry["user"] == "alice"
    assert entry["exit_code"] == 0
    assert "ts" in entry and "duration" in entry


def test_failed_connect_is_logged_too(tmp_path: Path, monkeypatch) -> None:
    """Exit codes are the point of the history view."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])

    assert _connect(config_path, "db", monkeypatch, exit_code=255) == 255
    (entry,) = _log_lines(tmp_path)
    assert entry["exit_code"] == 255


def test_no_log_tag_is_respected(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db")
    _seed(config_path, "secret", "--tag", "no-log")
    main(["history", "enable", "--config", str(config_path)])

    _connect(config_path, "secret", monkeypatch)
    assert _log_lines(tmp_path) == []
    _connect(config_path, "db", monkeypatch)
    assert [e["alias"] for e in _log_lines(tmp_path)] == ["db"]


def test_dry_run_is_not_logged(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])

    def boom(args, **kw):  # pragma: no cover - must not be reached
        raise AssertionError("dry-run must not spawn ssh")

    monkeypatch.setattr(connect_cmd.subprocess, "run", boom)
    rc = main(["connect", "db", "--dry-run", "--config", str(config_path)])
    assert rc == 0
    assert _log_lines(tmp_path) == []


def test_log_failure_never_breaks_connect(tmp_path: Path, monkeypatch) -> None:
    """The log path being unwritable degrades to a warning, not a failure."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    # Point the log at a directory — appending will fail with OSError.
    blocker = tmp_path / "blocked"
    blocker.mkdir()
    main(["history", "enable", "--file", str(blocker), "--config", str(config_path)])

    assert _connect(config_path, "db", monkeypatch) == 0  # ssh's code wins


@posix_only
def test_log_file_is_0600(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])
    _connect(config_path, "db", monkeypatch)

    mode = stat.S_IMODE((tmp_path / "xzssh.log").stat().st_mode)
    assert mode == 0o600


# ---------------------------------------------------------------------------
# the view
# ---------------------------------------------------------------------------

def test_view_disabled_hint(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()
    rc = main(["history", "--config", str(config_path)])
    assert rc == 0
    assert "history enable" in capsys.readouterr().out


def test_view_shows_events_newest_first(tmp_path: Path, monkeypatch, capsys) -> None:
    # Alias names must not collide with banner text ("Keyboard-first ...").
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "older")
    _seed(config_path, "newer")
    main(["history", "enable", "--config", str(config_path)])
    _connect(config_path, "older", monkeypatch)
    _connect(config_path, "newer", monkeypatch, exit_code=255)
    capsys.readouterr()

    rc = main(["history", "--config", str(config_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "older" in out and "newer" in out
    # Newest first: 'newer' must appear before 'older'.
    assert out.index("newer") < out.index("older")
    assert "255" in out


def test_view_limit(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "aaa")
    _seed(config_path, "bbb")
    main(["history", "enable", "--config", str(config_path)])
    _connect(config_path, "aaa", monkeypatch)
    _connect(config_path, "bbb", monkeypatch)
    capsys.readouterr()

    rc = main(["history", "--limit", "1", "--config", str(config_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "bbb" in out
    assert "aaa" not in out


def test_corrupt_log_lines_are_skipped(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["history", "enable", "--config", str(config_path)])
    _connect(config_path, "db", monkeypatch)
    with (tmp_path / "xzssh.log").open("a", encoding="utf-8") as f:
        f.write("{ not json\n")
    capsys.readouterr()

    rc = main(["history", "--config", str(config_path)])
    assert rc == 0
    assert "db" in capsys.readouterr().out
