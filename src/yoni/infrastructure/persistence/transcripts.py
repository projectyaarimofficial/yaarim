"""תמלילי שיחות: כל תור נשמר, לא רק הסיכום.

לפני השינוי הזה נשמר רק סיכום של 2-3 משפטים בסוף שיחה, והתמליל עצמו נזרק
ברגע שהתלמיד סגר את הדפדפן. המשמעות המעשית: יוני פגש את התלמיד מחדש בכל
פעם, ואי אפשר היה לחזור ולקרוא מה בעצם נאמר.

כמו ב-ConversationLog, שני מימושים שאינם כפילות:

    SqliteTranscriptStore  מקור האמת. נשאל בשאילתה, ממשיך שיחה שנקטעה.
    FileTranscriptMirror   מראה קריאה-לאדם: קובץ JSON לכל שיחה בתיקיית התלמיד.

הכתיבה למראה לעולם לא מפילה את השיחה - תמליל שלא נכתב לקובץ הוא באג,
תלמיד שהמסך שלו קרס באמצע משפט הוא נזק.
"""

import json
import logging
import os
import sqlite3
import uuid
from contextlib import closing
from typing import List, Optional, Sequence

from ...domain.models import Conversation
from ...domain.ports import TranscriptStore

log = logging.getLogger(__name__)

TITLE_MAX = 60


def make_title(text: str) -> str:
    """כותרת לשיחה מתוך המשפט הראשון של התלמיד - קוד, בלי לשאול את המודל."""
    clean = " ".join((text or "").split())
    if len(clean) <= TITLE_MAX:
        return clean
    return clean[:TITLE_MAX].rsplit(" ", 1)[0] + "…"


class SqliteTranscriptStore(TranscriptStore):
    def __init__(self, db_path, clock):
        self._db_path = db_path
        self._clock = clock
        self.initialize()

    def _connect(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        return sqlite3.connect(self._db_path)

    def initialize(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conversation_id TEXT PRIMARY KEY,
                    student_id      TEXT NOT NULL,
                    started_at      TEXT NOT NULL,
                    ended_at        TEXT,
                    title           TEXT NOT NULL DEFAULT '',
                    summary         TEXT NOT NULL DEFAULT '',
                    message_count   INTEGER NOT NULL DEFAULT 0
                )""")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS turns (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    student_id      TEXT NOT NULL,
                    seq             INTEGER NOT NULL,
                    speaker         TEXT NOT NULL,
                    text            TEXT NOT NULL,
                    is_safety       INTEGER NOT NULL DEFAULT 0,
                    ts              TEXT NOT NULL
                )""")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_conv"
                         " ON turns (conversation_id, seq)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_student"
                         " ON turns (student_id, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_conv_student"
                         " ON conversations (student_id, started_at)")

    def start(self, student_id: str, title: str = "") -> str:
        conversation_id = uuid.uuid4().hex
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO conversations (conversation_id, student_id, started_at,"
                " title) VALUES (?, ?, ?, ?)",
                (conversation_id, student_id, self._clock.now(), title),
            )
        return conversation_id

    def add_turn(self, conversation_id, student_id, speaker, text, is_safety=False):
        with closing(self._connect()) as conn, conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM turns WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            conn.execute(
                "INSERT INTO turns (conversation_id, student_id, seq, speaker, text,"
                " is_safety, ts) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (conversation_id, student_id, row[0] + 1, speaker, text,
                 1 if is_safety else 0, self._clock.now()),
            )
            conn.execute(
                "UPDATE conversations SET message_count = message_count + 1"
                " WHERE conversation_id = ?", (conversation_id,),
            )
            # שיחה שנפתחה בלי כותרת מקבלת אותה מהמשפט הראשון של התלמיד.
            if speaker == "student":
                conn.execute(
                    "UPDATE conversations SET title = ? WHERE conversation_id = ?"
                    " AND title = ''", (make_title(text), conversation_id),
                )

    def finish(self, conversation_id: str, summary: str = "") -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "UPDATE conversations SET ended_at = ?, summary = ?"
                " WHERE conversation_id = ?",
                (self._clock.now(), summary, conversation_id),
            )

    def turns(self, conversation_id: str) -> Sequence[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT speaker, text, is_safety, ts FROM turns"
                " WHERE conversation_id = ? ORDER BY seq", (conversation_id,),
            ).fetchall()
        return [{"speaker": r[0], "text": r[1], "is_safety": bool(r[2]), "ts": r[3]}
                for r in rows]

    def _row_to_conversation(self, row) -> Conversation:
        return Conversation(
            conversation_id=row[0], student_id=row[1], started_at=row[2],
            ended_at=row[3], title=row[4], summary=row[5], message_count=row[6],
        )

    def conversations(self, student_id: str, limit: int = 50) -> Sequence[Conversation]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT conversation_id, student_id, started_at, ended_at, title,"
                " summary, message_count FROM conversations WHERE student_id = ?"
                " AND message_count > 0 ORDER BY started_at DESC LIMIT ?",
                (student_id, limit),
            ).fetchall()
        return [self._row_to_conversation(r) for r in rows]

    def open_conversation(self, student_id: str) -> Optional[Conversation]:
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT conversation_id, student_id, started_at, ended_at, title,"
                " summary, message_count FROM conversations WHERE student_id = ?"
                " AND ended_at IS NULL AND message_count > 0"
                " ORDER BY started_at DESC LIMIT 1", (student_id,),
            ).fetchone()
        return self._row_to_conversation(row) if row else None

    def recent_turns(self, student_id, limit=40, exclude=None) -> Sequence[dict]:
        """התורות האחרונים מכל השיחות, מהישן לחדש.

        exclude מוציא את השיחה הנוכחית: מה שכבר נמצא בהיסטוריה של הסוכן לא
        צריך להיכנס שוב דרך הזיכרון ארוך-הטווח.
        """
        query = ("SELECT speaker, text, ts FROM turns WHERE student_id = ?"
                 " AND is_safety = 0")
        params: list = [student_id]
        if exclude:
            query += " AND conversation_id != ?"
            params.append(exclude)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with closing(self._connect()) as conn:
            rows = conn.execute(query, params).fetchall()
        return [{"speaker": r[0], "text": r[1], "ts": r[2]} for r in reversed(rows)]

    def delete(self, student_id: str, conversation_id: str) -> bool:
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute(
                "DELETE FROM conversations WHERE conversation_id = ? AND student_id = ?",
                (conversation_id, student_id),
            )
            if not cursor.rowcount:
                return False
            # התורות נמחקים רק אחרי שאומת שהשיחה באמת של התלמיד הזה.
            conn.execute(
                "DELETE FROM turns WHERE conversation_id = ? AND student_id = ?",
                (conversation_id, student_id),
            )
        return True


