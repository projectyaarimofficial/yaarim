"""מדידת tokens/sec לכל מודל מוגדר, ורישום התוצאות ללוג.

הרצה: python -m yoni.benchmark
משתמש בנתוני eval_count/eval_duration שאולמה מחזירה - מדידה אמיתית של קצב
הפקת טוקנים (generation), לא כולל זמן טעינת המודל (נמדד בנפרד כ-load_s).
מכבד את כלל ה-VRAM: המודלים נמדדים אחד-אחד דרך ensure_capacity.
"""

import json
import os
from datetime import datetime

import requests

from . import config, model_manager

BENCH_LOG = os.path.join(config.DATA_DIR, "benchmarks.jsonl")

PROMPTS = {
    "default": "הסבר בקצרה (3-4 משפטים) למה השמיים כחולים.",
    "qwen2.5-coder:7b": "Write a Python function that returns the n-th Fibonacci number. Code only.",
}


def _installed_models():
    try:
        response = requests.get(f"{config.OLLAMA_HOST}/api/tags", timeout=5)
        response.raise_for_status()
        return {m["name"] for m in response.json().get("models", [])}
    except requests.exceptions.RequestException:
        return set()


def bench_generate(model):
    """מודד מודל יצירה (generate). מחזיר dict תוצאה או None אם נכשל."""
    model_manager.ensure_capacity(model)
    prompt = PROMPTS.get(model, PROMPTS["default"])
    try:
        response = requests.post(
            config.OLLAMA_URL,
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=600,
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        return {"model": model, "error": str(e)}

    eval_count = data.get("eval_count", 0)
    eval_ns = data.get("eval_duration", 0)
    load_ns = data.get("load_duration", 0)
    tokens_per_sec = (eval_count / (eval_ns / 1e9)) if eval_ns else None
    return {
        "model": model,
        "tokens_per_sec": round(tokens_per_sec, 1) if tokens_per_sec else None,
        "eval_tokens": eval_count,
        "load_s": round(load_ns / 1e9, 1),
        "total_s": round(data.get("total_duration", 0) / 1e9, 1),
    }


def bench_embed(model):
    """מודד מודל embeddings (אין tokens/sec - מודדים זמן לבקשה)."""
    model_manager.ensure_capacity(model)
    text = "מערכת השמש מכילה שמונה כוכבי לכת הסובבים סביב השמש."
    try:
        start = datetime.now()
        response = requests.post(
            config.OLLAMA_EMBED_URL, json={"model": model, "prompt": text}, timeout=120
        )
        response.raise_for_status()
        elapsed = (datetime.now() - start).total_seconds()
        dim = len(response.json().get("embedding", []))
    except requests.exceptions.RequestException as e:
        return {"model": model, "error": str(e)}
    return {"model": model, "embed_s": round(elapsed, 2), "dim": dim}


def run():
    installed = _installed_models()
    targets = [
        config.TUTOR_MODEL,
        config.CODER_MODEL,
        config.REASONING_MODEL,
    ]
    # בלי כפילויות, בשמירת סדר
    targets = list(dict.fromkeys(targets))

    results = []
    print("🏁 בנצ'מרק מודלים (tokens/sec) - נמדד אחד-אחד לפי תקציב ה-VRAM\n")

    for warning in model_manager.startup_check():
        print(warning)

    for model in targets:
        if model not in installed:
            print(f"⏭️  {model}: לא מותקן - מדלג.")
            results.append({"model": model, "skipped": "not installed"})
            continue
        print(f"⏱️  מודד את {model} ...")
        results.append(bench_generate(model))

    if config.EMBED_MODEL in installed:
        print(f"⏱️  מודד את {config.EMBED_MODEL} (embeddings) ...")
        results.append(bench_embed(config.EMBED_MODEL))
    else:
        print(f"⏭️  {config.EMBED_MODEL}: לא מותקן - מדלג.")
        results.append({"model": config.EMBED_MODEL, "skipped": "not installed"})

    os.makedirs(config.DATA_DIR, exist_ok=True)
    entry = {"timestamp": datetime.now().isoformat(timespec="seconds"), "results": results}
    with open(BENCH_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print("\n📊 תוצאות:")
    for r in results:
        if r.get("skipped"):
            print(f"  {r['model']}: skipped ({r['skipped']})")
        elif r.get("error"):
            print(f"  {r['model']}: ERROR {r['error'][:80]}")
        elif "tokens_per_sec" in r:
            print(f"  {r['model']}: {r['tokens_per_sec']} tok/s  (load {r['load_s']}s, total {r['total_s']}s)")
        else:
            print(f"  {r['model']}: embed {r['embed_s']}s, dim={r['dim']}")
    print(f"\n📝 נרשם ל: {BENCH_LOG}")
    return results


if __name__ == "__main__":
    run()
