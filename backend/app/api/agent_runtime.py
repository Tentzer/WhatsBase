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
from app.retrieval.search import search as retrieval_search
from app.retrieval.types import ProductHit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["agent-runtime"])

_TEST_CHAT_PHONE = "__test_chat_owner__"
_SETUP_CHAT_PHONE = "__setup_assistant__"
_TEMP_DEFAULT_ASSISTANT_PROMPT = (
    "You are the WhatsBase assistant for onboarding and testing. "
    "Answer only using provided catalog/business context. "
    "Do not invent prices or stock. If missing information, say so clearly."
)


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
    hits = await retrieval_search(tenant_id=tenant_id, query=user_text, k=3)
    cards = _build_cards_from_hits(hits)

    model_cfg = get_model("conversation")
    conversation_system = system_prompt
    guardrail = (
        "You are answering in the tenant owner's TEST CHAT. "
        "Use only the provided catalog context for prices/stock. "
        "If information is missing, say you do not know and suggest asking a human."
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
            system=f"{conversation_system}\n\n{guardrail}\n\nCatalog context:\n{_format_catalog_context(hits)}",
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
    return reply_text, cards


@observe(name="api.setup_assistant.reply")
async def _generate_setup_assistant_reply(
    *,
    user_text: str,
    recent_messages: list[Message],
) -> str:
    model_cfg = get_model("conversation")
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
            system=_TEMP_DEFAULT_ASSISTANT_PROMPT,
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
        input_manifest={"source": "api"},
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

    row.status = payload.status
    report = dict(row.report or {})
    report["ui_progress_pct"] = payload.progress_pct
    report["ui_current_step"] = payload.current_step
    row.report = report
    if payload.status in {"passed", "failed"}:
        row.finished_at = datetime.now(timezone.utc)

    agent_result = await session.execute(select(Agent).where(Agent.tenant_id == tenant_id))
    agent = agent_result.scalar_one_or_none()
    if agent is None:
        agent = Agent(tenant_id=tenant_id, status="building")
        session.add(agent)
    if payload.status == "passed":
        agent.status = "live"
    elif payload.status == "failed":
        agent.status = "failed"
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
