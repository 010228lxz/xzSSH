from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from xzssh.cli.ui import print_error
from xzssh.model import Config, LocalForward
from xzssh.parser import ConfigParseError, load_config
from xzssh.platform import resolve_path


def load_config_or_error(config_path: Path) -> Optional[Config]:
    config = load_config_if_exists(config_path)
    if config is None:
        print_error(f"Config file not found: {config_path}")
        return None
    return config


def load_config_if_exists(config_path: Path) -> Optional[Config]:
    if not config_path.exists():
        return None
    try:
        return load_config(config_path)
    except ConfigParseError as exc:
        print_error(str(exc))
        return None


def parse_local_forward_arg(raw: str) -> LocalForward:
    parts = raw.split(":", 2)
    if len(parts) != 3:
        raise ValueError(
            "Invalid --local-forward value. Expected local_port:remote_host:remote_port"
        )
    local_port_str, remote_host, remote_port_str = parts
    if not remote_host:
        raise ValueError(
            "Invalid --local-forward value. remote_host must be non-empty"
        )
    try:
        local_port = int(local_port_str)
        remote_port = int(remote_port_str)
    except ValueError as exc:
        raise ValueError("LocalForward ports must be integers") from exc

    return LocalForward(
        local_port=local_port,
        remote_host=remote_host,
        remote_port=remote_port,
    )


def write_config(config_path: Path, config: Config) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, ensure_ascii=False)
    config_path.write_text(payload + "\n", encoding="utf-8")


def resolve_key_path(path_value: str, source_path: Path) -> Path:
    return resolve_path(path_value, source_path.parent)
