"""מסך המבחן: שאלה-שאלה, עם טפסים.

הממשק לא יודע מי מדרג מה. הוא קורא ל-assessment.grade ומקבל תוצאה; הניתוב
לקוד או למודל מתרחש עמוק יותר, ולא ניתן לעקיפה מכאן.
"""

import streamlit as st

from yoni.domain.models import Question


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
        if st.button("חזרה לשיחה"):
            st.session_state.quiz = None
            st.rerun()
        return

    question = questions[idx]
    st.info(f"מבחן — שאלה {idx + 1} מתוך {total}")
    st.markdown(f"**{question.question}**")

    with st.form(f"quiz_form_{idx}"):
        if question.type == Question.MULTIPLE_CHOICE:
            answer = st.radio("בחר תשובה:", list(question.options), key=f"ans_{idx}")
        elif question.type == Question.EXACT:
            answer = st.text_input("התשובה שלך:", key=f"ans_{idx}")
        else:
            answer = st.text_area("התשובה שלך:", key=f"ans_{idx}")
        submitted = st.form_submit_button("שלח תשובה")

    if submitted:
        try:
            with st.spinner("יוני בודק..."):
                result = container.assessment.grade(question, answer, student.student_id)
        except Exception as error:
            st.error(str(error))
            return
        quiz["results"].append(result)
        quiz["idx"] += 1
        st.rerun()
