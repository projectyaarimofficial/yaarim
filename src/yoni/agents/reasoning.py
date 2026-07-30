"""סוכן ההסקה - מודל כבד, מופעל במפורש בלבד (/reason)."""

import re

from .base import StudentAgent

SYSTEM_PROMPT = """אתה יוני במצב חשיבה מעמיקה: פותר בעיות שדורשות הסקה רב-שלבית
(מתמטיקה, לוגיקה, תכנון). חשוב בשקט צעד-צעד, ואז הצג לתלמיד רק את הפתרון
הסופי בעברית - מסודר, מנומק בקצרה, בלי להציף את כל שרשרת המחשבה."""

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class Reasoning(StudentAgent):
    def build_prompt(self, problem: str) -> str:
        return f"{SYSTEM_PROMPT}\n\nהבעיה:\n{problem}\n\nהפתרון:"

    def solve(self, problem: str) -> str:
        # Qwen3 עוטף חשיבה פנימית ב-<think> - מסירים לפני הצגה לתלמיד.
        return _THINK_RE.sub("", self._ask(self.build_prompt(problem))).strip()
