from __future__ import annotations

import argparse

from xzssh.cli.completion import alias_completer, key_completer


def build_parser() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--config",
        help="Path to JSON config file (default: ~/.ssh/xzssh.json)",
    )
    parent.add_argument(
        "--suggest-ports",
        action="store_true",
        help="Suggest next free LocalForward port when conflicts are found",
    )

    parser = argparse.ArgumentParser(prog="xzssh", add_help=False)
    parser.add_argument(
        "--config",
        help="Path to JSON config file (default: ~/.ssh/xzssh.json)",
    )
    parser.add_argument(
        "--suggest-ports",
        action="store_true",
        help="Suggest next free LocalForward port when conflicts are found",
    )
    parser.add_argument(
        "-h", "--help",
        action="store_true",
        help="Show this help message and exit",
    )

    subparsers = parser.add_subparsers(dest="command", required=False)

    list_parser = subparsers.add_parser("list", parents=[parent], help="List configured hosts")
    list_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="TAG",
        help=(
            "Show only hosts with this tag (repeatable; a host matches if it has"
            " any of the given tags)"
        ),
    )

    connect_parser = subparsers.add_parser(
        "connect", parents=[parent], help="Connect to a host"
    )
    connect_alias = connect_parser.add_argument(
        "alias", nargs="?", help="Alias of the host to connect to"
    )
    connect_alias.completer = alias_completer  # type: ignore[attr-defined]
    connect_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        metavar="TAG",
        help=(
            "Restrict fuzzy-search choices to hosts with this tag (repeatable;"
            " OR semantics; has no effect when <alias> is given explicitly)"
        ),
    )
    connect_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the ssh command that would run, without connecting or "
        "stamping last_used",
    )

    subparsers.add_parser("menu", parents=[parent], help="Open interactive management menu")

    edit_parser = subparsers.add_parser(
        "edit", parents=[parent], help="Edit a host's JSON entry in $EDITOR"
    )
    edit_alias = edit_parser.add_argument(
        "alias", help="Alias of the host to edit"
    )
    edit_alias.completer = alias_completer  # type: ignore[attr-defined]

    add_parser = subparsers.add_parser("add", parents=[parent], help="Add a host")
    add_parser.add_argument("--alias")
    add_parser.add_argument("--host-name")
    add_parser.add_argument("--user")
    add_parser.add_argument("--port", type=int)
    add_parser.add_argument("--identity-file")
    add_parser.add_argument(
        "--proxy-jump",
        metavar="ALIAS",
        help="Bastion host alias to jump through (becomes ProxyJump in the generated config)",
    )
    add_parser.add_argument("--tag", action="append", default=[], help="Tag for the host")
    add_parser.add_argument(
        "--local-forward",
        action="append",
        default=[],
        help="local_port:remote_host:remote_port",
    )
    add_parser.add_argument(
        "--remote-forward",
        action="append",
        default=[],
        help="remote_port:local_host:local_port",
    )
    add_parser.add_argument(
        "--dynamic-forward",
        action="append",
        default=[],
        type=int,
        metavar="PORT",
        help="Local SOCKS proxy port (repeatable)",
    )
    add_parser.add_argument(
        "--forward-agent",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable ssh-agent forwarding (ForwardAgent)",
    )
    add_parser.add_argument(
        "--compression",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable compression (Compression)",
    )
    add_parser.add_argument(
        "--identities-only",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Only use the configured IdentityFile (IdentitiesOnly)",
    )
    add_parser.add_argument(
        "--server-alive-interval",
        type=int,
        default=None,
        metavar="SECONDS",
        help="Keepalive interval in seconds (ServerAliveInterval)",
    )
    add_parser.add_argument(
        "--strict-host-key-checking",
        choices=["yes", "no", "ask", "accept-new", "off"],
        default=None,
        help="StrictHostKeyChecking policy",
    )
    add_parser.add_argument(
        "--user-known-hosts-file",
        default=None,
        metavar="PATH",
        help="Path for UserKnownHostsFile",
    )
    add_parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing host with the same alias",
    )

    remove_parser = subparsers.add_parser(
        "remove", parents=[parent], help="Remove a host"
    )
    remove_alias = remove_parser.add_argument(
        "alias", nargs="*", help="Alias of the host(s) to remove"
    )
    remove_alias.completer = alias_completer  # type: ignore[attr-defined]
    remove_parser.add_argument("--all", action="store_true", help="Remove all hosts")
    remove_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show which hosts would be removed without modifying the config",
    )

    import_parser = subparsers.add_parser(
        "import", parents=[parent], help="Import from SSH config"
    )
    import_parser.add_argument(
        "file", nargs="?", help="Path to OpenSSH config file (default: ~/.ssh/config)"
    )
    import_parser.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing hosts"
    )

    subparsers.add_parser("check", parents=[parent], help="Validate config")

    export_parser = subparsers.add_parser(
        "export",
        parents=[parent],
        help="Print a JSON snapshot of the config (for backup)",
    )
    export_parser.add_argument(
        "--output",
        help="Write the snapshot to this file instead of stdout",
    )

    import_json_parser = subparsers.add_parser(
        "import-json",
        parents=[parent],
        help="Restore the config from a JSON snapshot produced by export",
    )
    import_json_parser.add_argument(
        "file", help="Path to the JSON snapshot to import"
    )
    import_json_mode = import_json_parser.add_mutually_exclusive_group()
    import_json_mode.add_argument(
        "--merge",
        action="store_true",
        help="Add new hosts/keys, keep existing on alias conflict (default)",
    )
    import_json_mode.add_argument(
        "--replace",
        action="store_true",
        help="Replace the whole config with the snapshot (a .bak is saved first)",
    )

    which_parser = subparsers.add_parser(
        "which",
        parents=[parent],
        help="Print the resolved ssh command line for a host without running it",
    )
    which_alias = which_parser.add_argument(
        "alias", help="Alias of the host to resolve"
    )
    which_alias.completer = alias_completer  # type: ignore[attr-defined]

    search_parser = subparsers.add_parser(
        "search",
        parents=[parent],
        help="Search hosts by alias, hostname, user, tag, or proxy-jump",
    )
    search_parser.add_argument(
        "query", help="Case-insensitive substring to search for"
    )

    test_parser = subparsers.add_parser(
        "test",
        parents=[parent],
        help="Probe connectivity without opening an interactive shell",
    )
    test_alias = test_parser.add_argument(
        "alias",
        nargs="?",
        help="Alias of the host to probe (omit when using --all)",
    )
    test_alias.completer = alias_completer  # type: ignore[attr-defined]
    test_parser.add_argument(
        "--all",
        action="store_true",
        help="Probe every configured host in parallel",
    )
    test_parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        metavar="SECONDS",
        help="Per-host connect timeout (default: 5)",
    )

    generate_parser = subparsers.add_parser(
        "generate", parents=[parent], help="Generate ~/.ssh/config"
    )
    generate_parser.add_argument(
        "--output",
        help="Output path for generated OpenSSH config (default: ~/.ssh/config)",
    )
    generate_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file even if it wasn't generated by xzSSH "
        "(a .bak copy is always saved when overwriting)",
    )
    generate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the would-be output to stdout and exit without writing",
    )

    key_parser = subparsers.add_parser("key", parents=[parent], help="Manage keys")
    key_subparsers = key_parser.add_subparsers(dest="key_command", required=False)

    key_add = key_subparsers.add_parser(
        "add", parents=[parent], help="Add a key reference"
    )
    key_add.add_argument("name")
    key_add.add_argument("path")
    key_add.add_argument(
        "--replace",
        action="store_true",
        help="Replace existing key with the same name",
    )

    key_subparsers.add_parser("list", parents=[parent], help="List configured keys")

    key_add_agent = key_subparsers.add_parser(
        "add-agent", parents=[parent], help="Add key to ssh-agent"
    )
    key_add_agent_name = key_add_agent.add_argument("name")
    key_add_agent_name.completer = key_completer  # type: ignore[attr-defined]

    return parser
