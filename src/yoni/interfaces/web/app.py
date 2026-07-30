"""ממשק הווב (streamlit).

הקובץ הזה מציג ומקבל קלט. הוא לא יודע איך בודקים תשובה, איך מזהים מצוקה, או
לאן מותר לכתוב - כל זה נמצא בשירותים ומגיע דרך ה-Container.
"""

import html

import streamlit as st

from yoni.container import Container
from yoni.domain.ports import LanguageModelError
from yoni.interfaces.web import theme
from yoni.interfaces.web.auth_screen import entry_screen
from yoni.interfaces.web.quiz_screen import render_quiz


def boot():
    """מרכיב את המערכת פעם אחת לכל הרצה, ושומר ב-session."""
    if "container" not in st.session_state:
        st.session_state.container = Container()
    return st.session_state.container


def init_state():
    defaults = {
        "student": None, "tutor": None, "thread": [],
        "last_summary": None, "quiz": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_turn(turn):
    """הודעת מצוקה מקבלת מסגרת רכה - הפניה, לא אזעקה.

    בכוונה אין אדום ואין סימן אזהרה: ילד שסיפר משהו קשה לא צריך לפגוש מסך
    שנראה כמו שגיאה. ענבר, אותו צבע של "הנושא שעובדים עליו עכשיו".
    """
    role = "user" if turn.speaker == "student" else "assistant"
    with st.chat_message(role):
        if turn.safety:
            lines = "".join(
                f'<span class="care-line">{html.escape(line)}</span>'
                for line in turn.text.split("\n")
            )
            st.markdown(f'<div class="care">{lines}</div>', unsafe_allow_html=True)
        else:
            st.write(turn.text)


def sidebar(container, student):
    with st.sidebar:
        st.markdown(
            f'<p class="who">{html.escape(student.name)}</p>'
            f'<p class="who-id">{html.escape(student.student_id)}</p>',
            unsafe_allow_html=True,
        )
        status = container.repository.status(student.student_id)
        open_bricks = status.open_bricks

        # הקיר כאן אמיתי: הוא נבנה מ-status.json של התלמיד.
        st.markdown('<p class="eyebrow">הקיר שלך</p>', unsafe_allow_html=True)
        st.markdown(theme.student_wall(open_bricks), unsafe_allow_html=True)
        if open_bricks:
            for i, brick in enumerate(open_bricks):
                st.caption(f"{'●' if i == 0 else '○'} {brick.topic} — {brick.description}")
        else:
            st.caption("אין נושאים פתוחים כרגע.")

        if st.button("התנתק"):
            for key in ("student", "tutor", "thread", "quiz"):
                st.session_state[key] = [] if key == "thread" else None
            st.rerun()


def main():
    st.set_page_config(page_title="יוני - YAARIM", page_icon="🧱", layout="centered")
    st.markdown(theme.css(), unsafe_allow_html=True)

    container = boot()
    init_state()

    if not st.session_state.student:
        entry_screen(container)
        st.stop()

    student = st.session_state.student
    sidebar(container, student)

    if st.session_state.quiz is not None:
        render_quiz(container, student)
        st.stop()

    st.markdown('<h1 class="entry-title" style="font-size:2.1rem;">יוני</h1>',
                unsafe_allow_html=True)

    if st.session_state.last_summary:
        st.info(f"סיכום השיחה הקודמת: {st.session_state.last_summary}")

    for turn in st.session_state.thread:
        render_turn(turn)

    user_input = st.chat_input("כתוב הודעה ליוני...  (למבחן: 'בחן אותי על ...')")
    if user_input:
        conversation = container.conversation
        if st.session_state.tutor is None:
            st.session_state.tutor = conversation.new_tutor(
                container.repository.status(student.student_id))

        from yoni.domain.models import Turn
        st.session_state.thread.append(Turn(speaker="student", text=user_input))

        try:
            with st.spinner("יוני חושב..."):
                turn = conversation.handle(
                    user_input, st.session_state.tutor, student.student_id)
        except LanguageModelError as e:
            st.session_state.thread.append(Turn(speaker="system", text=f"⚠️ {e}"))
            st.rerun()
            return

        if turn.action == "start_quiz":
            try:
                with st.spinner("יוני מכין מבחן..."):
                    questions = container.assessment.create_quiz(user_input)
                st.session_state.quiz = {"questions": questions, "idx": 0, "results": []}
            except Exception as e:  # AgentError או שגיאת מודל
                st.session_state.thread.append(Turn(speaker="system", text=f"⚠️ {e}"))
        else:
            st.session_state.thread.append(turn)
        st.rerun()

    if st.button("סיים שיחה", disabled=st.session_state.tutor is None):
        try:
            with st.spinner("יוני חושב..."):
                st.session_state.last_summary = container.conversation.end_session(
                    st.session_state.tutor, student.student_id)
            st.session_state.tutor = None
            st.session_state.thread = []
            st.rerun()
        except Exception as e:
            st.error(f"לא הצלחתי לסכם את השיחה: {e}")


main()
