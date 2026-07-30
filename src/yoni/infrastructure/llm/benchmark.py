"""מדידת קצב הפקת טוקנים לכל מודל.

שוחזר ב-2026-07-30: היכולת אבדה בריפקטור. הגרף חשף את זה - הקובץ
data/benchmarks.jsonl המשיך להתקיים עם מדידות אמיתיות, בזמן שהכלי שמייצר אותן
כבר לא היה בשום מקום. נתון יתום הוא סימן לכך שמשהו נמחק בלי שהבחינו.

זו תשתית ולא לוגיקה עסקית: המדידה נשענת על eval_count/eval_duration שאולמה
מחזירה, כלומר על פרטי הספק. לכן היא יושבת כאן ולא בשכבת ה-application, ואינה
מרחיבה את הפורט LanguageModel עבור שימוש נדיר.
"""

import json
import os
from datetime import datetime
from typing import List, Optional

PROMPTS = {
    "default": "הסבר בקצרה (3-4 משפטים) למה השמיים כחולים.",
    "qwen2.5-coder:7b": "Write a Python function that returns the n-th Fibonacci number. Code only.",
}


class ModelBenchmark:
    """מודד מודלים אחד-אחד, תוך כיבוד תקציב ה-VRAM."""

    def __init__(self, settings, vram_budget, log_path: Optional[str] = None) -> None:
        self._settings = settings
        self._vram = vram_budget
        self._log_path = log_path or os.path.join(settings.data_dir, "benchmarks.jsonl")

    def _installed(self):
        import requests
        try:
            response = requests.get(self._settings.tags_url, timeout=5)
            response.raise_for_status()
            return {m["name"] for m in response.json().get("models", [])}
        except (requests.exceptions.RequestException, ValueError, KeyError):
            return set()

    def measure(self, model: str) -> dict:
        """מדידה אמיתית של קצב הפקה - לא כולל זמן טעינה, שנמדד בנפרד."""
        import requests
        self._vram.ensure_capacity(model)
        prompt = PROMPTS.get(model, PROMPTS["default"])
        try:
            response = requests.post(
                self._settings.generate_url,
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=self._settings.request_timeout_s,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            return {"model": model, "error": str(e)}

        eval_count = data.get("eval_count", 0)
        eval_ns = data.get("eval_duration", 0)
        return {
            "model": model,
            "tokens_per_sec": round(eval_count / (eval_ns / 1e9), 1) if eval_ns else None,
            "eval_tokens": eval_count,
            "load_s": round(data.get("load_duration", 0) / 1e9, 1),
            "total_s": round(data.get("total_duration", 0) / 1e9, 1),
        }

    def measure_embedding(self, model: str) -> dict:
        import requests
        self._vram.ensure_capacity(model)
        text = "מערכת השמש מכילה שמונה כוכבי לכת הסובבים סביב השמש."
        try:
            start = datetime.now()
            response = requests.post(
                self._settings.embed_url, json={"model": model, "prompt": text}, timeout=120
            )
            response.raise_for_status()
            elapsed = (datetime.now() - start).total_seconds()
            return {"model": model, "embed_s": round(elapsed, 2),
                    "dim": len(response.json().get("embedding", []))}
        except requests.exceptions.RequestException as e:
            return {"model": model, "error": str(e)}

    def targets(self) -> List[str]:
        """המודלים שנמדדים, בלי כפילויות ובשמירת סדר."""
        return list(dict.fromkeys([
            self._settings.tutor_model,
            self._settings.coder_model,
            self._settings.reasoning_model,
        ]))

    def run(self, report=print) -> List[dict]:
        """מודד הכל ורושם ל-jsonl. report מוזרק כדי שהמחלקה לא תדפיס בעצמה."""
        installed = self._installed()
        results = []

        report("🏁 בנצ'מרק מודלים (tokens/sec) - נמדד אחד-אחד לפי תקציב ה-VRAM\n")
        for warning in self._vram.warnings():
            report(warning)

        for model in self.targets():
            if model not in installed:
                report(f"⏭️  {model}: לא מותקן - מדלג.")
                results.append({"model": model, "skipped": "not installed"})
                continue
            report(f"⏱️  מודד את {model} ...")
            results.append(self.measure(model))

        embed_model = self._settings.embed_model
        if embed_model in installed:
            report(f"⏱️  מודד את {embed_model} (embeddings) ...")
            results.append(self.measure_embedding(embed_model))
        else:
            results.append({"model": embed_model, "skipped": "not installed"})

        self._append(results)

        report("\n📊 תוצאות:")
        for r in results:
            if r.get("skipped"):
                report(f"  {r['model']}: skipped ({r['skipped']})")
            elif r.get("error"):
                report(f"  {r['model']}: ERROR {r['error'][:80]}")
            elif "tokens_per_sec" in r:
                report(f"  {r['model']}: {r['tokens_per_sec']} tok/s"
                       f"  (load {r['load_s']}s, total {r['total_s']}s)")
            else:
                report(f"  {r['model']}: embed {r['embed_s']}s, dim={r['dim']}")
        report(f"\n📝 נרשם ל: {self._log_path}")
        return results

    def _append(self, results):
        os.makedirs(os.path.dirname(self._log_path), exist_ok=True)
        entry = {"timestamp": datetime.now().isoformat(timespec="seconds"), "results": results}
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def history(self) -> List[dict]:
        """המדידות הקודמות - כדי שאפשר יהיה להשוות בין חומרות."""
        if not os.path.exists(self._log_path):
            return []
        entries = []
        with open(self._log_path, encoding="utf-8") as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries
