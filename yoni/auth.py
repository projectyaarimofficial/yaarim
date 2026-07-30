"""אימות משתמשים למסך ההתחברות: מזהה (ID) + סיסמה.

המשתמשים נשמרים בטבלת users באותו קובץ SQLite הקיים (config.DB_PATH),
כך שאין צורך בקבצים או תיקיות חדשים. הסיסמאות נשמרות כ-hash עם salt
(pbkdf2_hmac) - לא בטקסט גלוי.
"""

import hashlib
import os
import secrets
import sqlite3

from . import config

_ITERATIONS = 200_000


def init_db():
    """יוצר את טבלת המשתמשים אם אינה קיימת."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
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
    conn.commit()
    conn.close()


def _hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    ).hex()


def user_exists(user_id):
    user_id = (user_id or "").strip()
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return row is not None


def create_user(user_id, password):
    """יוצר משתמש חדש. זורק ValueError אם חסר מידע או שהמזהה כבר קיים."""
    user_id = (user_id or "").strip()
    if not user_id or not password:
        raise ValueError("נדרשים גם מזהה וגם סיסמה.")
    if user_exists(user_id):
        raise ValueError("משתמש עם מזהה זה כבר קיים.")
    salt = secrets.token_hex(16)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        "INSERT INTO users (user_id, salt, password_hash) VALUES (?, ?, ?)",
        (user_id, salt, _hash(password, salt)),
    )
    conn.commit()
    conn.close()


def verify_user(user_id, password):
    """True אם המזהה קיים והסיסמה נכונה, אחרת False."""
    user_id = (user_id or "").strip()
    if not user_id or not password:
        return False
    conn = sqlite3.connect(config.DB_PATH)
    row = conn.execute(
        "SELECT salt, password_hash FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return False
    salt, stored = row
    return secrets.compare_digest(_hash(password, salt), stored)
