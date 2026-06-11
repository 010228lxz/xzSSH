"""Cross-platform process liveness and termination.

Used by ``xzssh tunnel`` to track detached ``ssh -N`` processes.

The POSIX idiom ``os.kill(pid, 0)`` must NEVER be used on Windows:
there, any signal number other than CTRL_C_EVENT / CTRL_BREAK_EVENT is
passed to ``TerminateProcess`` — a "liveness check" that kills the
process. The Windows path goes through OpenProcess instead.
"""
from __future__ import annotations

import os
import signal


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "posix":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True  # exists, just not ours to signal
        except OSError:
            return False
        return True
    return _windows_pid_alive(pid)


def _windows_pid_alive(pid: int) -> bool:
    import ctypes
    import ctypes.wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def terminate_pid(pid: int) -> bool:
    """Politely stop *pid* (SIGTERM; hard TerminateProcess on Windows).

    Returns False when the process was already gone or isn't ours.
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    return True
