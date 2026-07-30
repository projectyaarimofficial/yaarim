"""יצירת סוכנים דינמית מתוך ההגדרות - לא בנייה קשיחה בזמן ריצה.

להוסיף סוג סוכן = לרשום אותו כאן, בשורה אחת. שום קוד קיים לא משתנה.
כל סוכן מקבל את המודל בהזרקה; אף סוכן לא יוצר לעצמו לקוח HTTP.
"""

from typing import Tuple

from .builder import Coder, Planner
from .quiz import Quiz
from .reasoning import Reasoning
from .tutor import Tutor


class AgentFactory:
    """בונה סוכנים לפי שם תפקיד. המיפוי תפקיד→(מחלקה, שם מודל) הוא הנתון."""

    def __init__(self, language_model, settings) -> None:
        self._llm = language_model
        self._settings = settings
        self._registry = {
            "tutor": (Tutor, lambda s: s.tutor_model),
            "quiz": (Quiz, lambda s: s.quiz_model),
            "reasoning": (Reasoning, lambda s: s.reasoning_model),
            "planner": (Planner, lambda s: s.planner_model),
            "coder": (Coder, lambda s: s.coder_model),
        }

    def register(self, role: str, agent_class, model_selector) -> None:
        """רישום סוג סוכן חדש בזמן ריצה - בלי לשנות את המפעל."""
        self._registry[role] = (agent_class, model_selector)

    def roles(self) -> Tuple[str, ...]:
        return tuple(self._registry)

    def create(self, role: str, **kwargs):
        entry = self._registry.get(role)
        if entry is None:
            raise KeyError(f"תפקיד סוכן לא מוכר: {role!r}")
        agent_class, model_selector = entry
        return agent_class(self._llm, model_selector(self._settings), **kwargs)
