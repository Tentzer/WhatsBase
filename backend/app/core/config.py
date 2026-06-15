"""Application settings — single source for all environment configuration.

Every env var listed in SPEC.md (section "Environment variables") is declared
here. Required vs optional is split deliberately: the optional block lets the
test suite and local tooling import the app without live cloud credentials,
while the required block fails fast in any real run.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

IntakeMode = Literal["webhook", "polling"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # --- Supabase / Postgres ---
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_anon_key: str = ""
    # asyncpg DSN, e.g. postgresql+asyncpg://user:pass@host:5432/postgres
    database_url: str = ""

    # --- Queue ---
    redis_url: str = "redis://localhost:6379"
    # arq per-job timeout for long-running build tasks (seconds). Default 4 hours.
    build_job_timeout_seconds: int = 14_400

    # --- Observability (noop-safe when blank, see observability.py) ---
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # --- Runtime behavior ---
    # When true, run_self_test is a no-op and finalize_build does not gate on it.
    build_skip_self_test: bool = True
    intake_mode: IntakeMode = "polling"
    app_base_url: str = "http://localhost:8000"

    # Comma-separated frontend origins allowed to call the API from browsers.
    # Example:
    #   https://whatsbase.vercel.app,https://my-preview.vercel.app
    cors_allow_origins: str = ""
    cors_allow_credentials: bool = True

    # Test-mode allowlist. Comma-separated WhatsApp numbers (country code +
    # digits, no plus, no spaces). Empty = no filter. When non-empty, the
    # intake layer drops incoming messages from any chat not in this list,
    # including all group chats (@g.us), to keep the bot from replying to
    # real contacts during local testing.
    allowed_test_numbers: str = ""
    # Daily stale-lead re-engagement automation.
    reengagement_enabled: bool = False
    # Dry-run mode writes decisions/events but does not send WhatsApp messages.
    reengagement_dry_run: bool = True
    # Daily UTC hour (0-23) when candidate scanning is scheduled.
    reengagement_cron_hour_utc: int = 6
    # Eligible if last activity is at least this many days ago.
    reengagement_stale_days: int = 60
    # Per-tenant cap for daily re-engagement sends.
    reengagement_max_daily_per_tenant: int = 25
    # Lifetime cap per lead to avoid repeated outreach loops.
    reengagement_max_attempts_per_lead: int = 3
    # Cooldown after each sent re-engagement.
    reengagement_cooldown_days: int = 30
    # Minimum judge confidence required before any outreach.
    reengagement_min_confidence: float = 0.65

    # Secret used to encrypt per-tenant Green API tokens at rest (see schema).
    # Generated/rotated out of band; blank in tests.
    token_encryption_key: str = Field(default="", repr=False)

    # --- Seed/admin only (not used by the running app) ---
    # Used by scripts/seed_instance.py to bootstrap the demo WhatsApp instance.
    green_api_instance_id: str = ""
    green_api_token: str = Field(default="", repr=False)


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so the env is parsed once per process."""
    return Settings()
