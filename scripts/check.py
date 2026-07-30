#!/usr/bin/env python3
"""הבדיקה הדטרמיניסטית של הפרויקט - ירוק או אדום, בלי פרשנות.

הרצה:
    python scripts/check.py            (Windows · macOS · Linux)
    ./scripts/check.sh                 (עטיפה ל-Unix)
    .\\scripts\\check.ps1               (עטיפה ל-PowerShell)

הלוגיקה יושבת כאן, בפייתון, ולא ב-bash - כי המפתח הבא עשוי לעבוד ב-Windows בלי
Docker ובלי bash. גרסת bash שנייה הייתה נסחפת מהראשונה תוך שבועות; עטיפה דקה לא.

BLOCKER = הפרויקט לא במצב תקין. WARN = חוב מוכר שלא חוסם.
"""

import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

# צבעים רק כשהפלט הוא טרמינל אמיתי (ב-Windows הישן הם היו מופיעים כזבל)
_TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
def _c(code, text):
    return f"\033[{code}m{text}\033[0m" if _TTY else text

blockers, warnings = [], []


def blocker(msg):
    blockers.append(msg)
    print(f"  {_c('0;31m', 'BLOCKER')}  {msg}")


def warn(msg):
    warnings.append(msg)
    print(f"  {_c('0;33m', 'WARN')}     {msg}")


def ok(msg):
    print(f"  {_c('0;32m', 'ok')}       {msg}")


def section(title):
    print(f"\n{_c('2m', '── ' + title)}")


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, timeout=15)
        return out.stdout.splitlines() if out.returncode == 0 else []
    except (OSError, subprocess.SubprocessError):
        return []


print("\n🧱 YAARIM — בדיקת תקינות")

# ---------------------------------------------------------------------------
section("תלויות")
# ---------------------------------------------------------------------------
requirements = read("requirements.txt")
if not requirements:
    blocker("אין requirements.txt")
else:
    unpinned = [
        line.strip() for line in requirements.splitlines()
        if line.strip() and not line.startswith("#") and "==" not in line
    ]
    if unpinned:
        blocker(f"תלויות לא מקובעות (חייב ==): {' '.join(unpinned)}")
    else:
        ok("כל התלויות מקובעות ב-==")

# ---------------------------------------------------------------------------
section("שומרים — קיימים")
# ---------------------------------------------------------------------------
GUARDS = [
    ("src/yoni/infrastructure/security/paths.py", "גדר הכתיבה"),
    ("src/yoni/infrastructure/safety/keywords.py", "רשת הביטחון"),
    ("src/yoni/infrastructure/security/passwords.py", "אימות סיסמאות"),
    ("data/safety.json", "הגדרות בטיחות"),
]
for path, label in GUARDS:
    ok(f"{label} ({path})") if os.path.exists(path) else blocker(f"חסר: {path}")

# ---------------------------------------------------------------------------
section("שומרים — מחוברים")
# ---------------------------------------------------------------------------
if "write_policy" in read("src/yoni/application/authoring.py") \
        and "ProjectWritePolicy" in read("src/yoni/container.py"):
    ok("גדר הכתיבה מוזרקת לשירות הבנייה")
else:
    blocker("WritePolicy לא מחוברת — הכתיבה לא מוגבלת לפרויקט")

if "self._safety.inspect" in read("src/yoni/application/conversation.py"):
    ok("בדיקת מצוקה רצה לפני הניתוב ולפני המודל")
else:
    blocker("SafetyPolicy לא נבדקת בשיחה — כלל 5 בחוקה הוא רק טקסט")

if "passwords.verify" in read("src/yoni/interfaces/web/auth_screen.py"):
    ok("הכניסה דורשת סיסמה מאומתת")
else:
    blocker("האימות לא מחובר — היסטוריית תלמיד נפתחת עם מזהה בלבד")

# ---------------------------------------------------------------------------
section("ארכיטקטורה")
# ---------------------------------------------------------------------------
# הליבה לא מכירה תשתית. הפרה כאן היא מה שהופך ארכיטקטורה למצגת.
LEAK_RE = re.compile(r"^\s*(from \.{1,2}infrastructure|import requests|import streamlit|import sqlite3)",
                     re.MULTILINE)
leaks = []
for layer in ("src/yoni/domain", "src/yoni/application", "src/yoni/agents"):
    for dirpath, _dirs, files in os.walk(layer):
        for name in files:
            if name.endswith(".py"):
                full = os.path.join(dirpath, name)
                if LEAK_RE.search(read(full)):
                    leaks.append(full)
if leaks:
    blocker("שכבת הליבה מייבאת תשתית:")
    for path in leaks[:5]:
        print(f"           {path}")
else:
    ok("domain · application · agents אינם מייבאים תשתית")

# הבדיקה החיה: הליבה נטענת גם כשאין requests.
probe = (
    "import sys; sys.modules['requests'] = None;"
    "import yoni.domain.models, yoni.domain.ports;"
    "import yoni.application.conversation, yoni.application.assessment, yoni.application.authoring;"
    "import yoni.agents.base, yoni.agents.quiz, yoni.agents.tutor, yoni.agents.factory"
)
env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "src"))
result = subprocess.run([sys.executable, "-c", probe], capture_output=True, env=env)
if result.returncode == 0:
    ok("הליבה נטענת גם בלי requests — ההפרדה אמיתית")
else:
    blocker("הליבה לא נטענת בלי requests — יש תלות נסתרת בתשתית")

