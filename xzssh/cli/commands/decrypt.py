"""``xzssh decrypt`` — store the JSON config as plaintext again.

The inverse of ``xzssh encrypt``: prompts once to decrypt, clears
``Config.encryption``, and writes the file back as plain (0600) JSON.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from xzssh.cli.helpers import load_config_or_error, write_config
from xzssh.cli.ui import print_info, print_success


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    if config.encryption is None:
        print_info("Config is not encrypted; nothing to do.")
        return 0

    config.encryption = None
    write_config(config_path, config)
    print_success(f"{config_path} is plaintext JSON again (still 0600).")
    return 0
