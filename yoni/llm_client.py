import requests

from . import config, model_manager


def ask_yoni(prompt, model, expect_json=False):
    # אכיפת תקציב ה-VRAM לפני כל קריאה: לעולם לא שני מודלים כבדים יחד.
    model_manager.ensure_capacity(model)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if expect_json:
        payload["format"] = "json"

    response = requests.post(config.OLLAMA_URL, json=payload, timeout=600)
    response.raise_for_status()
    return response.json()["response"]


def embed(text, model=None):
    """מחזיר embedding (רשימת float) לטקסט, ל-RAG עתידי."""
    model = model or config.EMBED_MODEL
    model_manager.ensure_capacity(model)
    response = requests.post(
        config.OLLAMA_EMBED_URL,
        json={"model": model, "prompt": text},
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["embedding"]
