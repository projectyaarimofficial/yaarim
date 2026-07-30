"""סוכן ההוראה. שומר את היסטוריית השיחה ומסכם אותה בסיום."""

from typing import List, Optional, Tuple

from .base import StudentAgent

SYSTEM_PROMPT = """אתה יוני, מורה פרטי סבלני שמלמד תלמידים בעברית.

הבחנה חשובה בין שני סוגי בקשות:

1. בקשת הסבר/הוראה (למשל: "תלמד אותי על X", "מה זה Y", "ספר לי על Z", "תסביר לי איך...") -
   הסבר ישירות ולעומק, בצורה ברורה ומדורגת. אל תשאל שאלה מנחה במקום להסביר.
   רק בסוף ההסבר, שאל שאלת הבנה אחת קצרה כדי לוודא שהתלמיד עקב אחרי ההסבר.

2. בקשת פתרון/תרגול (למשל: "תפתור את זה", "עזור לי עם התרגיל", "למה זה לא עובד", "יש לי שגיאה") -
   כאן כן להשתמש בשיטה סוקרטית: תן רמז ושאלה מנחה אחת שתעזור לתלמיד לחשוב בעצמו,
   לפני מתן התשובה המלאה. רק אם התלמיד מתקשה, טועה שוב, או מבקש מפורשות את הפתרון - תן תשובה ישירה.

אם התלמיד עונה "תתחיל", "כן", "קדימה", "בסדר", "לא יודע" וכדומה - זו הסכמה או המשך לשיחה
הקיימת, לא בקשה חדשה. המשך מהנקודה שבה עצרת (למשל תן את ההסבר או הרמז הבא), אל תגיד "אני לא מבין".

ענה תמיד בעברית, בקצרה ובאדיבות."""

SUMMARY_PROMPT = """סכם בקצרה ובעברית (2-3 משפטים) את השיחה הלימודית הבאה בין יוני (מורה) לתלמיד:

{transcript}
"""


class Tutor(StudentAgent):
    """שיחה לימודית בעברית. ההיסטוריה היא מצב של הסוכן, לא של הממשק."""

    def __init__(self, language_model, model_name: str,
                 context: Optional[str] = None) -> None:
        super().__init__(language_model, model_name)
        self._history: List[Tuple[str, str]] = []
        self._context = context or ""

    @property
    def history(self) -> Tuple[Tuple[str, str], ...]:
        return tuple(self._history)

    @property
    def message_count(self) -> int:
        return len(self._history)

    def _transcript(self):
        return "\n".join(f"{speaker}: {text}" for speaker, text in self._history)

    def build_prompt(self, student_message: Optional[str] = None) -> str:
        head = SYSTEM_PROMPT
        if self._context:
            # מה שהתלמיד עדיין חייב - כדי שההוראה תתחבר למצב האמיתי שלו.
            head = f"{head}\n\nרקע על התלמיד: {self._context}"
        return f"{head}\n\nהיסטוריית השיחה:\n{self._transcript()}\nיוני:"

    def ask(self, student_message: str) -> str:
        self._history.append(("תלמיד", student_message))
        reply = self._ask(self.build_prompt())
        self._history.append(("יוני", reply))
        return reply

    def summarize(self) -> str:
        if not self._history:
            return "(שיחה ריקה - אין מה לסכם)"
        return self._ask(SUMMARY_PROMPT.format(transcript=self._transcript()))

    def reset(self) -> None:
        self._history = []
