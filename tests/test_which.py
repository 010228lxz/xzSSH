"""Tests for ``xzssh which`` — print the resolved ssh command, don't run it.

The output must be a single copy-pasteable command line with no banner
or decoration, so it can be captured by ``$(xzssh which db)``.
"""
from __future__ import annotations

import json
from pathlib import Path

from xzssh.cli.main import main


def _seed(config_path: Path, *extra: str) -> None:
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "db",
            "--host-name", "db.example.com",
            *extra,
        ]
    )


def test_which_prints_plain_ssh_command(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "--user", "alice", "--port", "2222")
    capsys.readouterr()  # drop seed/banner output

    exit_code = main(["which", "--config", str(config_path), "db"])

    assert exit_code == 0
    out = capsys.readouterr().out.strip()
    # The whole thing is a single line — no banner box-drawing characters.
    assert "╭" not in out  # ╭ banner corner
    assert out.startswith("ssh ")
    assert "-p 2222" in out
    assert "alice@db.example.com" in out


def test_which_includes_identity_and_proxy_jump(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    # bastion must exist for proxy_jump validation to pass.
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "bastion", "--host-name", "bastion.example.com",
        ]
    )
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "db", "--host-name", "db.internal",
            "--identity-file", "/home/me/.ssh/id_ed25519",
            "--proxy-jump", "bastion",
        ]
    )
    capsys.readouterr()

    main(["which", "--config", str(config_path), "db"])

    out = capsys.readouterr().out.strip()
    assert "-i /home/me/.ssh/id_ed25519" in out
    assert "-J bastion" in out
    assert out.endswith("db.internal")


def test_which_unknown_alias_errors(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)

    exit_code = main(["which", "--config", str(config_path), "ghost"])
    assert exit_code == 1


def test_which_does_not_modify_config(tmp_path: Path) -> None:
    """`which` is read-only — it must not stamp last_used or touch the file."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    before = config_path.read_text(encoding="utf-8")

    main(["which", "--config", str(config_path), "db"])

    assert config_path.read_text(encoding="utf-8") == before
    data = json.loads(before)
    db = next(h for h in data["hosts"] if h["alias"] == "db")
    assert "last_used" not in db


def test_which_output_is_shell_safe(tmp_path: Path, capsys) -> None:
    """A hostname/identity with a space must be quoted so the line is paste-safe."""
    config_path = tmp_path / "xzssh.json"
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "weird", "--host-name", "db.example.com",
            "--identity-file", "/home/me/my key",  # space in path
        ]
    )
    capsys.readouterr()

    main(["which", "--config", str(config_path), "weird"])
    out = capsys.readouterr().out.strip()
    # shlex.join must quote the spaced path so it survives a shell paste.
    assert "'/home/me/my key'" in out or '"/home/me/my key"' in out
