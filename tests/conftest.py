"""Suite-wide hermeticity.

Every test runs with the profile machinery pointed at a throwaway
registry and with no session profile override — so a developer's real
``~/.config/xzssh/profiles.json`` or exported ``XZSSH_PROFILE`` can
never redirect a test's config reads/writes.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_profile_registry(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    registry_file = tmp_path_factory.mktemp("profiles") / "profiles.json"
    monkeypatch.setenv("XZSSH_PROFILES_FILE", str(registry_file))
    monkeypatch.delenv("XZSSH_PROFILE", raising=False)
    return registry_file


@pytest.fixture(autouse=True)
def _isolated_tunnel_state(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Path:
    state_file = tmp_path_factory.mktemp("tunnels") / "tunnels.json"
    monkeypatch.setenv("XZSSH_TUNNELS_FILE", str(state_file))
    return state_file
