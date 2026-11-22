# FlowForge — Automate the function. Not just the task.

AI-native automation that takes a whole business function from first input to finished outcome:
**Input → Understand → Plan → Decide → Execute → Verify → Resolve → Outcome** — humans handle judgment, FlowForge handles the operational work.

The MVP function is **Procurement**: *"I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000."* becomes a verified purchase order,
with policy validation, vendor comparison, a decision engine (Level 1/2/3), an exception engine, human approvals and a full audit trail.

## Stack
* **Python 3.11 — all backend logic**: FastAPI, SQLAlchemy, Pydantic, PostgreSQL, bcrypt/JWT sessions (`backend/`)
* **JavaScript/JSX only for the UI** (Next.js App Router + Tailwind). **No TypeScript source is used anywhere.**
  (A minimal `tsconfig.json` shim exists solely because the hosting toolchain runs `tsc --noEmit`; it type-checks no TypeScript.)
* Next.js proxies `/api/*` to the Python API and starts/supervises it (`src/instrumentation.js`).

## Run
```bash
cp .env.example .env            # DATABASE_URL etc.
npm install && npm run build && npm run start     # starts UI on :3000 and Python API on :8000
# or: docker compose up
```
Python deps install automatically into `backend/.pylibs` on first start (or `pip install --target backend/.pylibs -r backend/requirements.txt`).

Sign in at `/login` with a demo role (password `flowforge-demo`, override with `DEMO_PASSWORD`):
`admin@` · `manager@` · `approver@` · `requester@` · `auditor@flowforge.demo`.

## 3-minute demo
1. Sign in as **admin** → **Functions → Procurement → ▶ Run the primary demo**.
2. Watch the workflow graph execute live: AI extraction, HR + policy checks, vendor comparison.
3. FlowForge detects Bluepeak is **18% above its historical average**, searches alternatives (none safe) and opens a **human review** with context and a recommendation. Approve it.
4. A manager approval is required by policy (₹91,000 ≥ ₹50,000). Approve it.
5. Execution continues: the **ERP times out and is retried automatically**, spend is committed, delivery confirmed, invoice three-way match verified.
6. Open **Audit timeline**, **Exceptions**, **Policies** (change a threshold and re-run), **Integrations** (disconnect one and watch the exception engine react).

Other scenarios: fully autonomous Level 1 purchase, vendor outage auto-recovery, Level 3 human decision, category-policy block.

## Tests
```bash
cd backend && PYTHONPATH=.pylibs python3 -m pytest tests -q
```
Covers the policy engine, decision engine, exception engine (retry, auto-resolution, escalation, resolution), workflow engine (transitions, completion, interruption/resumption), and the API (authentication, authorization, validation, error handling, full flow).

`backend/tests/test_review_regressions.py` pins the security/correctness fixes from the code review: tenant isolation, "modify" decisions that name an ineligible vendor, malformed modification payloads, separation of duties for admins, and login throttling. The login-redirect guard has its own test (no extra dependencies):
```bash
npm test
```

## Docs
`docs/API.md` · `docs/ARCHITECTURE.md` · `database/README.md`
