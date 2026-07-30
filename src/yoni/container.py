"""שורש ההרכבה (composition root) - המקום היחיד שבו נוצרים אובייקטים קונקרטיים.

זה מה שהופך "הזרקת תלויות" ממילה לתכונה: אף מחלקה במערכת לא בונה את התלויות
שלה. הן מגיעות מכאן. לכן אפשר להחליף מימוש (מודל מדומה, מדיניות כתיבה אחרת,
אחסון אחר) בלי לגעת בשום קובץ אחר - וזה בדיוק מה שהבדיקות עושות.

הבנייה עצלה (lazy): רכיב נוצר בפעם הראשונה שמבקשים אותו, פעם אחת.
"""

from .agents.factory import AgentFactory
from .application.assessment import AssessmentService
from .application.authoring import AuthoringService
from .application.conversation import ConversationService
from .config import settings as settings_module
from .domain.ports import Clock
from .infrastructure.persistence.files import FileConversationLog, FileStudentRepository
from .infrastructure.persistence.sqlite import (
    CompositeConversationLog,
    SqliteConversationLog,
)
from .infrastructure.safety.keywords import KeywordSafetyPolicy
from .infrastructure.security.passwords import SqlitePasswordStore
from .infrastructure.security.paths import ProjectWritePolicy

# מימושים שגוררים תלות חיצונית (requests) מיובאים בעצלתיים, בתוך המתודה.
# כך אפשר להריץ את כל המערכת עם מודל מוזרק - בלי להתקין דבר. זו בדיקה חיה
# להפרדה: אם הליבה הייתה תלויה בתשתית, השורה הזו לא הייתה אפשרית.


class SystemClock(Clock):
    def today(self):
        from datetime import date
        return date.today().isoformat()

    def now(self):
        from datetime import datetime
        return datetime.now().isoformat(timespec="seconds")


class Container:
    """מחזיק את התצורה ובונה את הגרף. כל תלות ניתנת לדריסה בבנאי."""

    def __init__(self, settings=None, language_model=None, clock=None, write_policy=None):
        self.settings = settings or settings_module.from_env()
        self._clock = clock or SystemClock()
        self._language_model = language_model  # הזרקה בבדיקות
        self._write_policy = write_policy
        self._cache = {}

    def _get(self, key, build):
        if key not in self._cache:
            self._cache[key] = build()
        return self._cache[key]

    # ---- תשתית ---------------------------------------------------------
    @property
    def clock(self):
        return self._clock

    @property
    def vram(self):
        def build():
            from .infrastructure.llm.vram import VramBudget
            return VramBudget(self.settings)
        return self._get("vram", build)

    @property
    def language_model(self):
        if self._language_model is not None:
            return self._language_model

        def build():
            from .infrastructure.llm.ollama import OllamaLanguageModel
            return OllamaLanguageModel(self.settings, self.vram)
        return self._get("llm", build)

    @property
    def write_policy(self):
        if self._write_policy is not None:
            return self._write_policy
        return self._get("write_policy", lambda: ProjectWritePolicy(self.settings.project_root))

    @property
    def benchmark(self):
        def build():
            from .infrastructure.llm.benchmark import ModelBenchmark
            return ModelBenchmark(self.settings, self.vram)
        return self._get("benchmark", build)

    @property
    def repository(self):
        return self._get("repo", lambda: FileStudentRepository(
            self.settings.students_dir, self._clock))

    @property
    def sqlite_log(self):
        return self._get("sqlite_log", lambda: SqliteConversationLog(self.settings.db_path))

    @property
    def conversation_log(self):
        """שני יעדים במפורש: קבצים לקריאה אנושית, SQL לשאילתות מצטברות."""
        return self._get("log", lambda: CompositeConversationLog(
            FileConversationLog(self.repository, self._clock),
            self.sqlite_log,
        ))

    @property
    def safety_policy(self):
        return self._get("safety", lambda: KeywordSafetyPolicy(self.settings.safety_config_path))

    @property
    def passwords(self):
        return self._get("passwords", lambda: SqlitePasswordStore(self.settings.db_path))

    # ---- סוכנים ושירותים ------------------------------------------------
    @property
    def agent_factory(self):
        return self._get("agents", lambda: AgentFactory(self.language_model, self.settings))

    @property
    def conversation(self):
        return self._get("conversation", lambda: ConversationService(
            self.agent_factory, self.safety_policy, self.conversation_log))

    @property
    def assessment(self):
        return self._get("assessment", lambda: AssessmentService(
            self.agent_factory, self.conversation_log, self.repository))

    @property
    def authoring(self):
        return self._get("authoring", lambda: AuthoringService(
            self.agent_factory, self.write_policy, self.sqlite_log, self.settings))
