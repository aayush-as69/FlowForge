#!/bin/sh
# Container start for hosted deployments (Render): apply migrations, optionally create the first admin, then serve.
set -e
cd /app/backend
PYTHONPATH=.pylibs python -m alembic upgrade head
if [ -n "$FLOWFORGE_ADMIN_EMAIL" ] && [ -n "$FLOWFORGE_ADMIN_PASSWORD" ]; then
  # Safe to repeat: it refuses (and we continue) when that administrator already exists.
  PYTHONPATH=.pylibs python create_admin.py || true
fi
cd /app
exec npm run start
