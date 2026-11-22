<div align="center">

# ⚒️ FlowForge

### Automate the function. Not just the task.

AI-native automation that takes a whole business function from first input to finished outcome: **Input → Understand → Plan → Decide → Execute → Verify → Resolve → Outcome**. The MVP function is **Procurement** — a natural-language request becomes a validated, approved purchase order with a full audit trail.

[![CI](https://github.com/aayush-as69/FlowForge/actions/workflows/ci.yml/badge.svg)](https://github.com/aayush-as69/FlowForge/actions/workflows/ci.yml)
![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=nextdotjs)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-Python%203.11-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind-4-38BDF8?logo=tailwindcss&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)

</div>

---

## ✨ Features

### 🔄 Workflow engine
- **Reusable engine** – steps, states (`pending`, `running`, `completed`, `failed`, `waiting_human`, `resolved`, `skipped`), conditional skips and persisted context
- **Rewind, retry and resume** – interrupted workflows pick up where they left off after a restart
- **Visual graph & step inspector** – watch each run progress and inspect every step's inputs and outputs
- **Console pages** – Dashboard, Functions, Workflows, Approval Center, Exceptions, Vendors, Integrations, Policies and Audit Trail

### 🛒 Procurement (MVP function)
- **Natural-language intake** – *"I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000."* becomes a structured request
- **Policy validation** – policy rows are interpreted at runtime, not hard-coded
- **Vendor comparison** – quotes are compared against history to surface price anomalies
- **Level 1 / 2 / 3 decisioning** – autonomy level chosen from facts, policy report and configurable thresholds, with a full rule trace:
  - **Level 1** `auto_execute` – proceeds without human involvement
  - **Level 2** `review` – a human reviews before it proceeds
  - **Level 3** `human_decision` – a human makes the call

### 🧯 Exceptions & humans in the loop
- **Exception engine** – detect → classify → retry → auto-resolve → escalate to a human → record → resume
- **Approval center** – approve, reject, modify or escalate, with RBAC and separation of duties
- **Append-only audit trail** – every important action is recorded

### 🔐 Security
- bcrypt + JWT sessions, role-based access control, database-backed login throttling
- AI can only act through a registered **tool allow-list**; destructive tools (e.g. `accounting.release_payment`) are never granted

---

## 🏗️ Architecture

```
Browser ──► Next.js (UI, /api/health, proxy) ──/api/*──► FastAPI ──► PostgreSQL
                 └── instrumentation.js supervises the Python process ──┘
```

| Layer | Location | Notes |
|---|---|---|
| **Workflow engine** | `backend/app/workflows/engine.py` | Generic: steps, states, conditions, approvals, rewind, retry, resume |
| **Procurement** | `backend/app/workflows/procurement.py` | The *only* procurement-specific code: handlers, exception specs, resolvers |
| **Policy engine** | `backend/app/services/policy_engine.py` | Pure functions over policy rows (`rule_type` + params) |
| **Decisions** | `backend/app/decisions` | Level 1/2/3 autonomy with rule trace |
| **Exceptions** | `backend/app/exceptions` | Detect, classify, retry, resolve, escalate |
| **Agents** | `backend/app/agents` | Extraction (LLM + deterministic fallback), planner, explanations, tool registry |
| **Integrations** | `backend/app/integrations` | ERP, CRM, email, vendor DB, HR, accounting, document storage — **simulated** adapters |
| **API** | `backend/app/api` | REST handlers: auth, requests, workflows, approvals, exceptions, admin |
| **UI** | `src/app`, `src/components` | Next.js App Router + Tailwind, plain JavaScript/JSX |

**Design principles**
- **AI proposes, deterministic code decides.** Extraction, plans and explanations come from AI; auth, RBAC, policies, thresholds, state and audit are enforced in Python.
- **Works without an LLM key** – extraction falls back to a rule-based parser and says so (`extraction_engine = heuristic`).
- **Adding a function is data, not a rewrite** – define a `WorkflowDefinition`, register `ExceptionSpec`s and add policy rows; the engine, approvals, audit and UI are reused unchanged.

More detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 🚀 Getting started

**Prerequisites:** Docker with Compose, and Node.js ≥ 20.9.

```bash
git clone https://github.com/aayush-as69/FlowForge.git
cd FlowForge
npm install

cp .env.example .env
# Set unique POSTGRES_PASSWORD, SECRET_KEY and DEMO_PASSWORD in .env
# Generate SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up
```

Open <http://localhost:3000>.

> The Compose file is a **development convenience** (it mounts source and builds at startup). Don't use it as a production image. Enterprise adapters are simulated, not live vendor connections.

### Demo accounts

Created only when `FF_SEED=1` and a `DEMO_PASSWORD` is set. The password is whatever you put in `.env`.

| Role | Email |
|---|---|
| Admin | `admin@flowforge.demo` |
| Manager | `manager@flowforge.demo` |
| Approver | `approver@flowforge.demo` |
| Requester | `requester@flowforge.demo` |
| Auditor | `auditor@flowforge.demo` |

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `SECRET_KEY` | ✅ | Session signing key, 32+ characters |
| `LLM_TIMEOUT` | – | LLM request timeout in seconds, default `12` |
| `APP_ENV` | – | `development` (default) or `production` |
| `COOKIE_SECURE` | – | Set `1` behind HTTPS (required in production) |
| `FF_SEED` | – | `1` seeds demo data. Keep `0` in production |
| `DEMO_PASSWORD` | – | Password for seeded demo accounts |
| `LLM_API_KEY` | – | Omit to use the heuristic extractor (`OPENAI_API_KEY` also works) |
| `LLM_BASE_URL` / `LLM_MODEL` | – | OpenAI-compatible endpoint and model |
| `API_METRIC_RETENTION_DAYS` | – | Metric retention, default `90` |

### Scripts

| Command | What it does |
|---|---|
| `npm run dev` | Start the Next.js dev server |
| `npm run build` / `npm start` | Production build / serve |
| `npm run lint` | ESLint |
| `npm test` | Frontend tests (currently covers the safe-redirect helper) |
| `cd backend && PYTHONPATH=. python -m pytest tests -q` | Backend tests |

---

## 🚢 Production

1. Set `APP_ENV=production`, `COOKIE_SECURE=1`, a unique `SECRET_KEY` (32+ chars) and a managed PostgreSQL `DATABASE_URL`.
2. Build the immutable image from the included `Dockerfile` (runs as a non-root user).
3. Apply migrations: `cd backend && PYTHONPATH=.pylibs python -m alembic upgrade head`
4. Create the first tenant administrator:

```bash
FLOWFORGE_ADMIN_EMAIL=admin@example.com \
FLOWFORGE_ADMIN_PASSWORD='a-unique-password-of-at-least-14-characters' \
FLOWFORGE_ADMIN_NAME='Platform Administrator' \
FLOWFORGE_ORG_NAME='Your Organization' \
python backend/create_admin.py
```

5. Keep `FF_SEED=0`, never expose PostgreSQL publicly, and use managed backups.

The Alembic baseline is safe on databases that already contain the SQLAlchemy-created schema; add all future changes as new revisions. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## 📁 Project structure

```
FlowForge/
├── backend/
│   ├── alembic/             # migrations
│   ├── app/                 # agents, api, core, decisions, exceptions,
│   │                        # integrations, models, schemas, services, workflows
│   ├── tests/
│   └── create_admin.py      # first-admin bootstrap
├── database/                # schema notes
├── docs/                    # API, ARCHITECTURE, DEPLOYMENT
├── src/
│   ├── app/                 # routes, login, api
│   ├── components/          # workflow graph, approvals, audit timeline, UI kit
│   └── lib/
├── Dockerfile               # immutable production image
├── docker-compose.yml       # local dev stack
└── .github/workflows/       # CI: frontend, backend, container build
```

---

## 📚 Docs

- [API](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Deployment](docs/DEPLOYMENT.md)
- [Database](database/README.md)

---

## 🤝 Contributing

Contributions are welcome. Run `npm run lint`, `npm test` and the backend tests before opening a pull request — CI runs both, plus a production image build.

## 📄 License

Released under the [MIT License](LICENSE).
