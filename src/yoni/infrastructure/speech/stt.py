"""תמלול דיבור עברי, מקומית.

המודל הוא whisper-large-v3-turbo שכוונן לעברית על ידי ivrit.ai. Whisper המקורי
מזהה עברית בינוני; הכיוונון הזה הוא ההבדל בין "עובד" ל"עובד עם ילד בן 12
שמדבר מהר".

מורד פעם אחת ונשמר במטמון. אחרי ההורדה - אפס רשת, כמו כל השאר ביערים.
"""

import io
import logging
import os
import tempfile
from typing import Optional

from ...domain.ports import SpeechTranscriber

log = logging.getLogger(__name__)

MODEL = "ivrit-ai/whisper-large-v3-turbo-ct2"

#: סימני כיווניות בלתי נראים (אותה רשימה שב-content/grader.py).
RTL_MARKS = "‎‏‪‫‬‭‮⁦⁧⁩"

#: חבילות ה-pip של NVIDIA שמות את ה-DLL תחת site-packages/nvidia/<x>/bin.
#: ב-Windows זה לא ב-PATH, ו-CTranslate2 נופל על "cublas64_12.dll is not
#: found" למרות שהקובץ קיים. os.add_dll_directory פותר בלי לגעת בסביבה.
_CUDA_DLL_DIRS = ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime")


def register_cuda_libraries() -> int:
    """מרשם את ספריות ה-CUDA של pip. מחזיר כמה תיקיות נרשמו."""
    if not hasattr(os, "add_dll_directory"):
        return 0  # לא Windows
    try:
        import nvidia
        # nvidia היא namespace package: __file__ הוא None ורק __path__ קיים.
        roots = list(getattr(nvidia, "__path__", []))
    except Exception:
        return 0

    count = 0
    for root in roots:
        for package in _CUDA_DLL_DIRS:
            path = os.path.join(root, package, "bin")
            if not os.path.isdir(path):
                continue
            try:
                os.add_dll_directory(path)
                # PATH נדרש גם הוא: DLL אחד טוען את השני בעקיפין.
                os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")
                count += 1
            except OSError:
                log.debug("Could not register CUDA dir %s", path)
    return count


class WhisperTranscriber(SpeechTranscriber):
    def __init__(self, model_name: str = MODEL, device: str = "auto",
                 compute_type: Optional[str] = None, download_root: Optional[str] = None):
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._download_root = download_root
        self._model = None
        self._broken = False

    @property
    def available(self) -> bool:
        """זמין = המודל כבר על הדיסק.

        בכוונה לא "זמין = אפשר להוריד": ההורדה היא 1.6GB, והיא קרתה בתוך
        הבקשה שבה התלמיד לחץ על המיקרופון - הממשק נתקע לדקות בלי שום סימן
        שמשהו קורה. הורדה היא פעולה מפורשת, לא תופעת לוואי של שיחה.
        """
        return not self._broken and self.downloaded

    @property
    def downloaded(self) -> bool:
        return bool(self._model or self._find_weights())

    def _find_weights(self) -> Optional[str]:
        """model.bin של faster-whisper, אם כבר ירד (ישירות או במטמון HF)."""
        root = self._download_root
        if not root or not os.path.isdir(root):
            return None
        for directory, _, files in os.walk(root):
            if "model.bin" in files:
                return os.path.join(directory, "model.bin")
        return None

    def download(self) -> bool:
        """מוריד את המודל. נקרא רק מפעולה מפורשת של המשתמש."""
        return self._load() is not None

    def _load(self):
        if self._model is not None or self._broken:
            return self._model
        try:
            from faster_whisper import WhisperModel

            if self._device == "auto":
                self._device, self._compute_type = self._pick_device(self._compute_type)
            device, compute = self._device, self._compute_type
            if self._download_root:
                os.makedirs(self._download_root, exist_ok=True)
            self._model = WhisperModel(
                self._model_name, device=device, compute_type=compute,
                download_root=self._download_root,
            )
        except Exception:
            log.exception("Transcriber unavailable; microphone disabled")
            self._broken = True
        return self._model

    @staticmethod
    def _pick_device(compute):
        """GPU אם יש, אחרת CPU - בלי להפיל את המערכת על מכונה בלי כרטיס."""
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                register_cuda_libraries()
                return "cuda", compute or "float16"
        except Exception:
            pass
        return "cpu", compute or "int8"

    def _fall_back_to_cpu(self) -> bool:
        """GPU שנטען אך אינו מצליח לחשב - עדיין אפשר לתמלל, רק לאט יותר.

        קורה כשספריות ה-CUDA חסרות: המודל נטען, וההתרסקות מגיעה רק בחישוב
        הראשון. תלמיד לא אמור לשלם על זה בשקט.
        """
        if self._device == "cpu":
            return False
        log.warning("CUDA transcription failed; retrying on CPU")
        self._device, self._compute_type = "cpu", "int8"
        self._model = None
        return self._load() is not None

    @staticmethod
    def _run(model, path: str) -> str:
        segments, _ = model.transcribe(
            path, language="he", beam_size=5, vad_filter=True,
        )
        text = " ".join(segment.text.strip() for segment in segments)
        # whisper מוסיף לעתים סימני כיווניות בתחילת עברית. הם בלתי נראים,
        # אבל נשמרים בתמליל ומשבשים השוואות וחיפוש.
        return text.translate({ord(mark): None for mark in RTL_MARKS}).strip()

    def transcribe(self, audio: bytes) -> str:
        if not audio:
            return ""
        model = self._load()
        if model is None:
            return ""

        # faster-whisper קורא דרך av, שרוצה קובץ או stream עם שם. בדיסק זה
        # הנתיב האמין ביותר מול פורמטים שונים שדפדפנים מקליטים בהם.
        path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                handle.write(audio)
                path = handle.name
            return self._run(model, path)
        except Exception:
            log.exception("Transcription failed")
            if self._fall_back_to_cpu():
                try:
                    return self._run(self._model, path)
                except Exception:
                    log.exception("Transcription failed on CPU too")
            return ""
        finally:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


class NoTranscriber(SpeechTranscriber):
    """אין תמלול. התלמיד מקליד."""

    @property
    def available(self) -> bool:
        return False

    def transcribe(self, audio: bytes) -> str:
        return ""
