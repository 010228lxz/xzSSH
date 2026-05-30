"""Tests for ``xzssh search`` — standalone host search.

Case-insensitive substring match across alias, hostname, user, tags,
and proxy_jump. Exit 0 on a hit, 1 on no match (grep-like).
"""
from __future__ import annotations

from pathlib import Path

from xzssh.cli.main import main


def _seed(config_path: Path) -> None:
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "prod-db", "--host-name", "db.prod.example.com",
            "--user", "postgres", "--tag", "production",
        ]
    )
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "staging-web", "--host-name", "web.staging.example.com",
            "--user", "deploy", "--tag", "staging",
        ]
    )


def test_search_matches_alias(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()

    rc = main(["search", "--config", str(config_path), "prod-db"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "prod-db" in out
    assert "staging-web" not in out


def test_search_matches_hostname_substring(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()

    rc = main(["search", "--config", str(config_path), "staging.example"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "staging-web" in out
    assert "prod-db" not in out


def test_search_matches_user(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()

    rc = main(["search", "--config", str(config_path), "postgres"])
    assert rc == 0
    assert "prod-db" in capsys.readouterr().out


def test_search_matches_tag(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()

    rc = main(["search", "--config", str(config_path), "production"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "prod-db" in out
    assert "staging-web" not in out


def test_search_matches_proxy_jump(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "bastion", "--host-name", "jump.corp.example.com",
        ]
    )
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "internal", "--host-name", "10.0.0.5",
            "--proxy-jump", "bastion",
        ]
    )
    capsys.readouterr()

    # Searching for the bastion alias finds the host that jumps through it.
    rc = main(["search", "--config", str(config_path), "bastion"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "internal" in out  # matched via proxy_jump
    assert "bastion" in out   # matched via its own alias


def test_search_is_case_insensitive(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()

    rc = main(["search", "--config", str(config_path), "PROD-DB"])
    assert rc == 0
    assert "prod-db" in capsys.readouterr().out


def test_search_no_match_returns_one(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    capsys.readouterr()

    rc = main(["search", "--config", str(config_path), "nonexistent-xyz"])
    assert rc == 1
    # The "no match" notice goes to stdout (print_info).
    assert "No hosts match" in capsys.readouterr().out


def test_search_missing_config_returns_one(tmp_path: Path) -> None:
    config_path = tmp_path / "absent.json"
    rc = main(["search", "--config", str(config_path), "anything"])
    assert rc == 1
