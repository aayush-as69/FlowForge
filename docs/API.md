# FlowForge API

All routes are served by the Python (FastAPI) backend under `/api` (interactive OpenAPI docs at `/api/docs`).
Authentication is a signed, `HttpOnly`, `SameSite=Lax` session cookie (`ff_session`) — or `Authorization: Bearer <jwt>`.
Errors are always `{ "detail": "<what happened>" }`; validation errors add `"errors": [{field, message}]` (HTTP 422).

| Area | Method & path | Permission | Notes |
|---|---|---|---|
| auth | `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` | public / session | bcrypt, login throttling, audited |
| functions | `GET /functions` · `GET /functions/procurement/scenarios` · `POST /functions/procurement/demo` | workflows:read / requests:create | demo runs the real engine |
| requests | `POST /requests` · `GET /requests` · `GET/PATCH /requests/{id}` · `POST /requests/{id}/execute` | requests:create | AI extraction on create; PATCH = human correction; execute → 202 + background workflow |
| workflows | `GET /workflows` (filter, search, pagination) · `GET /workflows/{id}` · `GET /workflows/{id}/steps` · `GET /workflows/{id}/audit` | workflows:read | requesters see only their own |
| | `POST /workflows/{id}/retry` · `POST /workflows/{id}/cancel` | workflows:operate | retry resumes from the failed step |
| workflow-steps | `GET /workflow-steps/{id}` | workflows:read | node inspector |
| approvals | `GET /approvals?status=pending|decided` · `GET /approvals/{id}` · `POST /approvals/{id}/decision` | approvals:read / approvals:decide | actions: approve, reject, modify, escalate; Level 3 needs a note; separation of duties enforced for every role, admins included; approvals of other organisations are `404`. `modify` takes `{"vendor_id": <positive integer>}` and is refused with `422` unless that vendor was evaluated, is approved and is eligible for the request |
| exceptions | `GET /exceptions?group=` · `GET /exceptions/summary` · `GET /exceptions/{id}` | exceptions:read | groups: auto_resolved, awaiting_review, escalated, failed, resolved_by_human |
| policies | `GET /policies` · `PATCH /policies/{id}` | policies:read / policies:write | params validated per rule type; versioned + audited |
| vendors | `GET /vendors` · `PATCH /vendors/{id}` | vendors:read / vendors:write | |
| integrations | `GET /integrations` · `POST /integrations/{key}/check` · `PATCH /integrations/{key}` | integrations:read / manage | disconnecting makes workflows raise `INTEGRATION_UNAVAILABLE` |
| audit | `GET /audit?workflow_id=&actor_type=&q=&page=` | audit:read | |
| dashboard | `GET /dashboard/summary` · `GET /dashboard/observability` | dashboard:read | metrics computed from real data |

## Sign-in throttling
`POST /auth/login` is limited per address + account (8 attempts / 5 min; the e-mail is trimmed and lower-cased first, so spelling variants share one counter) and per address (40 *failed* attempts / 5 min). Counters live in process memory; use a shared store if you run more than one API worker.

## Roles
`requester` (submit/track own) · `auditor` (read-only incl. audit) · `approver` (Level 2 reviews) · `manager` (approvals, operate workflows, vendors) · `admin` (everything incl. policies, integrations).

## Request body example
```json
POST /api/requests
{ "source": "text", "text": "I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000.", "demo_faults": [] }
```
