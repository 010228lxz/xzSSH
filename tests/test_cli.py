from pathlib import Path

from xzssh.cli.main import main


def test_add_list_remove_flow(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"

    exit_code = main(
        [
            "add",
            "--config",
            str(config_path),
            "--alias",
            "db",
            "--host-name",
            "db.example.com",
            "--user",
            "alice",
            "--port",
            "22",
        ]
    )
    assert exit_code == 0
    assert config_path.exists()

    exit_code = main(["list", "--config", str(config_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "db" in captured.out
    assert "db.example.com" in captured.out

    exit_code = main(["remove", "--config", str(config_path), "db"])
    assert exit_code == 0
    capsys.readouterr()  # Clear buffer after remove

    exit_code = main(["list", "--config", str(config_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "db" not in captured.out


def test_generate_writes_output(tmp_path: Path) -> None:
    config_path = tmp_path / "xzssh.json"
    output_path = tmp_path / "ssh_config"

    main(
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

    exit_code = main(
        [
            "generate",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ]
    )
    assert exit_code == 0
    assert output_path.exists()
    assert "Host db" in output_path.read_text(encoding="utf-8")


def test_key_add_and_list(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    key_path = tmp_path / "id_test"
    key_path.write_text("dummy", encoding="utf-8")

    exit_code = main(["key", "add", "id_test", str(key_path), "--config", str(config_path)])
    assert exit_code == 0

    exit_code = main(["key", "list", "--config", str(config_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "id_test" in captured.out


def test_import_basic(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "xzssh.json"
    ssh_config = tmp_path / "ssh_config"
    ssh_config.write_text(
        "Host test-import\n"
        "  HostName 1.2.3.4\n"
        "  User root\n",
        encoding="utf-8"
    )

    exit_code = main(["import", str(ssh_config), "--config", str(config_path)])
    assert exit_code == 0

    exit_code = main(["list", "--config", str(config_path)])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "test-import" in captured.out
    assert "1.2.3.4" in captured.out
