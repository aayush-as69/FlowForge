# Deployment and operations

## Required production configuration
- `APP_ENV=production`
- `SECRET_KEY`: unique random value, at least 32 characters; never reuse development key
- `DATABASE_URL`: managed PostgreSQL connection string
- `COOKIE_SECURE=1`
- `FF_SEED=0`
- `FLOWFORGE_ADMIN_EMAIL` and `FLOWFORGE_ADMIN_PASSWORD` only for the one-time bootstrap command

Do not deploy the local `docker-compose.yml` as a production image. It bind-mounts source and installs/builds packages at container startup. Build immutable images in CI, run schema migrations as a release step, and run the app as a non-root user.

## Split deployment (for example, Vercel + a Python host)

Deploy the Next.js frontend and FastAPI backend as separate services. Set `FLOWFORGE_API_URL` on the Next.js deployment to the backend origin (for example, `https://api.example.com`); this disables the local Python subprocess supervisor and makes the Next.js rewrite proxy requests to the external API. Set the same `SECRET_KEY` and database configuration on the backend only. Do not point a serverless Vercel deployment at `127.0.0.1` for its Python API.

## Deploying on Render (Blueprint)
`render.yaml` defines a managed PostgreSQL database and one Docker web service. In Render choose New → Blueprint, select this repository, and fill in `FLOWFORGE_ADMIN_EMAIL`, `FLOWFORGE_ADMIN_PASSWORD` (14+ characters) and `FLOWFORGE_ORG_NAME`. `SECRET_KEY` is generated and `DATABASE_URL` is wired automatically. `scripts/render-start.sh` runs `alembic upgrade head` on every start, creates the first administrator if none with that email exists, then starts the app. After the first successful deploy, delete the two `FLOWFORGE_ADMIN_*` variables. Free-tier services sleep when idle and free databases expire, so use paid plans for anything you keep. This blueprint has not been run on Render yet: check `/api/health` and the deploy logs on first use.

## First deployment
1. Provision PostgreSQL and private network access.
2. Install backend requirements and run `cd backend && PYTHONPATH=.pylibs python -m alembic upgrade head`.
3. Create the initial tenant administrator with `PYTHONPATH=backend/.pylibs python backend/create_admin.py` and the `FLOWFORGE_ADMIN_*` environment variables.
4. Deploy Next.js and FastAPI with the same `SECRET_KEY` and database configuration.
5. Verify `/api/health` and `/api/system/health`, login, tenant scoping, workflow execution and audit writes.
6. Configure backups, restore tests, TLS, edge rate limits and log/metric retention.

## Schema changes
Never rely on `Base.metadata.create_all()` for production upgrades. Add a new revision under `backend/alembic/versions`, test upgrades against an empty database and a copy of the previous schema, then run `alembic upgrade head` before deploying dependent code.

The first revision is a non-destructive baseline so an existing deployment that previously used `create_all()` can adopt Alembic without dropping data.

## Demo data
Demo fixtures are opt-in. `FF_SEED=1` and a unique `DEMO_PASSWORD` are required to create demo users/history. Do not enable this in production.

`FF_DEMO_MODE` controls the scripted demo scenarios (`POST /api/functions/procurement/demo`, fault injection). It defaults to on in development and **off when `APP_ENV=production`**; when on, only roles holding the `demo:run` permission (manager, admin) can start a scenario.

## Audit chain verification
`GET /api/audit/verify` (needs `audit:read`) recomputes every event hash and checks each link; the Audit page shows the result as a badge. It detects edited or removed events inside the history. It cannot detect events deleted from the very end, nor a database superuser rewriting the whole chain consistently; keep database backups and restrict DB ownership accordingly.

## Releases
Run `python scripts/make_release.py` to build a source zip. It refuses to run without `package-lock.json` or if secrets, databases or build output would be included.

## Request guards and headers
- The API refuses request bodies over 256 KB (413) and state-changing requests whose `Origin` header does not match the host (403). Behind a reverse proxy, forward the original `Host` (or `X-Forwarded-Host`).
- Next.js sends a CSP, `X-Frame-Options: DENY`, `nosniff`, a referrer policy and (in production) HSTS. Adjust `next.config.mjs` if you embed third-party scripts.
- `/api/docs` and `/api/openapi.json` are disabled when `APP_ENV=production`.
- API metrics are stored only for authenticated requests on matched routes and are purged periodically.
- There is no general API rate limit beyond login throttling; set one at your reverse proxy.

## Tests
Backend: `cd backend && python -m pytest tests -q` (SQLite) or with `TEST_DATABASE_URL=postgresql://...` (Postgres, also run in CI). Install `backend/requirements-dev.txt` for the test dependencies. Frontend: `npm test` (unit and component tests on Node's built-in runner with jsdom and Testing Library).

The demo endpoint only ever creates data in the caller's own organisation. Dashboard figures are computed in SQL, and workflow pages stop polling once a workflow has finished.
