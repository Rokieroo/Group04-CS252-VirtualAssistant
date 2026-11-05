"""Frozen portable DDL; generated once, independent of future ORM changes."""

import sqlalchemy as sa

from alembic import op

revision = "0010_quoted_exercises"
down_revision = "0009_roadmap_graph"
branch_labels = None
depends_on = None

TABLES = [
    """CREATE TABLE exercises (
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
)""",
    """CREATE TABLE exercise_subjects (
	exercise_id VARCHAR(36) NOT NULL,
	subject_id TEXT NOT NULL,
	PRIMARY KEY (exercise_id, subject_id),
	FOREIGN KEY(exercise_id) REFERENCES exercises (id) ON DELETE CASCADE,
	FOREIGN KEY(subject_id) REFERENCES subjects (id)
)""",
    """CREATE TABLE node_exercises (
	node_id VARCHAR(36) NOT NULL,
	exercise_id VARCHAR(36) NOT NULL,
	role TEXT NOT NULL,
	PRIMARY KEY (node_id, exercise_id, role),
	CONSTRAINT ck_node_exercise_role CHECK (role IN ('practice','checkpoint')),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(exercise_id) REFERENCES exercises (id) ON DELETE CASCADE
)""",
]
INDEXES = ["CREATE INDEX ix_exercises_owner_id ON exercises (owner_id)"]


def upgrade():
    for ddl in TABLES:
        op.execute(ddl)
    for ddl in INDEXES:
        op.execute(ddl)
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE items ADD COLUMN exercise_id VARCHAR(36) REFERENCES exercises(id) ON DELETE CASCADE"
        )
    else:
        op.add_column(
            "items",
            sa.Column(
                "exercise_id",
                sa.String(36),
                sa.ForeignKey(
                    "exercises.id", name="fk_items_exercise_id", ondelete="CASCADE"
                ),
            ),
        )
    op.execute("UPDATE items SET status = 'rejected' WHERE exercise_id IS NULL")


def downgrade():
    op.drop_column("items", "exercise_id")
    op.drop_table("node_exercises")
    op.drop_table("exercise_subjects")
    op.drop_table("exercises")
