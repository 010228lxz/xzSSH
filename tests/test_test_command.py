"""Tests for ``xzssh test`` — the connectivity probe.

We monkeypatch ``subprocess.run`` to fake SSH outcomes (returncode +
stderr) and verify that:

- the probe builds a BatchMode + ConnectTimeout command line
- (returncode, stderr) is classified into reachable / auth-failed /
  timeout / unreachable
- exit code 0 means every host reached, 1 means at least one didn't,
  2 means a usage / unknown-alias error
- ``--all`` probes every host
"""
from __future__ import annotations

import types
from pathlib import Path
from typing import List, Tuple

import pytest

from xzssh.cli.main import main


def _seed_one_host(config_path: Path, alias: str = "db") -> None:
    main(
        [
            "add",
            "--config", str(config_path),
            "--alias", alias,
            "--host-name", f"{alias}.example.com",
        ]
    )


def _seed_two_hosts(config_path: Path) -> None:
    for alias in ("db", "web"):
        main(
            [
                "add",
                "--config", str(config_path),
                "--alias", alias,
                "--host-name", f"{alias}.example.com",
            ]
        )


class FakeCompleted:
    def __init__(self, returncode: int, stderr: bytes = b"") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = b""


def _patch_subprocess(monkeypatch, factory) -> List[List[str]]:
    """Patch subprocess.run in the test module.

    *factory* receives the ssh argv and returns a FakeCompleted (or raises
    TimeoutExpired / FileNotFoundError).  Returns a list that records every
    argv the patched function saw.
    """
    calls: List[List[str]] = []

    def fake_run(args, *a, **kw):
        calls.append(list(args))
        return factory(args)

    monkeypatch.setattr("xzssh.cli.commands.test.subprocess.run", fake_run)
    return calls


def _both_streams(capsys) -> str:
    """Return stdout + stderr combined.

    ``print_success`` goes to stdout while ``print_warning`` and
    ``print_error`` go to stderr — and we don't care which stream the
    label landed on, only that the right label was emitted.
    """
    captured = capsys.readouterr()
    return captured.out + captured.err


# ---------------------------------------------------------------------------
# Single-host happy and sad paths
# ---------------------------------------------------------------------------

def test_test_reachable_returns_zero(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    _patch_subprocess(monkeypatch, lambda _: FakeCompleted(0))
    exit_code = main(["test", "--config", str(config_path), "db"])

    assert exit_code == 0
    assert "reachable" in _both_streams(capsys)


def test_test_auth_failed_returns_one(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    _patch_subprocess(
        monkeypatch,
        lambda _: FakeCompleted(255, b"db.example.com: Permission denied (publickey)."),
    )

    exit_code = main(["test", "--config", str(config_path), "db"])

    assert exit_code == 1
    assert "auth-failed" in _both_streams(capsys)


def test_test_timeout_returns_one(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    import subprocess as _subprocess

    def fake_run(args, *a, **kw):
        raise _subprocess.TimeoutExpired(cmd=args, timeout=kw.get("timeout", 5))

    monkeypatch.setattr("xzssh.cli.commands.test.subprocess.run", fake_run)

    exit_code = main(["test", "--config", str(config_path), "db"])

    assert exit_code == 1
    assert "timeout" in _both_streams(capsys)


def test_test_unreachable_returns_one(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    _patch_subprocess(
        monkeypatch,
        lambda _: FakeCompleted(255, b"ssh: connect to host db.example.com port 22: Connection refused"),
    )

    exit_code = main(["test", "--config", str(config_path), "db"])

    assert exit_code == 1
    assert "unreachable" in _both_streams(capsys)


# ---------------------------------------------------------------------------
# Argument handling
# ---------------------------------------------------------------------------

def test_test_unknown_alias_returns_two(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    # subprocess.run must never be called for an unknown alias.
    def fail(*a, **kw):
        raise AssertionError("subprocess.run must not be called for unknown alias")

    monkeypatch.setattr("xzssh.cli.commands.test.subprocess.run", fail)

    assert main(["test", "--config", str(config_path), "ghost"]) == 2


def test_test_no_args_returns_two(tmp_path: Path) -> None:
    """No alias and no --all is a usage error."""
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    assert main(["test", "--config", str(config_path)]) == 2


def test_test_passes_batchmode_and_timeout_flags(
    monkeypatch, tmp_path: Path
) -> None:
    """The probe must use BatchMode and a tight ConnectTimeout."""
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    calls = _patch_subprocess(monkeypatch, lambda _: FakeCompleted(0))
    main(["test", "--config", str(config_path), "--timeout", "3", "db"])

    assert len(calls) == 1
    argv = calls[0]
    assert "ssh" == argv[0]
    # BatchMode=yes must be set so ssh never prompts for a password.
    assert "BatchMode=yes" in argv
    # ConnectTimeout must reflect the --timeout flag.
    assert "ConnectTimeout=3" in argv
    # The last token must be the trivial command we ask the remote to run.
    assert argv[-1] == "true"


# ---------------------------------------------------------------------------
# --all probes every host
# ---------------------------------------------------------------------------

def test_test_all_probes_every_host(monkeypatch, tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)

    calls = _patch_subprocess(monkeypatch, lambda _: FakeCompleted(0))
    exit_code = main(["test", "--config", str(config_path), "--all"])

    assert exit_code == 0
    # Two hosts probed → two ssh invocations.
    assert len(calls) == 2
    out = _both_streams(capsys)
    assert "db" in out and "web" in out


def test_test_all_returns_one_when_any_host_fails(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_two_hosts(config_path)

    def per_host(argv: List[str]) -> FakeCompleted:
        # Find the host alias by looking at the last argument (target).
        if "db" in argv[-2] if len(argv) >= 2 else False:
            return FakeCompleted(0)
        if any("db.example.com" in tok for tok in argv):
            return FakeCompleted(0)
        return FakeCompleted(255, b"Connection refused")

    _patch_subprocess(monkeypatch, per_host)
    exit_code = main(["test", "--config", str(config_path), "--all"])

    assert exit_code == 1


def test_test_all_no_hosts_returns_one(tmp_path: Path) -> None:
    """--all on an empty config exits 1, not 0."""
    config_path = tmp_path / "xzssh.json"
    # Create a minimal empty config rather than seeding hosts.
    config_path.write_text(
        '{"version": 1, "hosts": [], "keys": {}}\n', encoding="utf-8"
    )

    assert main(["test", "--config", str(config_path), "--all"]) == 1
