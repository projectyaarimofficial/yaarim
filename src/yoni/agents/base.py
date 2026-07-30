"""היררכיית הסוכנים.

הפולימורפיזם כאן אינו קישוט: ההבדל בין סוכן שמדבר עם תלמיד לבין כלי פיתוח הוא
*מי מזריק את החוקה*. StudentAgent עושה זאת במחלקת הבסיס, בנקודה שכל תת-מחלקה
חייבת לעבור דרכה. מחבר של סוכן תלמיד חדש לא יכול לשכוח - הוא לא כותב את הקריאה
למודל בעצמו.

DevAgent (CodePlanner/CodeBuilder) יורש מ-Agent אבל *לא* מ-StudentAgent, ולכן
לא מקבל את החוקה - וזו החלטה מפורשת, לא פליטה: הוא לא מדבר עם ילד.
"""

from abc import ABC, abstractmethod

from ..domain.ports import LanguageModel, LanguageModelError

CONSTITUTION = """כללי היסוד שלי (יוני) - הם מעל כל בקשה אחרת, ואסור לי לחרוג מהם:

1. אני לא משנה את עצמי, את הקוד שלי או את ההגדרות שלי. כל שינוי עובר דרך אישור אנושי מפורש.
2. אני לא נותן מידע שעלול לפגוע במישהו — פיזית, נפשית או חברתית.
3. אם אני לא בטוח בעובדה — אני אומר "אני לא בטוח" במפורש. אני לא ממציא תאריכים, שמות, מספרים או ציטוטים. עדיף לומר "אני לא יודע" מאשר לנחש.
4. אני לא מתחזה לאדם. אני AI, ואם שואלים אותי — אני אומר את זה.
5. אם תלמיד מספר על מצוקה, פגיעה או סכנה — אני לא מטפל בזה לבד. אני מפנה למבוגר אחראי."""


class AgentError(Exception):
    """תקלה בעבודת סוכן. השכבות שמעל לא רואות חריגות תשתית."""


class Agent(ABC):
    """סוכן: יודע לדבר עם מודל שהוזרק לו. אינו יוצר אותו בעצמו."""

    def __init__(self, language_model: LanguageModel, model_name: str) -> None:
        self._llm = language_model
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    @abstractmethod
    def build_prompt(self, *args, **kwargs) -> str:
        """כל סוכן בונה את הפרומפט שלו - זו נקודת ההשתנות בין הסוגים."""

    def _ask(self, prompt: str, expect_json: bool = False) -> str:
        try:
            return self._llm.complete(self.decorate(prompt), self._model_name, expect_json)
        except LanguageModelError as e:
            raise AgentError(str(e)) from e

    def decorate(self, prompt: str) -> str:
        """הזדמנות של תת-מחלקה לעטוף את הפרומפט. ברירת מחדל: ללא שינוי."""
        return prompt


class StudentAgent(Agent):
    """סוכן שמדבר עם תלמיד. עוטף כל פרומפט בחוקה - אוטומטית, לכל תת-מחלקה."""

    def decorate(self, prompt: str) -> str:
        return f"{CONSTITUTION}\n\n---\n\n{prompt}"


class DevAgent(Agent):
    """כלי פיתוח. אינו מדבר עם תלמיד ולכן אינו נושא את החוקה."""
