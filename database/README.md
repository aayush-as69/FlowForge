# Database

FlowForge's tables live in the Postgres schema **`flowforge`** and are created/maintained by the Python backend
(`backend/app/models/entities.py`, `Base.metadata.create_all` on start-up). Keeping them in their own schema keeps the application-owned tables isolated from other Postgres objects.

| Table | Entity |
|---|---|
| organizations, users | Organization, User (roles: requester, auditor, approver, manager, admin) |
| business_functions | BusinessFunction (procurement active; others "coming soon") |
| policies | Policy – business rules *and* decision-engine thresholds as data |
| vendors | Vendor – catalog price, historical average, rating, warranty, reliability |
| requests | Request – original text + AI-extracted fields + human corrections |
| workflows, workflow_steps | Workflow, WorkflowStep – persisted state machine (resumable) |
| decisions | Decision – autonomy level, rule trace, actor |
| exceptions | Exception – class, recoverability, resolution trace |
| approvals | Approval – human-in-the-loop requests and outcomes |
| integrations | Integration – connection state, latency, call/failure counters |
| audit_events | AuditEvent – timestamp, actor, action, input, output, result, reason, status |
| purchase_orders | PurchaseOrder |

Inspect: `psql $DATABASE_URL -c '\dt flowforge.*'`. Demo data is seeded automatically on first start
(set `FF_SEED=0` to skip the historical workflows).
