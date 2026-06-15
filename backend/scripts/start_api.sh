#!/bin/sh
# Start the API immediately so Railway's healthcheck (/health/live) passes, then
# run migrations in the background. A migration failure is non-fatal to boot (the
# existing schema keeps serving) but is clearly surfaced in the deploy logs.
(alembic upgrade head \
    && echo "MIGRATIONS: up to date" \
    || echo "WARNING: migrations failed — check DATABASE_URL and run 'alembic upgrade head'") &
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
