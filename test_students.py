# בדיקות ל-yoni.students - קריאת פרופילי תלמידים מתיקיית students/ זמנית.

import json
import os
import shutil
import tempfile
import unittest

from yoni import students


class StudentsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="yoni_students_test_")
        self.addCleanup(shutil.rmtree, self.tmp_dir, ignore_errors=True)

        original = students.STUDENTS_DIR
        self.addCleanup(lambda: setattr(students, "STUDENTS_DIR", original))
        students.STUDENTS_DIR = os.path.join(self.tmp_dir, "students")

        self._make_student("demo", "eitan", {"student_id": "eitan", "name": "איתן", "is_demo": True})

    def _make_student(self, kind, student_id, profile, status=None):
        directory = os.path.join(students.STUDENTS_DIR, kind, student_id)
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "profile.json"), "w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False)
        if status is not None:
            with open(os.path.join(directory, "status.json"), "w", encoding="utf-8") as f:
                json.dump(status, f, ensure_ascii=False)


class TestStudents(StudentsTestCase):
    def test_load_existing_profile(self):
        profile = students.load_profile("eitan")
        self.assertIsNotNone(profile)
        self.assertEqual(profile["name"], "איתן")

    def test_load_missing_profile_returns_none(self):
        self.assertIsNone(students.load_profile("nobody"))

    def test_identify_existing_uses_canonical_name(self):
        profile = students.identify("eitan", "שם אחר")
        self.assertEqual(profile["student_id"], "eitan")
        self.assertEqual(profile["name"], "איתן")  # השם הקנוני מהפרופיל גובר
        self.assertNotIn("_ad_hoc", profile)

    def test_identify_new_student_creates_persistent_profile(self):
        profile = students.identify("newkid", "דני")
        self.assertEqual(profile["name"], "דני")
        self.assertFalse(profile.get("is_demo"))
        # הפרופיל נשמר לדיסק תחת real/ - הכניסה הבאה מזהה אותו.
        reloaded = students.load_profile("newkid")
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["name"], "דני")
        # וגם status.json ריק נוצר, מוכן ללבנים חסרות.
        status = students.load_status("newkid")
        self.assertEqual(status["missing_bricks"], [])

    def test_new_profile_has_full_demo_structure(self):
        # מבנה מלא כמו תלמיד הדמו: גם תיקיות sessions/ ו-quiz_results/.
        students.create_profile("structkid", "דנה")
        directory = students.student_dir("structkid")
        self.assertTrue(os.path.isdir(os.path.join(directory, "sessions")))
        self.assertTrue(os.path.isdir(os.path.join(directory, "quiz_results")))
        self.assertTrue(os.path.exists(os.path.join(directory, "profile.json")))
        self.assertTrue(os.path.exists(os.path.join(directory, "status.json")))

    def test_log_session_appends_daily_file(self):
        students.create_profile("logkid", "רון")
        students.log_session("logkid", "סיכום ראשון", 4)
        students.log_session("logkid", "סיכום שני", 6)
        directory = students.student_dir("logkid")
        files = os.listdir(os.path.join(directory, "sessions"))
        self.assertEqual(len(files), 1)  # אותו יום -> אותו קובץ
        with open(os.path.join(directory, "sessions", files[0]), encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["student_id"], "logkid")
        self.assertEqual([s["summary"] for s in data["sessions"]], ["סיכום ראשון", "סיכום שני"])
        self.assertEqual(data["sessions"][0]["message_count"], 4)

    def test_last_session_returns_most_recent(self):
        students.create_profile("memkid", "נעם")
        students.log_session("memkid", "סיכום ישן", 2)
        students.log_session("memkid", "סיכום חדש", 5)
        last = students.last_session("memkid")
        self.assertEqual(last["summary"], "סיכום חדש")
        self.assertIn("date", last)

    def test_last_session_none_when_empty(self):
        students.create_profile("emptykid", "רות")
        self.assertIsNone(students.last_session("emptykid"))

    def test_greeting_new_student(self):
        profile = students.identify("greetnew", "נועה")
        greeting = students.build_greeting(profile)
        self.assertIn("נועה", greeting)
        self.assertIn("נעים להכיר", greeting)

    def test_greeting_returning_with_last_session(self):
        students.create_profile("greetback", "עומר")
        students.log_session("greetback", "דיברנו על שברים.", 4)
        profile = students.identify("greetback", "עומר")  # כניסה שנייה
        greeting = students.build_greeting(
            profile, last=students.last_session("greetback")
        )
        self.assertIn("עומר", greeting)
        self.assertIn("טוב לראות אותך שוב", greeting)
        self.assertIn("דיברנו על שברים.", greeting)

    def test_greeting_returning_with_open_brick(self):
        greeting = students.build_greeting(
            {"student_id": "x", "name": "איתן"},
            status={"missing_bricks": [{"topic": "מערכת השמש", "status": "open"}]},
        )
        self.assertIn("איתן", greeting)
        self.assertIn("מערכת השמש", greeting)

    def test_greeting_returning_plain(self):
        greeting = students.build_greeting({"student_id": "x", "name": "דנה"})
        self.assertIn("דנה", greeting)
        self.assertIn("טוב לראות אותך שוב", greeting)

    def test_log_quiz_result_matches_demo_format(self):
        students.create_profile("quizkid", "גיל")
        exact_q = {
            "topic": "מערכת השמש", "question": "מה במרכז?", "type": "exact",
            "correct_answer": "שמש", "options": None, "rubric": None,
        }
        open_q = {
            "topic": "מערכת השמש", "question": "מהו כדור הארץ?", "type": "open",
            "correct_answer": None, "options": None, "rubric": "הסבר סביר",
        }
        students.log_quiz_result("quizkid", exact_q, "השמש", False)
        students.log_quiz_result("quizkid", open_q, "כוכב לכת", True)
        directory = students.student_dir("quizkid")
        files = os.listdir(os.path.join(directory, "quiz_results"))
        with open(os.path.join(directory, "quiz_results", files[0]), encoding="utf-8") as f:
            data = json.load(f)
        first, second = data["results"]
        # exact: כולל correct_answer (כמו בדמו); open: בלי.
        self.assertEqual(first["correct_answer"], "שמש")
        self.assertFalse(first["correct"])
        self.assertNotIn("correct_answer", second)
        self.assertTrue(second["correct"])

    def test_identify_requires_both_fields(self):
        with self.assertRaises(ValueError):
            students.identify("", "דני")
        with self.assertRaises(ValueError):
            students.identify("newkid", "")

    def test_load_status(self):
        self._make_student(
            "demo",
            "withstatus",
            {"student_id": "withstatus", "name": "x"},
            {"missing_bricks": [{"topic": "t", "brick": "b", "status": "open"}]},
        )
        status = students.load_status("withstatus")
        self.assertEqual(status["missing_bricks"][0]["status"], "open")

    def test_list_students(self):
        ids = {s[0] for s in students.list_students()}
        self.assertIn("eitan", ids)


if __name__ == "__main__":
    unittest.main()
