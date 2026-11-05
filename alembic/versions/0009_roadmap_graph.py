"""Frozen portable DDL; generated once, independent of future ORM changes."""

import sqlalchemy as sa

from alembic import op

revision = "0009_roadmap_graph"
down_revision = "0008_verified_catalog"
branch_labels = None
depends_on = None

TABLES = [
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
    """CREATE TABLE node_source_status (
	node_id VARCHAR(36) NOT NULL,
	status TEXT NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (node_id),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE
)""",
    """CREATE TABLE roadmap_edges (
	roadmap_id VARCHAR(36) NOT NULL,
	parent_id VARCHAR(36) NOT NULL,
	child_id VARCHAR(36) NOT NULL,
	kind TEXT NOT NULL,
	origin TEXT NOT NULL,
	confidence DOUBLE NOT NULL,
	reason VARCHAR(300) DEFAULT '' NOT NULL,
	created_by TEXT,
	created_at DATETIME NOT NULL,
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
)""",
    """CREATE TABLE graph_layouts (
	user_id TEXT NOT NULL,
	node_id VARCHAR(36) NOT NULL,
	x DOUBLE NOT NULL,
	y DOUBLE NOT NULL,
	pinned BOOLEAN NOT NULL,
	updated_at DATETIME NOT NULL,
	PRIMARY KEY (user_id, node_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE
)""",
    """CREATE TABLE node_materials (
	node_id VARCHAR(36) NOT NULL,
	source_id TEXT NOT NULL,
	confidence DOUBLE NOT NULL,
	PRIMARY KEY (node_id, source_id),
	FOREIGN KEY(node_id) REFERENCES roadmap_nodes (id) ON DELETE CASCADE,
	FOREIGN KEY(source_id) REFERENCES sources (id) ON DELETE CASCADE
)""",
]
INDEXES = ["CREATE INDEX ix_roadmap_edges_roadmap_id ON roadmap_edges (roadmap_id)"]


def upgrade():
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
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "ALTER TABLE roadmap_nodes ADD COLUMN concept_id TEXT REFERENCES concepts(id) ON DELETE SET NULL"
        )
    else:
        op.add_column(
            "roadmap_nodes",
            sa.Column(
                "concept_id",
                sa.Text(),
                sa.ForeignKey(
                    "concepts.id",
                    name="fk_roadmap_nodes_concept_id",
                    ondelete="SET NULL",
                ),
            ),
        )
    for ddl in TABLES:
        op.execute(ddl)
    for ddl in INDEXES:
        op.execute(ddl)


def downgrade():
    op.drop_column("resources", "catalog_course_id")
    op.drop_column("roadmap_nodes", "concept_id")
    op.drop_table("node_materials")
    op.drop_table("graph_layouts")
    op.drop_table("roadmap_edges")
    op.drop_table("node_source_status")
    op.drop_table("catalog_embeddings")
