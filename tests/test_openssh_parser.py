from pathlib import Path

from xzssh.parser import parse_openssh_config


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_basic_host(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "Host db\n"
        "  HostName db.example.com\n"
        "  User alice\n"
        "  Port 2222\n"
        "  IdentityFile ~/.ssh/id_ed25519\n",
    )

    hosts, warnings = parse_openssh_config(cfg)

    assert warnings == []
    assert len(hosts) == 1
    h = hosts[0]
    assert h.alias == "db"
    assert h.host_name == "db.example.com"
    assert h.user == "alice"
    assert h.port == 2222
    assert h.identity_file == "~/.ssh/id_ed25519"


def test_multi_host_line_creates_one_entry_per_alias(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "Host web1 web2 web3\n"
        "  HostName cluster.example.com\n"
        "  User deploy\n",
    )

    hosts, _ = parse_openssh_config(cfg)

    assert [h.alias for h in hosts] == ["web1", "web2", "web3"]
    assert all(h.host_name == "cluster.example.com" for h in hosts)
    assert all(h.user == "deploy" for h in hosts)


def test_equals_separator_and_quoted_values(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        'Host gw\n'
        '  HostName="gw.example.com"\n'
        "  User=root\n"
        "  Port = 2200\n",
    )

    hosts, _ = parse_openssh_config(cfg)

    assert hosts[0].host_name == "gw.example.com"
    assert hosts[0].user == "root"
    assert hosts[0].port == 2200


def test_match_block_directives_are_not_applied(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "Host real\n"
        "  HostName real.example.com\n"
        "Match user *\n"
        "  User overridden\n"
        "  Port 9999\n",
    )

    hosts, warnings = parse_openssh_config(cfg)

    assert len(hosts) == 1
    assert hosts[0].alias == "real"
    assert hosts[0].user is None
    assert hosts[0].port is None
    assert any("Match" in w for w in warnings)


def test_wildcard_hosts_are_warned_and_skipped(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "Host *.internal\n"
        "  User admin\n"
        "Host real\n"
        "  HostName real.example.com\n",
    )

    hosts, warnings = parse_openssh_config(cfg)

    assert [h.alias for h in hosts] == ["real"]
    assert any("wildcard" in w.lower() for w in warnings)


def test_include_emits_warning_and_does_not_follow(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "Include ~/.ssh/extras/*\n"
        "Host plain\n"
        "  HostName plain.example.com\n",
    )

    hosts, warnings = parse_openssh_config(cfg)

    assert [h.alias for h in hosts] == ["plain"]
    assert any("Include" in w for w in warnings)


def test_invalid_port_is_warned_not_fatal(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "Host bad-port\n"
        "  HostName x.example.com\n"
        "  Port not-a-number\n",
    )

    hosts, warnings = parse_openssh_config(cfg)

    assert len(hosts) == 1
    assert hosts[0].port is None
    assert any("Port" in w for w in warnings)


def test_comments_and_blank_lines_ignored(tmp_path: Path) -> None:
    cfg = _write(
        tmp_path / "ssh_config",
        "# top-level comment\n"
        "\n"
        "Host alpha\n"
        "  # nested comment\n"
        "  HostName a.example.com\n",
    )

    hosts, _ = parse_openssh_config(cfg)

    assert len(hosts) == 1
    assert hosts[0].alias == "alpha"
    assert hosts[0].host_name == "a.example.com"
