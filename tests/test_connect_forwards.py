"""Tests for opening a host's forwards with a ``connect`` session.

The contract:
- Plain ``connect <alias>`` never injects forwards and never prompts —
  scripted calls stay non-interactive; opt in with ``--forwards``.
- ``connect --forwards`` adds the host's LocalForward / RemoteForward /
  DynamicForward rules as ``-L``/``-R``/``-D`` flags.
- The interactive picker (no alias argument) asks once when the chosen
  host has forwards; answering no (or Ctrl-C) gives a plain connect.
"""
from __future__ import annotations

import types
from pathlib import Path

from xzssh.cli.main import main


def _seed_forward_host(config_path: Path) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", "db", "--host-name", "db.example.com",
         "--user", "alice",
         "--local-forward", "8080:localhost:80",
         "--remote-forward", "9090:localhost:3000",
         "--dynamic-forward", "1080"]
    )


def _seed_plain_host(config_path: Path) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", "plain", "--host-name", "plain.example.com"]
    )


def _patch_subprocess_run(monkeypatch, returncode: int = 0) -> list:
    calls = []

    def fake_run(args, *a, **kw):
        calls.append(args)
        return types.SimpleNamespace(returncode=returncode)

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run", fake_run
    )
    return calls


def _forbid_confirm(monkeypatch) -> None:
    def fail(*a, **kw):
        raise AssertionError("questionary.confirm must not be called")

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.questionary.confirm", fail
    )


def _patch_picker(monkeypatch, alias: str) -> None:
    monkeypatch.setattr(
        "xzssh.cli.commands.connect.questionary.autocomplete",
        lambda *a, **kw: types.SimpleNamespace(ask=lambda: alias),
    )


def _patch_confirm(monkeypatch, answer) -> list:
    asked = []

    def fake_confirm(message, *a, **kw):
        asked.append(message)
        return types.SimpleNamespace(ask=lambda: answer)

    monkeypatch.setattr(
        "xzssh.cli.commands.connect.questionary.confirm", fake_confirm
    )
    return asked


# ---------------------------------------------------------------------------
# --forwards flag
# ---------------------------------------------------------------------------


def test_connect_forwards_flag_injects_forward_flags(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    _forbid_confirm(monkeypatch)  # explicit flag: nothing to ask
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(
        ["connect", "--config", str(config_path), "--forwards", "db"]
    )

    assert exit_code == 0
    argv = calls[0]
    assert argv[argv.index("-L") + 1] == "8080:localhost:80"
    assert argv[argv.index("-R") + 1] == "9090:localhost:3000"
    assert argv[argv.index("-D") + 1] == "1080"
    # Still a normal interactive session, not a tunnel.
    assert "-N" not in argv
    assert argv[-1] == "alice@db.example.com"


def test_connect_without_flag_omits_forwards(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    _forbid_confirm(monkeypatch)  # explicit alias: must not prompt either
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(["connect", "--config", str(config_path), "db"])

    assert exit_code == 0
    argv = calls[0]
    assert "-L" not in argv
    assert "-R" not in argv
    assert "-D" not in argv


def test_connect_dry_run_forwards_prints_flags(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    monkeypatch.setattr(
        "xzssh.cli.commands.connect.subprocess.run",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no ssh")),
    )
    capsys.readouterr()

    exit_code = main(
        ["connect", "--config", str(config_path), "--dry-run", "--forwards", "db"]
    )

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "-L" in out and "8080:localhost:80" in out
    assert "-D" in out and "1080" in out


# ---------------------------------------------------------------------------
# interactive picker prompt
# ---------------------------------------------------------------------------


def test_picker_prompts_and_yes_includes_forwards(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    _patch_picker(monkeypatch, "db")
    asked = _patch_confirm(monkeypatch, answer=True)
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(["connect", "--config", str(config_path)])

    assert exit_code == 0
    assert len(asked) == 1
    assert "3 port-forward(s)" in asked[0]
    argv = calls[0]
    assert argv[argv.index("-L") + 1] == "8080:localhost:80"


def test_picker_prompt_no_gives_plain_connect(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    _patch_picker(monkeypatch, "db")
    _patch_confirm(monkeypatch, answer=False)
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(["connect", "--config", str(config_path)])

    assert exit_code == 0
    argv = calls[0]
    assert "-L" not in argv and "-R" not in argv and "-D" not in argv


def test_picker_prompt_dismissed_gives_plain_connect(
    monkeypatch, tmp_path: Path
) -> None:
    """Ctrl-C on the confirm returns None; connect proceeds without forwards."""
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    _patch_picker(monkeypatch, "db")
    _patch_confirm(monkeypatch, answer=None)
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(["connect", "--config", str(config_path)])

    assert exit_code == 0
    assert "-L" not in calls[0]


def test_picker_host_without_forwards_never_prompts(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_plain_host(config_path)
    _patch_picker(monkeypatch, "plain")
    _forbid_confirm(monkeypatch)
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(["connect", "--config", str(config_path)])

    assert exit_code == 0
    assert calls[0][-1] == "plain.example.com"


def test_picker_forwards_flag_skips_prompt(
    monkeypatch, tmp_path: Path
) -> None:
    """--forwards with the picker: already opted in, nothing to ask."""
    config_path = tmp_path / "xzssh.json"
    _seed_forward_host(config_path)
    _patch_picker(monkeypatch, "db")
    _forbid_confirm(monkeypatch)
    calls = _patch_subprocess_run(monkeypatch)

    exit_code = main(["connect", "--config", str(config_path), "--forwards"])

    assert exit_code == 0
    argv = calls[0]
    assert argv[argv.index("-L") + 1] == "8080:localhost:80"
