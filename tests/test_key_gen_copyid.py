"""Tests for `xzssh key gen` (ssh-keygen wrapper) and `xzssh key copy-id`
(ssh-copy-id wrapper), both added in v0.20.0.

subprocess is monkeypatched throughout: the real ssh-keygen/ssh-copy-id
are never invoked, and the fake keygen creates placeholder files so the
register/validate steps see a real key on disk.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import xzssh.cli.commands.key as key_cmd
from xzssh.cli.helpers import build_ssh_copy_id_command, load_config_if_exists
from xzssh.cli.main import main
from xzssh.model import Host


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    return tmp_path / "xzssh.json"


def _fake_keygen(captured: dict):
    """Return a subprocess.run stand-in that 'creates' the keypair."""

    def run(argv, *args, **kwargs):
        captured["argv"] = argv
        key_file = Path(argv[argv.index("-f") + 1])
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_text("PRIVATE\n", encoding="utf-8")
        key_file.chmod(0o600)
        key_file.with_name(key_file.name + ".pub").write_text(
            "PUBLIC\n", encoding="utf-8"
        )
        return SimpleNamespace(returncode=0)

    return run


# ---------------------------------------------------------------------------
# key gen
# ---------------------------------------------------------------------------

def test_gen_creates_and_registers(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))
    key_file = tmp_path / "id_work"

    rc = main(["key", "gen", "work", str(key_file), "--config", str(config_path)])

    assert rc == 0
    assert captured["argv"][:5] == ["ssh-keygen", "-t", "ed25519", "-f", str(key_file)]
    assert key_file.exists()
    config = load_config_if_exists(config_path)
    assert config.keys["work"] == str(key_file)


def test_gen_default_path_uses_ssh_dir(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    fake_ssh_dir = tmp_path / "dotssh"
    monkeypatch.setattr(key_cmd, "ssh_dir", lambda: fake_ssh_dir)
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))

    rc = main(["key", "gen", "work", "--config", str(config_path)])

    assert rc == 0
    assert captured["argv"][argv_index(captured, "-f") + 1] == str(
        fake_ssh_dir / "work"
    )


def test_gen_rsa_defaults_to_4096_bits(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))

    main([
        "key", "gen", "work", str(tmp_path / "k"),
        "--type", "rsa", "--config", str(config_path),
    ])

    argv = captured["argv"]
    assert "-b" in argv and argv[argv.index("-b") + 1] == "4096"


def test_gen_no_passphrase_passes_empty_N(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))

    main([
        "key", "gen", "work", str(tmp_path / "k"),
        "--no-passphrase", "--config", str(config_path),
    ])

    argv = captured["argv"]
    assert argv[argv.index("-N") + 1] == ""


def test_gen_no_register_skips_keys(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))

    rc = main([
        "key", "gen", "work", str(tmp_path / "k"),
        "--no-register", "--config", str(config_path),
    ])

    assert rc == 0
    config = load_config_if_exists(config_path)
    # Nothing registered → config is either absent or has no "work" key.
    assert config is None or "work" not in config.keys


def test_gen_refuses_existing_name(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))
    main(["key", "gen", "work", str(tmp_path / "k1"), "--config", str(config_path)])

    rc = main(["key", "gen", "work", str(tmp_path / "k2"), "--config", str(config_path)])

    assert rc == 1


def test_gen_refuses_existing_file(config_path, tmp_path, monkeypatch):
    existing = tmp_path / "id_work"
    existing.write_text("already here\n", encoding="utf-8")

    def boom(*args, **kwargs):
        raise AssertionError("ssh-keygen must not run when the file exists")

    monkeypatch.setattr(key_cmd.subprocess, "run", boom)

    rc = main(["key", "gen", "work", str(existing), "--config", str(config_path)])

    assert rc == 1


def test_gen_replace_overwrites(config_path, tmp_path, monkeypatch):
    captured: dict = {}
    existing = tmp_path / "id_work"
    existing.write_text("old\n", encoding="utf-8")
    monkeypatch.setattr(key_cmd.subprocess, "run", _fake_keygen(captured))

    rc = main([
        "key", "gen", "work", str(existing),
        "--replace", "--config", str(config_path),
    ])

    assert rc == 0
    assert existing.read_text(encoding="utf-8") == "PRIVATE\n"


def test_gen_keygen_failure_not_registered(config_path, tmp_path, monkeypatch):
    def fail(argv, *args, **kwargs):
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(key_cmd.subprocess, "run", fail)

    rc = main(["key", "gen", "work", str(tmp_path / "k"), "--config", str(config_path)])

    assert rc == 1
    config = load_config_if_exists(config_path)
    assert config is None or "work" not in config.keys


# ---------------------------------------------------------------------------
# key copy-id
# ---------------------------------------------------------------------------

def _make_host_config(config_path, tmp_path, **extra):
    args = ["add", "--alias", "db", "--host-name", "db.example.com"]
    for flag, value in extra.items():
        args.extend([f"--{flag.replace('_', '-')}", str(value)])
    args.extend(["--config", str(config_path)])
    main(args)


def test_copy_id_dry_run_uses_identity_file(config_path, tmp_path, capsys):
    key_file = tmp_path / "id_db"
    key_file.write_text("k\n", encoding="utf-8")
    _make_host_config(
        config_path, tmp_path,
        user="alice", port=2222, identity_file=str(key_file),
    )

    rc = main(["key", "copy-id", "db", "--dry-run", "--config", str(config_path)])

    assert rc == 0
    out = capsys.readouterr().out
    assert "ssh-copy-id" in out
    assert f"-i {key_file}" in out
    assert "-p 2222" in out
    assert "alice@db.example.com" in out


def test_copy_id_with_named_key(config_path, tmp_path, capsys):
    key_file = tmp_path / "id_named"
    key_file.write_text("k\n", encoding="utf-8")
    main(["key", "add", "deploy", str(key_file), "--config", str(config_path)])
    _make_host_config(config_path, tmp_path)

    rc = main([
        "key", "copy-id", "db", "--key", "deploy",
        "--dry-run", "--config", str(config_path),
    ])

    assert rc == 0
    assert f"-i {key_file}" in capsys.readouterr().out


def test_copy_id_runs_ssh_copy_id(config_path, tmp_path, monkeypatch):
    captured: dict = {}

    def fake(argv, *args, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(key_cmd.subprocess, "run", fake)
    _make_host_config(config_path, tmp_path)

    rc = main(["key", "copy-id", "db", "--config", str(config_path)])

    assert rc == 0
    assert captured["argv"][0] == "ssh-copy-id"
    assert captured["argv"][-1] == "db.example.com"


def test_copy_id_unknown_host(config_path, tmp_path):
    _make_host_config(config_path, tmp_path)
    rc = main(["key", "copy-id", "ghost", "--config", str(config_path)])
    assert rc == 1


def test_copy_id_unknown_key(config_path, tmp_path):
    _make_host_config(config_path, tmp_path)
    rc = main([
        "key", "copy-id", "db", "--key", "nope", "--config", str(config_path),
    ])
    assert rc == 1


# ---------------------------------------------------------------------------
# build_ssh_copy_id_command (unit)
# ---------------------------------------------------------------------------

def test_copy_id_command_routes_proxy_jump_via_o():
    host = Host(
        alias="db", host_name="db.internal", user="bob",
        proxy_jump="bastion", compression=True,
    )
    cmd = build_ssh_copy_id_command(host, identity_file="/keys/id")

    assert cmd[0] == "ssh-copy-id"
    assert "-J" not in cmd  # ssh-copy-id has no -J flag
    assert "-o" in cmd
    assert "ProxyJump=bastion" in cmd
    assert "Compression=yes" in cmd
    assert cmd[cmd.index("-i") + 1] == "/keys/id"
    assert cmd[-1] == "bob@db.internal"


def argv_index(captured: dict, flag: str) -> int:
    return captured["argv"].index(flag)
