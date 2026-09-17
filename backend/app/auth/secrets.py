"""The instance secret key and the symmetric encryption built on it.

``SECRET_KEY`` from the environment wins; otherwise a random key is generated
once and kept in ``DATA_DIR/secret.key`` so sessions and encrypted passwords
survive restarts without any configuration.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)

ENC_PREFIX = "enc:"


def load_or_create_secret(explicit: str | None, data_dir: Path) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    path = data_dir / "secret.key"
    if path.is_file():
        value = path.read_text().strip()
        if value:
            return value
    value = secrets.token_urlsafe(48)
    data_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(value)
    os.chmod(path, 0o600)
    log.info("generated a new secret key at %s", path)
    return value


class Cipher:
    """Encrypts short strings (project passwords) with a key derived from the secret."""

    def __init__(self, secret: str) -> None:
        key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, plain: str | None) -> str | None:
        if plain is None or plain == "":
            return None
        return ENC_PREFIX + self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, stored: str | None) -> str | None:
        """Returns the plaintext; values without the prefix are legacy plaintext."""
        if stored is None or stored == "":
            return None
        if not stored.startswith(ENC_PREFIX):
            return stored
        try:
            return self._fernet.decrypt(stored[len(ENC_PREFIX) :].encode()).decode()
        except InvalidToken as exc:
            raise SecretKeyMismatchError(
                "a stored password cannot be decrypted with the current SECRET_KEY; "
                "restore the previous key or re-enter the project's password"
            ) from exc

    @staticmethod
    def is_encrypted(stored: str | None) -> bool:
        return bool(stored) and stored.startswith(ENC_PREFIX)  # type: ignore[union-attr]


class SecretKeyMismatchError(RuntimeError):
    pass
