"""``xzssh encrypt`` — wrap the JSON config in a gpg/age envelope.

Opt-in to at-rest encryption: sets ``Config.encryption`` and rewrites
the file through the envelope. From then on every command that touches
the config prompts for the passphrase (that UX cost is the feature's
price — see the CHANGELOG entry).

Deliberately **no plaintext ``.bak``** is left behind — that would
silently defeat the point. The escape hatches are ``xzssh decrypt``
and ``xzssh export`` (which prints decrypted JSON for backups).
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import print_error, print_info, print_success, print_warning


def run(args: argparse.Namespace, config_path: Path) -> int:
    tool = args.tool
    if shutil.which(tool) is None:
        print_error(
            f"'{tool}' not found on PATH. Install it, or pick the other "
            "tool with --tool."
        )
        return 1

    config = load_config_or_error(config_path)  # decrypts if already enveloped
    if config is None:
        return 1

    if config.encryption == tool:
        print_info(f"Config is already encrypted with {tool}; nothing to do.")
        return 0

    previous = config.encryption
    config.encryption = tool
    write_config(config_path, config)

    if previous:
        print_success(
            f"Re-encrypted {config_path} with {tool} (was {previous})."
        )
    else:
        print_success(f"Encrypted {config_path} with {tool}.")
    print_warning(
        "Every xzssh command will now prompt for the passphrase. If you "
        "lose it, the config is unrecoverable — consider keeping a backup "
        "via `xzssh export --output <file>` somewhere safe (it is written "
        "DECRYPTED)."
    )
    print_info(
        "The generated ~/.ssh/config stays plaintext — ssh itself has to "
        "read it. Undo anytime with `xzssh decrypt`."
    )
    return 0
