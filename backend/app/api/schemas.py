from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TenantResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    created_at: datetime


class MeUserResponse(BaseModel):
    user_id: str
    email: str
    tenant_id: str | None = None


class MeResponse(BaseModel):
    user: MeUserResponse
    tenant: TenantResponse | None = None


class BusinessInfoItem(BaseModel):
    topic: Literal["hours", "location", "policy", "faq", "other"]
    content_he: str = ""
    content_en: str = ""


class ProductImagePayload(BaseModel):
    file_name: str | None = None
    storage_path: str
    public_url: str | None = None


class ProductPayload(BaseModel):
    stable_key: str = Field(min_length=1, max_length=255)
    name_he: str = ""
    name_en: str = ""
    category: str = ""
    price: Decimal | float | int = 0
    currency: str = "ILS"
    in_stock: bool = True
    colors: str = ""
    materials: str = ""
    style: str = ""
    image: ProductImagePayload | None = None


class ProductResponse(BaseModel):
    id: str
    stable_key: str
    name_he: str
    name_en: str
    category: str
    price: float
    currency: str
    in_stock: bool
    colors: str
    materials: str
    style: str
    image: ProductImagePayload | None = None


class WhatsAppConnectRequest(BaseModel):
    instance_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1)


class WhatsAppStatusResponse(BaseModel):
    connected: bool
    phone: str | None = None
    intake_mode: str
    checked_at: datetime | None = None
