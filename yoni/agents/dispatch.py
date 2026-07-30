from .base import AgentError
from .reasoning import Reasoning
from .router import REASON_PREFIX

BUILD_NOTICE = "🛠️ פקודות /build מטופלות ב-CLI (projectyaarimv0.py), לא כאן."


def handle_student_message(router, tutor, text):
    """מנתב הודעה אחת של תלמיד ומחזיר dict להצגה בממשק.

    לוגיקה טהורה, בלי תלות בממשק (streamlit) - כדי שתהיה ניתנת לבדיקה בקלות.
    לכוונת quiz מוחזר אות "action": "start_quiz" - הממשק הוא זה שמריץ את המבחן
    האינטראקטיבי (state + טפסים), כי צעד בקשה-תשובה בודד לא יכול לבטא זאת.
    """
    intent = router.route(text)

    if intent == "build":
        return {"speaker": "system", "text": BUILD_NOTICE}
    if intent == "quiz":
        return {"speaker": "system", "action": "start_quiz", "text": text}
    if intent == "reason":
        problem = text.strip()[len(REASON_PREFIX):].strip() or text
        try:
            reply = Reasoning().solve(problem)
            return {"speaker": "yoni", "text": reply}
        except AgentError as e:
            return {"speaker": "system", "text": f"⚠️ {e}"}

    try:
        reply = tutor.ask(text)
        return {"speaker": "yoni", "text": reply}
    except AgentError as e:
        return {"speaker": "system", "text": f"⚠️ {e}"}
