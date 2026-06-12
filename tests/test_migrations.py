"""Tests for the schema-version migration framework.

CURRENT_SCHEMA_VERSION is still 1, so no real migration exists yet —
these tests register synthetic migrations (monkeypatching the registry
and the current-version constant) to prove the machinery: in-memory
upgrade on load, one-time write-back with a ``.bak``, refusal of files
from a newer xzSSH, and hard errors on gaps in the chain.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict

import pytest

from xzssh.cli.completion import alias_completer
from xzssh.cli.main import main
from xzssh.model import CURRENT_SCHEMA_VERSION, Config
from xzssh.parser import ConfigParseError, load_config, load_config_versioned


posix_only = pytest.mark.skipif(
    os.name != "posix", reason="POSIX permission semantics"
)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _old_v1_file(path: Path) -> None:
    """A synthetic 'old' schema: hosts use ``name`` instead of ``alias``."""
    _write_json(
        path,
        {
            "version": 1,
            "hosts": [{"name": "db", "host_name": "db.example.com"}],
            "keys": {},
        },
    )


def _rename_name_to_alias(data: Dict[str, Any]) -> Dict[str, Any]:
    # Idempotent per the contract: a no-op on already-upgraded hosts.
    for host in data.get("hosts", []):
        if "alias" not in host and "name" in host:
            host["alias"] = host.pop("name")
    return data


@pytest.fixture
def v2_schema(monkeypatch: pytest.MonkeyPatch):
    """Pretend the current schema is v2, reached from v1 by the rename."""
    monkeypatch.setattr("xzssh.model.types.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr(
        "xzssh.parser.migrations.MIGRATIONS", {1: _rename_name_to_alias}
    )


# ---------------------------------------------------------------------------
# no-op path: file already at the current version
# ---------------------------------------------------------------------------

def test_config_default_version_is_current() -> None:
    assert Config().version == CURRENT_SCHEMA_VERSION


def test_current_version_file_loads_without_writeback(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    main(["add", "--config", str(config_path), "--alias", "db",
          "--host-name", "db.example.com"])
    before = config_path.read_text(encoding="utf-8")

    rc = main(["list", "--config", str(config_path)])
    assert rc == 0
    assert config_path.read_text(encoding="utf-8") == before
    assert not config_path.with_name("xzssh.json.bak").exists()


# ---------------------------------------------------------------------------
# the upgrade path
# ---------------------------------------------------------------------------

def test_migration_applied_in_memory_by_plain_load(
    tmp_path: Path, v2_schema
) -> None:
    """``load_config`` upgrades in memory but never writes anything."""
    config_path = tmp_path / "xzssh.json"
    _old_v1_file(config_path)
    before = config_path.read_text(encoding="utf-8")

    config = load_config(config_path)

    assert config.version == 2
    assert config.hosts[0].alias == "db"
    # Parser-level load is read-only: no rewrite, no backup.
    assert config_path.read_text(encoding="utf-8") == before
    assert not config_path.with_name("xzssh.json.bak").exists()


def test_load_config_versioned_reports_source_version(
    tmp_path: Path, v2_schema
) -> None:
    config_path = tmp_path / "xzssh.json"
    _old_v1_file(config_path)
    config, source_version = load_config_versioned(config_path)
    assert source_version == 1
    assert config.version == 2


def test_cli_load_writes_back_once_with_backup(tmp_path: Path, v2_schema) -> None:
    config_path = tmp_path / "xzssh.json"
    _old_v1_file(config_path)
    original = config_path.read_text(encoding="utf-8")

    rc = main(["list", "--config", str(config_path)])
    assert rc == 0

    # File upgraded on disk: stamped v2, alias field present.
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["version"] == 2
    assert data["hosts"][0]["alias"] == "db"
    assert "name" not in data["hosts"][0]

    # Backup holds the pre-migration original, byte for byte.
    backup = config_path.with_name("xzssh.json.bak")
    assert backup.read_text(encoding="utf-8") == original

    # Second load is a no-op: file and backup stay as they are.
    upgraded = config_path.read_text(encoding="utf-8")
    rc = main(["list", "--config", str(config_path)])
    assert rc == 0
    assert config_path.read_text(encoding="utf-8") == upgraded
    assert backup.read_text(encoding="utf-8") == original


@posix_only
def test_written_back_config_is_0600(tmp_path: Path, v2_schema) -> None:
    config_path = tmp_path / "xzssh.json"
    _old_v1_file(config_path)
    os.chmod(config_path, 0o644)

    main(["list", "--config", str(config_path)])

    mode = stat.S_IMODE(config_path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_multi_step_chain_runs_in_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("xzssh.model.types.CURRENT_SCHEMA_VERSION", 3)

    def step_1(data: Dict[str, Any]) -> Dict[str, Any]:
        data["hosts"][0]["host_name"] += ".one"
        return data

    def step_2(data: Dict[str, Any]) -> Dict[str, Any]:
        data["hosts"][0]["host_name"] += ".two"
        return data

    monkeypatch.setattr(
        "xzssh.parser.migrations.MIGRATIONS", {1: step_1, 2: step_2}
    )

    config_path = tmp_path / "xzssh.json"
    _write_json(
        config_path,
        {"version": 1,
         "hosts": [{"alias": "db", "host_name": "db"}], "keys": {}},
    )

    config = load_config(config_path)
    assert config.hosts[0].host_name == "db.one.two"
    assert config.version == 3


# ---------------------------------------------------------------------------
# refusals
# ---------------------------------------------------------------------------

def test_newer_schema_is_refused(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _write_json(config_path, {"version": 99, "hosts": [], "keys": {}})

    with pytest.raises(ConfigParseError, match="newer"):
        load_config(config_path)

    # And the CLI surfaces it as a clean failure, file untouched.
    before = config_path.read_text(encoding="utf-8")
    assert main(["check", "--config", str(config_path)]) == 1
    assert config_path.read_text(encoding="utf-8") == before


def test_gap_in_migration_chain_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Current is 2 but nobody registered the 1 -> 2 step.
    monkeypatch.setattr("xzssh.model.types.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr("xzssh.parser.migrations.MIGRATIONS", {})

    config_path = tmp_path / "xzssh.json"
    _write_json(config_path, {"version": 1, "hosts": [], "keys": {}})

    with pytest.raises(ConfigParseError, match="No migration registered"):
        load_config(config_path)


def test_migration_returning_non_dict_is_a_parse_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("xzssh.model.types.CURRENT_SCHEMA_VERSION", 2)
    monkeypatch.setattr(
        "xzssh.parser.migrations.MIGRATIONS", {1: lambda data: None}
    )

    config_path = tmp_path / "xzssh.json"
    _write_json(config_path, {"version": 1, "hosts": [], "keys": {}})

    with pytest.raises(ConfigParseError, match="did not return an object"):
        load_config(config_path)


# ---------------------------------------------------------------------------
# quiet-path safety
# ---------------------------------------------------------------------------

def test_export_stdout_stays_valid_json_during_migration(
    tmp_path: Path, v2_schema, capsys
) -> None:
    """The upgrade notice must go to stderr — export's stdout is piped."""
    config_path = tmp_path / "xzssh.json"
    _old_v1_file(config_path)

    rc = main(["export", "--config", str(config_path)])
    assert rc == 0

    out = capsys.readouterr().out
    data = json.loads(out)  # would blow up if the notice hit stdout
    assert data["hosts"][0]["alias"] == "db"


def test_completion_migrates_in_memory_without_writing(
    tmp_path: Path, v2_schema
) -> None:
    """Completers run inside the shell shim — they must never write."""
    config_path = tmp_path / "xzssh.json"
    _old_v1_file(config_path)
    before = config_path.read_text(encoding="utf-8")

    class FakeArgs:
        config = str(config_path)

    assert alias_completer("d", FakeArgs()) == ["db"]
    assert config_path.read_text(encoding="utf-8") == before
    assert not config_path.with_name("xzssh.json.bak").exists()
