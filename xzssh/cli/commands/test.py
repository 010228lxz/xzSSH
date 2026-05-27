"""``xzssh test`` — probe connectivity without opening an interactive shell.

Runs ``ssh -o BatchMode=yes -o ConnectTimeout=<n> ... true`` against the
target host and classifies the outcome (reachable / auth-failed / timeout
/ unreachable) by inspecting the SSH process return code and stderr.

Exit codes:
- ``0`` — every probed host was reachable
- ``1`` — at least one host was *not* reachable (auth fail, timeout, etc.)
- ``2`` — bad arguments or unknown alias

``--all`` probes every host in the config in parallel using a small
thread pool, keeping the per-host timeout tight so a single hung host
can't stall the whole run.
"""
from __future__ import annotations

import argparse
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple

from xzssh.cli.helpers import build_ssh_command, load_config_or_error
from xzssh.cli.ui import print_error, print_info, print_success, print_warning
from xzssh.model import Host


# Classification labels for the test outcome. Kept short so the printed
# table stays scannable.
STATUS_REACHABLE = "reachable"
STATUS_AUTH_FAILED = "auth-failed"
STATUS_TIMEOUT = "timeout"
STATUS_UNREACHABLE = "unreachable"
STATUS_SSH_MISSING = "ssh-missing"
STATUS_ERROR = "error"


def _classify(returncode: int, stderr: str) -> str:
    """Map (returncode, stderr) into one of the STATUS_* labels."""
    if returncode == 0:
        return STATUS_REACHABLE

    lowered = stderr.lower()
    if "permission denied" in lowered or "publickey" in lowered:
        return STATUS_AUTH_FAILED
    if "timed out" in lowered or "operation timed out" in lowered:
        return STATUS_TIMEOUT
    if (
        "no route to host" in lowered
        or "connection refused" in lowered
        or "could not resolve" in lowered
        or "name or service not known" in lowered
        or "host is down" in lowered
    ):
        return STATUS_UNREACHABLE
    return STATUS_ERROR


def _probe(host: Host, timeout: int) -> Tuple[str, int, str]:
    """Probe *host*. Returns (alias, returncode, status_label)."""
    extra = [
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=accept-new",
    ]
    cmd = build_ssh_command(host, extra_options=extra) + ["true"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout + 2,
        )
    except subprocess.TimeoutExpired:
        return (host.alias, 124, STATUS_TIMEOUT)
    except FileNotFoundError:
        return (host.alias, 127, STATUS_SSH_MISSING)

    stderr = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
    return (host.alias, result.returncode, _classify(result.returncode, stderr))


def _report(alias: str, returncode: int, status: str) -> bool:
    """Pretty-print a single result. Returns True iff the host was reachable."""
    if status == STATUS_REACHABLE:
        print_success(f"{alias}: reachable")
        return True
    if status == STATUS_AUTH_FAILED:
        print_warning(
            f"{alias}: auth-failed (host reachable but credentials rejected)"
        )
    elif status == STATUS_TIMEOUT:
        print_error(f"{alias}: timeout")
    elif status == STATUS_UNREACHABLE:
        print_error(f"{alias}: unreachable")
    elif status == STATUS_SSH_MISSING:
        print_error(f"{alias}: ssh executable not found in PATH")
    else:
        print_error(f"{alias}: error (rc={returncode})")
    return False


def run(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 2

    timeout = max(1, int(getattr(args, "timeout", 5)))

    if getattr(args, "all", False):
        targets: List[Host] = list(config.hosts)
        if not targets:
            print_error("No hosts configured.")
            return 1
        print_info(f"Probing {len(targets)} host(s) (timeout={timeout}s)...")
    else:
        if not args.alias:
            print_error("No alias provided. Pass an alias or use --all.")
            return 2
        host = next((h for h in config.hosts if h.alias == args.alias), None)
        if host is None:
            print_error(f"Unknown alias: {args.alias}")
            return 2
        targets = [host]

    # Sequential when single, threaded for --all.  Parallelism is capped so
    # 50-host configs don't fan out to 50 simultaneous ssh processes.
    results: List[Tuple[str, int, str]] = []
    if len(targets) == 1:
        results.append(_probe(targets[0], timeout))
    else:
        max_workers = min(8, len(targets))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_probe, h, timeout) for h in targets]
            for future in as_completed(futures):
                results.append(future.result())

    # Stable alphabetical output regardless of completion order.
    results.sort(key=lambda r: r[0])
    all_reachable = True
    for alias, returncode, status in results:
        ok = _report(alias, returncode, status)
        all_reachable = all_reachable and ok

    return 0 if all_reachable else 1
