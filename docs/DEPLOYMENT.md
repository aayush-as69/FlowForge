# Deployment and operations

## Required production configuration
- `APP_ENV=production`
- `SECRET_KEY`: unique random value, at least 32 characters; never reuse development key
- `DATABASE_URL`: managed PostgreSQL connection string
- `COOKIE_SECURE=1`
- `FF_SEED=0`
- `FLOWFORGE_ADMIN_EMAIL` and `FLOWFORGE_ADMIN_PASSWORD` only for the one-time bootstrap command

Do not deploy the local `docker-compose.yml` as a production image. It bind-mounts source and installs/builds packages at container startup. Build immutable images in CI, run schema migrations as a release step, and run the app as a non-root user.

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
