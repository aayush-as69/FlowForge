"""Make policy and integration identifiers tenant-scoped."""
from alembic import op
from sqlalchemy import inspect

revision = "0002_tenant_scoped_keys"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None
SCHEMA = "flowforge"

def _constraints(table):
    return {item["name"] for item in inspect(op.get_bind()).get_unique_constraints(table, schema=SCHEMA)}

def upgrade():
    existing = _constraints("policies")
    if "policies_key_key" in existing:
        op.drop_constraint("policies_key_key", "policies", schema=SCHEMA, type_="unique")
    if "uq_policies_org_key" not in _constraints("policies"):
        op.create_unique_constraint("uq_policies_org_key", "policies", ["org_id", "key"], schema=SCHEMA)
    existing = _constraints("integrations")
    if "integrations_key_key" in existing:
        op.drop_constraint("integrations_key_key", "integrations", schema=SCHEMA, type_="unique")
    if "uq_integrations_org_key" not in _constraints("integrations"):
        op.create_unique_constraint("uq_integrations_org_key", "integrations", ["org_id", "key"], schema=SCHEMA)

def downgrade():
    existing = _constraints("policies")
    if "uq_policies_org_key" in existing:
        op.drop_constraint("uq_policies_org_key", "policies", schema=SCHEMA, type_="unique")
    if "policies_key_key" not in _constraints("policies"):
        op.create_unique_constraint("policies_key_key", "policies", ["key"], schema=SCHEMA)
    existing = _constraints("integrations")
    if "uq_integrations_org_key" in existing:
        op.drop_constraint("uq_integrations_org_key", "integrations", schema=SCHEMA, type_="unique")
    if "integrations_key_key" not in _constraints("integrations"):
        op.create_unique_constraint("integrations_key_key", "integrations", ["key"], schema=SCHEMA)
