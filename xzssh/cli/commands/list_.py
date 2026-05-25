from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

import questionary

from xzssh.cli.commands import add as add_cmd
from xzssh.cli.commands import remove as remove_cmd
from xzssh.cli.helpers import filter_hosts_by_tags, load_config_or_error
from xzssh.cli.ui import (
    console,
    print_banner,
    print_error,
    print_errors,
    print_host_table,
    print_info,
    print_step,
    print_warnings,
    prompt_select_action,
    prompt_select_host,
    status,
)
from xzssh.validator import validate_config


def run(
    config_path: Path,
    suggest_ports: bool,
    interactive: bool = False,
    tags: Optional[List[str]] = None,
) -> int:
    tags = list(tags or [])
    while True:
        if interactive:
            console.clear()
            print_banner()

        with status("Scanning configuration"):
            config = load_config_or_error(config_path)
        if config is None:
            return 1

        with status("Validating host configuration"):
            result = validate_config(
                config, suggest_ports=suggest_ports, source_path=config_path
            )
        if result.errors:
            print_errors(result.errors)
            if not interactive:
                return 1
            questionary.press_any_key_to_continue().ask()
            return 0
        if result.warnings:
            print_warnings(result.warnings)

        displayed_hosts = filter_hosts_by_tags(config.hosts, tags)

        if tags:
            tag_str = ", ".join(tags)
            if not displayed_hosts:
                print_info(f"No hosts match tag(s): {tag_str}")
                return 0
            print_step(
                f"Showing {len(displayed_hosts)} of {len(config.hosts)} host(s)"
                f" · filter: {tag_str}"
            )
        else:
            print_step(f"Retrieved {len(config.hosts)} configured host(s)")

        print_host_table(displayed_hosts)

        if not interactive:
            return 0

        action = prompt_select_action(
            "Manage Hosts",
            choices=[
                questionary.Choice(
                    [("class:shortcut", "(a)"), ("class:text", " "), ("class:text", "Add New Host")],
                    value="add",
                ),
                questionary.Choice(
                    [("class:shortcut", "(r)"), ("class:text", " "), ("class:text", "Remove Host")],
                    value="remove",
                ),
                questionary.Separator(),
                questionary.Choice(
                    [("class:shortcut", "(b)"), ("class:text", " "), ("class:text", "Back to Menu")],
                    value="back",
                ),
            ],
            shortcuts={"a": "add", "r": "remove", "b": "back"},
        )

        if action == "back" or action is None:
            break
        elif action == "add":
            mock_args = argparse.Namespace(
                alias=None,
                host_name=None,
                user=None,
                port=None,
                identity_file=None,
                local_forward=[],
                tag=None,
                replace=False,
                suggest_ports=suggest_ports,
            )
            add_cmd.run(mock_args, config_path)
        elif action == "remove":
            if not config.hosts:
                print_error("No hosts to remove.")
                questionary.press_any_key_to_continue().ask()
                continue

            host_to_remove = prompt_select_host(config.hosts, "Select a host to remove:")
            if host_to_remove and host_to_remove != "back":
                alias_to_remove = (
                    host_to_remove.alias
                    if hasattr(host_to_remove, "alias")
                    else host_to_remove
                )
                mock_remove_args = argparse.Namespace(
                    alias=[alias_to_remove],
                    all=False,
                    suggest_ports=suggest_ports,
                )
                remove_cmd.run(mock_remove_args, config_path)

    return 0
