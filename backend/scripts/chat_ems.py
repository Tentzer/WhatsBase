"""Interactive local test chat with the EMS כפר סבא lead-qualification agent.

Bypasses HTTP, Supabase JWT, and the arq queue — calls run_turn directly.
Requires the EMS tenant to exist (run seed_ems_tenant.py first).
Requires ANTHROPIC_API_KEY in the environment (or .env file).

Usage (interactive REPL):
    cd C:\\Projects\\WhatsBase\\backend
    python scripts/chat_ems.py

Usage (single message):
    python scripts/chat_ems.py "שלום, אני מתעניין/ת באימוני EMS"
"""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.schema import Agent, Tenant
from app.runtime.context import TurnContext
from app.runtime.conversation import run_turn

TENANT_NAME = "EMS כפר סבא"


async def _load_agent(session) -> tuple[str, str, str]:
    """Return (tenant_id, system_prompt, agent_type)."""
    tenant_result = await session.execute(
        select(Tenant).where(Tenant.name == TENANT_NAME)
    )
    tenant = tenant_result.scalar_one_or_none()
    if tenant is None:
        print(f'ERROR: Tenant "{TENANT_NAME}" not found. Run scripts/seed_ems_tenant.py first.')
        sys.exit(1)

    agent_result = await session.execute(
        select(Agent).where(Agent.tenant_id == tenant.id)
    )
    agent = agent_result.scalar_one_or_none()
    if agent is None or agent.status != "live" or not agent.system_prompt:
        print("ERROR: Agent is not live. Re-run scripts/seed_ems_tenant.py.")
        sys.exit(1)

    return tenant.id, agent.system_prompt, getattr(agent, "agent_type", "lead_qualification")


async def chat(initial_message: str | None = None) -> None:
    async with SessionLocal() as session:
        tenant_id, system_prompt, agent_type = await _load_agent(session)

    print(f'EMS כפר סבא — lead_qualification agent (tenant: {tenant_id})')
    print('Type "exit" or Ctrl-C to quit.\n')

    history: list = []

    async def _turn(user_text: str) -> str:
        result = await run_turn(
            tenant_id=tenant_id,
            system_prompt=system_prompt,
            history=history,
            user_text=user_text,
            ctx=TurnContext(tenant_id=tenant_id, channel="test_chat"),
            agent_type=agent_type,
        )
        # Append to in-memory history so context carries across turns.
        from app.core.schema import Message
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        history.append(
            Message(
                direction="inbound",
                type="text",
                content=user_text,
                created_at=now,
            )
        )
        history.append(
            Message(
                direction="outbound",
                type="text",
                content=result.reply_text,
                created_at=now,
            )
        )
        return result.reply_text

    if initial_message:
        # Single-shot mode
        print(f"You: {initial_message}")
        reply = await _turn(initial_message)
        print(f"Bot: {reply}")
        return

    # Interactive REPL
    while True:
        try:
            user_text = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            break
        if not user_text:
            continue
        if user_text.lower() in {"exit", "quit", "bye"}:
            break
        reply = await _turn(user_text)
        print(f"Bot: {reply}\n")


if __name__ == "__main__":
    msg = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    asyncio.run(chat(msg))
