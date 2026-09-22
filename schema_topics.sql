PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS topics (
    id TEXT PRIMARY KEY,
    track TEXT NOT NULL,
    name_he TEXT NOT NULL,
    summary_he TEXT NOT NULL,
    grade_band TEXT NOT NULL,
    seq INTEGER NOT NULL,
    UNIQUE(track, seq)
);

CREATE TABLE IF NOT EXISTS topic_prereqs (
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    prereq_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY(topic_id, prereq_id),
    CHECK(topic_id <> prereq_id)
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('numeric', 'mcq', 'open')),
    difficulty REAL NOT NULL CHECK(difficulty > 0),
    prompt_he TEXT NOT NULL,
    choices_he TEXT,
    answer REAL,
    tolerance REAL,
    unit TEXT,
    rubric_he TEXT,
    explain_he TEXT NOT NULL,
    CHECK(kind <> 'numeric' OR (answer IS NOT NULL AND tolerance IS NOT NULL AND unit IS NOT NULL)),
    CHECK(kind <> 'mcq' OR (answer IS NOT NULL AND choices_he IS NOT NULL)),
    CHECK(kind <> 'open' OR (answer IS NULL AND rubric_he IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS mastery (
    student_id TEXT NOT NULL,
    topic_id TEXT NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    score REAL NOT NULL DEFAULT 0 CHECK(score >= 0 AND score <= 1),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    correct INTEGER NOT NULL DEFAULT 0 CHECK(correct >= 0),
    ease REAL NOT NULL DEFAULT 2.5 CHECK(ease >= 1.3),
    interval_d REAL NOT NULL DEFAULT 0 CHECK(interval_d >= 0),
    last_seen TEXT,
    next_due TEXT,
    PRIMARY KEY(student_id, topic_id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT NOT NULL,
    item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    raw_answer TEXT NOT NULL,
    verdict TEXT NOT NULL CHECK(verdict IN ('correct', 'wrong', 'needs_review')),
    graded_by TEXT NOT NULL,
    ts TEXT NOT NULL
);
