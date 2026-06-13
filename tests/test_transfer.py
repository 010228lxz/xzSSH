"""Tests for the scp/sftp/rsync alias-aware wrappers."""
from __future__ import annotations

import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

import xzssh.cli.commands.transfer as transfer_cmd
from xzssh.cli.main import main


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "xzssh.json"
    # bastion first — db's --proxy-jump must reference an existing alias.
    main(
        ["add", "--config", str(path),
         "--alias", "bastion", "--host-name", "bastion.example.com"]
    )
    main(
        ["add", "--config", str(path),
         "--alias", "db", "--host-name", "db.example.com",
         "--user", "alice", "--port", "2222",
         "--identity-file", "~/.ssh/id_db",
         "--proxy-jump", "bastion", "--compression"]
    )
    return path


@pytest.fixture
def spawn(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(transfer_cmd.subprocess, "run", fake_run)
    return captured


# ---------------------------------------------------------------------------
# scp
# ---------------------------------------------------------------------------

def test_scp_rewrites_alias_and_injects_options(config_path, spawn) -> None:
    # Tool args that start with '-' need the standard `--` separator.
    rc = main(["scp", "--config", str(config_path), "--", "-r", "db:/var/log", "."])
    assert rc == 0
    argv = spawn["argv"]

    assert argv[0] == "scp"
    # scp spells the port flag -P.
    assert argv[argv.index("-P") + 1] == "2222"
    assert "-p" not in argv[: argv.index("-r")]
    assert argv[argv.index("-i") + 1] == "~/.ssh/id_db"
    assert argv[argv.index("-J") + 1] == "bastion"
    assert "Compression=yes" in argv
    # Target rewritten, scp's own -r and the local path untouched.
    assert argv[-3:] == ["-r", "alice@db.example.com:/var/log", "."]


def test_scp_leaves_non_alias_tokens_alone(config_path, spawn) -> None:
    main(["scp", "--config", str(config_path),
          "notanalias:/x", "C:\\local\\file", "db:/y"])
    argv = spawn["argv"]
    assert "notanalias:/x" in argv
    assert "C:\\local\\file" in argv
    assert "alice@db.example.com:/y" in argv


def test_scp_exit_code_propagates(config_path, monkeypatch) -> None:
    monkeypatch.setattr(
        transfer_cmd.subprocess,
        "run",
        lambda argv, **kw: SimpleNamespace(returncode=23),
    )
    assert main(["scp", "--config", str(config_path), "db:/x", "."]) == 23


def test_scp_no_port_no_flag(tmp_path: Path, spawn) -> None:
    path = tmp_path / "xzssh.json"
    main(["add", "--config", str(path), "--alias", "p", "--host-name", "plain.example.com"])
    main(["scp", "--config", str(path), "p:/x", "."])
    assert "-P" not in spawn["argv"]


def test_multiple_aliases_skip_option_injection(config_path, spawn, capsys) -> None:
    """Remote→remote between two hosts: flags would be ambiguous."""
    main(["scp", "--config", str(config_path), "db:/x", "bastion:/y"])
    argv = spawn["argv"]
    assert "-P" not in argv and "-i" not in argv
    assert "alice@db.example.com:/x" in argv
    assert "bastion.example.com:/y" in argv
    assert "Multiple aliases" in capsys.readouterr().err


def test_missing_binary_is_127(config_path, monkeypatch) -> None:
    def raise_fnf(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(transfer_cmd.subprocess, "run", raise_fnf)
    assert main(["scp", "--config", str(config_path), "db:/x", "."]) == 127


def test_dry_run_prints_without_running(config_path, monkeypatch, capsys) -> None:
    def boom(argv, **kw):  # pragma: no cover - must not be reached
        raise AssertionError("dry-run must not spawn the tool")

    monkeypatch.setattr(transfer_cmd.subprocess, "run", boom)
    rc = main(["scp", "--dry-run", "--config", str(config_path), "db:/x", "."])
    assert rc == 0
    out = capsys.readouterr().out
    argv = shlex.split(out.strip())
    assert argv[0] == "scp"
    assert "alice@db.example.com:/x" in argv


def test_no_alias_passthrough_still_runs(config_path, spawn, capsys) -> None:
    rc = main(["scp", "--config", str(config_path), "local1", "local2"])
    assert rc == 0
    assert spawn["argv"] == ["scp", "local1", "local2"]
    assert "No configured alias" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# sftp
# ---------------------------------------------------------------------------

def test_sftp_rewrites_bare_alias(config_path, spawn) -> None:
    main(["sftp", "--config", str(config_path), "db"])
    argv = spawn["argv"]
    assert argv[0] == "sftp"
    assert argv[-1] == "alice@db.example.com"
    assert argv[argv.index("-P") + 1] == "2222"


def test_sftp_rewrites_alias_with_path(config_path, spawn) -> None:
    main(["sftp", "--config", str(config_path), "db:/srv"])
    assert spawn["argv"][-1] == "alice@db.example.com:/srv"


# ---------------------------------------------------------------------------
# rsync
# ---------------------------------------------------------------------------

def test_rsync_uses_e_ssh_options(config_path, spawn) -> None:
    main(["rsync", "--config", str(config_path), "--", "-az", "db:/data/", "backup/"])
    argv = spawn["argv"]
    assert argv[0] == "rsync"
    assert "-P" not in argv  # -P means something else entirely to rsync
    e_value = argv[argv.index("-e") + 1]
    ssh_argv = shlex.split(e_value)
    assert ssh_argv[0] == "ssh"
    assert ssh_argv[ssh_argv.index("-p") + 1] == "2222"
    assert ssh_argv[ssh_argv.index("-i") + 1] == "~/.ssh/id_db"
    assert "alice@db.example.com:/data/" in argv
    assert argv[-2:] == ["alice@db.example.com:/data/", "backup/"]


def test_rsync_without_options_has_no_e(tmp_path: Path, spawn) -> None:
    path = tmp_path / "xzssh.json"
    main(["add", "--config", str(path), "--alias", "p", "--host-name", "plain.example.com"])
    main(["rsync", "--config", str(path), "p:/x", "."])
    assert "-e" not in spawn["argv"]


# ---------------------------------------------------------------------------
# quiet stdout
# ---------------------------------------------------------------------------

def test_wrappers_do_not_print_banner(config_path, spawn, capsys) -> None:
    main(["scp", "--config", str(config_path), "db:/x", "."])
    assert "xzSSH" not in capsys.readouterr().out  # no banner on stdout
