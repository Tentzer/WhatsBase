from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, require_tenant
from app.api.schemas import LeadPayload, LeadProductsPayload, LeadResponse, LeadUpdatePayload
from app.core.db import get_session
from app.core.schema import Lead, LeadProduct, Tenant
from app.leads.service import (
    lead_query_for_tenant,
    lead_to_response,
    normalize_phone,
    replace_lead_products,
    validate_tenant_products,
)

router = APIRouter(prefix="/api", tags=["leads"])


@router.get("/leads", response_model=list[LeadResponse])
async def get_leads(
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    product_id: str | None = Query(default=None),
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[LeadResponse]:
    tenant_id = require_tenant(ctx)
    query = lead_query_for_tenant(tenant_id).order_by(Lead.updated_at.desc())
    if status:
        query = query.where(Lead.status == status)
    if q:
        like = f"%{q.strip()}%"
        if like != "%%":
            query = query.where(
                or_(
                    Lead.full_name.ilike(like),
                    Lead.phone_number.ilike(like),
                    Lead.notes.ilike(like),
                )
            )
    if product_id:
        query = query.where(
            Lead.id.in_(
                select(LeadProduct.lead_id).where(LeadProduct.product_id == product_id)
            )
        )
    rows = (await session.execute(query)).scalars().all()
    return [lead_to_response(row) for row in rows]


@router.post("/leads", response_model=LeadResponse)
async def create_lead(
    payload: LeadPayload,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> LeadResponse:
    tenant_id = require_tenant(ctx)
    phone = normalize_phone(payload.phone_number)
    existing = (
        await session.execute(
            lead_query_for_tenant(tenant_id).where(Lead.phone_number == phone)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Lead with this phone already exists")

    business_name = payload.business_name
    if not business_name:
        tenant = await session.get(Tenant, tenant_id)
        business_name = tenant.name if tenant else None

    try:
        valid_products = await validate_tenant_products(
            session, tenant_id=tenant_id, product_ids=payload.product_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    lead = Lead(
        tenant_id=tenant_id,
        full_name=payload.full_name.strip(),
        phone_number=phone,
        status=payload.status,
        did_buy=payload.did_buy,
        business_name=business_name,
        source=payload.source,
        notes=payload.notes,
        next_follow_up_at=payload.next_follow_up_at,
        last_message_sent_at=datetime.now(timezone.utc) if payload.source == "manual" else None,
    )
    session.add(lead)
    await session.flush()
    await replace_lead_products(session, lead_id=lead.id, product_ids=valid_products)
    await session.commit()

    created = (
        await session.execute(lead_query_for_tenant(tenant_id).where(Lead.id == lead.id))
    ).scalar_one()
    return lead_to_response(created)


@router.patch("/leads/{lead_id}", response_model=LeadResponse)
async def update_lead(
    lead_id: str,
    payload: LeadUpdatePayload,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> LeadResponse:
    tenant_id = require_tenant(ctx)
    lead = (
        await session.execute(lead_query_for_tenant(tenant_id).where(Lead.id == lead_id))
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    data = payload.model_dump(exclude_unset=True)
    if "phone_number" in data and data["phone_number"] is not None:
        data["phone_number"] = normalize_phone(data["phone_number"])
    for field, value in data.items():
        setattr(lead, field, value)
    await session.commit()

    updated = (
        await session.execute(lead_query_for_tenant(tenant_id).where(Lead.id == lead_id))
    ).scalar_one()
    return lead_to_response(updated)


@router.put("/leads/{lead_id}/products", response_model=LeadResponse)
async def set_lead_products(
    lead_id: str,
    payload: LeadProductsPayload,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> LeadResponse:
    tenant_id = require_tenant(ctx)
    lead = (
        await session.execute(lead_query_for_tenant(tenant_id).where(Lead.id == lead_id))
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        valid_products = await validate_tenant_products(
            session, tenant_id=tenant_id, product_ids=payload.product_ids
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await replace_lead_products(session, lead_id=lead_id, product_ids=valid_products)
    await session.commit()

    updated = (
        await session.execute(lead_query_for_tenant(tenant_id).where(Lead.id == lead_id))
    ).scalar_one()
    return lead_to_response(updated)


@router.delete("/leads/{lead_id}", status_code=204)
async def delete_lead(
    lead_id: str,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> None:
    tenant_id = require_tenant(ctx)
    lead = (
        await session.execute(select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    await session.delete(lead)
    await session.commit()

