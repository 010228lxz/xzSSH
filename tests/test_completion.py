"""Tests for shell-completion helpers in ``xzssh.cli.completion``.

We test the completer functions directly rather than driving them
through argcomplete's shim — the library's own integration is well
tested upstream, and our value-add is the dynamic alias / key lookup
plus the graceful no-config / bad-config fallbacks.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from xzssh.cli.completion import (
    _matches,
    alias_completer,
    install_argcomplete,
    key_completer,
)
from xzssh.cli.main import main


def _seed_config(config_path: Path) -> None:
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "prod-db",
            "--host-name", "db.prod.example.com",
        ]
    )
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "prod-web",
            "--host-name", "web.prod.example.com",
        ]
    )
    main(
        [
            "add", "--config", str(config_path),
            "--alias", "staging-db",
            "--host-name", "db.staging.example.com",
        ]
    )


def _seed_keys(config_path: Path, tmp_path: Path) -> None:
    """Add two key entries to the config (the files don't need to exist
    for the completer; it only reads the registry)."""
    # Use `xzssh key add` to populate keys.  The `add` command validates
    # that the file exists, so create real (empty) files.
    key1 = tmp_path / "id_rsa"
    key1.write_text("dummy", encoding="utf-8")
    key2 = tmp_path / "id_ed25519"
    key2.write_text("dummy", encoding="utf-8")
    main(["key", "add", "--config", str(config_path), "prod-key", str(key1)])
    main(["key", "add", "--config", str(config_path), "personal-key", str(key2)])


# ---------------------------------------------------------------------------
# _matches helper
# ---------------------------------------------------------------------------

def test_matches_filters_by_prefix() -> None:
    assert _matches("pro", ["prod-db", "prod-web", "staging-db"]) == [
        "prod-db", "prod-web"
    ]


def test_matches_returns_sorted() -> None:
    assert _matches("", ["z", "a", "m"]) == ["a", "m", "z"]


def test_matches_empty_prefix_returns_all() -> None:
    assert _matches("", ["a", "b"]) == ["a", "b"]


def test_matches_no_hits_returns_empty() -> None:
    assert _matches("xyz", ["a", "b"]) == []


# ---------------------------------------------------------------------------
# alias_completer
# ---------------------------------------------------------------------------

def test_alias_completer_returns_all_aliases_when_prefix_empty(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_config(config_path)

    parsed = types.SimpleNamespace(config=str(config_path))
    assert alias_completer("", parsed) == ["prod-db", "prod-web", "staging-db"]


def test_alias_completer_filters_by_prefix(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_config(config_path)

    parsed = types.SimpleNamespace(config=str(config_path))
    assert alias_completer("prod", parsed) == ["prod-db", "prod-web"]


def test_alias_completer_handles_missing_config(tmp_path: Path) -> None:
    """A missing config file must return [] rather than raise."""
    config_path = tmp_path / "does-not-exist.json"
    parsed = types.SimpleNamespace(config=str(config_path))
    assert alias_completer("", parsed) == []


def test_alias_completer_handles_corrupt_config(tmp_path: Path) -> None:
    """A bad JSON file must return [] rather than crash the shell."""
    config_path = tmp_path / "xzssh.json"
    config_path.write_text("{not valid json}", encoding="utf-8")

    parsed = types.SimpleNamespace(config=str(config_path))
    assert alias_completer("", parsed) == []


def test_alias_completer_handles_missing_config_attr() -> None:
    """When --config isn't in parsed_args at all, fall back to platform default.

    The platform default may or may not exist on the test machine; either
    way we must return a list (possibly empty), never raise.
    """
    parsed = types.SimpleNamespace()
    result = alias_completer("", parsed)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# key_completer
# ---------------------------------------------------------------------------

def test_key_completer_returns_configured_key_names(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_keys(config_path, tmp_path)

    parsed = types.SimpleNamespace(config=str(config_path))
    names = key_completer("", parsed)
    assert set(names) == {"prod-key", "personal-key"}


def test_key_completer_filters_by_prefix(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_keys(config_path, tmp_path)

    parsed = types.SimpleNamespace(config=str(config_path))
    assert key_completer("prod", parsed) == ["prod-key"]


# ---------------------------------------------------------------------------
# install_argcomplete
# ---------------------------------------------------------------------------

def test_install_argcomplete_no_ops_when_lib_absent(monkeypatch) -> None:
    """If argcomplete isn't importable the hook must silently no-op,
    not blow up the parser construction path."""
    # Block the import by removing it from sys.modules and installing a
    # finder that raises ImportError.
    import sys

    monkeypatch.setitem(sys.modules, "argcomplete", None)
    # Calling install_argcomplete must not raise.
    install_argcomplete(parser=None)


def test_install_argcomplete_calls_autocomplete_when_available(
    monkeypatch,
) -> None:
    """When argcomplete is importable we must hand it the parser."""
    calls = []

    fake_argcomplete = types.SimpleNamespace(
        autocomplete=lambda parser: calls.append(parser)
    )
    import sys

    monkeypatch.setitem(sys.modules, "argcomplete", fake_argcomplete)

    sentinel_parser = object()
    install_argcomplete(sentinel_parser)
    assert calls == [sentinel_parser]
