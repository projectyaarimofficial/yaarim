"""שירות המבחן: מייצר, מדרג, ורושם - כולל סגירת הלולאה.

הלולאה שהייתה פתוחה: המערכת מדדה טעויות אבל אף פעם לא *פתחה* לבנה חסרה.
כאן תשובה שגויה הופכת לנושא פתוח ב-status.json, ולכן היא חוזרת גם לברכת
הפתיחה וגם לרקע שהתלמיד מקבל בשיעור הבא.
"""

from typing import List, Optional

from ..content.seed_content import content_items
from ..domain.models import GradeResult, Question
from ..domain.ports import ConversationLog, StudentRepository


class AssessmentService:
    def __init__(self, agent_factory, conversation_log: ConversationLog,
                 repository: StudentRepository, content_db=None):
        self._agents = agent_factory
        self._log = conversation_log
        self._repo = repository
        self._content_db = content_db

    def create_quiz(self, request: str, num_questions: int = 3) -> List[Question]:
        return self._agents.create("quiz").generate(request, num_questions)

    def content_quiz(self, student_id: str, track: str = "finlit", num_questions: int = 3):
        """Read a quiz from the content bank; return an empty list when it is empty."""
        if not self._content_db:
            return []
        rows = content_items(self._content_db, track, num_questions)
        import json
        return [row | {"choices_he": json.loads(row["choices_he"])
                       if row["choices_he"] else None} for row in rows]

    def grade(self, question: Question, answer: str,
              student_id: Optional[str] = None) -> GradeResult:
        result = self._agents.create("quiz").grade(question, answer)
        if student_id:
            self._log.log_quiz_result(student_id, question, answer, result)
            if not result.correct and question.topic:
                # סגירת הלולאה: מדידה שלא משנה כלום אינה מדידה, היא רישום.
                self._repo.open_brick(student_id, question.topic, question.question)
        return result
