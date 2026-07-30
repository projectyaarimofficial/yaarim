"""שירות השיחה - כולל הבדיקה החשובה ביותר במערכת:
במצוקה, אף סוכן לא נשאל.

הודות להזרקה אפשר לבדוק את זה ישירות: FakeLanguageModel מתעד כל קריאה, ולכן
"המודל לא נשאל" הוא טענה שנבדקת, לא הבטחה בהערה.
"""

import unittest

from support import IsolatedProject
from yoni.application.conversation import ConversationService, Router


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_build_is_explicit_mode_not_keyword(self):
        self.assertEqual(self.router.route("/build הוסף פונקציה"), "build")
        # שאלה של תלמיד על קוד היא Tutor, לא Builder - זו הסיבה למצב מפורש.
        self.assertEqual(self.router.route("איך כותבים לולאה בפייתון?"), "chat")

    def test_reason_is_explicit_mode(self):
        self.assertEqual(self.router.route("/reason פתור את המשוואה"), "reason")

    def test_quiz_keywords(self):
        for text in ("בחן אותי על שברים", "אני רוצה מבחן", "test me on fractions"):
            self.assertEqual(self.router.route(text), "quiz")

    def test_unknown_falls_back_to_chat(self):
        self.assertEqual(self.router.route("שלום"), "chat")


class TestSafetyShortCircuit(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.write_safety_config()
        self.service = self.container.conversation

    def test_distress_never_reaches_any_agent(self):
        tutor = self.container.conversation.new_tutor()
        self.llm.calls.clear()  # יצירת הסוכן עצמה אינה קוראת למודל

        turn = self.service.handle("אני כבר לא רוצה לחיות", tutor, student_id=None)

        self.assertFalse(self.llm.was_called, "המודל נשאל למרות שזוהתה מצוקה")
        self.assertFalse(turn.model_called)
        self.assertEqual(turn.safety.category, "suicide")
        self.assertIn("מבוגר", turn.text)

    def test_ordinary_message_does_reach_the_tutor(self):
        tutor = self.service.new_tutor()
        self.llm.calls.clear()
        turn = self.service.handle("מה זה שבר עשרוני?", tutor)
        self.assertTrue(self.llm.was_called)
        self.assertTrue(turn.model_called)
        self.assertIsNone(turn.safety)

    def test_build_command_is_refused_in_web_without_model(self):
        turn = self.service.handle("/build הוסף כפתור", tutor=None)
        self.assertFalse(self.llm.was_called)
        self.assertEqual(turn.speaker, "system")

    def test_quiz_intent_signals_without_calling_model(self):
        turn = self.service.handle("בחן אותי על שברים", tutor=None)
        self.assertEqual(turn.action, "start_quiz")
        self.assertFalse(self.llm.was_called)

    def test_alert_is_written_for_a_known_student(self):
        self.container.repository.create("eitan", "איתן", is_demo=True)
        tutor = self.service.new_tutor()
        self.service.handle("מכים אותי בבית", tutor, student_id="eitan")

        import json, os
        directory = self.container.repository.directory("eitan")
        path = os.path.join(directory, "alerts", f"{self.clock.today()}.json")
        self.assertTrue(os.path.exists(path), "לא נרשמה התרעה")
        with open(path, encoding="utf-8") as f:
            alert = json.load(f)["alerts"][0]
        self.assertEqual(alert["category"], "abuse")
        self.assertIn("model was not called", alert["handled_by"])


class TestGreeting(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.write_safety_config()
        self.service = self.container.conversation

    def test_greeting_never_calls_the_model(self):
        student = self.container.repository.create("dana", "דנה", is_demo=True)
        self.llm.calls.clear()
        message = self.service.greeting(student)
        self.assertFalse(self.llm.was_called, "ברכת הפתיחה חייבת להיות קוד בלבד")
        self.assertIn("דנה", message)

    def test_new_student_gets_introduction(self):
        student = self.container.repository.create("dana", "דנה")
        self.assertIn("נעים להכיר", self.service.greeting(student))

    def test_returning_student_hears_the_last_session(self):
        student = self.container.repository.create("dana", "דנה")
        returning = student.as_returning()
        message = self.service.greeting(
            returning, last_session={"summary": "למדנו שברים", "date": "2026-01-01"})
        self.assertIn("שברים", message)

    def test_open_brick_surfaces_when_no_session(self):
        self.container.repository.create("dana", "דנה")
        self.container.repository.open_brick("dana", "מערכת השמש", "הכוכב שבמרכז")
        status = self.container.repository.status("dana")
        student = self.container.repository.find("dana")
        self.assertIn("מערכת השמש", self.service.greeting(student, status=status))


class TestTutorContext(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.write_safety_config()

    def test_open_brick_is_injected_into_the_tutor_prompt(self):
        """מה שהתלמיד חייב חוזר אליו בשיעור הבא - הלולאה נסגרת."""
        self.container.repository.create("dana", "דנה")
        self.container.repository.open_brick("dana", "שברים", "מכנה משותף")
        status = self.container.repository.status("dana")

        tutor = self.container.conversation.new_tutor(status)
        tutor.ask("שלום")
        self.assertIn("שברים", self.llm.last_prompt())


if __name__ == "__main__":
    unittest.main()
