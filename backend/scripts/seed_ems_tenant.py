"""Seed the EMS כפר סבא lead-qualification tenant for local testing.

Creates:
  1. Tenant row  ("EMS כפר סבא", status=active, plan=free)
  2. Agent row   (agent_type="lead_qualification", status="live",
                  system_prompt rendered from LEAD_QUALIFICATION_TEMPLATE
                  with David's voice examples)
  3. BusinessInfo rows (8 topics + voice_examples; no prices/packages/durations)

Run once from the backend directory:

    cd C:\\Projects\\WhatsBase\\backend
    python scripts/seed_ems_tenant.py

Prints the tenant_id on success. Re-running is safe: existing BusinessInfo rows
for this tenant are replaced; the agent row is upserted.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Ensure the backend package is importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.builder.prompts import render_lead_qual_prompt
from app.core.db import SessionLocal
from app.core.schema import Agent, BusinessInfo, Tenant

# ---------------------------------------------------------------------------
# EMS business data — NO prices, packages, session counts, or results claims
# ---------------------------------------------------------------------------
TENANT_NAME = "EMS כפר סבא"
TENANT_DESCRIPTION = "סטודיו לאימוני EMS אישיים בכפר סבא"

BUSINESS_INFO: list[dict] = [
    {
        "topic": "what_is_ems",
        "content_he": (
            "EMS (Electrical Muscle Stimulation) הוא אימון אישי של כ-20 דקות "
            "בחליפה מיוחדת שמפעילה את השרירים בעזרת גירוי חשמלי עדין בזמן תרגול. "
            "האימון מתבצע אחד-על-אחד עם המאמן דוד, עובד את כל הגוף, ומתאים לכל "
            "רמת כושר. בסשן EMS מופעלים כ-90% מהשרירים בו-זמנית, לעומת 3-4 קבוצות "
            "שרירים באימון רגיל."
        ),
        "content_en": (
            "EMS (Electrical Muscle Stimulation) is a personal ~20-minute session "
            "using a special suit that activates muscles through gentle electrical "
            "impulses during exercise. Sessions are one-on-one with trainer David, "
            "work the entire body, and suit all fitness levels. An EMS session activates "
            "~90% of muscles simultaneously, compared to 3-4 muscle groups in a "
            "regular workout."
        ),
    },
    {
        "topic": "location",
        "content_he": "הסטודיו נמצא ברחוב התע\"ש 20, כפר סבא, בית הפעמון.",
        "content_en": "The studio is located at HaTa'ash 20, Kfar Saba, Beit HaPaamon.",
    },
    {
        "topic": "contact",
        "content_he": (
            "מספר הטלפון של הסטודיו (ברירת מחדל): 050-871-2322. "
            "מספר אישי של דוד (רק אם הלקוח ביקש במפורש): 054-996-2612. "
            "ניתן לקבוע אימון ניסיון בטלפון או דרך טופס באתר."
        ),
        "content_en": (
            "Studio phone (default): 050-871-2322. "
            "David's personal number (only if explicitly requested): 054-996-2612. "
            "Trial sessions can be booked by phone or via the website form."
        ),
    },
    {
        "topic": "hours",
        "content_he": "שעות פעילות: ימים א'–ה' 08:30–20:30. שישי–שבת סגור.",
        "content_en": "Opening hours: Sunday–Thursday 08:30–20:30. Friday–Saturday closed.",
    },
    {
        "topic": "what_to_bring",
        "content_he": (
            "אין צורך להביא כלום — הכול מסופק במקום. "
            "מגיעים, מתאמנים, וזהו."
        ),
        "content_en": (
            "No need to bring anything — everything is provided on site. "
            "Just come as you are."
        ),
    },
    {
        "topic": "vs_gym",
        "content_he": (
            "בניגוד לחדר כושר רגיל, אימון EMS מפעיל כ-90% מהשרירים בו-זמנית "
            "תוך 20 דקות, ללא מאמץ על המפרקים. אין ציוד כבד. המאמן מלווה אישית "
            "לכל אורך האימון."
        ),
        "content_en": (
            "Unlike a regular gym, EMS activates ~90% of muscles simultaneously "
            "in 20 minutes, with no joint strain. No heavy equipment. "
            "The trainer guides you personally throughout every session."
        ),
    },
    {
        "topic": "suitability",
        "content_he": (
            "מתאים למגוון רחב של אנשים, כולל כאלה שלא יכלו להתאמן בשיטות אחרות "
            "(בעיות גב, אחרי פציעה). ההתאמה תמיד נקבעת עם דוד. "
            "ניתן לשלב עם ספורט אחר."
        ),
        "content_en": (
            "Suits a wide range of people, including those who couldn't train with "
            "other methods (back issues, post-injury). Suitability is always decided "
            "together with David. Can be combined with other sports."
        ),
    },
    {
        "topic": "medical_safety",
        "content_he": (
            "כל שאלה רפואית או אזכור של מצב גופני (קוצב לב, הריון, אפילפסיה, "
            "בעיות לב, פציעות) מטופלת ישירות ואישית על ידי דוד. "
            "הבוט לא נותן אישור ולא פוסל — לוקח פרטים ומעביר לדוד. "
            "ההחלטה הרפואית שייכת למאמן בלבד."
        ),
        "content_en": (
            "Any medical question or condition (pacemaker, pregnancy, epilepsy, "
            "heart conditions, injuries) is handled directly and personally by David. "
            "The bot never gives clearance and never rejects — it takes details and "
            "passes to David. The medical decision belongs to the trainer alone."
        ),
    },
]

# ---------------------------------------------------------------------------
# David's voice examples — stored as topic="voice_examples" in the DB.
# The {voice_examples} slot in LEAD_QUALIFICATION_TEMPLATE anchors the bot's
# tone and style; these examples are excluded from {business_summary}.
# ---------------------------------------------------------------------------
VOICE_EXAMPLES_HE = """\
לקוח: היי, רציתי להתעניין באימונים שלכם.
בוט: היי, מה נשמע. כיף שפנית. תוכל לספר לי קצת מה המטרה שלך באימון, ואני אכוון אותך לאימון ניסיון שיתאים לך אישית?

