"""Tests for --dry-run on destructive commands.

Dry-run must be visibly informative and must not touch the filesystem
in any way that would have happened without it.
"""
from __future__ import annotations

import json
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
