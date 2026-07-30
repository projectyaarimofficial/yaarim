import json
import os
import sqlite3

from . import config


def init_db():
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_request TEXT NOT NULL,
            summary TEXT NOT NULL,
            files_touched TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            timestamp TEXT NOT NULL,
            message_count INTEGER NOT NULL,
            summary TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT,
            timestamp TEXT NOT NULL,
            topic TEXT,
            question TEXT NOT NULL,
            student_answer TEXT,
            correct INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def log_change(user_request, summary, files_touched):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """
        INSERT INTO changes (timestamp, user_request, summary, files_touched)
        VALUES (datetime('now'), ?, ?, ?)
        """,
        (user_request, summary, json.dumps(files_touched, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()


def log_session(student_id, message_count, summary):
    conn = sqlite3.connect(config.DB_PATH)
    cursor = conn.execute(
        """
        INSERT INTO sessions (student_id, timestamp, message_count, summary)
        VALUES (?, datetime('now'), ?, ?)
        """,
        (student_id, message_count, summary),
    )
    conn.commit()
    session_id = cursor.lastrowid
    conn.close()
    return session_id


def log_quiz_result(student_id, topic, question, student_answer, correct):
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(
        """
        INSERT INTO quiz_results
            (student_id, timestamp, topic, question, student_answer, correct)
        VALUES (?, datetime('now'), ?, ?, ?, ?)
        """,
        (student_id, topic, question, student_answer, 1 if correct else 0),
    )
    conn.commit()
    conn.close()
