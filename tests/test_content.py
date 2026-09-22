import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta

from yoni.content.grader import grade, parse_number
from yoni.content.mastery import MasteryService
from yoni.content.seed_content import seed_content


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOPICS = os.path.join(ROOT, "data", "finlit_topics.json")
ITEMS = os.path.join(ROOT, "data", "finlit_items.json")
SCHEMA = os.path.join(ROOT, "schema_topics.sql")


class ContentTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp()
        self.db = os.path.join(self.temp, "yoni_memory.db")
        self.assertEqual(seed_content(self.db, TOPICS, ITEMS, SCHEMA), [])

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_seed_counts_and_idempotence(self):
        seed_content(self.db, TOPICS, ITEMS, SCHEMA)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM topics").fetchone()[0], 15)
            self.assertGreaterEqual(db.execute("SELECT count(*) FROM items").fetchone()[0], 25)

    def test_cycle_is_rejected_without_writing(self):
        with open(TOPICS, encoding="utf-8") as handle:
            topics = json.load(handle)
        topics["topics"][0]["prereqs"] = [topics["topics"][1]["id"]]
        topics["topics"][1]["prereqs"] = [topics["topics"][0]["id"]]
        bad_topics = os.path.join(self.temp, "bad_topics.json")
        with open(bad_topics, "w", encoding="utf-8") as handle:
            json.dump(topics, handle, ensure_ascii=False)
        bad_db = os.path.join(self.temp, "cycle.db")
        errors = seed_content(bad_db, bad_topics, ITEMS, SCHEMA)
        self.assertTrue(any("cycle" in error for error in errors))
        self.assertFalse(os.path.exists(bad_db))

    def test_number_parser_and_unparseable_grading(self):
        self.assertEqual(parse_number("180"), 180)
        self.assertEqual(parse_number("180 ש\"ח"), 180)
        self.assertEqual(parse_number("\u200f1,210"), 1210)
        item = {"kind": "numeric", "answer": 180, "tolerance": 0}
        self.assertEqual(grade(item, "junk")["verdict"], "needs_review")
        self.assertEqual(grade(item, "181")["verdict"], "wrong")

    def test_numeric_answers_match_declared_values(self):
        with open(ITEMS, encoding="utf-8") as handle:
            items = json.load(handle)["items"]
        expected = {
            "money-1": 15, "percent-1": 96, "percent-2": 170, "percent-3": 295,
            "bank-2": 1030, "payslip-1": 10200, "budget-1": 1800,
            "saving-1": 200, "simple-1": 400, "simple-2": 2300,
            "compound-1": 12100, "inflation-2": 220, "loan-1": 10800,
            "loan-2": 11400, "overdraft-1": 360, "tax-2": 18, "risk-1": 10,
        }
        for item in items:
            if item["kind"] == "numeric":
                self.assertEqual(item["answer"], expected[item["id"]])

    def test_attempts_update_mastery_and_schedule(self):
        service = MasteryService(self.db)
        right = service.record_attempt("eitan", "money-1", "15")
        wrong = service.record_attempt("eitan", "money-1", "16")
        open_result = service.record_attempt("eitan", "needs-2", "דוגמה במסגרת התקציב")
        self.assertEqual(right["verdict"], "correct")
        self.assertEqual(wrong["verdict"], "wrong")
        self.assertEqual(open_result["verdict"], "needs_review")
        with sqlite3.connect(self.db) as db:
            row = db.execute(
                "SELECT score, attempts, next_due FROM mastery WHERE student_id='eitan' AND topic_id='money-basics'"
            ).fetchone()
            self.assertEqual(row[1], 2)
            self.assertEqual(row[2], (date.today() + timedelta(days=1)).isoformat())
            self.assertLess(row[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM attempts").fetchone()[0], 3)


if __name__ == "__main__":
    unittest.main()
