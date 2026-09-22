"""Validate and seed subject content into SQLite."""

import json
import os
import sqlite3
from contextlib import closing

SCHEMA_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "schema_topics.sql"))
TOPICS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "finlit_topics.json"))
ITEMS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "finlit_items.json"))


def _load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _payload(data, key):
    return data.get(key, []) if isinstance(data, dict) else []


def validate_content(topics_data, items_data):
    """Return every validation error without touching SQLite."""
    errors = []
    topics = _payload(topics_data, "topics")
    items = _payload(items_data, "items")
    topic_ids = [topic.get("id") for topic in topics if isinstance(topic, dict)]
    item_ids = [item.get("id") for item in items if isinstance(item, dict)]
    for value in {value for value in topic_ids if value is not None}:
        if topic_ids.count(value) > 1:
            errors.append(f"duplicate topic id: {value}")
    for value in {value for value in item_ids if value is not None}:
        if item_ids.count(value) > 1:
            errors.append(f"duplicate item id: {value}")

    topic_set = set(topic_ids)
    graph = {topic_id: [] for topic_id in topic_set}
    for topic in topics:
        if not isinstance(topic, dict):
            errors.append("topic is not an object")
            continue
        topic_id = topic.get("id")
        for prereq in topic.get("prereqs", []):
            if prereq not in topic_set:
                errors.append(f"unknown prerequisite: {topic_id} -> {prereq}")
            else:
                graph.setdefault(topic_id, []).append(prereq)

    visiting = set()
    visited = set()

    def visit(topic_id, trail):
        if topic_id in visiting:
            errors.append("cycle: " + " -> ".join(trail + [topic_id]))
            return
        if topic_id in visited:
            return
        visiting.add(topic_id)
        for prereq in graph.get(topic_id, []):
            visit(prereq, trail + [topic_id])
        visiting.remove(topic_id)
        visited.add(topic_id)

    for topic_id in graph:
        visit(topic_id, [])

    for item in items:
        if not isinstance(item, dict):
            errors.append("item is not an object")
            continue
        item_id = item.get("id")
        if item.get("topic_id") not in topic_set:
            errors.append(f"item points at missing topic: {item_id} -> {item.get('topic_id')}")
        if not str(item.get("explain_he") or "").strip():
            errors.append(f"item has no explanation: {item_id}")
        if item.get("kind") in ("numeric", "mcq") and item.get("answer") is None:
            errors.append(f"checkable item has no answer: {item_id}")
        if item.get("kind") == "open" and not str(item.get("rubric_he") or "").strip():
            errors.append(f"open item has no rubric: {item_id}")
    return errors


def _connection(db):
    if isinstance(db, sqlite3.Connection):
        return db, False
    return sqlite3.connect(str(db)), True


def seed_content(db, topics_path=TOPICS_PATH, items_path=ITEMS_PATH, schema_path=SCHEMA_PATH):
    """Validate fully, then initialize and upsert content. Return validation errors."""
    topics_data = _load(topics_path)
    items_data = _load(items_path)
    errors = validate_content(topics_data, items_data)
    if errors:
        print("Content validation failed:")
        for error in errors:
            print(f"- {error}")
        return errors

    connection, owns_connection = _connection(db)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        with open(schema_path, encoding="utf-8") as schema:
            connection.executescript(schema.read())
        track = topics_data.get("track", "finlit")
        for topic in _payload(topics_data, "topics"):
            connection.execute(
                    """INSERT INTO topics(id, track, name_he, summary_he, grade_band, seq)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET track=excluded.track,
                       name_he=excluded.name_he, summary_he=excluded.summary_he,
                       grade_band=excluded.grade_band, seq=excluded.seq""",
                    (topic["id"], topic.get("track", track), topic["name_he"],
                     topic["summary_he"], topic["grade_band"], topic["seq"]),
                )
        for topic in _payload(topics_data, "topics"):
            connection.execute("DELETE FROM topic_prereqs WHERE topic_id = ?", (topic["id"],))
            for prereq in topic.get("prereqs", []):
                connection.execute(
                    "INSERT OR IGNORE INTO topic_prereqs(topic_id, prereq_id) VALUES (?, ?)",
                    (topic["id"], prereq),
                )
        for item in _payload(items_data, "items"):
            choices = item.get("choices_he")
            connection.execute(
                    """INSERT INTO items(id, topic_id, kind, difficulty, prompt_he, choices_he,
                       answer, tolerance, unit, rubric_he, explain_he)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET topic_id=excluded.topic_id,
                       kind=excluded.kind, difficulty=excluded.difficulty,
                       prompt_he=excluded.prompt_he, choices_he=excluded.choices_he,
                       answer=excluded.answer, tolerance=excluded.tolerance, unit=excluded.unit,
                       rubric_he=excluded.rubric_he, explain_he=excluded.explain_he""",
                    (item["id"], item["topic_id"], item["kind"], item["difficulty"],
                     item["prompt_he"], json.dumps(choices, ensure_ascii=False) if choices is not None else None,
                     item.get("answer"), item.get("tolerance"), item.get("unit"),
                     item.get("rubric_he"), item["explain_he"]),
                )
        connection.commit()
    finally:
        if owns_connection:
            connection.close()
    return []


seed = seed_content


def next_topic(db, student_id, track):
    """Return the first eligible topic ordered by track sequence, or None."""
    connection, owns_connection = _connection(db)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT t.* FROM topics t
               LEFT JOIN mastery m ON m.topic_id = t.id AND m.student_id = ?
               WHERE t.track = ? AND NOT (COALESCE(m.score, 0) >= 0.8
                   AND COALESCE(m.attempts, 0) >= 3)
               ORDER BY t.seq""", (student_id, track),
        ).fetchall()
        for row in rows:
            blocked = connection.execute(
                """SELECT 1 FROM topic_prereqs p
                   LEFT JOIN mastery m ON m.topic_id = p.prereq_id AND m.student_id = ?
                   WHERE p.topic_id = ? AND COALESCE(m.score, 0) < 0.8 LIMIT 1""",
                (student_id, row["id"]),
            ).fetchone()
            if not blocked:
                return dict(row)
        return None
    finally:
        if owns_connection:
            connection.close()


def prerequisite_names(db, topic_id):
    connection, owns_connection = _connection(db)
    try:
        return [row[0] for row in connection.execute(
            """SELECT p.name_he FROM topic_prereqs r
               JOIN topics p ON p.id = r.prereq_id
               WHERE r.topic_id = ? ORDER BY p.seq""", (topic_id,)
        ).fetchall()]
    finally:
        if owns_connection:
            connection.close()


def content_items(db, track, limit):
    connection, owns_connection = _connection(db)
    try:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT i.* FROM items i JOIN topics t ON t.id = i.topic_id
               WHERE t.track = ? ORDER BY t.seq, i.id LIMIT ?""",
            (track, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        if owns_connection:
            connection.close()
