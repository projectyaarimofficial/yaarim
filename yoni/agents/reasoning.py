import re

from .. import config
from .base import BaseAgent

SYSTEM_PROMPT = """אתה יוני במצב חשיבה מעמיקה: פותר בעיות שדורשות הסקה רב-שלבית
(מתמטיקה, לוגיקה, תכנון). חשוב בשקט צעד-צעד, ואז הצג לתלמיד רק את הפתרון
הסופי בעברית - מסודר, מנומק בקצרה, בלי להציף את כל שרשרת המחשבה."""

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_think(text):
    """Qwen3 עוטף חשיבה פנימית ב-<think>...</think> - מסירים לפני הצגה לתלמיד."""
    return _THINK_RE.sub("", text).strip()


class Reasoning(BaseAgent):
    """סוכן הסקה על Qwen3 8B - מודל כבד; model_manager דואג שלא יחיה לצד כבד אחר."""

    @property
    def model(self):
        return self._model_override or config.REASONING_MODEL

    def solve(self, problem):
        prompt = f"{SYSTEM_PROMPT}\n\nהבעיה:\n{problem}\n\nהפתרון:"
        return _strip_think(self._call_model(prompt))
