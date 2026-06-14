-- Runs once on first database start (mounted into the Postgres container).
-- Alembic migrations also create this, but enabling it here keeps a fresh
-- clone working even if migrations are run in an unexpected order.
CREATE EXTENSION IF NOT EXISTS vector;
