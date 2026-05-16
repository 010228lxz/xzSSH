from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from xzssh.model import Config, Host, LocalForward
from xzssh.platform import check_private_key_permissions, resolve_path


@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def validate_config(
    config: Config,
    suggest_ports: bool = False,
    source_path: Optional[Path] = None,
) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(config.version, int):
        result.errors.append("config.version must be an integer")

    seen_aliases: Set[str] = set()
    local_port_map: Dict[int, List[str]] = {}
    used_ports: Set[int] = set()

    for idx, host in enumerate(config.hosts):
        _validate_host(
            host,
            idx,
            result,
            seen_aliases,
            local_port_map,
            used_ports,
        )

    _validate_keys(config.keys, result, source_path)

    _validate_local_port_conflicts(
        local_port_map,
        used_ports,
        result,
        suggest_ports=suggest_ports,
    )

    return result


def _validate_host(
    host: Host,
    idx: int,
    result: ValidationResult,
    seen_aliases: Set[str],
    local_port_map: Dict[int, List[str]],
    used_ports: Set[int],
) -> None:
    alias = host.alias
    if not isinstance(alias, str) or not alias.strip():
        result.errors.append(f"hosts[{idx}].alias must be a non-empty string")
    elif alias in seen_aliases:
        result.errors.append(f"Duplicate host alias: {alias}")
    else:
        seen_aliases.add(alias)

    host_name = host.host_name
    if not isinstance(host_name, str) or not host_name.strip():
        result.errors.append(f"hosts[{idx}].host_name must be a non-empty string")

    if host.user is not None and not str(host.user).strip():
        result.errors.append(f"hosts[{idx}].user must be a non-empty string if provided")

    if host.port is not None:
        _validate_port(host.port, f"hosts[{idx}].port", result.errors)

    if host.identity_file is not None and not str(host.identity_file).strip():
        result.errors.append(
            f"hosts[{idx}].identity_file must be a non-empty string if provided"
        )

    host_label = _host_label(host)
    for lf_idx, local_forward in enumerate(host.local_forwards):
        _validate_local_forward(
            local_forward,
            idx,
            lf_idx,
            host_label,
            result,
            local_port_map,
            used_ports,
        )


def _validate_local_forward(
    local_forward: LocalForward,
    host_idx: int,
    lf_idx: int,
    host_label: str,
    result: ValidationResult,
    local_port_map: Dict[int, List[str]],
    used_ports: Set[int],
) -> None:
    _validate_port(
        local_forward.local_port,
        f"hosts[{host_idx}].local_forwards[{lf_idx}].local_port",
        result.errors,
    )
    _validate_port(
        local_forward.remote_port,
        f"hosts[{host_idx}].local_forwards[{lf_idx}].remote_port",
        result.errors,
    )

    if not isinstance(local_forward.remote_host, str) or not local_forward.remote_host.strip():
        result.errors.append(
            f"hosts[{host_idx}].local_forwards[{lf_idx}].remote_host must be a non-empty string"
        )

    if isinstance(local_forward.local_port, int):
        if local_forward.local_port < 1024:
            result.warnings.append(
                "LocalForward port below 1024: "
                f"{local_forward.local_port} on host {host_label}. "
                "Binding may require elevated privileges."
            )
        local_port_map.setdefault(local_forward.local_port, []).append(host_label)
        used_ports.add(local_forward.local_port)


def _validate_local_port_conflicts(
    local_port_map: Dict[int, List[str]],
    used_ports: Set[int],
    result: ValidationResult,
    suggest_ports: bool,
) -> None:
    for port, hosts in sorted(local_port_map.items()):
        if len(hosts) <= 1:
            continue
        host_list = ", ".join(hosts)
        message = (
            f"Duplicate LocalForward port {port} across hosts: {host_list}."
        )
        if suggest_ports:
            suggestion = _suggest_next_free_port(used_ports, port)
            if suggestion is not None:
                message += f" Suggestion: next free port is {suggestion}."
            else:
                message += " Suggestion: no free port available above this value."
        result.errors.append(message)


def _suggest_next_free_port(used_ports: Set[int], start_port: int) -> Optional[int]:
    for candidate in range(start_port + 1, 65536):
        if candidate not in used_ports:
            return candidate
    return None


def _host_label(host: Host) -> str:
    alias = host.alias
    host_name = host.host_name
    if host_name:
        return f"{alias} ({host_name})"
    return alias


def _validate_port(value: int, label: str, errors: List[str]) -> None:
    if not isinstance(value, int):
        errors.append(f"{label} must be an integer")
        return
    if value < 1 or value > 65535:
        errors.append(f"{label} must be between 1 and 65535")


def _validate_keys(
    keys: Dict[str, str],
    result: ValidationResult,
    source_path: Optional[Path],
) -> None:
    for name, path_value in keys.items():
        if not isinstance(name, str) or not name.strip():
            result.errors.append("Key name must be a non-empty string")
            continue
        if not isinstance(path_value, str) or not path_value.strip():
            result.errors.append(f"Key path for '{name}' must be a non-empty string")
            continue

        resolved = _resolve_key_path(path_value, source_path)
        if not resolved.exists():
            result.errors.append(f"Key '{name}' not found at {resolved}")
            continue
        if not resolved.is_file():
            result.errors.append(f"Key '{name}' path is not a file: {resolved}")
            continue

        warning = check_private_key_permissions(resolved)
        if warning:
            result.warnings.append(f"Key '{name}' {warning}")


def _resolve_key_path(path_value: str, source_path: Optional[Path]) -> Path:
    base_dir = source_path.parent if source_path is not None else None
    return resolve_path(path_value, base_dir)
