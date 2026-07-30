"""סוכן המבחנים.

כלל הברזל נשמר, ועכשיו הוא מפורש במבנה: הבדיקה עוברת דרך *מדרגים* פולימורפיים.
ExactGrader הוא קוד טהור ואין לו בכלל גישה למודל; RubricGrader הוא היחיד שמחזיק
מודל. כלומר אי אפשר "בטעות" לשלוח שאלה סגורה למודל - למדרג שלה אין למי לפנות.
"""

import json
import re
from abc import ABC, abstractmethod
from typing import List, Optional


from ..domain.models import GradeResult, Question
from .base import AgentError, StudentAgent

GENERATE_PROMPT = """אתה יוני, מורה שמכין מבחן קצר בעברית לתלמיד.
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

GRADE_OPEN_PROMPT = """אתה בודק תשובה של תלמיד לשאלה פתוחה, אך ורק לפי הקריטריון (rubric) שניתן לך.
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

VALID_TYPES = (Question.MULTIPLE_CHOICE, Question.EXACT, Question.OPEN)


def normalize(text) -> str:
    """נרמול להשוואת מחרוזות: רווחים מיותרים + חוסר-רגישות לאותיות."""
    return " ".join(str(text).strip().casefold().split())


def parse_json(raw):
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


def coerce_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in ("true", "1", "yes", "כן", "נכון")


# ---------------------------------------------------------------------------
# מדרגים - נקודת הפולימורפיזם
# ---------------------------------------------------------------------------
class Grader(ABC):
    @abstractmethod
    def grade(self, question: Question, answer: str) -> GradeResult:
        """GradeResult."""


class ExactGrader(Grader):
    """השוואת מחרוזות בלבד. אין למחלקה הזו מודל, ולכן אין לה דרך לפנות אליו."""

    def grade(self, question: Question, answer: str) -> GradeResult:
        correct = normalize(answer) == normalize(question.correct_answer or "")
        feedback = "נכון! כל הכבוד. ✅" if correct else f"לא מדויק. התשובה הנכונה: {question.correct_answer}"
        return GradeResult(correct=correct, feedback=feedback, graded_by="code")


class RubricGrader(Grader):
    """המדרג היחיד שמחזיק מודל, והוא פועל רק מול rubric מפורש."""

    def __init__(self, ask):
        self._ask = ask

    def grade(self, question: Question, answer: str) -> GradeResult:
        raw = self._ask(
            GRADE_OPEN_PROMPT.format(
                question=question.question, rubric=question.rubric or "", answer=answer
            ),
            expect_json=True,
        )
        data = parse_json(raw)
        if not isinstance(data, dict) or "correct" not in data:
            raise AgentError("לא הצלחתי לבדוק את התשובה הפתוחה.")
        correct = coerce_bool(data.get("correct"))
        feedback = str(data.get("feedback", "")).strip() or (
            "תשובה טובה." if correct else "כדאי לחדד את התשובה."
        )
        return GradeResult(correct=correct, feedback=feedback, graded_by="model")


class Quiz(StudentAgent):
    """מייצר שאלות ומנתב אותן למדרג המתאים לפי הסוג."""

    def __init__(self, language_model, model_name: str) -> None:
        super().__init__(language_model, model_name)
        self._graders = {
            Question.MULTIPLE_CHOICE: ExactGrader(),
            Question.EXACT: ExactGrader(),
            Question.OPEN: RubricGrader(self._ask),
        }

    def build_prompt(self, request: str, num_questions: int = 3) -> str:
        return GENERATE_PROMPT.format(request=request, num_questions=num_questions)

    def generate(self, request: str, num_questions: int = 3) -> List[Question]:
        raw = self._ask(self.build_prompt(request, num_questions), expect_json=True)
        data = parse_json(raw)
        raw_questions = data.get("questions") if isinstance(data, dict) else data
        if not isinstance(raw_questions, list):
            raise AgentError("המודל לא החזיר רשימת שאלות תקינה למבחן.")

        questions = [q for q in (self._validate(item) for item in raw_questions) if q]
        if not questions:
            raise AgentError("לא הצלחתי לייצר שאלות תקינות למבחן. נסה לנסח את הבקשה מחדש.")
        return questions

    def grade(self, question: Question, answer: str) -> GradeResult:
        grader = self._graders.get(question.type)
        if grader is None:
            # סוג לא מוכר לא נופל בשקט למסלול המודל - זו הייתה הפרה של כלל הברזל.
            raise ValueError(f"סוג שאלה לא נתמך: {question.type!r}")
        return grader.grade(question, answer)

    @staticmethod
    def _validate(item) -> Optional[Question]:
        """מחזיר Question תקין, או None אם הפריט פסול."""
        if not isinstance(item, dict):
            return None
        text = str(item.get("question", "")).strip()
        qtype = item.get("type")
        if not text or qtype not in VALID_TYPES:
            return None

        topic = str(item.get("topic", "")).strip() or None
        raw_correct = item.get("correct_answer")
        correct = str(raw_correct).strip() if raw_correct is not None else ""

        if qtype == Question.MULTIPLE_CHOICE:
            options = item.get("options")
            if not isinstance(options, list):
                return None
            options = tuple(str(o).strip() for o in options if str(o).strip())
            if len(options) < 2 or not correct:
                return None
            # בלי התאמה ל-options אי אפשר לבדוק בקוד, וזו הנקודה כולה.
            if normalize(correct) not in {normalize(o) for o in options}:
                return None
            return Question(text, qtype, topic, options, correct)

        if qtype == Question.EXACT:
            return Question(text, qtype, topic, (), correct) if correct else None

        rubric = str(item.get("rubric", "")).strip()
        if not rubric:
            return None
        return Question(text, qtype, topic, (), correct or None, rubric)
