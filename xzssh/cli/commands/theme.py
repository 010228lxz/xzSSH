"""``xzssh theme`` — show or persist the UI color theme.

- ``theme`` — list available themes, marking the active one and the
  saved preference.
- ``theme <name>`` — persist *name* in the profiles registry (the CLI
  configuration home; themes are not SSH data and never touch
  ``xzssh.json``).
- ``theme --unset`` — clear the preference (back to the default).

One-off override without persisting: ``xzssh --theme classic list``,
or ``$XZSSH_THEME`` for a shell session.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from xzssh.cli.profiles import ProfileError, load_registry, save_registry
from xzssh.cli.ui import (
    DEFAULT_THEME,
    active_theme_name,
    available_themes,
    console,
    print_error,
    print_info,
    print_success,
)


def run(args: argparse.Namespace, registry_file: Path) -> int:
    try:
        registry = load_registry(registry_file)
    except ProfileError as exc:
        print_error(str(exc))
        return 1

    if args.unset and args.name:
        print_error("Pass a theme name or --unset, not both.")
        return 2

    if args.unset:
        registry.theme = None
        save_registry(registry_file, registry)
        print_success(
            f"Theme preference cleared (default: {DEFAULT_THEME})."
        )
        return 0

    if args.name:
        registry.theme = args.name
        save_registry(registry_file, registry)
        print_success(f"Theme preference saved: {args.name}")
        print_info(
            "Takes effect on the next run. One-off override: "
            "`xzssh --theme <name> ...`; per-session: `$XZSSH_THEME`."
        )
        return 0

    active = active_theme_name()
    for name in available_themes():
        markers = []
        if name == active:
            markers.append("[success]active[/success]")
        if name == registry.theme:
            markers.append("[info]saved[/info]")
        suffix = f"  ({', '.join(markers)})" if markers else ""
        console.print(f"  [alias]{name}[/alias]{suffix}")
    if registry.theme is None:
        print_info(
            f"No saved preference — using '{DEFAULT_THEME}' unless "
            "--theme or $XZSSH_THEME says otherwise."
        )
    return 0
