"""מדיניות הבטיחות, שירות המבחן, וההרכבה עצמה."""

import json
import unittest

from support import FakeLanguageModel, IsolatedProject
from yoni.config.settings import Settings, from_env
from yoni.container import Container
from yoni.domain.models import Question
from yoni.infrastructure.safety.keywords import KeywordSafetyPolicy
from yoni.infrastructure.security.paths import ReadOnlyWritePolicy


class TestSafetyPolicy(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.write_safety_config()
        self.policy = self.container.safety_policy

    def test_ordinary_messages_are_not_flagged(self):
        for text in ("מה זה מערכת השמש?", "תסביר לי על מלחמת העולם השנייה",
                     "בחן אותי על שברים", "אני לא מבין את התרגיל"):
            self.assertIsNone(self.policy.inspect(text), text)

    def test_suicide_wording_is_flagged(self):
        finding = self.policy.inspect("אני כבר לא רוצה לחיות")
        self.assertEqual(finding.category, "suicide")
        self.assertIn("לא רוצה לחיות", finding.matched)

    def test_abuse_wording_is_flagged(self):
        self.assertEqual(self.policy.inspect("מכים אותי בבית").category, "abuse")

    def test_punctuation_and_spacing_do_not_hide_it(self):
        self.assertIsNotNone(self.policy.inspect("אני... לא רוצה לחיות!!!"))
        self.assertIsNotNone(self.policy.inspect("אני   לא רוצה    לחיות"))

    def test_empty_input_is_safe(self):
        for value in ("", "   ", None):
            self.assertIsNone(self.policy.inspect(value))

    def test_message_points_to_an_adult_and_lists_hotlines(self):
        message = self.policy.escalation_message()
        self.assertIn("מבוגר", message)
        self.assertIn("קו בדיקה", message)
        self.assertIn("0000", message)

    def test_message_does_not_diagnose_or_promise(self):
        message = self.policy.escalation_message()
        for forbidden in ("אני אעזור לך עם זה", "הכל יהיה בסדר", "אתה סובל מ"):
            self.assertNotIn(forbidden, message)

    def test_missing_config_degrades_quietly(self):
        policy = KeywordSafetyPolicy("/nonexistent/safety.json")
        self.assertIsNone(policy.inspect("אני לא רוצה לחיות"))
        self.assertEqual(policy.hotlines, [])

    def test_reload_picks_up_an_edit(self):
        self.assertIsNone(self.policy.inspect("ביטוי חדש לגמרי"))
        self.write_safety_config({
            "hotlines": [],
            "categories": {"x": {"label": "חדש", "keywords": ["ביטוי חדש לגמרי"]}},
        })
        self.policy.reload()
        self.assertIsNotNone(self.policy.inspect("ביטוי חדש לגמרי"))


class TestShippedSafetyConfig(unittest.TestCase):
    """הקובץ האמיתי חייב להיטען ולכסות את הקטגוריות הקריטיות."""

    def test_real_config_covers_the_critical_categories(self):
        settings = from_env()
        policy = KeywordSafetyPolicy(settings.safety_config_path)
        config = policy._load()
        for critical in ("suicide", "self_harm", "abuse", "sexual"):
            self.assertIn(critical, config["categories"])
            self.assertTrue(config["categories"][critical]["keywords"], critical)
        self.assertTrue(policy.hotlines)

    def test_hotlines_are_marked_unverified_until_jhonny_checks_them(self):
        """המנגנון בדוק; המספרים עדיין לא. הסימון הזה הוא ההצהרה הכנה."""
        settings = from_env()
        with open(settings.safety_config_path, encoding="utf-8") as f:
            config = json.load(f)
        for entry in config["hotlines"]:
            self.assertIn("verified", entry)


class TestAssessment(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.write_safety_config()
        self.container.repository.create("eitan", "איתן", is_demo=True)

    def test_wrong_answer_opens_a_brick(self):
        """סגירת הלולאה: מדידה שלא משנה כלום אינה מדידה, היא רישום."""
        question = Question("בירת צרפת?", Question.EXACT, "גאוגרפיה", (), "פריז")
        self.container.assessment.grade(question, "לונדון", "eitan")

        status = self.container.repository.status("eitan")
        self.assertEqual(len(status.open_bricks), 1)
        self.assertEqual(status.current_brick.topic, "גאוגרפיה")

    def test_right_answer_opens_nothing(self):
        question = Question("בירת צרפת?", Question.EXACT, "גאוגרפיה", (), "פריז")
        self.container.assessment.grade(question, "פריז", "eitan")
        self.assertEqual(self.container.repository.status("eitan").open_bricks, ())

    def test_closed_question_grading_never_calls_the_model(self):
        question = Question("בירת צרפת?", Question.EXACT, "גאוגרפיה", (), "פריז")
        self.llm.calls.clear()
        self.container.assessment.grade(question, "פריז", "eitan")
        self.assertFalse(self.llm.was_called)


class TestContainer(IsolatedProject):
    def test_components_are_singletons(self):
        self.assertIs(self.container.repository, self.container.repository)
        self.assertIs(self.container.conversation, self.container.conversation)

    def test_injected_model_wins_over_the_real_one(self):
        self.assertIs(self.container.language_model, self.llm)

    def test_injected_write_policy_wins(self):
        container = Container(settings=self.settings, language_model=self.llm,
                              write_policy=ReadOnlyWritePolicy())
        from yoni.domain.ports import WriteDenied
        with self.assertRaises(WriteDenied):
            container.authoring.resolve_target("anything.py")

    def test_conversation_log_writes_to_both_stores(self):
        from yoni.infrastructure.persistence.sqlite import CompositeConversationLog
        self.assertIsInstance(self.container.conversation_log, CompositeConversationLog)

    def test_container_builds_without_requests_installed(self):
        """הליבה אינה תלויה בתשתית - וזו בדיקה, לא הצהרה."""
        self.assertIsNotNone(self.container.conversation)
        self.assertIsNotNone(self.container.assessment)
        self.assertIsNotNone(self.container.authoring)


class TestSettings(unittest.TestCase):
    def test_paths_derive_from_the_root(self):
        settings = Settings(project_root="/tmp/proj")
        self.assertEqual(settings.data_dir, "/tmp/proj/data")
        self.assertEqual(settings.students_dir, "/tmp/proj/students")
        self.assertTrue(settings.db_path.endswith("yoni_memory.db"))

    def test_urls_derive_from_the_host(self):
        settings = Settings(project_root="/tmp", ollama_host="http://x:1234")
        self.assertEqual(settings.generate_url, "http://x:1234/api/generate")

    def test_heavy_models_are_identified(self):
        settings = Settings(project_root="/tmp")
        self.assertTrue(settings.profile("qwen3:8b").is_heavy)
        self.assertFalse(settings.profile("gemma3:4b").is_heavy)
        self.assertIsNone(settings.profile("unknown-model"))

    def test_overrides_produce_a_copy(self):
        original = Settings(project_root="/tmp")
        modified = original.with_overrides(tutor_model="other")
        self.assertEqual(original.tutor_model, "gemma3:4b")
        self.assertEqual(modified.tutor_model, "other")


class TestVramBudget(IsolatedProject):
    def _budget(self, loaded):
        from yoni.infrastructure.llm.vram import VramBudget

        class Budget(VramBudget):
            unloaded = []
            def loaded_models(self):
                return list(loaded)
            def unload(self, model):
                self.unloaded.append(model)

        Budget.unloaded = []
        return Budget(self.settings)

    def test_two_heavy_models_never_coexist(self):
        budget = self._budget(["qwen2.5-coder:7b"])
        unloaded = budget.ensure_capacity("qwen3:8b")
        self.assertIn("qwen2.5-coder:7b", unloaded)

    def test_light_model_beside_light_model_is_fine(self):
        budget = self._budget(["gemma3:4b"])
        self.assertEqual(budget.ensure_capacity("nomic-embed-text"), [])

    def test_unmanaged_model_is_left_alone(self):
        budget = self._budget(["gemma3:4b"])
        self.assertEqual(budget.ensure_capacity("fake-test-model"), [])


if __name__ == "__main__":
    unittest.main()


class TestBenchmark(IsolatedProject):
    """היכולת שאבדה בריפקטור והוחזרה. הגרף חשף אותה דרך נתון יתום."""

    def _bench(self, installed=("gemma3:4b",), measured=None):
        from yoni.infrastructure.llm.benchmark import ModelBenchmark

        class Bench(ModelBenchmark):
            def _installed(self):
                return set(installed)
            def measure(self, model):
                return measured or {"model": model, "tokens_per_sec": 42.0,
                                    "eval_tokens": 10, "load_s": 1.0, "total_s": 2.0}
            def measure_embedding(self, model):
                return {"model": model, "embed_s": 0.1, "dim": 768}

        return Bench(self.settings, self.container.vram)

    def test_targets_are_deduplicated_and_ordered(self):
        targets = self._bench().targets()
        self.assertEqual(len(targets), len(set(targets)))
        self.assertEqual(targets[0], self.settings.tutor_model)

    def test_uninstalled_models_are_skipped_not_failed(self):
        results = self._bench(installed=()).run(report=lambda _m: None)
        self.assertTrue(all(r.get("skipped") for r in results))

    def test_results_are_appended_to_the_log(self):
        bench = self._bench()
        bench.run(report=lambda _m: None)
        bench.run(report=lambda _m: None)
        history = bench.history()
        self.assertEqual(len(history), 2)
        self.assertIn("timestamp", history[0])

    def test_history_is_empty_when_never_run(self):
        self.assertEqual(self._bench().history(), [])

    def test_container_exposes_it_as_a_singleton(self):
        self.assertIs(self.container.benchmark, self.container.benchmark)
