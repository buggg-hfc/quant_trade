from __future__ import annotations

import base64
import os

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class KeyStore:
    """Encrypted API key storage using Fernet symmetric encryption.

    Plaintext never touches disk. Ciphertext stored in SQLite keystore table.
    Master password → PBKDF2 → Fernet key → encrypt/decrypt.
    """

    def __init__(self, db_path: str, salt: bytes | None = None) -> None:
        self._db_path = db_path
        # salt is non-secret (stored in .env as KEYSTORE_SALT), 32 bytes base64
        self._salt = salt or os.environ.get("KEYSTORE_SALT", "default_salt_change_me").encode()
        self._db = self._init_db()

    def _init_db(self):
        import sqlite3
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS keystore (name TEXT PRIMARY KEY, value BLOB)"
        )
        conn.commit()
        return conn

    def _derive_fernet(self, master_pwd: str) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self._salt,
            iterations=100_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(master_pwd.encode()))
        return Fernet(key)

    def set_key(self, name: str, plaintext: str, master_pwd: str) -> None:
        fernet = self._derive_fernet(master_pwd)
        ciphertext = fernet.encrypt(plaintext.encode())
        self._db.execute(
            "INSERT OR REPLACE INTO keystore (name, value) VALUES (?, ?)",
            (name, ciphertext),
        )
        self._db.commit()

    def get_key(self, name: str, master_pwd: str) -> str:
        row = self._db.execute(
            "SELECT value FROM keystore WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            raise KeyError(f"Key '{name}' not found in keystore")
        fernet = self._derive_fernet(master_pwd)
        return fernet.decrypt(row[0]).decode()

    def delete_key(self, name: str) -> None:
        self._db.execute("DELETE FROM keystore WHERE name = ?", (name,))
        self._db.commit()

    def list_keys(self) -> list[str]:
        rows = self._db.execute("SELECT name FROM keystore").fetchall()
        return [r[0] for r in rows]
