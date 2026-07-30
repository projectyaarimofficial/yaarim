"""כלי עזר לבדיקות: מימושים מזויפים של הפורטים.

זה הרווח המעשי מהזרקת תלויות: אין כאן שום patch של מודול. מזריקים אובייקט אחר,
וזהו. FakeLanguageModel גם *מתעד* אם נשאל בכלל - וזה מה שמאפשר לבדוק את הטענה
החשובה ביותר במערכת: שבמצוקה, המודל לא נשאל.
"""

import os
import shutil
import tempfile
import unittest

from yoni.config.settings import Settings
from yoni.container import Container
from yoni.domain.ports import Clock, LanguageModel, LanguageModelError


class FakeClock(Clock):
    def __init__(self, day="2026-01-01", moment="2026-01-01T09:00:00"):
        self._day, self._moment = day, moment

    def today(self):
        return self._day

    def now(self):
        return self._moment


class FakeLanguageModel(LanguageModel):
    """מודל מזויף. מתעד כל קריאה, ומחזיר תשובות שנקבעו מראש."""

    def __init__(self, responses=None, fail=False):
        self.calls = []
        self._responses = list(responses or [])
        self._fail = fail

    @property
    def was_called(self):
        return bool(self.calls)

    @property
    def call_count(self):
        return len(self.calls)

    def last_prompt(self):
        return self.calls[-1]["prompt"] if self.calls else None

    def complete(self, prompt, model=None, expect_json=False):
        self.calls.append({"prompt": prompt, "model": model, "json": expect_json})
        if self._fail:
            raise LanguageModelError("מודל לא זמין (מזויף)")
        return self._responses.pop(0) if self._responses else "תשובה מזויפת"

    def embed(self, text, model=None):
        self.calls.append({"prompt": text, "model": model, "embed": True})
        return [0.0, 0.1, 0.2]


class IsolatedProject(unittest.TestCase):
    """פרויקט זמני מלא לכל בדיקה - כולל students/ ו-data/, בלי לגעת באמיתי."""

    def setUp(self):
        self.root = os.path.realpath(tempfile.mkdtemp())
        os.makedirs(os.path.join(self.root, "data"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "students", "demo"), exist_ok=True)
        os.makedirs(os.path.join(self.root, "students", "real"), exist_ok=True)
        self.settings = Settings(project_root=self.root)
        self.llm = FakeLanguageModel()
        self.clock = FakeClock()
        self.container = Container(
            settings=self.settings, language_model=self.llm, clock=self.clock
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def write_safety_config(self, config=None):
        import json
        config = config or {
            "hotlines": [{"name": "קו בדיקה", "phone": "0000"}],
            "categories": {
                "suicide": {"label": "מחשבות אובדניות",
                            "keywords": ["לא רוצה לחיות", "להתאבד"]},
                "abuse": {"label": "אלימות או התעללות", "keywords": ["מכים אותי"]},
            },
        }
        with open(self.settings.safety_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False)
        return config
