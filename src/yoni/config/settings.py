"""הגדרות כאובייקט, לא כקבועים גלובליים.

ההבדל אינו סגנוני: כשההגדרות הן מודול גלובלי, כל מחלקה קוראת אותן ישירות ואי
אפשר להזריק הגדרות אחרות בבדיקה בלי לתקן (patch) את המודול. כאן Settings הוא
ערך שעובר בהזרקה, ולכן אפשר להריץ שתי תצורות שונות באותו תהליך.

מקור האמת לערכים הוא סביבת ההרצה (env), עם ברירות מחדל זהות להתנהגות הקודמת.
"""

import os
from dataclasses import dataclass, field, replace
from typing import Optional


@dataclass(frozen=True)
class ModelProfile:
    """איזה מודל משרת איזה תפקיד, ומה מחיר הזיכרון שלו."""

    name: str
    vram_gb: float

    @property
    def is_heavy(self) -> bool:
        return self.vram_gb >= HEAVY_THRESHOLD_GB


HEAVY_THRESHOLD_GB = 5.0


def _env(key, default):
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    """כל מה שניתן לכוון, במקום אחד."""

    project_root: str
    # 127.0.0.1 ולא localhost, בכוונה: על Windows השם מתרגם קודם ל-::1,
    # Ollama אינו מאזין ב-IPv6, וכל קריאה משלמת ~2 שניות timeout לפני
    # הנפילה ל-IPv4. נמדד: 2.05s מול 0.01s לאותה קריאה.
    ollama_host: str = "http://127.0.0.1:11434"

    tutor_model: str = "gemma3:12b"
    quiz_model: str = "gemma3:12b"
    planner_model: str = "gemma3:4b"
    coder_model: str = "qwen2.5-coder:7b"
    reasoning_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"

    # 15GB מתוך 16 של הכרטיס - שארית לצורכי המסך ולמנועי הדיבור.
    vram_budget_gb: float = 15.0
    max_context_chars: int = 6000
    request_timeout_s: int = 600

    # ---- דיבור ---------------------------------------------------------
    # הדיבור הוא מצב הבסיס של יוני; הכתב זמין דרך מתג בממשק.
    speech_enabled: bool = True
    speech_voice: str = "michael.onnx"
    speech_config: str = "model.config.json"
    speech_length_scale: float = 1.3   # גדול מ-1 = איטי יותר
    speech_noise_scale: float = 0.45   # נמוך = הגייה יציבה וברורה יותר
    speech_noise_w_scale: float = 0.6

    # מיקרופון: whisper שכוונן לעברית על ידי ivrit.ai.
    microphone_enabled: bool = True
    stt_model: str = "ivrit-ai/whisper-large-v3-turbo-ct2"

    model_vram: dict = field(default_factory=lambda: {
        "gemma3:4b": 3.5,
        "gemma3:12b": 9.0,
        "qwen2.5-coder:7b": 5.5,
        "qwen3:8b": 6.0,
        "nomic-embed-text": 0.4,
    })

    # ---- נתיבים נגזרים -------------------------------------------------
    @property
    def data_dir(self) -> str:
        # נתונים אינם קוד: הם יושבים בשורש הפרויקט, לא בתוך החבילה.
        return os.path.join(self.project_root, "data")

    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "yoni_memory.db")

    @property
    def backups_dir(self) -> str:
        return os.path.join(self.data_dir, "backups")

    @property
    def students_dir(self) -> str:
        return os.path.join(self.project_root, "students")

    @property
    def safety_config_path(self) -> str:
        return os.path.join(self.data_dir, "safety.json")

    @property
    def models_dir(self) -> str:
        """מודלים אינם קוד ואינם נתוני תלמיד - תיקייה משלהם."""
        return os.path.join(self.project_root, "models", "tts")

    @property
    def speech_voice_path(self) -> str:
        return os.path.join(self.models_dir, self.speech_voice)

    @property
    def speech_config_path(self) -> str:
        return os.path.join(self.models_dir, self.speech_config)

    @property
    def stt_cache_dir(self) -> str:
        return os.path.join(self.project_root, "models", "stt")

    @property
    def generate_url(self) -> str:
        return f"{self.ollama_host}/api/generate"

    @property
    def embed_url(self) -> str:
        return f"{self.ollama_host}/api/embeddings"

    @property
    def tags_url(self) -> str:
        return f"{self.ollama_host}/api/tags"

    @property
    def running_url(self) -> str:
        return f"{self.ollama_host}/api/ps"

    def profile(self, model_name: str) -> Optional[ModelProfile]:
        """ModelProfile למודל, או None אם אינו מנוהל (למשל מודל מדומה בבדיקה)."""
        vram = self.model_vram.get(model_name)
        return ModelProfile(model_name, vram) if vram is not None else None

    def with_overrides(self, **kwargs) -> "Settings":
        """עותק עם שינויים - שימושי בבדיקות, בלי לגעת במקור."""
        return replace(self, **kwargs)


def _normalize_host(host: str) -> str:
    """localhost -> 127.0.0.1, גם כשהוא מגיע מהסביבה.

    בלי זה, run.ps1 או docker-compose שמגדירים OLLAMA_HOST=localhost מחזירים
    את קנס ה-IPv6 מהדלת האחורית. שם מארח אחר (מכונה אחרת) נשאר כמו שהוא.
    """
    return host.replace("//localhost:", "//127.0.0.1:")


def _default_root():
    # src/yoni/config/settings.py → שורש הפרויקט
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def from_env(project_root=None):
    """בונה Settings מסביבת ההרצה. ברירות המחדל זהות להתנהגות שלפני הריפקטור."""
    return Settings(
        project_root=project_root or _env("YAARIM_ROOT", _default_root()),
        ollama_host=_normalize_host(_env("OLLAMA_HOST", "http://127.0.0.1:11434")),
        tutor_model=_env("YAARIM_TUTOR_MODEL", "gemma3:12b"),
        quiz_model=_env("YAARIM_QUIZ_MODEL", "gemma3:12b"),
        planner_model=_env("YAARIM_PLANNER_MODEL", "gemma3:4b"),
        coder_model=_env("YAARIM_CODER_MODEL", "qwen2.5-coder:7b"),
        reasoning_model=_env("YAARIM_REASONING_MODEL", "qwen3:8b"),
        embed_model=_env("YAARIM_EMBED_MODEL", "nomic-embed-text"),
        vram_budget_gb=float(_env("YAARIM_VRAM_BUDGET_GB", "15.0")),
        speech_enabled=_env("YAARIM_SPEECH", "1") not in ("0", "false", "False"),
        speech_voice=_env("YAARIM_SPEECH_VOICE", "michael.onnx"),
        speech_config=_env("YAARIM_SPEECH_CONFIG", "model.config.json"),
        speech_length_scale=float(_env("YAARIM_SPEECH_SPEED", "1.3")),
        microphone_enabled=_env("YAARIM_MIC", "1") not in ("0", "false", "False"),
        stt_model=_env("YAARIM_STT_MODEL", "ivrit-ai/whisper-large-v3-turbo-ct2"),
    )
