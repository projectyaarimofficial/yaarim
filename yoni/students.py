"""קריאת פרופילי תלמידים מתוך תיקיית students/.

מבנה: students/<demo|real>/<student_id>/profile.json (+ status.json, sessions/, quiz_results/).
המודול הזה קורא בלבד (זיהוי התלמיד וטעינת הפרופיל) - כתיבה/עדכון סטטוס ולבנים
חסרות שייכים לשלב הבא. אין כאן תלות ב-streamlit או במודל, כדי שיהיה קל לבדיקה.
"""

import json
import os
from datetime import date

from . import config

STUDENTS_DIR = os.path.join(config.BASE_DIR, "students")
_KINDS = ("demo", "real")


def student_dir(student_id):
    """מחזיר את נתיב תיקיית התלמיד (מחפש ב-demo/ ואז ב-real/), או None אם לא קיים."""
    student_id = (student_id or "").strip()
    if not student_id:
        return None
    for kind in _KINDS:
        path = os.path.join(STUDENTS_DIR, kind, student_id)
        if os.path.isdir(path):
            return path
    return None


def load_profile(student_id):
    """מחזיר את profile.json של התלמיד כ-dict, או None אם אין פרופיל כזה."""
    directory = student_dir(student_id)
    if not directory:
        return None
    path = os.path.join(directory, "profile.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def load_status(student_id):
    """מחזיר את status.json (לבנים חסרות וכו') כ-dict, או None אם אין."""
    directory = student_dir(student_id)
    if not directory:
        return None
    path = os.path.join(directory, "status.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def identify(student_id, name):
    """מזהה תלמיד לפי מזהה + שם.

    אם קיים פרופיל למזהה - מחזיר אותו (עם השם הקנוני מהפרופיל).
    אם לא - יוצר פרופיל חדש וקבוע תחת students/real/ ומחזיר אותו,
    כך שהתלמיד מזוהה מהכניסה הבאה ואילך ("המערכת זוכרת אותך").
    """
    student_id = (student_id or "").strip()
    name = (name or "").strip()
    if not student_id or not name:
        raise ValueError("נדרשים גם מזהה וגם שם.")

    profile = load_profile(student_id)
    if profile:
        # שומרים על השם הקנוני מהפרופיל, אבל מציינים שהתלמיד זוהה.
        profile.setdefault("name", name)
        return profile

    profile = create_profile(student_id, name)
    profile["_is_new"] = True  # דגל ארעי (לא נשמר לדיסק) - כניסה ראשונה
    return profile


def create_profile(student_id, name, kind="real"):
    """יוצר פרופיל חדש על הדיסק, במבנה המלא כמו תלמיד הדמו:

    profile.json + status.json ריק + תיקיות sessions/ ו-quiz_results/.
    """
    directory = os.path.join(STUDENTS_DIR, kind, student_id)
    os.makedirs(directory, exist_ok=True)
    os.makedirs(os.path.join(directory, "sessions"), exist_ok=True)
    os.makedirs(os.path.join(directory, "quiz_results"), exist_ok=True)

    profile = {
        "student_id": student_id,
        "is_demo": kind == "demo",
        "name": name,
        "grade": None,
        "language": "he",
        "created_at": date.today().isoformat(),
        "notes": "",
    }
    with open(os.path.join(directory, "profile.json"), "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    status_path = os.path.join(directory, "status.json")
    if not os.path.exists(status_path):
        status = {
            "student_id": student_id,
            "updated_at": date.today().isoformat(),
            "missing_bricks": [],
        }
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)

    return profile


def _append_daily(student_id, subdir, list_key, record):
    """מוסיף רשומה לקובץ היומי (YYYY-MM-DD.json) של התלמיד, בפורמט של תלמיד הדמו."""
    directory = student_dir(student_id)
    if not directory:
        return None
    day = date.today().isoformat()
    folder = os.path.join(directory, subdir)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{day}.json")

    data = {"date": day, "student_id": student_id, list_key: []}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    data.setdefault(list_key, []).append(record)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def log_session(student_id, summary, message_count):
    """רושם סיכום שיחה לקובץ sessions/YYYY-MM-DD.json של התלמיד."""
    return _append_daily(
        student_id, "sessions", "sessions",
        {"summary": summary, "message_count": message_count},
    )


def last_session(student_id):
    """מחזיר את סיכום הסשן האחרון של התלמיד ({date, summary, ...}), או None אם אין."""
    directory = student_dir(student_id)
    if not directory:
        return None
    folder = os.path.join(directory, "sessions")
    if not os.path.isdir(folder):
        return None
    for filename in sorted(os.listdir(folder), reverse=True):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        sessions = data.get("sessions") or []
        if sessions:
            entry = dict(sessions[-1])
            entry["date"] = data.get("date", filename[:-5])
            return entry
    return None


def build_greeting(profile, status=None, last=None):
    """בונה ברכת פתיחה אישית לכניסת תלמיד - קוד בלבד, בלי קריאה למודל.

    תלמיד חדש מקבל 'נעים להכיר'; תלמיד חוזר מקבל שלום + פרט קטן מהזיכרון
    (הסשן האחרון, או נושא פתוח מ-status.json) - כדי שירגיש שהמערכת זוכרת אותו.
    """
    name = profile.get("name") or profile.get("student_id", "")

    if profile.get("_is_new"):
        return (
            f"שלום {name}, נעים להכיר! 👋 אני יוני. "
            "מהיום אני אזכור את ההתקדמות שלך - במה תרצה להתחיל?"
        )

    if last and last.get("summary"):
        return (
            f"שלום {name}, טוב לראות אותך שוב! 👋 "
            f"בפעם הקודמת ({last.get('date', '')}): {last['summary']} "
            "רוצה להמשיך מאיפה שעצרנו?"
        )

    open_bricks = [
        b for b in (status or {}).get("missing_bricks", []) if b.get("status") == "open"
    ]
    if open_bricks:
        topic = open_bricks[0].get("topic", "")
        return (
            f"שלום {name}, טוב לראות אותך שוב! 👋 "
            f"יש לנו עדיין נושא פתוח לחיזוק: {topic}. רוצה שנמשיך בו?"
        )

    return f"שלום {name}, טוב לראות אותך שוב! 👋 במה נעסוק היום?"


def log_quiz_result(student_id, question, student_answer, correct):
    """רושם תוצאת שאלה לקובץ quiz_results/YYYY-MM-DD.json של התלמיד."""
    record = {
        "topic": question.get("topic"),
        "question": question.get("question"),
        "type": question.get("type"),
        "student_answer": student_answer,
    }
    # כמו בדמו: לשאלות עם תשובה יחידה נשמרת גם התשובה הנכונה.
    if question.get("type") in ("multiple_choice", "exact"):
        record["correct_answer"] = question.get("correct_answer")
    record["correct"] = bool(correct)
    return _append_daily(student_id, "quiz_results", "results", record)


def list_students():
    """מחזיר רשימת (student_id, name, kind) לכל התלמידים שקיימים על הדיסק."""
    result = []
    for kind in _KINDS:
        base = os.path.join(STUDENTS_DIR, kind)
        if not os.path.isdir(base):
            continue
        for student_id in sorted(os.listdir(base)):
            if not os.path.isdir(os.path.join(base, student_id)):
                continue
            profile = load_profile(student_id) or {}
            result.append((student_id, profile.get("name", ""), kind))
    return result
