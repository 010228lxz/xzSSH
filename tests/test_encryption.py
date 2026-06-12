"""Tests for at-rest encryption (`xzssh encrypt` / `decrypt`).

No real gpg/age runs: the envelope module's subprocess shim (``_run``)
is replaced with a reversible fake that produces realistically-headed
ciphertext (PGP armor / age header), so the magic-byte detection paths
are exercised for real.
"""
from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

import pytest

import xzssh.crypto.envelope as envelope
from xzssh.cli.completion import alias_completer
from xzssh.cli.main import main
from xzssh.crypto import EnvelopeError, detect_envelope
from xzssh.parser import ConfigParseError, load_config


posix_only = pytest.mark.skipif(
    os.name != "posix", reason="POSIX permission semantics"
)


def _fake_run(args, input_bytes):
    """Reversible stand-in for gpg/age with realistic headers."""
    tool = args[0]
    encrypting = "--symmetric" in args or "--passphrase" in args
    if encrypting:
        header = (
            envelope.GPG_ARMOR_PREFIX if tool == "gpg" else envelope.AGE_PREFIX
        )
        return header + b"\n" + base64.b64encode(input_bytes)
    body = input_bytes.split(b"\n", 1)[1]
    return base64.b64decode(body)


@pytest.fixture
def fake_crypto(monkeypatch):
    monkeypatch.setattr(envelope, "_run", _fake_run)
    monkeypatch.setattr("shutil.which", lambda name: f"/usr/bin/{name}")


def _seed(config_path: Path) -> None:
    main(
        ["add", "--config", str(config_path),
         "--alias", "db", "--host-name", "db.example.com", "--tag", "prod"]
    )


# ---------------------------------------------------------------------------
# envelope detection
# ---------------------------------------------------------------------------

def test_detect_plaintext_json() -> None:
    assert detect_envelope(b'{\n  "version": 1\n}') is None


def test_detect_gpg_armor() -> None:
    assert detect_envelope(b"-----BEGIN PGP MESSAGE-----\nxyz") == "gpg"


def test_detect_gpg_binary_msb() -> None:
    assert detect_envelope(bytes([0x8C, 0x0D, 0x04])) == "gpg"


def test_detect_age() -> None:
    assert detect_envelope(b"age-encryption.org/v1\n-> scrypt") == "age"
    assert detect_envelope(b"-----BEGIN AGE ENCRYPTED FILE-----\n") == "age"


# ---------------------------------------------------------------------------
# encrypt / decrypt commands
# ---------------------------------------------------------------------------

def test_encrypt_roundtrip(tmp_path: Path, fake_crypto) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)

    rc = main(["encrypt", "--config", str(config_path)])
    assert rc == 0

    # On disk: not JSON anymore, gpg-armored.
    raw = config_path.read_bytes()
    assert raw.startswith(envelope.GPG_ARMOR_PREFIX)

    # Transparent read: list works, encryption field survives in memory.
    assert main(["list", "--config", str(config_path)]) == 0
    config = load_config(config_path)
    assert config.encryption == "gpg"
    assert config.hosts[0].alias == "db"

    # Back to plaintext.
    rc = main(["decrypt", "--config", str(config_path)])
    assert rc == 0
    data = json.loads(config_path.read_text(encoding="utf-8"))
    assert data["hosts"][0]["alias"] == "db"
    assert "encryption" not in data


def test_writes_stay_encrypted(tmp_path: Path, fake_crypto) -> None:
    """Any mutating command must re-encrypt on write."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])

    rc = main(
        ["add", "--config", str(config_path),
         "--alias", "web", "--host-name", "web.example.com"]
    )
    assert rc == 0

    raw = config_path.read_bytes()
    assert raw.startswith(envelope.GPG_ARMOR_PREFIX)
    config = load_config(config_path)
    assert {h.alias for h in config.hosts} == {"db", "web"}
    assert config.encryption == "gpg"


def test_encrypt_with_age(tmp_path: Path, fake_crypto) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)

    rc = main(["encrypt", "--tool", "age", "--config", str(config_path)])
    assert rc == 0
    assert config_path.read_bytes().startswith(envelope.AGE_PREFIX)
    assert load_config(config_path).encryption == "age"


def test_encrypt_is_idempotent(tmp_path: Path, fake_crypto) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])
    before = config_path.read_bytes()

    rc = main(["encrypt", "--config", str(config_path)])
    assert rc == 0
    assert config_path.read_bytes() == before


def test_switching_tools_reencrypts(tmp_path: Path, fake_crypto) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--tool", "gpg", "--config", str(config_path)])

    rc = main(["encrypt", "--tool", "age", "--config", str(config_path)])
    assert rc == 0
    assert config_path.read_bytes().startswith(envelope.AGE_PREFIX)


def test_decrypt_plaintext_is_noop(tmp_path: Path, fake_crypto) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    before = config_path.read_text(encoding="utf-8")

    rc = main(["decrypt", "--config", str(config_path)])
    assert rc == 0
    assert config_path.read_text(encoding="utf-8") == before


def test_no_plaintext_bak_left_behind(tmp_path: Path, fake_crypto) -> None:
    """A plaintext .bak next to the encrypted file would defeat the point."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])
    assert not config_path.with_name("xzssh.json.bak").exists()


