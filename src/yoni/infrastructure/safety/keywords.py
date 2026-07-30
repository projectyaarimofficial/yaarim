"""מדיניות בטיחות מבוססת מילות מפתח - מימוש SafetyPolicy.

הטיה מכוונת לכיוון זיהוי-יתר: עדיף להפנות תלמיד למבוגר בלי צורך, מאשר לפספס
פעם אחת. זיהוי-יתר עולה שיחה מביכה; פספוס עולה משהו אחר.

מה זה כן: דלת דטרמיניסטית שמבטיחה שמישהו יוזעק.
מה זה לא: אבחון. הזיהוי מבוסס מילות מפתח והוא חלקי מטבעו - ילד שממציא ניסוח
משלו לא ייתפס. המנגנון מקטין את הסיכון, הוא לא מבטל אותו.

היותו פורט הוא מה שמאפשר להחליף אותו (למשל במסווג מקומי) בלי לגעת בשיחה.
"""

import json
from typing import List, Optional

from ...domain.models import SafetyFinding

from ...domain.ports import SafetyPolicy


def _normalize(text):
    text = " ".join(str(text or "").split())
    for ch in ",.!?;:\"'()[]{}":
        text = text.replace(ch, " ")
    return " ".join(text.split())


class KeywordSafetyPolicy(SafetyPolicy):
    def __init__(self, config_path):
        self._config_path = config_path
        self._config = None

    def _load(self):
        if self._config is None:
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._config = {"hotlines": [], "categories": {}}
        return self._config

    def reload(self) -> None:
        """מאפשר עריכה של קובץ ההגדרות בלי הפעלה מחדש."""
        self._config = None

    @property
    def hotlines(self) -> List[dict]:
        return self._load().get("hotlines", [])

    def inspect(self, text: Optional[str]) -> Optional[SafetyFinding]:
        normalized = _normalize(text)
        if not normalized:
            return None
        for category, spec in self._load().get("categories", {}).items():
            matched = tuple(
                kw for kw in spec.get("keywords", []) if _normalize(kw) in normalized
            )
            if matched:
                return SafetyFinding(
                    category=category,
                    label=spec.get("label", category),
                    matched=matched,
                )
        return None

    def escalation_message(self, finding: Optional[SafetyFinding] = None) -> str:
        """מפנה, לא מטפל: מכיר במה שנאמר, ומצביע על מבוגר. בלי אבחון ובלי הבטחות."""
        lines = [
            "מה שכתבת חשוב, ואני שמח שסיפרת לי. 💙",
            "",
            "זה גם משהו שאני לא יכול לעזור איתו לבד - וזה לא בגלל שזה לא רציני, אלא בדיוק "
            "בגלל שכן. מגיע לך מבוגר אמיתי שיקשיב לך: הורה, מורה, יועצת בית הספר, "
            "או מישהו אחר שאתה סומך עליו.",
            "",
            "אם קשה לדבר עם מישהו שאתה מכיר, אפשר לפנות גם לכאן:",
        ]
        for entry in self.hotlines:
            lines.append(f"  • {entry.get('name', '')} — {entry.get('phone', '')}")
        lines += ["", "אני כאן וממשיך ללמוד איתך מתי שתרצה."]
        return "\n".join(lines)
