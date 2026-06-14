# Convenience wrapper around the local demo steps. See README Quickstart for
# the explicit commands (use those on Windows if `make` is unavailable).

.PHONY: up down setup migrate seed run test demo logs

# Start local Postgres + pgvector and Redis.
up:
	docker compose -f infra/docker-compose.yml up -d

# Stop local infrastructure.
down:
	docker compose -f infra/docker-compose.yml down

# Create the backend virtualenv and install dependencies.
setup:
	cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

# Apply database migrations (schema + pgvector).
migrate:
	cd backend && . .venv/bin/activate && alembic upgrade head

# Build the demo tenant from the seed dataset.
seed:
	cd backend && . .venv/bin/activate && python -m app.builder.cli --tenant demo --assets ../demo_assets

# Run the API and the arq worker (two processes; Ctrl-C to stop).
run:
	cd backend && . .venv/bin/activate && \
		( uvicorn app.main:app --reload --port 8000 & \
		  arq app.intake.queue.WorkerSettings & \
		  wait )

# Backend tests.
test:
	cd backend && . .venv/bin/activate && pytest tests

# Full local demo, in order.
demo: up setup migrate seed run
