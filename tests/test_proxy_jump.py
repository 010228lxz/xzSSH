"""Tests for ProxyJump (bastion host) support.

ProxyJump touches every layer of the pipeline:

- model serialises the field
- json parser accepts it on load
- validator catches dangling and self-referential aliases
- generator emits ``ProxyJump`` in the OpenSSH config
- importer reads ``ProxyJump`` from an existing ssh_config
- ``xzssh add --proxy-jump`` records it
- ``build_ssh_command`` injects ``-J <bastion>`` so ``connect`` /
  ``test`` use the bastion

Each test below pins one of those edges so a future regression points
straight at the layer that broke.
"""
from __future__ import annotations

import json
import types
from pathlib import Path
from typing import List

from xzssh.cli.helpers import build_ssh_command
from xzssh.cli.main import main
from xzssh.generator import render_openssh
from xzssh.model import Config, Host
from xzssh.parser import load_config, parse_openssh_config
from xzssh.validator import validate_config


def _config_from_disk(config_path: Path) -> dict:
    return json.loads(config_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Model + serialisation
# ---------------------------------------------------------------------------

def test_host_serialises_proxy_jump_when_set() -> None:
    host = Host(alias="db", host_name="db.internal", proxy_jump="bastion")
    payload = host.to_dict()
    assert payload["proxy_jump"] == "bastion"


def test_host_omits_proxy_jump_when_none() -> None:
    host = Host(alias="db", host_name="db.example.com")
    payload = host.to_dict()
    assert "proxy_jump" not in payload


# ---------------------------------------------------------------------------
# JSON parser round-trip
# ---------------------------------------------------------------------------

def test_json_parser_roundtrips_proxy_jump(tmp_path: Path) -> None:
    raw = {
        "version": 1,
        "hosts": [
            {"alias": "bastion", "host_name": "bastion.example.com"},
            {
                "alias": "db",
                "host_name": "db.internal",
                "proxy_jump": "bastion",
            },
        ],
        "keys": {},
    }
    path = tmp_path / "xzssh.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)

    db = next(h for h in config.hosts if h.alias == "db")
    assert db.proxy_jump == "bastion"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def test_validator_accepts_existing_proxy_jump_target() -> None:
    config = Config(
        hosts=[
            Host(alias="bastion", host_name="bastion.example.com"),
            Host(alias="db", host_name="db.internal", proxy_jump="bastion"),
        ]
    )
    result = validate_config(config)
    assert not result.errors


def test_validator_rejects_dangling_proxy_jump_alias() -> None:
    config = Config(
        hosts=[
            Host(alias="db", host_name="db.internal", proxy_jump="ghost"),
        ]
    )
    result = validate_config(config)
    assert any("ghost" in e for e in result.errors)


def test_validator_rejects_self_referential_proxy_jump() -> None:
    config = Config(
        hosts=[
            Host(alias="db", host_name="db.internal", proxy_jump="db"),
        ]
    )
    result = validate_config(config)
    assert any("itself" in e for e in result.errors)


def test_validator_allows_forward_reference_to_later_host() -> None:
    """The bastion may be declared after the host that jumps through it."""
    config = Config(
        hosts=[
            Host(alias="db", host_name="db.internal", proxy_jump="bastion"),
            Host(alias="bastion", host_name="bastion.example.com"),
        ]
    )
    result = validate_config(config)
    assert not result.errors


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def test_generator_emits_proxy_jump_line(tmp_path: Path) -> None:
    config = Config(
        hosts=[
            Host(alias="bastion", host_name="bastion.example.com"),
            Host(alias="db", host_name="db.internal", proxy_jump="bastion"),
        ]
    )
    rendered = render_openssh(config, source_path=tmp_path / "x.json")
    assert "ProxyJump bastion" in rendered
    # And bastion itself must not get a ProxyJump line.
    bastion_block = rendered.split("Host bastion")[1].split("Host db")[0]
    assert "ProxyJump" not in bastion_block


# ---------------------------------------------------------------------------
# Importer
# ---------------------------------------------------------------------------

def test_openssh_importer_picks_up_proxy_jump(tmp_path: Path) -> None:
    ssh_config = tmp_path / "config"
    ssh_config.write_text(
        "Host bastion\n  HostName bastion.example.com\n\n"
        "Host db\n  HostName db.internal\n  ProxyJump bastion\n",
        encoding="utf-8",
    )

    hosts, _warnings = parse_openssh_config(ssh_config)
    db = next(h for h in hosts if h.alias == "db")
    assert db.proxy_jump == "bastion"


# ---------------------------------------------------------------------------
# CLI: add --proxy-jump
# ---------------------------------------------------------------------------

def test_add_proxy_jump_flag_persists_to_json(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"

    main(
        [
            "add",
            "--config", str(config_path),
            "--alias", "bastion",
            "--host-name", "bastion.example.com",
        ]
    )
    main(
        [
            "add",
            "--config", str(config_path),
            "--alias", "db",
            "--host-name", "db.internal",
            "--proxy-jump", "bastion",
        ]
    )

    data = _config_from_disk(config_path)
    db = next(h for h in data["hosts"] if h["alias"] == "db")
    assert db["proxy_jump"] == "bastion"


def test_add_proxy_jump_to_unknown_alias_fails_validation(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"

    exit_code = main(
        [
            "add",
            "--config", str(config_path),
            "--alias", "db",
            "--host-name", "db.internal",
            "--proxy-jump", "ghost",
        ]
    )

    # Validation catches the dangling reference before the write.
    assert exit_code == 1


# ---------------------------------------------------------------------------
# ssh argv: -J injection
# ---------------------------------------------------------------------------

def test_build_ssh_command_includes_jump_flag() -> None:
    host = Host(alias="db", host_name="db.internal", proxy_jump="bastion")
    argv = build_ssh_command(host)
    assert "-J" in argv
    j_index = argv.index("-J")
    assert argv[j_index + 1] == "bastion"


def test_build_ssh_command_omits_jump_flag_when_unset() -> None:
    host = Host(alias="db", host_name="db.example.com")
    argv = build_ssh_command(host)
    assert "-J" not in argv


def test_connect_uses_proxy_jump_via_build_ssh_command(
    monkeypatch, tmp_path: Path
) -> None:
    """End-to-end: ``xzssh connect`` should call ssh with ``-J <bastion>``."""
    config_path = tmp_path / "xzssh.json"

    main(
        [
            "add",
            "--config", str(config_path),
            "--alias", "bastion",
            "--host-name", "bastion.example.com",
        ]
    )
    main(
        [
            "add",
            "--config", str(config_path),
            "--alias", "db",
            "--host-name", "db.internal",
            "--proxy-jump", "bastion",
        ]
    )

    calls: List[List[str]] = []

    def fake_run(args, *a, **kw):
        calls.append(list(args))
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("xzssh.cli.commands.connect.subprocess.run", fake_run)

    main(["connect", "--config", str(config_path), "db"])

    assert len(calls) == 1
    argv = calls[0]
    assert "-J" in argv
    assert argv[argv.index("-J") + 1] == "bastion"
