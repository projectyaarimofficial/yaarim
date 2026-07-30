# יערים — סביבת ריצה לקוד הפייתון בלבד.
#
# Ollama *לא* נמצא כאן: הוא רץ על המארח, עם הגישה ל-GPU ול-VRAM. הקונטיינר פונה
# אליו דרך OLLAMA_HOST. זו הפרדה מכוונת — המודלים אצל מי שיש לו כרטיס מסך.
#
# הקוד לא מועתק לתמונה אלא מחובר כ-volume, כי /build כותב לתוך הפרויקט.
# מכאן גם התועלת האמיתית של הקונטיינר כאן: מה שלא חובר — לא קיים. גם אם תוכנית
# הזויה תכוון ל-~/.ssh או ל-/etc, הנתיב הזה פשוט אינו קיים בתוך המרחב הזה.
# path_guard חוסם בקוד; הקונטיינר מוודא שאין מה לחסום מלכתחילה.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src
# PYTHONPATH: החבילה יושבת תחת src/ (מבנה src-layout), ו-streamlit מוסיף ל-sys.path
# רק את תיקיית הסקריפט. בלי זה "from yoni import ..." נכשל.

WORKDIR /app

# שכבת התלויות נפרדת מהקוד — נבנית מחדש רק כשה-requirements משתנה.
COPY requirements.txt requirements-dev.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-dev.txt \
 && rm /tmp/requirements.txt /tmp/requirements-dev.txt
# requirements-dev כולל את requirements (שורת -r) ומוסיף את mypy. התמונה הזו
# היא סביבת פיתוח: הקוד מחובר כ-volume, והיא זו שמריצה את הבדיקה.

# משתמש לא-root. ה-UID ניתן לשינוי בזמן build כדי להתאים לבעלות הקבצים על המארח
# (ב-Linux, כשהפרויקט מחובר כ-volume): docker compose build --build-arg UID=$(id -u)
ARG UID=1000
ARG GID=1000
RUN groupadd -g "$GID" yaarim 2>/dev/null || true \
 && useradd -m -u "$UID" -g "$GID" -s /bin/bash yaarim 2>/dev/null || true
USER $UID:$GID

EXPOSE 8501

# ברירת מחדל: הממשק. ל-CLI של /build ראה docker-compose.yml (שירות cli).
CMD ["streamlit", "run", "src/yoni/interfaces/web/app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
