import os

import requests

from . import config
from .dev import CodeBuilder, CodePlanner
from .file_ops import backup_file, read_relevant_context, write_file
from .memory_db import init_db, log_change

_planner = CodePlanner()
_builder = CodeBuilder()


def resolve_path(target_file):
    if not target_file:
        return None
    if os.path.isabs(target_file):
        return target_file
    return os.path.normpath(os.path.join(config.BASE_DIR, target_file))


def run_plan_stage(user_request):
    print("\n🤖 יוני מחשב תוכנית עבודה...")
    plan_data = _planner.generate_plan(user_request)

    print("\n📋 --- תוכנית עבודה מוצעת ---")
    print(plan_data["plan"])
    if plan_data.get("target_file"):
        exists_label = "קיים" if plan_data.get("file_exists") else "חדש"
        print(f"\nקובץ יעד מוצע: {plan_data['target_file']} ({exists_label})")
    print("------------------------------")

    return plan_data


def run_execution_stage(user_request, plan_data):
    target_path = resolve_path(plan_data.get("target_file"))

    relevant_context = None
    if target_path and os.path.exists(target_path):
        relevant_context = read_relevant_context(target_path, user_request)

    print("\n🛠️ יוני כותב את הקוד...")
    generated_code = _builder.generate_code(user_request, plan_data["plan"], relevant_context)

    print("\n💾 --- קוד שנוצר ---")
    print(generated_code)
    print("--------------------")

    if not target_path:
        manual_path = input("\nלא זוהה קובץ יעד. הזן נתיב לשמירה (Enter לביטול): ").strip()
        if not manual_path:
            print("\n❌ השמירה בוטלה.")
            return
        target_path = resolve_path(manual_path)

    confirm_write = input(f"\nלשמור לקובץ: {target_path} ? (yes/no): ").strip().lower()
    if confirm_write not in ("yes", "y"):
        print("\n❌ השמירה בוטלה.")
        return

    backup_path = backup_file(target_path)
    if backup_path:
        print(f"🗄️  גיבוי של הקובץ הקיים נשמר ב: {backup_path}")

    write_file(target_path, generated_code)
    print(f"✅ נשמר בהצלחה: {target_path}")

    log_change(user_request, plan_data["plan"], [target_path])
    print("🧠 השינוי נרשם בזיכרון (SQLite).")


def main():
    print("🌲 ברוך הבא לפרויקט יערים (YAARIM) - יוני, מערכת בניה עצמית 🌲")
    init_db()

    from .model_manager import startup_check
    for warning in startup_check():
        print(warning)

    while True:
        try:
            user_request = input("\nמה תרצה להוסיף או לשנות במערכת? (או 'exit' ליציאה): ").strip()
            if user_request.lower() == "exit":
                break
            if not user_request:
                continue

            try:
                plan_data = run_plan_stage(user_request)
            except requests.exceptions.RequestException as e:
                print(f"\n⚠️ שגיאה בתקשורת עם המודל ({config.PLANNER_MODEL}): {e}")
                print("ודא ש-Ollama רץ (http://localhost:11434) ושהמודל קיים, ונסה שוב.")
                continue

            approval = input("\nהאם אתה מאשר את התוכנית? (yes/no): ").strip().lower()
            if approval not in ("yes", "y"):
                print("\n❌ התוכנית בוטלה. נסה להגדיר את הבקשה מחדש.")
                continue

            try:
                run_execution_stage(user_request, plan_data)
            except requests.exceptions.RequestException as e:
                print(f"\n⚠️ שגיאה בתקשורת עם המודל ({config.CODER_MODEL}): {e}")
                print("ודא ש-Ollama רץ (http://localhost:11434) ושהמודל קיים, ונסה שוב.")
                continue
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 יוצא. להתראות!")
            break


if __name__ == "__main__":
    main()
