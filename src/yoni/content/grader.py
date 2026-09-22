"""Pure grading and financial-advice checks for subject content."""

import re
from typing import Optional

RTL_MARKS = "\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2069"
NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
ASSET_WORDS = r"(?:מניית|מניות|מניה|ביטקוין|קריפטו|אתריום|איתריום)"
ADVICE_VERBS = r"(?:לקנות|למכור|להשקיע|לרכוש|תשקיע|תקנה|תמכור)"

ADVICE_PATTERNS = (
    (re.compile(r"כדאי לך\s+(?:לקנות|למכור|להשקיע)"), "advice_decision"),
    (re.compile(r"אני\s+ממליץ"), "advice_recommendation"),
    (re.compile(r"תשקיע\s+ב"), "advice_decision"),
    # רק המלצה על נכס ספציפי נחסמת - לא עצם האזכור, כדי לא לחסום הסבר חינוכי
    # על מה זו מניה או ביטקוין (למשל בנושא סיכון-תשואה-פיזור).
    (re.compile(rf"{ADVICE_VERBS}\s+(?:ב-?)?{ASSET_WORDS}"), "specific_asset"),
    (re.compile(rf"{ASSET_WORDS}\s+(?:היא|הוא)?\s*{ADVICE_VERBS}"), "specific_asset"),
    (re.compile(r"תשואה\s+מובטחת"), "guaranteed_return"),
)

REPLACEMENT = "יוני מלמד מנגנונים ועקרונות פיננסיים, ולא מקבל החלטות השקעה או קנייה במקום התלמיד."


def parse_number(raw) -> Optional[float]:
    """Extract the first decimal number, tolerating Hebrew currency formatting."""
    if raw is None:
        return None
    cleaned = str(raw)
    for mark in RTL_MARKS:
        cleaned = cleaned.replace(mark, "")
    match = NUMBER_RE.search(cleaned)
    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _choice_index(item, raw_answer) -> Optional[int]:
    choices = item.get("choices_he") or []
    text = " ".join(str(raw_answer).strip().split()).casefold()
    for index, choice in enumerate(choices):
        if text == " ".join(str(choice).strip().split()).casefold():
            return index
    number = parse_number(raw_answer)
    if number is not None and number.is_integer():
        index = int(number)
        if 0 <= index < len(choices):
            return index
    return None


def grade(item, raw_answer):
    """Return a stable verdict without invoking a language model."""
    kind = item.get("kind")
    if kind == "open":
        return {"verdict": "needs_review", "graded_by": "rubric_llm"}

    if kind == "numeric":
        actual = parse_number(raw_answer)
        if actual is None:
            return {"verdict": "needs_review", "graded_by": "code"}
        expected = float(item["answer"])
        tolerance = float(item.get("tolerance") or 0)
        verdict = "correct" if abs(actual - expected) <= tolerance else "wrong"
        return {"verdict": verdict, "graded_by": "code"}

    if kind == "mcq":
        actual = _choice_index(item, raw_answer)
        if actual is None:
            return {"verdict": "needs_review", "graded_by": "code"}
        verdict = "correct" if actual == int(item["answer"]) else "wrong"
        return {"verdict": verdict, "graded_by": "code"}

    return {"verdict": "needs_review", "graded_by": "code"}


def check_finance_output(text: str):
    """Block personalized financial decisions in outbound Hebrew messages."""
    content = str(text or "")
    for pattern, reason in ADVICE_PATTERNS:
        if pattern.search(content):
            return {"ok": False, "replacement": REPLACEMENT, "reason": reason}
    return {"ok": True, "replacement": None, "reason": None}
