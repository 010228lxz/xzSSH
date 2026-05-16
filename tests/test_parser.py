from pathlib import Path

import pytest

from xzssh.parser import ConfigParseError, load_config


def test_load_config_parses_hosts(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    config_path.write_text(
        """
        {
          "version": 1,
          "hosts": [
            {
              "alias": "db",
              "host_name": "db.example.com",
              "user": "alice",
              "port": 22,
              "identity_file": "~/.ssh/id_ed25519",
              "local_forwards": [
                {
                  "local_port": 5432,
                  "remote_host": "127.0.0.1",
                  "remote_port": 5432
                }
              ]
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert config.version == 1
    assert len(config.hosts) == 1
    host = config.hosts[0]
    assert host.alias == "db"
    assert host.host_name == "db.example.com"
    assert host.user == "alice"
    assert host.port == 22
    assert host.identity_file == "~/.ssh/id_ed25519"
    assert len(host.local_forwards) == 1
    lf = host.local_forwards[0]
    assert lf.local_port == 5432
    assert lf.remote_host == "127.0.0.1"
    assert lf.remote_port == 5432


def test_load_config_missing_hosts_raises(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    config_path.write_text("{\"version\": 1}", encoding="utf-8")

    with pytest.raises(ConfigParseError):
        load_config(config_path)
