"""אחסון מבוסס קבצים: פרופילי תלמידים ויומנים יומיים.

מבנה: students/<demo|real>/<student_id>/{profile,status}.json + sessions/ + quiz_results/ + alerts/
"""

import json
import os
from typing import Any, Dict, List, Optional

from ...domain.models import (
    Brick, GradeResult, Question, SafetyFinding, Student, StudentStatus,
)

from ...domain.ports import ConversationLog, StudentRepository

KINDS = ("demo", "real")


def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class FileStudentRepository(StudentRepository):
    def __init__(self, students_dir, clock):
        self._root = students_dir
        self._clock = clock

    def directory(self, student_id: Optional[str]) -> Optional[str]:
        """נתיב תיקיית התלמיד (מחפש ב-demo ואז ב-real), או None."""
        student_id = (student_id or "").strip()
        if not student_id:
            return None
        for kind in KINDS:
            path = os.path.join(self._root, kind, student_id)
            if os.path.isdir(path):
                return path
        return None

    def find(self, student_id: str) -> Optional[Student]:
        directory = self.directory(student_id)
        if not directory:
            return None
        raw = _read_json(os.path.join(directory, "profile.json"))
        if not raw:
            return None
        return Student(
            student_id=raw.get("student_id", student_id),
            name=raw.get("name", ""),
            is_demo=bool(raw.get("is_demo", False)),
            grade=raw.get("grade"),
            language=raw.get("language", "he"),
            created_at=raw.get("created_at", self._clock.today()),
            notes=raw.get("notes", ""),
        )

    def create(self, student_id: str, name: str, is_demo: bool = False) -> Student:
        student = Student(
            student_id=student_id.strip(),
            name=name.strip(),
            is_demo=is_demo,
            created_at=self._clock.today(),
            is_new=True,
        )
        directory = os.path.join(self._root, student.kind, student.student_id)
        for sub in ("sessions", "quiz_results", "alerts"):
            os.makedirs(os.path.join(directory, sub), exist_ok=True)

        _write_json(os.path.join(directory, "profile.json"), {
            "student_id": student.student_id,
            "is_demo": student.is_demo,
            "name": student.name,
            "grade": student.grade,
            "language": student.language,
            "created_at": student.created_at,
            "notes": student.notes,
        })
        status_path = os.path.join(directory, "status.json")
        if not os.path.exists(status_path):
            _write_json(status_path, {
                "student_id": student.student_id,
                "updated_at": self._clock.today(),
                "missing_bricks": [],
            })
        return student

    def status(self, student_id: str) -> StudentStatus:
        directory = self.directory(student_id)
        raw = _read_json(os.path.join(directory, "status.json")) if directory else None
        if not raw:
            return StudentStatus(student_id=student_id, updated_at=self._clock.today())
        bricks = tuple(
            Brick(
                topic=b.get("topic", ""),
                description=b.get("brick", ""),
                status=b.get("status", "open"),
            )
            for b in raw.get("missing_bricks", [])
        )
        return StudentStatus(
            student_id=raw.get("student_id", student_id),
            bricks=bricks,
            updated_at=raw.get("updated_at", self._clock.today()),
        )

    def open_brick(self, student_id: str, topic: str,
                   description: str = "") -> Optional[str]:
        """פותח לבנה חסרה. זה מה שסוגר את הלולאה: טעות במבחן הופכת לנושא פתוח."""
        directory = self.directory(student_id)
        if not directory:
            return None
        path = os.path.join(directory, "status.json")
        raw = _read_json(path) or {"student_id": student_id, "missing_bricks": []}
        existing = raw.setdefault("missing_bricks", [])
        for brick in existing:
            if brick.get("topic") == topic and brick.get("status") == "open":
                return path  # כבר פתוח - לא מכפילים
        existing.append({"topic": topic, "brick": description, "status": "open"})
        raw["updated_at"] = self._clock.today()
        _write_json(path, raw)
        return path

    def list_all(self) -> List[Student]:
        result = []
        for kind in KINDS:
            base = os.path.join(self._root, kind)
            if not os.path.isdir(base):
                continue
            for student_id in sorted(os.listdir(base)):
                if os.path.isdir(os.path.join(base, student_id)):
                    student = self.find(student_id)
                    if student:
                        result.append(student)
        return result


class FileConversationLog(ConversationLog):
    """יומנים יומיים בתיקיית התלמיד - קריאים לאדם, לא רק למכונה."""

    def __init__(self, repository, clock):
        self._repo = repository
        self._clock = clock

    def _append(self, student_id, subdir, list_key, record):
        directory = self._repo.directory(student_id) if student_id else None
        if not directory:
            return None
        day = self._clock.today()
        path = os.path.join(directory, subdir, f"{day}.json")
        data = _read_json(path) or {"date": day, "student_id": student_id, list_key: []}
        data.setdefault(list_key, []).append(record)
        _write_json(path, data)
        return path

    def log_session(self, student_id: Optional[str], summary: str,
                    message_count: int) -> Optional[str]:
        return self._append(student_id, "sessions", "sessions", {
            "summary": summary, "message_count": message_count,
        })

    def log_quiz_result(self, student_id: Optional[str], question: Question,
                        answer: str, result: GradeResult) -> Optional[str]:
        # רשומה הטרוגנית במכוון (str · None · bool) - כך היא נשמרת ל-JSON.
        record: Dict[str, Any] = {
            "topic": question.topic,
            "question": question.question,
            "type": question.type,
            "student_answer": answer,
        }
        if question.is_closed:
            record["correct_answer"] = question.correct_answer
        record["correct"] = bool(result.correct)
        record["graded_by"] = result.graded_by
        return self._append(student_id, "quiz_results", "results", record)

    def log_alert(self, student_id: Optional[str], finding: SafetyFinding,
                  text: str) -> Optional[str]:
        return self._append(student_id, "alerts", "alerts", {
            "timestamp": self._clock.now(),
            "category": finding.category,
            "label": finding.label,
            "matched": list(finding.matched),
            "student_text": text,
            "handled_by": "escalation (model was not called)",
        })

    def last_session(self, student_id: str) -> Optional[dict]:
        directory = self._repo.directory(student_id)
        folder = os.path.join(directory, "sessions") if directory else None
        if not folder or not os.path.isdir(folder):
            return None
        for filename in sorted(os.listdir(folder), reverse=True):
            if not filename.endswith(".json"):
                continue
            data = _read_json(os.path.join(folder, filename))
            sessions = (data or {}).get("sessions") or []
            if sessions:
                entry = dict(sessions[-1])
                entry["date"] = (data or {}).get("date", filename[:-5])
                return entry
        return None
