"""מימוש LanguageModel מול Ollama מקומי.

זו הנקודה היחידה בכל המערכת שיודעת ש-requests קיים ושיש HTTP. מעליה, כולם
מדברים דרך הפורט - ולכן בדיקה לא צריכה לרוץ מול שרת אמיתי, והחלפת ספק
(או ריצה מול מודל אחר לגמרי) אינה נוגעת בליבה.
"""

import requests
from typing import List, Optional, Set


from ...domain.ports import LanguageModel, LanguageModelError


class OllamaLanguageModel(LanguageModel):
    def __init__(self, settings, vram_budget=None):
        self._settings = settings
        self._vram = vram_budget  # אופציונלי: אם הוזרק, נאכף לפני כל קריאה

    def _ensure_capacity(self, model):
        if self._vram is not None:
            self._vram.ensure_capacity(model)

    def complete(self, prompt: str, model: Optional[str] = None,
                 expect_json: bool = False) -> str:
        model = model or self._settings.tutor_model
        self._ensure_capacity(model)
        payload = {"model": model, "prompt": prompt, "stream": False}
        if expect_json:
            payload["format"] = "json"
        try:
            response = requests.post(
                self._settings.generate_url,
                json=payload,
                timeout=self._settings.request_timeout_s,
            )
            response.raise_for_status()
            return response.json()["response"]
        except requests.exceptions.RequestException as e:
            raise LanguageModelError(f"שגיאה בתקשורת עם המודל ({model}): {e}") from e

    def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        model = model or self._settings.embed_model
        self._ensure_capacity(model)
        try:
            response = requests.post(
                self._settings.embed_url, json={"model": model, "prompt": text}, timeout=120
            )
            response.raise_for_status()
            return response.json()["embedding"]
        except requests.exceptions.RequestException as e:
            raise LanguageModelError(f"שגיאה ב-embedding ({model}): {e}") from e

    def installed_models(self) -> Set[str]:
        try:
            response = requests.get(self._settings.tags_url, timeout=5)
            response.raise_for_status()
            return {m["name"] for m in response.json().get("models", [])}
        except (requests.exceptions.RequestException, ValueError, KeyError):
            return set()
