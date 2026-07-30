"""אחסון: תלמידים, יומנים, הרכבה של שני מקורות, וסיסמאות."""

import json
import os
import unittest

from support import IsolatedProject
from yoni.domain.models import GradeResult, Question, SafetyFinding
from yoni.infrastructure.persistence.sqlite import CompositeConversationLog


class TestStudentRepository(IsolatedProject):
    def test_create_then_find(self):
        created = self.container.repository.create("eitan", "איתן", is_demo=True)
        self.assertTrue(created.is_new)
        found = self.container.repository.find("eitan")
        self.assertEqual(found.name, "איתן")
        self.assertTrue(found.is_demo)
        self.assertFalse(found.is_new, "תלמיד שנטען מהדיסק אינו חדש")

    def test_create_builds_the_full_layout(self):
        self.container.repository.create("eitan", "איתן")
        directory = self.container.repository.directory("eitan")
        for sub in ("sessions", "quiz_results", "alerts"):
            self.assertTrue(os.path.isdir(os.path.join(directory, sub)), sub)
        self.assertTrue(os.path.exists(os.path.join(directory, "status.json")))

    def test_unknown_student_is_none(self):
        self.assertIsNone(self.container.repository.find("nobody"))
        self.assertIsNone(self.container.repository.directory(""))

    def test_demo_and_real_are_separate(self):
        self.container.repository.create("a", "דמו", is_demo=True)
        self.container.repository.create("b", "אמיתי", is_demo=False)
        self.assertIn("demo", self.container.repository.directory("a"))
        self.assertIn("real", self.container.repository.directory("b"))

    def test_status_is_empty_for_a_new_student(self):
        self.container.repository.create("eitan", "איתן")
        status = self.container.repository.status("eitan")
        self.assertEqual(status.open_bricks, ())
        self.assertIsNone(status.current_brick)

    def test_open_brick_then_read_it_back(self):
        self.container.repository.create("eitan", "איתן")
        self.container.repository.open_brick("eitan", "שברים", "מכנה משותף")
        status = self.container.repository.status("eitan")
        self.assertEqual(len(status.open_bricks), 1)
        self.assertEqual(status.current_brick.topic, "שברים")

    def test_open_brick_is_not_duplicated(self):
        self.container.repository.create("eitan", "איתן")
        for _ in range(3):
            self.container.repository.open_brick("eitan", "שברים", "מכנה משותף")
        self.assertEqual(len(self.container.repository.status("eitan").open_bricks), 1)

    def test_list_all_returns_both_kinds(self):
        self.container.repository.create("a", "אחד", is_demo=True)
        self.container.repository.create("b", "שתיים")
        self.assertEqual(len(self.container.repository.list_all()), 2)


class TestConversationLogs(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.container.repository.create("eitan", "איתן", is_demo=True)
        self.log = self.container.conversation_log

    def _read(self, subdir, key):
        directory = self.container.repository.directory("eitan")
        path = os.path.join(directory, subdir, f"{self.clock.today()}.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)[key]

    def test_session_lands_in_both_stores(self):
        """שני מקורות אינם כפילות מקרית - זו החלטה, במקום אחד."""
        self.log.log_session("eitan", "סיכום", 4)
        self.assertEqual(self._read("sessions", "sessions")[0]["summary"], "סיכום")
        self.assertEqual(self.container.sqlite_log.last_session("eitan")["summary"], "סיכום")

    def test_quiz_result_records_who_graded(self):
        q = Question("מה?", Question.EXACT, "נושא", (), "פריז")
        self.log.log_quiz_result("eitan", q, "לונדון", GradeResult(False, "לא", "code"))
        record = self._read("quiz_results", "results")[0]
        self.assertFalse(record["correct"])
        self.assertEqual(record["graded_by"], "code")
        self.assertEqual(record["correct_answer"], "פריז")

    def test_alert_keeps_text_in_files_and_only_a_count_in_sql(self):
        """התוכן הרגיש נשאר בתיקיית התלמיד; ל-SQL הולכת רק העובדה."""
        finding = SafetyFinding("abuse", "אלימות", ("מכים אותי",))
        self.log.log_alert("eitan", finding, "טקסט רגיש של ילד")
        self.assertEqual(self._read("alerts", "alerts")[0]["student_text"], "טקסט רגיש של ילד")

        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            rows = conn.execute("SELECT category FROM alerts").fetchall()
        self.assertEqual(rows, [("abuse",)])

    def test_last_session_prefers_the_first_log(self):
        self.log.log_session("eitan", "מהקבצים", 1)
        self.assertEqual(self.log.last_session("eitan")["summary"], "מהקבצים")

    def test_unknown_student_does_not_crash(self):
        self.assertIsNone(
            self.container.conversation_log.last_session("nobody"))


class TestCompositePolymorphism(IsolatedProject):
    def test_composite_writes_to_every_target(self):
        class Spy:
            def __init__(self):
                self.sessions = []
            def log_session(self, *args):
                self.sessions.append(args); return "ok"
            def log_quiz_result(self, *args): ...
            def log_alert(self, *args): ...
            def last_session(self, _sid): return None

        a, b = Spy(), Spy()
        CompositeConversationLog(a, b).log_session("x", "s", 1)
        self.assertEqual(len(a.sessions), 1)
        self.assertEqual(len(b.sessions), 1)


class TestPasswords(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.store = self.container.passwords

    def test_create_then_verify(self):
        self.store.create("eitan", "sod123")
        self.assertTrue(self.store.verify("eitan", "sod123"))

    def test_wrong_password_fails(self):
        self.store.create("eitan", "sod123")
        self.assertFalse(self.store.verify("eitan", "wrong"))

    def test_unknown_user_fails(self):
        self.assertFalse(self.store.verify("nobody", "any"))

    def test_duplicate_is_refused(self):
        self.store.create("eitan", "sod123")
        with self.assertRaises(ValueError):
            self.store.create("eitan", "other")

    def test_missing_values_are_refused(self):
        with self.assertRaises(ValueError):
            self.store.create("", "x")
        self.assertFalse(self.store.verify("", ""))

    def test_password_is_never_stored_in_clear(self):
        self.store.create("eitan", "sod123")
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            row = conn.execute("SELECT salt, password_hash FROM users").fetchone()
        self.assertNotIn("sod123", row[1])
        self.assertTrue(len(row[0]) >= 32)


if __name__ == "__main__":
    unittest.main()
