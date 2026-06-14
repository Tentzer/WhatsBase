from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthContext, get_auth_context, require_tenant
from app.api.schemas import (
    BusinessInfoItem,
    MeResponse,
    MeUserResponse,
    ProductImageUploadResponse,
    ProductPayload,
    ProductResponse,
    TenantCreateRequest,
    TenantResponse,
    WhatsAppConnectRequest,
    WhatsAppStatusResponse,
)
from app.core.config import get_settings
from app.core.crypto import encrypt_token
from app.core.db import get_session
from app.core.product_images import (
    build_public_storage_url,
    list_orphan_tenant_uploads,
    stable_key_from_upload_object_name,
    upload_owner_image,
)
from app.core.schema import BusinessInfo, Product, ProductImage, Tenant, User, WhatsAppInstance

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["onboarding"])


async def _product_responses_for_tenant(
    session: AsyncSession,
    tenant_id: str,
) -> list[ProductResponse]:
    result = await session.execute(
        select(Product)
        .where(Product.tenant_id == tenant_id)
        .options(selectinload(Product.images))
        .order_by(Product.created_at.asc())
    )
    products = result.scalars().all()
    responses: list[ProductResponse] = []
    for product in products:
        image = product.images[0] if product.images else None
        responses.append(
            ProductResponse(
                id=product.id,
                stable_key=product.stable_key,
                name_he=product.name_he or "",
                name_en=product.name_en or "",
                category=product.category or "",
                price=float(product.price or 0),
                currency=product.currency,
                in_stock=product.in_stock,
                colors=str((product.attributes or {}).get("colors", "")),
                materials=str((product.attributes or {}).get("materials", "")),
                style=str((product.attributes or {}).get("style", "")),
                image=(
                    None
                    if image is None
                    else {
                        "file_name": None,
                        "storage_path": image.storage_path,
                        "public_url": image.public_url,
                    }
                ),
            )
        )
    return responses


@router.get("/debug")
async def debug_auth(
    ctx: AuthContext = Depends(get_auth_context),
) -> dict:
    """Return auth context details (no secrets) for diagnosing onboarding issues."""
    return {
        "supabase_user_id": ctx.supabase_user_id,
        "email": ctx.email,
        "has_user_row": ctx.user_row is not None,
        "user_row_id": str(ctx.user_row.id) if ctx.user_row else None,
        "tenant_id": str(ctx.user_row.tenant_id) if ctx.user_row else None,
    }


