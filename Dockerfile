FROM python:3.12-slim-bookworm

WORKDIR /app

# Build deps for asyncpg, cryptography, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/

RUN pip install --no-cache-dir -e ./backend

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend

# Railway sets $PORT. Override start command on the worker service to:
#   python -m app.worker
CMD sh -c "alembic upgrade head || echo 'Migration failed — check DATABASE_URL'; exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"
