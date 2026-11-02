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
    created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Scheduling workspace profile (migration 0002).
    name                   VARCHAR(80) NOT NULL DEFAULT '',
    timezone               VARCHAR(64) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    personality            VARCHAR(16) NOT NULL DEFAULT 'warm'  -- warm | direct | playful
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
    visual_notes TEXT,                                           -- vision model's notes on diagrams/images; never cited
    kind        TEXT NOT NULL DEFAULT 'material',                -- syllabus | material
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

-- ---------------------------------------------------------------------------
-- Scheduling workspace and companion (migration 0002_scheduling_workspace).
-- Timestamps are naive UTC; the backend converts at its boundary.
-- ---------------------------------------------------------------------------

-- Revocable bearer sessions; only the SHA-256 of the token is stored.
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  VARCHAR(64) PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE TABLE IF NOT EXISTS goals (
    id           VARCHAR(36) PRIMARY KEY,
    created_at   TIMESTAMP NOT NULL,
    owner_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        VARCHAR(200) NOT NULL,
    description  TEXT NOT NULL,
    due_at       TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_goals_owner_id ON goals (owner_id);

CREATE TABLE IF NOT EXISTS teams (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    owner_id    TEXT NOT NULL REFERENCES users(id),
    name        VARCHAR(100) NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_teams_owner_id ON teams (owner_id);

CREATE TABLE IF NOT EXISTS memberships (
    team_id  VARCHAR(36) NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, user_id)
);

-- Joining needs the matching email AND the out-of-band code (token_hash).
CREATE TABLE IF NOT EXISTS invitations (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    team_id     VARCHAR(36) NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    email       VARCHAR(254) NOT NULL,
    token_hash  VARCHAR(64) NOT NULL,
    accepted    BOOLEAN NOT NULL,
    UNIQUE (team_id, email)
);
CREATE INDEX IF NOT EXISTS ix_invitations_team_id ON invitations (team_id);

-- ---------------------------------------------------------------------------
-- Core loop: syllabus -> roadmap -> scheduled tasks (migration 0005_core_loop).
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS syllabi (
    id          VARCHAR(36) PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    raw_text    TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS learning_outcomes (
    id           VARCHAR(36) PRIMARY KEY,
    syllabus_id  VARCHAR(36) NOT NULL REFERENCES syllabi(id) ON DELETE CASCADE,
    code         TEXT NOT NULL,
    description  TEXT NOT NULL,
    bloom_level  TEXT NOT NULL DEFAULT 'understand'
);

CREATE TABLE IF NOT EXISTS assessments (
    id          VARCHAR(36) PRIMARY KEY,
    syllabus_id  VARCHAR(36) NOT NULL REFERENCES syllabi(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 0,
    due_week    INTEGER
);

CREATE TABLE IF NOT EXISTS roadmaps (
    id          VARCHAR(36) PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roadmap_nodes (
    id                VARCHAR(36) PRIMARY KEY,
    roadmap_id        VARCHAR(36) NOT NULL REFERENCES roadmaps(id) ON DELETE CASCADE,
    type              TEXT NOT NULL,                            -- topic | milestone
    title             TEXT NOT NULL,
    week              INTEGER,
    duration_minutes  INTEGER,
    due_at            TIMESTAMP,
    covers            TEXT                                      -- JSON array of covered node ids
);

CREATE TABLE IF NOT EXISTS resources (
    id        VARCHAR(36) PRIMARY KEY,
    url       TEXT NOT NULL,
    title     TEXT NOT NULL,
    provider  TEXT NOT NULL DEFAULT 'web',                      -- catalog | youtube | web
    kind      TEXT NOT NULL DEFAULT 'article',                  -- video | article | slide
    lang      TEXT NOT NULL DEFAULT 'vi'
);

CREATE TABLE IF NOT EXISTS node_resources (
    node_id          VARCHAR(36) NOT NULL REFERENCES roadmap_nodes(id) ON DELETE CASCADE,
    resource_id      VARCHAR(36) NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    relevance_score  REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (node_id, resource_id)
);

CREATE TABLE IF NOT EXISTS resource_feedback (
    id           VARCHAR(36) PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resource_id  VARCHAR(36) NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    rating       INTEGER NOT NULL,
    comment      TEXT
);

CREATE TABLE IF NOT EXISTS search_runs (
    id             VARCHAR(36) PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query          TEXT NOT NULL,
    provider       TEXT NOT NULL DEFAULT 'web',
    status         TEXT NOT NULL DEFAULT 'pending',
    results_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_syllabi_course_id ON syllabi (course_id);
CREATE INDEX IF NOT EXISTS ix_learning_outcomes_syllabus_id ON learning_outcomes (syllabus_id);
CREATE INDEX IF NOT EXISTS ix_assessments_syllabus_id ON assessments (syllabus_id);
CREATE INDEX IF NOT EXISTS ix_roadmaps_course_id ON roadmaps (course_id);
CREATE INDEX IF NOT EXISTS ix_roadmaps_user_id ON roadmaps (user_id);
CREATE INDEX IF NOT EXISTS ix_roadmap_nodes_roadmap_id ON roadmap_nodes (roadmap_id);
CREATE INDEX IF NOT EXISTS ix_node_resources_resource_id ON node_resources (resource_id);
CREATE INDEX IF NOT EXISTS ix_resource_feedback_user_id ON resource_feedback (user_id);
CREATE INDEX IF NOT EXISTS ix_resource_feedback_resource_id ON resource_feedback (resource_id);
CREATE INDEX IF NOT EXISTS ix_search_runs_user_id ON search_runs (user_id);

CREATE TABLE IF NOT EXISTS tasks (
    id                 VARCHAR(36) PRIMARY KEY,
    created_at         TIMESTAMP NOT NULL,
    owner_id           TEXT NOT NULL REFERENCES users(id),
    assignee_id        TEXT NOT NULL REFERENCES users(id),
    goal_id            VARCHAR(36) REFERENCES goals(id) ON DELETE SET NULL,
    team_id            VARCHAR(36) REFERENCES teams(id),
    title              VARCHAR(200) NOT NULL,
    description        TEXT NOT NULL,
    duration_minutes   INTEGER NOT NULL CHECK (duration_minutes > 0),
    completed_minutes  INTEGER NOT NULL,
    priority           INTEGER NOT NULL CHECK (priority BETWEEN 1 AND 3),
    due_at             TIMESTAMP NOT NULL,
    status             VARCHAR(16) NOT NULL,                     -- pending | completed | cancelled
    roadmap_node_id    VARCHAR(36) CONSTRAINT fk_tasks_roadmap_node_id REFERENCES roadmap_nodes(id) ON DELETE SET NULL,
    CHECK (completed_minutes >= 0 AND completed_minutes <= duration_minutes)
);
CREATE INDEX IF NOT EXISTS ix_tasks_owner_id ON tasks (owner_id);
CREATE INDEX IF NOT EXISTS ix_tasks_assignee_id ON tasks (assignee_id);
CREATE INDEX IF NOT EXISTS ix_tasks_team_id ON tasks (team_id);
CREATE INDEX IF NOT EXISTS ix_tasks_roadmap_node_id ON tasks (roadmap_node_id);
CREATE INDEX IF NOT EXISTS ix_tasks_assignee_status_due ON tasks (assignee_id, status, due_at);

CREATE TABLE IF NOT EXISTS availability (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starts_at   TIMESTAMP NOT NULL,
    ends_at     TIMESTAMP NOT NULL,
    CHECK (ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS ix_availability_user_id ON availability (user_id);

CREATE TABLE IF NOT EXISTS busy_blocks (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starts_at   TIMESTAMP NOT NULL,
    ends_at     TIMESTAMP NOT NULL,
    title       VARCHAR(200) NOT NULL,
    CHECK (ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS ix_busy_blocks_user_id ON busy_blocks (user_id);

CREATE TABLE IF NOT EXISTS schedule_entries (
    id              VARCHAR(36) PRIMARY KEY,
    created_at      TIMESTAMP NOT NULL,
    user_id         TEXT NOT NULL REFERENCES users(id),
    task_id         VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    starts_at       TIMESTAMP NOT NULL,
    ends_at         TIMESTAMP NOT NULL,
    status          VARCHAR(16) NOT NULL,                        -- planned | completed | missed
    actual_minutes  INTEGER NOT NULL,
    CHECK (ends_at > starts_at)
);
CREATE INDEX IF NOT EXISTS ix_schedule_entries_user_id ON schedule_entries (user_id);
CREATE INDEX IF NOT EXISTS ix_schedule_entries_task_id ON schedule_entries (task_id);
CREATE INDEX IF NOT EXISTS ix_schedule_user_status_start ON schedule_entries (user_id, status, starts_at);

-- created_at is when the notification becomes visible (reminders: 15 min before).
CREATE TABLE IF NOT EXISTS notifications (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_id    VARCHAR(36) UNIQUE REFERENCES schedule_entries(id) ON DELETE CASCADE,
    message     VARCHAR(500) NOT NULL,
    read        BOOLEAN NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(16) NOT NULL,                            -- user | assistant
    content     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chat_messages_user_id ON chat_messages (user_id);

-- Mark this schema as the latest migration so `alembic upgrade head` (and the
-- backend at startup) accept a database created from this file.
CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);
INSERT INTO alembic_version (version_num)
SELECT '0005_core_loop'
WHERE NOT EXISTS (SELECT 1 FROM alembic_version);