@router.get("/me", response_model=MeResponse)
async def get_me(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> MeResponse:
    tenant_resp: TenantResponse | None = None
    tenant_id = ctx.user_row.tenant_id if ctx.user_row else None
    if tenant_id:
        tenant = await session.get(Tenant, tenant_id)
        if tenant:
            tenant_resp = TenantResponse(
                id=tenant.id,
                name=tenant.name,
                description=tenant.description,
                created_at=tenant.created_at,
            )

    user_id = ctx.user_row.id if ctx.user_row else ctx.supabase_user_id
    return MeResponse(
        user=MeUserResponse(user_id=user_id, email=ctx.email, tenant_id=tenant_id),
        tenant=tenant_resp,
    )


@router.post("/tenants", response_model=TenantResponse)
async def create_or_update_tenant(
    payload: TenantCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> TenantResponse:
    tenant_name = payload.name.strip()
    if not tenant_name:
        raise HTTPException(status_code=400, detail="Tenant name is required")

    if ctx.user_row and ctx.user_row.tenant_id:
        tenant = await session.get(Tenant, ctx.user_row.tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant.name = tenant_name
        tenant.description = payload.description
    else:
        tenant = Tenant(name=tenant_name, description=payload.description, status="active", plan="free")
        session.add(tenant)
        await session.flush()

        if not ctx.email:
            raise HTTPException(status_code=400, detail="Authenticated user email is missing")
        user_row = User(
            tenant_id=tenant.id,
            supabase_user_id=ctx.supabase_user_id,
            email=ctx.email,
        )
        session.add(user_row)

    await session.commit()
    await session.refresh(tenant)
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        description=tenant.description,
        created_at=tenant.created_at,
    )


@router.get("/business-info", response_model=list[BusinessInfoItem])
async def get_business_info(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[BusinessInfoItem]:
    tenant_id = require_tenant(ctx)
    result = await session.execute(
        select(BusinessInfo)
        .where(BusinessInfo.tenant_id == tenant_id)
        .order_by(BusinessInfo.created_at.asc())
    )
    rows = result.scalars().all()
    return [
        BusinessInfoItem(
            topic=row.topic,
            content_he=row.content_he or "",
            content_en=row.content_en or "",
        )
        for row in rows
    ]


@router.post("/business-info", response_model=list[BusinessInfoItem])
async def save_business_info(
    payload: list[BusinessInfoItem],
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[BusinessInfoItem]:
    tenant_id = require_tenant(ctx)
    await session.execute(delete(BusinessInfo).where(BusinessInfo.tenant_id == tenant_id))
    for item in payload:
        session.add(
            BusinessInfo(
                tenant_id=tenant_id,
                topic=item.topic,
                content_he=item.content_he,
                content_en=item.content_en,
            )
        )
    await session.commit()
    return payload


@router.post("/products/upload-image", response_model=ProductImageUploadResponse)
async def upload_product_image(
    file: UploadFile = File(...),
    ctx: AuthContext = Depends(get_auth_context),
) -> ProductImageUploadResponse:
    """Upload a product photo to Supabase Storage for step-2 onboarding.

    The image is linked to a product row when the owner saves the catalog via
    POST /api/products (which writes the product_images table).
    """
    tenant_id = require_tenant(ctx)
    filename = (file.filename or "").strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        storage_path, public_url = await upload_owner_image(
            tenant_id,
            filename,
            content,
            file.content_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("product image upload failed for tenant %s", tenant_id)
        raise HTTPException(status_code=500, detail="Image upload failed") from exc

    return ProductImageUploadResponse(
        file_name=filename,
        storage_path=storage_path,
        public_url=public_url,
    )


@router.get("/products", response_model=list[ProductResponse])
async def get_products(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[ProductResponse]:
    tenant_id = require_tenant(ctx)
    return await _product_responses_for_tenant(session, tenant_id)


@router.post("/products/sync-uploads", response_model=list[ProductResponse])
async def sync_products_from_uploads(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[ProductResponse]:
    """Create product rows for photos already uploaded to Storage but not yet saved."""
    tenant_id = require_tenant(ctx)

    linked_result = await session.execute(
        select(ProductImage.storage_path)
        .join(Product, Product.id == ProductImage.product_id)
        .where(Product.tenant_id == tenant_id)
    )
    linked_paths = {row[0] for row in linked_result.all() if row[0]}

    orphans = await list_orphan_tenant_uploads(tenant_id, linked_paths)
    if orphans:
        existing_keys_result = await session.execute(
            select(Product.stable_key).where(Product.tenant_id == tenant_id)
        )
        used_keys = {row[0] for row in existing_keys_result.all() if row[0]}

        pending_images: list[tuple[Product, str]] = []
        for storage_path, storage_name in orphans:
            stable_key = stable_key_from_upload_object_name(storage_name)
            suffix = 1
            base_key = stable_key
            while stable_key in used_keys:
                stable_key = f"{base_key}-{suffix}"
                suffix += 1
            used_keys.add(stable_key)

            product = Product(
                tenant_id=tenant_id,
                stable_key=stable_key,
                currency="ILS",
                in_stock=True,
                source="owner_input",
            )
            session.add(product)
            pending_images.append((product, storage_path))

        await session.flush()

        for product, storage_path in pending_images:
            session.add(
                ProductImage(
                    product_id=product.id,
                    storage_path=storage_path,
                    public_url=build_public_storage_url(storage_path),
                )
            )

        await session.commit()
        logger.info(
            "sync_products_from_uploads: tenant=%s created %d product row(s)",
            tenant_id,
            len(orphans),
        )

    return await _product_responses_for_tenant(session, tenant_id)


@router.post("/products", response_model=list[ProductResponse])
async def save_products(
    payload: list[ProductPayload],
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> list[ProductResponse]:
    tenant_id = require_tenant(ctx)
    stable_keys = [item.stable_key.strip() for item in payload if item.stable_key.strip()]
    if not stable_keys:
        return await _product_responses_for_tenant(session, tenant_id)

    existing_result = await session.execute(
        select(Product)
        .where(Product.tenant_id == tenant_id, Product.stable_key.in_(stable_keys))
        .options(selectinload(Product.images))
    )
    products_by_key = {product.stable_key: product for product in existing_result.scalars().all()}

    created_any = False
    for item in payload:
        stable_key = item.stable_key.strip()
        if not stable_key:
            continue

        product = products_by_key.get(stable_key)
        if product is None:
            product = Product(tenant_id=tenant_id, stable_key=stable_key)
            session.add(product)
            products_by_key[stable_key] = product
            created_any = True

        product.name_he = item.name_he
        product.name_en = item.name_en
        product.category = item.category
        product.price = Decimal(str(item.price))
        product.currency = item.currency
        product.in_stock = item.in_stock
        product.attributes = {
            "colors": item.colors,
            "materials": item.materials,
            "style": item.style,
        }
        product.source = "owner_input"

        image_payload = item.image
        if image_payload is not None:
            image_row = product.images[0] if product.images else None
            if image_row is None:
                image_row = ProductImage(storage_path=image_payload.storage_path)
                session.add(image_row)
                product.images.append(image_row)
            image_row.storage_path = image_payload.storage_path
            image_row.public_url = image_payload.public_url

    if created_any:
        await session.flush()

    await session.commit()
    return await _product_responses_for_tenant(session, tenant_id)


@router.get("/whatsapp/status", response_model=WhatsAppStatusResponse)
async def get_whatsapp_status(
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> WhatsAppStatusResponse:
    tenant_id = require_tenant(ctx)
    result = await session.execute(
        select(WhatsAppInstance)
        .where(WhatsAppInstance.tenant_id == tenant_id)
        .order_by(WhatsAppInstance.updated_at.desc())
    )
    row = result.scalars().first()
    if row is None:
        return WhatsAppStatusResponse(connected=False, phone=None, intake_mode=get_settings().intake_mode)

    return WhatsAppStatusResponse(
        connected=row.status in {"connected", "active"},
        phone=row.phone,
        intake_mode=row.intake_mode,
        checked_at=row.updated_at,
    )


@router.post("/whatsapp/connect", response_model=WhatsAppStatusResponse)
async def connect_whatsapp(
    payload: WhatsAppConnectRequest,
    ctx: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_session),
) -> WhatsAppStatusResponse:
    tenant_id = require_tenant(ctx)
    settings = get_settings()
    if not settings.token_encryption_key:
        raise HTTPException(status_code=500, detail="TOKEN_ENCRYPTION_KEY is not configured")

    encrypted_token = encrypt_token(payload.token, settings.token_encryption_key)

    result = await session.execute(
        select(WhatsAppInstance).where(
            WhatsAppInstance.tenant_id == tenant_id,
            WhatsAppInstance.green_api_instance_id == payload.instance_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = WhatsAppInstance(
            tenant_id=tenant_id,
            green_api_instance_id=payload.instance_id,
            token_encrypted=encrypted_token,
            status="connected",
            intake_mode=settings.intake_mode,
        )
        session.add(row)
    else:
        row.token_encrypted = encrypted_token
        row.status = "connected"
        row.intake_mode = settings.intake_mode
    row.updated_at = datetime.now(tz=timezone.utc)

    await session.commit()
    await session.refresh(row)
    return WhatsAppStatusResponse(
        connected=True,
        phone=row.phone,
        intake_mode=row.intake_mode,
        checked_at=row.updated_at,
    )
