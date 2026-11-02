-- Canonical data model for the Study Companion (spec section 7).
-- Portable SQL: SQLite for local development/tests, PostgreSQL 16 for staging/production.
--
-- SQLite does not enforce foreign keys unless PRAGMA foreign_keys = ON is set on the
-- connection. The app and the dev CLI enable it in src/app/db.py before running this
-- file. PostgreSQL enforces foreign keys by default.

CREATE TABLE IF NOT EXISTS users (
    id                     TEXT PRIMARY KEY,
    email                  TEXT UNIQUE NOT NULL,
    password_hash          TEXT NOT NULL,
    role                   TEXT NOT NULL DEFAULT 'student',      -- student | teacher | parent | admin
    account_level          TEXT NOT NULL DEFAULT 'university',   -- university | k12
    birth_year             INTEGER,
    companion_mode         TEXT NOT NULL DEFAULT 'buddy',        -- off | buddy | mentor | girlfriend (18+ only)
    adult_verified         INTEGER NOT NULL DEFAULT 0,
    failed_login_attempts  INTEGER NOT NULL DEFAULT 0,
    locked_until           TEXT,
    created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS courses (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'university',              -- university | k12
    language    TEXT NOT NULL DEFAULT 'vi',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per page of an uploaded file: the unit every citation points to.
CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    file_name   TEXT NOT NULL,
    page        INTEGER NOT NULL CHECK (page >= 1),
    text        TEXT NOT NULL,
    UNIQUE (course_id, file_name, page)
);

CREATE TABLE IF NOT EXISTS concepts (
    id           TEXT PRIMARY KEY,
    course_id    TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    slug         TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    bloom_level  TEXT NOT NULL DEFAULT 'understand',             -- remember | understand | apply | analyze | evaluate | create
    source_pages TEXT,                                           -- JSON array of page numbers
    source_ids   TEXT NOT NULL DEFAULT '[]',                      -- JSON source IDs preserve file/page provenance
    confirmed    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (course_id, slug)
);

CREATE TABLE IF NOT EXISTS prereqs (
    parent_id   TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    child_id    TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'strict',                  -- strict | soft
    confidence  REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (parent_id, child_id)
);

CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    concept_id  TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    source_id   TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,  -- cite-or-refuse: no item without a citation
    type        TEXT NOT NULL,                                   -- mcq | numeric | short | spot_bug
    prompt      TEXT NOT NULL,
    choices     TEXT,                                            -- JSON array for MCQ
    answer      TEXT NOT NULL,
    rubric      TEXT,
    graded      INTEGER NOT NULL DEFAULT 0,                      -- 1 = hint-only, never reveal the answer
    status      TEXT NOT NULL DEFAULT 'draft'                    -- draft | approved | rejected
);

-- Mastery is per user, never stored on a shared concept.
CREATE TABLE IF NOT EXISTS cards (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    fsrs_state  TEXT NOT NULL,                                   -- JSON from the fsrs package
    due_at      TEXT NOT NULL,                                   -- ISO-8601 UTC
    PRIMARY KEY (user_id, item_id)
);

CREATE INDEX IF NOT EXISTS idx_cards_user_due ON cards (user_id, due_at);

-- Append-only: the scheduler, gap repair, companion and every metric read from here.
CREATE TABLE IF NOT EXISTS reviews (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id      TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),  -- 1 again | 2 hard | 3 good | 4 easy
    answer_text  TEXT,
    hints_used   INTEGER NOT NULL DEFAULT 0,
    score        REAL,
    reviewed_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companion_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,                                   -- session_done | streak | unlock | checkin
    payload     TEXT,                                            -- JSON
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews (user_id, reviewed_at);
