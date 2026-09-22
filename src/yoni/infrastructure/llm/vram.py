"""אכיפת תקציב VRAM: לעולם לא שני מודלים כבדים טעונים יחד.

הכלל נאכף לפני *כל* קריאה למודל, מתוך OllamaLanguageModel - כלומר בקוד, לא בתקווה.
המחלקה מקבלת את ההגדרות בהזרקה, ולכן אפשר לבדוק אותה מול תצורת חומרה מדומה.
"""

import subprocess
from typing import List, Optional

# requests מיובא בעצלתיים בשתי המתודות שבאמת פונות לרשת. חישוב התקציב עצמו
# (ensure_capacity, is_heavy) הוא לוגיקה טהורה וניתן לבדיקה בלי שום תלות.


class VramBudget:
    """אכיפת התקציב, עם זיכרון קצר על מה שכבר טעון.

    ensure_capacity נקרא לפני *כל* הודעה של תלמיד, והוא פנה ל-Ollama בכל פעם
    כדי לשאול מה טעון - כ-2 שניות שנוספו לכל תשובה, לרוב כדי לגלות שדבר לא
    השתנה. התשובה נשמרת לזמן קצר: המצב משתנה רק כשאנחנו עצמנו טוענים או
    מפרקים מודל, ואת שני אלה אנחנו יודעים מיד.
    """

    #: כמה שניות לסמוך על הרשימה השמורה. קצר מספיק כדי להתאושש משינוי חיצוני.
    CACHE_SECONDS = 30.0

    def __init__(self, settings, clock=None):
        self._settings = settings
        self._loaded: Optional[List[str]] = None
        self._checked_at = 0.0

    def _now(self) -> float:
        import time
        return time.monotonic()

    def invalidate(self) -> None:
        """מאלץ בדיקה אמיתית בפעם הבאה."""
        self._loaded = None

    def _gb(self, model):
        profile = self._settings.profile(model)
        return profile.vram_gb if profile else None

    def is_heavy(self, model: str) -> bool:
        profile = self._settings.profile(model)
        return bool(profile and profile.is_heavy)

    def _fresh_models(self) -> List[str]:
        """הרשימה מהמטמון אם היא טרייה, אחרת שאילתה אמיתית.

        בכוונה *לא* פרמטר על loaded_models: זו מתודה שמדומה בבדיקות, וחתימה
        שמשתנה שם שוברת כל מימוש חלופי.
        """
        if (self._loaded is not None
                and self._now() - self._checked_at < self.CACHE_SECONDS):
            return list(self._loaded)
        models = self.loaded_models()
        self._loaded = list(models)
        self._checked_at = self._now()
        return list(models)

    def loaded_models(self) -> List[str]:
        import requests
        try:
            response = requests.get(self._settings.running_url, timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except (requests.exceptions.RequestException, ValueError, KeyError):
            return []

    def unload(self, model: str) -> None:
        """שקט אם נכשל - במקרה הגרוע Ollama יפנה זיכרון בעצמו."""
        import requests
        try:
            requests.post(
                self._settings.generate_url,
                json={"model": model, "prompt": "", "keep_alive": 0},
                timeout=30,
            )
        except requests.exceptions.RequestException:
            pass
        finally:
            if self._loaded is not None:
                self._loaded = [m for m in self._loaded if m != model]

    def ensure_capacity(self, model: str) -> List[str]:
        """מפנה מקום לפני טעינה. מחזיר את רשימת המודלים שפורקו."""
        target = self._gb(model)
        if target is None:  # מודל לא מנוהל (למשל בבדיקות) - לא מתערבים
            return []

        unloaded = []
        current = [m for m in self._fresh_models() if m != model]

        # המודל המבוקש כבר טעון ואין אף אחד אחר - אין מה לפנות, וזה המקרה
        # הרגיל בשיחה רצופה. יציאה כאן חוסכת את כל השאר.
        if not current:
            if self._loaded is not None and model not in self._loaded:
                self._loaded.append(model)
            return []

        if self.is_heavy(model):
            for other in current:
                if self.is_heavy(other):
                    self.unload(other)
                    unloaded.append(other)
            current = [m for m in current if m not in unloaded]

        def total(models):
            return sum(self._gb(m) or 0 for m in models)

        remaining = sorted(current, key=lambda m: self._gb(m) or 0, reverse=True)
        while remaining and total(remaining) + target > self._settings.vram_budget_gb:
            unloaded.append(remaining.pop(0))
            self.unload(unloaded[-1])
        return unloaded

    def detect_vram_gb(self) -> Optional[float]:
        """VRAM אמיתי מ-nvidia-smi, או None (למשל בקונטיינר או על מק)."""
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10,
            )
            if out.returncode == 0 and out.stdout.strip():
                return float(out.stdout.strip().splitlines()[0]) / 1024.0
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
        return None

    def warnings(self) -> List[str]:
        """אזהרות פתיחה על מודלים שלא נכנסים בזיכרון."""
        messages = []
        vram = self.detect_vram_gb() or self._settings.vram_budget_gb
        profiles = self._settings.model_vram

        for model, estimate in profiles.items():
            if estimate > vram:
                messages.append(
                    f"⚠️ המודל {model} (~{estimate}GB) חורג מה-VRAM הזמין (~{vram:.1f}GB) - יגלוש ל-RAM ויאט משמעותית."
                )
        heavies = [m for m in profiles if self.is_heavy(m)]
        for i, first in enumerate(heavies):
            for second in heavies[i + 1:]:
                pair = profiles[first] + profiles[second]
                if pair > vram:
                    messages.append(
                        f"⚠️ {first} + {second} יחד (~{pair}GB) לא נכנסים ב-VRAM (~{vram:.1f}GB) - ייטענו רק אחד בכל רגע (נאכף אוטומטית)."
                    )
        return messages
