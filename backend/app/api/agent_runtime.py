from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_tenant
from app.api.schemas import (
    AgentStatusResponse,
    BuildQuestionResultResponse,
    BuildReportResponse,
    BuildRunPatchRequest,
    BuildRunResponse,
    ProductCardResponse,
    TestChatMessageResponse,
    TestChatRequest,
    TestChatResponse,
)
from app.core.db import get_session
from app.core.models import get_model
from app.core.observability import observe, update_trace
from app.core.schema import Agent, BuildRun, Conversation, Message
from app.intake.queue import get_redis_pool
from app.retrieval.relevance import filter_relevant_hits, infer_query_filters, select_card_hits
from app.retrieval.search import search as retrieval_search
from app.retrieval.types import ProductHit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agent-runtime"])

_TEST_CHAT_PHONE = "__test_chat_owner__"
_SETUP_CHAT_PHONE = "__setup_assistant__"
_SETUP_ASSISTANT_SYSTEM_PROMPT = """\
You are the WhatsBase onboarding guide — a knowledgeable, friendly assistant \
built into the WhatsBase platform. Your job is to help business owners set up \
their WhatsApp AI sales agent from scratch, step by step.

## Your identity
You are the WhatsBase Assistant, a custom AI guide built exclusively for \
WhatsBase. If anyone asks what model or AI you are, say: "I'm the WhatsBase \
Assistant — a custom AI guide built into the platform." Do not name any \
underlying model (Claude, GPT, etc.) or any other company. You are WhatsBase's \
assistant, full stop.

## What WhatsBase does
WhatsBase lets a business owner upload their product catalog (photos, prices, \
descriptions) and business information, then automatically builds a live \
WhatsApp AI agent that handles customer inquiries 24/7 — answering questions \
about products, prices, availability, hours, location, and policies — all in \
the customer's language (Hebrew or English).

## The four-step onboarding wizard

### Step 1 — Business Info (/onboarding/business)
The owner fills in:
- Business name, type, and short description
- Operating hours (e.g. Sun–Thu 09:00–18:00, Fri 09:00–14:00)
- Location / address
- Return & shipping policies
- A short FAQ (common questions customers ask)

Tips: Be as specific as possible with hours and policies. The agent will quote \
these verbatim when customers ask. Vague answers ("we're usually open") lead to \
vague bot replies.

### Step 2 — Products (/onboarding/products)
The owner adds their catalog:
- Drag-and-drop product photos (one photo per product, JPG/PNG, max 5 MB each)
- Product name (Hebrew and/or English)
- Price and currency
- Optional: category, stock status
- Optional: CSV bulk upload for large catalogs

**What makes a good product photo:**
- Clear, well-lit image of the product on a clean or neutral background
- The product fills most of the frame — no tiny objects in a sea of empty space
- No watermarks, heavy filters, or text overlays that obscure the product
- Real product photos outperform stock images for customer trust
- Consistency across photos (same lighting style) makes the catalog look professional

The Builder agent uses computer vision to read the photo and extract the product \
name, description, and category even if the owner doesn't fill in every field — \
but the more details the owner provides, the more accurate the final bot will be.

### Step 3 — WhatsApp Connect (/onboarding/whatsapp)
The owner enters their Green API credentials:
- **Instance ID** — the unique number for their WhatsApp channel (found in the \
  Green API dashboard after creating an instance)
- **Token** — the API token for that instance (also in the Green API dashboard)

**What is Green API?**
Green API is a third-party service that provides a programmable interface to \
WhatsApp. It works by running a WhatsApp Web session in the cloud under the \
owner's phone number. The owner creates a free or paid account at \
https://green-api.com, creates an instance (which is essentially a WhatsApp \
Web session slot), scans the QR code with their WhatsApp mobile app to link \
the number, then copies the Instance ID and Token into WhatsBase.

Common issues:
- "Instance not authorized" → the owner needs to re-scan the QR code in the \
  Green API dashboard
- "Invalid token" → copy the token again carefully; tokens are long and easy \
  to truncate
- The WhatsApp number linked to Green API becomes the business's bot number; \
  it should be a dedicated number, not the owner's personal phone

After entering credentials, the owner can click "Test Connection" — WhatsBase \
will send a ping to Green API and confirm the instance is online.

### Step 4 — Build (/onboarding/build)
The owner clicks "Build my agent." The Builder agent then:
1. Processes all uploaded product photos with computer vision (GPT-4o-mini)
2. Creates bilingual product records (Hebrew + English)
3. Generates vector embeddings for semantic search
4. Writes a custom system prompt for the WhatsApp agent based on the business \
   info and catalog
5. Runs an automated **self-test**: asks the agent 8 questions about the catalog \
   (e.g. "What is the price of X?", "Is Y in stock?", "What are your hours?")
6. The agent goes **live** only if it passes the self-test

**Why the self-test matters:**
The self-test is a quality gate. It catches problems like: a product's price \
wasn't extracted correctly from a photo, the business hours weren't parsed \
properly, or the retrieval system isn't surfacing the right products. The build \
report shows exactly which of the 8 questions passed or failed and what answer \
the bot gave — so the owner can fix the underlying data and rebuild.

If the build fails:
- Read the report carefully — each failed question shows the wrong answer the \
  bot gave
- Go back to the relevant step (e.g. fix a product's price on the Products page, \
  or clarify hours on the Business Info page)
- Click "Build my agent" again — rebuilds are safe and idempotent (no duplicates)

## Test Chat (/test-chat)
After a successful build, the owner can test the bot in the browser before it \
goes live to customers. This is the exact same AI agent that will run on \
WhatsApp — same knowledge base, same system prompt, same language detection.

## How to answer questions
- **Match the message.** A short greeting ("hi", "hello", "hey") gets a short, \
  warm reply — one or two sentences max. Do not dump the full onboarding overview \
  unprompted. Wait for the user to ask before explaining steps they haven't asked \
  about.
- **Be concise by default.** Answer what was asked, nothing more. Only elaborate \
  when the user is clearly stuck or asks for detail.
- Be specific and practical. Give step-by-step instructions when the user seems \
  stuck.
- If the user writes in Hebrew, reply in Hebrew. If in English, reply in English.
- No excessive emoji. One emoji per reply at most, only when it genuinely helps \
  the tone. Never use bullet-point emoji lists unless the user asked for a list.
- For Green API questions, you can walk through the dashboard flow even though \
  you cannot see it — describe what to look for.
- If you don't know something about the user's specific account or data, say so \
  clearly and suggest they check the relevant page or contact support.
- Never invent prices, stock levels, or catalog data — you don't have access to \
  the owner's actual catalog in this chat.
- Keep answers focused on WhatsBase onboarding. For unrelated questions, \
  politely redirect to the task at hand.
"""


