"""The conversation agent: a plain while-loop over the Anthropic Messages API
with native tool use. No agent framework.

`run_turn` is channel-agnostic — the WhatsApp worker and the REST test-chat
endpoint both call it. It is the single conversation core for the platform
(extracted and upgraded from the original `api/agent_runtime` test-chat reply).
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from datetime import datetime, timezone

from app.core.models import ModelConfig, get_model
from app.core.observability import get_current_trace_id, get_langfuse, observe, update_trace
from app.runtime import guardrails
from app.runtime import tools as runtime_tools
from app.runtime.context import TurnContext
from app.runtime.types import TurnResult

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6
_HISTORY_WINDOW = 12


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%A %Y-%m-%d %H:%M UTC")


def _format_history(history) -> list[dict]:
    """Map stored Message rows -> Anthropic messages, last N, starting on a user
    turn (the API requires the first message to be a user message)."""
    msgs: list[dict] = []
    for row in list(history)[-_HISTORY_WINDOW:]:
        content = getattr(row, "content", None)
        if not content:
            continue
        role = "user" if getattr(row, "direction", None) == "inbound" else "assistant"
        msgs.append({"role": role, "content": content})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _extract_text(resp) -> str:
    chunks: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            chunks.append(block.text)
    return "\n".join(chunks).strip()


def _get_anthropic_client():
    from anthropic import Anthropic

    from app.core.config import get_settings

    return Anthropic(api_key=get_settings().anthropic_api_key)


async def _call_model(model_cfg: ModelConfig, system: str, messages: list[dict]):
    """One Anthropic Messages API call. Patched in unit tests."""
    lf = get_langfuse()
    obs_ctx = (
        lf.start_as_current_observation(
            name="conversation-llm",
            as_type="generation",
            model=model_cfg.name,
            model_parameters={
                "temperature": model_cfg.temperature if model_cfg.temperature is not None else 0.3,
                "max_tokens": model_cfg.max_tokens or 1024,
            },
        )
        if lf is not None
        else nullcontext()
    )

    def _call():
        client = _get_anthropic_client()
        return client.messages.create(
            model=model_cfg.name,
            max_tokens=model_cfg.max_tokens or 1024,
            temperature=model_cfg.temperature if model_cfg.temperature is not None else 0.3,
            system=system,
            tools=runtime_tools.TOOL_SCHEMAS,
            messages=messages,
        )

    with obs_ctx:
        resp = await asyncio.to_thread(_call)
        if lf is not None:
            try:
                lf.update_current_generation(
                    usage_details={
                        "input": resp.usage.input_tokens,
                        "output": resp.usage.output_tokens,
                    }
                )
            except Exception:  # noqa: BLE001
                pass
    return resp


@observe(name="runtime.run_turn")
async def run_turn(
    *,
    tenant_id: str,
    system_prompt: str,
    history,
    user_text: str,
    ctx: TurnContext,
    model_role: str = "conversation",
    lead_summary: str | None = None,
    agent_type: str = "catalog_sales",
) -> TurnResult:
    """Run one agent turn: native tool-use loop, max iterations, then a graceful
    language-mirrored fallback. Returns the reply text + any cards + handoff."""
    if not tenant_id:
        raise ValueError("tenant_id is required for run_turn")

    lang = guardrails.detect_language(user_text)
    ctx.lang = lang
    update_trace(tenant_id=tenant_id, conversation_id=ctx.conversation_id)

    lead_memory_block = (
        (
            "\n\nLead memory from previous conversations:\n"
            f"{lead_summary}\n\n"
            "Use this as context continuity only. Prefer current-turn facts when there is a conflict."
        )
        if lead_summary
        else ""
    )
    full_system = (
        f"{system_prompt}\n\n"
        f"{guardrails.system_preamble(lang, _now_str(), agent_type)}"
        f"{lead_memory_block}"
    )
    messages = _format_history(history)
    messages.append({"role": "user", "content": user_text})

    model_cfg = get_model(model_role)  # type: ignore[arg-type]

    reply_text = ""
    for _ in range(MAX_ITERATIONS):
        resp = await _call_model(model_cfg, full_system, messages)
        messages.append({"role": "assistant", "content": resp.content})

        tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
        if not tool_uses:
            reply_text = _extract_text(resp)
            break

        tool_results: list[dict] = []
        for tool_use in tool_uses:
            tool_input = getattr(tool_use, "input", None) or {}
            try:
                result = await runtime_tools.dispatch(tool_use.name, tool_input, ctx)
            except Exception as exc:  # noqa: BLE001 -- a tool failing must not crash the turn
                logger.exception("tool %s failed", getattr(tool_use, "name", "?"))
                result = f"Tool error: {exc}"
            tool_results.append(
                {"type": "tool_result", "tool_use_id": tool_use.id, "content": result}
            )
        messages.append({"role": "user", "content": tool_results})

    if not reply_text:
        # A card-only turn still succeeded -- use a neutral line, not the apology.
        reply_text = (
            guardrails.cards_only_reply(lang, ctx.cards) if ctx.cards
            else guardrails.fallback_reply(lang)
        )

    # Price guardrail -- two branches depending on agent_type.
    if agent_type == "lead_qualification":
        # Lead-qual agents must NEVER mention any price.  Any currency-adjacent
        # number in the reply means the model violated the hard rule -- replace.
        if guardrails.any_price_mention(reply_text):
            logger.warning(
                "guardrail blocked price mention in lead_qual turn tenant=%s", tenant_id
            )
            update_trace(guardrail_block="lead_qual_price_mention")
            reply_text = guardrails.fallback_reply(lang)
    else:
        # catalog_sales: only block prices that are NOT backed by a tool result
        # (the model invented them).  Tool-backed prices are always allowed.
        invented = guardrails.unsupported_price_claim(reply_text, ctx.tool_prices)
        if invented is not None:
            logger.warning(
                "guardrail blocked unsupported price %.2f tenant=%s", invented, tenant_id
            )
            update_trace(guardrail_block="unsupported_price")
            reply_text = guardrails.fallback_reply(lang)

    # Emoji guardrail -- mechanical backstop for lead_qualification.
    if agent_type == "lead_qualification":
        reply_text = guardrails.strip_emojis(reply_text)

    return TurnResult(
        reply_text=reply_text,
        cards=list(ctx.cards),
        handoff=ctx.handoff,
        trace_id=get_current_trace_id(),
    )
