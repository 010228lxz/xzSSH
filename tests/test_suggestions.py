"""A mistyped sub-command should produce a themed 'did you mean?' message
(exit 2), while invalid *option* values keep argparse's default error so
their valid choices still show.
"""
from __future__ import annotations

import pytest

import xzssh.cli.parser as parser_mod
from xzssh.cli.main import main


@pytest.fixture
def captured_msgs(monkeypatch):
    """Capture the parser's themed error/notice output by name (robust to
    however rich routes its streams)."""
    msgs: list[str] = []
    monkeypatch.setattr(parser_mod, "print_error", lambda m: msgs.append(m))
    monkeypatch.setattr(parser_mod, "print_notice", lambda m: msgs.append(m))
    return msgs


def test_unknown_command_suggests_closest(captured_msgs):
    with pytest.raises(SystemExit) as exc:
        main(["lsit"])
    assert exc.value.code == 2
    joined = " ".join(captured_msgs)
    assert "Unknown command" in joined
    assert "lsit" in joined
    # Not just `"list" in joined`: the help pointer ("...full command
    # list.") contains the word "list", which masked the 3.12 regression.
    assert "Did you mean" in joined
    assert "list" in joined  # the suggestion


def test_unknown_nested_subcommand_suggests(captured_msgs):
    with pytest.raises(SystemExit) as exc:
        main(["key", "gne"])
    assert exc.value.code == 2
    joined = " ".join(captured_msgs)
    assert "Unknown command" in joined
    assert "Did you mean" in joined
    assert "gen" in joined  # suggestion for the key sub-command


def test_suggests_from_unquoted_choices_like_python_312(captured_msgs):
    """Python 3.12.x joins the choices with str() instead of repr()
    (cpython gh-117766, reverted in 3.13), so the message lists them
    unquoted. Feed that format directly so every interpreter exercises
    the 3.12 parsing path."""
    p = parser_mod._SuggestingArgumentParser(prog="xzssh")
    with pytest.raises(SystemExit) as exc:
        p.error(
            "argument key_command: invalid choice: 'gne' "
            "(choose from add, list, add-agent, gen, copy-id)"
        )
    assert exc.value.code == 2
    joined = " ".join(captured_msgs)
    assert "Unknown command" in joined
    assert "Did you mean" in joined
    assert "gen" in joined


def test_no_close_match_still_points_at_help(captured_msgs):
    with pytest.raises(SystemExit) as exc:
        main(["zzzzzz"])
    assert exc.value.code == 2
    joined = " ".join(captured_msgs)
    assert "Unknown command" in joined
    assert "--help" in joined
    # No confident suggestion for gibberish.
    assert "Did you mean" not in joined


def test_invalid_option_value_uses_default_error(captured_msgs):
    # An invalid --theme value must NOT be treated as an unknown command;
    # argparse's default error (which lists the valid themes) handles it.
    with pytest.raises(SystemExit) as exc:
        main(["--theme", "sparkly", "list"])
    assert exc.value.code == 2
    assert captured_msgs == []  # our handler stayed out of it
