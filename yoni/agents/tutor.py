from .. import config, memory_db
from .base import BaseAgent

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

SUMMARY_PROMPT_TEMPLATE = """סכם בקצרה ובעברית (2-3 משפטים) את השיחה הלימודית הבאה בין יוני (מורה) לתלמיד:

{transcript}
"""


class Tutor(BaseAgent):
    """סוכן שיחה לימודית בעברית, בשיטה סוקרטית. שומר היסטוריית סשן וסיכום ל-memory_db."""

    @property
    def model(self):
        return self._model_override or config.TUTOR_MODEL

    def __init__(self, model=None):
        super().__init__(model=model)
        self.history = []  # רשימת (דובר, טקסט)

    def _transcript(self):
        return "\n".join(f"{speaker}: {text}" for speaker, text in self.history)

    def ask(self, student_message):
        self.history.append(("תלמיד", student_message))
        prompt = f"{SYSTEM_PROMPT}\n\nהיסטוריית השיחה:\n{self._transcript()}\nיוני:"
        reply = self._call_model(prompt)
        self.history.append(("יוני", reply))
        return reply

    def _summarize(self):
        if not self.history:
            return "(שיחה ריקה - אין מה לסכם)"
        prompt = SUMMARY_PROMPT_TEMPLATE.format(transcript=self._transcript())
        return self._call_model(prompt)

    def end_session(self, student_id=None):
        summary = self._summarize()
        memory_db.log_session(student_id, len(self.history), summary)
        return summary
