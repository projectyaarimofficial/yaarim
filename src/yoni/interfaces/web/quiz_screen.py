"""מסך המבחן: שאלה-שאלה, עם טפסים.

הממשק לא יודע מי מדרג מה. הוא קורא ל-assessment.grade ומקבל תוצאה; הניתוב
לקוד או למודל מתרחש עמוק יותר, ולא ניתן לעקיפה מכאן.
"""

import streamlit as st

from yoni.domain.models import GradeResult, Question


def render_quiz(container, student):
    quiz = st.session_state.quiz
    questions = quiz["questions"]
    idx = quiz["idx"]
    total = len(questions)

    if idx >= total:
        correct = sum(1 for r in quiz["results"] if r.correct)
        st.success(f"סיימת את המבחן! ענית נכון על {correct} מתוך {total}. ✅")
        for i, result in enumerate(quiz["results"], start=1):
            st.write(f"{'✅' if result.correct else '❌'} שאלה {i}: {result.feedback}")
            explanations = quiz.get("explanations", [])
            if i <= len(explanations) and explanations[i - 1]:
                st.caption(explanations[i - 1])
        if st.button("חזרה לשיחה"):
            st.session_state.quiz = None
            st.rerun()
        return

    question = questions[idx]
    st.info(f"מבחן — שאלה {idx + 1} מתוך {total}")
    is_content_item = isinstance(question, dict)
    prompt = question["prompt_he"] if is_content_item else question.question
    st.markdown(f"**{prompt}**")

    with st.form(f"quiz_form_{idx}"):
        question_type = question.get("kind") if is_content_item else question.type
        if question_type in ("mcq", Question.MULTIPLE_CHOICE):
            choices = question["choices_he"] if is_content_item else question.options
            answer = st.radio("בחר תשובה:", list(choices), key=f"ans_{idx}")
        elif question_type in ("numeric", Question.EXACT):
            answer = st.text_input("התשובה שלך:", key=f"ans_{idx}")
        else:
            answer = st.text_area("התשובה שלך:", key=f"ans_{idx}")
        submitted = st.form_submit_button("שלח תשובה")

    if submitted:
        try:
            with st.spinner("יוני בודק..."):
                if is_content_item:
                    graded = container.mastery.record_attempt(
                        student.student_id, question["id"], answer)
                    result = GradeResult(
                        correct=graded["verdict"] == "correct",
                        feedback=("נכון! כל הכבוד." if graded["verdict"] == "correct"
                                  else "התשובה נרשמה לבדיקה."),
                        graded_by=graded["graded_by"],
                    )
                else:
                    result = container.assessment.grade(question, answer, student.student_id)
        except Exception as error:
            st.error(str(error))
            return
        quiz["results"].append(result)
        if is_content_item:
            quiz.setdefault("explanations", []).append(question["explain_he"])
        else:
            quiz.setdefault("explanations", []).append(None)
        quiz["idx"] += 1
        st.rerun()
