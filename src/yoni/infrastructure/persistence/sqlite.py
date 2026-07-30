"""אחסון SQLite: שאילתות מצטברות על פני תלמידים וזמן.

זה המקום שבו ה"חוב" של שני מקורות אמת הופך להחלטה מפורשת. שני המימושים אינם
כפילות מקרית - הם שני שימושים שונים:

    FileConversationLog   קריא לאדם, לכל תלמיד בנפרד, יומי (מורה פותח וקורא)
    SqliteConversationLog נשאל בשאילתה: "כמה טעויות בשברים בכל הכיתה החודש?"

CompositeConversationLog כותב לשניהם *במפורש*, במקום אחד, במקום ששכבת הממשק
תזכור לקרוא לשניהם - וזו בדיוק הטעות שהייתה קודם.
"""

import json
import os
import sqlite3
from contextlib import closing

from typing import Optional

from ...domain.ports import ConversationLog


class SqliteConversationLog(ConversationLog):
    def __init__(self, db_path):
        self._db_path = db_path
        self.initialize()

    def _connect(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        return sqlite3.connect(self._db_path)

    def initialize(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS changes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    user_request TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    files_touched TEXT NOT NULL
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT,
                    timestamp TEXT NOT NULL,
                    message_count INTEGER NOT NULL,
                    summary TEXT NOT NULL
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quiz_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT,
                    timestamp TEXT NOT NULL,
                    topic TEXT,
                    question TEXT NOT NULL,
                    student_answer TEXT,
                    correct INTEGER NOT NULL
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id TEXT,
                    timestamp TEXT NOT NULL,
                    category TEXT NOT NULL,
                    label TEXT
                )""")

    def log_session(self, student_id, summary, message_count):
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "INSERT INTO sessions (student_id, timestamp, message_count, summary)"
                " VALUES (?, datetime('now'), ?, ?)",
                (student_id, message_count, summary),
            )
            return cursor.lastrowid

    def log_quiz_result(self, student_id, question, answer, result):
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO quiz_results (student_id, timestamp, topic, question,"
                " student_answer, correct) VALUES (?, datetime('now'), ?, ?, ?, ?)",
                (student_id, question.topic, question.question, answer,
                 1 if result.correct else 0),
            )

    def log_alert(self, student_id, finding, text):
        # התוכן עצמו לא נשמר ב-SQL: הוא נשמר בתיקיית התלמיד. כאן רק העובדה
        # שהייתה התרעה, כדי שאפשר יהיה לספור בלי לפתוח מידע רגיש בשאילתה.
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO alerts (student_id, timestamp, category, label)"
                " VALUES (?, datetime('now'), ?, ?)",
                (student_id, finding.category, finding.label),
            )

    def log_change(self, user_request: str, summary: str, files_touched: list) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO changes (timestamp, user_request, summary, files_touched)"
                " VALUES (datetime('now'), ?, ?, ?)",
                (user_request, summary, json.dumps(files_touched, ensure_ascii=False)),
            )

    def last_session(self, student_id: str) -> Optional[dict]:
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT summary, timestamp FROM sessions WHERE student_id = ?"
                " ORDER BY session_id DESC LIMIT 1", (student_id,),
            ).fetchone()
        return {"summary": row[0], "date": row[1][:10]} if row else None


class CompositeConversationLog(ConversationLog):
    """כותב לכל היעדים, וקורא מהראשון שעונה. סדר היעדים קובע עדיפות בקריאה."""

    def __init__(self, *logs):
        self._logs = logs

    def log_session(self, student_id, summary, message_count):
        return [log.log_session(student_id, summary, message_count) for log in self._logs]

    def log_quiz_result(self, student_id, question, answer, result):
        return [log.log_quiz_result(student_id, question, answer, result) for log in self._logs]

    def log_alert(self, student_id, finding, text):
        return [log.log_alert(student_id, finding, text) for log in self._logs]

    def last_session(self, student_id: str) -> Optional[dict]:
        for log in self._logs:
            found = log.last_session(student_id)
            if found:
                return found
        return None
