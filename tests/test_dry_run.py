"""Tests for --dry-run on destructive commands.

Dry-run must be visibly informative and must not touch the filesystem
in any way that would have happened without it.
"""
from __future__ import annotations

import argparse
import json
import types
from pathlib import Path

from xzssh.cli.main import main


def _seed_two_hosts(config_path: Path) -> None:
    main(
        [
            "add",
            "--config",
            str(config_path),
            "--alias",
            "db",
            "--host-name",
            "db.example.com",
        ]
    )
    main(
        [
            "add",
            "--config",
            str(config_path),
            "--alias",
            "web",
            "--host-name",
            "web.example.com",
        ]
    )


def test_generate_dry_run_does_not_write_output(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    output_path = tmp_path / "ssh_config"
    _seed_two_hosts(config_path)

    exit_code = main(
        [
            "generate",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert not output_path.exists()

    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "Host db" in captured.out
    assert "Host web" in captured.out


def test_generate_dry_run_preserves_existing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    output_path = tmp_path / "ssh_config"
    _seed_two_hosts(config_path)

    user_content = "# my hand-rolled config\nHost user-host\n  HostName 10.0.0.1\n"
    output_path.write_text(user_content, encoding="utf-8")

    # Without --dry-run this would fail with "refusing to overwrite";
    # --dry-run should bypass the write entirely.
    exit_code = main(
        [
            "generate",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert output_path.read_text(encoding="utf-8") == user_content
    assert not output_path.with_name(output_path.name + ".bak").exists()


def test_remove_dry_run_keeps_config_intact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)
    before = config_path.read_text(encoding="utf-8")

    exit_code = main(
        ["remove", "--config", str(config_path), "--dry-run", "db"]
    )

    assert exit_code == 0
    assert config_path.read_text(encoding="utf-8") == before

    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    assert "db" in captured.out


def test_remove_all_dry_run_keeps_config_intact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)
    before = config_path.read_text(encoding="utf-8")

    exit_code = main(
        ["remove", "--config", str(config_path), "--all", "--dry-run"]
    )

    assert exit_code == 0
    assert config_path.read_text(encoding="utf-8") == before

    captured = capsys.readouterr()
    assert "--dry-run" in captured.out
    # Both hosts should be mentioned in the preview
    assert "db" in captured.out
    assert "web" in captured.out


def test_remove_dry_run_unknown_alias_still_errors(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)

    exit_code = main(
        ["remove", "--config", str(config_path), "--dry-run", "ghost"]
    )

    # An unknown alias is an error regardless of dry-run.
    assert exit_code == 1

    # Config still has both original hosts.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert {h["alias"] for h in data["hosts"]} == {"db", "web"}


# -----------------------------------------------------------------------------
# connect --dry-run
# -----------------------------------------------------------------------------


def test_connect_dry_run_does_not_invoke_ssh(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)

    def fail(*a, **k):
        raise AssertionError("ssh must not run under --dry-run")

    monkeypatch.setattr("xzssh.cli.commands.connect.subprocess.run", fail)

    exit_code = main(["connect", "--config", str(config_path), "--dry-run", "db"])
    assert exit_code == 0


def test_connect_dry_run_does_not_stamp_last_used(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)
    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no ssh")),
    )

    main(["connect", "--config", str(config_path), "--dry-run", "db"])

    data = json.loads(config_path.read_text(encoding="utf-8"))
    db = next(h for h in data["hosts"] if h["alias"] == "db")
    assert "last_used" not in db


def test_connect_dry_run_prints_resolved_command(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "xzssh.json"
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "db", "--host-name", "db.internal",
            "--user", "alice", "--port", "2222",
        ]
    )
    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no ssh")),
    )
    capsys.readouterr()

    main(["connect", "--config", str(config_path), "--dry-run", "db"])
    out = capsys.readouterr().out
    assert "ssh -p 2222 alice@db.internal" in out


def test_connect_run_without_dry_run_attr_still_connects(
    monkeypatch, tmp_path: Path
) -> None:
    """The interactive menus call connect.run with a Namespace that has no
    dry_run attribute — getattr must default it to False and connect."""
    from xzssh.cli.commands import connect as connect_cmd

    config_path = tmp_path / "xzssh.json"
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "db", "--host-name", "db.internal",
        ]
    )

    calls = []
    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run",
        lambda argv, *a, **k: calls.append(argv) or types.SimpleNamespace(returncode=0),
    )

    # Namespace mirrors the menu: alias only, no dry_run / tag attributes.
    rc = connect_cmd.run(
        argparse.Namespace(alias="db"), config_path, suggest_ports=False
    )
    assert rc == 0
    assert len(calls) == 1  # ssh actually ran
