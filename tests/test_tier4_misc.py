"""Tests for the v0.19.0 odds and ends: --match-all tag filtering (the
roadmap's tags-instead-of-folders resolution) and `key add-agent
--keychain` (macOS Keychain integration).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import xzssh.cli.commands.key as key_cmd
from xzssh.cli.helpers import filter_hosts_by_tags
from xzssh.cli.main import main
from xzssh.model import Host
from xzssh.platform import Platform


# ---------------------------------------------------------------------------
# --match-all
# ---------------------------------------------------------------------------

def _hosts():
    return [
        Host(alias="prod-db", host_name="a", tags=["prod", "db"]),
        Host(alias="prod-web", host_name="b", tags=["prod", "web"]),
        Host(alias="dev-db", host_name="c", tags=["dev", "db"]),
    ]


def test_or_semantics_unchanged() -> None:
    matched = filter_hosts_by_tags(_hosts(), ["prod", "db"])
    assert {h.alias for h in matched} == {"prod-db", "prod-web", "dev-db"}


def test_match_all_requires_every_tag() -> None:
    matched = filter_hosts_by_tags(_hosts(), ["prod", "db"], match_all=True)
    assert {h.alias for h in matched} == {"prod-db"}


def test_match_all_with_empty_tags_returns_everything() -> None:
    hosts = _hosts()
    assert filter_hosts_by_tags(hosts, [], match_all=True) == hosts


def test_list_match_all_end_to_end(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    main(["add", "--config", str(config_path), "--alias", "prod-db",
          "--host-name", "a.example.com", "--tag", "prod", "--tag", "db"])
    main(["add", "--config", str(config_path), "--alias", "prod-web",
          "--host-name", "b.example.com", "--tag", "prod", "--tag", "web"])
    capsys.readouterr()

    rc = main(["list", "--config", str(config_path),
               "--tag", "prod", "--tag", "db", "--match-all"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "prod-db" in out
    assert "prod-web" not in out

    # Without --match-all the same tags are OR — both hosts show.
    rc = main(["list", "--config", str(config_path),
               "--tag", "prod", "--tag", "db"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "prod-db" in out and "prod-web" in out


# ---------------------------------------------------------------------------
# key add-agent --keychain
# ---------------------------------------------------------------------------

@pytest.fixture
def keyed_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "xzssh.json"
    key_file = tmp_path / "id_test"
    key_file.write_text("fake key\n", encoding="utf-8")
    key_file.chmod(0o600)
    main(["add", "--config", str(config_path),
          "--alias", "db", "--host-name", "db.example.com"])
    main(["key", "add", "work", str(key_file), "--config", str(config_path)])
    return config_path


def test_keychain_flag_on_macos(keyed_config, monkeypatch) -> None:
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(key_cmd.subprocess, "run", fake_run)
    monkeypatch.setattr(key_cmd, "detect_platform", lambda: Platform.MACOS)

    rc = main(["key", "add-agent", "work", "--keychain",
               "--config", str(keyed_config)])
    assert rc == 0
    assert captured["argv"][0] == "ssh-add"
    assert "--apple-use-keychain" in captured["argv"]


def test_keychain_flag_rejected_off_macos(keyed_config, monkeypatch) -> None:
    def boom(argv, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("ssh-add must not run when --keychain is invalid")

    monkeypatch.setattr(key_cmd.subprocess, "run", boom)
    monkeypatch.setattr(key_cmd, "detect_platform", lambda: Platform.OTHER)

    rc = main(["key", "add-agent", "work", "--keychain",
               "--config", str(keyed_config)])
    assert rc == 2


def test_add_agent_without_keychain_unchanged(keyed_config, monkeypatch) -> None:
    captured = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(key_cmd.subprocess, "run", fake_run)

    rc = main(["key", "add-agent", "work", "--config", str(keyed_config)])
    assert rc == 0
    assert "--apple-use-keychain" not in captured["argv"]
