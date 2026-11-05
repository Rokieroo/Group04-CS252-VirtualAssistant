"""Frozen portable DDL; generated once, independent of future ORM changes."""

import sqlalchemy as sa

from alembic import op

revision = "0008_verified_catalog"
down_revision = "0007_search_metrics"
branch_labels = None
depends_on = None

TABLES = [
    """CREATE TABLE institutions (
	id VARCHAR(36) NOT NULL,
	ror_id TEXT NOT NULL,
	name TEXT NOT NULL,
	name_vi TEXT,
	country TEXT NOT NULL,
	domain TEXT NOT NULL,
	tier INTEGER NOT NULL,
	rank_signal TEXT DEFAULT '{}' NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_institutions_tier CHECK (tier BETWEEN 1 AND 3),
	UNIQUE (ror_id)
)""",
    """CREATE TABLE catalog_courses (
	id VARCHAR(36) NOT NULL,
	institution_id VARCHAR(36),
	provider TEXT NOT NULL,
	external_id TEXT NOT NULL,
	code TEXT,
	title TEXT NOT NULL,
	level TEXT DEFAULT 'undergrad' NOT NULL,
	grade INTEGER,
	language TEXT DEFAULT 'en' NOT NULL,
	license TEXT,
	url TEXT NOT NULL,
	year INTEGER,
	PRIMARY KEY (id),
	UNIQUE (provider, external_id),
	FOREIGN KEY(institution_id) REFERENCES institutions (id) ON DELETE SET NULL
)""",
    """CREATE TABLE subjects (
	id TEXT NOT NULL,
	parent_id TEXT,
	name TEXT NOT NULL,
	name_vi TEXT NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(parent_id) REFERENCES subjects (id)
)""",
    """CREATE TABLE resource_subjects (
	resource_id VARCHAR(36) NOT NULL,
	subject_id TEXT NOT NULL,
	confidence DOUBLE NOT NULL,
	method TEXT NOT NULL,
	PRIMARY KEY (resource_id, subject_id),
	CONSTRAINT ck_resource_subject_confidence CHECK (confidence BETWEEN 0 AND 1),
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE,
	FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE CASCADE
)""",
    """CREATE TABLE node_subjects (
	node_id VARCHAR(36) NOT NULL,
	subject_id TEXT NOT NULL,
	confidence DOUBLE NOT NULL,
	method TEXT NOT NULL,
	PRIMARY KEY (node_id, subject_id),
	CONSTRAINT ck_node_subject_confidence CHECK (confidence BETWEEN 0 AND 1),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(subject_id) REFERENCES subjects (id) ON DELETE CASCADE
)""",
    """CREATE TABLE catalog_embeddings (
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
)""",
    """CREATE TABLE resource_verifications (
	id VARCHAR(36) NOT NULL,
	resource_id VARCHAR(36) NOT NULL,
	"check" TEXT NOT NULL,
	result TEXT NOT NULL,
	details TEXT DEFAULT '{}' NOT NULL,
	checked_at DATETIME NOT NULL,
	checked_by TEXT,
	PRIMARY KEY (id),
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE,
	FOREIGN KEY(checked_by) REFERENCES users (id) ON DELETE SET NULL
)""",
    """CREATE TABLE catalog_units (
	id VARCHAR(36) NOT NULL,
	course_id VARCHAR(36) NOT NULL,
	position INTEGER NOT NULL,
	title TEXT NOT NULL,
	resource_id VARCHAR(36) NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(course_id) REFERENCES catalog_courses (id) ON DELETE CASCADE,
	FOREIGN KEY(resource_id) REFERENCES resources (id) ON DELETE CASCADE
)""",
    """CREATE TABLE node_source_status (
	node_id VARCHAR(36) NOT NULL,
	status TEXT NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (node_id),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE
)""",
]
INDEXES = [
    "CREATE INDEX ix_institutions_domain ON institutions (domain)",
    "CREATE INDEX ix_resource_subjects_subject_id ON resource_subjects (subject_id)",
    "CREATE INDEX ix_node_subjects_subject_id ON node_subjects (subject_id)",
    "CREATE INDEX ix_resource_verifications_resource_id ON resource_verifications (resource_id)",
]


def upgrade():
    for ddl in TABLES[:3]:
        op.execute(ddl)
    op.add_column("resources", sa.Column("canonical_url", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("domain", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("format", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("license", sa.Text(), nullable=True))
    op.add_column(
        "resources",
        sa.Column("is_free", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("resources", sa.Column("duration_min", sa.Integer(), nullable=True))
    op.add_column("resources", sa.Column("content_hash", sa.Text(), nullable=True))
    op.add_column(
        "resources",
        sa.Column(
            "verification_status", sa.Text(), nullable=False, server_default="pending"
        ),
    )
    op.add_column("resources", sa.Column("source_connector", sa.Text(), nullable=True))
    op.add_column("resources", sa.Column("ingested_at", sa.DateTime(), nullable=True))
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE resources ADD COLUMN catalog_course_id VARCHAR(36) REFERENCES catalog_courses(id) ON DELETE SET NULL"
        )
    else:
        op.add_column(
            "resources",
            sa.Column(
                "catalog_course_id",
                sa.String(36),
                sa.ForeignKey(
                    "catalog_courses.id",
                    name="fk_resources_catalog_course",
                    ondelete="SET NULL",
                ),
            ),
        )
    op.execute(
        "UPDATE resources SET canonical_url = url WHERE id IN (SELECT MIN(id) FROM resources GROUP BY url)"
    )
    op.create_index(
        "ix_resources_canonical_url", "resources", ["canonical_url"], unique=True
    )
    op.create_index("ix_resources_domain", "resources", ["domain"])
    op.create_index(
        "ix_resources_verification_status", "resources", ["verification_status"]
    )
    for ddl in TABLES[3:]:
        op.execute(ddl)
    for ddl in INDEXES:
        op.execute(ddl)


def downgrade():
    op.drop_table("node_source_status")
    op.drop_table("catalog_units")
    op.drop_table("resource_verifications")
    op.drop_table("catalog_embeddings")
    op.drop_table("node_subjects")
    op.drop_table("resource_subjects")
    op.drop_index("ix_resources_canonical_url", table_name="resources")
    op.drop_index("ix_resources_domain", table_name="resources")
    op.drop_index("ix_resources_verification_status", table_name="resources")
    op.drop_column("resources", "catalog_course_id")
    op.drop_column("resources", "ingested_at")
    op.drop_column("resources", "source_connector")
    op.drop_column("resources", "verification_status")
    op.drop_column("resources", "content_hash")
    op.drop_column("resources", "duration_min")
    op.drop_column("resources", "is_free")
    op.drop_column("resources", "license")
    op.drop_column("resources", "format")
    op.drop_column("resources", "domain")
    op.drop_column("resources", "canonical_url")
    op.drop_table("subjects")
    op.drop_table("catalog_courses")
    op.drop_table("institutions")
