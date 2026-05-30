"""``xzssh export`` — print a pretty JSON snapshot of the config.

A backup / portability aid. With no ``--output`` it writes the JSON to
stdout (banner-suppressed, so `xzssh export > backup.json` produces a
valid file). With ``--output FILE`` it writes there instead.

The payload is exactly ``Config.to_dict()`` serialized with ``indent=2``
— the same shape ``load_config`` (and ``xzssh import-json``) reads back.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from xzssh.cli.helpers import load_config_or_error
from xzssh.cli.ui import print_error, print_success
from xzssh.platform import ensure_secure_file_permissions


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    payload = json.dumps(config.to_dict(), indent=2, ensure_ascii=False) + "\n"

    output = getattr(args, "output", None)
    if output:
        out_path = Path(output)
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(payload, encoding="utf-8")
            # The snapshot holds the same secret content (hostnames, key
            # paths) as xzssh.json — apply the same 0600 / ACL posture.
            ensure_secure_file_permissions(out_path)
        except OSError as exc:
            print_error(f"Failed to write export to {out_path}: {exc}")
            return 1
        print_success(
            f"Exported {len(config.hosts)} host(s) to {out_path}"
        )
        return 0

    # Write straight to stdout — bypass rich so line-wrapping can't corrupt
    # the JSON when the output is redirected or piped.
    sys.stdout.write(payload)
    return 0
