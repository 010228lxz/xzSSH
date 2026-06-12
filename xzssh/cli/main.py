from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from xzssh.cli.commands import (
    add as add_cmd,
    check as check_cmd,
    connect as connect_cmd,
    decrypt as decrypt_cmd,
    edit as edit_cmd,
    encrypt as encrypt_cmd,
    export as export_cmd,
    generate as generate_cmd,
    history as history_cmd,
    import_ as import_cmd,
    import_json as import_json_cmd,
    key as key_cmd,
    list_ as list_cmd,
    menu as menu_cmd,
    profile as profile_cmd,
    remove as remove_cmd,
    search as search_cmd,
    sync as sync_cmd,
    test as test_cmd,
    theme as theme_cmd,
    transfer as transfer_cmd,
    tunnel as tunnel_cmd,
    which as which_cmd,
)
from xzssh.cli.completion import install_argcomplete
from xzssh.cli.parser import build_parser
from xzssh.cli.profiles import (
    ProfileError,
    registry_path,
    resolve_config_path,
    resolve_theme,
)
from xzssh.cli.ui import (
    apply_theme,
    print_banner,
    print_error,
    print_help,
    print_warning,
)
from xzssh.crypto import EnvelopeError
from xzssh.platform import (
    default_output_path as platform_default_output_path,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    # Activate shell completion when argcomplete is installed AND the
    # process is being driven by the completion shim. No-op otherwise.
    install_argcomplete(parser)
    args = parser.parse_args(argv)

    # Theme first — everything below prints. The flag value is already
    # argparse-validated; bad env/registry values degrade with a warning
    # (to stderr, so quiet commands' stdout stays clean).
    theme_name, theme_warning = resolve_theme(getattr(args, "theme", None))
    apply_theme(theme_name)
    if theme_warning:
        print_warning(theme_warning)

    if getattr(args, "help", False):
        print_banner()
        print_help()
        return 0

    # `profile` and `theme` are dispatched BEFORE config-path resolution:
    # a dangling default profile must never lock the user out of the very
    # commands needed to repair the registry.
    if args.command == "profile":
        print_banner()
        if getattr(args, "profile_command", None) is None:
            print_help()
            return 0
        return profile_cmd.run(args, registry_path())

    if args.command == "theme":
        print_banner()
        return theme_cmd.run(args, registry_path())

    try:
        config_path = resolve_config_path(
            args.config, getattr(args, "profile", None)
        )
    except ProfileError as exc:
        print_error(str(exc))
        return 2

    # Single choke point for envelope failures (cancelled pinentry,
    # wrong passphrase on re-encrypt, missing gpg/age binary): every
    # command writes through write_config, which raises EnvelopeError
    # before touching the file.
    try:
        return _dispatch(args, config_path)
    except EnvelopeError as exc:
        print_error(str(exc))
        return 1


def _dispatch(args, config_path: Path) -> int:
    if args.command is None:
        return menu_cmd.default_menu(config_path, args.suggest_ports)

    # Commands whose stdout is meant to be captured or piped must NOT emit
    # the decorative banner — it would corrupt redirected output (e.g.
    # `xzssh export > backup.json`, `$(xzssh which db)`). The transfer
    # wrappers are quiet too: rsync/scp output is often piped or parsed.
    QUIET_COMMANDS = {"which", "search", "export", "scp", "sftp", "rsync"}
    if args.command not in QUIET_COMMANDS:
        print_banner()

    if args.command == "which":
        return which_cmd.run(args, config_path)
    if args.command == "search":
        return search_cmd.run(args, config_path)
    if args.command == "export":
        return export_cmd.run(args, config_path)
    if args.command == "import-json":
        return import_json_cmd.run(args, config_path)
    if args.command == "list":
        return list_cmd.run(
            config_path,
            args.suggest_ports,
            tags=getattr(args, "tag", None) or [],
        )
    if args.command == "connect":
        return connect_cmd.run(
            args,
            config_path,
            args.suggest_ports,
            tags=getattr(args, "tag", None) or [],
        )
    if args.command == "menu":
        return menu_cmd.main_menu(config_path, args.suggest_ports)
    if args.command == "add":
        return add_cmd.run(args, config_path)
    if args.command == "edit":
        return edit_cmd.run(args, config_path)
    if args.command == "remove":
        return remove_cmd.run(args, config_path)
    if args.command == "import":
        return import_cmd.run(args, config_path)
    if args.command == "check":
        return check_cmd.run(config_path, args.suggest_ports)
    if args.command == "test":
        return test_cmd.run(args, config_path)
    if args.command in ("scp", "sftp", "rsync"):
        return transfer_cmd.run(args, config_path, args.command)
    if args.command == "history":
        return history_cmd.run(args, config_path)
    if args.command == "encrypt":
        return encrypt_cmd.run(args, config_path)
    if args.command == "decrypt":
        return decrypt_cmd.run(args, config_path)
    if args.command == "tunnel":
        if getattr(args, "tunnel_command", None) is None:
            print_help()
            return 0
        return tunnel_cmd.run(args, config_path)
    if args.command == "sync":
        output_path = (
            Path(args.output) if args.output else platform_default_output_path()
        )
        return sync_cmd.run(args, config_path, output_path)
    if args.command == "generate":
        output_path = (
            Path(args.output) if args.output else platform_default_output_path()
        )
        return generate_cmd.run(
            config_path,
            output_path,
            suggest_ports=args.suggest_ports,
            force=args.force,
            dry_run=args.dry_run,
        )
    if args.command == "key":
        if getattr(args, "key_command", None) is None:
            print_help()
            return 0
        return key_cmd.run(args, config_path)

    print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
