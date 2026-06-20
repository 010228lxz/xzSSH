"""Tests for ``xzssh tunnel`` (start / start --detach / list / stop).

No real ssh is ever spawned: subprocess.run / subprocess.Popen are
monkeypatched, and liveness checks are stubbed per-pid. The autouse
fixture in conftest.py points XZSSH_TUNNELS_FILE at a tmp state file.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

import xzssh.cli.commands.tunnel as tunnel_cmd
from xzssh.cli.main import main
from xzssh.cli.tunnels import TunnelRecord, load_state, save_state, state_path
from xzssh.model import Host, LocalForward, RemoteForward

# Captured before the autouse fixture stubs the module attribute, so the
# unit test below can exercise the genuine implementation.
_REAL_BUSY_LOCAL_PORTS = tunnel_cmd._busy_local_ports


def _seed_forward_host(config_path: Path) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", "db", "--host-name", "db.example.com",
         "--user", "alice", "--port", "2222",
         "--local-forward", "8080:localhost:80",
         "--remote-forward", "9090:localhost:3000",
         "--dynamic-forward", "1080"]
    )


def _seed_plain_host(config_path: Path) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", "plain", "--host-name", "plain.example.com"]
    )


@pytest.fixture(autouse=True)
def _ports_free(monkeypatch):
    """The local-port pre-check passes by default so spawn tests are
    deterministic regardless of what's bound on the host running them; the
    pre-check tests override this seam explicitly."""
    monkeypatch.setattr(tunnel_cmd, "_busy_local_ports", lambda host: [])


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------

def test_build_tunnel_command_argv() -> None:
    host = Host(
        alias="db",
        host_name="db.example.com",
        user="alice",
        port=2222,
        local_forwards=[LocalForward(8080, "localhost", 80)],
        remote_forwards=[RemoteForward(9090, "localhost", 3000)],
        dynamic_forwards=[1080],
    )
    argv = tunnel_cmd.build_tunnel_command(host)

    assert argv[0] == "ssh"
    assert "-N" in argv
    # A tunnel whose forwards failed to bind must die, not linger.
    assert "ExitOnForwardFailure=yes" in argv
    assert argv[argv.index("-L") + 1] == "8080:localhost:80"
    assert argv[argv.index("-R") + 1] == "9090:localhost:3000"
    assert argv[argv.index("-D") + 1] == "1080"
    assert argv[-1] == "alice@db.example.com"
    assert argv[argv.index("-p") + 1] == "2222"


# ---------------------------------------------------------------------------
# start (foreground)
# ---------------------------------------------------------------------------

def test_start_foreground_runs_ssh(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)

    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = args
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tunnel_cmd.subprocess, "run", fake_run)

    rc = main(["tunnel", "start", "db", "--config", str(config_path)])
    assert rc == 0
    assert "-N" in captured["args"]


def test_start_foreground_propagates_ssh_exit_code(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    monkeypatch.setattr(
        tunnel_cmd.subprocess,
        "run",
        lambda args, **kw: SimpleNamespace(returncode=255),
    )
    assert main(["tunnel", "start", "db", "--config", str(config_path)]) == 255


def test_start_ctrl_c_is_a_clean_stop(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)

    def fake_run(args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(tunnel_cmd.subprocess, "run", fake_run)
    assert main(["tunnel", "start", "db", "--config", str(config_path)]) == 0


def test_start_without_forwards_is_usage_error(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_plain_host(config_path)

    def boom(args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("ssh must not be spawned for a forward-less host")

    monkeypatch.setattr(tunnel_cmd.subprocess, "run", boom)
    monkeypatch.setattr(tunnel_cmd.subprocess, "Popen", boom)

    assert main(["tunnel", "start", "plain", "--config", str(config_path)]) == 2


def test_start_unknown_alias(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    assert main(["tunnel", "start", "ghost", "--config", str(config_path)]) == 1


# ---------------------------------------------------------------------------
# start --detach
# ---------------------------------------------------------------------------

class FakeProc:
    def __init__(self, pid: int, exit_code=None):
        self.pid = pid
        self._exit_code = exit_code

    def poll(self):
        return self._exit_code


def test_detach_records_state(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)

    monkeypatch.setattr(tunnel_cmd, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(
        tunnel_cmd.subprocess, "Popen", lambda *a, **kw: FakeProc(4242)
    )

    rc = main(["tunnel", "start", "db", "--detach", "--config", str(config_path)])
    assert rc == 0

    records = load_state(state_path())
    assert len(records) == 1
    assert records[0].alias == "db"
    assert records[0].pid == 4242
    assert any("8080" in f for f in records[0].forwards)
    # The log file rides along for post-mortems.
    assert records[0].log_file and Path(records[0].log_file).exists()


def test_detach_refuses_second_tunnel_while_alive(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)

    monkeypatch.setattr(tunnel_cmd, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(
        tunnel_cmd.subprocess, "Popen", lambda *a, **kw: FakeProc(4242)
    )
    monkeypatch.setattr(tunnel_cmd, "pid_alive", lambda pid: True)

    assert main(["tunnel", "start", "db", "--detach", "--config", str(config_path)]) == 0
    assert main(["tunnel", "start", "db", "--detach", "--config", str(config_path)]) == 1
    assert len(load_state(state_path())) == 1


def test_detach_replaces_stale_record(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    save_state(
        state_path(),
        [TunnelRecord(alias="db", pid=999999, started_at="then")],
    )

    monkeypatch.setattr(tunnel_cmd, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(
        tunnel_cmd.subprocess, "Popen", lambda *a, **kw: FakeProc(4242)
    )
    monkeypatch.setattr(tunnel_cmd, "pid_alive", lambda pid: pid == 4242)

    rc = main(["tunnel", "start", "db", "--detach", "--config", str(config_path)])
    assert rc == 0
    records = load_state(state_path())
    assert [r.pid for r in records] == [4242]


def test_detach_detects_instant_death(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)

    monkeypatch.setattr(tunnel_cmd, "_STARTUP_GRACE_SECONDS", 0)
    monkeypatch.setattr(
        tunnel_cmd.subprocess,
        "Popen",
        lambda *a, **kw: FakeProc(4242, exit_code=255),
    )

    rc = main(["tunnel", "start", "db", "--detach", "--config", str(config_path)])
    assert rc == 1
    # A dead-on-arrival tunnel must not be recorded.
    assert load_state(state_path()) == []


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_list_shows_and_prunes(tmp_path: Path, monkeypatch, capsys) -> None:
    save_state(
        state_path(),
        [
            TunnelRecord(alias="up", pid=111, started_at="now",
                         forwards=["L 8080 → localhost:80"]),
            TunnelRecord(alias="down", pid=222, started_at="then"),
        ],
    )
    monkeypatch.setattr(tunnel_cmd, "pid_alive", lambda pid: pid == 111)
    capsys.readouterr()

    rc = main(["tunnel", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "up" in out
    assert "down" in out  # shown once, with dead status...

    # ...then pruned from the state file.
    assert [r.alias for r in load_state(state_path())] == ["up"]


def test_list_empty_state(capsys) -> None:
    rc = main(["tunnel", "list"])
    assert rc == 0
    assert "No tunnels recorded" in capsys.readouterr().out


def test_corrupt_state_is_treated_as_empty(capsys) -> None:
    state_file = Path(os.environ["XZSSH_TUNNELS_FILE"])
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text("{ corrupt", encoding="utf-8")

    rc = main(["tunnel", "list"])
    assert rc == 0
    assert "No tunnels recorded" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

def test_stop_terminates_and_forgets(monkeypatch) -> None:
    save_state(
        state_path(), [TunnelRecord(alias="db", pid=4242, started_at="now")]
    )
    killed = []
    monkeypatch.setattr(
        tunnel_cmd, "terminate_pid", lambda pid: killed.append(pid) or True
    )

    rc = main(["tunnel", "stop", "db"])
    assert rc == 0
    assert killed == [4242]
    assert load_state(state_path()) == []


def test_stop_unknown_alias() -> None:
    assert main(["tunnel", "stop", "ghost"]) == 1


def test_stop_without_alias_or_all_is_usage_error() -> None:
    assert main(["tunnel", "stop"]) == 2


def test_stop_all(monkeypatch) -> None:
    save_state(
        state_path(),
        [
            TunnelRecord(alias="a", pid=1, started_at="now"),
            TunnelRecord(alias="b", pid=2, started_at="now"),
        ],
    )
    killed = []
    monkeypatch.setattr(
        tunnel_cmd, "terminate_pid", lambda pid: killed.append(pid) or True
    )

    rc = main(["tunnel", "stop", "--all"])
    assert rc == 0
    assert sorted(killed) == [1, 2]
    assert load_state(state_path()) == []


def test_stop_dead_pid_still_cleans_up(monkeypatch) -> None:
    save_state(
        state_path(), [TunnelRecord(alias="db", pid=4242, started_at="now")]
    )
    monkeypatch.setattr(tunnel_cmd, "terminate_pid", lambda pid: False)

    rc = main(["tunnel", "stop", "db"])
    assert rc == 0
    assert load_state(state_path()) == []


# ---------------------------------------------------------------------------
# state round-trip
# ---------------------------------------------------------------------------

def test_state_roundtrip() -> None:
    records = [
        TunnelRecord(
            alias="db", pid=1, started_at="t", forwards=["L 1 → h:2"],
            log_file="/tmp/x.log",
        )
    ]
    save_state(state_path(), records)
    data = json.loads(state_path().read_text(encoding="utf-8"))
    assert data["tunnels"][0]["alias"] == "db"
    assert load_state(state_path()) == records


# ---------------------------------------------------------------------------
# local-port pre-check
# ---------------------------------------------------------------------------

def test_start_aborts_when_local_port_in_use(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)

    # Pretend 8080 (the host's local_forward port) is taken.
    monkeypatch.setattr(tunnel_cmd, "_busy_local_ports", lambda host: [8080])

    def boom(*args, **kwargs):
        raise AssertionError("ssh must not be spawned when a port is busy")

    monkeypatch.setattr(tunnel_cmd.subprocess, "run", boom)
    monkeypatch.setattr(tunnel_cmd.subprocess, "Popen", boom)

    rc = main(["tunnel", "start", "db", "--config", str(config_path)])
    assert rc == 1


def test_start_detached_aborts_when_local_port_in_use(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    monkeypatch.setattr(tunnel_cmd, "_busy_local_ports", lambda host: [1080])

    def boom(*args, **kwargs):
        raise AssertionError("ssh must not be spawned when a port is busy")

    monkeypatch.setattr(tunnel_cmd.subprocess, "Popen", boom)

    rc = main(["tunnel", "start", "db", "--detach", "--config", str(config_path)])
    assert rc == 1
    # No tunnel should have been recorded.
    assert load_state(state_path()) == []


def test_port_in_use_detects_a_bound_socket() -> None:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))  # OS picks a free port
        srv.listen(1)
        bound_port = srv.getsockname()[1]
        # The real function (not the autouse stub) sees the live bind.
        assert tunnel_cmd._port_in_use(bound_port) is True

    # Once released, a fresh ephemeral port is free again.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    assert tunnel_cmd._port_in_use(free_port) is False


def test_busy_local_ports_skips_remote_forwards(monkeypatch) -> None:
    # Only LocalForward + DynamicForward are loopback binds; RemoteForward
    # binds on the server and must not be probed locally.
    host = Host(
        alias="db",
        host_name="db",
        local_forwards=[LocalForward(8080, "localhost", 80)],
        remote_forwards=[RemoteForward(9090, "localhost", 3000)],
        dynamic_forwards=[1080],
    )
    probed: list = []

    def fake_in_use(port: int) -> bool:
        probed.append(port)
        return False

    monkeypatch.setattr(tunnel_cmd, "_port_in_use", fake_in_use)
    assert _REAL_BUSY_LOCAL_PORTS(host) == []
    assert probed == [8080, 1080]  # 9090 (remote) is not probed
