"""``xzssh scp`` / ``xzssh sftp`` / ``xzssh rsync`` — alias-aware wrappers.

Thin pass-throughs to the real binaries that understand xzSSH aliases:

- Any non-flag token of the form ``<alias>:<path>`` (where ``<alias>``
  is configured) is rewritten to ``user@hostname:<path>``. For sftp, a
  bare ``<alias>`` token is rewritten too (its positional *is* the
  host; for scp/rsync a bare token is a local path and stays
  untouched).
- When exactly **one** distinct alias is referenced, the host's
  connection options are injected: ``-P port -i identity -J jump -o
  Key=Value`` for scp/sftp, ``-e "ssh -p ... -i ..."`` for rsync. With
  several aliases (remote→remote copies) per-host flags would be
  ambiguous, so only the targets are rewritten and per-host options
  are left to the generated ``~/.ssh/config``.
- The wrapped tool's exit code is propagated verbatim.

xzSSH's own flags (``--dry-run``, ``--config``, ...) must come right
after the subcommand — everything after the first unrecognized token
belongs to the wrapped tool. When the tool's *first* argument starts
with a dash, separate it with the standard ``--``::

    xzssh scp -- -r db:/var/log .
    xzssh rsync -- -az db:/data/ backup/
"""
from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from xzssh.cli.helpers import _scalar_ssh_options, load_config_or_error
from xzssh.cli.ui import print_error, print_notice, print_step
from xzssh.model import Host


def run(args: argparse.Namespace, config_path: Path, tool: str) -> int:
    config = load_config_or_error(config_path)
    if config is None:
        return 1

    aliases = {h.alias: h for h in config.hosts}
    tokens: List[str] = list(args.args)
    if tokens and tokens[0] == "--":
        tokens = tokens[1:]

    rewritten: List[str] = []
    used: Dict[str, Host] = {}
    for token in tokens:
        new_token, host = _rewrite_token(token, aliases, tool)
        if host is not None:
            used[host.alias] = host
        rewritten.append(new_token)

    option_args: List[str] = []
    if len(used) == 1:
        (host,) = used.values()
        option_args = _connection_options(host, tool)
    elif len(used) > 1:
        print_notice(
            f"Multiple aliases referenced ({', '.join(sorted(used))}); "
            "per-host options are left to ~/.ssh/config — run "
            "`xzssh generate` if it is stale."
        )
    else:
        print_notice(
            "No configured alias referenced; passing through unchanged."
        )

    argv = [tool] + option_args + rewritten

    if getattr(args, "dry_run", False):
        # Raw to stdout, like `which`: must survive $(...) capture.
        sys.stdout.write(shlex.join(argv) + "\n")
        return 0

    print_step(shlex.join(argv))
    try:
        return subprocess.run(argv).returncode
    except FileNotFoundError:
        print_error(f"'{tool}' not found on PATH.")
        return 127
    except KeyboardInterrupt:
        return 130


def _rewrite_token(
    token: str, aliases: Dict[str, Host], tool: str
) -> Tuple[str, Optional[Host]]:
    if token.startswith("-"):
        return token, None
    # sftp's positional is the host itself.
    if tool == "sftp" and token in aliases:
        host = aliases[token]
        return _target(host), host
    if ":" in token:
        prefix, rest = token.split(":", 1)
        host = aliases.get(prefix)
        if host is not None:
            return f"{_target(host)}:{rest}", host
    return token, None


def _target(host: Host) -> str:
    if host.user:
        return f"{host.user}@{host.host_name}"
    return host.host_name


def _connection_options(host: Host, tool: str) -> List[str]:
    # scp/sftp spell the port flag -P; ssh (inside rsync's -e) uses -p.
    ssh_style: List[str] = []
    if host.port:
        ssh_style.extend(["-p", str(host.port)])
    if host.identity_file:
        ssh_style.extend(["-i", host.identity_file])
    if host.proxy_jump:
        ssh_style.extend(["-J", host.proxy_jump])
    for key, value in _scalar_ssh_options(host):
        ssh_style.extend(["-o", f"{key}={value}"])

    if tool == "rsync":
        if not ssh_style:
            return []
        return ["-e", shlex.join(["ssh"] + ssh_style)]

    options = list(ssh_style)
    if host.port:
        options[options.index("-p")] = "-P"
    return options
