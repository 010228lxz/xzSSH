"""Tests for the extended SSH fields added to Host in v0.9.0.

Covers all five layers for the new fields: model serialisation, JSON
parse, validator constraints, generator emission (incl. bool->yes/no),
OpenSSH importer pickup (yes/no->bool), build_ssh_command -o options,
and the `add` CLI flags.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xzssh.cli.helpers import build_ssh_command
from xzssh.cli.main import main
from xzssh.generator import render_openssh
from xzssh.model import Config, Host, RemoteForward
from xzssh.parser import load_config, parse_openssh_config
from xzssh.validator import validate_config


# ---------------------------------------------------------------------------
# Model serialisation: bools emit only when set; lists always present
# ---------------------------------------------------------------------------

def test_bool_fields_omitted_when_none() -> None:
    payload = Host(alias="db", host_name="db.example.com").to_dict()
    for key in ("forward_agent", "compression", "identities_only",
                "server_alive_interval", "strict_host_key_checking",
                "user_known_hosts_file"):
        assert key not in payload


def test_bool_field_false_is_emitted() -> None:
    """False must survive serialisation — it is distinct from unset (None)."""
    payload = Host(
        alias="db", host_name="db.example.com", compression=False
    ).to_dict()
    assert payload["compression"] is False


def test_forward_lists_always_present() -> None:
    payload = Host(alias="db", host_name="db.example.com").to_dict()
    assert payload["remote_forwards"] == []
    assert payload["dynamic_forwards"] == []


# ---------------------------------------------------------------------------
# JSON parser round-trip
# ---------------------------------------------------------------------------

def test_json_roundtrip_all_fields(tmp_path: Path) -> None:
    raw = {
        "version": 1,
        "hosts": [
            {
                "alias": "db",
                "host_name": "db.internal",
                "forward_agent": True,
                "compression": False,
                "server_alive_interval": 30,
                "identities_only": True,
                "strict_host_key_checking": "accept-new",
                "user_known_hosts_file": "~/.ssh/known_hosts_work",
                "remote_forwards": [
                    {"remote_port": 8080, "local_host": "localhost", "local_port": 80}
                ],
                "dynamic_forwards": [1080, 1081],
            }
        ],
        "keys": {},
    }
    path = tmp_path / "xzssh.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    config = load_config(path)
    db = config.hosts[0]
    assert db.forward_agent is True
    assert db.compression is False
    assert db.server_alive_interval == 30
    assert db.identities_only is True
    assert db.strict_host_key_checking == "accept-new"
    assert db.user_known_hosts_file == "~/.ssh/known_hosts_work"
    assert db.remote_forwards[0].remote_port == 8080
    assert db.remote_forwards[0].local_host == "localhost"
    assert db.remote_forwards[0].local_port == 80
    assert db.dynamic_forwards == [1080, 1081]


def test_json_parser_rejects_non_bool_for_bool_field(tmp_path: Path) -> None:
    raw = {
        "version": 1,
        "hosts": [
            {"alias": "db", "host_name": "db.internal", "compression": "yes"}
        ],
        "keys": {},
    }
    path = tmp_path / "xzssh.json"
    path.write_text(json.dumps(raw), encoding="utf-8")

    from xzssh.parser import ConfigParseError

    with pytest.raises(ConfigParseError):
        load_config(path)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def test_validator_accepts_valid_strict_host_key_checking() -> None:
    for value in ("yes", "no", "ask", "accept-new", "off"):
        config = Config(hosts=[
            Host(alias="db", host_name="db.internal", strict_host_key_checking=value)
        ])
        assert not validate_config(config).errors, value


def test_validator_rejects_bad_strict_host_key_checking() -> None:
    config = Config(hosts=[
        Host(alias="db", host_name="db.internal", strict_host_key_checking="maybe")
    ])
    assert validate_config(config).errors


def test_validator_rejects_negative_server_alive_interval() -> None:
    config = Config(hosts=[
        Host(alias="db", host_name="db.internal", server_alive_interval=-5)
    ])
    assert validate_config(config).errors


def test_validator_rejects_out_of_range_remote_forward_port() -> None:
    config = Config(hosts=[
        Host(
            alias="db", host_name="db.internal",
            remote_forwards=[RemoteForward(remote_port=70000, local_host="x", local_port=80)],
        )
    ])
    assert validate_config(config).errors


def test_validator_rejects_out_of_range_dynamic_forward_port() -> None:
    config = Config(hosts=[
        Host(alias="db", host_name="db.internal", dynamic_forwards=[999999])
    ])
    assert validate_config(config).errors


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def test_generator_emits_bools_as_yes_no(tmp_path: Path) -> None:
    config = Config(hosts=[
        Host(
            alias="db", host_name="db.internal",
            forward_agent=True, compression=False, identities_only=True,
        )
    ])
    out = render_openssh(config, source_path=tmp_path / "x.json")
    assert "ForwardAgent yes" in out
    assert "Compression no" in out
    assert "IdentitiesOnly yes" in out


def test_generator_emits_forwards_and_scalars(tmp_path: Path) -> None:
    config = Config(hosts=[
        Host(
            alias="db", host_name="db.internal",
            server_alive_interval=60,
            strict_host_key_checking="accept-new",
            user_known_hosts_file="~/.ssh/kh",
            remote_forwards=[RemoteForward(remote_port=9000, local_host="127.0.0.1", local_port=9001)],
            dynamic_forwards=[1080],
        )
    ])
    out = render_openssh(config, source_path=tmp_path / "x.json")
    assert "ServerAliveInterval 60" in out
    assert "StrictHostKeyChecking accept-new" in out
    assert "UserKnownHostsFile ~/.ssh/kh" in out
    assert "RemoteForward 9000 127.0.0.1:9001" in out
    assert "DynamicForward 1080" in out


def test_generator_omits_unset_scalars(tmp_path: Path) -> None:
    config = Config(hosts=[Host(alias="db", host_name="db.internal")])
    out = render_openssh(config, source_path=tmp_path / "x.json")
    assert "ForwardAgent" not in out
    assert "Compression" not in out
    assert "ServerAliveInterval" not in out


# ---------------------------------------------------------------------------
# OpenSSH importer
# ---------------------------------------------------------------------------

def test_importer_maps_yes_no_to_bool(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.write_text(
        "Host db\n"
        "  HostName db.internal\n"
        "  ForwardAgent yes\n"
        "  Compression no\n"
        "  ServerAliveInterval 45\n"
        "  StrictHostKeyChecking accept-new\n",
        encoding="utf-8",
    )
    hosts, _ = parse_openssh_config(cfg)
    db = hosts[0]
    assert db.forward_agent is True
    assert db.compression is False
    assert db.server_alive_interval == 45
    assert db.strict_host_key_checking == "accept-new"


def test_importer_picks_up_forwards(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.write_text(
        "Host db\n"
        "  HostName db.internal\n"
        "  LocalForward 5432 db.internal:5432\n"
        "  RemoteForward 8080 localhost:80\n"
        "  DynamicForward 1080\n",
        encoding="utf-8",
    )
    hosts, _ = parse_openssh_config(cfg)
    db = hosts[0]
    assert db.local_forwards[0].local_port == 5432
    assert db.remote_forwards[0].remote_port == 8080
    assert db.remote_forwards[0].local_host == "localhost"
    assert db.remote_forwards[0].local_port == 80
    assert db.dynamic_forwards == [1080]


def test_import_generate_roundtrip_preserves_bools(tmp_path: Path) -> None:
    """generate -> import must preserve yes/no semantics."""
    config = Config(hosts=[
        Host(alias="db", host_name="db.internal", forward_agent=True, compression=False)
    ])
    rendered = render_openssh(config, source_path=tmp_path / "x.json")
    cfg = tmp_path / "config"
    cfg.write_text(rendered, encoding="utf-8")

    hosts, _ = parse_openssh_config(cfg)
    assert hosts[0].forward_agent is True
    assert hosts[0].compression is False


# ---------------------------------------------------------------------------
# build_ssh_command: scalar -o options, NO forwards
# ---------------------------------------------------------------------------

def test_build_ssh_command_includes_scalar_options() -> None:
    host = Host(
        alias="db", host_name="db.internal",
        forward_agent=True, compression=False, server_alive_interval=30,
        identities_only=True, strict_host_key_checking="accept-new",
        user_known_hosts_file="~/.ssh/kh",
    )
    argv = build_ssh_command(host)
    joined = " ".join(argv)
    assert "ForwardAgent=yes" in joined
    assert "Compression=no" in joined
    assert "ServerAliveInterval=30" in joined
    assert "IdentitiesOnly=yes" in joined
    assert "StrictHostKeyChecking=accept-new" in joined
    assert "UserKnownHostsFile=~/.ssh/kh" in joined


def test_build_ssh_command_omits_forwards() -> None:
    """Forwards belong in the generated config, never the connect command."""
    host = Host(
        alias="db", host_name="db.internal",
        remote_forwards=[RemoteForward(remote_port=8080, local_host="localhost", local_port=80)],
        dynamic_forwards=[1080],
    )
    joined = " ".join(build_ssh_command(host))
    assert "RemoteForward" not in joined
    assert "DynamicForward" not in joined
    assert "8080" not in joined
    assert "1080" not in joined


# ---------------------------------------------------------------------------
# add CLI flags
# ---------------------------------------------------------------------------

def _host_dict(config_path: Path, alias: str) -> dict:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return next(h for h in data["hosts"] if h["alias"] == alias)


def test_add_forward_agent_flag(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    main([
        "add", "--config", str(config_path),
        "--alias", "db", "--host-name", "db.internal", "--forward-agent",
    ])
    assert _host_dict(config_path, "db")["forward_agent"] is True


def test_add_no_forward_agent_flag(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    main([
        "add", "--config", str(config_path),
        "--alias", "db", "--host-name", "db.internal", "--no-forward-agent",
    ])
    assert _host_dict(config_path, "db")["forward_agent"] is False


def test_add_scalar_and_forward_flags(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    main([
        "add", "--config", str(config_path),
        "--alias", "db", "--host-name", "db.internal",
        "--server-alive-interval", "30",
        "--strict-host-key-checking", "accept-new",
        "--remote-forward", "8080:localhost:80",
        "--dynamic-forward", "1080",
        "--dynamic-forward", "1081",
    ])
    h = _host_dict(config_path, "db")
    assert h["server_alive_interval"] == 30
    assert h["strict_host_key_checking"] == "accept-new"
    assert h["remote_forwards"] == [
        {"remote_port": 8080, "local_host": "localhost", "local_port": 80}
    ]
    assert h["dynamic_forwards"] == [1080, 1081]


def test_add_rejects_bad_strict_choice(tmp_path: Path) -> None:
    """argparse choices should reject an invalid policy with exit 2."""
    config_path = tmp_path / "xzssh.json"
    with pytest.raises(SystemExit) as exc:
        main([
            "add", "--config", str(config_path),
            "--alias", "db", "--host-name", "db.internal",
            "--strict-host-key-checking", "bogus",
        ])
    assert exc.value.code == 2


def test_add_run_tolerates_namespace_without_new_fields(tmp_path: Path) -> None:
    """The interactive menu paths build argparse.Namespace by hand and don't
    set the v0.9.0 fields. add.run must read them via getattr and not crash."""
    import argparse

    from xzssh.cli.commands import add as add_cmd

    config_path = tmp_path / "xzssh.json"
    # Mirror the menu's minimal Namespace: no remote_forward / forward_agent /
    # dynamic_forward / etc. defined at all.
    ns = argparse.Namespace(
        alias="db",
        host_name="db.internal",
        user=None,
        port=None,
        identity_file=None,
        local_forward=[],
        tag=[],
        replace=False,
        suggest_ports=False,
    )
    rc = add_cmd.run(ns, config_path)
    assert rc == 0
    assert _host_dict(config_path, "db")["host_name"] == "db.internal"
