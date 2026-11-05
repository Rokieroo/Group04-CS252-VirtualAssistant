"""Frozen schema declarations; dialect-aware DDL independent of future ORM changes."""

import sqlalchemy as sa

from alembic import op

revision = "0009_roadmap_graph"
down_revision = "0008_verified_catalog"
branch_labels = None
depends_on = None


def _create_tables():
    op.create_table(
        "catalog_embeddings",
        sa.Column("id", sa.Text(), primary_key=True, nullable=False),
        sa.Column("kind", sa.Text(), primary_key=True, nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("vector", sa.Text(), nullable=False),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "resource_id",
            sa.String(36),
            sa.ForeignKey("resources.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_table(
        "node_source_status",
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "roadmap_edges",
        sa.Column(
            "roadmap_id",
            sa.String(36),
            sa.ForeignKey("roadmaps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "parent_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "child_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Double(), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False, server_default=""),
        sa.Column(
            "created_by",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "confidence BETWEEN 0 AND 1", name="ck_roadmap_edge_confidence"
        ),
        sa.CheckConstraint("kind IN ('soft','strict')", name="ck_roadmap_edge_kind"),
        sa.CheckConstraint(
            "origin IN ('week_order','llm','user')", name="ck_roadmap_edge_origin"
        ),
        sa.CheckConstraint("length(reason) <= 300", name="ck_roadmap_edge_reason"),
        sa.CheckConstraint("parent_id <> child_id", name="ck_roadmap_edge_self"),
    )
    op.create_table(
        "graph_layouts",
        sa.Column(
            "user_id",
            sa.Text(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("x", sa.Double(), nullable=False),
        sa.Column("y", sa.Double(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "node_materials",
        sa.Column(
            "node_id",
            sa.String(36),
            sa.ForeignKey("roadmap_nodes.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Text(),
            sa.ForeignKey("sources.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("confidence", sa.Double(), nullable=False),
    )


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
    _create_tables()
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
