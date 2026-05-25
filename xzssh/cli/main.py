from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from xzssh.cli.commands import (
    add as add_cmd,
    check as check_cmd,
    connect as connect_cmd,
    generate as generate_cmd,
    import_ as import_cmd,
    key as key_cmd,
    list_ as list_cmd,
    menu as menu_cmd,
    remove as remove_cmd,
)
from xzssh.cli.parser import build_parser
from xzssh.cli.ui import print_banner, print_help
from xzssh.platform import (
    default_config_path as platform_default_config_path,
    default_output_path as platform_default_output_path,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    config_path = (
        Path(args.config) if args.config else platform_default_config_path()
    )

    if getattr(args, "help", False):
        print_banner()
        print_help()
        return 0

    if args.command is None:
        return menu_cmd.default_menu(config_path, args.suggest_ports)

    print_banner()

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
    if args.command == "remove":
        return remove_cmd.run(args, config_path)
    if args.command == "import":
        return import_cmd.run(args, config_path)
    if args.command == "check":
        return check_cmd.run(config_path, args.suggest_ports)
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
