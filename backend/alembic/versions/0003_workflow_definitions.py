"""Add user-built, versioned workflow definitions."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0003_workflow_definitions"
down_revision = "0002_tenant_scoped_keys"
branch_labels = None
depends_on = None
SCHEMA = "flowforge"


def upgrade():
    if "workflow_definitions" in inspect(op.get_bind()).get_table_names(schema=SCHEMA):
        return
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("org_id", sa.Integer, sa.ForeignKey(f"{SCHEMA}.organizations.id"), nullable=False, index=True),
        sa.Column("key", sa.String(60), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("spec", sa.JSON, nullable=False),
        sa.Column("tests", sa.JSON, nullable=False),
        sa.Column("template_key", sa.String(60), nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "key", "version", name="uq_workflow_definitions_org_key_version"),
        schema=SCHEMA,
    )


def downgrade():
    if "workflow_definitions" in inspect(op.get_bind()).get_table_names(schema=SCHEMA):
        op.drop_table("workflow_definitions", schema=SCHEMA)