@posix_only
def test_encrypted_file_is_0600(tmp_path: Path, fake_crypto) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])
    mode = stat.S_IMODE(config_path.stat().st_mode)
    assert mode == 0o600


def test_missing_tool_is_clean_error(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    monkeypatch.setattr("shutil.which", lambda name: None)

    rc = main(["encrypt", "--config", str(config_path)])
    assert rc == 1
    # Untouched — still plaintext JSON.
    json.loads(config_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# failure paths
# ---------------------------------------------------------------------------

def test_failed_decrypt_is_a_parse_error(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "xzssh.json"
    config_path.write_bytes(b"-----BEGIN PGP MESSAGE-----\ngarbage")

    def failing_run(args, input_bytes):
        raise EnvelopeError("gpg exited with code 2")

    monkeypatch.setattr(envelope, "_run", failing_run)

    with pytest.raises(ConfigParseError, match="Could not decrypt"):
        load_config(config_path)
    # And the CLI fails cleanly.
    assert main(["list", "--config", str(config_path)]) == 1


def test_cancelled_reencrypt_leaves_file_intact(
    tmp_path: Path, fake_crypto, monkeypatch
) -> None:
    """Cancelling the passphrase prompt on write must not corrupt the file."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])
    before = config_path.read_bytes()

    def run_decrypt_only(args, input_bytes):
        if "--decrypt" in args:
            return _fake_run(args, input_bytes)
        raise EnvelopeError("gpg exited with code 2 (cancelled?)")

    monkeypatch.setattr(envelope, "_run", run_decrypt_only)

    rc = main(
        ["add", "--config", str(config_path),
         "--alias", "web", "--host-name", "web.example.com"]
    )
    assert rc == 1
    assert config_path.read_bytes() == before


def test_manually_encrypted_file_roundtrips(tmp_path: Path, fake_crypto) -> None:
    """A config the user encrypted themselves (no 'encryption' field in
    the JSON) must stay encrypted across a write."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    plaintext = config_path.read_bytes()
    config_path.write_bytes(
        envelope.GPG_ARMOR_PREFIX + b"\n" + base64.b64encode(plaintext)
    )

    config = load_config(config_path)
    assert config.encryption == "gpg"  # detected from the file itself

    main(
        ["add", "--config", str(config_path),
         "--alias", "web", "--host-name", "web.example.com"]
    )
    assert config_path.read_bytes().startswith(envelope.GPG_ARMOR_PREFIX)


# ---------------------------------------------------------------------------
# quiet paths
# ---------------------------------------------------------------------------

def test_completion_never_decrypts(tmp_path: Path, fake_crypto, monkeypatch) -> None:
    """A pinentry prompt mid-<TAB> would be hostile: completers skip
    encrypted configs entirely."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])

    def explode(args, input_bytes):  # pragma: no cover - must not be reached
        raise AssertionError("completion must never invoke gpg/age")

    monkeypatch.setattr(envelope, "_run", explode)

    class FakeArgs:
        config = str(config_path)
        profile = None

    assert alias_completer("d", FakeArgs()) == []


def test_export_prints_decrypted_snapshot(
    tmp_path: Path, fake_crypto, capsys
) -> None:
    """`export` is the documented plaintext-backup escape hatch."""
    config_path = tmp_path / "xzssh.json"
    _seed(config_path)
    main(["encrypt", "--config", str(config_path)])
    capsys.readouterr()

    rc = main(["export", "--config", str(config_path)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["hosts"][0]["alias"] == "db"


def test_validator_rejects_unknown_tool() -> None:
    from xzssh.model import Config
    from xzssh.validator import validate_config

    result = validate_config(Config(encryption="rot13"))
    assert any("encryption" in e for e in result.errors)
