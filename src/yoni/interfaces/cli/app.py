"""ממשק ה-CLI: הבנייה העצמית (/build).

הממשק אחראי רק על קלט/פלט ועל *לשאול את המשתמש*. כל ההחלטות נמצאות בשירות.
לכן אין כאן לוגיקה עסקית, ואפשר להחליף את הממשק בלי לגעת בה.
"""

import sys
from typing import Optional

from ...container import Container
from ...domain.ports import LanguageModelError, WriteDenied


class BuildCli:
    def __init__(self, container: Optional[Container] = None,
                 reader=input, writer=print) -> None:
        self._c = container or Container()
        self._read = reader
        self._write = writer

    def _confirm(self, question):
        return self._read(f"\n{question} (yes/no): ").strip().lower() in ("yes", "y")

    def run_once(self, request: str) -> bool:
        """מחזור אחד: תוכנית → אישור → קוד → אישור → כתיבה."""
        service = self._c.authoring

        self._write("\n🤖 יוני מחשב תוכנית עבודה...")
        try:
            plan = service.plan(request)
        except LanguageModelError as e:
            self._write(f"\n⚠️ {e}")
            self._write(f"ודא ש-Ollama רץ ({self._c.settings.ollama_host}) ושהמודל קיים.")
            return False

        self._write("\n📋 --- תוכנית עבודה מוצעת ---")
        self._write(plan.summary)
        if plan.target_file:
            self._write(f"\nקובץ יעד מוצע: {plan.target_file}"
                        f" ({'קיים' if plan.file_exists else 'חדש'})")
        self._write("------------------------------")

        if not self._confirm("האם אתה מאשר את התוכנית?"):
            self._write("\n❌ התוכנית בוטלה.")
            return False

        try:
            target = service.resolve_target(plan.target_file)
        except WriteDenied as e:
            # היעד נדחה בקוד. לא שואלים את המשתמש אם לאשר - פשוט מסרבים.
            self._write(f"\n🚫 {e}")
            target = None

        self._write("\n🛠️ יוני כותב את הקוד...")
        try:
            code = service.generate(request, plan, target)
        except LanguageModelError as e:
            self._write(f"\n⚠️ {e}")
            return False

        self._write("\n💾 --- קוד שנוצר ---")
        self._write(code)
        self._write("--------------------")

        if not target:
            manual = self._read("\nלא זוהה קובץ יעד. הזן נתיב לשמירה (Enter לביטול): ").strip()
            if not manual:
                self._write("\n❌ השמירה בוטלה.")
                return False
            try:
                target = service.resolve_target(manual)
            except WriteDenied as e:
                # גם נתיב שהוזן ידנית עובר את אותה גדר - אישור אנושי לא עוקף אותה.
                self._write(f"\n🚫 {e}")
                return False

        if not self._confirm(f"לשמור לקובץ: {target} ?"):
            self._write("\n❌ השמירה בוטלה.")
            return False

        outcome = service.commit(request, plan, code, target)
        if outcome["backup"]:
            self._write(f"🗄️  גיבוי נשמר ב: {outcome['backup']}")
        self._write(f"✅ נשמר בהצלחה: {outcome['path']}")
        self._write("🧠 השינוי נרשם בזיכרון (SQLite).")
        return True

    def loop(self) -> None:
        self._write("🧱 יערים (YAARIM) - יוני, מערכת בנייה עצמית")
        self._write("   /bench למדידת קצב המודלים · exit ליציאה")
        for warning in self._c.vram.warnings():
            self._write(warning)

        while True:
            try:
                request = self._read("\nמה תרצה להוסיף או לשנות במערכת? (או 'exit'): ").strip()
            except (EOFError, KeyboardInterrupt):
                self._write("\n\n👋 יוצא. להתראות!")
                return
            if request.lower() == "exit":
                self._write("\n👋 להתראות!")
                return
            if request.lower() in ("/bench", "/benchmark"):
                self._c.benchmark.run(report=self._write)
                continue
            if request:
                self.run_once(request)


def main(argv=None):
    BuildCli().loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
