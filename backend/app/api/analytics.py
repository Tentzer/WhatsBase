from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AuthContext, get_auth_context, require_tenant
from app.api.schemas import (
    LangfuseAnalyticsResponse,
    LangfuseDailyUsageRow,
    LangfuseModelCostRow,
)
from app.core.config import get_settings

router = APIRouter(prefix="/api/langfuse", tags=["analytics"])


def _to_float(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _to_int(value: Any) -> int:
    return int(round(_to_float(value)))


def _post_metrics(query: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.langfuse_public_key or not settings.langfuse_secret_key:
        raise HTTPException(status_code=500, detail="Langfuse credentials are not configured")

    host = settings.langfuse_host.rstrip("/")
    auth = base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode("utf-8")
    ).decode("utf-8")
    url = f"{host}/api/public/v2/metrics"
    payload = json.dumps(query).encode("utf-8")

    request = Request(
        url=url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except HTTPError as exc:
        # Some Langfuse deployments expose metrics query through GET+query.
        if exc.code == 405:
            fallback_url = f"{url}?{urlencode({'query': json.dumps(query)})}"
            fallback_request = Request(
                url=fallback_url,
                method="GET",
                headers={"Authorization": f"Basic {auth}"},
            )
            try:
                with urlopen(fallback_request, timeout=20) as response:  # noqa: S310
                    raw = response.read().decode("utf-8")
                    return json.loads(raw)
            except (HTTPError, URLError, json.JSONDecodeError) as fallback_exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Langfuse fallback request failed: {fallback_exc}",
                ) from fallback_exc

        detail = exc.read().decode("utf-8", errors="ignore")
        raise HTTPException(
            status_code=502,
            detail=f"Langfuse metrics request failed ({exc.code}): {detail}",
        ) from exc
    except URLError as exc:
        raise HTTPException(status_code=502, detail=f"Langfuse request error: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"Invalid Langfuse JSON response: {exc}") from exc


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _build_daily_usage(rows: list[dict[str, Any]], now: datetime) -> list[LangfuseDailyUsageRow]:
    day_calls: dict[str, int] = {}
    for row in rows:
        day_key = str(row.get("time_dimension") or row.get("timeDimension") or "")[:10]
        if not day_key:
            continue
        calls = _to_int(row.get("count_countObservations", row.get("count_count", 0)))
        day_calls[day_key] = calls

    output: list[LangfuseDailyUsageRow] = []
    for offset in range(6, -1, -1):
        day = now - timedelta(days=offset)
        day_key = day.strftime("%Y-%m-%d")
        output.append(LangfuseDailyUsageRow(date=day_key, calls=day_calls.get(day_key, 0)))
    return output


@router.get("/analytics", response_model=LangfuseAnalyticsResponse)
async def get_langfuse_analytics(
    ctx: AuthContext = Depends(get_auth_context),
) -> LangfuseAnalyticsResponse:
    require_tenant(ctx)

    if (ctx.email or "").lower() != "roytentzer@gmail.com":
        raise HTTPException(status_code=403, detail="Analytics access denied")

    now = datetime.now(UTC)
    month_start = datetime(now.year, now.month, 1, tzinfo=UTC)
    thirty_days_ago = now - timedelta(days=30)
    six_days_ago = now - timedelta(days=6)

    monthly_total_raw = _post_metrics(
        {
            "view": "observations",
            "metrics": [{"measure": "totalCost", "aggregation": "sum"}],
            "dimensions": [],
            "fromTimestamp": month_start.isoformat(),
            "toTimestamp": now.isoformat(),
            "config": {"row_limit": 1},
        }
    )
    cost_by_model_raw = _post_metrics(
        {
            "view": "observations",
            "metrics": [
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "countObservations", "aggregation": "count"},
            ],
            "dimensions": [{"field": "providedModelName"}],
            "fromTimestamp": thirty_days_ago.isoformat(),
            "toTimestamp": now.isoformat(),
            "orderBy": [{"field": "sum_totalCost", "direction": "desc"}],
            "config": {"row_limit": 20},
        }
    )
    daily_usage_raw = _post_metrics(
        {
            "view": "observations",
            "metrics": [{"measure": "countObservations", "aggregation": "count"}],
            "dimensions": [],
            "timeDimension": {"granularity": "day"},
            "fromTimestamp": six_days_ago.isoformat(),
            "toTimestamp": now.isoformat(),
            "orderBy": [{"field": "time_dimension", "direction": "asc"}],
            "config": {"row_limit": 7},
        }
    )

    monthly_rows = _extract_rows(monthly_total_raw)
    total_cost = 0.0
    if monthly_rows:
        total_cost = _to_float(monthly_rows[0].get("sum_totalCost"))

    model_rows = _extract_rows(cost_by_model_raw)
    cost_by_model = [
        LangfuseModelCostRow(
            model_name=str(row.get("providedModelName") or "Unknown"),
            calls=_to_int(row.get("count_countObservations", row.get("count_count", 0))),
            total_cost_usd=_to_float(row.get("sum_totalCost")),
        )
        for row in model_rows
    ]
    cost_by_model.sort(key=lambda row: row.total_cost_usd, reverse=True)

    daily_rows = _extract_rows(daily_usage_raw)
    daily_usage = _build_daily_usage(daily_rows, now)

    return LangfuseAnalyticsResponse(
        total_cost_this_month_usd=total_cost,
        cost_by_model=cost_by_model,
        daily_usage_last_7_days=daily_usage,
    )
