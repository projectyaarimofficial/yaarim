"""SQLite-backed mastery tracking and SM-2-style scheduling."""

import sqlite3
from datetime import date, timedelta

from .grader import grade


class MasteryService:
    def __init__(self, db, clock=None):
        self._db = db
        self._clock = clock

    def _today(self):
        return self._clock.today() if self._clock else date.today().isoformat()

    def _connect(self):
        if isinstance(self._db, sqlite3.Connection):
            return self._db, False
        return sqlite3.connect(str(self._db)), True

    def record_attempt(self, student_id, item_id, raw_answer):
        connection, owns_connection = self._connect()
        try:
            connection.row_factory = sqlite3.Row
            item = connection.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
            if item is None:
                raise ValueError(f"Unknown item: {item_id}")
            result = grade(dict(item) | {"choices_he": _choices(item["choices_he"])}, raw_answer)
            timestamp = self._clock.now() if self._clock else None
            if timestamp is None:
                from datetime import datetime
                timestamp = datetime.now().isoformat(timespec="seconds")
            connection.execute(
                "INSERT INTO attempts(student_id, item_id, raw_answer, verdict, graded_by, ts) VALUES (?, ?, ?, ?, ?, ?)",
                (student_id, item_id, str(raw_answer or ""), result["verdict"], result["graded_by"], timestamp),
            )
            previous = connection.execute(
                "SELECT * FROM mastery WHERE student_id = ? AND topic_id = ?",
                (student_id, item["topic_id"]),
            ).fetchone()
            old_attempts = previous["attempts"] if previous else 0
            old_score = float(previous["score"]) if previous else 0.0
            old_ease = float(previous["ease"]) if previous else 2.5
            old_interval = float(previous["interval_d"]) if previous else 0.0
            difficulty = max(float(item["difficulty"]), 1.0)
            if result["verdict"] == "correct":
                weighted_score = (old_score * old_attempts + difficulty) / (old_attempts + difficulty)
                quality = 5
            elif result["verdict"] == "wrong":
                weighted_score = (old_score * old_attempts) / (old_attempts + difficulty)
                quality = 2
            else:
                weighted_score = old_score
                quality = 3
            was_mastered = old_attempts >= 3 and old_score >= 0.8
            new_attempts = old_attempts + 1
            new_score = max(weighted_score, 0.8) if was_mastered else weighted_score
            old_correct = previous["correct"] if previous else 0
            new_correct = old_correct + (1 if result["verdict"] == "correct" else 0)
            new_ease = max(1.3, old_ease + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
            if quality == 2:
                new_interval = 1.0
            elif old_interval < 1:
                new_interval = 1.0
            elif old_interval < 6:
                new_interval = 6.0
            else:
                new_interval = old_interval * new_ease
            next_due = (date.fromisoformat(self._today()) + timedelta(days=max(1, round(new_interval)))).isoformat()
            connection.execute(
                """INSERT INTO mastery(student_id, topic_id, score, attempts, correct, ease, interval_d,
                   last_seen, next_due) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(student_id, topic_id) DO UPDATE SET score=excluded.score,
                   attempts=excluded.attempts, correct=excluded.correct, ease=excluded.ease,
                   interval_d=excluded.interval_d, last_seen=excluded.last_seen, next_due=excluded.next_due""",
                (student_id, item["topic_id"], new_score, new_attempts, new_correct,
                 new_ease, new_interval, timestamp, next_due),
            )
            connection.commit()
            return result
        finally:
            if owns_connection:
                connection.close()

    def due_topics(self, student_id):
        connection, owns_connection = self._connect()
        try:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                """SELECT t.*, m.score, m.attempts, m.next_due FROM mastery m
                   JOIN topics t ON t.id = m.topic_id
                   WHERE m.student_id = ? AND m.next_due <= ?
                   ORDER BY m.next_due, t.seq""", (student_id, self._today()),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            if owns_connection:
                connection.close()


def _choices(value):
    import json
    return json.loads(value) if value else []


def record_attempt(db, student_id, item_id, raw_answer):
    return MasteryService(db).record_attempt(student_id, item_id, raw_answer)


def due_topics(db, student_id):
    return MasteryService(db).due_topics(student_id)
