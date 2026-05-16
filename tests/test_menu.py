"""Smoke tests for the interactive ``default_menu`` and ``main_menu`` loops.

The menus are the primary advertised entry point (running ``xzssh`` with
no arguments) and contain the bulk of the CLI's interactive code, but
their logic is entirely driven by ``questionary`` prompts that can't run
under pytest's captured stdin.

These tests monkeypatch the prompt primitives to feed scripted answers
and verify that:

- both loops can be entered, dispatch to at least one branch, and exit
  cleanly without crashing
- the "exit" action breaks the loop
- branches that don't require further user input (help, check, generate)
  route through the correct sub-command

We deliberately don't cover every branch — that's exhaustive UI testing
the menus weren't designed for. The goal is to catch import errors,
typos, and dispatch-table regressions.
"""
from __future__ import annotations

import types
from pathlib import Path
from typing import List, Optional

import pytest

from xzssh.cli.commands.menu import default_menu, main_menu
from xzssh.cli.main import main as cli_main


class ScriptedActions:
    """Callable that returns scripted answers one at a time.

    Each call returns the next answer in order. Running out of answers
    is an error — the test under-specified the script.
    """

    def __init__(self, answers: List[Optional[str]]):
        self._answers = list(answers)
        self.calls: List[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if not self._answers:
            raise AssertionError(
                f"ScriptedActions ran out of answers after {len(self.calls)} calls"
            )
        return self._answers.pop(0)


@pytest.fixture
def silence_console(monkeypatch):
    """Stop the menu from clearing the screen and waiting for keypresses."""
    from xzssh.cli.ui import console

    monkeypatch.setattr(console, "clear", lambda: None)
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.questionary.press_any_key_to_continue",
        lambda *a, **kw: types.SimpleNamespace(ask=lambda: None),
    )
    monkeypatch.setattr(
        "xzssh.cli.commands.list_.questionary.press_any_key_to_continue",
        lambda *a, **kw: types.SimpleNamespace(ask=lambda: None),
    )


def _seed_one_host(config_path: Path) -> None:
    cli_main(
        [
            "add",
            "--config",
            str(config_path),
            "--alias",
            "db",
            "--host-name",
            "db.example.com",
        ]
    )


# -----------------------------------------------------------------------------
# default_menu
# -----------------------------------------------------------------------------


def test_default_menu_exits_immediately_with_no_config(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"  # doesn't exist
    script = ScriptedActions(["exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    rc = default_menu(config_path, suggest_ports=False)

    assert rc == 0
    assert len(script.calls) == 1


def test_default_menu_exits_immediately_with_hosts(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    script = ScriptedActions(["exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    rc = default_menu(config_path, suggest_ports=False)

    assert rc == 0


def test_default_menu_none_action_breaks_loop(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    """Pressing Ctrl-C / dismissing the prompt returns None; loop must exit."""
    config_path = tmp_path / "xzssh.json"

    script = ScriptedActions([None])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    rc = default_menu(config_path, suggest_ports=False)
    assert rc == 0


def test_default_menu_help_then_exit_routes_through_help(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"

    script = ScriptedActions(["help", "exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    help_calls: List[None] = []
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.print_help",
        lambda: help_calls.append(None),
    )

    rc = default_menu(config_path, suggest_ports=False)

    assert rc == 0
    assert len(help_calls) == 1


def test_default_menu_generate_then_exit_routes_through_generate(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    script = ScriptedActions(["generate", "exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    generate_calls: List[tuple] = []

    def fake_generate_run(*args, **kwargs):
        generate_calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(
        "xzssh.cli.commands.menu.generate_cmd.run", fake_generate_run
    )

    rc = default_menu(config_path, suggest_ports=False)

    assert rc == 0
    assert len(generate_calls) == 1


# -----------------------------------------------------------------------------
# main_menu
# -----------------------------------------------------------------------------


def test_main_menu_exits_immediately(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"

    script = ScriptedActions(["exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    rc = main_menu(config_path, suggest_ports=False)
    assert rc == 0


def test_main_menu_none_action_breaks_loop(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"

    script = ScriptedActions([None])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    rc = main_menu(config_path, suggest_ports=False)
    assert rc == 0


def test_main_menu_check_then_exit_routes_through_check(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed_one_host(config_path)

    script = ScriptedActions(["check", "exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    check_calls: List[tuple] = []

    def fake_check_run(*args, **kwargs):
        check_calls.append((args, kwargs))
        return 0

    monkeypatch.setattr(
        "xzssh.cli.commands.menu.check_cmd.run", fake_check_run
    )

    rc = main_menu(config_path, suggest_ports=False)

    assert rc == 0
    assert len(check_calls) == 1


def test_main_menu_help_then_exit_routes_through_help(
    monkeypatch, tmp_path: Path, silence_console
) -> None:
    config_path = tmp_path / "xzssh.json"

    script = ScriptedActions(["help", "exit"])
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.prompt_select_action", script
    )

    help_calls: List[None] = []
    monkeypatch.setattr(
        "xzssh.cli.commands.menu.print_help",
        lambda: help_calls.append(None),
    )

    rc = main_menu(config_path, suggest_ports=False)
    assert rc == 0
    assert len(help_calls) == 1
