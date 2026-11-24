# FlowForge API

All routes are served by the Python (FastAPI) backend under `/api` (interactive OpenAPI docs at `/api/docs`).
Authentication is a signed, `HttpOnly`, `SameSite=Lax` session cookie (`ff_session`) — or `Authorization: Bearer <jwt>`. Tokens carry unique session IDs; logout revokes the current token in the database, including bearer sessions.
Validation errors return HTTP 422 with an `errors` array.

| Area | Method & path | Permission | Notes |
|---|---|---|---|
| auth | `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` | public / session | bcrypt, persistent login throttling, audited |
| functions | `GET /functions` · `GET /functions/procurement/scenarios` · `POST /functions/procurement/demo` | workflows:read / requests:create | demo runs the workflow engine |
| requests | `POST /requests` · `GET /requests` · `GET/PATCH /requests/{id}` · `POST /requests/{id}/execute` | requests:create | extraction on create; PATCH = human correction; execute → 202 |
| workflows | `GET /workflows` · `GET /workflows/{id}` · `GET /workflows/{id}/steps` · `GET /workflows/{id}/audit` | workflows:read | requesters see only their own |
| | `POST /workflows/{id}/retry` · `POST /workflows/{id}/cancel` | workflows:operate | retry resumes persisted state |
| workflow-steps | `GET /workflow-steps/{id}` | workflows:read | node inspector |
| approvals | `GET /approvals` · `GET /approvals/{id}` · `POST /approvals/{id}/decision` | approvals:read / approvals:decide | approve, reject, modify, escalate; separation of duties enforced |
| exceptions | `GET /exceptions` · `GET /exceptions/summary` · `GET /exceptions/{id}` | exceptions:read | exception review and resolution |
| policies | `GET /policies` · `PATCH /policies/{id}` | policies:read / policies:write | validated, versioned and audited |
| vendors | `GET /vendors` · `PATCH /vendors/{id}` | vendors:read / vendors:write | |
| integrations | `GET /integrations` · `POST /integrations/{key}/check` · `PATCH /integrations/{key}` | integrations:read / integrations:manage | adapters are simulated in this release |
| audit | `GET /audit` · `GET /audit/verify` | audit:read | verify recomputes the hash chain; forks from concurrent writers are reported, not failed |
| dashboard | `GET /dashboard/summary` · `GET /dashboard/observability` | dashboard:read | keep metrics scoped to the authenticated organisation |
| explainability | `GET /workflows/{id}/explanation` · `GET /workflows/{id}/cost` | workflows:read / dashboard:read | explanation is built only from stored facts (no model call); cost is an estimate from the `ROI_*` assumptions |
| action center | `GET /action-center` | workflows:read | approvals, exceptions and failed workflows in one list: overdue (24h+) first, then yours, then oldest |
| analytics | `GET /analytics/overview?days=` | dashboard:read (not requesters) | automation rate, human intervention, durations, approval latency, failure reasons, estimated savings with the assumptions used |
| policy simulator | `POST /policies/simulate` | policies:write | replays recorded workflows (or one what-if purchase) through the real policy and decision engines; writes nothing |
| workflow builder | `GET /builder/templates` · `GET /builder/definitions` · `GET /builder/definitions/{id}` | workflows:read | definitions are data (typed steps), never code |
| | `POST /builder/definitions` · `PUT /builder/definitions/{id}` · `POST …/{id}/new-version` · `POST …/{id}/publish` · `POST …/{id}/archive` | policies:write | drafts are editable; published versions are immutable; publishing requires at least one test case and all passing |
| | `POST /builder/test` · `POST /builder/definitions/{id}/tests/run` | workflows:read | test mode: dry run with no database writes and nobody asked |
| | `POST /builder/definitions/{id}/run` | workflows:operate | starts a published version; the workflow stays pinned to that version; the starter cannot approve it |

## Sign-in throttling

Login attempts are persisted in the database so limits apply across API workers and restarts. Deployments should additionally apply edge-level limits to public and expensive endpoints.

## Demo data

Demo accounts and history are created only when `FF_SEED=1` and an explicit `DEMO_PASSWORD` is supplied. Keep `FF_SEED=0` in production. Production must provision the first organisation and administrator through a controlled bootstrap process; do not enable demo seeding for production identities.

## Request body example

```json
POST /api/requests
{ "source": "text", "text": "I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000." }
```

## Workflow builder step types

`extract` (reads the request into `item`, `category`, `quantity`, `amount`, `purpose`, …) · `rule` (conditions joined by AND; `on_fail` is `approval` to flag the case or `block` to send it to a manager for review) · `approval` (`role` approver/manager/admin, `when` always/flagged) · `notify` (recorded in the audit trail; nothing is sent externally). Steps run in order. A missing value never satisfies a comparison, so an unreadable amount is flagged rather than auto-approved.
