from __future__ import annotations

import os
import platform as sys_platform
import stat
from enum import Enum
from pathlib import Path
from typing import Optional


class Platform(str, Enum):
    MACOS = "macos"
    WINDOWS = "windows"
    OTHER = "other"


def detect_platform() -> Platform:
    system = sys_platform.system().lower()
    if system.startswith("win"):
        return Platform.WINDOWS
    if system == "darwin":
        return Platform.MACOS
    return Platform.OTHER


def ssh_dir() -> Path:
    _ = detect_platform()
    return Path.home() / ".ssh"


def default_config_path() -> Path:
    return ssh_dir() / "xzssh.json"


def default_output_path() -> Path:
    return ssh_dir() / "config"


def resolve_path(path_value: str, base_dir: Optional[Path]) -> Path:
    expanded = os.path.expandvars(path_value)
    path = Path(expanded).expanduser()
    if not path.is_absolute() and base_dir is not None:
        path = (base_dir / path).resolve(strict=False)
    return path


def ensure_secure_file_permissions(path: Path) -> Optional[str]:
    try:
        if os.name == "posix":
            os.chmod(path, 0o600)
            return None
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        return (
            "Windows permissions are enforced by ACLs; "
            "ensure this file is restricted to the current user."
        )
    except OSError as exc:
        return f"Unable to set permissions for {path}: {exc}"


def check_private_key_permissions(path: Path) -> Optional[str]:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        return f"Unable to read permissions for key '{path}': {exc}"

    if os.name == "posix":
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return (
                f"permissions are too open: {oct(mode)}. "
                "Consider chmod 600."
            )
    return None
