import os

import pytest

from xzssh.model import Config, Host, LocalForward
from xzssh.validator import validate_config


def test_duplicate_alias_detection() -> None:
    config = Config(
        version=1,
        hosts=[
            Host(alias="db", host_name="db1"),
            Host(alias="db", host_name="db2"),
        ],
    )

    result = validate_config(config)
    assert any("Duplicate host alias" in error for error in result.errors)


def test_duplicate_local_forward_port_detection() -> None:
    config = Config(
        version=1,
        hosts=[
            Host(
                alias="db",
                host_name="db",
                local_forwards=[LocalForward(5432, "127.0.0.1", 5432)],
            ),
            Host(
                alias="cache",
                host_name="cache",
                local_forwards=[LocalForward(5432, "127.0.0.1", 6379)],
            ),
        ],
    )

    result = validate_config(config, suggest_ports=True)
    assert any("Duplicate LocalForward port 5432" in error for error in result.errors)
    assert any("db (db)" in error for error in result.errors)
    assert any("cache (cache)" in error for error in result.errors)
    assert any("Suggestion: next free port" in error for error in result.errors)


def test_port_range_validation() -> None:
    config = Config(
        version=1,
        hosts=[
            Host(
                alias="bad",
                host_name="bad",
                port=70000,
                local_forwards=[LocalForward(0, "127.0.0.1", 65536)],
            )
        ],
    )

    result = validate_config(config)
    assert any("hosts[0].port" in error for error in result.errors)
    assert any("local_port" in error for error in result.errors)
    assert any("remote_port" in error for error in result.errors)


def test_low_port_warning() -> None:
    config = Config(
        version=1,
        hosts=[
            Host(
                alias="db",
                host_name="db",
                local_forwards=[LocalForward(22, "127.0.0.1", 22)],
            )
        ],
    )

    result = validate_config(config)
    assert any("below 1024" in warning for warning in result.warnings)


def test_key_missing_file_error(tmp_path) -> None:
    config = Config(
        version=1,
        hosts=[],
        keys={"id_test": "missing_key"},
    )
    config_path = tmp_path / "xzssh.json"
    result = validate_config(config, source_path=config_path)
    assert any("id_test" in error for error in result.errors)


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
def test_key_permission_warning(tmp_path) -> None:
    key_path = tmp_path / "id_test"
    key_path.write_text("dummy", encoding="utf-8")
    key_path.chmod(0o644)

    config = Config(
        version=1,
        hosts=[],
        keys={"id_test": str(key_path)},
    )

    result = validate_config(config)
    assert any("permissions are too open" in warning for warning in result.warnings)
