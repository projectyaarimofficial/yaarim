import re

from .. import config
from ..llm_client import ask_yoni

CODE_PROMPT_TEMPLATE = """אתה יוני, עוזר תכנות. בהתבסס על התוכנית הבאה שאושרה על ידי המשתמש, כתוב את הקוד בפועל.

בקשת המשתמש המקורית:
"{request}"

התוכנית שאושרה:
{plan}

הקשר קיים מהקובץ (אם רלוונטי, אחרת אין קובץ קיים):
{context}

כתוב את התוכן המלא של קובץ הפייתון. אל תוסיף הסברים מסביב לקוד - רק את הקוד עצמו, בלי גדרות markdown (בלי ```).
"""

_CODE_FENCE_RE = re.compile(r"```(?:[a-zA-Z0-9_+-]*\n)?(.*?)```", re.DOTALL)


def _strip_code_fences(text):
    text = text.strip()
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip("\n")

    # גדר markdown פתוחה בלי סגירה (למשל תשובה שנקטעה) - מסירים רק את השורה הראשונה
    if text.startswith("```"):
        first_newline = text.find("\n")
        text = text[first_newline + 1 :] if first_newline != -1 else ""
        if text.endswith("```"):
            text = text[:-3]
        return text.strip("\n")

    return text


class CodeBuilder:
    """כותב את הקוד בפועל על בסיס תוכנית מאושרת - dev tooling, לא סוכן מול תלמיד."""

    def __init__(self, model=None):
        self._model_override = model

    @property
    def model(self):
        return self._model_override or config.CODER_MODEL

    def generate_code(self, user_request, plan_text, relevant_context=None):
        prompt = CODE_PROMPT_TEMPLATE.format(
            request=user_request,
            plan=plan_text,
            context=relevant_context or "(אין קובץ קיים - זהו קובץ חדש)",
        )
        raw = ask_yoni(prompt, self.model)
        return _strip_code_fences(raw)
