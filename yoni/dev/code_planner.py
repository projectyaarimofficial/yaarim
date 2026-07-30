import json
import re

from .. import config
from ..llm_client import ask_yoni

PLAN_PROMPT_TEMPLATE = """אתה יוני, עוזר תכנות שמסייע לבנות מערכת AI בשם YAARIM.
המשתמש מבקש את השינוי הבא:
"{request}"

אם המשתמש ציין במפורש שם קובץ או נתיב בבקשה - יש להשתמש בדיוק באותו נתיב, בלי לשנות שם, סיומת או תיקייה.

החזר אך ורק אובייקט JSON תקין (ללא טקסט נוסף, ללא קוד) במבנה הבא:
{{
  "plan": "תוכנית עבודה קצרה וברורה בעברית: מה יבוצע ולמה. בלי קוד.",
  "target_file": "נתיב יחסי (מתוך שורש הפרויקט) לקובץ הפייתון שיש ליצור או לערוך",
  "file_exists": true/false
}}
"""


def _parse_plan_response(raw):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return {"plan": raw, "target_file": None, "file_exists": False}


class CodePlanner:
    """מתכנן שינויי קוד לכלי הבנייה הפנימי (dev tooling) - לא סוכן מול תלמיד."""

    def __init__(self, model=None):
        self._model_override = model

    @property
    def model(self):
        return self._model_override or config.PLANNER_MODEL

    def generate_plan(self, user_request, max_attempts=2):
        prompt = PLAN_PROMPT_TEMPLATE.format(request=user_request)

        raw = ""
        data = {}
        for _ in range(max_attempts):
            raw = ask_yoni(prompt, self.model, expect_json=True)
            data = _parse_plan_response(raw)
            if data.get("plan"):
                break

        data.setdefault("plan", raw)
        data.setdefault("target_file", None)
        data.setdefault("file_exists", False)
        return data
