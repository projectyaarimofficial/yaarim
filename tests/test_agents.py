"""סוכנים: החוקה, הפולימורפיזם של המדרגים, והמפעל."""

import unittest

from support import FakeLanguageModel, IsolatedProject
from yoni.agents.base import CONSTITUTION, AgentError, DevAgent, StudentAgent
from yoni.agents.builder import Coder, Planner, strip_fences
from yoni.agents.factory import AgentFactory
from yoni.agents.quiz import ExactGrader, Quiz, RubricGrader
from yoni.agents.reasoning import Reasoning
from yoni.agents.tutor import Tutor
from yoni.config.settings import Settings
from yoni.domain.models import Question


class _NewStudentAgent(StudentAgent):
    """סוכן תלמיד חדש שנכתב אחרי הריפקטור - לא עושה דבר כדי לקבל את החוקה."""

    def build_prompt(self, text):
        return f"שאלה: {text}"

    def run(self, text):
        return self._ask(self.build_prompt(text))


class _NewDevAgent(DevAgent):
    def build_prompt(self, text):
        return text

    def run(self, text):
        return self._ask(text)


class TestConstitution(unittest.TestCase):
    def test_new_student_agent_inherits_it_automatically(self):
        llm = FakeLanguageModel()
        _NewStudentAgent(llm, "m").run("מה זה שבר?")
        self.assertIn(CONSTITUTION, llm.last_prompt())

    def test_dev_agent_deliberately_does_not_carry_it(self):
        """כלי פיתוח לא מדבר עם ילד - וזו החלטה במבנה, לא פליטה."""
        llm = FakeLanguageModel()
        _NewDevAgent(llm, "m").run("כתוב פונקציה")
        self.assertNotIn(CONSTITUTION, llm.last_prompt())

    def test_constitution_holds_the_five_rules(self):
        for marker in ("1.", "2.", "3.", "4.", "5."):
            self.assertIn(marker, CONSTITUTION)
        self.assertIn("מבוגר אחראי", CONSTITUTION)

    def test_model_error_becomes_agent_error(self):
        agent = _NewStudentAgent(FakeLanguageModel(fail=True), "m")
        with self.assertRaises(AgentError):
            agent.run("שלום")


class TestTutor(unittest.TestCase):
    def test_history_grows_with_both_voices(self):
        tutor = Tutor(FakeLanguageModel(["תשובה"]), "m")
        tutor.ask("שאלה")
        self.assertEqual(tutor.message_count, 2)
        self.assertEqual(tutor.history[0][0], "תלמיד")

    def test_context_reaches_the_prompt(self):
        llm = FakeLanguageModel()
        Tutor(llm, "m", context="נושא פתוח: שברים").ask("שלום")
        self.assertIn("שברים", llm.last_prompt())

    def test_empty_conversation_summary_needs_no_model(self):
        llm = FakeLanguageModel()
        self.assertIn("ריקה", Tutor(llm, "m").summarize())
        self.assertFalse(llm.was_called)

    def test_reset_clears_history(self):
        tutor = Tutor(FakeLanguageModel(), "m")
        tutor.ask("א")
        tutor.reset()
        self.assertEqual(tutor.message_count, 0)


class TestGraderPolymorphism(unittest.TestCase):
    """כלל הברזל: שאלה סגורה נבדקת בקוד. למדרג שלה אין בכלל מודל."""

    def setUp(self):
        self.llm = FakeLanguageModel(['{"correct": true, "feedback": "טוב"}'])
        self.quiz = Quiz(self.llm, "m")

    def test_multiple_choice_never_touches_the_model(self):
        q = Question("מה?", Question.MULTIPLE_CHOICE, "נושא", ("א", "ב"), "א")
        result = self.quiz.grade(q, "א")
        self.assertTrue(result.correct)
        self.assertEqual(result.graded_by, "code")
        self.assertFalse(self.llm.was_called)

    def test_exact_never_touches_the_model(self):
        q = Question("בירת צרפת?", Question.EXACT, "גאוגרפיה", (), "פריז")
        self.assertTrue(self.quiz.grade(q, " פריז ").correct)  # נרמול רווחים
        self.assertFalse(self.llm.was_called)

    def test_wrong_exact_answer_reports_the_right_one(self):
        q = Question("בירת צרפת?", Question.EXACT, None, (), "פריז")
        result = self.quiz.grade(q, "לונדון")
        self.assertFalse(result.correct)
        self.assertIn("פריז", result.feedback)

    def test_open_question_uses_the_model_with_its_rubric(self):
        q = Question("הסבר", Question.OPEN, "נושא", (), None, "חייב להזכיר X")
        result = self.quiz.grade(q, "תשובה")
        self.assertTrue(self.llm.was_called)
        self.assertEqual(result.graded_by, "model")
        self.assertIn("חייב להזכיר X", self.llm.last_prompt())

    def test_unknown_type_raises_instead_of_falling_through(self):
        q = Question("מה?", "invented_type")
        with self.assertRaises(ValueError):
            self.quiz.grade(q, "משהו")
        self.assertFalse(self.llm.was_called, "סוג לא מוכר לא נופל בשקט למודל")

    def test_exact_grader_has_no_model_attribute_at_all(self):
        self.assertFalse(hasattr(ExactGrader(), "_ask"))
        self.assertTrue(hasattr(RubricGrader(lambda *_a, **_k: ""), "_ask"))


