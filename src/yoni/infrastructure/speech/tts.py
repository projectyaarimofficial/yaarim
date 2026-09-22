"""דיבור עברי מקומי, דרך Piper.

שני פורמטים של קולות עבריים קיימים בשטח, והם דורשים צינור שונה:

    phoneme_type="hebrew"  Piper מנקד בעצמו (Nakdimon) וממיר ל-IPA.
                           מזינים לו עברית רגילה. למשל he_IL-saspeech-medium.
    phoneme_type="raw"     הקול מצפה ל-IPA מוכן. הניקוד נעשה בחוץ (Phonikud),
                           ו-Piper 1.8 לא מכיר את הערך הזה בכלל - ולכן מכריזים
                           espeak בתצורה, מדלגים על הפינום, וממפים ידנית.

הטעות הקלה כאן היא להריץ ניקוד חיצוני *ו*להזין לקול מהסוג הראשון: הוא מפנם
שוב, והתוצאה ג'יבריש שנשמע כמו שפה זרה.

הכל רץ מקומית. שום טקסט של תלמיד לא עוזב את המכונה.
"""

import io
import json
import logging
import os
import re
import wave
from typing import Optional

from ...domain.ports import SpeechSynthesizer

log = logging.getLogger(__name__)

#: תווים שמודל שפה מייצר ואין להקריא: markdown, אימוג'ים, סימני עיצוב.
_MARKDOWN = re.compile(r"[*_`#>|~]+")
_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿]+"
)
_BULLET = re.compile(r"^\s*[-•·]\s*", re.MULTILINE)
_LINK = re.compile(r"https?://\S+")
_WHITESPACE = re.compile(r"[ \t]+")
_BLANK_LINES = re.compile(r"\n{2,}")

#: מעל זה הדיבור ארוך מדי לשיעור - נקטע בגבול משפט.
MAX_CHARS = 1200


def speakable(text: str) -> str:
    """מנקה טקסט לקראת הקראה. מה שנראה טוב על המסך לא בהכרח נשמע טוב."""
    clean = _LINK.sub(" ", text or "")
    clean = _EMOJI.sub(" ", clean)
    clean = _BULLET.sub("", clean)
    clean = _MARKDOWN.sub("", clean)
    clean = _WHITESPACE.sub(" ", clean)
    clean = _BLANK_LINES.sub("\n", clean).strip()

    if len(clean) > MAX_CHARS:
        cut = clean[:MAX_CHARS]
        stop = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"), cut.rfind("\n"))
        clean = cut[:stop + 1] if stop > MAX_CHARS // 2 else cut
    return clean


class PiperSpeech(SpeechSynthesizer):
    """טוען את הקול פעם אחת, בעצלתיים, ומשרת ממנו את כל ההקראות."""

    def __init__(self, model_path: str, config_path: Optional[str] = None,
                 length_scale: float = 1.3, noise_scale: float = 0.45,
                 noise_w_scale: float = 0.6):
        self._model_path = model_path
        self._config_path = config_path
        self._length_scale = length_scale
        self._noise_scale = noise_scale
        self._noise_w_scale = noise_w_scale
        self._voice = None
        self._phonikud = None
        self._raw_ipa = False
        self._broken = False

    @property
    def available(self) -> bool:
        if self._broken:
            return False
        return os.path.exists(self._model_path)

    # ---- טעינה ---------------------------------------------------------
    def _patched_config(self) -> str:
        """Piper 1.8 דוחה phoneme_type=raw. מכריזים espeak ומדלגים על הפינום."""
        with open(self._config_path, encoding="utf-8") as handle:
            config = json.load(handle)
        if config.get("phoneme_type") != "raw":
            return self._config_path

        self._raw_ipa = True
        config["phoneme_type"] = "espeak"
        patched = os.path.join(os.path.dirname(self._config_path),
                               "_piper_patched.config.json")
        with open(patched, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False)
        return patched

    def _load(self):
        if self._voice is not None or self._broken:
            return self._voice
        try:
            from piper import PiperVoice

            config_path = self._patched_config() if self._config_path else None
            voice = PiperVoice.load(self._model_path, config_path=config_path)
            # קול מסוג raw בלי מנקד אינו "חצי עובד" - הוא שובר כל הקראה.
            # לכן שניהם נטענים למשתנים מקומיים, ורק הצלחה מלאה מתפרסמת.
            phonikud = self._load_phonikud() if self._raw_ipa else None
            self._voice, self._phonikud = voice, phonikud
        except Exception:
            log.exception("Speech engine unavailable; falling back to text")
            self._broken = True
            self._voice = self._phonikud = None
        return self._voice

    def _load_phonikud(self):
        from phonikud_onnx import Phonikud

        model = os.path.join(os.path.dirname(self._model_path),
                             "phonikud-1.0.int8.onnx")
        if not os.path.exists(model):
            raise FileNotFoundError(f"missing diacritics model: {model}")
        return Phonikud(model)

    # ---- הקראה ---------------------------------------------------------
    def _config(self):
        from piper import SynthesisConfig

        return SynthesisConfig(
            length_scale=self._length_scale,
            noise_scale=self._noise_scale,
            noise_w_scale=self._noise_w_scale,
            normalize_audio=True,
        )

    def _to_wav(self, audio, rate: int) -> bytes:
        if hasattr(audio, "audio_int16_bytes"):
            frames = audio.audio_int16_bytes
        elif isinstance(audio, (bytes, bytearray)):
            frames = bytes(audio)
        else:
            import numpy as np

            array = np.asarray(audio)
            if array.dtype != np.int16:
                peak = float(np.max(np.abs(array))) or 1.0
                array = (array / peak * 32767 * 0.95).astype(np.int16)
            frames = array.tobytes()

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(rate)
            handle.writeframes(frames)
        return buffer.getvalue()

    def speak(self, text: str) -> Optional[bytes]:
        content = speakable(text)
        if not content:
            return None
        voice = self._load()
        if voice is None:
            return None

        try:
            if self._raw_ipa:
                if self._phonikud is None:
                    raise RuntimeError("raw-IPA voice loaded without a diacritizer")
                from phonikud import phonemize

                ipa = phonemize(self._phonikud.add_diacritics(content))
                ids = voice.phonemes_to_ids(list(ipa))
                audio = voice.phoneme_ids_to_audio(ids, syn_config=self._config())
                return self._to_wav(audio, voice.config.sample_rate)

            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as handle:
                voice.synthesize_wav(content, handle, syn_config=self._config())
            return buffer.getvalue()
        except Exception:
            # שיעור לא נעצר בגלל תקלת קול. ממשיכים בכתב.
            log.exception("Speech synthesis failed")
            return None


class NoSpeech(SpeechSynthesizer):
    """אין מנוע דיבור. מפורש עדיף על None שמסתובב במערכת."""

    @property
    def available(self) -> bool:
        return False

    def speak(self, text: str) -> Optional[bytes]:
        return None
