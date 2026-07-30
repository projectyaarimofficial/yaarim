"""ניהול טעינת מודלים מול תקציב ה-VRAM (RTX 5060, 8GB).

הכלל המרכזי: לעולם לא שני מודלים "כבדים" (7-8B) טעונים יחד - 8GB לא מכיל
את שניהם. ensure_capacity נקרא לפני כל קריאה למודל (דרך llm_client) ומפרק
מהזיכרון מודלים אחרים לפי הצורך, כך שהאכיפה בקוד ולא בתקווה.

מודלים שאינם ברשימת MODEL_VRAM_GB לא מנוהלים (למשל מודלים מדומים בבדיקות).
"""

import subprocess

import requests

from . import config


def _vram_gb(model):
    return config.MODEL_VRAM_GB.get(model)


def is_heavy(model):
    estimate = _vram_gb(model)
    return estimate is not None and estimate >= config.HEAVY_THRESHOLD_GB


def loaded_models():
    """מחזיר רשימת שמות המודלים הטעונים כרגע ב-Ollama (ריק אם השרת לא זמין)."""
    try:
        response = requests.get(f"{config.OLLAMA_HOST}/api/ps", timeout=5)
        response.raise_for_status()
        return [m["name"] for m in response.json().get("models", [])]
    except (requests.exceptions.RequestException, ValueError, KeyError):
        return []


def unload(model):
    """מפרק מודל מהזיכרון (keep_alive=0). שקט אם נכשל - במקרה הגרוע Ollama יפנה לבד."""
    try:
        requests.post(
            config.OLLAMA_URL,
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=30,
        )
    except requests.exceptions.RequestException:
        pass


def ensure_capacity(model):
    """מפנה מקום לפני טעינת model: מפרק מודלים כבדים אחרים ומוודא עמידה בתקציב.

    מחזיר רשימת מודלים שפורקו (לצורכי לוג/בדיקה).
    """
    target = _vram_gb(model)
    if target is None:  # מודל לא מוכר (למשל בבדיקות) - לא מתערבים
        return []

    unloaded = []
    current = [m for m in loaded_models() if m != model]

    # כלל 1: מודל כבד לא חי לצד מודל כבד אחר.
    if is_heavy(model):
        for other in current:
            if is_heavy(other):
                unload(other)
                unloaded.append(other)
        current = [m for m in current if m not in unloaded]

    # כלל 2: אם עדיין חורגים מהתקציב הכולל - מפרקים מהגדול לקטן.
    def total(models):
        return sum(_vram_gb(m) or 0 for m in models)

    remaining = sorted(current, key=lambda m: _vram_gb(m) or 0, reverse=True)
    while remaining and total(remaining) + target > config.VRAM_BUDGET_GB:
        victim = remaining.pop(0)
        unload(victim)
        unloaded.append(victim)

    return unloaded


def detect_vram_gb():
    """VRAM אמיתי מ-nvidia-smi (GB), או None אם אין GPU/כלי זמין."""
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


def startup_check():
    """בדיקת פתיחה: אזהרות על מודלים שלא נכנסים ב-VRAM. מחזיר רשימת אזהרות."""
    warnings = []
    vram = detect_vram_gb() or config.VRAM_BUDGET_GB

    for model, estimate in config.MODEL_VRAM_GB.items():
        if estimate > vram:
            warnings.append(
                f"⚠️ המודל {model} (~{estimate}GB) חורג מה-VRAM הזמין (~{vram:.1f}GB) - יגלוש ל-RAM ויאט משמעותית."
            )

    heavies = [m for m in config.MODEL_VRAM_GB if is_heavy(m)]
    for i, first in enumerate(heavies):
        for second in heavies[i + 1:]:
            pair = config.MODEL_VRAM_GB[first] + config.MODEL_VRAM_GB[second]
            if pair > vram:
                warnings.append(
                    f"⚠️ {first} + {second} יחד (~{pair}GB) לא נכנסים ב-VRAM (~{vram:.1f}GB) - ייטענו רק אחד בכל רגע (נאכף אוטומטית)."
                )
    return warnings
