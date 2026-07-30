import os

OLLAMA_HOST = "http://localhost:11434"
OLLAMA_URL = f"{OLLAMA_HOST}/api/generate"
OLLAMA_EMBED_URL = f"{OLLAMA_HOST}/api/embeddings"

# מודל נפרד לכל שלב/סוכן - כדי שאפשר יהיה להחליף מודל בלי לגעת בלוגיקה.
# החומרה: RTX 5060 (8GB VRAM), 32GB RAM, i5-14400F.
PLANNER_MODEL = "gemma3:4b"   # שלב התוכנית/הסיכום (dev tooling) - טקסט בלבד
CODER_MODEL = "qwen2.5-coder:7b"  # שלב כתיבת הקוד בפועל (dev tooling)
TUTOR_MODEL = "gemma3:4b"  # סוכן ה-Tutor (מול תלמיד) - העברית הטובה ביותר, משאיר מקום ב-VRAM
QUIZ_MODEL = "gemma3:4b"  # סוכן ה-Quiz (יצירת שאלות + בדיקת שאלות פתוחות)
REASONING_MODEL = "qwen3:8b"  # סוכן חשיבה/הסקה - נכנס ל-8GB ב-Q4
EMBED_MODEL = "nomic-embed-text"  # embeddings ל-RAG עתידי (קטן, ~0.3GB)

# תקציב VRAM (GB). אסור ששני מודלים "כבדים" (7-8B) יהיו טעונים יחד -
# 8GB לא מכיל את שניהם. model_manager אוכף זאת בכל קריאה למודל.
VRAM_BUDGET_GB = 8.0

# הערכת VRAM לכל מודל (GB, Q4 + הקשר). "כבד" = מעל HEAVY_THRESHOLD_GB.
MODEL_VRAM_GB = {
    "gemma3:4b": 3.5,
    "qwen2.5-coder:7b": 5.5,
    "qwen3:8b": 6.0,
    "nomic-embed-text": 0.4,
}
HEAVY_THRESHOLD_GB = 5.0

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(PACKAGE_DIR)

DATA_DIR = os.path.join(PACKAGE_DIR, "data")
BACKUPS_DIR = os.path.join(DATA_DIR, "backups")
DB_PATH = os.path.join(DATA_DIR, "yoni_memory.db")

# מעל הסף הזה (בתווים) נשלח למודל רק את הפונקציות/מחלקות הרלוונטיות
# מתוך הקובץ הקיים, ולא את כולו - כדי לחסוך הקשר על מודל 7B בלי GPU.
MAX_CONTEXT_CHARS = 6000
