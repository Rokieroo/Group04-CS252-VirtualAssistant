-- Canonical portable schema through migration 0010.

CREATE TABLE IF NOT EXISTS users (
    id                     TEXT PRIMARY KEY,
    email                  TEXT UNIQUE NOT NULL,
    password_hash          TEXT NOT NULL,
    role                   TEXT NOT NULL DEFAULT 'student',
    account_level          TEXT NOT NULL DEFAULT 'university',
    birth_year             INTEGER,
    companion_mode         TEXT NOT NULL DEFAULT 'buddy',
    adult_verified         INTEGER NOT NULL DEFAULT 0,
    failed_login_attempts  INTEGER NOT NULL DEFAULT 0,
    locked_until           TEXT,
    created_at             TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    name                   VARCHAR(80) NOT NULL DEFAULT '',
    timezone               VARCHAR(64) NOT NULL DEFAULT 'Asia/Ho_Chi_Minh',
    personality            VARCHAR(16) NOT NULL DEFAULT 'warm'
);

CREATE TABLE IF NOT EXISTS search_cache (
    signature   VARCHAR(64) PRIMARY KEY,
    payload     TEXT NOT NULL,
    expires_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS institutions (
    id           VARCHAR(36) PRIMARY KEY,
    ror_id       TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL,
    name_vi      TEXT,
    country      TEXT NOT NULL,
    domain       TEXT NOT NULL,
    tier         INTEGER NOT NULL DEFAULT 3 CHECK (tier BETWEEN 1 AND 3),
    rank_signal  TEXT
);

CREATE TABLE IF NOT EXISTS subjects (
    id         VARCHAR(36) PRIMARY KEY,
    parent_id  VARCHAR(36) REFERENCES subjects(id),
    slug       TEXT NOT NULL UNIQUE,
    name       TEXT NOT NULL,
    name_vi    TEXT
);

CREATE TABLE IF NOT EXISTS alembic_version (
    version_num VARCHAR(32) NOT NULL PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS courses (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'university',
    language    TEXT NOT NULL DEFAULT 'vi',
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companion_events (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,
    payload     TEXT,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  VARCHAR(64) PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS goals (
    id           VARCHAR(36) PRIMARY KEY,
    created_at   TIMESTAMP NOT NULL,
    owner_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        VARCHAR(200) NOT NULL,
    description  TEXT NOT NULL,
    due_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teams (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    owner_id    TEXT NOT NULL REFERENCES users(id),
    name        VARCHAR(100) NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id          VARCHAR(36) PRIMARY KEY,
    kind        TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}',
    status      VARCHAR(16) NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts    INTEGER NOT NULL DEFAULT 0,
    run_after   TIMESTAMP NOT NULL,
    locked_at   TIMESTAMP,
    dedupe_key  TEXT,
    user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,
    result      TEXT,
    error       TEXT,
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_courses (
    id              VARCHAR(36) PRIMARY KEY,
    institution_id  VARCHAR(36) REFERENCES institutions(id) ON DELETE SET NULL,
    provider        TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    code            TEXT,
    title           TEXT NOT NULL,
    level           TEXT NOT NULL CHECK (level IN ('k12', 'undergrad', 'grad')),
    grade           INTEGER CHECK (grade BETWEEN 1 AND 12),
    language        TEXT NOT NULL,
    license         TEXT,
    url             TEXT NOT NULL,
    year            INTEGER,
    UNIQUE (provider, external_id)
);

CREATE TABLE IF NOT EXISTS availability (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starts_at   TIMESTAMP NOT NULL,
    ends_at     TIMESTAMP NOT NULL,
    CHECK (ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS busy_blocks (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    starts_at   TIMESTAMP NOT NULL,
    ends_at     TIMESTAMP NOT NULL,
    title       VARCHAR(200) NOT NULL,
    CHECK (ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        VARCHAR(16) NOT NULL,
    content     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id          TEXT PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    file_name   TEXT NOT NULL,
    page        INTEGER NOT NULL CHECK (page >= 1),
    text        TEXT NOT NULL,
    visual_notes TEXT,
    kind        TEXT NOT NULL DEFAULT 'material',
    UNIQUE (course_id, file_name, page)
);

CREATE TABLE IF NOT EXISTS concepts (
    id           TEXT PRIMARY KEY,
    course_id    TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    slug         TEXT NOT NULL,
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    bloom_level  TEXT NOT NULL DEFAULT 'understand',
    source_pages TEXT,
    source_refs  TEXT NOT NULL DEFAULT '[]',
    confirmed    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (course_id, slug)
);

CREATE TABLE IF NOT EXISTS memberships (
    team_id  VARCHAR(36) NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id  TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (team_id, user_id)
);

CREATE TABLE IF NOT EXISTS invitations (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    team_id     VARCHAR(36) NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    email       VARCHAR(254) NOT NULL,
    token_hash  VARCHAR(64) NOT NULL,
    accepted    BOOLEAN NOT NULL,
    UNIQUE (team_id, email)
);

CREATE TABLE IF NOT EXISTS syllabi (
    id          VARCHAR(36) PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    raw_text    TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS roadmaps (
    id          VARCHAR(36) PRIMARY KEY,
    course_id   TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS resources (
	id VARCHAR(36) NOT NULL,
	url TEXT NOT NULL,
	title TEXT NOT NULL,
	provider TEXT DEFAULT 'web' NOT NULL,
	kind TEXT DEFAULT 'article' NOT NULL,
	lang TEXT DEFAULT 'vi' NOT NULL,
	last_checked_at TIMESTAMP,
	http_status INTEGER,
	failed_checks INTEGER DEFAULT '0' NOT NULL,
	catalog_course_id VARCHAR(36),
	canonical_url TEXT NOT NULL,
	domain TEXT,
	format TEXT,
	license TEXT,
	is_free BOOLEAN,
	duration_min INTEGER CHECK (duration_min >= 0),
	content_hash VARCHAR(64),
	source_connector TEXT,
	ingested_at TIMESTAMP,
	verification_status VARCHAR(16) DEFAULT 'pending' NOT NULL CHECK (verification_status IN ('pending', 'verified', 'rejected', 'stale')),
	PRIMARY KEY (id),
	FOREIGN KEY(catalog_course_id) REFERENCES catalog_courses (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS prereqs (
    parent_id   TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    child_id    TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'strict',
    confidence  REAL NOT NULL DEFAULT 1.0,
    PRIMARY KEY (parent_id, child_id)
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

CREATE TABLE IF NOT EXISTS roadmap_nodes (
	id VARCHAR(36) NOT NULL,
	roadmap_id VARCHAR(36) NOT NULL,
	type TEXT NOT NULL,
	title TEXT NOT NULL,
	week INTEGER,
	duration_minutes INTEGER,
	due_at TIMESTAMP,
	covers TEXT,
	concept_id TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(roadmap_id) REFERENCES roadmaps (id) ON DELETE CASCADE,
	FOREIGN KEY(concept_id) REFERENCES concepts (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS resource_feedback (
    id           VARCHAR(36) PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resource_id  VARCHAR(36) NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    rating       INTEGER NOT NULL,
    comment      TEXT
);

CREATE TABLE IF NOT EXISTS catalog_units (
    id           VARCHAR(36) PRIMARY KEY,
    course_id    VARCHAR(36) NOT NULL REFERENCES catalog_courses(id) ON DELETE CASCADE,
    position     INTEGER NOT NULL CHECK (position >= 1),
    title        TEXT NOT NULL,
    resource_id  VARCHAR(36) REFERENCES resources(id) ON DELETE SET NULL,
    UNIQUE (course_id, position)
);

CREATE TABLE IF NOT EXISTS resource_subjects (
    resource_id  VARCHAR(36) NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    subject_id   VARCHAR(36) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    confidence   REAL NOT NULL DEFAULT 1 CHECK (confidence >= 0 AND confidence <= 1),
    method       TEXT NOT NULL,
    PRIMARY KEY (resource_id, subject_id)
);

CREATE TABLE IF NOT EXISTS resource_verifications (
    id           VARCHAR(36) PRIMARY KEY,
    resource_id  VARCHAR(36) NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    check_name   TEXT NOT NULL,
    result       TEXT NOT NULL,
    details      TEXT,
    checked_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    checked_by   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exercises (
	id VARCHAR(36) NOT NULL,
	origin TEXT NOT NULL,
	resource_id VARCHAR(36),
	source_id TEXT,
	page INTEGER,
	quote_hash TEXT NOT NULL,
	source_hash TEXT NOT NULL,
	owner_id TEXT,
	type TEXT NOT NULL,
	prompt TEXT,
	choices TEXT,
	answer TEXT,
	solution_ref TEXT,
	location TEXT,
	difficulty INTEGER NOT NULL,
	bloom_level TEXT NOT NULL,
	license TEXT NOT NULL,
	verification_status TEXT NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_exercise_origin CHECK (origin IN ('catalog','user_material')),
	CONSTRAINT ck_exercise_difficulty CHECK (difficulty BETWEEN 1 AND 5),
	CONSTRAINT ck_exercise_type CHECK (type IN ('mcq','numeric','short','proof','code')),
	CONSTRAINT ck_exercise_source CHECK ((origin = 'catalog' AND resource_id IS NOT NULL AND source_id IS NULL AND owner_id IS NULL) OR (origin = 'user_material' AND source_id IS NOT NULL AND resource_id IS NULL AND owner_id IS NOT NULL AND page IS NOT NULL AND page >= 1)),
	CONSTRAINT ck_exercise_content CHECK (prompt IS NOT NULL OR location IS NOT NULL),
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE,
	FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE,
	FOREIGN KEY(owner_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS items (
    id          TEXT PRIMARY KEY,
    exercise_id VARCHAR(36) REFERENCES exercises(id) ON DELETE CASCADE,
    concept_id  TEXT NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    source_id   TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    prompt      TEXT NOT NULL,
    choices     TEXT,
    answer      TEXT NOT NULL,
    rubric      TEXT,
    graded      INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'draft'
);

CREATE TABLE IF NOT EXISTS node_resources (
    node_id          VARCHAR(36) NOT NULL REFERENCES roadmap_nodes(id) ON DELETE CASCADE,
    resource_id      VARCHAR(36) NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    relevance_score  REAL NOT NULL DEFAULT 0,
    status           TEXT NOT NULL DEFAULT 'shown',
    PRIMARY KEY (node_id, resource_id)
);

CREATE TABLE IF NOT EXISTS resource_searches (
    id               VARCHAR(36) PRIMARY KEY,
    node_id          VARCHAR(36) REFERENCES roadmap_nodes(id) ON DELETE SET NULL,
    user_id          TEXT REFERENCES users(id) ON DELETE CASCADE,
    node_title       TEXT NOT NULL,
    status           TEXT NOT NULL,
    cache_hit        INTEGER NOT NULL DEFAULT 0,
    queries          INTEGER NOT NULL DEFAULT 0,
    candidates       INTEGER NOT NULL DEFAULT 0,
    vetted           INTEGER NOT NULL DEFAULT 0,
    kept             INTEGER NOT NULL DEFAULT 0,
    llm_calls        INTEGER NOT NULL DEFAULT 0,
    llm_cost_usd     REAL NOT NULL DEFAULT 0,
    search_cost_usd  REAL NOT NULL DEFAULT 0,
    duration_ms      INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS node_subjects (
    node_id     VARCHAR(36) NOT NULL REFERENCES roadmap_nodes(id) ON DELETE CASCADE,
    subject_id  VARCHAR(36) NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    confidence  REAL NOT NULL DEFAULT 1 CHECK (confidence >= 0 AND confidence <= 1),
    method      TEXT NOT NULL,
    PRIMARY KEY (node_id, subject_id)
);

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
    status             VARCHAR(16) NOT NULL,
    roadmap_node_id    VARCHAR(36) CONSTRAINT fk_tasks_roadmap_node_id REFERENCES roadmap_nodes(id) ON DELETE SET NULL,
    CHECK (completed_minutes >= 0 AND completed_minutes <= duration_minutes)
);

CREATE TABLE IF NOT EXISTS catalog_embeddings (
	id TEXT NOT NULL,
	kind TEXT NOT NULL,
	model TEXT NOT NULL,
	content_hash TEXT NOT NULL,
	vector TEXT NOT NULL,
	node_id VARCHAR(36),
	resource_id VARCHAR(36),
	PRIMARY KEY (id, kind),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS node_source_status (
	node_id VARCHAR(36) NOT NULL,
	status TEXT NOT NULL,
	updated_at TIMESTAMP NOT NULL,
	PRIMARY KEY (node_id),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS roadmap_edges (
	roadmap_id VARCHAR(36) NOT NULL,
	parent_id VARCHAR(36) NOT NULL,
	child_id VARCHAR(36) NOT NULL,
	kind TEXT NOT NULL,
	origin TEXT NOT NULL,
	confidence FLOAT NOT NULL,
	reason VARCHAR(300) DEFAULT '' NOT NULL,
	created_by TEXT,
	created_at TIMESTAMP NOT NULL,
	PRIMARY KEY (parent_id, child_id),
	CONSTRAINT ck_roadmap_edge_self CHECK (parent_id <> child_id),
	CONSTRAINT ck_roadmap_edge_kind CHECK (kind IN ('soft','strict')),
	CONSTRAINT ck_roadmap_edge_origin CHECK (origin IN ('week_order','llm','user')),
	CONSTRAINT ck_roadmap_edge_confidence CHECK (confidence BETWEEN 0 AND 1),
	CONSTRAINT ck_roadmap_edge_reason CHECK (length(reason) <= 300),
	FOREIGN KEY(roadmap_id) REFERENCES roadmaps (id) ON DELETE CASCADE,
	FOREIGN KEY(parent_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(child_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(created_by) REFERENCES users (id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS graph_layouts (
	user_id TEXT NOT NULL,
	node_id VARCHAR(36) NOT NULL,
	x FLOAT NOT NULL,
	y FLOAT NOT NULL,
	pinned BOOLEAN NOT NULL,
	updated_at TIMESTAMP NOT NULL,
	PRIMARY KEY (user_id, node_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS node_materials (
	node_id VARCHAR(36) NOT NULL,
	source_id TEXT NOT NULL,
	confidence FLOAT NOT NULL,
	method TEXT DEFAULT 'manual' NOT NULL,
	PRIMARY KEY (node_id, source_id),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS source_subjects (
	source_id TEXT NOT NULL,
	subject_id TEXT NOT NULL,
	confidence FLOAT NOT NULL,
	PRIMARY KEY (source_id, subject_id),
	FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE,
	FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exercise_subjects (
	exercise_id VARCHAR(36) NOT NULL,
	subject_id TEXT NOT NULL,
	PRIMARY KEY (exercise_id, subject_id),
	FOREIGN KEY(exercise_id) REFERENCES exercises (id) ON DELETE CASCADE,
	FOREIGN KEY(subject_id) REFERENCES subjects (id)
);

CREATE TABLE IF NOT EXISTS node_exercises (
	node_id VARCHAR(36) NOT NULL,
	exercise_id VARCHAR(36) NOT NULL,
	role TEXT NOT NULL,
	PRIMARY KEY (node_id, exercise_id, role),
	CONSTRAINT ck_node_exercise_role CHECK (role IN ('practice','checkpoint')),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(exercise_id) REFERENCES exercises (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cards (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    fsrs_state  TEXT NOT NULL,
    due_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, item_id)
);

CREATE TABLE IF NOT EXISTS reviews (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id      TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    rating       INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 4),
    answer_text  TEXT,
    hints_used   INTEGER NOT NULL DEFAULT 0,
    score        REAL,
    reviewed_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS search_runs (
    id             VARCHAR(36) PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    query          TEXT NOT NULL,
    provider       TEXT NOT NULL DEFAULT 'web',
    status         TEXT NOT NULL DEFAULT 'pending',
    results_count  INTEGER NOT NULL DEFAULT 0,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    search_id      VARCHAR(36) REFERENCES resource_searches(id) ON DELETE CASCADE,
    latency_ms     INTEGER NOT NULL DEFAULT 0,
    cost_usd       REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS schedule_entries (
    id              VARCHAR(36) PRIMARY KEY,
    created_at      TIMESTAMP NOT NULL,
    user_id         TEXT NOT NULL REFERENCES users(id),
    task_id         VARCHAR(36) NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    starts_at       TIMESTAMP NOT NULL,
    ends_at         TIMESTAMP NOT NULL,
    status          VARCHAR(16) NOT NULL,
    actual_minutes  INTEGER NOT NULL,
    CHECK (ends_at > starts_at)
);

CREATE TABLE IF NOT EXISTS notifications (
    id          VARCHAR(36) PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entry_id    VARCHAR(36) UNIQUE REFERENCES schedule_entries(id) ON DELETE CASCADE,
    message     VARCHAR(500) NOT NULL,
    read        BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS external_results (
    query_hash VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    payload TEXT NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (query_hash, provider)
);

CREATE TABLE IF NOT EXISTS recommendations (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    node_id VARCHAR(36) NOT NULL REFERENCES roadmap_nodes(id) ON DELETE CASCADE,
    resource_ref TEXT NOT NULL,
    kind VARCHAR(32) NOT NULL,
    rank INTEGER NOT NULL DEFAULT 1,
    score REAL NOT NULL DEFAULT 0.0,
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    dismissed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recommendation_events (
    id VARCHAR(36) PRIMARY KEY,
    recommendation_id VARCHAR(36) NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    event VARCHAR(32) NOT NULL CHECK (event IN ('shown', 'opened', 'helpful', 'not_helpful', 'pinned')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cards_user_due ON cards (user_id, due_at);

CREATE INDEX IF NOT EXISTS idx_reviews_user ON reviews (user_id, reviewed_at);

CREATE INDEX IF NOT EXISTS ix_auth_sessions_user_id ON auth_sessions (user_id);

CREATE INDEX IF NOT EXISTS ix_goals_owner_id ON goals (owner_id);

CREATE INDEX IF NOT EXISTS ix_teams_owner_id ON teams (owner_id);

CREATE INDEX IF NOT EXISTS ix_invitations_team_id ON invitations (team_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_resources_canonical_url ON resources (canonical_url);

CREATE INDEX IF NOT EXISTS ix_resources_verification_status ON resources (verification_status);

CREATE INDEX IF NOT EXISTS ix_resources_domain ON resources (domain);

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

CREATE INDEX IF NOT EXISTS ix_search_runs_search_id ON search_runs (search_id);

CREATE INDEX IF NOT EXISTS ix_search_runs_created_at ON search_runs (created_at);

CREATE INDEX IF NOT EXISTS ix_resource_searches_node_id ON resource_searches (node_id);

CREATE INDEX IF NOT EXISTS ix_resource_searches_user_id ON resource_searches (user_id);

CREATE INDEX IF NOT EXISTS ix_resource_searches_created_at ON resource_searches (created_at);

CREATE INDEX IF NOT EXISTS ix_jobs_status_run_after ON jobs (status, run_after);

CREATE UNIQUE INDEX IF NOT EXISTS ux_jobs_dedupe_key ON jobs (dedupe_key);

CREATE INDEX IF NOT EXISTS ix_jobs_user_id ON jobs (user_id);

CREATE INDEX IF NOT EXISTS ix_search_cache_expires_at ON search_cache (expires_at);

CREATE INDEX IF NOT EXISTS ix_catalog_courses_institution_id ON catalog_courses (institution_id);

CREATE INDEX IF NOT EXISTS ix_catalog_units_resource_id ON catalog_units (resource_id);

CREATE INDEX IF NOT EXISTS ix_resource_subjects_subject_id ON resource_subjects (subject_id);

CREATE INDEX IF NOT EXISTS ix_node_subjects_subject_id ON node_subjects (subject_id);

CREATE INDEX IF NOT EXISTS ix_resource_verifications_resource_id_checked_at
    ON resource_verifications (resource_id, checked_at);

CREATE INDEX IF NOT EXISTS ix_tasks_owner_id ON tasks (owner_id);

CREATE INDEX IF NOT EXISTS ix_tasks_assignee_id ON tasks (assignee_id);

CREATE INDEX IF NOT EXISTS ix_tasks_team_id ON tasks (team_id);

CREATE INDEX IF NOT EXISTS ix_tasks_roadmap_node_id ON tasks (roadmap_node_id);

CREATE INDEX IF NOT EXISTS ix_tasks_assignee_status_due ON tasks (assignee_id, status, due_at);

CREATE INDEX IF NOT EXISTS ix_availability_user_id ON availability (user_id);

CREATE INDEX IF NOT EXISTS ix_busy_blocks_user_id ON busy_blocks (user_id);

CREATE INDEX IF NOT EXISTS ix_schedule_entries_user_id ON schedule_entries (user_id);

CREATE INDEX IF NOT EXISTS ix_schedule_entries_task_id ON schedule_entries (task_id);

CREATE INDEX IF NOT EXISTS ix_schedule_user_status_start ON schedule_entries (user_id, status, starts_at);

CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications (user_id);

CREATE INDEX IF NOT EXISTS ix_chat_messages_user_id ON chat_messages (user_id);

CREATE INDEX IF NOT EXISTS ix_recommendations_user_id ON recommendations (user_id);

CREATE INDEX IF NOT EXISTS ix_recommendations_node_id ON recommendations (node_id);

CREATE INDEX IF NOT EXISTS ix_recommendations_user_node ON recommendations (user_id, node_id);

CREATE INDEX IF NOT EXISTS ix_recommendation_events_recommendation_id ON recommendation_events (recommendation_id);

CREATE INDEX IF NOT EXISTS ix_external_results_fetched_at ON external_results (fetched_at);

INSERT INTO alembic_version (version_num)
SELECT '0014_recommendations'
WHERE NOT EXISTS (SELECT 1 FROM alembic_version);

CREATE INDEX IF NOT EXISTS ix_roadmap_edges_roadmap_id ON roadmap_edges (roadmap_id);

CREATE INDEX IF NOT EXISTS ix_exercises_owner_id ON exercises (owner_id);
