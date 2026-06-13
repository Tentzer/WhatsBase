"""8-question self-test gate for the Builder.

Two layers for every question:
  1. Retrieval assertion: call retrieval.search() with appropriate filters,
     check expected products appear (or expected empty set for out-of-scope).
  2. Behavior check: LLM call at temperature=0 (conversation role), verify the
     response text satisfies the property being tested.

Gate passes only if BOTH layers pass ALL 8 questions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from sqlalchemy import select

from app.builder.context import BuildContext
from app.core.models import get_model
from app.core.observability import get_langfuse, observe
from app.core.schema import Agent, Product

logger = logging.getLogger(__name__)


@dataclass
class SelfTestQuestion:
    q: str                               # question text (sent to retrieval + LLM)
    kind: str                            # "retrieval" | "behavior" — primary check type
    retrieval_filters: dict
    min_hits: int                        # expected minimum retrieval hits (0 = expect empty)
    expected_ids: list[str]              # specific product IDs that must appear in top-k
    behavior_assert: Callable[[str], bool]  # True if LLM response is acceptable
    behavior_hint: str                   # description for the report


@lru_cache(maxsize=1)
def _get_anthropic():
    from anthropic import Anthropic

    return Anthropic(api_key=_settings().anthropic_api_key)


def _settings():
    from app.core.config import get_settings
    return get_settings()


def _normalize_price(s: str) -> str:
    """Strip currency symbols, commas, and whitespace variants so price comparisons are robust."""
    return s.replace("₪", "").replace(",", "").replace(" ", "").replace(" ", "")


# Hebrew Unicode block U+0590–U+05FF.
_HEBREW_RE = re.compile(r"[֐-׿]")


def _question_language_directive(question: str) -> str:
    """Mirror the runtime's per-turn language directive (runtime/guardrails.py
    ``language_directive``) so the self-test behavior call answers in the same
    language as the question — exactly as the real conversation loop does.

    Deliberately duplicated rather than imported: builder/ must never import
    runtime/ (invariant #1). Keep these two strings in sync with
    runtime/guardrails.py::language_directive.
    """
    if _HEBREW_RE.search(question or ""):
        return "The customer wrote in Hebrew. Reply in Hebrew."
    return "The customer wrote in English. Reply in English."


def _build_questions(products: list[Product]) -> list[SelfTestQuestion]:
    """Generate 8 deterministic questions from the real catalog."""

    def _find(category: str | None = None, in_stock: bool | None = None,
               color: str | None = None) -> Product | None:
        for p in products:
            if category and (p.category or "").lower() != category.lower():
                continue
            if in_stock is not None and bool(p.in_stock) != in_stock:
                continue
            if color:
                colors = (p.attributes or {}).get("colors", [])
                if not any(color.lower() in c.lower() for c in colors):
                    continue
            return p
        return None

    white_sofa = _find("sofa", in_stock=True, color="white")
    any_sofa_in = _find("sofa", in_stock=True)
    out_of_stock_sofa = _find("sofa", in_stock=False)
    bed = _find("bed")
    lamp = _find("lamp")
    any_in_stock_cheap = next(
        (p for p in products if p.in_stock and p.price is not None and p.price < 1500),
        None,
    )

    anchor_sofa = white_sofa or any_sofa_in
    anchor_price = float(anchor_sofa.price) if anchor_sofa and anchor_sofa.price else None

    def _price_str(p: float | None) -> str:
        if p is None:
            return "price"
        return str(int(p)) if p == int(p) else str(p)

    questions: list[SelfTestQuestion] = [
        # Q1: English attribute — must find the anchor sofa
        SelfTestQuestion(
            q="Do you have a white sofa?",
            kind="retrieval",
            retrieval_filters={"category": "sofa"},
            min_hits=1,
            expected_ids=[anchor_sofa.id] if anchor_sofa else [],
            behavior_assert=lambda r: any(
                w in r.lower() for w in ["sofa", "sofas", "ספה", "ספות", "couch"]
            ),
            behavior_hint="Response mentions a sofa",
        ),
        # Q2: Hebrew — same query, same expected product
        SelfTestQuestion(
            q="יש לכם ספה לבנה?",
            kind="retrieval",
            retrieval_filters={"category": "sofa"},
            min_hits=1,
            expected_ids=[anchor_sofa.id] if anchor_sofa else [],
            behavior_assert=lambda r: any(
                w in r for w in ["ספה", "ספות", "sofa", "couch"]
            ),
            behavior_hint="Hebrew response mentions a sofa",
        ),
        # Q3: Out-of-stock honesty — must report not available
        SelfTestQuestion(
            q="Do you have a cream sofa?",
            kind="behavior",
            retrieval_filters={"category": "sofa"},
            min_hits=0 if out_of_stock_sofa is None else 1,
            expected_ids=[out_of_stock_sofa.id] if out_of_stock_sofa else [],
            behavior_assert=lambda r: any(
                w in r.lower()
                for w in ["out of stock", "out-of-stock", "sold out", "not available",
                          "unavailable", "not in stock",
                          "אזל", "לא זמין", "אין במלאי", "לא במלאי", "אזל מהמלאי", "אינו זמין"]
            ),
            behavior_hint="Response reports out-of-stock (no false availability claim)",
        ),
        # Q4: Price exactness — must cite exact price
        SelfTestQuestion(
            q="How much is the white sofa?",
            kind="behavior",
            retrieval_filters={"category": "sofa"},
            min_hits=1,
            expected_ids=[anchor_sofa.id] if anchor_sofa else [],
            behavior_assert=lambda r: (
                _price_str(anchor_price) in _normalize_price(r) if anchor_price else True
            ),
            behavior_hint=f"Response cites exact price ({_price_str(anchor_price)})",
        ),
        # Q5: Category breadth — must find a bed
        SelfTestQuestion(
            q="Do you have any bed frames?",
            kind="retrieval",
            retrieval_filters={"category": "bed"},
            min_hits=1 if bed else 0,
            expected_ids=[bed.id] if bed else [],
            behavior_assert=lambda r: any(
                w in r.lower() for w in ["bed", "beds", "מיטה", "מיטות", "frame", "frames", "מסגרת", "מסגרות"]
            ),
            behavior_hint="Response mentions beds/bed frames",
        ),
        # Q6: Out-of-scope — must decline and offer handoff
        SelfTestQuestion(
            q="Do you sell mattresses?",
            kind="behavior",
            retrieval_filters={},
            min_hits=0,
            expected_ids=[],
            behavior_assert=lambda r: not any(
                w in r.lower() for w in ["yes, we sell", "we have mattresses", "our mattresses"]
            ) and any(
                w in r.lower()
                for w in ["don't", "do not", "no mattress", "unfortunately", "human", "contact",
                          "representative",
                          "אין לנו", "מצטער", "לא מוכר", "אנחנו לא", "לא קיים"]
            ),
            behavior_hint="Response politely declines and offers handoff (no invented mattress info)",
        ),
        # Q7: Price-range filter — lamps under 1000
        SelfTestQuestion(
            q="Lamps under 1000 shekels",
            kind="retrieval",
            retrieval_filters={"category": "lamp", "price_max": 1000},
            min_hits=1 if (lamp and lamp.price and lamp.price < 1000) else 0,
            expected_ids=[lamp.id] if (lamp and lamp.price and lamp.price < 1000) else [],
            behavior_assert=lambda r: any(
                w in r.lower() for w in ["lamp", "lamps", "מנורה", "מנורות", "light", "תאורה"]
            ) if lamp and lamp.price and lamp.price < 1000 else True,
            behavior_hint="Price-range filter returns lamp(s) under 1000",
        ),
        # Q8: Compound filter — in_stock + price_max
        SelfTestQuestion(
            q="What's in stock under 1500 shekels?",
            kind="retrieval",
            retrieval_filters={"in_stock": True, "price_max": 1500},
            min_hits=1 if any_in_stock_cheap else 0,
            expected_ids=[any_in_stock_cheap.id] if any_in_stock_cheap else [],
            behavior_assert=lambda r: len(r) > 10,  # non-empty response
            behavior_hint="Compound filter (in_stock + price_max) returns results",
        ),
    ]
    return questions


async def run_self_test(ctx: BuildContext) -> str:
    """Run the 8-question self-test. Updates ctx.self_test_passed and the report."""
    if ctx.dry_run:
        logger.info("[dry-run] would run self-test — skipping (no products in DB)")
        ctx.self_test_passed = True
        ctx.report.self_test = {"passed": True, "dry_run": True, "questions": []}
        return json.dumps({"passed": True, "dry_run": True, "questions_passed": 0, "total": 0})

    from app.retrieval.search import search

    session = ctx.session

    # Load tenant products.
    products_result = await session.execute(
        select(Product).where(Product.tenant_id == ctx.tenant_id)
    )
    products = products_result.scalars().all()

    if not products:
        ctx.self_test_passed = False
        ctx.report.self_test = {"passed": False, "questions": [],
                                "error": "No products found — index_embeddings must run first"}
        return json.dumps({"passed": False, "error": "No products indexed"})

    # Load system prompt.
    agent_result = await session.execute(
        select(Agent).where(Agent.tenant_id == ctx.tenant_id)
    )
    agent = agent_result.scalar_one_or_none()
    system_prompt = agent.system_prompt if agent else "You are a helpful sales assistant."

    questions = _build_questions(list(products))
    results = []
    all_ok = True

    for q in questions:
        q_result = await _check_question(ctx, q, system_prompt)
        results.append(q_result)
        got = q_result["got"]
        if q_result["ok"]:
            logger.info("  [OK  ] %s  %r", q.kind, q.q)
        else:
            all_ok = False
            note = got.get("retrieval_note") or got.get("behavior_note") or ""
            note_str = note.split("\n")[0][:80] if note else ""
            logger.warning("  [FAIL] %s  %r%s", q.kind, q.q,
                           f" — {note_str}" if note_str else "")

    ctx.self_test_passed = all_ok
    ctx.report.self_test = {"passed": all_ok, "questions": results}

    logger.info(
        "self-test: %s (%d/%d passed)",
        "PASSED" if all_ok else "FAILED",
        sum(1 for r in results if r["ok"]),
        len(results),
    )
    return json.dumps({"passed": all_ok, "questions_passed": sum(1 for r in results if r["ok"]),
                       "total": len(results)})


async def _check_question(
    ctx: BuildContext, q: SelfTestQuestion, system_prompt: str
) -> dict:
    from app.retrieval.search import search

    # --- Layer 1: Retrieval assertion ---
    retrieval_ok = True
    retrieval_note = ""
    hits = []
    try:
        filters = dict(q.retrieval_filters) if q.retrieval_filters else None
        hits = await search(ctx.tenant_id, q.q, filters=filters, k=5)
        hit_ids = [h.product_id for h in hits]

        if q.min_hits > 0 and len(hits) < q.min_hits:
            retrieval_ok = False
            retrieval_note = f"expected ≥{q.min_hits} hits, got {len(hits)}"
        elif q.expected_ids:
            missing = [eid for eid in q.expected_ids if eid not in hit_ids]
            if missing:
                retrieval_ok = False
                retrieval_note = f"expected product IDs not in top-k: {missing}"
        elif q.min_hits == 0 and hits:
            # Out-of-scope: retrieval returning results is fine (we check behavior)
            pass
    except Exception as exc:
        retrieval_ok = False
        retrieval_note = f"retrieval error: {exc}"

    # --- Layer 2: Behavior check ---
    behavior_ok = True
    behavior_note = ""
    llm_response = ""
    try:
        retrieval_context = _format_retrieval_context(hits)
        llm_response = await _behavior_call(system_prompt, q.q, retrieval_context)
        behavior_ok = q.behavior_assert(llm_response)
        if not behavior_ok:
            behavior_note = f"behavior check failed: {q.behavior_hint}"
    except Exception as exc:
        behavior_ok = False
        behavior_note = f"behavior call error: {exc}"

    ok = retrieval_ok and behavior_ok
    return {
        "q": q.q,
        "kind": q.kind,
        "expected": {"min_hits": q.min_hits, "hint": q.behavior_hint},
        "got": {
            "retrieval_hits": len(hits),
            "retrieval_ok": retrieval_ok,
            "retrieval_note": retrieval_note,
            "behavior_ok": behavior_ok,
            "behavior_note": behavior_note,
            "llm_response_snippet": llm_response[:200],
        },
        "ok": ok,
    }


@observe(as_type="generation")
async def _behavior_call(system_prompt: str, question: str, retrieval_context: str) -> str:
    """One-shot conversation-role call at temperature=0 (deterministic gate)."""
    model_cfg = get_model("conversation")
    client = _get_anthropic()

    user_content = (
        f"Customer question: {question}\n\n"
        f"Available product information from search:\n{retrieval_context}"
    )

    # Append the language directive the real runtime uses, so the harness mirrors
    # the question's language (English question → English answer) instead of
    # drifting into Hebrew — the drift that made out-of-scope checks flaky.
    full_system = f"{system_prompt}\n\n{_question_language_directive(question)}"

    def _call():
        return client.messages.create(
            model=model_cfg.name,
            max_tokens=512,
            temperature=0,  # override: self-test must be deterministic
            system=full_system,
            messages=[{"role": "user", "content": user_content}],
        )

    resp = await asyncio.to_thread(_call)

    lf = get_langfuse()
    if lf is not None:
        try:
            lf.update_current_generation(
                model=model_cfg.name,
                usage_details={
                    "input": resp.usage.input_tokens,
                    "output": resp.usage.output_tokens,
                },
            )
        except Exception:
            pass

    return resp.content[0].text if resp.content else ""


def _format_retrieval_context(hits) -> str:
    if not hits:
        return "(no relevant products found)"
    lines = []
    for h in hits:
        name = h.name_en or h.name_he or "Unknown"
        price_str = f"{h.price} {h.currency}" if h.price else "price unknown"
        stock = "in stock" if h.in_stock else "OUT OF STOCK"
        lines.append(f"- {name}: {price_str}, {stock}")
    return "\n".join(lines)
