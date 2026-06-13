"""Post-retrieval relevance filtering for test chat and runtime."""

from __future__ import annotations

import re

from app.retrieval.types import ProductHit

_COLOR_ALIASES: dict[str, tuple[str, ...]] = {
    "white": ("white", "off-white", "off white", "לבן", "לבנה", "לבנים", "לבן"),
    "cream": ("cream", "שמנת", "קרם", "ivory", "בז"),
    "black": ("black", "שחור", "שחורה", "שחורים"),
    "brown": ("brown", "חום", "עץ"),
    "gray": ("gray", "grey", "אפור"),
    "blue": ("blue", "כחול"),
    "green": ("green", "ירוק"),
}

_CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "sofa": ("sofa", "sofas", "ספה", "ספות", "כורסא", "כורסה"),
    "bed": ("bed", "beds", "מיטה", "מיטות"),
    "chair": ("chair", "armchair", "כורסא", "כיסא"),
    "table": ("table", "שולחן"),
    "lamp": ("lamp", "מנורה", "מנורות"),
    "bookshelf": ("bookshelf", "bookcase", "מדף", "ספרייה"),
}


def _normalize(text: str) -> str:
    text = re.sub(r"[*_`]", "", text)
    return re.sub(r"\s+", " ", text.strip().lower())


def infer_query_filters(query: str) -> dict:
    """Best-effort structured filters from natural-language product queries."""
    normalized = _normalize(query)
    filters: dict = {}

    colors: list[str] = []
    for color, terms in _COLOR_ALIASES.items():
        if any(term in normalized for term in terms):
            colors.append(color)
    if colors:
        filters["colors"] = colors

    for category, terms in _CATEGORY_ALIASES.items():
        if any(term in normalized for term in terms):
            filters["category"] = category
            break

    return filters


def _hit_color_text(hit: ProductHit) -> str:
    parts = [hit.name_en or "", hit.name_he or "", " ".join(hit.colors)]
    return _normalize(" ".join(parts))


def _hit_matches_requested_colors(hit: ProductHit, requested_colors: list[str]) -> bool:
    text = _hit_color_text(hit)
    for color in requested_colors:
        aliases = _COLOR_ALIASES.get(color, (color,))
        if any(alias in text for alias in aliases):
            return True
    return False


def _hit_conflicts_with_requested_colors(hit: ProductHit, requested_colors: list[str]) -> bool:
    """True when the hit clearly advertises a different color than requested."""
    text = _hit_color_text(hit)
    for color, aliases in _COLOR_ALIASES.items():
        if color in requested_colors:
            continue
        if any(alias in text for alias in aliases):
            return True
    return False


def filter_relevant_hits(
    query: str,
    hits: list[ProductHit],
    *,
    max_results: int = 3,
    min_relative_score: float = 0.72,
    absolute_min_score: float = 0.22,
) -> list[ProductHit]:
    """Drop weak or intent-mismatched retrieval hits before showing cards."""
    if not hits:
        return []

    filters = infer_query_filters(query)
    requested_colors = filters.get("colors", [])
    working = list(hits)

    if requested_colors:
        color_matched = [h for h in working if _hit_matches_requested_colors(h, requested_colors)]
        if color_matched:
            working = color_matched
        else:
            working = [
                h for h in working if not _hit_conflicts_with_requested_colors(h, requested_colors)
            ] or working

    best_score = working[0].score
    score_floor = max(absolute_min_score, best_score * min_relative_score)
    working = [h for h in working if h.score >= score_floor]

    return working[:max_results]


def hits_mentioned_in_reply(reply: str, hits: list[ProductHit]) -> list[ProductHit]:
    """Keep only products explicitly referenced in the assistant reply text."""
    if not reply.strip() or not hits:
        return []

    normalized_reply = _normalize(reply)
    mentioned: list[ProductHit] = []
    for hit in hits:
        candidates = [hit.name_en, hit.name_he, hit.stable_key]
        for name in candidates:
            if not name:
                continue
            norm_name = _normalize(name)
            if len(norm_name) >= 4 and norm_name in normalized_reply:
                mentioned.append(hit)
                break
    return mentioned


def select_card_hits(query: str, reply: str, hits: list[ProductHit]) -> list[ProductHit]:
    """Choose which retrieval hits become UI product cards."""
    relevant = filter_relevant_hits(query, hits)
    mentioned = hits_mentioned_in_reply(reply, relevant)
    return mentioned or relevant
