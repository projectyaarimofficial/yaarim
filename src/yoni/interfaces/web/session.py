"""פתיחה, שחזור ומעבר בין שיחות - הלוגיקה המשותפת למסך הכניסה ולמסך השיחה.

מודול נפרד כדי ששני המסכים יוכלו להשתמש בו בלי ייבוא מעגלי, ובעיקר כדי
שהכלל "לא מאבדים שיחה" יישב במקום אחד: מי שנכנס שוב ממשיך את השיחה הפתוחה
שלו, ולא פותח אחת חדשה מעל השרידים של הקודמת.
"""

import streamlit as st

from yoni.domain.models import Turn


def _thread_from(turns):
    return [
        Turn(speaker=t["speaker"], text=t["text"], model_called=False)
        for t in turns
    ]


def open_or_resume(container, student) -> None:
    """נכנסים לשיחה: ממשיכים את הפתוחה אם יש, אחרת פותחים חדשה עם ברכה."""
    transcripts = container.transcripts
    existing = transcripts.open_conversation(student.student_id)

    if existing:
        st.session_state.conversation_id = existing.conversation_id
        st.session_state.thread = _thread_from(transcripts.turns(existing.conversation_id))
        st.session_state.tutor = container.conversation.resume_tutor(
            existing.conversation_id,
            container.repository.status(student.student_id),
            student.student_id,
        )
        return

    start_new(container, student)


def start_new(container, student) -> None:
    """שיחה חדשה. הברכה נבנית בקוד - בלי קריאה למודל."""
    st.session_state.conversation_id = container.transcripts.start(student.student_id)
    st.session_state.tutor = None
    greeting = container.conversation.greeting(
        student,
        status=container.repository.status(student.student_id),
        last_session=container.conversation_log.last_session(student.student_id),
    )
    st.session_state.thread = [
        Turn(speaker="yoni", text=greeting, model_called=False)
    ]
    # הברכה היא חלק מהשיחה: בלעדיה התמליל השמור מתחיל באמצע.
    container.transcripts.add_turn(
        st.session_state.conversation_id, student.student_id, "yoni", greeting)
    st.session_state.viewing = None


def open_existing(container, student, conversation_id: str) -> None:
    """פותח שיחה מההיסטוריה לקריאה בלבד."""
    st.session_state.viewing = conversation_id


def reopen(container, student, conversation_id: str) -> None:
    """ממשיך שיחה ישנה - היא חוזרת להיות השיחה הפעילה."""
    st.session_state.conversation_id = conversation_id
    st.session_state.viewing = None
    st.session_state.thread = _thread_from(container.transcripts.turns(conversation_id))
    st.session_state.tutor = container.conversation.resume_tutor(
        conversation_id,
        container.repository.status(student.student_id),
        student.student_id,
    )
