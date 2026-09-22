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
    Conversation,
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


class TranscriptStore(ABC):
    """התמליל המלא של השיחות - כל תור, לא רק הסיכום.

    ConversationLog שומר *מסקנות* (סיכום, ציון, התרעה). כאן נשמר מה שנאמר
    בפועל, וזה מה שמאפשר גם להמשיך שיחה אחרי שהדפדפן נסגר וגם ליוני לזכור
    שיחות קודמות במקום לפגוש את התלמיד מאפס בכל פעם.

    שני מימושים אמיתיים: SQLite (נשאל בשאילתה) וקבצי JSON בתיקיית התלמיד
    (נפתחים ונקראים בעין) - אותה הפרדה שכבר קיימת ב-ConversationLog.
    """

    @abstractmethod
    def start(self, student_id: str, title: str = "") -> str:
        """פותח שיחה חדשה ומחזיר את המזהה שלה."""

    @abstractmethod
    def add_turn(self, conversation_id: str, student_id: str, speaker: str,
                 text: str, is_safety: bool = False) -> None:
        """מוסיף תור. חייב להיות עמיד: כישלון כתיבה לא יפיל את השיחה."""

    @abstractmethod
    def finish(self, conversation_id: str, summary: str = "") -> None:
        """סוגר שיחה. summary אופציונלי - שיחה שנקטעה נסגרת בלעדיו."""

    @abstractmethod
    def turns(self, conversation_id: str) -> Sequence[dict]:
        """כל התורות בשיחה, לפי הסדר. dict עם speaker · text · ts."""

    @abstractmethod
    def conversations(self, student_id: str, limit: int = 50) -> Sequence[Conversation]:
        """שיחות התלמיד, החדשה ראשונה."""

    @abstractmethod
    def open_conversation(self, student_id: str) -> Optional[Conversation]:
        """השיחה הפתוחה האחרונה, אם יש - כדי להמשיך אותה ולא לפתוח חדשה."""

    @abstractmethod
    def recent_turns(self, student_id: str, limit: int = 40,
                     exclude: Optional[str] = None) -> Sequence[dict]:
        """התורות האחרונים *מכל* השיחות - הזיכרון ארוך-הטווח של יוני."""

    @abstractmethod
    def delete(self, student_id: str, conversation_id: str) -> bool:
        """מוחק שיחה ואת כל התורות שלה. student_id נדרש כדי שלא נמחק
        שיחה של תלמיד אחר בגלל מזהה שהודבק בטעות."""


class SpeechSynthesizer(ABC):
    """הופך טקסט עברי לדיבור. מקומי בלבד - שום טקסט של תלמיד לא יוצא מהמכונה.

    הדיבור הוא מצב הבסיס של יוני, לא קישוט: תלמיד שמתקשה בקריאה לומד טוב
    יותר כששומעים לו. הכתב נשאר זמין דרך מתג.
    """

    @abstractmethod
    def speak(self, text: str) -> Optional[bytes]:
        """WAV שלם כ-bytes, או None אם הדיבור אינו זמין.

        None הוא תשובה לגיטימית: אם מנוע הדיבור חסר, השיעור נמשך בכתב.
        """

    @property
    @abstractmethod
    def available(self) -> bool:
        """האם אפשר לדבר עכשיו - בלי לנסות ולהיכשל מול התלמיד."""


class SpeechTranscriber(ABC):
    """הופך הקלטה של התלמיד לטקסט. גם כאן - מקומי בלבד."""

    @abstractmethod
    def transcribe(self, audio: bytes) -> str:
        """טקסט בעברית, או מחרוזת ריקה אם לא זוהה דבר."""

    @property
    @abstractmethod
    def available(self) -> bool:
        ...


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
    "Brick", "Clock", "Conversation", "ConversationLog", "GradeResult",
    "LanguageModel", "LanguageModelError", "PasswordStore", "Question",
    "SafetyFinding", "SafetyPolicy", "Student", "StudentStatus",
    "SpeechSynthesizer", "SpeechTranscriber", "StudentRepository",
    "TranscriptStore", "WriteDenied", "WritePolicy",
]
