#!/bin/sh
# SENTINEL backend container entrypoint:
#   1. run Alembic migrations against the (already-healthy) database
#   2. seed the admin user  (idempotent; skipped if ADMIN_PASSWORD is unset,
#      in which case a random one is generated and printed so the demo works)
#   3. exec uvicorn
set -e

export PYTHONPATH="/app:${PYTHONPATH}"

echo "[entrypoint] running migrations..."
( cd /database && alembic -c alembic.ini upgrade head )

if [ -z "${ADMIN_PASSWORD}" ]; then
  ADMIN_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(12))')"
  export ADMIN_PASSWORD
  echo "[entrypoint] ADMIN_PASSWORD was not set -> generated one for this run:"
  echo "[entrypoint]     username=${ADMIN_USERNAME:-admin}  password=${ADMIN_PASSWORD}"
fi

echo "[entrypoint] seeding database..."
python /scripts/seed_db.py || echo "[entrypoint] seed step skipped/failed (continuing)"

echo "[entrypoint] starting API on :${BACKEND_PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${BACKEND_PORT:-8000}" ${UVICORN_RELOAD:+--reload}
