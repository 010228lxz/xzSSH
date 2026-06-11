from __future__ import annotations

import argparse
from pathlib import Path

import questionary

from xzssh.cli.commands import (
    add as add_cmd,
    check as check_cmd,
    connect as connect_cmd,
    generate as generate_cmd,
    import_ as import_cmd,
    list_ as list_cmd,
    remove as remove_cmd,
)
from xzssh.cli.helpers import load_config_if_exists
from xzssh.cli.ui import (
    console,
    print_banner,
    print_error,
    print_help,
    print_host_status,
    prompt_select_action,
    status,
)
from xzssh.model import Config
from xzssh.platform import default_output_path


def default_menu(config_path: Path, suggest_ports: bool) -> int:
    """Welcome menu shown when xzssh is invoked with no arguments."""
    while True:
        console.clear()
        print_banner()
        config = load_config_if_exists(config_path)

        if config and config.hosts:
            recent_hosts = sorted(
                [h for h in config.hosts if h.last_used],
                key=lambda h: h.last_used,
                reverse=True,
            )[:3]
            if recent_hosts:
                console.print("[section]Recent Connections[/section]")
                for h in recent_hosts:
                    print_host_status(h.alias, h.host_name, "online")
                console.print("")

        choices = []
        shortcuts = {}
        if config and config.hosts:
            choices.extend([
                questionary.Choice(
                    [("class:shortcut", "(c)"), ("class:text", " "), ("class:text", "Connect to a host")],
                    value="connect",
                ),
                questionary.Choice(
                    [("class:shortcut", "(m)"), ("class:text", " "), ("class:text", "Manage hosts (List/Add/Remove)")],
                    value="menu",
                ),
            ])
            shortcuts.update({"c": "connect", "m": "menu"})
        else:
            choices.extend([
                questionary.Choice(
                    [("class:shortcut", "(a)"), ("class:text", " "), ("class:text", "Add your first host")],
                    value="add",
                ),
                questionary.Choice(
                    [("class:shortcut", "(i)"), ("class:text", " "), ("class:text", "Import from SSH config")],
                    value="import",
                ),
            ])
            shortcuts.update({"a": "add", "i": "import"})

        choices.extend([
            questionary.Choice(
                [("class:shortcut", "(g)"), ("class:text", " "), ("class:text", "Generate SSH config")],
                value="generate",
            ),
            questionary.Separator(),
            questionary.Choice(
                [("class:shortcut", "(h)"), ("class:text", " "), ("class:text", "View help")],
                value="help",
            ),
            questionary.Choice(
                [("class:shortcut", "(x)"), ("class:text", " "), ("class:text", "Exit")],
                value="exit",
            ),
        ])
        shortcuts.update({"g": "generate", "h": "help", "x": "exit"})

        action = prompt_select_action(
            "Welcome! What would you like to do?",
            choices=choices,
            shortcuts=shortcuts,
        )

        if action == "exit" or action is None:
            break

        if action == "connect":
            connect_cmd.run(
                argparse.Namespace(alias=None), config_path, suggest_ports
            )
        elif action == "menu":
            main_menu(config_path, suggest_ports)
        elif action == "add":
            add_cmd.run(
                argparse.Namespace(
                    alias=None,
                    host_name=None,
                    user=None,
                    port=None,
                    identity_file=None,
                    proxy_jump=None,
                    local_forward=[],
                    tag=None,
                    replace=False,
                    suggest_ports=suggest_ports,
                ),
                config_path,
            )
            questionary.press_any_key_to_continue().ask()
        elif action == "import":
            default_path = str(Path.home() / ".ssh" / "config")
            import_file = questionary.text(
                "Path to OpenSSH config file:", default=default_path
            ).ask()

            if import_file:
                import_cmd.run(
                    argparse.Namespace(file=import_file, overwrite=False),
                    config_path,
                )
            else:
                print_error("Import cancelled.")
            questionary.press_any_key_to_continue().ask()
        elif action == "generate":
            generate_cmd.run(config_path, default_output_path(), suggest_ports)
            questionary.press_any_key_to_continue().ask()
        elif action == "help":
            print_help()
            questionary.press_any_key_to_continue().ask()

    return 0


