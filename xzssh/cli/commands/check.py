from __future__ import annotations

from pathlib import Path

from xzssh.cli.helpers import load_config_or_error
from xzssh.cli.ui import print_errors, print_success, print_warnings, status
from xzssh.validator import validate_config


def run(config_path: Path, suggest_ports: bool) -> int:
    with status("Analyzing configuration health"):
        config = load_config_or_error(config_path)
    if config is None:
        return 1

    with status("Performing semantic validation"):
        result = validate_config(
            config, suggest_ports=suggest_ports, source_path=config_path
        )
    if result.errors:
        print_errors(result.errors)
        return 1
    if result.warnings:
        print_warnings(result.warnings)
    print_success("Configuration analysis complete. No issues found.")
    return 0
