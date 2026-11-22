"""Baseline schema, compatible with databases initially bootstrapped by SQLAlchemy."""
from alembic import op
from app.core.db import Base, SCHEMA
from app import models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"')
    # create_all is idempotent here and also lets existing deployments adopt Alembic
    # by running this baseline once without dropping or rewriting existing data.
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)


def downgrade():
    # Deliberately non-destructive: the baseline may be stamped onto a live database.
    pass