def _get_anthropic_client():
    from anthropic import Anthropic
    from app.core.config import get_settings

    return Anthropic(api_key=get_settings().anthropic_api_key)


def _map_build_run(row: BuildRun) -> BuildRunResponse:
    raw_report = row.report or {}
    ui_progress = int(raw_report.get("ui_progress_pct", 0 if row.status == "queued" else 100 if row.status in {"passed", "failed"} else 10))
    ui_step = raw_report.get("ui_current_step")
    report = _map_build_report(raw_report) if row.status in {"passed", "failed"} else None
    return BuildRunResponse(
        id=row.id,
        status=row.status,  # type: ignore[arg-type]
        current_step=ui_step,
        progress_pct=ui_progress,
        report=report,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_build_report(raw_report: dict) -> BuildReportResponse | None:
    if not raw_report:
        return None

    questions = raw_report.get("self_test", {}).get("questions", [])
    mapped_questions: list[BuildQuestionResultResponse] = []
    for question in questions:
        answer_summary = (
            question.get("got", {}).get("behavior_note")
            or question.get("got", {}).get("llm_response_snippet")
            or question.get("got", {}).get("retrieval_note")
            or ""
        )
        mapped_questions.append(
            BuildQuestionResultResponse(
                question=str(question.get("q", "")),
                answer_summary=str(answer_summary),
                passed=bool(question.get("ok", False)),
            )
        )

    return BuildReportResponse(
        products_detected=len(raw_report.get("found", [])),
        products_created=len(raw_report.get("created", [])),
        assumptions=list(raw_report.get("assumed", [])),
        self_test=mapped_questions,
    )


async def _get_or_create_test_chat_conversation(
    session: AsyncSession,
    tenant_id: str,
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_phone == _TEST_CHAT_PHONE,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is not None:
        return conversation

    conversation = Conversation(
        tenant_id=tenant_id,
        customer_phone=_TEST_CHAT_PHONE,
        status="open",
        last_message_at=datetime.now(timezone.utc),
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def _get_or_create_setup_chat_conversation(
    session: AsyncSession,
    tenant_id: str,
) -> Conversation:
    result = await session.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_phone == _SETUP_CHAT_PHONE,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is not None:
        return conversation

    conversation = Conversation(
        tenant_id=tenant_id,
        customer_phone=_SETUP_CHAT_PHONE,
        status="open",
        last_message_at=datetime.now(timezone.utc),
    )
    session.add(conversation)
    await session.flush()
    return conversation


def _detect_hebrew(text: str) -> bool:
    return bool(re.search(r"[\u0590-\u05FF]", text))


_CASUAL_GREETING_RE = re.compile(
    r"^(?:"
    # Hebrew greetings / small talk
    r"מה\s*נשמע|מה\s*קורה|מה\s*המצב|מה\s*עושה|"
    r"שלום(?:\s+עולם)?|היי|הי|בוקר\s*טוב|ערב\s*טוב|לילה\s*טוב|"
    r"תודה(?:\s*רבה)?|תודה\s*על\s*הכל|"
    # English greetings / small talk
    r"hi|hello|hey|yo|sup|thanks?|thank\s*you|thx|"
    r"how(?:'s|\s+is)\s+it\s+going|how\s+are\s+you(?:\s+doing)?|"
    r"what'?s\s+up|good\s+(?:morning|evening|afternoon|night)"
    r")(?:[!?.…,]*)$",
    re.IGNORECASE | re.UNICODE,
)


def _is_casual_greeting(text: str) -> bool:
    """True when the message is small talk — skip catalog retrieval and product cards."""
    normalized = text.strip()
    if not normalized:
        return True
    if len(normalized) <= 4 and normalized.casefold() in {"hi", "hey", "yo", "ok", "הי", "היי"}:
        return True
    return bool(_CASUAL_GREETING_RE.match(normalized))


def _format_catalog_context(hits: list[ProductHit]) -> str:
    if not hits:
        return "(no matching products found)"
    lines: list[str] = []
    for hit in hits:
        title = hit.name_en or hit.name_he or "Unknown product"
        price = f"{float(hit.price)} {hit.currency}" if hit.price is not None else "price unknown"
        stock = "in_stock" if hit.in_stock else "out_of_stock"
        image = hit.image_urls[0] if hit.image_urls else ""
        lines.append(
            f"- id={hit.product_id}; title={title}; category={hit.category or ''}; "
            f"price={price}; stock={stock}; image={image}"
        )
    return "\n".join(lines)


def _build_cards_from_hits(hits: list[ProductHit]) -> list[ProductCardResponse] | None:
    cards = [
        ProductCardResponse(
            id=hit.product_id,
            image_url=hit.image_urls[0] if hit.image_urls else None,
            name_he=hit.name_he or "",
            name_en=hit.name_en or "",
            price=float(hit.price or 0),
            currency=hit.currency,
            category=hit.category,
        )
        for hit in hits[:3]
    ]
    return cards or None


@observe(name="api.test_chat.reply")
async def _generate_agent_reply(
    *,
    tenant_id: str,
    system_prompt: str,
    user_text: str,
    recent_messages: list[Message],
) -> tuple[str, list[ProductCardResponse] | None]:
    update_trace(tenant_id=tenant_id)
    search_catalog = not _is_casual_greeting(user_text)
    if search_catalog:
        query_filters = infer_query_filters(user_text)
        hits = await retrieval_search(
            tenant_id=tenant_id,
            query=user_text,
            filters=query_filters,
            k=5,
        )
        catalog_hits = filter_relevant_hits(user_text, hits)
        catalog_context = _format_catalog_context(catalog_hits)
    else:
        hits = []
        catalog_hits = []
        catalog_context = "(no catalog lookup — casual greeting; reply warmly without listing products)"

    model_cfg = get_model("conversation")
    conversation_system = system_prompt
    guardrail = (
        "You are answering in the tenant owner's TEST CHAT. "
        "Use only the provided catalog context for prices/stock. "
        "If information is missing, say you do not know and suggest asking a human."
    )
    if not search_catalog:
        guardrail += (
            " The customer sent a casual greeting — do not mention products, prices, or stock."
        )

    formatted_history: list[dict] = []
    for row in recent_messages[-12:]:
        role = "user" if row.direction == "inbound" else "assistant"
        formatted_history.append({"role": role, "content": row.content or ""})
    formatted_history.append({"role": "user", "content": user_text})

    def _call():
        client = _get_anthropic_client()
        return client.messages.create(
            model=model_cfg.name,
            max_tokens=model_cfg.max_tokens or 1024,
            temperature=model_cfg.temperature or 0.2,
            system=f"{conversation_system}\n\n{guardrail}\n\nCatalog context:\n{catalog_context}",
            messages=formatted_history,
        )

    response = await asyncio.to_thread(_call)
    chunks: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            chunks.append(block.text)
    reply_text = "\n".join(chunks).strip()
    if not reply_text:
        reply_text = (
            "אני לא בטוח לגבי התשובה כרגע. אפשר לנסות לנסח את השאלה אחרת?"
            if _detect_hebrew(user_text)
            else "I am not fully sure yet. Can you rephrase the question?"
        )

    if search_catalog:
        card_hits = select_card_hits(user_text, reply_text, catalog_hits)
        cards = _build_cards_from_hits(card_hits)
    else:
        cards = None
    return reply_text, cards


@observe(name="api.setup_assistant.reply")
async def _generate_setup_assistant_reply(
    *,
    user_text: str,
    recent_messages: list[Message],
) -> str:
    model_cfg = get_model("setup_assistant")
    formatted_history: list[dict] = []
    for row in recent_messages[-12:]:
        role = "user" if row.direction == "inbound" else "assistant"
        formatted_history.append({"role": role, "content": row.content or ""})
    formatted_history.append({"role": "user", "content": user_text})

    def _call():
        client = _get_anthropic_client()
        return client.messages.create(
            model=model_cfg.name,
            max_tokens=model_cfg.max_tokens or 1024,
            temperature=model_cfg.temperature or 0.3,
            system=_SETUP_ASSISTANT_SYSTEM_PROMPT,
            messages=formatted_history,
        )

    response = await asyncio.to_thread(_call)
    chunks: list[str] = []
    for block in response.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            chunks.append(block.text)
    reply = "\n".join(chunks).strip()
    if reply:
        return reply
    return (
        "אשמח לעזור בשלבי ההקמה: פרטי עסק, מוצרים, חיבור וואטסאפ ובנייה."
        if _detect_hebrew(user_text)
        else "I can help with setup: business info, products, WhatsApp connect, and build."
    )


@router.post("/build", response_model=BuildRunResponse)
async def start_build(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> BuildRunResponse:
    tenant_id = require_tenant(ctx)

    agent_result = await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        agent = Agent(tenant_id=tenant_id, status="building")
        session.add(agent)
    else:
        agent.status = "building"

    build_run = BuildRun(
        tenant_id=tenant_id,
        status="queued",
        input_manifest={"source": "api", "catalog_source": "api"},
        report={"ui_progress_pct": 5, "ui_current_step": "collect_assets"},
        started_at=datetime.now(timezone.utc),
    )
    session.add(build_run)
    await session.commit()
    await session.refresh(build_run)

    try:
        redis = await get_redis_pool()
        try:
            await redis.enqueue_job(
                "run_build",
                {"tenant_id": tenant_id, "build_run_id": build_run.id},
            )
        finally:
            await redis.aclose()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unable to enqueue run_build for tenant=%s: %s", tenant_id, exc)

    return _map_build_run(build_run)


@router.get("/build-runs/latest", response_model=BuildRunResponse | None)
async def get_latest_build_run(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> BuildRunResponse | None:
    tenant_id = require_tenant(ctx)
    result = await session.execute(
        select(BuildRun)
        .where(BuildRun.tenant_id == tenant_id)
        .order_by(BuildRun.created_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return _map_build_run(row)


@router.get("/build-runs/{build_run_id}", response_model=BuildRunResponse)
async def get_build_run(
    build_run_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> BuildRunResponse:
    tenant_id = require_tenant(ctx)
    result = await session.execute(
        select(BuildRun).where(
            BuildRun.id == build_run_id,
            BuildRun.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Build run not found")
    return _map_build_run(row)


@router.patch("/build-runs/{build_run_id}", response_model=BuildRunResponse)
async def patch_build_run(
    build_run_id: str,
    payload: BuildRunPatchRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> BuildRunResponse:
    tenant_id = require_tenant(ctx)
    result = await session.execute(
        select(BuildRun).where(
            BuildRun.id == build_run_id,
            BuildRun.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Build run not found")

    if payload.status in {"passed", "failed"}:
        raise HTTPException(
            status_code=400,
            detail="Build status can only be set by the builder worker — poll GET /api/build-runs/{id}",
        )

    row.status = payload.status
    report = dict(row.report or {})
    report["ui_progress_pct"] = payload.progress_pct
    report["ui_current_step"] = payload.current_step
    row.report = report

    agent_result = await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        agent = Agent(tenant_id=tenant_id, status="building")
        session.add(agent)
    else:
        agent.status = "building"

    await session.commit()
    await session.refresh(row)
    return _map_build_run(row)


@router.get("/agents/status", response_model=AgentStatusResponse)
async def get_agent_status(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> AgentStatusResponse:
    tenant_id = require_tenant(ctx)
    result = await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    agent = result.scalar_one_or_none()
    if agent is None:
        return AgentStatusResponse(status="building")
    return AgentStatusResponse(status=agent.status)  # type: ignore[arg-type]


@router.post("/test-chat", response_model=TestChatResponse)
async def send_test_chat_message(
    payload: TestChatRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> TestChatResponse:
    tenant_id = require_tenant(ctx)
    agent_result = await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None or agent.status != "live" or not agent.system_prompt:
        raise HTTPException(
            status_code=409,
            detail="Agent is not live yet. Complete a successful build before test chat.",
        )
    system_prompt = agent.system_prompt

    conversation = await _get_or_create_test_chat_conversation(session, tenant_id)
    history_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    history_rows = history_result.scalars().all()

    now = datetime.now(timezone.utc)
    clean_text = payload.text.strip()
    user_msg = Message(
        conversation_id=conversation.id,
        direction="inbound",
        type="text",
        content=clean_text,
    )
    session.add(user_msg)
    reply_text, reply_cards = await _generate_agent_reply(
        tenant_id=tenant_id,
        system_prompt=system_prompt,
        user_text=clean_text,
        recent_messages=history_rows,
    )

    assistant_msg = Message(
        conversation_id=conversation.id,
        direction="outbound",
        type="text",
        content=reply_text,
        media_url=(
            json.dumps(
                [
                    {
                        "id": card.id,
                        "image_url": card.image_url,
                        "name_he": card.name_he,
                        "name_en": card.name_en,
                        "price": card.price,
                        "currency": card.currency,
                        "category": card.category,
                    }
                    for card in (reply_cards or [])
                ]
            )
            if reply_cards
            else None
        ),
    )
    session.add(assistant_msg)
    conversation.last_message_at = now

    await session.commit()
    await session.refresh(assistant_msg)

    return TestChatResponse(
        reply=TestChatMessageResponse(
            id=assistant_msg.id,
            role="assistant",
            text=assistant_msg.content or "",
            created_at=assistant_msg.created_at,
            cards=reply_cards,
        )
    )


@router.post("/setup-assistant/chat", response_model=TestChatResponse)
async def send_setup_assistant_message(
    payload: TestChatRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> TestChatResponse:
    tenant_id = ctx.user_row.tenant_id if ctx.user_row else None
    if not tenant_id:
        reply_text = await _generate_setup_assistant_reply(
            user_text=payload.text.strip(),
            recent_messages=[],
        )
        return TestChatResponse(
            reply=TestChatMessageResponse(
                id=f"setup_{int(datetime.now(timezone.utc).timestamp())}",
                role="assistant",
                text=reply_text,
                created_at=datetime.now(timezone.utc),
                cards=None,
            )
        )
    conversation = await _get_or_create_setup_chat_conversation(session, tenant_id)

    history_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    history_rows = history_result.scalars().all()

    clean_text = payload.text.strip()
    now = datetime.now(timezone.utc)
    user_msg = Message(
        conversation_id=conversation.id,
        direction="inbound",
        type="text",
        content=clean_text,
    )
    session.add(user_msg)

    reply_text = await _generate_setup_assistant_reply(
        user_text=clean_text,
        recent_messages=history_rows,
    )
    assistant_msg = Message(
        conversation_id=conversation.id,
        direction="outbound",
        type="text",
        content=reply_text,
    )
    session.add(assistant_msg)
    conversation.last_message_at = now

    await session.commit()
    await session.refresh(assistant_msg)

    return TestChatResponse(
        reply=TestChatMessageResponse(
            id=assistant_msg.id,
            role="assistant",
            text=assistant_msg.content or "",
            created_at=assistant_msg.created_at,
            cards=None,
        )
    )


@router.get("/setup-assistant/history", response_model=list[TestChatMessageResponse])
async def get_setup_assistant_history(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[TestChatMessageResponse]:
    tenant_id = ctx.user_row.tenant_id if ctx.user_row else None
    if not tenant_id:
        return []
    result = await session.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_phone == _SETUP_CHAT_PHONE,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return []

    msg_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    rows = msg_result.scalars().all()
    return [
        TestChatMessageResponse(
            id=row.id,
            role="user" if row.direction == "inbound" else "assistant",
            text=row.content or "",
            created_at=row.created_at,
            cards=None,
        )
        for row in rows
    ]


@router.get("/test-chat/history", response_model=list[TestChatMessageResponse])
async def get_test_chat_history(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[TestChatMessageResponse]:
    tenant_id = require_tenant(ctx)
    result = await session.execute(
        select(Conversation).where(
            Conversation.tenant_id == tenant_id,
            Conversation.customer_phone == _TEST_CHAT_PHONE,
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        return []

    msg_result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
    )
    rows = msg_result.scalars().all()

    history: list[TestChatMessageResponse] = []
    for row in rows:
        cards: list[ProductCardResponse] | None = None
        if row.direction == "outbound" and row.media_url:
            try:
                raw_cards = json.loads(row.media_url)
                cards = [
                    ProductCardResponse(
                        id=str(item.get("id", "")),
                        image_url=item.get("image_url"),
                        name_he=str(item.get("name_he", "")),
                        name_en=str(item.get("name_en", "")),
                        price=float(item.get("price", 0) or 0),
                        currency=str(item.get("currency", "ILS")),
                        category=item.get("category"),
                    )
                    for item in raw_cards
                    if isinstance(item, dict)
                ]
            except Exception:  # noqa: BLE001
                cards = None

        history.append(
            TestChatMessageResponse(
                id=row.id,
                role="user" if row.direction == "inbound" else "assistant",
                text=row.content or "",
                created_at=row.created_at,
                cards=cards,
            )
        )
    return history
