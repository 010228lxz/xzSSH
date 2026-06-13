from __future__ import annotations

import argparse

from xzssh.cli.completion import (
    alias_completer,
    key_completer,
    profile_completer,
)
from xzssh.cli.ui import available_themes


def build_parser() -> argparse.ArgumentParser:
    # The same global options exist on the top-level parser AND (via this
    # parent) on every subparser, so they work in either position. The
    # subparser copies use default=SUPPRESS: without it, a subparser that
    # doesn't see the flag writes its default into the shared namespace,
    # silently clobbering a value parsed before the subcommand
    # (`xzssh --config foo list`) on Python 3.13+.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--config",
        default=argparse.SUPPRESS,
        help="Path to JSON config file (default: ~/.ssh/xzssh.json)",
    )
    parent_profile = parent.add_argument(
        "--profile",
        metavar="NAME",
        default=argparse.SUPPRESS,
        help="Use a registered profile's config file (see `xzssh profile`)",
    )
    parent_profile.completer = profile_completer  # type: ignore[attr-defined]
    parent.add_argument(
        "--theme",
        choices=available_themes(),
        default=argparse.SUPPRESS,
        help="UI color theme for this invocation (see `xzssh theme`)",
    )
    parent.add_argument(
        "--suggest-ports",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Suggest next free LocalForward port when conflicts are found",
    )

    parser = argparse.ArgumentParser(prog="xzssh", add_help=False)
    parser.add_argument(
        "--config",
        help="Path to JSON config file (default: ~/.ssh/xzssh.json)",
    )
    top_profile = parser.add_argument(
        "--profile",
        metavar="NAME",
        help="Use a registered profile's config file (see `xzssh profile`)",
    )
    top_profile.completer = profile_completer  # type: ignore[attr-defined]
    parser.add_argument(
        "--theme",
        choices=available_themes(),
        help="UI color theme for this invocation (see `xzssh theme`)",
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
    list_parser.add_argument(
        "--match-all",
        action="store_true",
        help="Require ALL given --tag values instead of any (AND semantics)",
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
        "--match-all",
        action="store_true",
        help="Require ALL given --tag values instead of any (AND semantics)",
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

    history_parser = subparsers.add_parser(
        "history",
        parents=[parent],
        help="Show recent connections (from the opt-in event log)",
    )
    history_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Show at most N entries (default: 50)",
    )
    history_subparsers = history_parser.add_subparsers(
        dest="history_command", required=False
    )
    history_enable = history_subparsers.add_parser(
        "enable", parents=[parent], help="Opt in to connection logging"
    )
    history_enable.add_argument(
        "--file",
        metavar="PATH",
        help="Log file path (default: xzssh.log next to the config file)",
    )
    history_subparsers.add_parser(
        "disable", parents=[parent], help="Stop logging (keeps the log file)"
    )
    history_subparsers.add_parser(
        "clear", parents=[parent], help="Delete the log file"
    )

    encrypt_parser = subparsers.add_parser(
        "encrypt",
        parents=[parent],
        help="Encrypt the JSON config at rest (gpg or age envelope)",
    )
    encrypt_parser.add_argument(
        "--tool",
        choices=["gpg", "age"],
        default="gpg",
        help="Encryption tool to use (default: gpg, symmetric AES256)",
    )

    subparsers.add_parser(
        "decrypt",
        parents=[parent],
        help="Store the JSON config as plaintext again",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        parents=[parent],
        help="Detect and resolve drift between the JSON and ~/.ssh/config",
    )
    sync_parser.add_argument(
        "--output",
        help="Path of the OpenSSH config to compare (default: ~/.ssh/config)",
    )
    sync_parser.add_argument(
        "--prefer",
        choices=["json", "file"],
        help="Resolve all drift in one direction without prompting",
    )
    sync_parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Choose json/file per drifted host",
    )
    sync_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow --prefer json to overwrite a file containing unmodeled "
        "constructs (Match/Include/wildcards); a .bak is always saved",
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

    tunnel_parser = subparsers.add_parser(
        "tunnel",
        parents=[parent],
        help="Open a host's port-forwards without a shell",
    )
    tunnel_subparsers = tunnel_parser.add_subparsers(
        dest="tunnel_command", required=False
    )

    tunnel_start = tunnel_subparsers.add_parser(
        "start", parents=[parent], help="Open the tunnel (ssh -N)"
    )
    tunnel_start_alias = tunnel_start.add_argument(
        "alias", help="Alias of the host whose forwards to open"
    )
    tunnel_start_alias.completer = alias_completer  # type: ignore[attr-defined]
    tunnel_start.add_argument(
        "--detach",
        action="store_true",
        help="Run in the background; manage with `tunnel list` / `tunnel stop`",
    )

    tunnel_subparsers.add_parser(
        "list", parents=[parent], help="Show recorded tunnels and their status"
    )

    tunnel_stop = tunnel_subparsers.add_parser(
        "stop", parents=[parent], help="Stop a background tunnel"
    )
    tunnel_stop_alias = tunnel_stop.add_argument(
        "alias", nargs="?", help="Alias of the tunnel to stop"
    )
    tunnel_stop_alias.completer = alias_completer  # type: ignore[attr-defined]
    tunnel_stop.add_argument(
        "--all", action="store_true", help="Stop every recorded tunnel"
    )

    profile_parser = subparsers.add_parser(
        "profile", parents=[parent], help="Manage config profiles"
    )
    profile_subparsers = profile_parser.add_subparsers(
        dest="profile_command", required=False
    )

    profile_add = profile_subparsers.add_parser(
        "add", parents=[parent], help="Register a named config file"
    )
    profile_add.add_argument("name", help="Profile name (e.g. work)")
    profile_add.add_argument("path", help="Path to that profile's JSON config")
    profile_add.add_argument(
        "--default",
        action="store_true",
        dest="set_default",
        help="Also make this the default profile",
    )
    profile_add.add_argument(
        "--replace",
        action="store_true",
        help="Replace an existing profile with the same name",
    )

    profile_subparsers.add_parser(
        "list", parents=[parent], help="List registered profiles"
    )

    profile_use = profile_subparsers.add_parser(
        "use", parents=[parent], help="Set the default profile"
    )
    profile_use_name = profile_use.add_argument("name")
    profile_use_name.completer = profile_completer  # type: ignore[attr-defined]

    profile_remove = profile_subparsers.add_parser(
        "remove",
        parents=[parent],
        help="Unregister a profile (keeps its config file)",
    )
    profile_remove_name = profile_remove.add_argument("name")
    profile_remove_name.completer = profile_completer  # type: ignore[attr-defined]

    for tool, tool_help in (
        ("scp", "Run scp with alias rewriting (db:/path → user@host:/path)"),
        ("sftp", "Run sftp against an alias"),
        ("rsync", "Run rsync with alias rewriting and -e ssh options"),
    ):
        tool_parser = subparsers.add_parser(tool, parents=[parent], help=tool_help)
        tool_parser.add_argument(
            "--dry-run",
            action="store_true",
            help=f"Print the resolved {tool} command without running it",
        )
        tool_parser.add_argument(
            "args",
            nargs=argparse.REMAINDER,
            metavar="ARGS",
            help=f"Arguments passed to {tool}; <alias>:<path> tokens are "
            "rewritten. xzssh's own flags come first; use `--` before "
            f"{tool} flags (e.g. `xzssh {tool} -- -r ...`)",
        )

    theme_parser = subparsers.add_parser(
        "theme", parents=[parent], help="Show or set the UI color theme"
    )
    theme_parser.add_argument(
        "name",
        nargs="?",
        choices=available_themes(),
        help="Theme to persist as your preference",
    )
    theme_parser.add_argument(
        "--unset",
        action="store_true",
        help="Clear the persisted theme preference",
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
    key_add_agent.add_argument(
        "--keychain",
        action="store_true",
        help="macOS only: store the passphrase in the Keychain "
        "(ssh-add --apple-use-keychain), so later loads don't prompt",
    )

    return parser
