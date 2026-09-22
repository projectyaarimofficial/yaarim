"""ממשק הווב (streamlit).

הקובץ הזה מציג ומקבל קלט. הוא לא יודע איך בודקים תשובה, איך מזהים מצוקה, או
לאן מותר לכתוב - כל זה נמצא בשירותים ומגיע דרך ה-Container.
"""

import html

import streamlit as st

from yoni.container import Container
from yoni.agents.base import AgentError
from yoni.domain.ports import LanguageModelError
from yoni.interfaces.web import session, theme
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
        "conversation_id": None, "viewing": None, "pending_delete": None,
        # דיבור הוא ברירת המחדל: קל יותר ללמוד כששומעים הסבר מאשר קוראים אותו.
        "speech_on": True, "audio_cache": {}, "last_audio": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def voice_of(container, text):
    """WAV להודעה, עם מטמון בזיכרון הסשן.

    בלי המטמון כל rerun של streamlit היה מסנתז מחדש את כל השיחה - וזה גם
    איטי וגם היה מנגן הודעות ישנות שוב.
    """
    cache = st.session_state.setdefault("audio_cache", {})
    key = hash(text)
    if key not in cache:
        cache[key] = container.speech.speak(text)
    return cache[key]


def render_turn(turn, container=None, is_last=False):
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

        # הטקסט נשאר על המסך גם במצב דיבור: מי שרוצה לעקוב בעיניים יכול.
        # מה שמשתנה הוא שההודעה *נאמרת* בלי שצריך ללחוץ.
        if (container and turn.speaker == "yoni" and not turn.safety
                and st.session_state.get("speech_on")
                and container.speech.available):
            audio = voice_of(container, turn.text)
            if audio:
                st.audio(audio, format="audio/wav", autoplay=is_last)


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

        speech_switch(container)
        history_panel(container, student)

        if st.button("התנתק"):
            for key in ("student", "tutor", "thread", "quiz",
                        "conversation_id", "viewing", "pending_delete"):
                st.session_state[key] = [] if key == "thread" else None
            st.rerun()


def speech_switch(container):
    """המתג בין דיבור לכתב. דיבור דולק כברירת מחדל."""
    if not container.speech.available:
        st.caption("🔇 מנוע הדיבור אינו זמין - השיעור בכתב.")
        st.session_state.speech_on = False
        return

    st.session_state.speech_on = st.toggle(
        "🔊 יוני מדבר", value=st.session_state.speech_on,
        help="כבה כדי ללמוד בכתב בלבד",
    )


def history_panel(container, student):
    """היסטוריית השיחות: כל שיחה שמורה במלואה, לא רק הסיכום שלה."""
    st.markdown('<p class="eyebrow">השיחות שלנו</p>', unsafe_allow_html=True)

    if st.button("➕ שיחה חדשה", use_container_width=True):
        session.start_new(container, student)
        st.rerun()

    past = container.transcripts.conversations(student.student_id, limit=30)
    if not past:
        st.caption("עוד לא דיברנו. זו השיחה הראשונה.")
        return

    for conversation in past:
        cid = conversation.conversation_id
        active = cid == st.session_state.conversation_id
        label = conversation.title or "(שיחה ללא כותרת)"
        date = (conversation.started_at or "")[:10]

        open_col, delete_col = st.columns([5, 1])
        with open_col:
            if st.button(f"{'● ' if active else ''}{label}",
                         key=f"conv_{cid}", use_container_width=True,
                         help=f"{date} · {conversation.message_count} הודעות"):
                st.session_state.viewing = None if active else cid
                st.rerun()
        with delete_col:
            if st.button("🗑", key=f"del_{cid}", help="מחק שיחה"):
                st.session_state.pending_delete = cid
                st.rerun()

        # מחיקה היא בלתי הפיכה, ולכן היא דורשת אישור מפורש ולא לחיצה אחת.
        if st.session_state.pending_delete == cid:
            st.caption(f"למחוק לצמיתות את \"{label}\"?")
            yes_col, no_col = st.columns(2)
            with yes_col:
                if st.button("כן, מחק", key=f"yes_{cid}", use_container_width=True):
                    container.transcripts.delete(student.student_id, cid)
                    st.session_state.pending_delete = None
                    if active:
                        # מחקנו את השיחה שאנחנו יושבים בה - פותחים חדשה.
                        session.start_new(container, student)
                    if st.session_state.viewing == cid:
                        st.session_state.viewing = None
                    st.rerun()
            with no_col:
                if st.button("ביטול", key=f"no_{cid}", use_container_width=True):
                    st.session_state.pending_delete = None
                    st.rerun()


