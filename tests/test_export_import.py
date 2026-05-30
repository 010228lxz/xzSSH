"""Tests for ``xzssh export`` and ``xzssh import-json``.

Export must produce *valid JSON on stdout* (the banner trap). Import
must validate before writing, default to a non-destructive merge, and
back up the existing config on --replace.
"""
from __future__ import annotations

import json
from pathlib import Path

from xzssh.cli.main import main


def _seed(config_path: Path, alias: str, hostname: str, *extra: str) -> None:
    main(
        [
            "add", "--config", str(config_path),
            "--alias", alias, "--host-name", hostname, *extra,
        ]
    )


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_stdout_is_valid_json(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com", "--user", "alice")
    capsys.readouterr()  # drop banner/seed noise

    rc = main(["export", "--config", str(config_path)])
    assert rc == 0

    out = capsys.readouterr().out
    # The discriminating assertion: stdout parses as JSON. A banner would
    # break this.
    data = json.loads(out)
    assert data["hosts"][0]["alias"] == "db"
    assert data["hosts"][0]["user"] == "alice"


def test_export_to_file(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    backup = tmp_path / "backup.json"
    _seed(config_path, "db", "db.example.com")

    rc = main(["export", "--config", str(config_path), "--output", str(backup)])
    assert rc == 0
    assert backup.exists()
    data = json.loads(backup.read_text(encoding="utf-8"))
    assert {h["alias"] for h in data["hosts"]} == {"db"}


def test_export_missing_config_returns_one(tmp_path: Path) -> None:
    rc = main(["export", "--config", str(tmp_path / "absent.json")])
    assert rc == 1


def test_export_roundtrips_through_load(tmp_path: Path, capsys) -> None:
    """An exported snapshot must be re-importable byte-for-byte."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.internal", "--port", "2200")
    capsys.readouterr()

    main(["export", "--config", str(config_path)])
    snapshot = capsys.readouterr().out
    # Round-trip: snapshot is valid JSON matching the on-disk config.
    assert json.loads(snapshot) == json.loads(
        config_path.read_text(encoding="utf-8")
    )


# ---------------------------------------------------------------------------
# import-json --merge (default)
# ---------------------------------------------------------------------------

def test_import_json_merge_adds_new_hosts(tmp_path: Path) -> None:
    target = tmp_path / "xzssh.json"
    snapshot = tmp_path / "snap.json"
    _seed(target, "existing", "existing.example.com")
    _seed(snapshot, "fresh", "fresh.example.com")

    rc = main(["import-json", "--config", str(target), str(snapshot)])
    assert rc == 0

    data = json.loads(target.read_text(encoding="utf-8"))
    assert {h["alias"] for h in data["hosts"]} == {"existing", "fresh"}


def test_import_json_merge_is_default(tmp_path: Path) -> None:
    """No flag should behave as --merge, not --replace."""
    target = tmp_path / "xzssh.json"
    snapshot = tmp_path / "snap.json"
    _seed(target, "existing", "existing.example.com")
    _seed(snapshot, "fresh", "fresh.example.com")

    main(["import-json", "--config", str(target), str(snapshot)])

    data = json.loads(target.read_text(encoding="utf-8"))
    # existing host survived → it was a merge, not a replace
    assert "existing" in {h["alias"] for h in data["hosts"]}


def test_import_json_merge_keeps_existing_on_conflict(tmp_path: Path) -> None:
    target = tmp_path / "xzssh.json"
    snapshot = tmp_path / "snap.json"
    _seed(target, "db", "original.example.com")
    _seed(snapshot, "db", "snapshot.example.com")  # same alias, different host

    main(["import-json", "--config", str(target), str(snapshot)])

    data = json.loads(target.read_text(encoding="utf-8"))
    db = next(h for h in data["hosts"] if h["alias"] == "db")
    # Existing host wins on conflict.
    assert db["host_name"] == "original.example.com"


# ---------------------------------------------------------------------------
# import-json --replace
# ---------------------------------------------------------------------------

def test_import_json_replace_swaps_config_and_backs_up(tmp_path: Path) -> None:
    target = tmp_path / "xzssh.json"
    snapshot = tmp_path / "snap.json"
    _seed(target, "old", "old.example.com")
    _seed(snapshot, "new", "new.example.com")

    rc = main(
        ["import-json", "--config", str(target), "--replace", str(snapshot)]
    )
    assert rc == 0

    data = json.loads(target.read_text(encoding="utf-8"))
    # Old host gone, only snapshot host remains.
    assert {h["alias"] for h in data["hosts"]} == {"new"}

    # A .bak of the pre-replace config must exist.
    backup = target.with_name(target.name + ".bak")
    assert backup.exists()
    bak_data = json.loads(backup.read_text(encoding="utf-8"))
    assert {h["alias"] for h in bak_data["hosts"]} == {"old"}


# ---------------------------------------------------------------------------
# validation / safety
# ---------------------------------------------------------------------------

def test_import_json_missing_file_returns_one(tmp_path: Path) -> None:
    target = tmp_path / "xzssh.json"
    _seed(target, "db", "db.example.com")
    rc = main(["import-json", "--config", str(target), str(tmp_path / "nope.json")])
    assert rc == 1


def test_import_json_invalid_snapshot_aborts_without_touching_config(
    tmp_path: Path,
) -> None:
    target = tmp_path / "xzssh.json"
    snapshot = tmp_path / "bad.json"
    _seed(target, "db", "db.example.com")
    before = target.read_text(encoding="utf-8")

    snapshot.write_text("{ this is not valid json", encoding="utf-8")

    rc = main(["import-json", "--config", str(target), str(snapshot)])
    assert rc == 1
    # Live config untouched.
    assert target.read_text(encoding="utf-8") == before


def test_import_json_semantically_invalid_snapshot_aborts(tmp_path: Path) -> None:
    """A snapshot with a duplicate alias fails validation → no write."""
    target = tmp_path / "xzssh.json"
    snapshot = tmp_path / "dup.json"
    _seed(target, "db", "db.example.com")
    before = target.read_text(encoding="utf-8")

    snapshot.write_text(
        json.dumps(
            {
                "version": 1,
                "hosts": [
                    {"alias": "x", "host_name": "a.example.com"},
                    {"alias": "x", "host_name": "b.example.com"},
                ],
                "keys": {},
            }
        ),
        encoding="utf-8",
    )

    rc = main(["import-json", "--config", str(target), str(snapshot)])
    assert rc == 1
    assert target.read_text(encoding="utf-8") == before
