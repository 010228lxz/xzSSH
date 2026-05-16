"""Tests for ``xzssh connect`` exit-code and last_used semantics.

The contract we promise:
- ``last_used`` is updated only when the SSH session actually succeeded.
- OpenSSH returns 255 for connection-setup failures (host unreachable,
  auth failure, etc.). Any other code means we did connect.
- The CLI exit code mirrors SSH's exit code, so shell pipelines like
  ``xzssh connect host && deploy`` behave correctly.
"""
from __future__ import annotations

import json
import types
from pathlib import Path

import pytest

from xzssh.cli.main import main


def _seed_one_host(config_path: Path, alias: str = "db") -> None:
    main(
        [
            "add",
            "--config",
            str(config_path),
            "--alias",
            alias,
            "--host-name",
            f"{alias}.example.com",
        ]
    )


def _patch_subprocess_run(monkeypatch, returncode: int) -> list:
    """Patch ``subprocess.run`` in the connect module and record calls."""
    calls = []

    def fake_run(args, *a, **kw):
        calls.append(args)
        return types.SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run", fake_run
    )
    return calls


def _last_used(config_path: Path, alias: str) -> str | None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    host = next(h for h in data["hosts"] if h["alias"] == alias)
    return host.get("last_used")


def test_connect_success_stamps_last_used_and_returns_zero(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)
    assert _last_used(config_path, "db") is None

    _patch_subprocess_run(monkeypatch, returncode=0)

    exit_code = main(["connect", "--config", str(config_path), "db"])

    assert exit_code == 0
    assert _last_used(config_path, "db") is not None


def test_connect_255_does_not_stamp_last_used(
    monkeypatch, tmp_path: Path
) -> None:
    """255 means OpenSSH couldn't connect — last_used must NOT update."""
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)
    assert _last_used(config_path, "db") is None

    _patch_subprocess_run(monkeypatch, returncode=255)

    exit_code = main(["connect", "--config", str(config_path), "db"])

    assert exit_code == 255
    assert _last_used(config_path, "db") is None


def test_connect_nonzero_nonconnection_error_still_stamps(
    monkeypatch, tmp_path: Path
) -> None:
    """Remote command exiting non-zero (e.g. 130 from Ctrl-C in the remote
    shell) means we did connect — last_used should still update."""
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    _patch_subprocess_run(monkeypatch, returncode=130)

    exit_code = main(["connect", "--config", str(config_path), "db"])

    assert exit_code == 130
    assert _last_used(config_path, "db") is not None


def test_connect_keyboard_interrupt_treated_as_130(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    def fake_run(*args, **kwargs):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run", fake_run
    )

    exit_code = main(["connect", "--config", str(config_path), "db"])

    # 130 is the conventional "terminated by Ctrl-C" exit code; we did
    # technically establish the session by the time the user pressed Ctrl-C,
    # so last_used stamping is fine and exit code mirrors SSH convention.
    assert exit_code == 130
    assert _last_used(config_path, "db") is not None


def test_connect_unknown_alias_errors(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    # Should never even reach subprocess.run
    def fake_run(*args, **kwargs):
        raise AssertionError("subprocess.run should not be called for unknown host")

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run", fake_run
    )

    exit_code = main(["connect", "--config", str(config_path), "ghost"])

    assert exit_code == 1


def test_connect_passes_port_user_and_identity_to_ssh(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    key_path = tmp_path / "id_test"
    key_path.write_text("dummy", encoding="utf-8")

    main(
        [
            "add",
            "--config",
            str(config_path),
            "--alias",
            "db",
            "--host-name",
            "db.example.com",
            "--user",
            "alice",
            "--port",
            "2222",
            "--identity-file",
            str(key_path),
        ]
    )

    calls = _patch_subprocess_run(monkeypatch, returncode=0)

    exit_code = main(["connect", "--config", str(config_path), "db"])
    assert exit_code == 0

    assert len(calls) == 1
    ssh_args = calls[0]
    assert ssh_args[0] == "ssh"
    assert "-p" in ssh_args and "2222" in ssh_args
    assert "-i" in ssh_args and str(key_path) in ssh_args
    assert "alice@db.example.com" in ssh_args
