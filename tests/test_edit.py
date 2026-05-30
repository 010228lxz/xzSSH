"""Tests for ``xzssh edit`` — edit a host's JSON in $EDITOR.

We never launch a real editor: ``subprocess.run`` is monkeypatched with
a fake that rewrites the temp file (the last argv element) to simulate
the user's edit, then returns. This lets us drive every branch — valid
edit, rename, bad JSON, validation failure — deterministically.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from xzssh.cli.main import main


def _seed(config_path: Path, alias: str = "db", host: str = "db.example.com", *extra: str) -> None:
    main(
        [
            "add", "--config", str(config_path),
            "--alias", alias, "--host-name", host, *extra,
        ]
    )


def _fake_editor(monkeypatch, new_dict) -> None:
    """Patch the editor so it overwrites the temp file with *new_dict*.

    Passing ``None`` leaves the file untouched (simulates "saved without
    changes"); passing a raw string writes it verbatim (for bad-JSON cases).
    """
    monkeypatch.setenv("EDITOR", "fake-editor")

    def fake_run(argv, *a, **kw):
        tmp = Path(argv[-1])
        if new_dict is None:
            pass  # no change
        elif isinstance(new_dict, str):
            tmp.write_text(new_dict, encoding="utf-8")
        else:
            tmp.write_text(json.dumps(new_dict, indent=2), encoding="utf-8")
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("xzssh.cli.commands.edit.subprocess.run", fake_run)


def _hosts(config_path: Path):
    return json.loads(config_path.read_text(encoding="utf-8"))["hosts"]


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------

def test_edit_applies_field_change(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com", "--user", "alice")

    _fake_editor(
        monkeypatch,
        {"alias": "db", "host_name": "db.example.com", "user": "bob",
         "local_forwards": [], "tags": []},
    )

    rc = main(["edit", "--config", str(config_path), "db"])
    assert rc == 0

    db = next(h for h in _hosts(config_path) if h["alias"] == "db")
    assert db["user"] == "bob"


def test_edit_rename_alias_splices_by_position(monkeypatch, tmp_path: Path) -> None:
    """Changing the alias in the editor must rename the host, not orphan it."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "old-name", "host.example.com")

    _fake_editor(
        monkeypatch,
        {"alias": "new-name", "host_name": "host.example.com",
         "local_forwards": [], "tags": []},
    )

    rc = main(["edit", "--config", str(config_path), "old-name"])
    assert rc == 0

    aliases = {h["alias"] for h in _hosts(config_path)}
    assert aliases == {"new-name"}


def test_edit_no_change_is_idempotent(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com")
    _fake_editor(monkeypatch, None)  # save without editing

    rc = main(["edit", "--config", str(config_path), "db"])
    assert rc == 0
    assert {h["alias"] for h in _hosts(config_path)} == {"db"}


# ---------------------------------------------------------------------------
# Error paths — original must survive
# ---------------------------------------------------------------------------

def test_edit_invalid_json_keeps_original(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com", "--user", "alice")
    before = config_path.read_text(encoding="utf-8")

    _fake_editor(monkeypatch, "{ this is not valid json")

    rc = main(["edit", "--config", str(config_path), "db"])
    assert rc == 1
    assert config_path.read_text(encoding="utf-8") == before


def test_edit_duplicate_alias_fails_validation(monkeypatch, tmp_path: Path) -> None:
    """Renaming host B onto host A's alias must be rejected, original kept."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "alpha", "a.example.com")
    _seed(config_path, "beta", "b.example.com")
    before = config_path.read_text(encoding="utf-8")

    # Edit beta to collide with alpha's alias.
    _fake_editor(
        monkeypatch,
        {"alias": "alpha", "host_name": "b.example.com",
         "local_forwards": [], "tags": []},
    )

    rc = main(["edit", "--config", str(config_path), "beta"])
    assert rc == 1
    assert config_path.read_text(encoding="utf-8") == before


def test_edit_missing_required_field_keeps_original(monkeypatch, tmp_path: Path) -> None:
    """Deleting host_name (a required field) must abort cleanly."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com")
    before = config_path.read_text(encoding="utf-8")

    _fake_editor(monkeypatch, {"alias": "db", "local_forwards": [], "tags": []})

    rc = main(["edit", "--config", str(config_path), "db"])
    assert rc == 1
    assert config_path.read_text(encoding="utf-8") == before


def test_edit_unknown_alias_errors(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com")

    # subprocess.run must never run for an unknown alias.
    monkeypatch.setenv("EDITOR", "fake-editor")
    monkeypatch.setattr(
        "xzssh.cli.commands.edit.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("editor should not launch")),
    )

    rc = main(["edit", "--config", str(config_path), "ghost"])
    assert rc == 1


def test_edit_no_editor_found_errors(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com")

    monkeypatch.setattr(
        "xzssh.cli.commands.edit._resolve_editor", lambda: None
    )

    rc = main(["edit", "--config", str(config_path), "db"])
    assert rc == 1