class TestQuizGeneration(unittest.TestCase):
    def _quiz(self, payload):
        return Quiz(FakeLanguageModel([payload]), "m")

    def test_valid_payload_becomes_questions(self):
        payload = ('{"questions":[{"question":"מה?","type":"exact",'
                   '"correct_answer":"פריז","topic":"גאוגרפיה"}]}')
        questions = self._quiz(payload).generate("בחן אותי")
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].correct_answer, "פריז")

    def test_answer_absent_from_options_is_rejected(self):
        """בלי התאמה ל-options אי אפשר לבדוק בקוד - וזו כל הנקודה."""
        payload = ('{"questions":[{"question":"מה?","type":"multiple_choice",'
                   '"options":["א","ב"],"correct_answer":"ג"}]}')
        with self.assertRaises(AgentError):
            self._quiz(payload).generate("בחן אותי")

    def test_open_question_without_rubric_is_rejected(self):
        payload = '{"questions":[{"question":"הסבר","type":"open"}]}'
        with self.assertRaises(AgentError):
            self._quiz(payload).generate("בחן אותי")

    def test_json_wrapped_in_prose_is_recovered(self):
        payload = 'בבקשה: {"questions":[{"question":"מה?","type":"exact","correct_answer":"א"}]} תודה'
        self.assertEqual(len(self._quiz(payload).generate("בחן")), 1)

    def test_garbage_raises_a_clear_error(self):
        with self.assertRaises(AgentError):
            self._quiz("לא JSON בכלל").generate("בחן")


class TestReasoning(unittest.TestCase):
    def test_think_block_is_stripped(self):
        llm = FakeLanguageModel(["<think>חשיבה פנימית</think>\nהתשובה היא 42"])
        answer = Reasoning(llm, "m").solve("בעיה")
        self.assertNotIn("חשיבה פנימית", answer)
        self.assertIn("42", answer)


class TestBuilder(unittest.TestCase):
    def test_plan_parses_json(self):
        llm = FakeLanguageModel(['{"plan":"תוכנית","target_file":"a.py","file_exists":false}'])
        plan = Planner(llm, "m").plan("בקשה")
        self.assertEqual(plan.target_file, "a.py")

    def test_plan_survives_broken_json(self):
        plan = Planner(FakeLanguageModel(["טקסט חופשי"]), "m").plan("בקשה")
        self.assertIsNone(plan.target_file)
        self.assertTrue(plan.summary)

    def test_code_fences_are_stripped(self):
        self.assertEqual(strip_fences("```python\nx = 1\n```"), "x = 1")
        self.assertEqual(strip_fences("```\nx = 1"), "x = 1")  # גדר לא סגורה
        self.assertEqual(strip_fences("x = 1"), "x = 1")

    def test_coder_returns_clean_code(self):
        llm = FakeLanguageModel(["```python\nprint(1)\n```"])
        self.assertEqual(Coder(llm, "m").write_code("בקשה", "תוכנית"), "print(1)")


class TestFactory(IsolatedProject):
    def test_creates_every_declared_role(self):
        factory = self.container.agent_factory
        for role in ("tutor", "quiz", "reasoning", "planner", "coder"):
            self.assertIsNotNone(factory.create(role))

    def test_role_maps_to_its_configured_model(self):
        settings = Settings(project_root=self.root, tutor_model="A", coder_model="B")
        factory = AgentFactory(self.llm, settings)
        self.assertEqual(factory.create("tutor").model_name, "A")
        self.assertEqual(factory.create("coder").model_name, "B")

    def test_unknown_role_raises(self):
        with self.assertRaises(KeyError):
            self.container.agent_factory.create("no_such_role")

    def test_new_role_registers_without_touching_the_factory(self):
        """הוספת סוג סוכן היא שורת רישום, לא שינוי קוד קיים."""
        factory = self.container.agent_factory
        factory.register("custom", _NewStudentAgent, lambda s: s.tutor_model)
        self.assertIn("custom", factory.roles())
        self.assertIsInstance(factory.create("custom"), _NewStudentAgent)


if __name__ == "__main__":
    unittest.main()
