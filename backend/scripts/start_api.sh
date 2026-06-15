#!/bin/sh
# Run migrations BEFORE serving so the app never starts against a stale schema.
# Fail loudly: a failed migration aborts the deploy (Railway keeps the previous
# healthy release) instead of silently booting a broken API.
set -e
echo "Running database migrations (alembic upgrade head)..."
alembic upgrade head
echo "Migrations complete. Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
