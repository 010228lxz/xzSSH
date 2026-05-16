from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from xzssh.model import Config, Host, LocalForward


class ConfigParseError(ValueError):
    pass


def load_config(path: Path) -> Config:
    try:
        raw_text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigParseError(f"Config file not found: {path}") from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigParseError(f"Invalid JSON in config file: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigParseError("Config root must be a JSON object")

    version_value = data.get("version", 1)
    version = _coerce_int(version_value, "version")

    keys_value = data.get("keys", {})
    if keys_value is None:
        keys_value = {}
    if not isinstance(keys_value, dict):
        raise ConfigParseError("Field 'keys' must be an object if provided")
    keys = _parse_keys(keys_value)

    hosts_value = data.get("hosts")
    if hosts_value is None:
        raise ConfigParseError("Config is missing required field 'hosts'")
    if not isinstance(hosts_value, list):
        raise ConfigParseError("Field 'hosts' must be a list")

    hosts: List[Host] = []
    for idx, host_data in enumerate(hosts_value):
        if not isinstance(host_data, dict):
            raise ConfigParseError(f"Host entry at index {idx} must be an object")
        hosts.append(_parse_host(host_data, idx))

    return Config(version=version, hosts=hosts, keys=keys)


def _parse_keys(data: Dict[str, Any]) -> Dict[str, str]:
    keys: Dict[str, str] = {}
    for name, path in data.items():
        if not isinstance(name, str) or not name.strip():
            raise ConfigParseError("Key name must be a non-empty string")
        if not isinstance(path, str) or not path.strip():
            raise ConfigParseError(f"Key path for '{name}' must be a non-empty string")
        keys[name] = path
    return keys


def _parse_host(data: Dict[str, Any], idx: int) -> Host:
    alias = _require_str(data, "alias", f"hosts[{idx}].alias")
    host_name = _require_str(data, "host_name", f"hosts[{idx}].host_name")

    user = _optional_str(data, "user")
    port = _optional_int(data, "port")
    identity_file = _optional_str(data, "identity_file")
    last_used = _optional_str(data, "last_used")
    
    tags_value = data.get("tags", [])
    if tags_value is None:
        tags_value = []
    if not isinstance(tags_value, list):
        raise ConfigParseError(f"hosts[{idx}].tags must be a list if provided")
    tags = [str(t) for t in tags_value]

    local_forwards_value = data.get("local_forwards", [])
    if local_forwards_value is None:
        local_forwards_value = []
    if not isinstance(local_forwards_value, list):
        raise ConfigParseError(
            f"hosts[{idx}].local_forwards must be a list if provided"
        )

    local_forwards: List[LocalForward] = []
    for lf_idx, lf_data in enumerate(local_forwards_value):
        if not isinstance(lf_data, dict):
            raise ConfigParseError(
                f"hosts[{idx}].local_forwards[{lf_idx}] must be an object"
            )
        local_forwards.append(_parse_local_forward(lf_data, idx, lf_idx))

    return Host(
        alias=alias,
        host_name=host_name,
        user=user,
        port=port,
        identity_file=identity_file,
        local_forwards=local_forwards,
        tags=tags,
        last_used=last_used,
    )


def _parse_local_forward(
    data: Dict[str, Any], host_idx: int, lf_idx: int
) -> LocalForward:
    local_port = _require_int(
        data, "local_port", f"hosts[{host_idx}].local_forwards[{lf_idx}].local_port"
    )
    remote_host = _require_str(
        data, "remote_host", f"hosts[{host_idx}].local_forwards[{lf_idx}].remote_host"
    )
    remote_port = _require_int(
        data, "remote_port", f"hosts[{host_idx}].local_forwards[{lf_idx}].remote_port"
    )

    return LocalForward(
        local_port=local_port,
        remote_host=remote_host,
        remote_port=remote_port,
    )


def _require_str(data: Dict[str, Any], key: str, label: str) -> str:
    if key not in data:
        raise ConfigParseError(f"Missing required field '{label}'")
    value = data[key]
    if value is None:
        raise ConfigParseError(f"Field '{label}' cannot be null")
    return str(value)


def _optional_str(data: Dict[str, Any], key: str) -> Optional[str]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    return str(value)


def _require_int(data: Dict[str, Any], key: str, label: str) -> int:
    if key not in data:
        raise ConfigParseError(f"Missing required field '{label}'")
    value = data[key]
    return _coerce_int(value, label)


def _optional_int(data: Dict[str, Any], key: str) -> Optional[int]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    return _coerce_int(value, key)


def _coerce_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigParseError(f"Field '{label}' must be an integer") from exc
