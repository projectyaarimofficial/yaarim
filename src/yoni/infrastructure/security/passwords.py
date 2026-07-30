"""אחסון ואימות סיסמאות - מימוש PasswordStore מעל SQLite.

הסיסמאות נשמרות כ-hash עם salt (pbkdf2_hmac), לא בטקסט גלוי, וההשוואה היא
compare_digest כדי שלא תדלוף מידע דרך זמן ההשוואה.
"""

import hashlib
import os
import secrets
import sqlite3
from contextlib import closing

from ...domain.ports import PasswordStore

ITERATIONS = 200_000


class SqlitePasswordStore(PasswordStore):
    def __init__(self, db_path):
        self._db_path = db_path
        self.initialize()

    def _connect(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        return sqlite3.connect(self._db_path)

    def initialize(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

    @staticmethod
    def _hash(password, salt):
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS
        ).hex()

    def exists(self, user_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", ((user_id or "").strip(),)
            ).fetchone()
        return row is not None

    def create(self, user_id: str, password: str) -> None:
        user_id = (user_id or "").strip()
        if not user_id or not password:
            raise ValueError("נדרשים גם מזהה וגם סיסמה.")
        if self.exists(user_id):
            raise ValueError("משתמש עם מזהה זה כבר קיים.")
        salt = secrets.token_hex(16)
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO users (user_id, salt, password_hash) VALUES (?, ?, ?)",
                (user_id, salt, self._hash(password, salt)),
            )

    def verify(self, user_id: str, password: str) -> bool:
        user_id = (user_id or "").strip()
        if not user_id or not password:
            return False
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT salt, password_hash FROM users WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return False
        salt, stored = row
        return secrets.compare_digest(self._hash(password, salt), stored)
