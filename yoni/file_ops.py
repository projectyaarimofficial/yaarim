import ast
import os
import re
import shutil
from datetime import datetime

from . import config


def read_relevant_context(file_path, user_request):
    """קורא קובץ קיים ומחזיר רק את החלק הרלוונטי לבקשה, כדי לחסוך הקשר במודל."""
    if not file_path or not os.path.exists(file_path):
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        source = f.read()

    if len(source) <= config.MAX_CONTEXT_CHARS:
        return source

    keywords = _extract_keywords(user_request)
    chunks = _extract_chunks(source)
    relevant = [chunk for chunk in chunks if _matches(chunk, keywords)]

    if not relevant:
        return source[: config.MAX_CONTEXT_CHARS] + "\n# ... (הקובץ נחתך, ארוך מדי לשליחה מלאה)"

    return "\n\n".join(relevant)


def _extract_keywords(text):
    words = re.findall(r"[a-zA-Zא-ת_]{3,}", text.lower())
    return set(words)


def _extract_chunks(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return [source]

    lines = source.splitlines()
    chunks = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno)
            chunks.append("\n".join(lines[start:end]))
    return chunks


def _matches(chunk, keywords):
    chunk_lower = chunk.lower()
    return any(keyword in chunk_lower for keyword in keywords)


def backup_file(file_path):
    if not file_path or not os.path.exists(file_path):
        return None

    os.makedirs(config.BACKUPS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.basename(file_path)
    backup_path = os.path.join(config.BACKUPS_DIR, f"{filename}.{timestamp}.bak")
    shutil.copy2(file_path, backup_path)
    return backup_path


def write_file(file_path, content):
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
