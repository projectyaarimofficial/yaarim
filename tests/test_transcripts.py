"""היסטוריית השיחות: שום דבר ממה שנאמר לא נזרק.

הבדיקה המרכזית כאן היא "שיחה שנקטעה": תלמיד שסגר דפדפן באמצע שיעור חייב
למצוא את אותה שיחה כשהוא חוזר - לא מסך ריק. זו הייתה ההתנהגות הקודמת, והיא
הסיבה שיוני פגש את התלמיד מאפס בכל פעם.
"""

import os
import unittest

from support import IsolatedProject
from yoni.infrastructure.persistence.transcripts import make_title


class TestTitle(unittest.TestCase):
    def test_short_question_becomes_the_title(self):
        self.assertEqual(make_title("מה זה שבר?"), "מה זה שבר?")

    def test_long_text_is_cut_on_a_word_boundary(self):
        title = make_title("מה " * 60)
        self.assertLessEqual(len(title), 61)
        self.assertTrue(title.endswith("…"))

    def test_whitespace_is_collapsed(self):
        self.assertEqual(make_title("  מה    זה\nשבר  "), "מה זה שבר")


class TestTranscripts(IsolatedProject):
    def setUp(self):
        super().setUp()
        self.write_safety_config()
        self.container.repository.create("dana", "דנה")
        self.transcripts = self.container.transcripts
        self.service = self.container.conversation

    def _talk(self, *messages):
        conversation_id = self.transcripts.start("dana")
        tutor = self.service.new_tutor(student_id="dana",
                                       conversation_id=conversation_id)
        for message in messages:
            self.service.handle(message, tutor, "dana", conversation_id)
        return conversation_id, tutor

    def test_every_turn_is_stored_both_sides(self):
        conversation_id, _ = self._talk("מה זה שבר?", "ומה זה מכנה?")
        turns = self.transcripts.turns(conversation_id)
        self.assertEqual([t["speaker"] for t in turns],
                         ["student", "yoni", "student", "yoni"])
        self.assertEqual(turns[0]["text"], "מה זה שבר?")

    def test_title_comes_from_the_first_student_message(self):
        conversation_id, _ = self._talk("מה זה שבר?", "ועוד שאלה")
        conversation = self.transcripts.conversations("dana")[0]
        self.assertEqual(conversation.conversation_id, conversation_id)
        self.assertEqual(conversation.title, "מה זה שבר?")
        self.assertEqual(conversation.message_count, 4)

    def test_an_interrupted_conversation_is_resumable(self):
        """אין קריאה ל-end_session - בדיוק כמו דפדפן שנסגר."""
        conversation_id, _ = self._talk("מה זה שבר?")
        still_open = self.transcripts.open_conversation("dana")
        self.assertIsNotNone(still_open)
        self.assertEqual(still_open.conversation_id, conversation_id)

        resumed = self.service.resume_tutor(conversation_id, student_id="dana")
        self.assertEqual(resumed.message_count, 2)
        self.assertIn("מה זה שבר?", resumed.build_prompt())

    def test_finished_conversation_is_no_longer_open(self):
        conversation_id, tutor = self._talk("מה זה שבר?")
        self.service.end_session(tutor, "dana", conversation_id)
        self.assertIsNone(self.transcripts.open_conversation("dana"))
        self.assertFalse(self.transcripts.conversations("dana")[0].is_open)

    def test_yoni_remembers_previous_conversations(self):
        first, tutor = self._talk("דיברנו על מערכת השמש")
        self.service.end_session(tutor, "dana", first)

        second = self.transcripts.start("dana")
        later = self.service.new_tutor(student_id="dana", conversation_id=second)
        later.ask("שלום")
        self.assertIn("מערכת השמש", self.llm.last_prompt())

    def test_current_conversation_is_not_duplicated_into_memory(self):
        conversation_id, tutor = self._talk("מה זה שבר?")
        memory = self.service.memory("dana", exclude=conversation_id)
        self.assertEqual(memory, [])

    def test_distress_turns_stay_out_of_the_model_memory(self):
        """תוכן רגיש נשמר בתיקיית התלמיד - אבל לא חוזר לפרומפט."""
        conversation_id = self.transcripts.start("dana")
        tutor = self.service.new_tutor(student_id="dana",
                                       conversation_id=conversation_id)
        self.service.handle("אני לא רוצה לחיות", tutor, "dana", conversation_id)

        stored = self.transcripts.turns(conversation_id)
        self.assertTrue(any(t["is_safety"] for t in stored))
        remembered = [t["text"] for t in self.service.memory("dana")]
        self.assertNotIn(self.container.safety_policy.escalation_message(), remembered)

    def test_a_human_readable_copy_lands_in_the_student_folder(self):
        conversation_id, _ = self._talk("מה זה שבר?")
        folder = os.path.join(self.settings.students_dir, "real", "dana",
                              "conversations")
        self.assertIn(f"{conversation_id}.json", os.listdir(folder))

    def test_empty_conversations_are_not_listed(self):
        self.transcripts.start("dana")
        self.assertEqual(self.transcripts.conversations("dana"), [])

    def test_delete_removes_the_conversation_and_its_turns(self):
        conversation_id, _ = self._talk("מה זה שבר?")
        self.assertTrue(self.transcripts.delete("dana", conversation_id))
        self.assertEqual(self.transcripts.conversations("dana"), [])
        self.assertEqual(self.transcripts.turns(conversation_id), [])

    def test_delete_also_removes_the_readable_copy(self):
        conversation_id, _ = self._talk("מה זה שבר?")
        folder = os.path.join(self.settings.students_dir, "real", "dana",
                              "conversations")
        self.transcripts.delete("dana", conversation_id)
        self.assertNotIn(f"{conversation_id}.json", os.listdir(folder))

    def test_delete_forgets_it_from_the_model_memory_too(self):
        """מחיקה שלא מוחקת מהזיכרון היא הבטחה שקרית לתלמיד."""
        first, tutor = self._talk("דיברנו על מערכת השמש")
        self.service.end_session(tutor, "dana", first)
        self.transcripts.delete("dana", first)

        second = self.transcripts.start("dana")
        later = self.service.new_tutor(student_id="dana", conversation_id=second)
        later.ask("שלום")
        self.assertNotIn("מערכת השמש", self.llm.last_prompt())

    def test_delete_refuses_another_students_conversation(self):
        self.container.repository.create("yossi", "יוסי")
        conversation_id, _ = self._talk("מה זה שבר?")
        self.assertFalse(self.transcripts.delete("yossi", conversation_id))
        self.assertEqual(len(self.transcripts.turns(conversation_id)), 2)

    def test_delete_of_a_missing_conversation_is_false_not_an_error(self):
        self.assertFalse(self.transcripts.delete("dana", "אין-כזה"))


if __name__ == "__main__":
    unittest.main()
