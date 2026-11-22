# FlowForge — Automate the function. Not just the task.

AI-native automation that takes a whole business function from first input to finished outcome: **Input → Understand → Plan → Decide → Execute → Verify → Resolve → Outcome**.

The MVP function is **Procurement**: a natural-language request becomes a purchase order with policy validation, vendor comparison, Level 1/2/3 decisioning, exception handling, human approvals and an audit trail.

## Stack
- **Python 3.11 backend:** FastAPI, SQLAlchemy, Pydantic, PostgreSQL, bcrypt/JWT sessions
- **JavaScript/JSX frontend:** Next.js App Router + Tailwind; no TypeScript application source
- Next.js proxies `/api/*` to FastAPI and supervises the Python process

## Local demo
```bash
cp .env.example .env
# Set unique POSTGRES_PASSWORD, SECRET_KEY and DEMO_PASSWORD values in .env.
# Generate SECRET_KEY with: python -c "import secrets; print(secrets.token_urlsafe(48))"
# Keep FF_SEED=1 only for a local demo.
npm install
docker compose up
```

The Compose file is a development convenience: it mounts source and builds Next.js at container startup. Do not use it as a production image. Demo accounts are created only when `FF_SEED=1` and an explicit `DEMO_PASSWORD` is supplied. Enterprise adapters (ERP, HR, CRM, accounting, email and document storage) are simulated, not live vendor connections.

## Production bootstrap
1. Set `APP_ENV=production`, `COOKIE_SECURE=1`, a unique `SECRET_KEY` (32+ characters), and a managed PostgreSQL `DATABASE_URL`.
2. Build immutable deployment images and install dependencies in the image.
3. Apply migrations: `cd backend && PYTHONPATH=.pylibs python -m alembic upgrade head`.
4. Provision the first tenant administrator with a strong password from your secret manager:
```bash
FLOWFORGE_ADMIN_EMAIL=admin@example.com \
FLOWFORGE_ADMIN_PASSWORD='use-a-unique-password-of-at-least-14-characters' \
FLOWFORGE_ADMIN_NAME='Platform Administrator' \
FLOWFORGE_ORG_NAME='Your Organization' \
python backend/create_admin.py
```
5. Keep `FF_SEED=0` in production. Never expose PostgreSQL publicly; use private networking and managed backups.

The initial Alembic baseline is safe to apply to databases that already contain the SQLAlchemy-created schema. Future schema changes must be added as new Alembic revisions.

## Tests
Frontend: `npm ci && npm test && npm run build`.
Backend: `python -m pip install -r backend/requirements.txt`, then `cd backend && PYTHONPATH=. python -m pytest tests -q`.

GitHub Actions runs frontend tests/build and backend tests on pushes to `main` and pull requests.

## Docs
- `docs/API.md`
- `docs/ARCHITECTURE.md`
- `docs/DEPLOYMENT.md`
- `database/README.md`
