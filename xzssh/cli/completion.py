"""Shell-completion glue.

Driven by `argcomplete <https://kislyuk.github.io/argcomplete/>`_, which
- works on bash, zsh, and fish via a single shell hook
- supports per-argument dynamic completers (used here for host aliases)
- is purely optional: if the user hasn't installed it the parser still
  works fine, just without tab-completion.

The install path is documented in the README; the runtime hook is
``argcomplete.autocomplete(parser)`` which short-circuits when the
process isn't being driven by the completion shim.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from xzssh.cli.profiles import (
    load_registry,
    registry_path,
    resolve_config_path,
)
from xzssh.crypto import detect_envelope
from xzssh.parser import ConfigParseError, load_config
from xzssh.platform import default_config_path


def _completion_config_path(parsed_args) -> Path:
    """The config file the completion should read.

    Honours ``--config`` and ``--profile`` (plus ``$XZSSH_PROFILE`` and
    the default profile) like the real CLI; any resolution problem
    falls back to the platform default rather than blowing up the
    shell.
    """
    try:
        return resolve_config_path(
            getattr(parsed_args, "config", None),
            getattr(parsed_args, "profile", None),
        )
    except ValueError:
        return default_config_path()


def _load_for_completion(config_path: Path):
    """Load a config for completion purposes, or None.

    An encrypted config is deliberately skipped: ``load_config`` would
    shell out to gpg/age, and a passphrase prompt in the middle of
    <TAB> completion is hostile.
    """
    if not config_path.exists():
        return None
    if detect_envelope(config_path.read_bytes()) is not None:
        return None
    return load_config(config_path)


def alias_completer(prefix: str, parsed_args, **_kwargs) -> List[str]:
    """argcomplete completer that returns host aliases.

    Honours ``--config`` / ``--profile`` if the user has typed them,
    otherwise falls back to the platform default (``~/.ssh/xzssh.json``).
    Any error loading the config — missing file, bad JSON, permissions —
    returns an empty list rather than blowing up the shell.
    """
    try:
        config = _load_for_completion(_completion_config_path(parsed_args))
    except (ConfigParseError, OSError, ValueError):
        return []
    if config is None:
        return []

    return _matches(prefix, (h.alias for h in config.hosts))


def key_completer(prefix: str, parsed_args, **_kwargs) -> List[str]:
    """argcomplete completer that returns configured key names (for ``key add-agent``)."""
    try:
        config = _load_for_completion(_completion_config_path(parsed_args))
    except (ConfigParseError, OSError, ValueError):
        return []
    if config is None:
        return []

    return _matches(prefix, config.keys.keys())


def profile_completer(prefix: str, parsed_args, **_kwargs) -> List[str]:
    """argcomplete completer that returns registered profile names."""
    try:
        registry = load_registry(registry_path())
    except (OSError, ValueError):
        return []

    return _matches(prefix, registry.profiles.keys())


def _matches(prefix: str, candidates: Iterable[str]) -> List[str]:
    """Filter *candidates* by *prefix*. Sorted for deterministic output."""
    prefix = prefix or ""
    return sorted(c for c in candidates if c.startswith(prefix))


def install_argcomplete(parser) -> None:
    """Activate argcomplete on *parser* if the library is available.

    Silently no-ops when argcomplete isn't installed — completion is a
    convenience, not a requirement.
    """
    try:
        import argcomplete  # noqa: WPS433  (optional dep)
    except ImportError:
        return
    argcomplete.autocomplete(parser)
