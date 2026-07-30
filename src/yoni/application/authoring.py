"""שירות הבנייה העצמית (/build): תכנון → אישור → כתיבה → גיבוי → רישום.

שני שומרים פועלים כאן, ושניהם מוזרקים:
    WritePolicy   מחליט אם היעד מותר בכלל (כלל 1 בחוקה)
    approve       פונקציית אישור אנושי - הממשק מספק אותה

השירות עצמו לא מדפיס ולא קורא input: הוא מקבל את האישור כתלות. לכן אפשר
לבדוק אותו בלי מסך, ואפשר לחבר אותו ל-CLI או לממשק אחר בלי שינוי.
"""

import ast
import os
import re
import shutil
from typing import Optional


from ..domain.models import BuildPlan
from ..domain.ports import WriteDenied, WritePolicy


class ContextReader:
    """קורא רק את החלק הרלוונטי מקובץ קיים, כדי לחסוך הקשר במודל."""

    def __init__(self, max_chars: int):
        self._max_chars = max_chars

    def read(self, path: Optional[str], request: str) -> Optional[str]:
        if not path or not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        if len(source) <= self._max_chars:
            return source

        keywords = set(re.findall(r"[a-zA-Zא-ת_]{3,}", request.lower()))
        chunks = self._chunks(source)
        relevant = [c for c in chunks if any(k in c.lower() for k in keywords)]
        if not relevant:
            return source[: self._max_chars] + "\n# ... (הקובץ נחתך, ארוך מדי לשליחה מלאה)"
        return "\n\n".join(relevant)

    @staticmethod
    def _chunks(source):
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return [source]
        lines = source.splitlines()
        out = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.append("\n".join(lines[node.lineno - 1: getattr(node, "end_lineno", node.lineno)]))
        return out


class AuthoringService:
    def __init__(self, agent_factory, write_policy: WritePolicy,
                 change_log, settings):
        self._agents = agent_factory
        self._policy = write_policy
        self._log = change_log
        self._settings = settings
        self._context = ContextReader(settings.max_context_chars)

    def plan(self, request: str) -> BuildPlan:
        return self._agents.create("planner").plan(request)

    def resolve_target(self, target_file: Optional[str]) -> Optional[str]:
        """נתיב מאושר, או None אם לא צוין. זורק WriteDenied אם היעד מחוץ לפרויקט."""
        return self._policy.resolve(target_file) if target_file else None

    def generate(self, request: str, plan: BuildPlan,
                 target_path: Optional[str] = None) -> str:
        context = self._context.read(target_path, request) if target_path else None
        return self._agents.create("coder").write_code(request, plan.summary, context)

    def backup(self, path: Optional[str]) -> Optional[str]:
        if not path or not os.path.exists(path):
            return None
        os.makedirs(self._settings.backups_dir, exist_ok=True)
        from datetime import datetime
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        destination = os.path.join(
            self._settings.backups_dir, f"{os.path.basename(path)}.{stamp}.bak"
        )
        shutil.copy2(path, destination)
        return destination

    def commit(self, request: str, plan: BuildPlan, code: str,
               target_path: str) -> dict:
        """כותב בפועל. הנתיב עובר שוב דרך המדיניות - אישור אנושי לא עוקף אותה."""
        approved = self._policy.resolve(target_path)  # WriteDenied אם השתנה בינתיים
        backup_path = self.backup(approved)
        os.makedirs(os.path.dirname(approved), exist_ok=True)
        with open(approved, "w", encoding="utf-8") as f:
            f.write(code)
        if hasattr(self._log, "log_change"):
            self._log.log_change(request, plan.summary, [approved])
        return {"path": approved, "backup": backup_path}
