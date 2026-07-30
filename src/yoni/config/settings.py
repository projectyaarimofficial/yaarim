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
    ollama_host: str = "http://localhost:11434"

    tutor_model: str = "gemma3:4b"
    quiz_model: str = "gemma3:4b"
    planner_model: str = "gemma3:4b"
    coder_model: str = "qwen2.5-coder:7b"
    reasoning_model: str = "qwen3:8b"
    embed_model: str = "nomic-embed-text"

    vram_budget_gb: float = 8.0
    max_context_chars: int = 6000
    request_timeout_s: int = 600

    model_vram: dict = field(default_factory=lambda: {
        "gemma3:4b": 3.5,
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


def _default_root():
    # src/yoni/config/settings.py → שורש הפרויקט
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(os.path.dirname(here)))


def from_env(project_root=None):
    """בונה Settings מסביבת ההרצה. ברירות המחדל זהות להתנהגות שלפני הריפקטור."""
    return Settings(
        project_root=project_root or _env("YAARIM_ROOT", _default_root()),
        ollama_host=_env("OLLAMA_HOST", "http://localhost:11434"),
        tutor_model=_env("YAARIM_TUTOR_MODEL", "gemma3:4b"),
        quiz_model=_env("YAARIM_QUIZ_MODEL", "gemma3:4b"),
        planner_model=_env("YAARIM_PLANNER_MODEL", "gemma3:4b"),
        coder_model=_env("YAARIM_CODER_MODEL", "qwen2.5-coder:7b"),
        reasoning_model=_env("YAARIM_REASONING_MODEL", "qwen3:8b"),
        embed_model=_env("YAARIM_EMBED_MODEL", "nomic-embed-text"),
        vram_budget_gb=float(_env("YAARIM_VRAM_BUDGET_GB", "8.0")),
    )
