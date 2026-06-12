#!/bin/sh
# Start API immediately for Railway healthcheck; run migrations in background.
(alembic upgrade head || echo "WARNING: migrations failed — check DATABASE_URL") &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
