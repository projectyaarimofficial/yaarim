"""מסך הכניסה: מזהה + סיסמה.

כניסה והרשמה הן שתי פעולות נפרדות ומפורשות. הודעת השגיאה אחידה בכוונה - היא
לא מגלה אם המזהה קיים או שהסיסמה שגויה.
"""

import streamlit as st

from yoni.interfaces.web import theme


def _enter(container, student):
    """מכניס תלמיד מאומת, עם ברכת פתיחה שנבנית בקוד (בלי קריאה למודל)."""
    st.session_state.student = student
    conversation = container.conversation
    greeting = conversation.greeting(
        student,
        status=container.repository.status(student.student_id),
        last_session=container.conversation_log.last_session(student.student_id),
    )
    from yoni.domain.models import Turn
    st.session_state.thread = [Turn(speaker="yoni", text=greeting, model_called=False)]
    st.rerun()


def login_form(container):
    with st.form("login_form"):
        student_id = st.text_input("מזהה תלמיד (ID)", key="login_id")
        password = st.text_input("סיסמה", type="password", key="login_pw")
        if not st.form_submit_button("כניסה"):
            return
        if not student_id.strip() or not password:
            st.error("נדרשים גם מזהה וגם סיסמה.")
            return
        if not container.passwords.verify(student_id, password):
            st.error("מזהה או סיסמה שגויים.")
            return
        student = container.repository.find(student_id)
        if not student:
            st.error("המשתמש קיים אבל אין לו פרופיל תלמיד. פנה למורה.")
            return
        _enter(container, student)


def register_form(container):
    with st.form("register_form"):
        student_id = st.text_input("מזהה תלמיד (ID)", key="reg_id")
        name = st.text_input("שם", key="reg_name")
        password = st.text_input("סיסמה", type="password", key="reg_pw")
        confirm = st.text_input("אימות סיסמה", type="password", key="reg_pw2")
        if not st.form_submit_button("הרשמה"):
            return
        if not student_id.strip() or not name.strip() or not password:
            st.error("נדרשים מזהה, שם וסיסמה.")
            return
        if password != confirm:
            st.error("הסיסמאות אינן תואמות.")
            return
        if len(password) < 6:
            st.error("הסיסמה חייבת להכיל לפחות 6 תווים.")
            return
        try:
            container.passwords.create(student_id, password)
        except ValueError as error:
            st.error(str(error))
            return
        student = container.repository.find(student_id) or container.repository.create(
            student_id, name)
        _enter(container, student)


def entry_screen(container):
    # הכותרת היא הטענה של המוצר: הקיר כמעט שלם, ולבנה אחת חסרה - היא של התלמיד.
    st.markdown(
        '<div class="entry-head">'
        '<p class="eyebrow">יערים</p>'
        '<h1 class="entry-title">יוני</h1>'
        '<p class="entry-sub">נשארה <span class="accent">לבנה אחת</span>. היא שלך.</p>'
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(theme.wall(theme.ENTRY_WALL), unsafe_allow_html=True)

    login_tab, register_tab = st.tabs(["כניסה", "הרשמה"])
    with login_tab:
        login_form(container)
    with register_tab:
        register_form(container)
