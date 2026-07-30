import json
import re

from .. import config
from .base import AgentError, BaseAgent

GENERATE_PROMPT_TEMPLATE = """אתה יוני, מורה שמכין מבחן קצר בעברית לתלמיד.
הבקשה של התלמיד: "{request}"

צור בדיוק {num_questions} שאלות. זהה את הנושא מתוך הבקשה.

החזר אך ורק אובייקט JSON תקין (בלי טקסט מסביב, בלי markdown) במבנה:
{{
  "questions": [
    {{
      "question": "נוסח השאלה בעברית",
      "type": "multiple_choice",
      "options": ["אפשרות 1", "אפשרות 2", "אפשרות 3", "אפשרות 4"],
      "correct_answer": "התשובה הנכונה המדויקת",
      "rubric": "קריטריון בדיקה מפורש",
      "topic": "הנושא"
    }}
  ]
}}

הנחיות לשדות:
- "type" חייב להיות אחד מ: "multiple_choice", "exact", "open".
- multiple_choice: שאלה אמריקאית עם 3-4 ערכים ב-"options". "correct_answer" חייבת להיות זהה בדיוק לאחת מה-options. אין "rubric".
- exact: שאלה עם תשובה קצרה ומדויקת אחת (מילה/מספר/ביטוי) ב-"correct_answer". "options" הוא null. אין "rubric".
- open: שאלה פתוחה שדורשת הסבר. ספק "rubric" ברור שמגדיר מה נחשב תשובה טובה. "options" הוא null.
- ערבב סוגי שאלות. כתוב הכל בעברית.
"""

GRADE_OPEN_PROMPT_TEMPLATE = """אתה בודק תשובה של תלמיד לשאלה פתוחה, אך ורק לפי הקריטריון (rubric) שניתן לך.
אל תמציא קריטריונים חדשים ואל תשפוט לפי דעה חופשית - בדוק רק אם התשובה עומדת בקריטריון.

השאלה: "{question}"
קריטריון הבדיקה (rubric): "{rubric}"
תשובת התלמיד: "{answer}"

החזר אך ורק אובייקט JSON תקין:
{{
  "correct": true,
  "feedback": "משוב קצר ומנומק בעברית לתלמיד"
}}
"""

VALID_TYPES = ("multiple_choice", "exact", "open")


def _normalize(text):
    """נרמול להשוואת מחרוזות: הסרת רווחים מיותרים + חוסר-רגישות לאותיות."""
    return " ".join(str(text).strip().casefold().split())


def _coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("true", "1", "yes", "כן", "נכון")


def _parse_json(raw):
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    match = re.search(r"[\[{].*[\]}]", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate_question(q):
    """מחזיר שאלה מנורמלת ותקינה, או None אם היא פסולה."""
    if not isinstance(q, dict):
        return None

    question = str(q.get("question", "")).strip()
    qtype = q.get("type")
    if not question or qtype not in VALID_TYPES:
        return None

    topic = str(q.get("topic", "")).strip() or None
    raw_correct = q.get("correct_answer")
    correct = str(raw_correct).strip() if raw_correct is not None else ""

    if qtype == "multiple_choice":
        options = q.get("options")
        if not isinstance(options, list):
            return None
        options = [str(o).strip() for o in options if str(o).strip()]
        if len(options) < 2 or not correct:
            return None
        # correct_answer חייבת להתאים לאחת מה-options - אחרת אי אפשר לבדוק בקוד.
        if _normalize(correct) not in {_normalize(o) for o in options}:
            return None
        return {
            "question": question,
            "type": qtype,
            "options": options,
            "correct_answer": correct,
            "rubric": None,
            "topic": topic,
        }

    if qtype == "exact":
        if not correct:
            return None
        return {
            "question": question,
            "type": qtype,
            "options": None,
            "correct_answer": correct,
            "rubric": None,
            "topic": topic,
        }

    # open
    rubric = str(q.get("rubric", "")).strip()
    if not rubric:
        return None
    return {
        "question": question,
        "type": qtype,
        "options": None,
        "correct_answer": correct or None,
        "rubric": rubric,
        "topic": topic,
    }


class Quiz(BaseAgent):
    """סוכן מבחנים בעברית: מייצר שאלות JSON, ובודק אותן.

    כלל ברזל לבדיקה:
    - multiple_choice / exact (תשובה נכונה יחידה) נבדקות בקוד בלבד (השוואת מחרוזות),
      לעולם לא דרך המודל.
    - open (שאלה פתוחה) בלבד נבדקת ע"י המודל, ואך ורק מול rubric מפורש.
    ההפרדה נאכפת במבנה הקוד (grade מנתב לפי type לפני כל מסלול מודל).
    """

    @property
    def model(self):
        return self._model_override or config.QUIZ_MODEL

    def generate(self, request, num_questions=3):
        prompt = GENERATE_PROMPT_TEMPLATE.format(
            request=request, num_questions=num_questions
        )
        raw = self._call_model(prompt, expect_json=True)
        data = _parse_json(raw)

        raw_questions = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(raw_questions, list):
            raise AgentError("המודל לא החזיר רשימת שאלות תקינה למבחן.")

        questions = [v for v in (_validate_question(q) for q in raw_questions) if v]
        if not questions:
            raise AgentError(
                "לא הצלחתי לייצר שאלות תקינות למבחן. נסה לנסח את הבקשה מחדש."
            )
        return questions

    def grade(self, question, student_answer):
        """מחזיר {"correct": bool, "feedback": str}. מנתב לפי סוג השאלה."""
        qtype = question.get("type")
        if qtype in ("multiple_choice", "exact"):
            return self._grade_exact_match(question, student_answer)
        if qtype == "open":
            return self._grade_open(question, student_answer)
        # סוג לא מוכר - לא נופלים למסלול המודל בשקט (זה היה מפר את כלל הברזל).
        raise ValueError(f"סוג שאלה לא נתמך: {qtype!r}")

    @staticmethod
    def _grade_exact_match(question, student_answer):
        """בדיקה בקוד בלבד - אין כאן שום קריאה למודל, ובכוונה."""
        correct_answer = question.get("correct_answer", "")
        is_correct = _normalize(student_answer) == _normalize(correct_answer)
        if is_correct:
            feedback = "נכון! כל הכבוד. ✅"
        else:
            feedback = f"לא מדויק. התשובה הנכונה: {correct_answer}"
        return {"correct": is_correct, "feedback": feedback}

    def _grade_open(self, question, student_answer):
        prompt = GRADE_OPEN_PROMPT_TEMPLATE.format(
            question=question.get("question", ""),
            rubric=question.get("rubric", ""),
            answer=student_answer,
        )
        raw = self._call_model(prompt, expect_json=True)
        data = _parse_json(raw)
        if not isinstance(data, dict) or "correct" not in data:
            raise AgentError("לא הצלחתי לבדוק את התשובה הפתוחה.")

        is_correct = _coerce_bool(data.get("correct"))
        feedback = str(data.get("feedback", "")).strip()
        if not feedback:
            feedback = "תשובה טובה." if is_correct else "כדאי לחדד את התשובה."
        return {"correct": is_correct, "feedback": feedback}
