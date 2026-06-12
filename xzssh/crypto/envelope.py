"""Optional at-rest encryption envelope for the JSON config.

The JSON holds hostnames, usernames, and identity-file paths; ``0600``
is the default protection, and users who want more can wrap the file in
a symmetric ``gpg`` or ``age`` envelope. The envelope is transparent:
``load_config`` detects it by magic bytes and decrypts, ``write_config``
re-encrypts whenever ``Config.encryption`` is set (the field travels
inside the plaintext JSON, so the choice survives round-trips).

Trade-offs, by design:

- The passphrase is prompted by the tool itself (gpg's pinentry, age's
  tty prompt) on **every** operation that reads or writes the config.
  That UX cost is the price of the feature; nothing is cached here.
- The generated ``~/.ssh/config`` stays plaintext — ssh itself has to
  read it. The envelope protects the source of truth only.
- Shell completers refuse to touch an enveloped config: a pinentry
  popup mid-<TAB> would be hostile.

Both tools are invoked as subprocesses with the ciphertext/plaintext on
stdin/stdout; xzSSH never sees or stores a passphrase.
"""
from __future__ import annotations

import subprocess
from typing import List, Optional

GPG_ARMOR_PREFIX = b"-----BEGIN PGP MESSAGE-----"
AGE_PREFIX = b"age-encryption.org/v1"
AGE_ARMOR_PREFIX = b"-----BEGIN AGE ENCRYPTED FILE-----"

ENCRYPTION_TOOLS = ("gpg", "age")


class EnvelopeError(Exception):
    pass


def detect_envelope(data: bytes) -> Optional[str]:
    """Identify an encryption envelope by magic bytes; None = plaintext.

    Binary OpenPGP packets always have the MSB of the first byte set —
    JSON (or any UTF-8 text) never does, so the check can't
    false-positive on a plaintext config.
    """
    if data.startswith(GPG_ARMOR_PREFIX):
        return "gpg"
    if data.startswith(AGE_PREFIX) or data.startswith(AGE_ARMOR_PREFIX):
        return "age"
    if data and (data[0] & 0x80) != 0:
        return "gpg"
    return None


def decrypt(data: bytes, tool: str) -> str:
    if tool == "gpg":
        args = ["gpg", "--quiet", "--decrypt"]
    elif tool == "age":
        args = ["age", "--decrypt"]
    else:
        raise EnvelopeError(f"Unknown encryption tool: {tool}")
    plaintext = _run(args, data)
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnvelopeError(
            f"{tool} produced non-UTF-8 plaintext — wrong file?"
        ) from exc


def encrypt(plaintext: str, tool: str) -> bytes:
    if tool == "gpg":
        # Armored so the file stays inspectable as "this is encrypted".
        args = [
            "gpg", "--quiet", "--symmetric", "--armor",
            "--cipher-algo", "AES256", "--output", "-",
        ]
    elif tool == "age":
        args = ["age", "--encrypt", "--passphrase", "--armor"]
    else:
        raise EnvelopeError(f"Unknown encryption tool: {tool}")
    return _run(args, plaintext.encode("utf-8"))


def _run(args: List[str], input_bytes: bytes) -> bytes:
    """Run the tool with stdin/stdout piped; stderr/tty stay attached so
    the tool's own passphrase prompt works."""
    try:
        proc = subprocess.run(
            args, input=input_bytes, stdout=subprocess.PIPE
        )
    except FileNotFoundError as exc:
        raise EnvelopeError(
            f"'{args[0]}' not found on PATH — install it or use the other "
            "tool (xzssh encrypt --tool gpg|age)"
        ) from exc
    except OSError as exc:
        raise EnvelopeError(f"Could not run {args[0]}: {exc}") from exc
    if proc.returncode != 0:
        raise EnvelopeError(
            f"{args[0]} exited with code {proc.returncode} "
            "(wrong passphrase, or the prompt was cancelled?)"
        )
    return proc.stdout
