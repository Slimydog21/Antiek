"""Intelligent search over recursive twin substrate (pure).

Term-overlap over caller-supplied twin records only.
remote_index_queried is always False — never invents hits or embeddings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

MatchedField = Literal["insights", "questions", "source_label"]


class TwinIntelligentSearchError(ValueError):
    """Fail-closed validation for twin intelligent search."""


@dataclass(frozen=True)
class TwinSearchHit:
    twin_id: str
    parent_asset_id: str
    matched_fields: tuple[MatchedField, ...]
    score: float
    snippets: tuple[str, ...]


@dataclass(frozen=True)
class TwinSearchResult:
    query: str
    hits: tuple[TwinSearchHit, ...]
    remote_index_queried: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "hits": [
                {
                    "twin_id": h.twin_id,
                    "parent_asset_id": h.parent_asset_id,
                    "matched_fields": list(h.matched_fields),
                    "score": h.score,
                    "snippets": list(h.snippets),
                }
                for h in self.hits
            ],
            "remote_index_queried": False,
            "notes": list(self.notes),
            "authority": "twin_intelligent_search_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinIntelligentSearchError(f"{field} must be a non-empty string")
    return value.strip()


def _tokenize(q: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", q.lower()) if len(t) >= 2]


def _count_overlaps(haystack: str, tokens: list[str]) -> int:
    h = haystack.lower()
    return sum(1 for t in tokens if t in h)


def search_twin_substrate(
    *,
    query: object,
    records: object,
    limit: object = 20,
) -> TwinSearchResult:
    """Search twin substrate records for query terms. Never invents hits."""
    q = _require_nonempty(query, field="query")
    if not isinstance(records, list):
        raise TwinIntelligentSearchError("records must be an array")
    if not isinstance(limit, (int, float)) or isinstance(limit, bool):
        raise TwinIntelligentSearchError(
            "limit must be a positive finite number when set"
        )
    lim = int(limit)
    if lim < 1:
        raise TwinIntelligentSearchError(
            "limit must be a positive finite number when set"
        )

    notes: list[str] = [
        "remote_index_queried=false — pure substrate scan only",
        "hits are term-overlap only (no invent embeddings)",
    ]
    tokens = _tokenize(q)
    if not tokens:
        raise TwinIntelligentSearchError(
            "query must contain at least one token of length >= 2"
        )

    hits: list[TwinSearchHit] = []
    for i, r in enumerate(records):
        if not isinstance(r, dict):
            raise TwinIntelligentSearchError(f"records[{i}] must be an object")
        twin_id = _require_nonempty(r.get("twin_id"), field=f"records[{i}].twin_id")
        parent = _require_nonempty(
            r.get("parent_asset_id"), field=f"records[{i}].parent_asset_id"
        )
        insights = r.get("insights")
        questions = r.get("questions")
        if not isinstance(insights, list) or not isinstance(questions, list):
            raise TwinIntelligentSearchError(
                f"records[{i}].insights and questions must be string arrays"
            )
        for j, ins in enumerate(insights):
            if not isinstance(ins, str):
                raise TwinIntelligentSearchError(
                    f"records[{i}].insights[{j}] must be a string"
                )
        for j, qq in enumerate(questions):
            if not isinstance(qq, str):
                raise TwinIntelligentSearchError(
                    f"records[{i}].questions[{j}] must be a string"
                )

        matched: list[MatchedField] = []
        snippets: list[str] = []
        score = 0.0

        for insight in insights:
            n = _count_overlaps(insight, tokens)
            if n > 0:
                if "insights" not in matched:
                    matched.append("insights")
                score += n
                if len(snippets) < 3:
                    snippets.append(insight.strip()[:200])
        for question in questions:
            n = _count_overlaps(question, tokens)
            if n > 0:
                if "questions" not in matched:
                    matched.append("questions")
                score += n
                if len(snippets) < 3:
                    snippets.append(question.strip()[:200])
        source_label = r.get("source_label")
        if isinstance(source_label, str) and source_label.strip():
            n = _count_overlaps(source_label, tokens)
            if n > 0:
                matched.append("source_label")
                score += n * 0.5

        if score > 0 and matched:
            hits.append(
                TwinSearchHit(
                    twin_id=twin_id,
                    parent_asset_id=parent,
                    matched_fields=tuple(matched),
                    score=score,
                    snippets=tuple(snippets),
                )
            )

    hits.sort(key=lambda h: h.score, reverse=True)
    limited = hits[:lim]
    notes.append(f"hits={len(limited)} of {len(hits)} before limit={lim}")
    notes.append("remote_index_queried=false")

    return TwinSearchResult(
        query=q,
        hits=tuple(limited),
        remote_index_queried=False,
        notes=tuple(notes),
        authority="twin_intelligent_search_advisory",
    )


__all__ = [
    "TwinIntelligentSearchError",
    "TwinSearchHit",
    "TwinSearchResult",
    "search_twin_substrate",
]