ports = len(re.findall(r"^class .*\(ABC\)", read("src/yoni/domain/ports.py"), re.MULTILINE))
ok(f"פורטים מוגדרים: {ports}")

# שורש נקי: נקודת הכניסה היחידה ל-CLI היא python -m yoni.
root_py = [f for f in os.listdir(".") if f.endswith(".py")]
if root_py:
    blocker(f"קבצי פייתון בשורש הפרויקט: {' '.join(root_py)}")
else:
    ok("אין קבצי פייתון בשורש — הכניסה היא python -m yoni")

# streamlit מריץ את קובץ הכניסה כסקריפט, לא כמודול - ייבוא יחסי בו נשבר.
if re.search(r"^from \.{1,2}[a-z]", read("src/yoni/interfaces/web/app.py"), re.MULTILINE):
    blocker("קובץ הכניסה של streamlit מכיל ייבוא יחסי — יישבר בהרצה כסקריפט")
else:
    ok("קובץ הכניסה של streamlit משתמש בייבוא מוחלט")

# ---------------------------------------------------------------------------
section("טיפוסים")
# ---------------------------------------------------------------------------
# בלי בודק, ההערות הן תיעוד - לא הבטחה. הן יכולות לשקר בלי שאיש יבחין.
# mypy הוא מה שהופך אותן למנגנון. הוא כלי פיתוח: אם אינו מותקן, זו אזהרה
# ולא חסימה, כדי שהרצה של האפליקציה לא תדרוש אותו.
result = subprocess.run([sys.executable, "-m", "mypy", "--version"],
                        capture_output=True, text=True)
if result.returncode != 0:
    warn("mypy לא מותקן - הטיפוסים אינם נבדקים (pip install -r requirements-dev.txt)")
else:
    result = subprocess.run([sys.executable, "-m", "mypy"],
                            capture_output=True, text=True, env=env)
    summary = (result.stdout or result.stderr).strip().splitlines()
    verdict = summary[-1] if summary else "(sans sortie)"
    if result.returncode == 0:
        ok(f"טיפוסים תקינים — {verdict}")
    else:
        blocker(f"שגיאות טיפוסים — {verdict}")
        for line in [l for l in summary if ": error:" in l][:5]:
            print(f"           {line.strip()}")

# ---------------------------------------------------------------------------
section("בדיקות")
# ---------------------------------------------------------------------------
stray = [f for f in os.listdir(".") if f.startswith("test_") and f.endswith(".py")]
if stray:
    blocker(f"קבצי בדיקה מחוץ ל-tests/: {' '.join(stray)}")
else:
    ok("כל הבדיקות תחת tests/")

env_tests = dict(os.environ,
                 PYTHONPATH=os.pathsep.join([os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]))
result = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py"],
    capture_output=True, text=True, env=env_tests,
)
summary = " ".join(
    line for line in result.stderr.splitlines() if line.startswith(("OK", "FAILED", "Ran "))
)
if result.returncode == 0:
    ok(f"כל הבדיקות עוברות — {summary}")
else:
    blocker(f"בדיקות נכשלות — {summary}")
    for line in [l for l in result.stderr.splitlines() if l.startswith(("ERROR:", "FAIL:"))][:5]:
        print(f"           {line}")

# ---------------------------------------------------------------------------
section("חוב ידוע")
# ---------------------------------------------------------------------------
stubs = []
for dirpath, _dirs, files in os.walk("src"):
    for name in files:
        if name.endswith(".py") and name != "ports.py":
            content = read(os.path.join(dirpath, name))
            if "NotImplementedError" in content and "@abstractmethod" not in content:
                stubs.append(os.path.join(dirpath, name))
if stubs:
    warn(f"שלד לא ממומש: {' '.join(stubs)}")

todos = 0
for dirpath, _dirs, files in os.walk("src"):
    for name in files:
        if name.endswith(".py"):
            todos += len(re.findall(r"TODO|FIXME|XXX", read(os.path.join(dirpath, name))))
if todos:
    warn(f"סימוני TODO/FIXME: {todos}")

try:
    hotlines = json.loads(read("data/safety.json")).get("hotlines", [])
    pending = sum(1 for h in hotlines if not h.get("verified"))
    if pending:
        warn(f"מספרי חירום שטרם אומתו מול המקור הרשמי: {pending}")
except (json.JSONDecodeError, AttributeError):
    blocker("data/safety.json אינו קריא")

# ---------------------------------------------------------------------------
section("פרטיות")
# ---------------------------------------------------------------------------
files = tracked_files()
if not files:
    warn("git לא זמין - דילוג על בדיקות הפרטיות")
else:
    leaked = [f for f in files if f.startswith("students/real") and not f.endswith("README.md")]
    if leaked:
        blocker(f"נתוני תלמידים אמיתיים ב-git: {' '.join(leaked)}")
    else:
        ok("אין נתוני תלמידים אמיתיים ב-git")

    databases = [f for f in files if re.search(r"\.(db|sqlite3?)$", f)]
    if databases:
        blocker(f"קובץ מסד נתונים מנוהל ב-git: {' '.join(databases)}")
    else:
        ok("אין מסדי נתונים ב-git")

# ---------------------------------------------------------------------------
print()
if blockers:
    print(f"{_c('0;31m', f'✖ {len(blockers)} חסימות')} · {len(warnings)} אזהרות\n")
    sys.exit(1)
print(f"{_c('0;32m', '✔ תקין')} · {len(warnings)} אזהרות\n")
sys.exit(0)
