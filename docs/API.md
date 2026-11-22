# FlowForge API

All routes are served by the Python (FastAPI) backend under `/api` (interactive OpenAPI docs at `/api/docs`).
Authentication is a signed, `HttpOnly`, `SameSite=Lax` session cookie (`ff_session`) — or `Authorization: Bearer <jwt>`.
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
| audit | `GET /audit` | audit:read | |
| dashboard | `GET /dashboard/summary` · `GET /dashboard/observability` | dashboard:read | keep metrics scoped to the authenticated organisation |

## Sign-in throttling

Login attempts are persisted in the database so limits apply across API workers and restarts. Deployments should additionally apply edge-level limits to public and expensive endpoints.

## Demo data

Demo accounts and history are created only when `FF_SEED=1` and an explicit `DEMO_PASSWORD` is supplied. Keep `FF_SEED=0` in production. Production must provision the first organisation and administrator through a controlled bootstrap process; do not enable demo seeding for production identities.

## Request body example

```json
POST /api/requests
{ "source": "text", "text": "I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000." }
```
