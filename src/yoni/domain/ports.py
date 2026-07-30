"""הפורטים: החוזים שהליבה מגדירה, והתשתית מממשת.

כל פורט כאן קיים כי יש לו *לפחות שני* מימושים אמיתיים או שני צרכנים אמיתיים -
לא הפשטה ספקולטיבית:

    LanguageModel     Ollama בפועל, Fake בבדיקות
    ConversationLog   SQLite וגם קבצי JSON יומיים (וגם Composite שכותב לשניהם)
    StudentRepository קבצים היום, אפשר SQL מחר, בלי לגעת בליבה
    SafetyPolicy      מילות מפתח היום; אפשר להחליף בלי לגעת בשיחה
    WritePolicy       גדר הפרויקט; בבדיקות אפשר גדר על תיקייה זמנית

זו ההפרדה שמאפשרת להזריק (dependency injection) במקום ליצור תלות בתוך המחלקה.

החתימות מוערות (type hints) בכוונה: החוזה חייב לומר *מה* עובר בו. בלי זה, מי
שמממש פורט צריך לקרוא את המימוש הקיים כדי לנחש - וזו בדיוק התלות שהפורט אמור למנוע.
"""

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from .models import (
    Brick,
    GradeResult,
    Question,
    SafetyFinding,
    Student,
    StudentStatus,
)


class LanguageModelError(Exception):
    """תקלה בתקשורת עם המודל. השכבות שמעל לא רואות חריגות של requests."""


class LanguageModel(ABC):
    """מודל שפה. הליבה מדברת רק דרך הממשק הזה."""

    @abstractmethod
    def complete(self, prompt: str, model: Optional[str] = None,
                 expect_json: bool = False) -> str:
        """מחזיר טקסט. זורק LanguageModelError בכישלון."""

    @abstractmethod
    def embed(self, text: str, model: Optional[str] = None) -> Sequence[float]:
        """מחזיר וקטור embedding."""


class StudentRepository(ABC):
    """קריאה וכתיבה של תלמידים ומצבם."""

    @abstractmethod
    def find(self, student_id: str) -> Optional[Student]:
        """Student או None."""

    @abstractmethod
    def create(self, student_id: str, name: str, is_demo: bool = False) -> Student:
        """יוצר ומחזיר Student."""

    @abstractmethod
    def status(self, student_id: str) -> StudentStatus:
        """StudentStatus (ריק אם אין)."""

    @abstractmethod
    def list_all(self) -> Sequence[Student]:
        """רשימת Student."""

    @abstractmethod
    def open_brick(self, student_id: str, topic: str,
                   description: str = "") -> Optional[str]:
        """פותח לבנה חסרה ומחזיר את נתיב הקובץ שנכתב, או None.

        זה מה שסוגר את הלולאה: טעות במבחן הופכת לנושא פתוח שחוזר בשיעור הבא.
        """


class ConversationLog(ABC):
    """תיעוד: סיכומי שיחות, תוצאות מבחן, והתרעות מצוקה."""

    @abstractmethod
    def log_session(self, student_id: Optional[str], summary: str,
                    message_count: int) -> object:
        ...

    @abstractmethod
    def log_quiz_result(self, student_id: Optional[str], question: Question,
                        answer: str, result: GradeResult) -> object:
        ...

    @abstractmethod
    def log_alert(self, student_id: Optional[str], finding: SafetyFinding,
                  text: str) -> object:
        ...

    @abstractmethod
    def last_session(self, student_id: str) -> Optional[dict]:
        """dict עם summary ו-date, או None."""


class SafetyPolicy(ABC):
    """מדיניות בטיחות: מזהה מצוקה לפני שהמודל נשאל."""

    @abstractmethod
    def inspect(self, text: Optional[str]) -> Optional[SafetyFinding]:
        """SafetyFinding או None."""

    @abstractmethod
    def escalation_message(self, finding: Optional[SafetyFinding] = None) -> str:
        """הטקסט שמופנה לתלמיד במקום תשובת המודל."""


class WritePolicy(ABC):
    """מי מחליט לאן מותר לכתוב. זו האכיפה של כלל 1 בחוקה."""

    @abstractmethod
    def resolve(self, target: Optional[str]) -> str:
        """נתיב מוחלט ומאושר, או זורק WriteDenied."""


class WriteDenied(Exception):
    """נתיב היעד נדחה - מחוץ לגבול המותר."""


class PasswordStore(ABC):
    """אחסון ואימות סיסמאות."""

    @abstractmethod
    def exists(self, user_id: str) -> bool:
        ...

    @abstractmethod
    def create(self, user_id: str, password: str) -> None:
        """זורק ValueError אם חסר מידע או שהמזהה תפוס."""

    @abstractmethod
    def verify(self, user_id: str, password: str) -> bool:
        ...


class Clock(ABC):
    """זמן כתלות מוזרקת - כדי שבדיקות לא יהיו תלויות בשעון האמיתי."""

    @abstractmethod
    def today(self) -> str:
        """YYYY-MM-DD"""

    @abstractmethod
    def now(self) -> str:
        """ISO-8601, שניות"""


__all__ = [
    "Brick", "Clock", "ConversationLog", "GradeResult", "LanguageModel",
    "LanguageModelError", "PasswordStore", "Question", "SafetyFinding",
    "SafetyPolicy", "Student", "StudentStatus", "StudentRepository",
    "WriteDenied", "WritePolicy",
]
