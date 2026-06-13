"""Profile registry — named pointers to alternate xzssh.json files.

Power users juggle work / personal / client configs. A *profile* is a
name → config-file-path mapping, so ``xzssh --profile work connect db``
works without remembering ``--config ~/team-ssh.json`` everywhere.

The registry is a small JSON file that lives **outside** ``~/.ssh`` —
it is CLI configuration, not SSH data:

- POSIX: ``$XDG_CONFIG_HOME/xzssh/profiles.json`` (default
  ``~/.config/xzssh/profiles.json``)
- Windows: ``%APPDATA%\\xzssh\\profiles.json``
- ``$XZSSH_PROFILES_FILE`` overrides the location outright (also how
  the test suite stays hermetic).

(JSON rather than TOML: Python 3.9 has no stdlib TOML reader and no
stdlib TOML writer at any version, and the runtime dep tree stays
rich + questionary only.)

Shape::

    {
      "default": "work",                  // optional
      "profiles": { "work": "~/team-ssh.json", ... }
    }

Resolution order for the active config file (first match wins):

1. ``--config PATH`` — an explicit file; combining it with
   ``--profile`` is an error rather than a silent precedence guess.
2. ``--profile NAME``
3. ``$XZSSH_PROFILE`` (per-shell-session override)
4. the registry's ``default`` profile
5. the platform default (``~/.ssh/xzssh.json``)

Relative profile paths resolve relative to the registry file's
directory, mirroring how ``identity_file`` anchors to the config file.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from xzssh.platform import (
    default_config_path,
    detect_platform,
    Platform,
    ensure_secure_file_permissions,
    resolve_path,
)


class ProfileError(ValueError):
    pass


@dataclass
class ProfileRegistry:
    default: Optional[str] = None
    profiles: Dict[str, str] = field(default_factory=dict)
    # Persisted UI theme preference (`xzssh theme <name>`). Lives here
    # because this file is xzSSH's CLI configuration home — it is not
    # SSH data and must not live in xzssh.json.
    theme: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {"profiles": dict(self.profiles)}
        if self.default is not None:
            data["default"] = self.default
        if self.theme is not None:
            data["theme"] = self.theme
        return data


def registry_path() -> Path:
    override = os.environ.get("XZSSH_PROFILES_FILE")
    if override:
        return Path(override).expanduser()
    if detect_platform() == Platform.WINDOWS:
        base = os.environ.get("APPDATA")
        base_path = (
            Path(base) if base else Path.home() / "AppData" / "Roaming"
        )
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        base_path = Path(base).expanduser() if base else Path.home() / ".config"
    return base_path / "xzssh" / "profiles.json"


def load_registry(path: Path) -> ProfileRegistry:
    """Read the registry; a missing file is an empty registry."""
    if not path.exists():
        return ProfileRegistry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"Invalid profile registry at {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError(f"Profile registry root must be a JSON object: {path}")

    profiles_value = data.get("profiles", {})
    if not isinstance(profiles_value, dict):
        raise ProfileError(f"'profiles' must be an object in {path}")
    profiles: Dict[str, str] = {}
    for name, path_value in profiles_value.items():
        if not isinstance(name, str) or not name.strip():
            raise ProfileError(f"Profile name must be a non-empty string in {path}")
        if not isinstance(path_value, str) or not path_value.strip():
            raise ProfileError(
                f"Path for profile '{name}' must be a non-empty string in {path}"
            )
        profiles[name] = path_value

    default = data.get("default")
    if default is not None and not isinstance(default, str):
        raise ProfileError(f"'default' must be a string in {path}")

    theme = data.get("theme")
    if theme is not None and not isinstance(theme, str):
        raise ProfileError(f"'theme' must be a string in {path}")

    return ProfileRegistry(default=default, profiles=profiles, theme=theme)


def save_registry(path: Path, registry: ProfileRegistry) -> None:
    """Persist the registry atomically, like ``write_config`` does.

    0600 as well — profile paths reveal where config files live.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(registry.to_dict(), indent=2, ensure_ascii=False) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    try:
        tmp_path.write_text(payload, encoding="utf-8")
        ensure_secure_file_permissions(tmp_path)
        os.replace(tmp_path, path)
    except OSError:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def profile_config_path(registry: ProfileRegistry, name: str) -> Path:
    """Resolve a registered profile name to its config file path."""
    path_value = registry.profiles.get(name)
    if path_value is None:
        known = ", ".join(sorted(registry.profiles)) or "none registered"
        raise ProfileError(
            f"Unknown profile '{name}' (known profiles: {known}). "
            "See `xzssh profile list`."
        )
    return resolve_path(path_value, registry_path().parent)


def resolve_config_path(
    config_arg: Optional[str], profile_arg: Optional[str]
) -> Path:
    """Pick the active config file. See the module docstring for the order.

    Raises ``ProfileError`` on a conflicting/unknown selection or an
    unreadable registry.
    """
    if config_arg and profile_arg:
        raise ProfileError(
            "--config and --profile are mutually exclusive; pass one or the other"
        )
    if config_arg:
        return Path(config_arg)

    name = profile_arg
    source = "--profile"
    if not name:
        name = os.environ.get("XZSSH_PROFILE") or None
        source = "$XZSSH_PROFILE"

    registry = load_registry(registry_path())
    if not name:
        name = registry.default
        source = "default profile"
    if not name:
        return default_config_path()

    try:
        return profile_config_path(registry, name)
    except ProfileError as exc:
        raise ProfileError(f"{exc} (selected via {source})") from exc


def resolve_theme(theme_arg: Optional[str]) -> "tuple[str, Optional[str]]":
    """Pick the UI theme: ``--theme`` > ``$XZSSH_THEME`` > registry > default.

    Returns ``(name, warning)``. The flag value is already validated by
    argparse; a bad env/registry value degrades to the default with a
    warning instead of bricking the CLI — and a broken registry is left
    for config-path resolution to report, not theming.
    """
    from xzssh.cli.ui import DEFAULT_THEME, available_themes

    if theme_arg:
        return theme_arg, None

    name = os.environ.get("XZSSH_THEME") or None
    source = "$XZSSH_THEME"
    if not name:
        try:
            registry = load_registry(registry_path())
        except ProfileError:
            return DEFAULT_THEME, None
        name = registry.theme
        source = "the profiles registry"
    if not name:
        return DEFAULT_THEME, None
    if name not in available_themes():
        return DEFAULT_THEME, (
            f"Ignoring unknown theme '{name}' from {source} "
            f"(available: {', '.join(available_themes())})"
        )
    return name, None
