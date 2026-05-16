from __future__ import annotations

from pathlib import Path

from xzssh.cli.helpers import load_config_or_error
from xzssh.cli.ui import print_errors, print_success, print_warnings, status
from xzssh.generator import render_openssh
from xzssh.platform import ensure_secure_file_permissions
from xzssh.validator import validate_config


def run(config_path: Path, output_path: Path, suggest_ports: bool) -> int:
    with status("Reading source configuration"):
        config = load_config_or_error(config_path)
    if config is None:
        return 1

    with status("Final validation before generation"):
        result = validate_config(
            config, suggest_ports=suggest_ports, source_path=config_path
        )
    if result.errors:
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)

    with status(f"Generating OpenSSH config at {output_path}"):
        content = render_openssh(config, config_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        warning = ensure_secure_file_permissions(output_path)
    if warning:
        print_warnings([warning])
    print_success(f"OpenSSH configuration has been generated at {output_path}")
    return 0
