"""Tests for v0.22.0 host-management convenience:
`xzssh tag add/rm <alias> <tag>...` and `xzssh add --from <alias>`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from xzssh.cli.main import main
from xzssh.parser import load_config


def _add_host(cfg: Path, alias: str, **flags) -> None:
    args = ["add", "--alias", alias, "--host-name", f"{alias}.example.com"]
    for k, v in flags.items():
        flag = "--" + k.replace("_", "-")
        if isinstance(v, bool):
            args.append(flag)
        elif isinstance(v, (list, tuple)):
            for item in v:
                args += [flag, str(item)]
        else:
            args += [flag, str(v)]
    args += ["--config", str(cfg)]
    assert main(args) == 0


# ---------------------------------------------------------------------------
# tag add / rm
# ---------------------------------------------------------------------------

def test_tag_add(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    assert main(["tag", "add", "web", "prod", "edge", "--config", str(cfg)]) == 0
    host = load_config(cfg).hosts[0]
    assert host.tags == ["prod", "edge"]


def test_tag_add_is_idempotent(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web", tag=["prod"])
    rc = main(["tag", "add", "web", "prod", "db", "--config", str(cfg)])
    assert rc == 0
    # 'prod' not duplicated; 'db' appended.
    assert load_config(cfg).hosts[0].tags == ["prod", "db"]


def test_tag_rm(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web", tag=["prod", "db", "edge"])
    assert main(["tag", "rm", "web", "db", "--config", str(cfg)]) == 0
    assert load_config(cfg).hosts[0].tags == ["prod", "edge"]


def test_tag_rm_missing_tag_is_noop_success(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web", tag=["prod"])
    rc = main(["tag", "rm", "web", "nope", "--config", str(cfg)])
    assert rc == 0
    assert load_config(cfg).hosts[0].tags == ["prod"]


def test_tag_unknown_host_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    assert main(["tag", "add", "ghost", "x", "--config", str(cfg)]) == 1


# ---------------------------------------------------------------------------
# add --from (clone)
# ---------------------------------------------------------------------------

def test_clone_copies_fields(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(
        cfg, "web",
        user="deploy", port=2222, tag=["prod", "web"],
    )
    # Clone into a new alias + hostname; everything else inherited.
    rc = main([
        "add", "--from", "web", "--alias", "web2",
        "--host-name", "web2.example.com", "--config", str(cfg),
    ])
    assert rc == 0
    clone = next(h for h in load_config(cfg).hosts if h.alias == "web2")
    assert clone.host_name == "web2.example.com"
    assert clone.user == "deploy"      # inherited
    assert clone.port == 2222          # inherited
    assert clone.tags == ["prod", "web"]  # inherited


def test_clone_flag_overrides_source(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web", user="deploy", port=2222)
    rc = main([
        "add", "--from", "web", "--alias", "web2", "--user", "root",
        "--config", str(cfg),
    ])
    assert rc == 0
    clone = next(h for h in load_config(cfg).hosts if h.alias == "web2")
    assert clone.user == "root"        # overridden
    assert clone.port == 2222          # still inherited
    assert clone.host_name == "web.example.com"  # inherited (no override)


def test_clone_does_not_copy_last_used(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    # Stamp last_used on the source by editing the JSON via reload/save.
    config = load_config(cfg)
    config.hosts[0].last_used = "2026-01-01T00:00:00"
    from xzssh.cli.helpers import write_config
    write_config(cfg, config)

    assert main(["add", "--from", "web", "--alias", "web2", "--config", str(cfg)]) == 0
    clone = next(h for h in load_config(cfg).hosts if h.alias == "web2")
    assert clone.last_used is None


def test_clone_unknown_source_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    assert main(["add", "--from", "ghost", "--alias", "x", "--config", str(cfg)]) == 1


def test_clone_requires_new_alias(tmp_path: Path) -> None:
    cfg = tmp_path / "x.json"
    _add_host(cfg, "web")
    # --from but no --alias → usage error (exit 2), nothing added.
    assert main(["add", "--from", "web", "--config", str(cfg)]) == 2
    assert len(load_config(cfg).hosts) == 1