לקוח: אפשר לקבוע אימון ניסיון?
בוט: בטח, אין בעיה. מעביר אותך לדוד שיתקשר לקבוע אימון ניסיון אישי. רק לפני זה — מה השם שלך?

לקוח: כמה עולה חבילה אצלכם?
בוט: המחיר משתנה לפי התוכנית האישית שדוד יבנה לך כדי להגיע למטרה שלך. הוא ייצור איתך קשר לתאם מועד שנוח לך.

לקוח: יש לי בעיה בגב, אני יכולה להתאמן?
בוט: אשמח להעביר אותך לדוד, הוא יודע להתאים תוכנית לכל מצב. הוא יחזור אליך עם הסבר מדויק ולתאם אימון ניסיון.

לקוח: מה צריך להביא לאימון?
בוט: לא צריך להביא כלום, הכול אצלנו במקום. באים, מתאמנים, וזהו."""


def _build_business_summary() -> str:
    """Compose the {business_summary} block from BUSINESS_INFO rows.
    voice_examples is handled separately and intentionally excluded here."""
    lines = []
    for item in BUSINESS_INFO:
        lines.append(f"  [{item['topic']}]")
        if item.get("content_en"):
            lines.append(f"    EN: {item['content_en']}")
        if item.get("content_he"):
            lines.append(f"    HE: {item['content_he']}")
    return "\n".join(lines)


async def main() -> None:
    async with SessionLocal() as session:
        # ------------------------------------------------------------------ #
        # 1. Tenant — skip if already exists
        # ------------------------------------------------------------------ #
        result = await session.execute(
            select(Tenant).where(Tenant.name == TENANT_NAME)
        )
        tenant = result.scalar_one_or_none()

        if tenant is not None:
            print(f"Tenant already exists — skipping creation.")
            print(f"tenant_id: {tenant.id}")
        else:
            tenant = Tenant(
                name=TENANT_NAME,
                description=TENANT_DESCRIPTION,
                status="active",
                plan="free",
            )
            session.add(tenant)
            await session.flush()  # assigns tenant.id
            print(f"Created tenant: {tenant.name}")
            print(f"tenant_id: {tenant.id}")

        tenant_id = tenant.id

        # ------------------------------------------------------------------ #
        # 2. BusinessInfo rows — delete existing, re-insert (idempotent)
        # ------------------------------------------------------------------ #
        from sqlalchemy import delete as sql_delete
        await session.execute(
            sql_delete(BusinessInfo).where(BusinessInfo.tenant_id == tenant_id)
        )
        for item in BUSINESS_INFO:
            session.add(
                BusinessInfo(
                    tenant_id=tenant_id,
                    topic=item["topic"],
                    content_he=item["content_he"],
                    content_en=item["content_en"],
                )
            )
        # Store voice examples as a BusinessInfo row so the Builder CLI can
        # find them via add_business_info and knowledge.py extracts them.
        session.add(
            BusinessInfo(
                tenant_id=tenant_id,
                topic="voice_examples",
                content_he=VOICE_EXAMPLES_HE,
                content_en="",
            )
        )
        print(f"Seeded {len(BUSINESS_INFO)} business_info rows + voice_examples.")

        # ------------------------------------------------------------------ #
        # 3. Agent — render system_prompt from template + voice examples
        # ------------------------------------------------------------------ #
        agent_result = await session.execute(
            select(Agent).where(Agent.tenant_id == tenant_id)
        )
        agent = agent_result.scalar_one_or_none()

        business_summary = _build_business_summary()
        system_prompt = render_lead_qual_prompt(
            business_name=TENANT_NAME,
            business_description=TENANT_DESCRIPTION,
            business_summary=business_summary,
            voice_examples=VOICE_EXAMPLES_HE,
        )

        if agent is None:
            agent = Agent(
                tenant_id=tenant_id,
                status="live",
                agent_type="lead_qualification",
                system_prompt=system_prompt,
            )
            session.add(agent)
            print("Created agent row (status=live, agent_type=lead_qualification).")
        else:
            agent.status = "live"
            agent.agent_type = "lead_qualification"
            agent.system_prompt = system_prompt
            print("Updated existing agent row.")

        await session.commit()

    print()
    print("=" * 60)
    print("EMS tenant ready. Agent uses lead_qualification path with")
    print("David's voice examples loaded into {voice_examples} slot.")
    print(f"tenant_id : {tenant_id}")
    print()
    print("To run a quick local conversation (no HTTP, no auth):")
    print("  python scripts/chat_ems.py")
    print()
    print("To send a single message:")
    print('  python scripts/chat_ems.py "שלום, אני מתעניין/ת באימוני EMS"')
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
