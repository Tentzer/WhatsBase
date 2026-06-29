"""Seed one realistic test lead + conversation for the EMS tenant.

Creates data the same way the real intake path does (tasks.py:run_agent_turn
and _upsert_lead_after_turn), so the dashboard's leads list and conversation
view render real-looking data.

Creates:
  1. Conversation  (tenant_id + customer_phone, status="open")
  2. 5 Messages    (alternating inbound / outbound, realistic Hebrew EMS exchange)
  3. Lead          (status="awaiting_owner", source="whatsapp_auto", conversation linked)

Idempotent: if a Lead already exists for this tenant + phone, prints its IDs
and exits without duplicating anything.

Run from the backend directory:

    cd C:\\Projects\\WhatsBase\\backend
    python scripts/seed_test_lead.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

# Ensure the backend package is importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.schema import Conversation, Lead, Message, Tenant
from app.leads.service import normalize_phone

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TENANT_ID = "7d82152f-57b2-49ec-8590-102fbcd8c652"   # EMS כפר סבא

# Fictitious test phone — international format, no @ suffix (matches how
# tasks.py stores it: chat_id.split("@")[0] passed to get_or_create_conversation,
# then normalize_phone applied for the Lead row).
CUSTOMER_PHONE_RAW = "972500000001"   # as stored on Conversation.customer_phone

# Realistic Hebrew EMS exchange — 3 inbound, 2 outbound.
# Timestamps spread over 10 minutes to simulate a real conversation.
_NOW = datetime.now(timezone.utc)

MESSAGES: list[dict] = [
    {
        "direction": "inbound",
        "type": "text",
        "content": "היי, ראיתי את הסטודיו שלכם ב-Waze. מה זה בדיוק EMS?",
        "media_url": None,
        "agent_trace_id": None,
        "created_at": _NOW - timedelta(minutes=10),
    },
    {
        "direction": "outbound",
        "type": "text",
        "content": (
            "שלום! כיף שפנית. EMS זה אימון אישי של כ-20 דקות בחליפה מיוחדת "
            "שמפעילה את השרירים בגירוי חשמלי. עובד את כל הגוף בבת אחת, "
            "אחד-על-אחד עם המאמן דוד. מה המטרה שלך באימון?"
        ),
        "media_url": None,
        "agent_trace_id": None,
        "created_at": _NOW - timedelta(minutes=9),
    },
    {
        "direction": "inbound",
        "type": "text",
        "content": "אני רוצה לרדת במשקל ולהתחזק. יש לי גם קצת כאבי גב. זה מתאים לי בכלל?",
        "media_url": None,
        "agent_trace_id": None,
        "created_at": _NOW - timedelta(minutes=7),
    },
    {
        "direction": "outbound",
        "type": "text",
        "content": (
            "מעביר אותך לדוד שיבדוק איתך אישית את ההתאמה, כולל הגב. "
            "הוא מתמחה בהתאמות כאלו. רק תן לי שם ומספר ודוד יחזור אליך לתאם אימון ניסיון."
        ),
        "media_url": None,
        "agent_trace_id": None,
        "created_at": _NOW - timedelta(minutes=6),
    },
    {
        "direction": "inbound",
        "type": "text",
        "content": "השם שלי ישראל ישראלי. המספר הזה טוב, תודה.",
        "media_url": None,
        "agent_trace_id": None,
        "created_at": _NOW - timedelta(minutes=5),
    },
]

LEAD_SUMMARY = (
    "הליד (ישראל ישראלי) מתעניין ב-EMS לירידה במשקל וחיזוק. "
    "ציין כאבי גב. ביקש שדוד יחזור אליו לתאם אימון ניסיון."
)


async def main() -> None:
    phone = normalize_phone(CUSTOMER_PHONE_RAW)   # "972500000001" → unchanged

    async with SessionLocal() as session:
        # ------------------------------------------------------------------ #
        # Idempotency check: is there already a lead for this tenant + phone?
        # ------------------------------------------------------------------ #
        existing_lead = (
            await session.execute(
                select(Lead).where(
                    Lead.tenant_id == TENANT_ID,
                    Lead.phone_number == phone,
                )
            )
        ).scalar_one_or_none()

        if existing_lead is not None:
            print("Lead already exists — no changes made.")
            print()
            print("=" * 60)
            print(f"  lead_id         = {existing_lead.id}")
            print(f"  conversation_id = {existing_lead.conversation_id}")
            msg_count = (
                await session.execute(
                    select(Message).where(
                        Message.conversation_id == existing_lead.conversation_id
                    )
                )
            ).scalars().all() if existing_lead.conversation_id else []
            print(f"  message_count   = {len(msg_count)}")
            print("=" * 60)
            return

        # ------------------------------------------------------------------ #
        # 1. Conversation — matching memory.get_or_create_conversation exactly
        # ------------------------------------------------------------------ #
        conversation = (
            await session.execute(
                select(Conversation).where(
                    Conversation.tenant_id == TENANT_ID,
                    Conversation.customer_phone == CUSTOMER_PHONE_RAW,
                )
            )
        ).scalar_one_or_none()

        if conversation is None:
            conversation = Conversation(
                tenant_id=TENANT_ID,
                customer_phone=CUSTOMER_PHONE_RAW,
                status="open",
            )
            session.add(conversation)
            await session.flush()   # assign conversation.id via gen_random_uuid()
            print(f"Created conversation id={conversation.id}")
        else:
            print(f"Reusing existing conversation id={conversation.id}")

        conversation.last_message_at = _NOW - timedelta(minutes=5)

        # ------------------------------------------------------------------ #
        # 2. Messages — matching Message() calls in run_agent_turn exactly
        # ------------------------------------------------------------------ #
        for msg_data in MESSAGES:
            session.add(
                Message(
                    conversation_id=conversation.id,
                    direction=msg_data["direction"],
                    type=msg_data["type"],
                    content=msg_data["content"],
                    media_url=msg_data["media_url"],
                    agent_trace_id=msg_data["agent_trace_id"],
                    created_at=msg_data["created_at"],
                )
            )
        print(f"Added {len(MESSAGES)} messages.")

        # ------------------------------------------------------------------ #
        # 3. Lead — matching _upsert_lead_after_turn exactly, then status bump
        # ------------------------------------------------------------------ #
        tenant = await session.get(Tenant, TENANT_ID)
        business_name = tenant.name if tenant else None

        lead = Lead(
            tenant_id=TENANT_ID,
            full_name=f"Lead {phone[-4:]}",          # "Lead 0001"
            phone_number=phone,
            status="awaiting_owner",                  # as if handoff was signalled
            source="whatsapp_auto",
            business_name=business_name,
        )
        session.add(lead)
        await session.flush()                         # assign lead.id

        lead.conversation_id = conversation.id
        lead.last_message_sent_at = _NOW - timedelta(minutes=5)
        lead.last_conversation_summary = LEAD_SUMMARY

        await session.commit()
        await session.refresh(lead)
        await session.refresh(conversation)

    print()
    print("=" * 60)
    print("Test lead seeded successfully.")
    print(f"  lead_id         = {lead.id}")
    print(f"  phone_number    = {lead.phone_number}")
    print(f"  status          = {lead.status}")
    print(f"  conversation_id = {lead.conversation_id}")
    print(f"  message_count   = {len(MESSAGES)}")
    print(f"  business_name   = {lead.business_name}")
    print("=" * 60)
    print()
    print("Open the dashboard → Leads to see this lead,")
    print('then click "Chat / שיחה" to read the conversation.')


if __name__ == "__main__":
    asyncio.run(main())
