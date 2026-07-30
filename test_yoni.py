# בדיקות אוטומטיות ל-yoni. תשובות Ollama מדומות (mock) כדי שהריצה תהיה מהירה
# ולא תלויה במודל אמיתי או ב-Ollama שרץ ברקע.

import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests

from yoni import config, constitution, file_ops, llm_client, memory_db
from yoni.agents import (
    AgentError,
    BaseAgent,
    Critic,
    Quiz,
    Router,
    Tutor,
    handle_student_message,
)
from yoni.dev.code_builder import CodeBuilder, _strip_code_fences
from yoni.dev.code_planner import CodePlanner
from yoni.main import main


class TempConfigTestCase(unittest.TestCase):
    """מפנה את כל נתיבי הדאטה של yoni לתיקיית זמן נפרדת לכל בדיקה."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yoni_test_")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        original = {
            "BASE_DIR": config.BASE_DIR,
            "DATA_DIR": config.DATA_DIR,
            "BACKUPS_DIR": config.BACKUPS_DIR,
            "DB_PATH": config.DB_PATH,
        }
        self.addCleanup(lambda: config.__dict__.update(original))

        config.BASE_DIR = self.tmp_dir
        config.DATA_DIR = os.path.join(self.tmp_dir, "data")
        config.BACKUPS_DIR = os.path.join(config.DATA_DIR, "backups")
        config.DB_PATH = os.path.join(config.DATA_DIR, "yoni_memory.db")


class TestLLMClient(unittest.TestCase):
    @patch("yoni.llm_client.requests.post")
    def test_ask_yoni_success_sends_requested_model(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "תשובה מהמודל"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = llm_client.ask_yoni("פרומפט", "some-model")

        self.assertEqual(result, "תשובה מהמודל")
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "some-model")
        self.assertNotIn("format", payload)

    @patch("yoni.llm_client.requests.post")
    def test_ask_yoni_expect_json_sets_format(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "{}"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        llm_client.ask_yoni("פרומפט", "some-model", expect_json=True)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["format"], "json")

    @patch("yoni.llm_client.requests.post")
    def test_ask_yoni_nonexistent_model_raises_request_exception(self, mock_post):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404 Client Error: Not Found for url: http://localhost:11434/api/generate"
        )
        mock_post.return_value = mock_response

        with self.assertRaises(requests.exceptions.RequestException):
            llm_client.ask_yoni("פרומפט", "this-model-does-not-exist:9b")


class TestStripCodeFences(unittest.TestCase):
    def test_closed_fence_is_stripped(self):
        text = "```python\ndef f():\n    pass\n```"
        self.assertEqual(_strip_code_fences(text), "def f():\n    pass")

    def test_unclosed_fence_is_stripped(self):
        text = "```python\ndef f():\n    pass\n"
        self.assertEqual(_strip_code_fences(text), "def f():\n    pass")

    def test_no_fence_returned_unchanged(self):
        text = "def f():\n    pass"
        self.assertEqual(_strip_code_fences(text), "def f():\n    pass")


class TestCodePlanner(unittest.TestCase):
    @patch("yoni.dev.code_planner.ask_yoni")
    def test_valid_json_on_first_attempt(self, mock_ask):
        mock_ask.return_value = json.dumps(
            {"plan": "תוכנית תקינה", "target_file": "foo.py", "file_exists": False}
        )

        result = CodePlanner().generate_plan("בקשה")

        self.assertEqual(result["plan"], "תוכנית תקינה")
        self.assertEqual(result["target_file"], "foo.py")
        self.assertEqual(mock_ask.call_count, 1)

    @patch("yoni.dev.code_planner.ask_yoni")
    def test_empty_json_triggers_one_retry(self, mock_ask):
        mock_ask.side_effect = [
            "{}",
            json.dumps({"plan": "תוכנית אחרי ניסיון שני", "target_file": "bar.py", "file_exists": True}),
        ]

        result = CodePlanner().generate_plan("בקשה")

        self.assertEqual(result["plan"], "תוכנית אחרי ניסיון שני")
        self.assertEqual(mock_ask.call_count, 2)

    @patch("yoni.dev.code_planner.ask_yoni")
    def test_empty_json_on_both_attempts_falls_back_to_raw_text(self, mock_ask):
        mock_ask.side_effect = ["{}", "{}"]

        result = CodePlanner().generate_plan("בקשה")

        self.assertEqual(result["plan"], "{}")
        self.assertIsNone(result["target_file"])
        self.assertEqual(mock_ask.call_count, 2)


class TestCodeBuilder(unittest.TestCase):
    @patch("yoni.dev.code_builder.ask_yoni")
    def test_generate_code_strips_markdown_fences(self, mock_ask):
        mock_ask.return_value = "```python\ndef add(a, b):\n    return a + b\n```"

        code = CodeBuilder().generate_code("בקשה", "תוכנית")

        self.assertEqual(code, "def add(a, b):\n    return a + b")


class TestFileOps(TempConfigTestCase):
    def test_write_then_backup_preserves_original_content(self):
        target = os.path.join(self.tmp_dir, "sample.py")
        file_ops.write_file(target, "x = 1\n")

        backup_path = file_ops.backup_file(target)
        file_ops.write_file(target, "x = 2\n")

        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "x = 2\n")
        with open(backup_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "x = 1\n")

    def test_backup_missing_file_returns_none(self):
        missing = os.path.join(self.tmp_dir, "nope.py")
        self.assertIsNone(file_ops.backup_file(missing))

    def test_read_relevant_context_small_file_returns_whole_file(self):
        target = os.path.join(self.tmp_dir, "small.py")
        content = "def foo():\n    return 1\n"
        file_ops.write_file(target, content)

        self.assertEqual(file_ops.read_relevant_context(target, "תוסיף בדיקה"), content)

    def test_read_relevant_context_large_file_extracts_matching_function_only(self):
        target = os.path.join(self.tmp_dir, "big.py")
        padding = "\n".join(f"    # padding line {i}" for i in range(400))
        content = (
            f"def unrelated_padding():\n{padding}\n    return 1\n\n"
            "def handle_undo_action(history):\n    return history.pop()\n\n"
            "def another_helper():\n    return 42\n"
        )
        file_ops.write_file(target, content)
        self.assertGreater(len(content), config.MAX_CONTEXT_CHARS)

        ctx = file_ops.read_relevant_context(target, "תוסיף אפשרות undo לבטל שינוי")

        self.assertIn("handle_undo_action", ctx)
        self.assertNotIn("unrelated_padding", ctx)

    def test_read_relevant_context_missing_file_returns_none(self):
        missing = os.path.join(self.tmp_dir, "missing.py")
        self.assertIsNone(file_ops.read_relevant_context(missing, "בקשה"))


class TestMemoryDB(TempConfigTestCase):
    def test_init_and_log_change(self):
        memory_db.init_db()
        memory_db.log_change("בקשה לדוגמה", "סיכום", ["a.py", "b.py"])

        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute("SELECT user_request, summary, files_touched FROM changes").fetchall()
        conn.close()

        self.assertEqual(len(rows), 1)
        user_request, summary, files_touched = rows[0]
        self.assertEqual(user_request, "בקשה לדוגמה")
        self.assertEqual(summary, "סיכום")
        self.assertEqual(json.loads(files_touched), ["a.py", "b.py"])

    def test_log_session_writes_to_sessions_table(self):
        memory_db.init_db()
        session_id = memory_db.log_session("student-42", 4, "סיכום שיחה")

        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute(
            "SELECT student_id, message_count, summary FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        conn.close()

        self.assertEqual(rows, [("student-42", 4, "סיכום שיחה")])

    def test_log_session_allows_null_student_id(self):
        memory_db.init_db()
        memory_db.log_session(None, 1, "סיכום")

        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute("SELECT student_id FROM sessions").fetchall()
        conn.close()

        self.assertEqual(rows, [(None,)])

    def test_sessions_and_changes_are_separate_tables(self):
        memory_db.init_db()
        memory_db.log_session("student-1", 2, "סיכום שיחה")

        conn = sqlite3.connect(config.DB_PATH)
        changes_rows = conn.execute("SELECT * FROM changes").fetchall()
        conn.close()

        self.assertEqual(changes_rows, [])


class TestMainFlow(TempConfigTestCase):
    def _run_main_with_inputs(self, inputs):
        with patch("builtins.input", side_effect=inputs):
            main()

    def _db_rows(self):
        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute("SELECT user_request FROM changes").fetchall()
        conn.close()
        return rows

    @patch("yoni.main._builder.generate_code")
    @patch("yoni.main._planner.generate_plan")
    def test_create_new_file(self, mock_plan, mock_code):
        mock_plan.return_value = {
            "plan": "יצירת פונקציית חיבור",
            "target_file": "math_utils.py",
            "file_exists": False,
        }
        mock_code.return_value = "def add(a, b):\n    return a + b\n"

        self._run_main_with_inputs(
            ["תוסיף פונקציית חיבור add(a, b) לקובץ math_utils.py", "yes", "yes", "exit"]
        )

        target = os.path.join(config.BASE_DIR, "math_utils.py")
        self.assertTrue(os.path.exists(target))
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "def add(a, b):\n    return a + b\n")
        self.assertEqual(len(self._db_rows()), 1)

    @patch("yoni.main._builder.generate_code")
    @patch("yoni.main._planner.generate_plan")
    def test_edit_existing_file_creates_backup_and_merges(self, mock_plan, mock_code):
        target = os.path.join(config.BASE_DIR, "math_utils.py")
        file_ops.write_file(target, "def add(a, b):\n    return a + b\n")

        mock_plan.return_value = {
            "plan": "הוספת פונקציית חיסור",
            "target_file": "math_utils.py",
            "file_exists": True,
        }
        mock_code.return_value = (
            "def add(a, b):\n    return a + b\n\n" "def subtract(a, b):\n    return a - b\n"
        )

        self._run_main_with_inputs(["תוסיף subtract(a, b) לקובץ math_utils.py", "yes", "yes", "exit"])

        with open(target, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("def add", content)
        self.assertIn("def subtract", content)

        backups = os.listdir(config.BACKUPS_DIR)
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].startswith("math_utils.py."))

    @patch("yoni.main._builder.generate_code")
    @patch("yoni.main._planner.generate_plan")
    def test_reject_plan_writes_nothing_and_logs_nothing(self, mock_plan, mock_code):
        mock_plan.return_value = {
            "plan": "תוכנית שתידחה",
            "target_file": "rejected.py",
            "file_exists": False,
        }

        self._run_main_with_inputs(["בקשה כלשהי", "no", "exit"])

        mock_code.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(config.BASE_DIR, "rejected.py")))
        self.assertEqual(self._db_rows(), [])

    def test_empty_stdin_exits_gracefully_without_crashing(self):
        with patch("builtins.input", side_effect=EOFError):
            try:
                main()
            except EOFError:
                self.fail("main() should catch EOFError and exit gracefully, not raise")

    @patch("yoni.main._planner.generate_plan")
    def test_nonexistent_model_error_does_not_crash_the_loop(self, mock_plan):
        mock_plan.side_effect = requests.exceptions.HTTPError(
            "404 Client Error: Not Found for url: http://localhost:11434/api/generate"
        )

        self._run_main_with_inputs(["בקשה שתיכשל בגלל מודל לא קיים", "exit"])

        mock_plan.assert_called_once()
        self.assertEqual(self._db_rows(), [])


class TestRouter(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_build_prefix_routes_to_build(self):
        self.assertEqual(self.router.route("/build תוסיף פונקציה לקובץ x.py"), "build")

    def test_build_prefix_is_case_insensitive(self):
        self.assertEqual(self.router.route("/BUILD do something"), "build")

    def test_quiz_keyword_routes_to_quiz(self):
        self.assertEqual(self.router.route("תבחן אותי במבחן קצר על לולאות"), "quiz")

    def test_chat_keyword_routes_to_chat(self):
        self.assertEqual(self.router.route("תסביר לי מה זה משתנה"), "chat")

    def test_code_question_routes_to_chat_not_build(self):
        # תלמיד ששואל על קוד הוא מקרה של Tutor, לא Builder - אין סיווג "code" לפי מילות מפתח
        self.assertEqual(self.router.route("איך כותבים פונקציה בפייתון?"), "chat")

    def test_unknown_input_falls_back_to_chat(self):
        self.assertEqual(self.router.route("בננה מטוס כיסא"), "chat")

    def test_dispatch_maps_chat_to_tutor(self):
        self.assertIs(self.router.dispatch("תסביר לי מה זה משתנה"), Tutor)

    def test_dispatch_maps_quiz_to_quiz(self):
        self.assertIs(self.router.dispatch("בוא נעשה מבחן"), Quiz)

    def test_dispatch_returns_none_for_build(self):
        self.assertIsNone(self.router.dispatch("/build תוסיף קובץ"))


class TestTutor(TempConfigTestCase):
    """יורש מ-TempConfigTestCase כי end_session() כותב ל-DB (מבודד לתיקיית זמן)."""

    def setUp(self):
        super().setUp()
        memory_db.init_db()

    @patch("yoni.agents.base.ask_yoni")
    def test_ask_appends_history_and_returns_reply(self, mock_ask):
        mock_ask.return_value = "איזה סוג משתנה אתה חושב שזה?"
        tutor = Tutor()

        reply = tutor.ask("מה זה משתנה בפייתון?")

        self.assertEqual(reply, "איזה סוג משתנה אתה חושב שזה?")
        self.assertEqual(
            tutor.history,
            [
                ("תלמיד", "מה זה משתנה בפייתון?"),
                ("יוני", "איזה סוג משתנה אתה חושב שזה?"),
            ],
        )

        sent_prompt = mock_ask.call_args.args[0]
        self.assertIn("שיטה סוקרטית", sent_prompt)
        self.assertIn("מה זה משתנה בפייתון?", sent_prompt)

    @patch("yoni.agents.base.ask_yoni")
    def test_ask_uses_configured_tutor_model(self, mock_ask):
        mock_ask.return_value = "תשובה"
        Tutor().ask("שאלה")

        sent_model = mock_ask.call_args.args[1]
        self.assertEqual(sent_model, config.TUTOR_MODEL)

    @patch("yoni.agents.base.ask_yoni")
    def test_connection_error_is_wrapped_as_agent_error(self, mock_ask):
        mock_ask.side_effect = requests.exceptions.ConnectionError("no route to host")

        with self.assertRaises(AgentError):
            Tutor().ask("שאלה")

    def test_end_session_with_empty_history_skips_model_call(self):
        summary = Tutor().end_session()
        self.assertIn("ריקה", summary)

    @patch("yoni.agents.base.ask_yoni")
    def test_end_session_logs_to_sessions_table_not_changes(self, mock_ask):
        mock_ask.side_effect = ["שאלה מנחה", "סיכום קצר של השיחה"]

        tutor = Tutor()
        tutor.ask("מה זה לולאה?")
        tutor.end_session(student_id="student-1")

        conn = sqlite3.connect(config.DB_PATH)
        session_rows = conn.execute(
            "SELECT student_id, message_count, summary FROM sessions"
        ).fetchall()
        changes_rows = conn.execute("SELECT * FROM changes").fetchall()
        conn.close()

        self.assertEqual(session_rows, [("student-1", 2, "סיכום קצר של השיחה")])
        self.assertEqual(changes_rows, [])


class TestAgentStubs(unittest.TestCase):
    def test_critic_review_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            Critic().review()


class TestHandleStudentMessage(unittest.TestCase):
    def setUp(self):
        self.router = Router()

    def test_build_intent_returns_system_note_without_calling_tutor(self):
        tutor = MagicMock()

        result = handle_student_message(self.router, tutor, "/build תוסיף קובץ")

        self.assertEqual(result["speaker"], "system")
        tutor.ask.assert_not_called()

    def test_quiz_intent_returns_start_quiz_action_without_calling_tutor(self):
        tutor = MagicMock()

        result = handle_student_message(self.router, tutor, "בוא נעשה מבחן קצר")

        self.assertEqual(result.get("action"), "start_quiz")
        self.assertEqual(result["text"], "בוא נעשה מבחן קצר")
        tutor.ask.assert_not_called()

    def test_chat_intent_calls_tutor_and_returns_reply(self):
        tutor = MagicMock()
        tutor.ask.return_value = "איזה סוג משתנה אתה חושב שזה?"

        result = handle_student_message(self.router, tutor, "מה זה משתנה?")

        tutor.ask.assert_called_once_with("מה זה משתנה?")
        self.assertEqual(result, {"speaker": "yoni", "text": "איזה סוג משתנה אתה חושב שזה?"})

    def test_agent_error_from_tutor_returns_system_note_not_raised(self):
        tutor = MagicMock()
        tutor.ask.side_effect = AgentError("שגיאה בתקשורת עם המודל (gemma3:4b): connection refused")

        result = handle_student_message(self.router, tutor, "מה זה משתנה?")

        self.assertEqual(result["speaker"], "system")
        self.assertIn("connection refused", result["text"])


VALID_QUIZ_JSON = json.dumps(
    {
        "questions": [
            {
                "question": "כמה זה 2+2?",
                "type": "exact",
                "options": None,
                "correct_answer": "4",
                "topic": "חשבון",
            },
            {
                "question": "מה צבע השמיים ביום בהיר?",
                "type": "multiple_choice",
                "options": ["כחול", "ירוק", "אדום"],
                "correct_answer": "כחול",
                "topic": "טבע",
            },
            {
                "question": "הסבר במילים שלך מהי לולאה בתכנות.",
                "type": "open",
                "options": None,
                "rubric": "התשובה מזכירה חזרה על פעולה מספר פעמים.",
                "topic": "תכנות",
            },
        ]
    },
    ensure_ascii=False,
)


class TestQuizGeneration(unittest.TestCase):
    @patch("yoni.agents.base.ask_yoni")
    def test_generate_parses_and_validates_all_types(self, mock_ask):
        mock_ask.return_value = VALID_QUIZ_JSON

        questions = Quiz().generate("בוא נעשה מבחן")

        self.assertEqual(len(questions), 3)
        by_type = {q["type"]: q for q in questions}
        # multiple_choice שומר רשימת options; שאר הסוגים מקבלים None.
        self.assertEqual(by_type["multiple_choice"]["options"], ["כחול", "ירוק", "אדום"])
        self.assertIsNone(by_type["exact"]["options"])
        self.assertIsNone(by_type["open"]["options"])
        self.assertTrue(by_type["open"]["rubric"])
        self.assertEqual(by_type["exact"]["correct_answer"], "4")

    @patch("yoni.agents.base.ask_yoni")
    def test_generate_uses_quiz_model(self, mock_ask):
        mock_ask.return_value = VALID_QUIZ_JSON
        Quiz().generate("מבחן על טבע")
        self.assertEqual(mock_ask.call_args.args[1], config.QUIZ_MODEL)

    @patch("yoni.agents.base.ask_yoni")
    def test_generate_drops_invalid_questions(self, mock_ask):
        # MC שבו correct_answer לא נמצא ב-options => לא ניתן לבדוק בקוד => נזרק.
        mock_ask.return_value = json.dumps(
            {
                "questions": [
                    {
                        "question": "שאלה תקינה",
                        "type": "exact",
                        "correct_answer": "42",
                        "topic": "x",
                    },
                    {
                        "question": "MC פסול",
                        "type": "multiple_choice",
                        "options": ["א", "ב"],
                        "correct_answer": "ג",
                        "topic": "x",
                    },
                    {"question": "בלי סוג", "correct_answer": "משהו"},
                ]
            },
            ensure_ascii=False,
        )

        questions = Quiz().generate("מבחן")

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["correct_answer"], "42")

    @patch("yoni.agents.base.ask_yoni")
    def test_generate_raises_when_no_valid_questions(self, mock_ask):
        mock_ask.return_value = json.dumps({"questions": [{"foo": "bar"}]})
        with self.assertRaises(AgentError):
            Quiz().generate("מבחן")

    @patch("yoni.agents.base.ask_yoni")
    def test_generate_raises_on_malformed_json(self, mock_ask):
        mock_ask.return_value = "זה בכלל לא JSON"
        with self.assertRaises(AgentError):
            Quiz().generate("מבחן")


class TestQuizGrading(unittest.TestCase):
    """כלל הברזל: שאלות עם תשובה יחידה נבדקות בקוד; המודל מתוקן כך שיזרוק
    כדי להוכיח שהוא לא נקרא כלל במסלול הזה."""

    MC_QUESTION = {
        "question": "מה צבע השמיים?",
        "type": "multiple_choice",
        "options": ["כחול", "ירוק"],
        "correct_answer": "כחול",
        "topic": "טבע",
    }
    EXACT_QUESTION = {
        "question": "כמה זה 2+2?",
        "type": "exact",
        "options": None,
        "correct_answer": "4",
        "topic": "חשבון",
    }
    OPEN_QUESTION = {
        "question": "מהי לולאה?",
        "type": "open",
        "options": None,
        "rubric": "מזכיר חזרה על פעולה.",
        "topic": "תכנות",
    }

    @patch("yoni.agents.base.ask_yoni", side_effect=AssertionError("המודל לא אמור להיקרא"))
    def test_multiple_choice_graded_in_code(self, _mock_ask):
        quiz = Quiz()
        self.assertTrue(quiz.grade(self.MC_QUESTION, "כחול")["correct"])
        self.assertFalse(quiz.grade(self.MC_QUESTION, "ירוק")["correct"])

    @patch("yoni.agents.base.ask_yoni", side_effect=AssertionError("המודל לא אמור להיקרא"))
    def test_exact_graded_in_code_with_normalization(self, _mock_ask):
        quiz = Quiz()
        # רווחים מיותרים ואותיות רישיות לא אמורים לפסול תשובה נכונה.
        self.assertTrue(quiz.grade(self.EXACT_QUESTION, "  4 ")["correct"])
        self.assertFalse(quiz.grade(self.EXACT_QUESTION, "5")["correct"])

    @patch("yoni.agents.base.ask_yoni", side_effect=AssertionError("המודל לא אמור להיקרא"))
    def test_exact_case_insensitive(self, _mock_ask):
        q = {"type": "exact", "question": "?", "correct_answer": "Python", "options": None}
        self.assertTrue(Quiz().grade(q, "python")["correct"])

    @patch("yoni.agents.base.ask_yoni")
    def test_open_question_uses_model_against_rubric(self, mock_ask):
        mock_ask.return_value = json.dumps(
            {"correct": True, "feedback": "יפה מאוד"}, ensure_ascii=False
        )

        result = Quiz().grade(self.OPEN_QUESTION, "לולאה חוזרת על פעולה כמה פעמים")

        self.assertTrue(result["correct"])
        self.assertEqual(result["feedback"], "יפה מאוד")
        mock_ask.assert_called_once()
        sent_prompt = mock_ask.call_args.args[0]
        self.assertIn("מזכיר חזרה על פעולה", sent_prompt)  # ה-rubric הוזרק לפרומפט

    @patch("yoni.agents.base.ask_yoni", side_effect=AssertionError("המודל לא אמור להיקרא"))
    def test_unknown_type_raises_without_calling_model(self, _mock_ask):
        with self.assertRaises(ValueError):
            Quiz().grade({"type": "bogus", "question": "?"}, "תשובה")


class TestQuizResultsDB(TempConfigTestCase):
    def setUp(self):
        super().setUp()
        memory_db.init_db()

    def test_log_quiz_result_writes_row(self):
        memory_db.log_quiz_result("student-7", "חשבון", "כמה זה 2+2?", "4", True)
        memory_db.log_quiz_result("student-7", "חשבון", "כמה זה 2+3?", "6", False)

        conn = sqlite3.connect(config.DB_PATH)
        rows = conn.execute(
            "SELECT student_id, topic, question, student_answer, correct "
            "FROM quiz_results ORDER BY id"
        ).fetchall()
        conn.close()

        self.assertEqual(
            rows,
            [
                ("student-7", "חשבון", "כמה זה 2+2?", "4", 1),
                ("student-7", "חשבון", "כמה זה 2+3?", "6", 0),
            ],
        )


class TestConstitution(unittest.TestCase):
    """כללי היסוד: תוכן, הזרקה אוטומטית לסוכני תלמיד, והדרה מסוכני הפיתוח."""

    RULE_PHRASES = (
        "אני לא משנה את עצמי",          # כלל 1
        "מידע שעלול לפגוע",             # כלל 2
        "אני לא בטוח",                  # כלל 3
        "אני לא מתחזה לאדם",            # כלל 4
        "מפנה למבוגר אחראי",           # כלל 5
    )

    def test_constitution_contains_all_five_rules(self):
        for phrase in self.RULE_PHRASES:
            self.assertIn(phrase, constitution.CONSTITUTION)

    def test_with_constitution_prepends_and_preserves_agent_prompt(self):
        agent_prompt = "פרומפט ייחודי של סוכן כלשהו"
        result = constitution.with_constitution(agent_prompt)

        self.assertIn(agent_prompt, result)
        self.assertIn("מפנה למבוגר אחראי", result)
        # הכללים באים לפני הפרומפט של הסוכן.
        self.assertLess(result.index("כללי היסוד"), result.index(agent_prompt))

    @patch("yoni.agents.base.ask_yoni")
    def test_new_base_agent_subclass_gets_constitution_automatically(self, mock_ask):
        # נועל את ההבטחה עצמה: תת-מחלקה חדשה שלא עשתה כלום מיוחד עדיין מקבלת
        # את כללי היסוד, כי ההזרקה קורית ב-BaseAgent._call_model.
        mock_ask.return_value = "תשובה כלשהי"

        class _DummyStudentAgent(BaseAgent):
            pass

        _DummyStudentAgent()._call_model("שאלה כלשהי לתלמיד")

        sent_prompt = mock_ask.call_args.args[0]
        for phrase in self.RULE_PHRASES:
            self.assertIn(phrase, sent_prompt)
        self.assertIn("שאלה כלשהי לתלמיד", sent_prompt)

    @patch("yoni.agents.base.ask_yoni")
    def test_tutor_prompt_includes_constitution(self, mock_ask):
        mock_ask.return_value = "תשובה"
        Tutor().ask("שאלה")

        sent_prompt = mock_ask.call_args.args[0]
        self.assertIn("מפנה למבוגר אחראי", sent_prompt)

    @patch("yoni.dev.code_planner.ask_yoni")
    def test_code_planner_prompt_excludes_constitution(self, mock_ask):
        mock_ask.return_value = '{"plan": "x", "target_file": null, "file_exists": false}'
        CodePlanner().generate_plan("תוסיף פונקציה לקובץ")

        sent_prompt = mock_ask.call_args.args[0]
        self.assertNotIn("כללי היסוד", sent_prompt)
        self.assertNotIn("מפנה למבוגר אחראי", sent_prompt)

    @patch("yoni.dev.code_builder.ask_yoni")
    def test_code_builder_prompt_excludes_constitution(self, mock_ask):
        mock_ask.return_value = "print('hi')"
        CodeBuilder().generate_code("בקשה", "תוכנית מאושרת")

        sent_prompt = mock_ask.call_args.args[0]
        self.assertNotIn("כללי היסוד", sent_prompt)
        self.assertNotIn("מפנה למבוגר אחראי", sent_prompt)


if __name__ == "__main__":
    unittest.main()
