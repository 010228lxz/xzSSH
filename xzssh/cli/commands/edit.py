"""``xzssh edit <alias>`` — edit a host's JSON entry in ``$EDITOR``.

Until now the only ways to change a host were ``add --replace`` (a full
flag-driven rewrite) or remove-then-add. This opens just that host's
``to_dict()`` in the user's editor, then on save:

1. re-parses the edited JSON (shape check),
2. splices it back into the config **by the host's original position**
   — so renaming the alias in the editor works,
3. re-validates the *whole* Config (dup-alias, ProxyJump, port
   conflicts all still fire),
4. writes atomically only if everything is valid.

On any error — bad JSON, failed validation, editor not found — the
original config is left untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import (
    print_error,
    print_errors,
    print_info,
    print_success,
    print_warnings,
    status,
)
from xzssh.parser import ConfigParseError, load_config
from xzssh.validator import validate_config


def _resolve_editor() -> Optional[List[str]]:
    """Return the editor command as an argv list, or None if none found."""
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        # Allow editors specified with args, e.g. EDITOR="code --wait".
        try:
            return shlex.split(editor)
        except ValueError:
            return [editor]

    if os.name == "nt":
        return ["notepad"]

    import shutil

    for candidate in ("nano", "vim", "vi"):
        if shutil.which(candidate):
            return [candidate]
    return None


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    alias = getattr(args, "alias", None)
    if not alias:
        print_error("No alias provided.")
        return 2

    idx = next(
        (i for i, h in enumerate(config.hosts) if h.alias == alias), None
    )
    if idx is None:
        print_error(f"Host not found: {alias}")
        return 1

    editor_argv = _resolve_editor()
    if editor_argv is None:
        print_error(
            "No editor found. Set $EDITOR (or $VISUAL) and try again."
        )
        return 1

    original_dict = config.hosts[idx].to_dict()
    # mkstemp creates the file 0600 — it holds hostnames and key paths.
    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="xzssh-edit-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(original_dict, indent=2, ensure_ascii=False) + "\n")

        print_info(f"Opening {alias} in {editor_argv[0]}...")
        try:
            subprocess.run(editor_argv + [str(tmp_path)], check=False)
        except FileNotFoundError:
            print_error(f"Editor not found: {editor_argv[0]}")
            return 1

        edited_text = tmp_path.read_text(encoding="utf-8")
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    try:
        edited_dict = json.loads(edited_text)
    except json.JSONDecodeError as exc:
        print_error(f"Edited JSON is invalid: {exc}. No changes were made.")
        return 1

    if not isinstance(edited_dict, dict):
        print_error("Edited content must be a JSON object. No changes were made.")
        return 1

    # Splice the edited host back in by POSITION (so a rename is honored)
    # and re-parse the whole config through the normal pipeline.
    merged = config.to_dict()
    merged["hosts"][idx] = edited_dict

    new_config = _config_from_dict(merged, config_path)
    if new_config is None:
        return 1

    result = validate_config(new_config, source_path=config_path)
    if result.errors:
        print_error("Edited config failed validation; no changes were made:")
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    with status("Saving changes"):
        write_config(config_path, new_config)
    new_alias = edited_dict.get("alias", alias)
    print_success(f"Host '{new_alias}' updated.")
    return 0


def _config_from_dict(data: dict, config_path: Path):
    """Round-trip a config dict through ``load_config`` for shape validation.

    Writing to a temp file and reading it back reuses the JSON parser's
    required-field and type checks rather than duplicating them here.
    """
    fd, tmp_name = tempfile.mkstemp(suffix=".json", prefix="xzssh-merge-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False))
        return load_config(tmp_path)
    except ConfigParseError as exc:
        print_error(f"Edited host is structurally invalid: {exc}. No changes were made.")
        return None
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
