"""שירות הבנייה העצמית: קריאת הקשר, ושרשרת התכנון→כתיבה.

מכסה את מה שהיה ב-test_yoni.py הישן עבור file_ops ו-dev, בתוספת מה שלא היה
אפשרי קודם: לבדוק שהגדר נאכפת גם כשהנתיב מגיע מהמודל וגם כשאדם הקליד אותו.
"""

import os
import unittest

from support import FakeLanguageModel, IsolatedProject
from yoni.application.authoring import ContextReader
from yoni.container import Container
from yoni.domain.models import BuildPlan
from yoni.domain.ports import WriteDenied
from yoni.infrastructure.security.paths import ReadOnlyWritePolicy


class TestContextReader(unittest.TestCase):
    """מעל הסף נשלחות רק הפונקציות הרלוונטיות, לא כל הקובץ."""

    def setUp(self):
        self.reader = ContextReader(max_chars=200)

    def _write(self, tmpdir, source):
        path = os.path.join(tmpdir, "module.py")
        with open(path, "w", encoding="utf-8") as f:
            f.write(source)
        return path

    def test_small_file_is_sent_whole(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "def small():\n    return 1\n")
            self.assertIn("def small", self.reader.read(path, "משהו"))

    def test_large_file_keeps_only_matching_chunks(self):
        import tempfile
        source = (
            "def alpha():\n    " + "x = 1\n    " * 20 + "\n\n"
            "def target_function():\n    return 'needle'\n\n"
            "def omega():\n    " + "y = 2\n    " * 20 + "\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, source)
            context = self.reader.read(path, "עדכן את target_function")
            self.assertIn("target_function", context)
            self.assertLess(len(context), len(source))

    def test_large_file_without_match_is_truncated_with_a_notice(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "def a():\n    " + "z = 0\n    " * 60 + "\n")
            context = self.reader.read(path, "מילים שלא מופיעות בקובץ בכלל")
            self.assertIn("נחתך", context)

    def test_broken_syntax_does_not_crash(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "def broken(:\n    " + "q = 1\n    " * 60)
            self.assertIsNotNone(self.reader.read(path, "משהו"))

    def test_missing_file_is_none(self):
        self.assertIsNone(self.reader.read("/nonexistent/x.py", "בקשה"))
        self.assertIsNone(self.reader.read(None, "בקשה"))


class TestAuthoringService(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.service = self.container.authoring

    def test_plan_is_parsed_into_a_domain_object(self):
        self.llm._responses = ['{"plan":"נוסיף פונקציה","target_file":"src/new.py","file_exists":false}']
        plan = self.service.plan("הוסף פונקציה")
        self.assertIsInstance(plan, BuildPlan)
        self.assertEqual(plan.target_file, "src/new.py")

    def test_target_inside_the_project_is_resolved(self):
        resolved = self.service.resolve_target("src/new.py")
        self.assertTrue(resolved.startswith(self.root))

    def test_target_outside_the_project_is_denied(self):
        """הנתיב הגיע מהמודל - והוא נדחה בקוד, לפני שנשאלת שאלת אישור."""
        for evil in ("../../../etc/passwd", "/etc/passwd",
                     os.path.expanduser("~/.zshrc")):
            with self.assertRaises(WriteDenied, msg=evil):
                self.service.resolve_target(evil)

    def test_no_target_is_none_not_an_error(self):
        self.assertIsNone(self.service.resolve_target(None))

    def test_commit_writes_and_logs(self):
        target = self.service.resolve_target("src/created.py")
        outcome = self.service.commit("בקשה", BuildPlan("תוכנית"), "x = 1\n", target)

        self.assertTrue(os.path.exists(outcome["path"]))
        with open(outcome["path"], encoding="utf-8") as f:
            self.assertEqual(f.read(), "x = 1\n")
        self.assertIsNone(outcome["backup"], "קובץ חדש אינו דורש גיבוי")

        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.settings.db_path)) as conn:
            rows = conn.execute("SELECT user_request FROM changes").fetchall()
        self.assertEqual(rows, [("בקשה",)])

    def test_overwrite_creates_a_backup_first(self):
        target = self.service.resolve_target("src/existing.py")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write("original\n")

        outcome = self.service.commit("בקשה", BuildPlan("תוכנית"), "new\n", target)
        self.assertIsNotNone(outcome["backup"])
        with open(outcome["backup"], encoding="utf-8") as f:
            self.assertEqual(f.read(), "original\n")

    def test_commit_re_checks_the_policy(self):
        """אישור אנושי אינו עוקף את הגדר: הנתיב נבדק שוב ברגע הכתיבה."""
        with self.assertRaises(WriteDenied):
            self.service.commit("בקשה", BuildPlan("תוכנית"), "code", "/etc/evil.py")

    def test_read_only_policy_blocks_the_whole_flow(self):
        container = Container(settings=self.settings, language_model=self.llm,
                              write_policy=ReadOnlyWritePolicy())
        with self.assertRaises(WriteDenied):
            container.authoring.commit("בקשה", BuildPlan("ת"), "code", "src/ok.py")

    def test_generate_passes_existing_context_to_the_model(self):
        target = self.service.resolve_target("src/ctx.py")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            f.write("def marker_function():\n    return 1\n")

        self.llm._responses = ["print(1)"]
        self.service.generate("עדכן את marker_function", BuildPlan("תוכנית"), target)
        self.assertIn("marker_function", self.llm.last_prompt())


if __name__ == "__main__":
    unittest.main()