class FileTranscriptMirror(TranscriptStore):
    """קובץ JSON לכל שיחה, בתיקיית התלמיד. נועד לקריאה בעין, לא לשאילתה."""

    def __init__(self, repository, clock):
        self._repo = repository
        self._clock = clock

    def _path(self, student_id, conversation_id) -> Optional[str]:
        directory = self._repo.directory(student_id) if student_id else None
        if not directory:
            return None
        folder = os.path.join(directory, "conversations")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, f"{conversation_id}.json")

    def _load(self, path) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self, path, data) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def start(self, student_id: str, title: str = "") -> str:
        # המזהה נקבע ב-SqliteTranscriptStore; המראה רק עוקבת אחריו.
        return ""

    def add_turn(self, conversation_id, student_id, speaker, text, is_safety=False):
        path = self._path(student_id, conversation_id)
        if not path:
            return
        data = self._load(path)
        data.setdefault("conversation_id", conversation_id)
        data.setdefault("student_id", student_id)
        data.setdefault("started_at", self._clock.now())
        data.setdefault("turns", []).append({
            "speaker": speaker, "text": text, "ts": self._clock.now(),
            **({"safety": True} if is_safety else {}),
        })
        self._save(path, data)

    def finish(self, conversation_id: str, summary: str = "") -> None:
        # בלי student_id אי אפשר לאתר את הקובץ; הסיכום נכתב דרך finish_for.
        return

    def finish_for(self, student_id, conversation_id, summary="") -> None:
        path = self._path(student_id, conversation_id)
        if not path or not os.path.exists(path):
            return
        data = self._load(path)
        data["ended_at"] = self._clock.now()
        data["summary"] = summary
        self._save(path, data)

    def turns(self, conversation_id: str) -> Sequence[dict]:
        return []

    def conversations(self, student_id: str, limit: int = 50) -> Sequence[Conversation]:
        return []

    def open_conversation(self, student_id: str) -> Optional[Conversation]:
        return None

    def recent_turns(self, student_id, limit=40, exclude=None) -> Sequence[dict]:
        return []

    def delete(self, student_id: str, conversation_id: str) -> bool:
        path = self._path(student_id, conversation_id)
        if not path or not os.path.exists(path):
            return False
        os.remove(path)
        return True


class CompositeTranscriptStore(TranscriptStore):
    """כותב לכל היעדים, קורא מהראשון. כישלון של מראה אינו מפיל שיחה."""

    def __init__(self, primary: TranscriptStore, *mirrors: TranscriptStore):
        self._primary = primary
        self._mirrors = mirrors

    def _mirror(self, method, *args, **kwargs) -> None:
        for mirror in self._mirrors:
            try:
                getattr(mirror, method)(*args, **kwargs)
            except Exception:  # מראה קריאה-לאדם היא נוחות, לא תלות
                log.exception("Transcript mirror failed on %s", method)

    def start(self, student_id: str, title: str = "") -> str:
        return self._primary.start(student_id, title)

    def add_turn(self, conversation_id, student_id, speaker, text, is_safety=False):
        self._primary.add_turn(conversation_id, student_id, speaker, text, is_safety)
        self._mirror("add_turn", conversation_id, student_id, speaker, text, is_safety)

    def finish(self, conversation_id: str, summary: str = "") -> None:
        self._primary.finish(conversation_id, summary)

    def finish_for(self, student_id, conversation_id, summary="") -> None:
        self._primary.finish(conversation_id, summary)
        self._mirror("finish_for", student_id, conversation_id, summary)

    def turns(self, conversation_id: str) -> Sequence[dict]:
        return self._primary.turns(conversation_id)

    def conversations(self, student_id: str, limit: int = 50) -> Sequence[Conversation]:
        return self._primary.conversations(student_id, limit)

    def open_conversation(self, student_id: str) -> Optional[Conversation]:
        return self._primary.open_conversation(student_id)

    def recent_turns(self, student_id, limit=40, exclude=None) -> Sequence[dict]:
        return self._primary.recent_turns(student_id, limit, exclude)

    def delete(self, student_id: str, conversation_id: str) -> bool:
        deleted = self._primary.delete(student_id, conversation_id)
        # המראה נמחקת גם אם המקור כבר לא היה שם - כדי לא להשאיר תמליל יתום.
        self._mirror("delete", student_id, conversation_id)
        return deleted


__all__: List[str] = [
    "CompositeTranscriptStore", "FileTranscriptMirror", "SqliteTranscriptStore",
    "make_title",
]
