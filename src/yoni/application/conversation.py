"""שירות השיחה - התזמור בין בטיחות, ניתוב וסוכנים.

זו השכבה שהחליפה את dispatch: היא לא יודעת מה זה streamlit ומה זה CLI, ולכן
אותה לוגיקה משרתת את שני הממשקים. הכל מוזרק דרך הבנאי - אין כאן import של
תשתית ואין יצירת אובייקטים בזמן ריצה.
"""

from typing import Optional

from ..domain.models import Student, StudentStatus, Turn
from ..domain.ports import ConversationLog, SafetyPolicy

BUILD_NOTICE = "🛠️ פקודות /build מטופלות ב-CLI, לא כאן."
BUILD_PREFIX = "/build"
REASON_PREFIX = "/reason"

QUIZ_KEYWORDS = ("מבחן", "שאלון", "בחן אותי", "תרגיל", "quiz", "test me")
CHAT_KEYWORDS = ("מה זה", "איך", "למה", "תסביר", "explain", "what is", "how does")


class Router:
    """ניתוב מבוסס-חוקים בלבד, בלי קריאה למודל.

    build ו-reason הם מצבים *מפורשים* (prefix), לא כוונות שמוסקות ממילות מפתח:
    שאלה של תלמיד על קוד היא מקרה של Tutor, לא של Builder.
    """

    def is_build(self, text: str) -> bool:
        return text.strip().lower().startswith(BUILD_PREFIX)

    def is_reason(self, text: str) -> bool:
        return text.strip().lower().startswith(REASON_PREFIX)

    def classify(self, text: str) -> str:
        lower = text.lower()
        if any(k in lower for k in QUIZ_KEYWORDS):
            return "quiz"
        if any(k in lower for k in CHAT_KEYWORDS):
            return "chat"
        return "unknown"

    def route(self, text: str) -> str:
        if self.is_build(text):
            return "build"
        if self.is_reason(text):
            return "reason"
        intent = self.classify(text)
        return "chat" if intent == "unknown" else intent


class ConversationService:
    """מטפל בהודעה אחת של תלמיד ומחזיר Turn."""

    def __init__(self, agent_factory, safety_policy: SafetyPolicy,
                 conversation_log: ConversationLog, router: Optional[Router] = None):
        self._agents = agent_factory
        self._safety = safety_policy
        self._log = conversation_log
        self._router = router or Router()

    def handle(self, text: str, tutor, student_id: Optional[str] = None) -> Turn:
        """הבדיקה הבטיחותית קודמת לניתוב ולכל קריאה למודל - זו הנקודה כולה.

        אם זוהתה מצוקה, אף סוכן לא נשאל: לא Tutor, לא Router, ולא Reasoning.
        """
        finding = self._safety.inspect(text)
        if finding:
            self._log.log_alert(student_id, finding, text)
            return Turn(
                speaker="yoni",
                text=self._safety.escalation_message(finding),
                safety=finding,
                model_called=False,
            )

        intent = self._router.route(text)
        if intent == "build":
            return Turn(speaker="system", text=BUILD_NOTICE, model_called=False)
        if intent == "quiz":
            return Turn(speaker="system", text=text, action="start_quiz", model_called=False)
        if intent == "reason":
            problem = text.strip()[len(REASON_PREFIX):].strip() or text
            return Turn(speaker="yoni", text=self._agents.create("reasoning").solve(problem))

        return Turn(speaker="yoni", text=tutor.ask(text))

    def new_tutor(self, status: Optional[StudentStatus] = None):
        """סוכן הוראה חדש, עם רקע על מה שהתלמיד עדיין חייב."""
        context = ""
        if status is not None and status.current_brick:
            brick = status.current_brick
            context = f"נושא פתוח שדורש חיזוק: {brick.topic} — {brick.description}"
        return self._agents.create("tutor", context=context)

    def end_session(self, tutor, student_id: Optional[str]) -> str:
        summary = tutor.summarize()
        self._log.log_session(student_id, summary, tutor.message_count)
        return summary

    def greeting(self, student: Student, status: Optional[StudentStatus] = None,
                 last_session: Optional[dict] = None) -> str:
        """ברכת פתיחה - קוד בלבד, בלי קריאה למודל. מהירה, וצפויה."""
        name = student.name or student.student_id
        if student.is_new:
            return (
                f"שלום {name}, נעים להכיר! 👋 אני יוני. "
                "מהיום אני אזכור את ההתקדמות שלך - במה תרצה להתחיל?"
            )
        if last_session and last_session.get("summary"):
            return (
                f"שלום {name}, טוב לראות אותך שוב! 👋 "
                f"בפעם הקודמת ({last_session.get('date', '')}): {last_session['summary']} "
                "רוצה להמשיך מאיפה שעצרנו?"
            )
        if status is not None and status.current_brick:
            return (
                f"שלום {name}, טוב לראות אותך שוב! 👋 "
                f"יש לנו עדיין נושא פתוח לחיזוק: {status.current_brick.topic}. רוצה שנמשיך בו?"
            )
        return f"שלום {name}, טוב לראות אותך שוב! 👋 במה נעסוק היום?"
