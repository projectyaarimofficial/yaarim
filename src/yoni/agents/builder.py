"""כלי הפיתוח: תכנון וכתיבת קוד.

יורשים מ-DevAgent ולא מ-StudentAgent, ולכן אינם נושאים את החוקה. ההפרדה הזו
היא במבנה ולא בהערה: אין להם דרך לקבל אותה בטעות.
"""

import json
import re
from typing import Optional


from ..domain.models import BuildPlan
from .base import DevAgent

PLAN_PROMPT = """אתה יוני, עוזר תכנות שמסייע לבנות מערכת AI בשם YAARIM.
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

CODE_PROMPT = """אתה יוני, עוזר תכנות. בהתבסס על התוכנית הבאה שאושרה על ידי המשתמש, כתוב את הקוד בפועל.

בקשת המשתמש המקורית:
"{request}"

התוכנית שאושרה:
{plan}

הקשר קיים מהקובץ (אם רלוונטי, אחרת אין קובץ קיים):
{context}

כתוב את התוכן המלא של קובץ הפייתון. אל תוסיף הסברים מסביב לקוד - רק את הקוד עצמו, בלי גדרות markdown (בלי ```).
"""

_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*\n)?(.*?)```", re.DOTALL)


def strip_fences(text):
    text = text.strip()
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip("\n")
    if text.startswith("```"):  # גדר פתוחה בלי סגירה (תשובה שנקטעה)
        newline = text.find("\n")
        text = text[newline + 1:] if newline != -1 else ""
        if text.endswith("```"):
            text = text[:-3]
        return text.strip("\n")
    return text


class Planner(DevAgent):
    """מתרגם בקשה חופשית לתוכנית מובנית."""

    def build_prompt(self, request: str) -> str:
        return PLAN_PROMPT.format(request=request)

    def plan(self, request: str, max_attempts: int = 2) -> BuildPlan:
        raw, data = "", {}
        for _ in range(max_attempts):
            raw = self._ask(self.build_prompt(request), expect_json=True)
            data = self._parse(raw)
            if data.get("plan"):
                break
        return BuildPlan(
            summary=data.get("plan") or raw,
            target_file=data.get("target_file"),
            file_exists=bool(data.get("file_exists")),
        )

    @staticmethod
    def _parse(raw):
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
        return {}


class Coder(DevAgent):
    """כותב את הקוד בפועל, על בסיס תוכנית שאושרה."""

    def build_prompt(self, request: str, plan_summary: str,
                     context: Optional[str] = None) -> str:
        return CODE_PROMPT.format(
            request=request,
            plan=plan_summary,
            context=context or "(אין קובץ קיים - זהו קובץ חדש)",
        )

    def write_code(self, request: str, plan_summary: str,
                   context: Optional[str] = None) -> str:
        return strip_fences(self._ask(self.build_prompt(request, plan_summary, context)))
