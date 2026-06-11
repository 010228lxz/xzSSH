"""``xzssh profile`` — manage named pointers to alternate config files.

Subcommands:

- ``add <name> <path>`` — register a profile (``--default`` to also
  make it the default, ``--replace`` to overwrite an existing name).
  The config file itself is *not* created here — like the platform
  default, it comes into being on the first write (``xzssh add
  --profile <name> ...``).
- ``list`` — table of registered profiles.
- ``use <name>`` — set the default profile.
- ``remove <name>`` — unregister (never deletes the config file).

These subcommands deliberately do not go through profile *resolution* —
a dangling default profile must never lock the user out of the very
commands needed to repair it.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from xzssh.cli.profiles import (
    ProfileError,
    ProfileRegistry,
    load_registry,
    profile_config_path,
    save_registry,
)
from xzssh.cli.ui import (
    print_error,
    print_info,
    print_profile_table,
    print_success,
)

# Names must stay shell- and env-var-friendly ($XZSSH_PROFILE).
_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def run(args: argparse.Namespace, registry_file: Path) -> int:
    try:
        registry = load_registry(registry_file)
    except ProfileError as exc:
        print_error(str(exc))
        return 1

    command = args.profile_command
    if command == "add":
        return _add(args, registry_file, registry)
    if command == "list":
        return _list(registry)
    if command == "use":
        return _use(args, registry_file, registry)
    if command == "remove":
        return _remove(args, registry_file, registry)
    print_error(f"Unknown profile command: {command}")
    return 2


def _add(
    args: argparse.Namespace, registry_file: Path, registry: ProfileRegistry
) -> int:
    name = args.name
    if not _NAME_RE.match(name):
        print_error(
            f"Invalid profile name '{name}': use letters, digits, '.', '_', "
            "'-' (must start with a letter or digit)"
        )
        return 2

    if name in registry.profiles and not args.replace:
        print_error(
            f"Profile already exists: {name} → {registry.profiles[name]}. "
            "Use --replace to overwrite."
        )
        return 1

    registry.profiles[name] = args.path
    if args.set_default:
        registry.default = name
    save_registry(registry_file, registry)

    print_success(f"Profile '{name}' → {args.path}")
    if args.set_default:
        print_info(f"'{name}' is now the default profile.")
    if not profile_config_path(registry, name).exists():
        print_info(
            "That config file doesn't exist yet — it will be created on "
            f"the first write (e.g. `xzssh add --profile {name} ...`)."
        )
    return 0


def _list(registry: ProfileRegistry) -> int:
    rows = [
        (
            name,
            path_value,
            name == registry.default,
            profile_config_path(registry, name).exists(),
        )
        for name, path_value in sorted(registry.profiles.items())
    ]
    print_profile_table(rows)
    return 0


def _use(
    args: argparse.Namespace, registry_file: Path, registry: ProfileRegistry
) -> int:
    if args.name not in registry.profiles:
        print_error(
            f"Unknown profile '{args.name}'. See `xzssh profile list`."
        )
        return 1
    registry.default = args.name
    save_registry(registry_file, registry)
    print_success(f"Default profile is now '{args.name}'.")
    return 0


def _remove(
    args: argparse.Namespace, registry_file: Path, registry: ProfileRegistry
) -> int:
    if args.name not in registry.profiles:
        print_error(
            f"Unknown profile '{args.name}'. See `xzssh profile list`."
        )
        return 1
    path_value = registry.profiles.pop(args.name)
    if registry.default == args.name:
        registry.default = None
        print_info("Removed profile was the default; no default profile now.")
    save_registry(registry_file, registry)
    print_success(
        f"Profile '{args.name}' removed (the config file {path_value} "
        "itself was not deleted)."
    )
    return 0
