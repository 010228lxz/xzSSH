"""Tests for ``xzssh profile`` and ``--profile`` config resolution.

The autouse fixture in conftest.py points ``XZSSH_PROFILES_FILE`` at a
throwaway registry, so these tests never touch a real
``~/.config/xzssh/profiles.json``.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from xzssh.cli.main import main
from xzssh.cli.profiles import (
    ProfileError,
    load_registry,
    registry_path,
    resolve_config_path,
)


posix_only = pytest.mark.skipif(
    os.name != "posix", reason="POSIX permission semantics"
)


def _seed(config_path: Path, alias: str, hostname: str) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", alias, "--host-name", hostname]
    )


# ---------------------------------------------------------------------------
# registry commands
# ---------------------------------------------------------------------------

def test_profile_add_registers(tmp_path: Path) -> None:
    rc = main(["profile", "add", "work", str(tmp_path / "work.json")])
    assert rc == 0

    registry = load_registry(registry_path())
    assert registry.profiles == {"work": str(tmp_path / "work.json")}
    assert registry.default is None


def test_profile_add_duplicate_needs_replace(tmp_path: Path) -> None:
    main(["profile", "add", "work", str(tmp_path / "one.json")])
    rc = main(["profile", "add", "work", str(tmp_path / "two.json")])
    assert rc == 1
    assert load_registry(registry_path()).profiles["work"].endswith("one.json")

    rc = main(
        ["profile", "add", "work", str(tmp_path / "two.json"), "--replace"]
    )
    assert rc == 0
    assert load_registry(registry_path()).profiles["work"].endswith("two.json")


def test_profile_add_rejects_hostile_names(tmp_path: Path) -> None:
    rc = main(["profile", "add", "bad name!", str(tmp_path / "x.json")])
    assert rc == 2
    assert load_registry(registry_path()).profiles == {}


def test_profile_add_default_flag(tmp_path: Path) -> None:
    main(["profile", "add", "work", str(tmp_path / "w.json"), "--default"])
    assert load_registry(registry_path()).default == "work"


def test_profile_use_sets_default(tmp_path: Path) -> None:
    main(["profile", "add", "work", str(tmp_path / "w.json")])
    main(["profile", "add", "home", str(tmp_path / "h.json")])

    rc = main(["profile", "use", "home"])
    assert rc == 0
    assert load_registry(registry_path()).default == "home"

    assert main(["profile", "use", "nope"]) == 1


def test_profile_remove(tmp_path: Path) -> None:
    config = tmp_path / "w.json"
    _seed(config, "db", "db.example.com")
    main(["profile", "add", "work", str(config), "--default"])

    rc = main(["profile", "remove", "work"])
    assert rc == 0
    registry = load_registry(registry_path())
    assert registry.profiles == {}
    assert registry.default is None
    # Unregistering never deletes the config file itself.
    assert config.exists()

    assert main(["profile", "remove", "work"]) == 1


def test_profile_list_smoke(tmp_path: Path, capsys) -> None:
    main(["profile", "add", "work", str(tmp_path / "w.json")])
    capsys.readouterr()
    rc = main(["profile", "list"])
    assert rc == 0
    assert "work" in capsys.readouterr().out


@posix_only
def test_registry_file_is_0600(tmp_path: Path) -> None:
    main(["profile", "add", "work", str(tmp_path / "w.json")])
    mode = stat.S_IMODE(registry_path().stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# resolution: --profile / $XZSSH_PROFILE / default / --config
# ---------------------------------------------------------------------------

def test_global_flags_work_before_the_subcommand(tmp_path: Path) -> None:
    """Regression: on Python 3.13+ subparser defaults clobbered globals
    parsed before the subcommand (`xzssh --config foo list`)."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path, "db", "db.example.com")

    assert main(["--config", str(config_path), "list"]) == 0
    main(["profile", "add", "work", str(config_path)])
    assert main(["--profile", "work", "list"]) == 0


def test_profile_flag_routes_commands(tmp_path: Path) -> None:
    work_config = tmp_path / "work.json"
    main(["profile", "add", "work", str(work_config)])

    rc = main(
        ["add", "--profile", "work",
         "--alias", "db", "--host-name", "db.work.example"]
    )
    assert rc == 0

    data = json.loads(work_config.read_text(encoding="utf-8"))
    assert data["hosts"][0]["alias"] == "db"

    # And reading back through the same profile works.
    assert main(["list", "--profile", "work"]) == 0


def test_env_var_selects_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work_config = tmp_path / "work.json"
    _seed(work_config, "db", "db.work.example")
    main(["profile", "add", "work", str(work_config)])

    monkeypatch.setenv("XZSSH_PROFILE", "work")
    assert resolve_config_path(None, None) == work_config
    assert main(["list"]) == 0


def test_flag_beats_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    main(["profile", "add", "work", str(tmp_path / "w.json")])
    main(["profile", "add", "home", str(tmp_path / "h.json")])
    monkeypatch.setenv("XZSSH_PROFILE", "work")

    assert resolve_config_path(None, "home") == tmp_path / "h.json"


def test_default_profile_used_when_nothing_else(tmp_path: Path) -> None:
    main(["profile", "add", "work", str(tmp_path / "w.json"), "--default"])
    assert resolve_config_path(None, None) == tmp_path / "w.json"


def test_no_profiles_falls_back_to_platform_default() -> None:
    from xzssh.platform import default_config_path

    assert resolve_config_path(None, None) == default_config_path()


def test_config_flag_short_circuits_profiles(tmp_path: Path) -> None:
    """--config must not even read the registry (it may be corrupt)."""
    Path(os.environ["XZSSH_PROFILES_FILE"]).write_text(
        "{ corrupt", encoding="utf-8"
    )
    explicit = tmp_path / "explicit.json"
    assert resolve_config_path(str(explicit), None) == explicit


def test_config_and_profile_conflict(tmp_path: Path) -> None:
    with pytest.raises(ProfileError, match="mutually exclusive"):
        resolve_config_path(str(tmp_path / "x.json"), "work")
    rc = main(
        ["list", "--config", str(tmp_path / "x.json"), "--profile", "work"]
    )
    assert rc == 2


def test_unknown_profile_is_clean_error(tmp_path: Path) -> None:
    rc = main(["list", "--profile", "ghost"])
    assert rc == 2


def test_dangling_default_does_not_lock_out_profile_commands(
    tmp_path: Path,
) -> None:
    """A registry whose default points nowhere must still be repairable."""
    registry_file = Path(os.environ["XZSSH_PROFILES_FILE"])
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(
        json.dumps({"default": "ghost", "profiles": {}}), encoding="utf-8"
    )

    # Normal commands fail cleanly...
    assert main(["list"]) == 2
    # ...but the repair path still works.
    assert main(["profile", "add", "work", str(tmp_path / "w.json")]) == 0
    assert main(["profile", "use", "work"]) == 0
    assert main(["profile", "list"]) == 0


def test_relative_profile_path_anchors_to_registry_dir() -> None:
    registry_file = Path(os.environ["XZSSH_PROFILES_FILE"])
    main(["profile", "add", "work", "work.json"])
    resolved = resolve_config_path(None, "work")
    assert resolved == registry_file.parent / "work.json"
