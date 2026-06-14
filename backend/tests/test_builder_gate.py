"""Unit tests for the Builder finalize_build gate and self-test question templating.

No live DB or API keys required — all stubs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Minimal stubs ────────────────────────────────────────────────────────────

class FakeSession:
    def __init__(self):
        self.executed: list = []
        self.added: list = []
        self.committed = 0

    async def execute(self, stmt, params=None):
        self.executed.append(stmt)
        return FakeResult()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1

    async def flush(self):
        pass


class FakeResult:
    def scalar_one_or_none(self):
        return None

    def scalar_one(self):
        return "fake-uuid-1234"

    def scalars(self):
        return self

    def all(self):
        return []


def _make_ctx(self_test_passed: bool = True, dry_run: bool = False) -> Any:
    from app.builder.context import BuildContext
    from app.builder.report import BuildReport

    ctx = BuildContext(
        tenant_id="t-test",
        assets_dir=Path("/tmp/fake"),
        dry_run=dry_run,
        session=FakeSession(),
        report=BuildReport(),
        self_test_passed=self_test_passed,
    )
    return ctx


# ── Gate enforcement ─────────────────────────────────────────────────────────

@pytest.fixture
def self_test_gate_enabled():
    """Gate tests require the self-test to be enforced (not skipped)."""
    with patch("app.builder.tools.finalize.get_settings") as mock_settings:
        mock_settings.return_value.build_skip_self_test = False
        yield


@pytest.mark.asyncio
async def test_finalize_passes_when_self_test_passed():
    from app.builder.tools.finalize import finalize_build

    ctx = _make_ctx(self_test_passed=True)
    result_json = await finalize_build(ctx)
    result = json.loads(result_json)
    assert result["status"] == "passed"
    assert result["agent"] == "live"


@pytest.mark.asyncio
async def test_finalize_refused_when_self_test_not_passed(self_test_gate_enabled):
    from app.builder.tools.finalize import finalize_build

    ctx = _make_ctx(self_test_passed=False)
    result_json = await finalize_build(ctx)
    result = json.loads(result_json)
    assert result["status"] == "failed"
    assert "self-test" in result["reason"].lower()


# ── Parameterized gate: each failing question individually ───────────────────

@pytest.mark.parametrize("failing_q_index", range(8))
@pytest.mark.asyncio
async def test_gate_refused_when_any_single_question_fails(failing_q_index, self_test_gate_enabled):
    """Gate must reject if ANY of the 8 questions fails."""
    from app.builder.tools.finalize import finalize_build
    from app.builder.report import BuildReport

    questions = [
        {"q": f"Question {i}", "kind": "retrieval", "ok": i != failing_q_index,
         "expected": {}, "got": {}}
        for i in range(8)
    ]
    ctx = _make_ctx(self_test_passed=False)
    ctx.report.self_test = {"passed": False, "questions": questions}

    result_json = await finalize_build(ctx)
    result = json.loads(result_json)
    assert result["status"] == "failed", (
        f"Gate should have refused when question {failing_q_index} fails"
    )


@pytest.mark.asyncio
async def test_finalize_passes_when_self_test_skipped_by_config():
    from app.builder.tools.finalize import finalize_build

    ctx = _make_ctx(self_test_passed=False)
    with patch("app.builder.tools.finalize.get_settings") as mock_settings:
        mock_settings.return_value.build_skip_self_test = True
        result_json = await finalize_build(ctx)
    result = json.loads(result_json)
    assert result["status"] == "passed"


@pytest.mark.asyncio
async def test_gate_passes_only_when_all_8_pass():
    from app.builder.tools.finalize import finalize_build
    from app.builder.report import BuildReport

    questions = [
        {"q": f"Question {i}", "kind": "retrieval", "ok": True, "expected": {}, "got": {}}
        for i in range(8)
    ]
    ctx = _make_ctx(self_test_passed=True)
    ctx.report.self_test = {"passed": True, "questions": questions}

    result_json = await finalize_build(ctx)
    result = json.loads(result_json)
    assert result["status"] == "passed"


# ── Question templating ──────────────────────────────────────────────────────

@dataclass
class FakeProduct:
    id: str
    category: str | None = None
    in_stock: bool = True
    price: float | None = None
    attributes: dict = field(default_factory=dict)
    name_en: str | None = None
    name_he: str | None = None
    stable_key: str = ""


def _demo_products() -> list:
    return [
        FakeProduct("p-sofa-white", "sofa", True, 4990.0,
                    {"colors": ["white"]}, "White 3-Seat Sofa", "ספה לבנה תלת-מושבית", "white-3-seat-sofa"),
        FakeProduct("p-sofa-cream", "sofa", False, 4290.0,
                    {"colors": ["cream"]}, "Cream 2-Seat Sofa", "ספה דו-מושבית שמנת", "cream-2-seat-sofa"),
        FakeProduct("p-bed", "bed", True, 3490.0, {}, "Gray Queen Bed Frame", "מסגרת מיטה", "gray-queen-bed"),
        FakeProduct("p-lamp", "lamp", True, 690.0, {}, "Brass Floor Lamp", "מנורת רצפה", "brass-floor-lamp"),
        FakeProduct("p-armchair", "armchair", True, 2290.0, {}, "Brown Armchair", "כורסה", "brown-armchair"),
    ]


def _bed_shop_products() -> list:
    return [
        FakeProduct("p-bed-gray", "bed", True, 2490.0,
                    {"colors": ["gray"]}, "Gray Bed", "מיטה אפורה", "bed-gray-mattress-gift"),
        FakeProduct("p-bed-black", "bed", True, 2690.0,
                    {"colors": ["black"]}, "Black Bed", "מיטה שחורה", "bed-black-mattress-gift"),
        FakeProduct("p-bed-storage", "bed", True, 3190.0,
                    {"colors": ["cream"]}, "Storage Bed", "מיטה עם ארגון", "bed-cream-storage-mattress-gift"),
    ]


def test_question_templating_produces_8_questions():
    from app.builder.validation import _build_questions

    questions = _build_questions(_demo_products())
    assert len(questions) == 8


def test_question_templating_uses_real_product_ids():
    from app.builder.validation import _build_questions

    products = _demo_products()
    questions = _build_questions(products)

    # Q1 should point to the white sofa
    q1 = questions[0]
    assert "p-sofa-white" in q1.expected_ids

    # Q3 (out-of-stock) should point to cream sofa
    q3 = questions[2]
    assert "p-sofa-cream" in q3.expected_ids


def test_question_templating_q6_out_of_scope_has_min_hits_zero():
    from app.builder.validation import _build_questions

    questions = _build_questions(_demo_products())
    q6 = questions[5]  # out-of-scope mattress question
    assert q6.min_hits == 0
    assert q6.expected_ids == []


def test_question_q3_behavior_check_detects_out_of_stock():
    from app.builder.validation import _build_questions

    questions = _build_questions(_demo_products())
    q3 = questions[2]
    # Must pass when response says out of stock
    assert q3.behavior_assert("Sorry, that sofa is out of stock")
    assert q3.behavior_assert("This item is currently not available")
    # Must fail when response implies availability
    assert not q3.behavior_assert("Yes, we have the cream sofa in stock!")


def test_question_q6_behavior_check_rejects_invented_mattress_info():
    from app.builder.validation import _build_questions

    questions = _build_questions(_demo_products())
    q6 = questions[5]
    # Polite decline should pass
    assert q6.behavior_assert("We don't carry mattresses, but I can connect you with a human")
    assert q6.behavior_assert("Unfortunately, we don't sell mattresses.")
    # Invented product info must fail
    assert not q6.behavior_assert("Yes, we sell mattresses in various sizes!")


def test_bed_catalog_uses_bed_anchor_not_sofa():
    from app.builder.validation import _build_questions

    questions = _build_questions(_bed_shop_products())
    assert questions[0].q == "Do you have a gray bed?"
    assert "p-bed-gray" in questions[0].expected_ids
    assert questions[5].q == "Do you sell kitchen refrigerators?"


@pytest.mark.asyncio
async def test_update_ui_progress_does_not_clobber_terminal_build_status():
    from app.builder.context import BuildContext
    from app.builder.progress import update_ui_progress
    from app.builder.report import BuildReport

    row = MagicMock()
    row.status = "passed"
    row.report = {"ui_progress_pct": 100, "ui_current_step": "finalize"}

    session = AsyncMock()
    session.get = AsyncMock(return_value=row)

    ctx = BuildContext(
        tenant_id="t-test",
        assets_dir=Path("/tmp/fake"),
        dry_run=False,
        session=session,
        report=BuildReport(),
        build_run_id="run-1",
    )

    await update_ui_progress(ctx, "finalize_build")

    session.commit.assert_not_called()
