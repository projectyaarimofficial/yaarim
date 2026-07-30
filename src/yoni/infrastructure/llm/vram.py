"""אכיפת תקציב VRAM: לעולם לא שני מודלים כבדים טעונים יחד.

הכלל נאכף לפני *כל* קריאה למודל, מתוך OllamaLanguageModel - כלומר בקוד, לא בתקווה.
המחלקה מקבלת את ההגדרות בהזרקה, ולכן אפשר לבדוק אותה מול תצורת חומרה מדומה.
"""

import subprocess
from typing import List, Optional

# requests מיובא בעצלתיים בשתי המתודות שבאמת פונות לרשת. חישוב התקציב עצמו
# (ensure_capacity, is_heavy) הוא לוגיקה טהורה וניתן לבדיקה בלי שום תלות.


class VramBudget:
    def __init__(self, settings):
        self._settings = settings

    def _gb(self, model):
        profile = self._settings.profile(model)
        return profile.vram_gb if profile else None

    def is_heavy(self, model: str) -> bool:
        profile = self._settings.profile(model)
        return bool(profile and profile.is_heavy)

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

    def ensure_capacity(self, model: str) -> List[str]:
        """מפנה מקום לפני טעינה. מחזיר את רשימת המודלים שפורקו."""
        target = self._gb(model)
        if target is None:  # מודל לא מנוהל (למשל בבדיקות) - לא מתערבים
            return []

        unloaded = []
        current = [m for m in self.loaded_models() if m != model]

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
