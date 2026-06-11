"""``xzssh tunnel`` — open a host's port-forwards without a shell.

Subcommands (nested like ``key``, so ``list``/``stop`` can never
collide with a host alias):

- ``start <alias>`` — run ``ssh -N`` in the foreground with the host's
  LocalForward / RemoteForward / DynamicForward rules as ``-L``/``-R``/
  ``-D`` flags. Ctrl-C is the expected way to stop and exits 0.
- ``start <alias> --detach`` — spawn ssh in its own session, record the
  pid in the tunnel state file, and return. stderr goes to a per-alias
  log next to the state file so early failures are diagnosable.
- ``list`` — show recorded tunnels with liveness; dead records are
  pruned.
- ``stop <alias> | --all`` — SIGTERM the recorded pid(s) and forget
  them.

The forwards are passed explicitly on the command line (not via the
generated ``~/.ssh/config``) so the tunnel works even when the config
was never generated or is stale. ``ExitOnForwardFailure=yes`` is always
set: a tunnel whose forwards failed to bind is worse than a failed
command.

Deliberately NOT ``ssh -f``: ssh's own daemonization forks a child
whose pid we can't learn, which would make ``tunnel stop`` impossible.
``Popen`` + own session gives the same detachment with a known pid.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from xzssh.cli.helpers import build_ssh_command, load_config_or_error
from xzssh.cli.tunnels import (
    TunnelRecord,
    load_state,
    save_state,
    state_path,
)
from xzssh.cli.ui import (
    print_error,
    print_info,
    print_step,
    print_success,
    print_tunnel_table,
)
from xzssh.model import Host
from xzssh.platform import pid_alive, terminate_pid

# Grace period before declaring a detached ssh "started" — long enough
# to catch immediate failures (unknown host, port already bound), short
# enough not to be annoying. Tests shrink it.
_STARTUP_GRACE_SECONDS = 0.5


def run(args: argparse.Namespace, config_path: Path) -> int:
    command = args.tunnel_command
    if command == "start":
        return _start(args, config_path)
    if command == "list":
        return _list()
    if command == "stop":
        return _stop(args)
    print_error(f"Unknown tunnel command: {command}")
    return 2


def _forward_descriptions(host: Host) -> List[str]:
    described: List[str] = []
    for lf in host.local_forwards:
        described.append(
            f"L {lf.local_port} → {lf.remote_host}:{lf.remote_port}"
        )
    for rf in host.remote_forwards:
        described.append(
            f"R {rf.remote_port} → {rf.local_host}:{rf.local_port}"
        )
    for dp in host.dynamic_forwards:
        described.append(f"D {dp} (SOCKS)")
    return described


def build_tunnel_command(host: Host) -> List[str]:
    """The ``ssh -N`` argv for *host*'s forwards.

    Forwards are injected as flags here — unlike connect/which/test,
    where they deliberately stay in the generated config — because for
    a tunnel the forwards ARE the command.
    """
    extra: List[str] = ["-N", "-o", "ExitOnForwardFailure=yes"]
    for lf in host.local_forwards:
        extra.extend(["-L", f"{lf.local_port}:{lf.remote_host}:{lf.remote_port}"])
    for rf in host.remote_forwards:
        extra.extend(["-R", f"{rf.remote_port}:{rf.local_host}:{rf.local_port}"])
    for dp in host.dynamic_forwards:
        extra.extend(["-D", str(dp)])
    return build_ssh_command(host, extra_options=extra)


def _start(args: argparse.Namespace, config_path: Path) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    host = next((h for h in config.hosts if h.alias == args.alias), None)
    if host is None:
        print_error(f"Host not found: {args.alias}")
        return 1

    forwards = _forward_descriptions(host)
    if not forwards:
        print_error(
            f"Host '{host.alias}' has no forwards configured — a tunnel "
            "would do nothing. Add local_forwards / remote_forwards / "
            f"dynamic_forwards first (e.g. `xzssh edit {host.alias}`)."
        )
        return 2

    ssh_args = build_tunnel_command(host)

    if getattr(args, "detach", False):
        return _start_detached(host, ssh_args, forwards)

    print_info(
        f"Opening tunnel to [bold]{host.alias}[/bold] "
        f"({len(forwards)} forward(s)). Press Ctrl-C to stop."
    )
    for description in forwards:
        print_step(description)

    try:
        returncode = subprocess.run(ssh_args).returncode
    except KeyboardInterrupt:
        # Ctrl-C is the documented way to close a foreground tunnel.
        print_info("Tunnel closed.")
        return 0
    if returncode != 0:
        print_error(f"ssh exited with code {returncode}.")
    return returncode


def _start_detached(
    host: Host, ssh_args: List[str], forwards: List[str]
) -> int:
    records = load_state(state_path())

    existing = next((r for r in records if r.alias == host.alias), None)
    if existing is not None:
        if pid_alive(existing.pid):
            print_error(
                f"A tunnel for '{host.alias}' is already running "
                f"(pid {existing.pid}). Stop it first: "
                f"`xzssh tunnel stop {host.alias}`."
            )
            return 1
        records.remove(existing)  # stale record from a dead process

    log_file = state_path().parent / f"tunnel-{host.alias}.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    popen_kwargs = {}
    if sys.platform == "win32":
        DETACHED_PROCESS = 0x00000008
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        popen_kwargs["creationflags"] = (
            DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        )
    else:
        popen_kwargs["start_new_session"] = True

    try:
        with open(log_file, "ab") as log:
            proc = subprocess.Popen(
                ssh_args,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                **popen_kwargs,
            )
    except OSError as exc:
        print_error(f"Could not start ssh: {exc}")
        return 1

    # Catch instant failures (unknown host, forward port already bound)
    # instead of reporting a tunnel that died before we returned.
    time.sleep(_STARTUP_GRACE_SECONDS)
    early_exit = proc.poll()
    if early_exit is not None:
        print_error(
            f"Tunnel to '{host.alias}' exited immediately "
            f"(ssh exit code {early_exit}). See {log_file} for details."
        )
        return 1

    records.append(
        TunnelRecord(
            alias=host.alias,
            pid=proc.pid,
            started_at=datetime.now().isoformat(),
            forwards=forwards,
            log_file=str(log_file),
        )
    )
    save_state(state_path(), records)

    print_success(
        f"Tunnel to '{host.alias}' running in the background "
        f"(pid {proc.pid})."
    )
    print_info(f"Stop it with `xzssh tunnel stop {host.alias}`.")
    return 0


def _list() -> int:
    records = load_state(state_path())
    rows = [
        (r.alias, r.pid, pid_alive(r.pid), r.started_at, r.forwards)
        for r in records
    ]
    print_tunnel_table(rows)

    live = [r for r in records if pid_alive(r.pid)]
    if len(live) != len(records):
        save_state(state_path(), live)  # prune dead records
    return 0


def _stop(args: argparse.Namespace) -> int:
    records = load_state(state_path())

    if getattr(args, "all", False):
        targets = list(records)
        if not targets:
            print_info("No tunnels recorded.")
            return 0
    else:
        if not args.alias:
            print_error("Pass an alias or --all.")
            return 2
        target = next((r for r in records if r.alias == args.alias), None)
        if target is None:
            print_error(
                f"No tunnel recorded for '{args.alias}'. "
                "See `xzssh tunnel list`."
            )
            return 1
        targets = [target]

    for record in targets:
        if terminate_pid(record.pid):
            print_success(
                f"Tunnel to '{record.alias}' stopped (pid {record.pid})."
            )
        else:
            print_info(
                f"Tunnel to '{record.alias}' (pid {record.pid}) was not "
                "running; record cleaned up."
            )
        records.remove(record)

    save_state(state_path(), records)
    return 0
