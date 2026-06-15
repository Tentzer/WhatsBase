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


class ProductImageUploadResponse(BaseModel):
    file_name: str
    storage_path: str
    public_url: str


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


LeadStatus = Literal[
    "pending",
    "contacted",
    "qualified",
    "not_interested",
    "success",
]


class LeadPayload(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    phone_number: str = Field(min_length=3, max_length=32)
    status: LeadStatus = "pending"
    did_buy: bool = False
    business_name: str | None = None
    source: str = "manual"
    notes: str | None = None
    next_follow_up_at: datetime | None = None
    product_ids: list[str] = Field(default_factory=list)


class LeadUpdatePayload(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, min_length=3, max_length=32)
    status: LeadStatus | None = None
    did_buy: bool | None = None
    business_name: str | None = None
    source: str | None = None
    notes: str | None = None
    next_follow_up_at: datetime | None = None
    last_conversation_summary: str | None = None
    last_message_sent_at: datetime | None = None


class LeadProductsPayload(BaseModel):
    product_ids: list[str] = Field(default_factory=list)


class LeadResponse(BaseModel):
    id: str
    full_name: str
    phone_number: str
    status: LeadStatus
    did_buy: bool
    business_name: str | None = None
    source: str
    notes: str | None = None
    next_follow_up_at: datetime | None = None
    last_message_sent_at: datetime | None = None
    last_conversation_summary: str | None = None
    last_reengagement_at: datetime | None = None
    last_reengagement_decision: str | None = None
    reengagement_attempt_count: int = 0
    reengagement_cooldown_until: datetime | None = None
    product_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class LeadAutomationEventResponse(BaseModel):
    id: str
    lead_id: str
    automation_type: str
    decision: str
    reason: str | None = None
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None
    idempotency_key: str
    payload_json: dict = Field(default_factory=dict)
    created_at: datetime


class LeadAutomationSettingsResponse(BaseModel):
    auto_reply_enabled: bool
    reengagement_enabled: bool


class LeadAutomationSettingsUpdateRequest(BaseModel):
    auto_reply_enabled: bool | None = None
    reengagement_enabled: bool | None = None


class WhatsAppConnectRequest(BaseModel):
    instance_id: str = Field(min_length=1, max_length=64)
    token: str = Field(min_length=1)


class WhatsAppStatusResponse(BaseModel):
    connected: bool
    phone: str | None = None
    intake_mode: str
    checked_at: datetime | None = None


class LangfuseModelCostRow(BaseModel):
    model_name: str
    calls: int
    total_cost_usd: float


class LangfuseDailyUsageRow(BaseModel):
    date: str
    calls: int


class LangfuseLatencyRow(BaseModel):
    name: str
    p50_ms: float
    p95_ms: float
    calls: int


class LangfuseAnalyticsResponse(BaseModel):
    total_cost_this_month_usd: float
    cost_by_model: list[LangfuseModelCostRow]
    daily_usage_last_7_days: list[LangfuseDailyUsageRow]
    latency_by_name: list[LangfuseLatencyRow]


class BuildQuestionResultResponse(BaseModel):
    question: str
    answer_summary: str
    passed: bool


class BuildReportResponse(BaseModel):
    products_detected: int
    products_created: int
    assumptions: list[str]
    self_test: list[BuildQuestionResultResponse]


class BuildRunResponse(BaseModel):
    id: str
    status: Literal["queued", "running", "passed", "failed"]
    current_step: Literal[
        "collect_assets",
        "caption_images",
        "index_embeddings",
        "run_self_test",
        "finalize",
    ] | None = None
    progress_pct: int
    report: BuildReportResponse | None = None
    created_at: datetime
    updated_at: datetime


class BuildRunPatchRequest(BaseModel):
    status: Literal["queued", "running", "passed", "failed"]
    progress_pct: int = Field(ge=0, le=100)
    current_step: Literal[
        "collect_assets",
        "caption_images",
        "index_embeddings",
        "run_self_test",
        "finalize",
    ] | None = None


class AgentStatusResponse(BaseModel):
    status: Literal["building", "live", "failed"]


class ProductCardResponse(BaseModel):
    id: str
    image_url: str | None = None
    name_he: str
    name_en: str
    price: float
    currency: str


class TestChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime
    cards: list[ProductCardResponse] | None = None


class TestChatRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class TestChatResponse(BaseModel):
    reply: TestChatMessageResponse


class ClearTestChatResponse(BaseModel):
    deleted: int
