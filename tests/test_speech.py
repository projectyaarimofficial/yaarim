"""דיבור: ניקוי הטקסט, והכלל שתקלת קול לא עוצרת שיעור.

הבדיקות כאן אינן מסנתזות אודיו - הן בודקות את ההחלטות שסביב הסינתזה, שהן
מה שנשבר בפועל: מה מוקרא, ומה קורה כשהמנוע חסר.
"""

import unittest

from support import IsolatedProject
from yoni.infrastructure.speech.tts import NoSpeech, PiperSpeech, speakable
from yoni.infrastructure.speech.stt import NoTranscriber


class TestSpeakable(unittest.TestCase):
    def test_markdown_is_not_read_aloud(self):
        self.assertEqual(speakable("**שלום** _עולם_"), "שלום עולם")

    def test_emoji_is_dropped(self):
        self.assertEqual(speakable("שלום 👋 עולם"), "שלום עולם")

    def test_links_are_dropped(self):
        self.assertNotIn("http", speakable("ראה https://example.com/a"))

    def test_bullets_become_plain_lines(self):
        self.assertEqual(speakable("- ראשון\n- שני"), "ראשון\nשני")

    def test_long_text_is_cut_on_a_sentence_boundary(self):
        text = ("משפט ראשון. " * 200)
        result = speakable(text)
        self.assertLessEqual(len(result), 1200)
        self.assertTrue(result.endswith("."))

    def test_empty_stays_empty(self):
        self.assertEqual(speakable(""), "")
        self.assertEqual(speakable(None), "")


class TestFallbacks(unittest.TestCase):
    def test_missing_engine_reports_unavailable_instead_of_raising(self):
        speech = PiperSpeech("לא-קיים.onnx")
        self.assertFalse(speech.available)
        self.assertIsNone(speech.speak("שלום"))

    def test_no_speech_is_explicit(self):
        self.assertFalse(NoSpeech().available)
        self.assertIsNone(NoSpeech().speak("שלום"))

    def test_no_transcriber_returns_empty_text(self):
        self.assertFalse(NoTranscriber().available)
        self.assertEqual(NoTranscriber().transcribe(b"..."), "")


class TestWiring(IsolatedProject):
    def test_speech_can_be_switched_off_by_configuration(self):
        container = self.container
        container.settings = self.settings.with_overrides(speech_enabled=False)
        self.assertFalse(container.speech.available)

    def test_microphone_can_be_switched_off_by_configuration(self):
        container = self.container
        container.settings = self.settings.with_overrides(microphone_enabled=False)
        self.assertFalse(container.transcriber.available)

    def test_model_paths_derive_from_the_project_root(self):
        self.assertTrue(self.settings.speech_voice_path.startswith(self.root))
        self.assertTrue(self.settings.stt_cache_dir.startswith(self.root))


if __name__ == "__main__":
    unittest.main()
