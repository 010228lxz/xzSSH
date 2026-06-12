"""Tests for ``xzssh sync`` — drift detection and resolution.

Strategy: build a real JSON config through the CLI, ``generate`` the
file, then hand-edit one side and assert the report / the chosen
resolution. No ssh involved anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import xzssh.cli.commands.sync as sync_cmd
from xzssh.cli.main import main
from xzssh.model import Host, LocalForward
from xzssh.sync import compare_hosts


def _setup(tmp_path: Path) -> tuple:
    """A config with one host, generated to a file — in sync by construction."""
    config_path = tmp_path / "xzssh.json"
    output_path = tmp_path / "config"
    main(
        ["add", "--config", str(config_path),
         "--alias", "db", "--host-name", "db.example.com",
         "--user", "alice", "--port", "2222", "--tag", "prod"]
    )
    rc = main(
        ["generate", "--config", str(config_path), "--output", str(output_path)]
    )
    assert rc == 0
    return config_path, output_path


def _sync(config_path: Path, output_path: Path, *extra: str) -> int:
    return main(
        ["sync", "--config", str(config_path), "--output", str(output_path),
         *extra]
    )


# ---------------------------------------------------------------------------
# report mode (no flags)
# ---------------------------------------------------------------------------

def test_in_sync_exits_zero(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    assert _sync(config_path, output_path) == 0


def test_changed_field_is_drift(tmp_path: Path, capsys) -> None:
    config_path, output_path = _setup(tmp_path)
    content = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        content.replace("Port 2222", "Port 9999"), encoding="utf-8"
    )
    capsys.readouterr()

    rc = _sync(config_path, output_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert "db" in out
    assert "port" in out
    # Report mode never writes.
    assert "Port 9999" in output_path.read_text(encoding="utf-8")


def test_hand_added_host_is_drift(tmp_path: Path, capsys) -> None:
    config_path, output_path = _setup(tmp_path)
    with output_path.open("a", encoding="utf-8") as f:
        f.write("\nHost web\n  HostName web.example.com\n  User bob\n")
    capsys.readouterr()

    assert _sync(config_path, output_path) == 1
    assert "web" in capsys.readouterr().out


def test_json_only_host_is_drift(tmp_path: Path, capsys) -> None:
    config_path, output_path = _setup(tmp_path)
    main(
        ["add", "--config", str(config_path),
         "--alias", "extra", "--host-name", "extra.example.com"]
    )
    capsys.readouterr()
    assert _sync(config_path, output_path) == 1
    assert "extra" in capsys.readouterr().out


def test_missing_file_is_drift(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    output_path.unlink()
    assert _sync(config_path, output_path) == 1


def test_removed_redundant_port22_is_not_drift(tmp_path: Path) -> None:
    """Port unset ≡ Port 22 — explicitness is not drift."""
    config_path = tmp_path / "xzssh.json"
    output_path = tmp_path / "config"
    main(
        ["add", "--config", str(config_path),
         "--alias", "db", "--host-name", "db.example.com", "--port", "22"]
    )
    main(["generate", "--config", str(config_path), "--output", str(output_path)])

    stripped = "\n".join(
        line
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if "Port 22" not in line
    )
    output_path.write_text(stripped + "\n", encoding="utf-8")

    assert _sync(config_path, output_path) == 0


def test_identity_path_resolution_is_not_drift(tmp_path: Path) -> None:
    """JSON-relative identity vs generated-absolute must compare equal."""
    json_host = Host(
        alias="db", host_name="db.example.com", identity_file="id_test"
    )
    file_host = Host(
        alias="db",
        host_name="db.example.com",
        identity_file=str(tmp_path / "id_test"),
    )
    report = compare_hosts(
        [json_host], [file_host],
        json_base_dir=tmp_path, file_base_dir=tmp_path,
    )
    assert report.in_sync


# ---------------------------------------------------------------------------
# --prefer json
# ---------------------------------------------------------------------------

def test_prefer_json_regenerates_file(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    output_path.write_text("Host db\n  HostName hijacked\n", encoding="utf-8")

    rc = _sync(config_path, output_path, "--prefer", "json")
    assert rc == 0
    content = output_path.read_text(encoding="utf-8")
    assert "db.example.com" in content
    assert "hijacked" not in content
    # The hand-edited file was backed up.
    assert "hijacked" in (
        output_path.with_name("config.bak").read_text(encoding="utf-8")
    )
    assert _sync(config_path, output_path) == 0


def test_unmodeled_constructs_alone_are_not_drift(tmp_path: Path) -> None:
    """Hosts match, file has an extra Match block → in sync, nothing wiped."""
    config_path, output_path = _setup(tmp_path)
    with output_path.open("a", encoding="utf-8") as f:
        f.write("\nMatch user root\n  Compression yes\n")
    before = output_path.read_text(encoding="utf-8")

    assert _sync(config_path, output_path, "--prefer", "json") == 0
    assert output_path.read_text(encoding="utf-8") == before


def test_prefer_json_refuses_unmodeled_constructs(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    content = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        content.replace("Port 2222", "Port 9999")
        + "\nMatch user root\n  Compression yes\n",
        encoding="utf-8",
    )
    before = output_path.read_text(encoding="utf-8")

    rc = _sync(config_path, output_path, "--prefer", "json")
    assert rc == 2
    assert output_path.read_text(encoding="utf-8") == before

    # --force overrides, with a .bak.
    rc = _sync(config_path, output_path, "--prefer", "json", "--force")
    assert rc == 0
    assert "Match" not in output_path.read_text(encoding="utf-8")
    assert "Match" in (
        output_path.with_name("config.bak").read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# --prefer file
# ---------------------------------------------------------------------------

def test_prefer_file_updates_json_and_preserves_metadata(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    content = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        content.replace("Port 2222", "Port 9999"), encoding="utf-8"
    )
    file_before = output_path.read_text(encoding="utf-8")

    rc = _sync(config_path, output_path, "--prefer", "file")
    assert rc == 0

    data = json.loads(config_path.read_text(encoding="utf-8"))
    db = next(h for h in data["hosts"] if h["alias"] == "db")
    assert db["port"] == 9999
    # JSON-only metadata survives a file-wins resolution.
    assert db["tags"] == ["prod"]
    assert db["user"] == "alice"

    # The file itself is never touched by --prefer file...
    assert output_path.read_text(encoding="utf-8") == file_before
    # ...and a .bak of the previous JSON exists.
    bak = json.loads(
        config_path.with_name("xzssh.json.bak").read_text(encoding="utf-8")
    )
    assert next(h for h in bak["hosts"] if h["alias"] == "db")["port"] == 2222

    assert _sync(config_path, output_path) == 0


def test_prefer_file_imports_hand_added_host(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(
            "\nHost web\n  HostName web.example.com\n  User bob\n"
            "  LocalForward 8080 localhost:80\n"
        )

    rc = _sync(config_path, output_path, "--prefer", "file")
    assert rc == 0

    data = json.loads(config_path.read_text(encoding="utf-8"))
    web = next(h for h in data["hosts"] if h["alias"] == "web")
    assert web["host_name"] == "web.example.com"
    assert web["local_forwards"] == [
        {"local_port": 8080, "remote_host": "localhost", "remote_port": 80}
    ]
    assert _sync(config_path, output_path) == 0


def test_prefer_file_removes_json_only_host(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    main(
        ["add", "--config", str(config_path),
         "--alias", "extra", "--host-name", "extra.example.com"]
    )

    rc = _sync(config_path, output_path, "--prefer", "file")
    assert rc == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert {h["alias"] for h in data["hosts"]} == {"db"}


def test_prefer_file_validates_before_writing(tmp_path: Path) -> None:
    """A hand-edit that breaks invariants aborts with nothing written."""
    config_path = tmp_path / "xzssh.json"
    output_path = tmp_path / "config"
    main(
        ["add", "--config", str(config_path),
         "--alias", "db", "--host-name", "db.example.com",
         "--local-forward", "8080:localhost:80"]
    )
    main(["generate", "--config", str(config_path), "--output", str(output_path)])

    # Hand-add a host whose LocalForward collides with db's.
    with output_path.open("a", encoding="utf-8") as f:
        f.write(
            "\nHost evil\n  HostName evil.example.com\n"
            "  LocalForward 8080 localhost:99\n"
        )
    json_before = config_path.read_text(encoding="utf-8")

    rc = _sync(config_path, output_path, "--prefer", "file")
    assert rc == 1
    assert config_path.read_text(encoding="utf-8") == json_before
    assert not config_path.with_name("xzssh.json.bak").exists()


def test_prefer_file_proceeds_despite_unmodeled_constructs(
    tmp_path: Path,
) -> None:
    """File-wins never touches the file, so Match/Include only warn."""
    config_path, output_path = _setup(tmp_path)
    content = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        content.replace("Port 2222", "Port 9999")
        + "\nMatch user root\n  Compression yes\n",
        encoding="utf-8",
    )

    rc = _sync(config_path, output_path, "--prefer", "file")
    assert rc == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["hosts"][0]["port"] == 9999


# ---------------------------------------------------------------------------
# --interactive
# ---------------------------------------------------------------------------

class _ScriptedSelect:
    def __init__(self, answers):
        self._answers = list(answers)

    def __call__(self, *args, **kwargs):
        answer = self._answers.pop(0)
        return type("Q", (), {"ask": staticmethod(lambda: answer)})()


def test_interactive_mixed_decisions(tmp_path: Path, monkeypatch) -> None:
    """file-wins for the changed host + json-wins for the removed one."""
    config_path, output_path = _setup(tmp_path)
    main(
        ["add", "--config", str(config_path),
         "--alias", "extra", "--host-name", "extra.example.com"]
    )
    content = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        content.replace("Port 2222", "Port 9999"), encoding="utf-8"
    )

    # Drifts are alias-sorted: db (changed) then extra (removed).
    monkeypatch.setattr(
        sync_cmd.questionary, "select", _ScriptedSelect(["file", "json"])
    )

    rc = _sync(config_path, output_path, "--interactive")
    assert rc == 0

    # db took the file's port; extra was restored into the file.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    db = next(h for h in data["hosts"] if h["alias"] == "db")
    assert db["port"] == 9999
    regenerated = output_path.read_text(encoding="utf-8")
    assert "extra.example.com" in regenerated
    assert "Port 9999" in regenerated

    assert _sync(config_path, output_path) == 0


def test_interactive_abort_changes_nothing(tmp_path: Path, monkeypatch) -> None:
    config_path, output_path = _setup(tmp_path)
    content = output_path.read_text(encoding="utf-8")
    output_path.write_text(
        content.replace("Port 2222", "Port 9999"), encoding="utf-8"
    )
    json_before = config_path.read_text(encoding="utf-8")
    file_before = output_path.read_text(encoding="utf-8")

    monkeypatch.setattr(
        sync_cmd.questionary, "select", _ScriptedSelect([None])  # Ctrl-C
    )

    rc = _sync(config_path, output_path, "--interactive")
    assert rc == 1
    assert config_path.read_text(encoding="utf-8") == json_before
    assert output_path.read_text(encoding="utf-8") == file_before


# ---------------------------------------------------------------------------
# usage
# ---------------------------------------------------------------------------

def test_prefer_and_interactive_conflict(tmp_path: Path) -> None:
    config_path, output_path = _setup(tmp_path)
    rc = _sync(config_path, output_path, "--prefer", "json", "--interactive")
    assert rc == 2
