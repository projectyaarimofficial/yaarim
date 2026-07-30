import streamlit as st

from yoni import memory_db, students
from yoni.agents import AgentError, Quiz, Router, Tutor, handle_student_message

st.set_page_config(page_title="יוני - YAARIM", page_icon="🌲")

RTL_CSS = """
<style>
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    direction: rtl;
}
[data-testid="stChatMessage"] {
    direction: rtl;
    text-align: right;
}
[data-testid="stChatInput"] textarea,
[data-testid="stTextInput"] input,
textarea, input {
    direction: rtl;
    text-align: right;
}
.stMarkdown, .stAlert, h1, h2, h3, p, label {
    direction: rtl;
    text-align: right;
}
</style>
"""
st.markdown(RTL_CSS, unsafe_allow_html=True)

memory_db.init_db()

if "student" not in st.session_state:
    st.session_state.student = None
if "tutor" not in st.session_state:
    st.session_state.tutor = None
if "thread" not in st.session_state:
    st.session_state.thread = []
if "last_summary" not in st.session_state:
    st.session_state.last_summary = None
if "quiz" not in st.session_state:
    st.session_state.quiz = None

router = Router()


# ---------------------------------------------------------------------------
# מסך כניסה: זיהוי התלמיד לפי מזהה + שם. חוסם את הגישה עד שמזוהה תלמיד.
# ---------------------------------------------------------------------------
def entry_screen():
    st.title("🌲 יוני - מערכת YAARIM")
    st.subheader("כניסה")
    with st.form("entry_form"):
        student_id = st.text_input("מזהה תלמיד (ID)", key="entry_id")
        name = st.text_input("שם", key="entry_name")
        submitted = st.form_submit_button("כניסה")
        if submitted:
            try:
                profile = students.identify(student_id, name)
            except ValueError as error:
                st.error(str(error))
            else:
                st.session_state.student = profile
                # ברכת פתיחה אוטומטית: שלום + שם + פרט קטן מהזיכרון,
                # כדי שהתלמיד ירגיש (ובצדק) שהמערכת זוכרת אותו.
                sid = profile["student_id"]
                greeting = students.build_greeting(
                    profile,
                    status=students.load_status(sid),
                    last=students.last_session(sid),
                )
                st.session_state.thread = [{"speaker": "yoni", "text": greeting}]
                st.rerun()


if not st.session_state.student:
    entry_screen()
    st.stop()


student = st.session_state.student
student_id = student["student_id"]


# ---------------------------------------------------------------------------
# מבחן אינטראקטיבי: state בתוך session_state.quiz, שאלה-שאלה עם טפסים.
# multiple_choice/exact נבדקות בקוד (Quiz.grade), open נבדקת מול rubric דרך המודל.
# ---------------------------------------------------------------------------
def render_quiz():
    quiz = st.session_state.quiz
    questions = quiz["questions"]
    idx = quiz["idx"]
    total = len(questions)

    if idx >= total:  # סיום - מסך סיכום
        correct = sum(1 for r in quiz["results"] if r["correct"])
        st.success(f"סיימת את המבחן! ענית נכון על {correct} מתוך {total}. ✅")
        for i, result in enumerate(quiz["results"], start=1):
            icon = "✅" if result["correct"] else "❌"
            st.write(f"{icon} שאלה {i}: {result['feedback']}")
        if st.button("חזרה לשיחה"):
            st.session_state.quiz = None
            st.rerun()
        return

    question = questions[idx]
    st.info(f"מבחן — שאלה {idx + 1} מתוך {total}")
    st.markdown(f"**{question['question']}**")

    with st.form(f"quiz_form_{idx}"):
        if question["type"] == "multiple_choice":
            answer = st.radio("בחר תשובה:", question["options"], key=f"quiz_ans_{idx}")
        elif question["type"] == "exact":
            answer = st.text_input("התשובה שלך:", key=f"quiz_ans_{idx}")
        else:  # open
            answer = st.text_area("התשובה שלך:", key=f"quiz_ans_{idx}")
        submitted = st.form_submit_button("שלח תשובה")

    if submitted:
        try:
            with st.spinner("יוני בודק..."):
                result = Quiz().grade(question, answer)
        except AgentError as error:
            st.error(str(error))
            return
        memory_db.log_quiz_result(
            student_id,
            question.get("topic"),
            question.get("question"),
            answer,
            result["correct"],
        )
        # רישום גם לתיקיית התלמיד (quiz_results/YYYY-MM-DD.json), כמו במבנה הדמו.
        students.log_quiz_result(student_id, question, answer, result["correct"])
        quiz["results"].append(result)
        quiz["idx"] += 1
        st.rerun()


# ---------------------------------------------------------------------------
# המסך הראשי (אחרי כניסה).
# ---------------------------------------------------------------------------
st.title("🌲 יוני - מערכת YAARIM")

with st.sidebar:
    st.write(f"👤 **{student.get('name', '')}**  ({student_id})")

    status = students.load_status(student_id)
    open_bricks = [
        b for b in (status or {}).get("missing_bricks", []) if b.get("status") == "open"
    ]
    if open_bricks:
        st.caption("🧱 לבנים חסרות (פתוחות):")
        for brick in open_bricks:
            st.caption(f"• {brick.get('topic')}: {brick.get('brick')}")

    if st.button("התנתק"):
        st.session_state.student = None
        st.session_state.tutor = None
        st.session_state.thread = []
        st.session_state.quiz = None
        st.rerun()

# כשמבחן פעיל - מציגים אותו במקום הצ'אט.
if st.session_state.quiz is not None:
    render_quiz()
    st.stop()

if st.session_state.last_summary:
    st.info(f"סיכום השיחה הקודמת: {st.session_state.last_summary}")

for turn in st.session_state.thread:
    role = "user" if turn["speaker"] == "student" else "assistant"
    with st.chat_message(role):
        st.write(turn["text"])

user_input = st.chat_input("כתוב הודעה ליוני...  (למבחן: 'בחן אותי על ...')")
if user_input:
    if st.session_state.tutor is None:
        st.session_state.tutor = Tutor()

    st.session_state.thread.append({"speaker": "student", "text": user_input})
    result = None
    with st.spinner("יוני חושב..."):
        result = handle_student_message(router, st.session_state.tutor, user_input)

    if result.get("action") == "start_quiz":
        try:
            with st.spinner("יוני מכין מבחן..."):
                questions = Quiz().generate(user_input, num_questions=3)
            st.session_state.quiz = {"questions": questions, "idx": 0, "results": []}
        except AgentError as error:
            st.session_state.thread.append({"speaker": "system", "text": f"⚠️ {error}"})
    else:
        st.session_state.thread.append(result)
    st.rerun()

if st.button("סיים שיחה", disabled=st.session_state.tutor is None):
    try:
        with st.spinner("יוני חושב..."):
            summary = st.session_state.tutor.end_session(student_id=student_id)
        # רישום גם לתיקיית התלמיד (sessions/YYYY-MM-DD.json), כמו במבנה הדמו.
        students.log_session(student_id, summary, len(st.session_state.thread))
        st.session_state.last_summary = summary
        st.session_state.tutor = None
        st.session_state.thread = []
        st.rerun()
    except AgentError as e:
        st.error(f"לא הצלחתי לסכם את השיחה: {e}")
