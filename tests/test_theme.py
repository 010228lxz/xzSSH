"""Tests for UI themes (`xzssh theme`, `--theme`, `$XZSSH_THEME`).

The conftest autouse fixture resets the module-global consoles to the
default theme after every test, so the mutation in apply_theme can't
bleed between tests.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from xzssh.cli import ui
from xzssh.cli.main import main
from xzssh.cli.profiles import load_registry, registry_path, resolve_theme


# ---------------------------------------------------------------------------
# apply_theme mechanics
# ---------------------------------------------------------------------------

def test_apply_theme_switches_console_styles() -> None:
    neon_alias = ui.console.get_style("alias")
    ui.apply_theme("classic")
    assert ui.active_theme_name() == "classic"
    assert ui.console.get_style("alias") != neon_alias
    # And both consoles move together.
    assert ui.error_console.get_style("alias") == ui.console.get_style("alias")


def test_apply_theme_is_reversible() -> None:
    before = ui.console.get_style("alias")
    ui.apply_theme("mono")
    ui.apply_theme("neon")
    assert ui.console.get_style("alias") == before


def test_apply_theme_unknown_name_raises() -> None:
    with pytest.raises(ValueError, match="Unknown theme"):
        ui.apply_theme("sparkly")


def test_every_palette_defines_the_same_style_names() -> None:
    """A missing semantic name in any palette would crash at render time."""
    reference = set(ui.PALETTES["neon"]["styles"])
    for name, palette in ui.PALETTES.items():
        assert set(palette["styles"]) == reference, name
        assert set(palette["prompt"]) == set(ui.PALETTES["neon"]["prompt"]), name


def test_banner_renders_under_every_theme(capsys) -> None:
    for name in ui.available_themes():
        ui.apply_theme(name)
        ui.print_banner()  # would raise on a missing style name
    capsys.readouterr()


# ---------------------------------------------------------------------------
# resolution: --theme > $XZSSH_THEME > registry > default
# ---------------------------------------------------------------------------

def test_flag_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XZSSH_THEME", "classic")
    assert resolve_theme("mono") == ("mono", None)


def test_env_var_selects_theme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XZSSH_THEME", "classic")
    assert resolve_theme(None) == ("classic", None)


def test_registry_preference(tmp_path: Path) -> None:
    main(["theme", "high-contrast"])
    assert resolve_theme(None) == ("high-contrast", None)


def test_default_when_nothing_set() -> None:
    assert resolve_theme(None) == (ui.DEFAULT_THEME, None)


def test_invalid_env_theme_warns_and_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XZSSH_THEME", "sparkly")
    name, warning = resolve_theme(None)
    assert name == ui.DEFAULT_THEME
    assert warning and "sparkly" in warning


def test_flag_applies_end_to_end(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    main(["add", "--config", str(config_path),
          "--alias", "db", "--host-name", "db.example.com"])

    rc = main(["--theme", "classic", "list", "--config", str(config_path)])
    assert rc == 0
    assert ui.active_theme_name() == "classic"


def test_argparse_rejects_unknown_theme_flag(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(["--theme", "sparkly", "list", "--config", str(tmp_path / "x.json")])


# ---------------------------------------------------------------------------
# the theme command
# ---------------------------------------------------------------------------

def test_theme_command_persists_preference() -> None:
    rc = main(["theme", "classic"])
    assert rc == 0
    registry_file = Path(os.environ["XZSSH_PROFILES_FILE"])
    data = json.loads(registry_file.read_text(encoding="utf-8"))
    assert data["theme"] == "classic"


def test_theme_unset_clears_preference() -> None:
    main(["theme", "classic"])
    rc = main(["theme", "--unset"])
    assert rc == 0
    assert load_registry(registry_path()).theme is None


def test_theme_list_shows_all(capsys) -> None:
    main(["theme", "classic"])
    capsys.readouterr()
    rc = main(["theme"])
    assert rc == 0
    out = capsys.readouterr().out
    for name in ui.available_themes():
        assert name in out
    assert "saved" in out


def test_theme_preference_survives_profile_operations(tmp_path: Path) -> None:
    """profile add must not clobber the theme key (same registry file)."""
    main(["theme", "mono"])
    main(["profile", "add", "work", str(tmp_path / "w.json")])
    registry = load_registry(registry_path())
    assert registry.theme == "mono"
    assert "work" in registry.profiles
