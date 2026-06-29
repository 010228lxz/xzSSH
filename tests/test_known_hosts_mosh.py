"""Tests for v0.23.0 ssh-tooling wrappers:
`xzssh known-hosts remove <alias>` and `xzssh mosh <alias>`.

subprocess is monkeypatched throughout — real ssh-keygen / mosh are
never invoked.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import xzssh.cli.commands.known_hosts as kh_cmd
import xzssh.cli.commands.mosh as mosh_cmd
from xzssh.cli.main import main


def _add_host(cfg: Path, alias: str, **flags) -> None:
    args = ["add", "--alias", alias, "--host-name", f"{alias}.example.com"]
    for k, v in flags.items():
        args += ["--" + k.replace("_", "-"), str(v)]
    args += ["--config", str(cfg)]
    assert main(args) == 0


# ---------------------------------------------------------------------------
# known-hosts remove
# ---------------------------------------------------------------------------

def test_known_hosts_remove_default_port(tmp_path, monkeypatch):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    captured = {}

    def fake(argv, **kw):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(kh_cmd.subprocess, "run", fake)
    rc = main(["known-hosts", "remove", "web", "--config", str(cfg)])
    assert rc == 0
    assert captured["argv"] == ["ssh-keygen", "-R", "web.example.com"]


def test_known_hosts_remove_nondefault_port_is_bracketed(tmp_path, monkeypatch):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web", port=2222)
    captured = {}
    monkeypatch.setattr(
        kh_cmd.subprocess, "run",
        lambda argv, **kw: captured.update(argv=argv)
        or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    main(["known-hosts", "remove", "web", "--config", str(cfg)])
    assert captured["argv"] == ["ssh-keygen", "-R", "[web.example.com]:2222"]


def test_known_hosts_remove_honors_known_hosts_file(tmp_path, monkeypatch):
    cfg = tmp_path / "x.json"
    khfile = tmp_path / "kh"
    _add_host(cfg, "web", user_known_hosts_file=str(khfile))
    captured = {}
    monkeypatch.setattr(
        kh_cmd.subprocess, "run",
        lambda argv, **kw: captured.update(argv=argv)
        or SimpleNamespace(returncode=0, stdout="", stderr=""),
    )
    main(["known-hosts", "remove", "web", "--config", str(cfg)])
    assert "-f" in captured["argv"]
    assert str(khfile) in captured["argv"]


def test_known_hosts_remove_dry_run(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web", port=2222)

    def boom(*a, **k):
        raise AssertionError("ssh-keygen must not run on --dry-run")

    monkeypatch.setattr(kh_cmd.subprocess, "run", boom)
    rc = main(["known-hosts", "remove", "web", "--dry-run", "--config", str(cfg)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "ssh-keygen -R '[web.example.com]:2222'" in out or \
        "ssh-keygen -R [web.example.com]:2222" in out


def test_known_hosts_remove_unknown_host(tmp_path):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    assert main(["known-hosts", "remove", "ghost", "--config", str(cfg)]) == 1


# ---------------------------------------------------------------------------
# mosh
# ---------------------------------------------------------------------------

def test_mosh_builds_command_with_ssh_options(tmp_path, monkeypatch):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "db", user="alice", port=2222)
    captured = {}
    monkeypatch.setattr(
        mosh_cmd.subprocess, "run",
        lambda argv, **kw: captured.update(argv=argv)
        or SimpleNamespace(returncode=0),
    )
    rc = main(["mosh", "db", "--config", str(cfg)])
    assert rc == 0
    argv = captured["argv"]
    assert argv[0] == "mosh"
    assert argv[-1] == "alice@db.example.com"
    # port/identity flow through the --ssh bootstrap option
    assert any(a.startswith("--ssh=") and "-p 2222" in a for a in argv)


def test_mosh_no_options_omits_ssh_flag(tmp_path, monkeypatch):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "db")  # no user/port/identity
    captured = {}
    monkeypatch.setattr(
        mosh_cmd.subprocess, "run",
        lambda argv, **kw: captured.update(argv=argv)
        or SimpleNamespace(returncode=0),
    )
    main(["mosh", "db", "--config", str(cfg)])
    argv = captured["argv"]
    assert argv == ["mosh", "db.example.com"]


def test_mosh_dry_run(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "db", port=2222)

    def boom(*a, **k):
        raise AssertionError("mosh must not run on --dry-run")

    monkeypatch.setattr(mosh_cmd.subprocess, "run", boom)
    rc = main(["mosh", "db", "--dry-run", "--config", str(cfg)])
    assert rc == 0
    assert "mosh" in capsys.readouterr().out


def test_mosh_unknown_host(tmp_path):
    cfg = tmp_path / "x.json"
    _add_host(cfg, "db")
    assert main(["mosh", "ghost", "--config", str(cfg)]) == 1
