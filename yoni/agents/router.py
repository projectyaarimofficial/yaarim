from .quiz import Quiz
from .reasoning import Reasoning
from .tutor import Tutor

BUILD_PREFIX = "/build"
REASON_PREFIX = "/reason"

QUIZ_KEYWORDS = ("מבחן", "שאלון", "בחן אותי", "תרגיל", "quiz", "test me")
CHAT_KEYWORDS = ("מה זה", "איך", "למה", "תסביר", "explain", "what is", "how does")


class Router:
    """מנתב מבוסס-חוקים בלבד (בלי קריאה למודל).

    מצב build/dev הוא MODE מפורש (prefix "/build"), לא כוונה שמוסקת ממילות מפתח -
    שאלה של תלמיד על קוד היא מקרה של Tutor, לא של Builder.
    """

    AGENT_MAP = {
        "chat": Tutor,
        "quiz": Quiz,
        "reason": Reasoning,
        # "build" לא ממופה כאן בכוונה - זה dev tooling (yoni.dev), לא סוכן מול תלמיד
    }

    def is_build_command(self, text):
        return text.strip().lower().startswith(BUILD_PREFIX)

    def is_reason_command(self, text):
        # מצב מפורש, כמו /build - כבד (8B), לכן מופעל בכוונה ולא ממילות מפתח.
        return text.strip().lower().startswith(REASON_PREFIX)

    def classify(self, text):
        lower = text.lower()
        if any(keyword in lower for keyword in QUIZ_KEYWORDS):
            return "quiz"
        if any(keyword in lower for keyword in CHAT_KEYWORDS):
            return "chat"
        return "unknown"

    def route(self, text):
        if self.is_build_command(text):
            return "build"
        if self.is_reason_command(text):
            return "reason"
        intent = self.classify(text)
        return "chat" if intent == "unknown" else intent

    def dispatch(self, text):
        """מחזיר את מחלקת הסוכן המתאימה, או None עבור 'build' (מטופל בנפרד ע"י yoni.dev)."""
        return self.AGENT_MAP.get(self.route(text))
