"""שירות השיחה - התזמור בין בטיחות, ניתוב וסוכנים.

זו השכבה שהחליפה את dispatch: היא לא יודעת מה זה streamlit ומה זה CLI, ולכן
אותה לוגיקה משרתת את שני הממשקים. הכל מוזרק דרך הבנאי - אין כאן import של
תשתית ואין יצירת אובייקטים בזמן ריצה.
"""

from typing import Optional
import logging

from ..content.seed_content import next_topic, prerequisite_names
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
                 conversation_log: ConversationLog, router: Optional[Router] = None,
                 content_db=None, mastery=None, track: Optional[str] = None,
                 transcripts=None):
        self._agents = agent_factory
        self._safety = safety_policy
        self._log = conversation_log
        self._router = router or Router()
        self._content_db = content_db
        self._mastery = mastery
        self._track = track
        self._transcripts = transcripts

    def _guard(self, text, student_id):
        if not (self._content_db and self._track == "finlit" and student_id):
            return text
        from ..content.grader import check_finance_output
        result = check_finance_output(text)
        if not result["ok"]:
            logging.getLogger(__name__).warning("Financial output blocked: %s", result["reason"])
            return result["replacement"]
        return text

    def _record(self, conversation_id, student_id, speaker, text, is_safety=False):
        """כותב תור לתמליל. תקלת כתיבה לא תפיל שיחה עם תלמיד."""
        if not (self._transcripts and conversation_id and student_id):
            return
        try:
            self._transcripts.add_turn(
                conversation_id, student_id, speaker, text, is_safety)
        except Exception:
            logging.getLogger(__name__).exception("Failed to record turn")

    def handle(self, text: str, tutor, student_id: Optional[str] = None,
               conversation_id: Optional[str] = None) -> Turn:
        """הבדיקה הבטיחותית קודמת לניתוב ולכל קריאה למודל - זו הנקודה כולה.

        אם זוהתה מצוקה, אף סוכן לא נשאל: לא Tutor, לא Router, ולא Reasoning.
        """
        self._record(conversation_id, student_id, "student", text)

        finding = self._safety.inspect(text)
        if finding:
            self._log.log_alert(student_id, finding, text)
            turn = Turn(
                speaker="yoni",
                text=self._safety.escalation_message(finding),
                safety=finding,
                model_called=False,
            )
            # התמליל מסמן שהיה כאן רגע של מצוקה, אבל התוכן הרגיש נשאר
            # בתיקיית התלמיד בלבד - ולכן is_safety מוציא אותו מהזיכרון של יוני.
            self._record(conversation_id, student_id, "yoni", turn.text, True)
            return turn

        intent = self._router.route(text)
        if intent == "build":
            return Turn(speaker="system", text=BUILD_NOTICE, model_called=False)
        if intent == "quiz":
            return Turn(speaker="system", text=text, action="start_quiz", model_called=False)
        if intent == "reason":
            problem = text.strip()[len(REASON_PREFIX):].strip() or text
            reply = self._agents.create("reasoning").solve(problem)
            answer = self._guard(reply, student_id)
            self._record(conversation_id, student_id, "yoni", answer)
            return Turn(speaker="yoni", text=answer)

        answer = self._guard(tutor.ask(text), student_id)
        self._record(conversation_id, student_id, "yoni", answer)
        return Turn(speaker="yoni", text=answer)

    def _suggested_topic(self, status, student_id) -> str:
        """מה *היה* מתאים ללמוד - הצעה, לא סדר יום.

        הניסוח כאן חשוב לא פחות מהתוכן: הטקסט הזה נכנס לפרומפט, וכשהוא נוסח
        כ"נושא במסלול X" המודל קרא אותו כהוראה והתחיל כל שיחה בדחיפת הנושא.
        """
        if self._content_db and self._mastery and student_id and self._track:
            due = self._mastery.due_topics(student_id)
            topic = due[0] if due else next_topic(self._content_db, student_id, self._track)
            if topic:
                names = ", ".join(prerequisite_names(self._content_db, topic["id"]))
                return (
                    f"אם וכאשר התלמיד ישאל 'מה נלמד' או יבקש הצעה, הנושא הבא "
                    f"שמתאים לו הוא: {topic['name_he']} — {topic['summary_he']}."
                    + (f" (נושאי יסוד: {names})" if names else "")
                )
        if status is not None and status.current_brick:
            brick = status.current_brick
            return (
                f"אם וכאשר התלמיד יבקש הצעה, יש נושא שנשאר פתוח מפעם קודמת: "
                f"{brick.topic} — {brick.description}."
            )
        return ""

    def memory(self, student_id: Optional[str], limit: int = 12,
               exclude: Optional[str] = None):
        """התורות האחרונים משיחות קודמות - הזיכרון שיוני נכנס איתו לשיחה."""
        if not (self._transcripts and student_id):
            return []
        try:
            return list(self._transcripts.recent_turns(student_id, limit, exclude))
        except Exception:
            logging.getLogger(__name__).exception("Failed to load memory")
            return []

    def new_tutor(self, status: Optional[StudentStatus] = None,
                  student_id: Optional[str] = None,
                  conversation_id: Optional[str] = None):
        """סוכן הוראה חדש: זוכר שיחות קודמות, ולא מכתיב נושא."""
        tutor = self._agents.create(
            "tutor", context=self._suggested_topic(status, student_id))
        past = self.memory(student_id, exclude=conversation_id)
        if past and hasattr(tutor, "remember"):
            tutor.remember([(t["speaker"], t["text"]) for t in past])
        return tutor

    def resume_tutor(self, conversation_id: str, status=None, student_id=None):
        """בונה מחדש סוכן על שיחה קיימת - אחרי רענון דף או סגירת דפדפן."""
        tutor = self.new_tutor(status, student_id, conversation_id)
        if self._transcripts and hasattr(tutor, "load_history"):
            turns = [t for t in self._transcripts.turns(conversation_id)
                     if not t.get("is_safety")]
            tutor.load_history([(t["speaker"], t["text"]) for t in turns])
        return tutor

    def end_session(self, tutor, student_id: Optional[str],
                    conversation_id: Optional[str] = None) -> str:
        summary = tutor.summarize()
        self._log.log_session(student_id, summary, tutor.message_count)
        guarded = self._guard(summary, student_id)
        if self._transcripts and conversation_id:
            try:
                self._transcripts.finish_for(student_id, conversation_id, guarded)
            except Exception:
                logging.getLogger(__name__).exception("Failed to close conversation")
        return guarded

    def greeting(self, student: Student, status: Optional[StudentStatus] = None,
                 last_session: Optional[dict] = None) -> str:
        """ברכת פתיחה - קוד בלבד, בלי קריאה למודל. מהירה, וצפויה.

        הברכה מזכירה מה היה, אבל *לא* מציעה להמשיך בו. השאלה הפתוחה "במה
        תרצה לעסוק?" משאירה את ההגה אצל התלמיד; קודם נשאל כאן "רוצה להמשיך
        מאיפה שעצרנו?", וזו שאלה שמזמינה תשובה אחת בלבד.
        """
        name = student.name or student.student_id
        if student.is_new:
            return (
                f"שלום {name}, נעים להכיר! 👋 אני יוני. "
                "מהיום אני אזכור את ההתקדמות שלך - במה תרצה להתחיל?"
            )
        if last_session and last_session.get("summary"):
            return (
                f"שלום {name}, טוב לראות אותך שוב! 👋 "
                f"רק שתדע שאני זוכר — בפעם הקודמת ({last_session.get('date', '')}): "
                f"{last_session['summary']}\n\nבמה תרצה לעסוק היום?"
            )
        return f"שלום {name}, טוב לראות אותך שוב! 👋 במה נעסוק היום?"
