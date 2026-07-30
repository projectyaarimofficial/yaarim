"""ישויות הליבה. שכבה זו לא יודעת דבר על SQLite, על Ollama או על streamlit.

כל אובייקט כאן הוא immutable (frozen dataclass): מי שרוצה לשנות מקבל עותק חדש.
זה מונע תופעות לוואי סמויות - הבעיה הנפוצה ביותר כשמעבירים dict בין שכבות.
"""

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Brick:
    """לבנה בקיר הידע של התלמיד: נושא שנרכש (closed) או חסר (open)."""

    topic: str
    description: str = ""
    status: str = "open"

    @property
    def is_open(self) -> bool:
        return self.status == "open"


@dataclass(frozen=True)
class Student:
    """תלמיד. is_demo נשמר על האובייקט עצמו כדי שהמידע ישרוד גם אם קובץ יזוז."""

    student_id: str
    name: str
    is_demo: bool = False
    grade: Optional[str] = None
    language: str = "he"
    created_at: str = field(default_factory=lambda: date.today().isoformat())
    notes: str = ""
    is_new: bool = False

    @property
    def kind(self) -> str:
        return "demo" if self.is_demo else "real"

    def as_returning(self) -> "Student":
        return replace(self, is_new=False)


@dataclass(frozen=True)
class StudentStatus:
    """מצב לימודי: אילו לבנים חסרות. הלבנה הפתוחה הראשונה היא "מה שעכשיו"."""

    student_id: str
    bricks: tuple = ()
    updated_at: str = field(default_factory=lambda: date.today().isoformat())

    @property
    def open_bricks(self) -> tuple:
        return tuple(b for b in self.bricks if b.is_open)

    @property
    def current_brick(self) -> Optional[Brick]:
        return self.open_bricks[0] if self.open_bricks else None


@dataclass(frozen=True)
class Question:
    """שאלה במבחן. הסוג קובע *מי* בודק אותה - קוד או מודל."""

    question: str
    type: str
    topic: Optional[str] = None
    options: tuple = ()
    correct_answer: Optional[str] = None
    rubric: Optional[str] = None

    MULTIPLE_CHOICE = "multiple_choice"
    EXACT = "exact"
    OPEN = "open"

    @property
    def is_closed(self) -> bool:
        """תשובה יחידה ומדויקת - נבדקת בקוד בלבד, לעולם לא דרך המודל."""
        return self.type in (self.MULTIPLE_CHOICE, self.EXACT)


@dataclass(frozen=True)
class GradeResult:
    correct: bool
    feedback: str
    graded_by: str = "code"  # "code" | "model" - שקיפות על מי הכריע


@dataclass(frozen=True)
class SafetyFinding:
    """ממצא מצוקה. קיומו של אובייקט כזה עוצר את השיחה לפני כל קריאה למודל."""

    category: str
    label: str
    matched: tuple = ()


@dataclass(frozen=True)
class Turn:
    """תור בשיחה. model_called מתעד אם המודל בכלל נשאל - חשוב לביקורת."""

    speaker: str
    text: str
    safety: Optional[SafetyFinding] = None
    action: Optional[str] = None
    model_called: bool = True


@dataclass(frozen=True)
class BuildPlan:
    """תוכנית שינוי קוד שהמודל הציע. target_file עדיין לא מאומת בשלב הזה."""

    summary: str
    target_file: Optional[str] = None
    file_exists: bool = False
