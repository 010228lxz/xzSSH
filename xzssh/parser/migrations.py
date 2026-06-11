"""Schema-migration registry for the JSON config file.

The on-disk JSON carries a ``version`` field (``Config.version``); the
version this code understands is ``CURRENT_SCHEMA_VERSION`` in
:mod:`xzssh.model.types`. When ``load_config`` reads a file with an
older version it upgrades the raw dict in memory by applying the
functions registered here, one step at a time. Persisting the upgraded
file (with a ``.bak`` of the original) is the CLI's job — see
``load_config_if_exists`` in ``xzssh/cli/helpers.py``.

Contract — read this before bumping the schema version:

- ``MIGRATIONS[n]`` upgrades a raw config **dict** (not a ``Config``)
  from schema ``n`` to schema ``n + 1``. Register exactly one entry per
  retired version; a gap makes every older file unreadable and the
  loader treats it as a hard error.
- Never lower ``CURRENT_SCHEMA_VERSION``; never re-use a version number.
- Migrations must be pure (no I/O) and idempotent — applying one to an
  already-upgraded dict must be a no-op. The loader stamps ``version``
  after each step, so the chain never re-runs under normal operation;
  idempotency is defence in depth for half-written upgrades.
- A migration may assume its input parsed as JSON and has a dict root,
  nothing more. Shape errors it lets through are caught by the normal
  parse that follows the chain.
"""
from __future__ import annotations

from typing import Any, Callable, Dict

# version n -> function upgrading a raw config dict from schema n to n+1.
MIGRATIONS: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
