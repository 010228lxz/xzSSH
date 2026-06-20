from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from xzssh.model import Config, Host, LocalForward
from xzssh.platform import check_private_key_permissions, resolve_path


# Accepted values for ssh's StrictHostKeyChecking (includes `off`, an alias
# for `no`, which ssh itself accepts).
STRICT_HOST_KEY_CHECKING_VALUES = {"yes", "no", "ask", "accept-new", "off"}


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

    if config.encryption is not None and config.encryption not in (
        "gpg",
        "age",
    ):
        result.errors.append(
            "config.encryption must be 'gpg' or 'age' if provided"
        )

    seen_aliases: Set[str] = set()
    # Client-side binds (LocalForward.local_port + DynamicForward) share one
    # local-port namespace, so they are checked together across every host.
    # Each entry is (host_label, forward_kind) for an accurate message.
    local_bind_map: Dict[int, List[Tuple[str, str]]] = {}
    used_ports: Set[int] = set()
    # RemoteForward binds on the *server*, so a port collision is only real
    # among forwards landing on the same host_name — keyed accordingly.
    remote_bind_map: Dict[Tuple[str, int], List[str]] = {}

    for idx, host in enumerate(config.hosts):
        _validate_host(
            host,
            idx,
            result,
            seen_aliases,
            local_bind_map,
            used_ports,
            remote_bind_map,
        )

    # ProxyJump references can only be resolved after every host has been
    # seen — a bastion may be declared after the host that jumps through it.
    _validate_proxy_jump_references(config.hosts, seen_aliases, result)

    _validate_keys(config.keys, result, source_path)

    _validate_local_bind_conflicts(
        local_bind_map,
        used_ports,
        result,
        suggest_ports=suggest_ports,
    )
    _validate_remote_bind_conflicts(remote_bind_map, result)

    return result


def _validate_host(
    host: Host,
    idx: int,
    result: ValidationResult,
    seen_aliases: Set[str],
    local_bind_map: Dict[int, List[Tuple[str, str]]],
    used_ports: Set[int],
    remote_bind_map: Dict[Tuple[str, int], List[str]],
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

    if host.proxy_jump is not None and not str(host.proxy_jump).strip():
        result.errors.append(
            f"hosts[{idx}].proxy_jump must be a non-empty string if provided"
        )

    if host.server_alive_interval is not None:
        if (
            not isinstance(host.server_alive_interval, int)
            or host.server_alive_interval < 0
        ):
            result.errors.append(
                f"hosts[{idx}].server_alive_interval must be a non-negative integer"
            )

    if host.strict_host_key_checking is not None:
        if host.strict_host_key_checking not in STRICT_HOST_KEY_CHECKING_VALUES:
            allowed = ", ".join(sorted(STRICT_HOST_KEY_CHECKING_VALUES))
            result.errors.append(
                f"hosts[{idx}].strict_host_key_checking must be one of: {allowed}"
            )

    host_label = _host_label(host)
    for lf_idx, local_forward in enumerate(host.local_forwards):
        _validate_local_forward(
            local_forward,
            idx,
            lf_idx,
            host_label,
            result,
            local_bind_map,
            used_ports,
        )

    for rf_idx, remote_forward in enumerate(host.remote_forwards):
        _validate_port(
            remote_forward.remote_port,
            f"hosts[{idx}].remote_forwards[{rf_idx}].remote_port",
            result.errors,
        )
        _validate_port(
            remote_forward.local_port,
            f"hosts[{idx}].remote_forwards[{rf_idx}].local_port",
            result.errors,
        )
        if (
            not isinstance(remote_forward.local_host, str)
            or not remote_forward.local_host.strip()
        ):
            result.errors.append(
                f"hosts[{idx}].remote_forwards[{rf_idx}].local_host "
                "must be a non-empty string"
            )
        # The bind is on the remote server, so collisions are tracked
        # per host_name, not across the whole config.
        if isinstance(remote_forward.remote_port, int) and isinstance(
            host.host_name, str
        ) and host.host_name.strip():
            remote_bind_map.setdefault(
                (host.host_name, remote_forward.remote_port), []
            ).append(host_label)

    for df_idx, dynamic_port in enumerate(host.dynamic_forwards):
        _validate_port(
            dynamic_port,
            f"hosts[{idx}].dynamic_forwards[{df_idx}]",
            result.errors,
        )
        if isinstance(dynamic_port, int):
            if dynamic_port < 1024:
                result.warnings.append(
                    "DynamicForward port below 1024: "
                    f"{dynamic_port} on host {host_label}. "
                    "Binding may require elevated privileges."
                )
            local_bind_map.setdefault(dynamic_port, []).append(
                (host_label, "DynamicForward")
            )
            used_ports.add(dynamic_port)


def _validate_local_forward(
    local_forward: LocalForward,
    host_idx: int,
    lf_idx: int,
    host_label: str,
    result: ValidationResult,
    local_bind_map: Dict[int, List[Tuple[str, str]]],
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
        local_bind_map.setdefault(local_forward.local_port, []).append(
            (host_label, "LocalForward")
        )
        used_ports.add(local_forward.local_port)


def _validate_proxy_jump_references(
    hosts: List[Host],
    seen_aliases: Set[str],
    result: ValidationResult,
) -> None:
    """Surface dangling ProxyJump references as errors.

    A host that declares ``proxy_jump = "bastion"`` must reference an
    alias that exists elsewhere in the config — otherwise ``ssh`` will
    fail at connect time with a confusing "No such host" message. We
    catch the typo here instead.
    """
    for host in hosts:
        target = host.proxy_jump
        if target is None or not target.strip():
            continue
        # Whitespace-tolerant: "bastion " is the same alias as "bastion".
        target = target.strip()
        if target == host.alias:
            result.errors.append(
                f"Host '{host.alias}' has proxy_jump pointing at itself"
            )
            continue
        if target not in seen_aliases:
            result.errors.append(
                f"Host '{host.alias}' references unknown ProxyJump alias "
                f"'{target}' — declare that host first or remove the reference"
            )


def _validate_local_bind_conflicts(
    local_bind_map: Dict[int, List[Tuple[str, str]]],
    used_ports: Set[int],
    result: ValidationResult,
    suggest_ports: bool,
) -> None:
    for port, entries in sorted(local_bind_map.items()):
        if len(entries) <= 1:
            continue
        kinds = {kind for _, kind in entries}
        # Keep the original wording when only LocalForwards collide; spell
        # out the forward kinds once a DynamicForward enters the mix (both
        # contend for the same local port).
        if kinds == {"LocalForward"}:
            who = ", ".join(label for label, _ in entries)
            message = f"Duplicate LocalForward port {port} across hosts: {who}."
        else:
            who = ", ".join(f"{label} [{kind}]" for label, kind in entries)
            message = f"Duplicate local bind port {port} across forwards: {who}."
        if suggest_ports:
            suggestion = _suggest_next_free_port(used_ports, port)
            if suggestion is not None:
                message += f" Suggestion: next free port is {suggestion}."
            else:
                message += " Suggestion: no free port available above this value."
        result.errors.append(message)


def _validate_remote_bind_conflicts(
    remote_bind_map: Dict[Tuple[str, int], List[str]],
    result: ValidationResult,
) -> None:
    for (host_name, port), labels in sorted(remote_bind_map.items()):
        if len(labels) <= 1:
            continue
        who = ", ".join(labels)
        result.errors.append(
            f"Duplicate RemoteForward remote port {port} on server "
            f"'{host_name}' across hosts: {who}."
        )


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
