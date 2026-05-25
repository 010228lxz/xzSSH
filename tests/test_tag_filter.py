"""Tests for ``--tag`` filtering on ``xzssh list`` and ``xzssh connect``.

OR semantics are used throughout: a host matches if it has *any* of the
given tags.  Passing no ``--tag`` flag returns all hosts unchanged.
"""
from __future__ import annotations

import types
from pathlib import Path
from typing import List

from xzssh.cli.main import main


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _seed_tagged_hosts(config_path: Path) -> None:
    """Seed four hosts with varying tag sets."""
    specs = [
        ("prod-db",    "db.prod.example.com",     ["prod", "db"]),
        ("prod-web",   "web.prod.example.com",    ["prod", "web"]),
        ("staging-db", "db.staging.example.com",  ["staging", "db"]),
        ("personal",   "pi.local",                []),
    ]
    for alias, hostname, tags in specs:
        cmd = [
            "add", "--config", str(config_path),
            "--alias", alias,
            "--host-name", hostname,
        ]
        for tag in tags:
            cmd.extend(["--tag", tag])
        main(cmd)


# ---------------------------------------------------------------------------
# xzssh list --tag
# ---------------------------------------------------------------------------

def test_list_no_tag_shows_all_hosts(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)

    exit_code = main(["list", "--config", str(config_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    for alias in ("prod-db", "prod-web", "staging-db", "personal"):
        assert alias in out


def test_list_single_tag_shows_only_matching_hosts(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)
    capsys.readouterr()  # discard seed output

    exit_code = main(["list", "--config", str(config_path), "--tag", "prod"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "prod-db" in out
    assert "prod-web" in out
    assert "staging-db" not in out
    assert "personal" not in out


def test_list_multiple_tags_or_semantics(tmp_path: Path, capsys) -> None:
    """--tag prod --tag staging should show the union of both sets."""
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)
    capsys.readouterr()  # discard seed output

    exit_code = main(
        ["list", "--config", str(config_path), "--tag", "prod", "--tag", "staging"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "prod-db" in out
    assert "prod-web" in out
    assert "staging-db" in out
    assert "personal" not in out


def test_list_unknown_tag_exits_zero_with_no_hosts(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)
    capsys.readouterr()  # discard seed output

    exit_code = main(["list", "--config", str(config_path), "--tag", "nonexistent"])

    assert exit_code == 0
    out = capsys.readouterr().out
    for alias in ("prod-db", "prod-web", "staging-db", "personal"):
        assert alias not in out


def test_list_filter_shows_correct_count_message(tmp_path: Path, capsys) -> None:
    """The step message should mention the filter and the counts."""
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)

    main(["list", "--config", str(config_path), "--tag", "db"])

    out = capsys.readouterr().out
    # "2 of 4" (prod-db and staging-db match the "db" tag)
    assert "2" in out
    assert "4" in out
    # The filter tag name should appear in the output
    assert "db" in out


# ---------------------------------------------------------------------------
# xzssh connect --tag (fuzzy-search path)
# ---------------------------------------------------------------------------

def test_connect_tag_restricts_autocomplete_choices(monkeypatch, tmp_path: Path) -> None:
    """When --tag is given without an alias, fuzzy choices are filtered."""
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)

    captured_choices: List[List[str]] = []

    def fake_autocomplete(prompt, choices=(), **kwargs):
        captured_choices.append(list(choices))
        # Return None from .ask() — simulates the user pressing Ctrl-C.
        return types.SimpleNamespace(ask=lambda: None)

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.questionary.autocomplete", fake_autocomplete
    )

    main(["connect", "--config", str(config_path), "--tag", "staging"])

    # autocomplete must have been called once
    assert len(captured_choices) == 1
    shown = captured_choices[0]
    assert "staging-db" in shown
    assert "prod-db" not in shown
    assert "prod-web" not in shown
    assert "personal" not in shown


def test_connect_tag_no_matching_hosts_errors_before_prompt(
    monkeypatch, tmp_path: Path
) -> None:
    """An empty filtered set must error out without reaching questionary."""
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("questionary.autocomplete must not be called")

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.questionary.autocomplete", fail_if_called
    )

    exit_code = main(["connect", "--config", str(config_path), "--tag", "nonexistent"])

    assert exit_code == 1


def test_connect_explicit_alias_ignores_tag_filter(monkeypatch, tmp_path: Path) -> None:
    """An explicit alias connects regardless of whether it carries the filter tag."""
    config_path = tmp_path / "xzssh.json"
    _seed_tagged_hosts(config_path)

    # prod-db has tags ["prod", "db"] — NOT "staging" — but should still connect.
    subprocess_calls: List[List[str]] = []

    def fake_run(args, *a, **kw):
        subprocess_calls.append(list(args))
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("xzssh.cli.commands.connect.subprocess.run", fake_run)

    exit_code = main(
        ["connect", "--config", str(config_path), "--tag", "staging", "prod-db"]
    )

    assert exit_code == 0
    assert len(subprocess_calls) == 1
    assert any("db.prod.example.com" in arg for arg in subprocess_calls[0])