def main_menu(config_path: Path, suggest_ports: bool) -> int:
    """Full management menu (xzssh menu subcommand)."""
    while True:
        console.clear()
        print_banner()
        with status("Loading configuration"):
            config = load_config_if_exists(config_path)
        if config is None:
            config = Config(hosts=[])

        action = prompt_select_action(
            "Main Menu",
            choices=[
                questionary.Choice(
                    [("class:shortcut", "(c)"), ("class:text", " "), ("class:text", "Connect to Host")],
                    value="connect",
                ),
                questionary.Choice(
                    [("class:shortcut", "(l)"), ("class:text", " "), ("class:text", "List Hosts")],
                    value="list",
                ),
                questionary.Choice(
                    [("class:shortcut", "(a)"), ("class:text", " "), ("class:text", "Add Host")],
                    value="add",
                ),
                questionary.Choice(
                    [("class:shortcut", "(r)"), ("class:text", " "), ("class:text", "Remove Host")],
                    value="remove",
                ),
                questionary.Choice(
                    [("class:shortcut", "(i)"), ("class:text", " "), ("class:text", "Import Config")],
                    value="import",
                ),
                questionary.Choice(
                    [("class:shortcut", "(g)"), ("class:text", " "), ("class:text", "Generate Config")],
                    value="generate",
                ),
                questionary.Choice(
                    [("class:shortcut", "(k)"), ("class:text", " "), ("class:text", "Check Health")],
                    value="check",
                ),
                questionary.Choice(
                    [("class:shortcut", "(h)"), ("class:text", " "), ("class:text", "View Help")],
                    value="help",
                ),
                questionary.Separator(),
                questionary.Choice(
                    [("class:shortcut", "(x)"), ("class:text", " "), ("class:text", "Back to Welcome")],
                    value="exit",
                ),
            ],
            shortcuts={
                "c": "connect",
                "l": "list",
                "a": "add",
                "r": "remove",
                "i": "import",
                "g": "generate",
                "k": "check",
                "h": "help",
                "x": "exit",
            },
        )

        if action == "exit" or action is None:
            break

        if action == "connect":
            connect_cmd.run(
                argparse.Namespace(alias=None), config_path, suggest_ports
            )
        elif action == "list":
            list_cmd.run(config_path, suggest_ports, interactive=True)
        elif action == "add":
            mock_args = argparse.Namespace(
                alias=None,
                host_name=None,
                user=None,
                port=None,
                identity_file=None,
                proxy_jump=None,
                local_forward=[],
                tag=[],
                replace=False,
                suggest_ports=suggest_ports,
            )
            add_cmd.run(mock_args, config_path)
            questionary.press_any_key_to_continue().ask()
        elif action == "remove":
            if not config.hosts:
                print_error("No hosts to remove.")
                questionary.press_any_key_to_continue().ask()
                continue

            remove_choices = [
                questionary.Choice(
                    title=[
                        ("class:shortcut", f"({i+1})"),
                        ("class:text", " "),
                        ("class:text", f"{h.alias} ({h.host_name})"),
                    ],
                    value=h,
                )
                for i, h in enumerate(config.hosts)
            ]
            remove_choices.extend([
                questionary.Separator(),
                questionary.Choice(
                    [("class:shortcut", "(b)"), ("class:text", " "), ("class:text", "Back / Cancel")],
                    value="back",
                ),
            ])

            remove_shortcuts = {
                str(i + 1): h.alias for i, h in enumerate(config.hosts) if i < 9
            }
            remove_shortcuts["b"] = "back"

            host_to_remove = prompt_select_action(
                "Select a host to remove:",
                choices=remove_choices,
                shortcuts=remove_shortcuts,
            )

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
                questionary.press_any_key_to_continue().ask()
        elif action == "import":
            default_path = str(Path.home() / ".ssh" / "config")
            import_file = questionary.text(
                "Path to OpenSSH config file:", default=default_path
            ).ask()

            if import_file:
                import_cmd.run(
                    argparse.Namespace(file=import_file, overwrite=False),
                    config_path,
                )
            else:
                print_error("Import cancelled.")
            questionary.press_any_key_to_continue().ask()
        elif action == "generate":
            generate_cmd.run(config_path, default_output_path(), suggest_ports)
            questionary.press_any_key_to_continue().ask()
        elif action == "check":
            check_cmd.run(config_path, suggest_ports)
            questionary.press_any_key_to_continue().ask()
        elif action == "help":
            print_help()
            questionary.press_any_key_to_continue().ask()

    return 0
