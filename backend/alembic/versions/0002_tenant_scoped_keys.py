"""Make policy and integration identifiers tenant-scoped."""
from alembic import op

revision = "0002_tenant_scoped_keys"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

SCHEMA = "flowforge"


def upgrade():
    op.drop_constraint("policies_key_key", "policies", schema=SCHEMA, type_="unique")
    op.create_unique_constraint("uq_policies_org_key", "policies", ["org_id", "key"], schema=SCHEMA)
    op.drop_constraint("integrations_key_key", "integrations", schema=SCHEMA, type_="unique")
    op.create_unique_constraint("uq_integrations_org_key", "integrations", ["org_id", "key"], schema=SCHEMA)


def downgrade():
    op.drop_constraint("uq_policies_org_key", "policies", schema=SCHEMA, type_="unique")
    op.create_unique_constraint("policies_key_key", "policies", ["key"], schema=SCHEMA)
    op.drop_constraint("uq_integrations_org_key", "integrations", schema=SCHEMA, type_="unique")
    op.create_unique_constraint("integrations_key_key", "integrations", ["key"], schema=SCHEMA)
