FROM python:3.12-slim-bookworm

WORKDIR /app

# Build deps for asyncpg, cryptography, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/
COPY demo_assets/ ./demo_assets/

RUN pip install --no-cache-dir -e ./backend \
    && chmod +x ./backend/scripts/start_api.sh

ENV PYTHONUNBUFFERED=1
WORKDIR /app/backend

# Railway sets $PORT. Override start command on the worker service to:
#   python -m app.worker
CMD ["./scripts/start_api.sh"]
