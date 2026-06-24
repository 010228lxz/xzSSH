"""Tests for the free-form ``options`` passthrough on Host (v0.21.0).

A Host can carry arbitrary ssh_config directives that xzSSH doesn't model
as first-class fields. They round-trip through JSON, render verbatim in
the generated config, and are injected into the interactive ssh command.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from xzssh.cli.helpers import build_ssh_command, parse_option_arg
from xzssh.cli.main import main
from xzssh.generator import render_openssh
from xzssh.model import Config, Host
from xzssh.parser import load_config
from xzssh.parser.json_parser import ConfigParseError
from xzssh.validator import validate_config


# ---------------------------------------------------------------------------
# model / parser round-trip
# ---------------------------------------------------------------------------

def test_to_dict_includes_options() -> None:
    host = Host(alias="db", host_name="db", options={"ControlMaster": "auto"})
    data = host.to_dict()
    assert data["options"] == {"ControlMaster": "auto"}


def test_options_round_trip_through_json(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    config = Config(
        hosts=[
            Host(
                alias="db",
                host_name="db.example.com",
                options={"ControlMaster": "auto", "SetEnv": "FOO=bar"},
            )
        ]
    )
    cfg.write_text(json.dumps(config.to_dict()), encoding="utf-8")

    loaded = load_config(cfg)
    assert loaded.hosts[0].options == {"ControlMaster": "auto", "SetEnv": "FOO=bar"}


def test_options_default_empty_when_absent(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    cfg.write_text(
        json.dumps({"version": 1, "hosts": [{"alias": "a", "host_name": "h"}], "keys": {}}),
        encoding="utf-8",
    )
    loaded = load_config(cfg)
    assert loaded.hosts[0].options == {}


def test_options_must_be_object(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": [{"alias": "a", "host_name": "h", "options": ["nope"]}],
                "keys": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigParseError):
        load_config(cfg)


def test_options_value_coerced_to_string(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": [
                    {"alias": "a", "host_name": "h", "options": {"ConnectTimeout": 10}}
                ],
                "keys": {},
            }
        ),
        encoding="utf-8",
    )
    loaded = load_config(cfg)
    assert loaded.hosts[0].options == {"ConnectTimeout": "10"}


def test_options_null_value_rejected(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    cfg.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": [{"alias": "a", "host_name": "h", "options": {"X": None}}],
                "keys": {},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigParseError):
        load_config(cfg)


# ---------------------------------------------------------------------------
# generator
# ---------------------------------------------------------------------------

def test_generator_renders_options_verbatim(tmp_path: Path) -> None:
    config = Config(
        hosts=[
            Host(
                alias="db",
                host_name="db.example.com",
                options={"ControlMaster": "auto", "RemoteCommand": "tmux attach"},
            )
        ]
    )
    out = render_openssh(config, tmp_path / "x.json")
    assert "  ControlMaster auto" in out
    assert "  RemoteCommand tmux attach" in out


def test_generator_renders_options_after_typed_fields(tmp_path: Path) -> None:
    # The typed field must come first so ssh (first-match wins) keeps it.
    config = Config(
        hosts=[
            Host(
                alias="db",
                host_name="db.example.com",
                port=2222,
                options={"Port": "9999"},
            )
        ]
    )
    out = render_openssh(config, tmp_path / "x.json")
    assert out.index("  Port 2222") < out.index("  Port 9999")


# ---------------------------------------------------------------------------
# build_ssh_command
# ---------------------------------------------------------------------------

def test_build_ssh_command_injects_options() -> None:
    host = Host(
        alias="db",
        host_name="db.example.com",
        options={"ControlMaster": "auto"},
    )
    argv = build_ssh_command(host)
    assert "-o" in argv
    assert "ControlMaster=auto" in argv


def test_build_ssh_command_scalar_precedes_option_duplicate() -> None:
    host = Host(
        alias="db",
        host_name="db.example.com",
        compression=True,
        options={"Compression": "no"},
    )
    argv = build_ssh_command(host)
    # The managed scalar must be injected before the duplicate option so
    # ssh's first-match wins keeps Compression=yes.
    assert argv.index("Compression=yes") < argv.index("Compression=no")


# ---------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------

def test_validator_warns_on_managed_directive_collision() -> None:
    config = Config(
        hosts=[Host(alias="db", host_name="db", options={"Port": "22"})]
    )
    result = validate_config(config)
    assert not result.errors
    assert any("duplicates a directive" in w for w in result.warnings)


def test_validator_case_insensitive_collision() -> None:
    config = Config(
        hosts=[Host(alias="db", host_name="db", options={"compression": "yes"})]
    )
    result = validate_config(config)
    assert any("duplicates a directive" in w for w in result.warnings)


def test_validator_allows_unmanaged_option() -> None:
    config = Config(
        hosts=[Host(alias="db", host_name="db", options={"ControlMaster": "auto"})]
    )
    result = validate_config(config)
    assert not result.errors
    assert not any("duplicates a directive" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# parse_option_arg
# ---------------------------------------------------------------------------

def test_parse_option_arg_basic() -> None:
    assert parse_option_arg("ControlMaster=auto") == ("ControlMaster", "auto")


def test_parse_option_arg_value_with_equals() -> None:
    # SetEnv values legitimately contain '=' — only the first splits.
    assert parse_option_arg("SetEnv=FOO=bar") == ("SetEnv", "FOO=bar")


def test_parse_option_arg_missing_equals() -> None:
    with pytest.raises(ValueError):
        parse_option_arg("ControlMaster")


def test_parse_option_arg_empty_key() -> None:
    with pytest.raises(ValueError):
        parse_option_arg("=auto")


# ---------------------------------------------------------------------------
# add CLI
# ---------------------------------------------------------------------------

def test_add_with_option_flag(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    rc = main([
        "add", "--alias", "db", "--host-name", "db.example.com",
        "--option", "ControlMaster=auto",
        "--option", "SetEnv=FOO=bar",
        "--config", str(cfg),
    ])
    assert rc == 0
    loaded = load_config(cfg)
    assert loaded.hosts[0].options == {"ControlMaster": "auto", "SetEnv": "FOO=bar"}


def test_add_with_malformed_option_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    rc = main([
        "add", "--alias", "db", "--host-name", "h",
        "--option", "NoEqualsHere",
        "--config", str(cfg),
    ])
    assert rc == 2
    assert not cfg.exists()
