from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from xzssh.crypto import EnvelopeError, decrypt, detect_envelope
from xzssh.model import Config, Host, LocalForward, RemoteForward
from xzssh.model import types as model_types

from . import migrations


class ConfigParseError(ValueError):
    pass


def load_config(path: Path) -> Config:
    config, _ = load_config_versioned(path)
    return config


def load_config_versioned(path: Path) -> Tuple[Config, int]:
    """Load a config, returning ``(config, source_version)``.

    ``source_version`` is the schema version found in the file. When it
    is older than ``CURRENT_SCHEMA_VERSION`` the registered migrations
    are applied **in memory only** — the returned config is already
    upgraded (``config.version`` is current), but the file is untouched.
    Persisting the upgrade is the caller's decision; the CLI does it in
    ``load_config_if_exists`` so every command shares one write-back
    path.
    """
    try:
        raw_bytes = path.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigParseError(f"Config file not found: {path}") from exc

    envelope_tool = detect_envelope(raw_bytes)
    if envelope_tool is not None:
        try:
            raw_text = decrypt(raw_bytes, envelope_tool)
        except EnvelopeError as exc:
            raise ConfigParseError(f"Could not decrypt {path}: {exc}") from exc
    else:
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConfigParseError(
                f"Config file is not valid UTF-8: {path}"
            ) from exc

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ConfigParseError(f"Invalid JSON in config file: {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigParseError("Config root must be a JSON object")

    source_version = _coerce_int(data.get("version", 1), "version")
    data = _apply_migrations(data, source_version)

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

    encryption = _optional_str(data, "encryption")
    if envelope_tool is not None:
        # The file's actual state wins over the stored field, so a
        # manually-encrypted config round-trips encrypted.
        encryption = envelope_tool

    event_log = _optional_str(data, "event_log")

    return (
        Config(
            version=version,
            hosts=hosts,
            keys=keys,
            encryption=encryption,
            event_log=event_log,
        ),
        source_version,
    )


def _apply_migrations(data: Dict[str, Any], source_version: int) -> Dict[str, Any]:
    """Upgrade a raw config dict to the current schema, step by step.

    Reads ``CURRENT_SCHEMA_VERSION`` and ``MIGRATIONS`` through their
    modules (not from-imports) so tests can monkeypatch them. The
    ``version`` field is stamped here after each step — migrations
    don't have to remember to do it.
    """
    current = model_types.CURRENT_SCHEMA_VERSION
    if source_version > current:
        raise ConfigParseError(
            f"Config schema v{source_version} is newer than this xzSSH "
            f"understands (v{current}). Upgrade xzSSH to read this file."
        )

    version = source_version
    while version < current:
        migrate = migrations.MIGRATIONS.get(version)
        if migrate is None:
            raise ConfigParseError(
                f"No migration registered for config schema v{version} "
                f"(current is v{current}); cannot upgrade this file"
            )
        data = migrate(data)
        if not isinstance(data, dict):
            raise ConfigParseError(
                f"Migration from schema v{version} did not return an object"
            )
        version += 1
        data["version"] = version
    return data


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
    proxy_jump = _optional_str(data, "proxy_jump")
    forward_agent = _optional_bool(data, "forward_agent", f"hosts[{idx}].forward_agent")
    compression = _optional_bool(data, "compression", f"hosts[{idx}].compression")
    server_alive_interval = _optional_int(data, "server_alive_interval")
    identities_only = _optional_bool(
        data, "identities_only", f"hosts[{idx}].identities_only"
    )
    strict_host_key_checking = _optional_str(data, "strict_host_key_checking")
    user_known_hosts_file = _optional_str(data, "user_known_hosts_file")
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

    remote_forwards_value = data.get("remote_forwards", [])
    if remote_forwards_value is None:
        remote_forwards_value = []
    if not isinstance(remote_forwards_value, list):
        raise ConfigParseError(
            f"hosts[{idx}].remote_forwards must be a list if provided"
        )

    remote_forwards: List[RemoteForward] = []
    for rf_idx, rf_data in enumerate(remote_forwards_value):
        if not isinstance(rf_data, dict):
            raise ConfigParseError(
                f"hosts[{idx}].remote_forwards[{rf_idx}] must be an object"
            )
        remote_forwards.append(_parse_remote_forward(rf_data, idx, rf_idx))

    dynamic_forwards_value = data.get("dynamic_forwards", [])
    if dynamic_forwards_value is None:
        dynamic_forwards_value = []
    if not isinstance(dynamic_forwards_value, list):
        raise ConfigParseError(
            f"hosts[{idx}].dynamic_forwards must be a list if provided"
        )
    dynamic_forwards = [
        _coerce_int(v, f"hosts[{idx}].dynamic_forwards[{df_idx}]")
        for df_idx, v in enumerate(dynamic_forwards_value)
    ]

    options_value = data.get("options", {})
    if options_value is None:
        options_value = {}
    if not isinstance(options_value, dict):
        raise ConfigParseError(
            f"hosts[{idx}].options must be an object if provided"
        )
    options: Dict[str, str] = {}
    for opt_key, opt_val in options_value.items():
        if not isinstance(opt_key, str) or not opt_key.strip():
            raise ConfigParseError(
                f"hosts[{idx}].options keys must be non-empty strings"
            )
        if opt_val is None:
            raise ConfigParseError(
                f"hosts[{idx}].options['{opt_key}'] cannot be null"
            )
        options[opt_key] = str(opt_val)

    return Host(
        alias=alias,
        host_name=host_name,
        user=user,
        port=port,
        identity_file=identity_file,
        proxy_jump=proxy_jump,
        forward_agent=forward_agent,
        compression=compression,
        server_alive_interval=server_alive_interval,
        identities_only=identities_only,
        strict_host_key_checking=strict_host_key_checking,
        user_known_hosts_file=user_known_hosts_file,
        local_forwards=local_forwards,
        remote_forwards=remote_forwards,
        dynamic_forwards=dynamic_forwards,
        tags=tags,
        last_used=last_used,
        options=options,
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


def _parse_remote_forward(
    data: Dict[str, Any], host_idx: int, rf_idx: int
) -> RemoteForward:
    remote_port = _require_int(
        data, "remote_port", f"hosts[{host_idx}].remote_forwards[{rf_idx}].remote_port"
    )
    local_host = _require_str(
        data, "local_host", f"hosts[{host_idx}].remote_forwards[{rf_idx}].local_host"
    )
    local_port = _require_int(
        data, "local_port", f"hosts[{host_idx}].remote_forwards[{rf_idx}].local_port"
    )

    return RemoteForward(
        remote_port=remote_port,
        local_host=local_host,
        local_port=local_port,
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


def _optional_bool(data: Dict[str, Any], key: str, label: str) -> Optional[bool]:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    raise ConfigParseError(f"Field '{label}' must be a boolean (true/false)")


def _coerce_int(value: Any, label: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigParseError(f"Field '{label}' must be an integer") from exc
