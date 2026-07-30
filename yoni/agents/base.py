import requests

from .. import config
from ..constitution import with_constitution
from ..llm_client import ask_yoni


class AgentError(Exception):
    """שגיאה בתקשורת עם המודל - סוכנים זורקים את זה במקום לדלוף חריגות requests גולמיות."""


class BaseAgent:
    """בסיס משותף לסוכנים מול תלמיד: קריאה למודל + טיפול שגיאות אחיד."""

    def __init__(self, model=None):
        self._model_override = model

    @property
    def model(self):
        return self._model_override or config.PLANNER_MODEL

    def _call_model(self, prompt, expect_json=False):
        # כללי היסוד מוזרקים כאן, בנקודה שכל סוכן תלמיד עובר דרכה - כך שגם תת-מחלקה
        # חדשה של BaseAgent מקבלת אותם אוטומטית, בלי להסתמך על כך שהמחבר יזכור.
        full_prompt = with_constitution(prompt)
        try:
            return ask_yoni(full_prompt, self.model, expect_json=expect_json)
        except requests.exceptions.RequestException as e:
            raise AgentError(f"שגיאה בתקשורת עם המודל ({self.model}): {e}") from e