def offer_microphone_download(transcriber):
    """המיקרופון דורש מודל של 1.6GB. מציעים להוריד - לא מורידים בשקט."""
    if not hasattr(transcriber, "download") or getattr(transcriber, "_broken", False):
        return
    with st.expander("🎤 להפעיל דיבור אל יוני?"):
        st.caption("נדרשת הורדה חד-פעמית של מודל ההקשבה בעברית (כ-1.6GB). "
                   "אחריה הכל עובד מקומית, בלי אינטרנט.")
        if st.button("הורד עכשיו"):
            with st.spinner("מוריד את מודל ההקשבה... זה ייקח כמה דקות."):
                transcriber.download()
            st.rerun()


def microphone(container):
    """הקלטה -> טקסט. מחזיר את מה שנאמר, או None.

    הטקסט המתומלל חוזר לאותו מסלול בדיוק של הקלדה - כולל בדיקת הבטיחות.
    תלמיד שאומר בקול משהו מדאיג חייב לקבל את אותה תגובה כאילו הקליד אותו.
    """
    transcriber = container.transcriber
    if not transcriber.available:
        offer_microphone_download(transcriber)
        return None

    recording = st.audio_input("🎤 או דבר אל יוני", key="mic")
    if recording is None:
        return None

    audio = recording.getvalue()
    # אותה הקלטה נשארת ב-widget אחרי rerun; בלי זה היינו מתמללים שוב ושוב.
    if st.session_state.get("last_audio") == hash(audio):
        return None
    st.session_state.last_audio = hash(audio)

    with st.spinner("מקשיב..."):
        said = container.transcriber.transcribe(audio)
    if not said:
        st.warning("לא הצלחתי להבין את ההקלטה. נסה שוב, או הקלד.")
        return None
    return said


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

    if st.session_state.viewing:
        render_archive(container, student)
        st.stop()

    if st.session_state.last_summary:
        st.info(f"סיכום השיחה הקודמת: {st.session_state.last_summary}")

    thread = st.session_state.thread
    for index, turn in enumerate(thread):
        # רק ההודעה האחרונה מתנגנת מעצמה - אחרת כל rerun היה מנגן הכל מחדש.
        render_turn(turn, container, is_last=(index == len(thread) - 1))

    user_input = st.chat_input("כתוב הודעה ליוני...  (למבחן: 'בחן אותי על ...')")
    user_input = user_input or microphone(container)
    if user_input:
        conversation = container.conversation
        if st.session_state.conversation_id is None:
            st.session_state.conversation_id = container.transcripts.start(
                student.student_id)
        if st.session_state.tutor is None:
            st.session_state.tutor = conversation.new_tutor(
                container.repository.status(student.student_id), student.student_id,
                st.session_state.conversation_id)
        # מצב דיבור משנה גם את אורך התשובה, לא רק את ההקראה.
        if hasattr(st.session_state.tutor, "set_spoken"):
            st.session_state.tutor.set_spoken(st.session_state.speech_on)

        from yoni.domain.models import Turn
        st.session_state.thread.append(Turn(speaker="student", text=user_input))

        try:
            with st.spinner("יוני חושב..."):
                turn = conversation.handle(
                    user_input, st.session_state.tutor, student.student_id,
                    st.session_state.conversation_id)
        except (LanguageModelError, AgentError) as e:
            st.session_state.thread.append(Turn(speaker="system", text=f"⚠️ {e}"))
            st.rerun()
            return

        if turn.action == "start_quiz":
            try:
                with st.spinner("יוני מכין מבחן..."):
                    questions = container.assessment.content_quiz(student.student_id)
                    if not questions:
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
                    st.session_state.tutor, student.student_id,
                    st.session_state.conversation_id)
            # השיחה נסגרה אבל לא נעלמה - היא עוברת להיסטוריה בסרגל הצד.
            session.start_new(container, student)
            st.rerun()
        except Exception as e:
            st.error(f"לא הצלחתי לסכם את השיחה: {e}")


def render_archive(container, student):
    """קריאה בשיחה ישנה. מוצג בלבד - כדי לכתוב בה צריך לבחור 'המשך שיחה'."""
    conversation_id = st.session_state.viewing
    header = next((c for c in container.transcripts.conversations(student.student_id)
                   if c.conversation_id == conversation_id), None)

    left, right = st.columns([3, 1])
    with left:
        st.caption(f"📁 {header.title if header else 'שיחה קודמת'}"
                   f" · {(header.started_at or '')[:16] if header else ''}")
    with right:
        if st.button("חזרה", use_container_width=True):
            st.session_state.viewing = None
            st.rerun()

    if header and header.summary:
        st.info(f"סיכום: {header.summary}")

    for turn in container.transcripts.turns(conversation_id):
        with st.chat_message("user" if turn["speaker"] == "student" else "assistant"):
            st.write(turn["text"])

    if st.button("המשך את השיחה הזו", use_container_width=True):
        session.reopen(container, student, conversation_id)
        st.rerun()


main()
