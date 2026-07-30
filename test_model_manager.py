# בדיקות ל-model_manager: אכיפת "מודל כבד אחד בלבד" ותקציב VRAM. הכל ב-mock.

import unittest
from unittest.mock import patch

from yoni import config, model_manager


class TestHeavyClassification(unittest.TestCase):
    def test_heavy_models(self):
        self.assertTrue(model_manager.is_heavy("qwen2.5-coder:7b"))
        self.assertTrue(model_manager.is_heavy("qwen3:8b"))

    def test_light_models(self):
        self.assertFalse(model_manager.is_heavy("gemma3:4b"))
        self.assertFalse(model_manager.is_heavy("nomic-embed-text"))

    def test_unknown_model_not_heavy(self):
        self.assertFalse(model_manager.is_heavy("some-mock-model"))


class TestEnsureCapacity(unittest.TestCase):
    @patch("yoni.model_manager.unload")
    @patch("yoni.model_manager.loaded_models")
    def test_heavy_evicts_other_heavy(self, mock_loaded, mock_unload):
        mock_loaded.return_value = ["qwen2.5-coder:7b"]
        unloaded = model_manager.ensure_capacity("qwen3:8b")
        self.assertIn("qwen2.5-coder:7b", unloaded)
        mock_unload.assert_called_once_with("qwen2.5-coder:7b")

    @patch("yoni.model_manager.unload")
    @patch("yoni.model_manager.loaded_models")
    def test_two_heavies_never_coexist_even_via_budget(self, mock_loaded, mock_unload):
        # גם אם התקציב היה ענק - כלל "כבד אחד בלבד" חייב להתקיים.
        mock_loaded.return_value = ["qwen3:8b"]
        with patch.object(config, "VRAM_BUDGET_GB", 100.0):
            unloaded = model_manager.ensure_capacity("qwen2.5-coder:7b")
        self.assertIn("qwen3:8b", unloaded)

    @patch("yoni.model_manager.unload")
    @patch("yoni.model_manager.loaded_models")
    def test_light_next_to_heavy_ok(self, mock_loaded, mock_unload):
        # gemma3:4b (3.5) + qwen3:8b (6.0) = 9.5 > 8 -> הכבד מפונה כשמבקשים את הקל.
        mock_loaded.return_value = ["qwen3:8b"]
        unloaded = model_manager.ensure_capacity("gemma3:4b")
        self.assertIn("qwen3:8b", unloaded)

    @patch("yoni.model_manager.unload")
    @patch("yoni.model_manager.loaded_models")
    def test_light_next_to_light_untouched(self, mock_loaded, mock_unload):
        # nomic (0.4) + gemma3 (3.5) = 3.9 < 8 -> אין פינוי.
        mock_loaded.return_value = ["nomic-embed-text"]
        unloaded = model_manager.ensure_capacity("gemma3:4b")
        self.assertEqual(unloaded, [])
        mock_unload.assert_not_called()

    @patch("yoni.model_manager.loaded_models")
    def test_unknown_model_is_not_managed(self, mock_loaded):
        # מודלים לא מוכרים (כמו בבדיקות) - לא נוגעים בכלום ולא קוראים ל-ps.
        unloaded = model_manager.ensure_capacity("some-mock-model")
        self.assertEqual(unloaded, [])
        mock_loaded.assert_not_called()

    @patch("yoni.model_manager.unload")
    @patch("yoni.model_manager.loaded_models")
    def test_already_loaded_model_is_not_self_evicted(self, mock_loaded, mock_unload):
        mock_loaded.return_value = ["qwen3:8b"]
        unloaded = model_manager.ensure_capacity("qwen3:8b")
        self.assertEqual(unloaded, [])
        mock_unload.assert_not_called()


class TestStartupCheck(unittest.TestCase):
    @patch("yoni.model_manager.detect_vram_gb", return_value=8.0)
    def test_warns_about_heavy_pair(self, _mock_vram):
        warnings = model_manager.startup_check()
        joined = " ".join(warnings)
        self.assertIn("qwen2.5-coder:7b", joined)
        self.assertIn("qwen3:8b", joined)

    @patch("yoni.model_manager.detect_vram_gb", return_value=4.0)
    def test_warns_when_model_exceeds_vram(self, _mock_vram):
        warnings = model_manager.startup_check()
        self.assertTrue(any("qwen3:8b" in w and "חורג" in w for w in warnings))

    @patch("yoni.model_manager.detect_vram_gb", return_value=24.0)
    def test_no_warnings_on_big_gpu(self, _mock_vram):
        self.assertEqual(model_manager.startup_check(), [])


if __name__ == "__main__":
    unittest.main()
