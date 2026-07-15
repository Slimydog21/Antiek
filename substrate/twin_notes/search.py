"""Offline search over twin-document insights and questions.

Pure ranking over a :class:`TwinNotesStore` (or any list of twins). No network,
no LLM. Intended for combining contexts and intelligent search over the
recursive note-taker substrate.

Scoring: bag-of-tokens with simple IDF-ish weighting (document frequency across
the searched twin set). Higher score = better match.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from substrate.twin_notes.store import TwinDocument, TwinNotesStore

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [t.casefold() for t in _TOKEN.findall(text or "")]


@dataclass(frozen=True)
class TwinSearchHit:
    twin_id: str
    parent_asset_id: str
    score: float
    matched_insights: list[str]
    matched_questions: list[str]
    source_label: str


def _doc_text(doc: TwinDocument) -> str:
    # Scope is insights + questions only (not source_label metadata).
    return " ".join(list(doc.insights) + list(doc.questions))


def _df(tokens: Sequence[str], corpus_token_sets: Sequence[set[str]]) -> dict[str, int]:
    df: dict[str, int] = {}
    uniq = set(tokens)
    for tok in uniq:
        df[tok] = sum(1 for s in corpus_token_sets if tok in s)
    return df


def score_twin(query_tokens: Sequence[str], doc: TwinDocument, df: dict[str, int], n_docs: int) -> float:
    if not query_tokens or n_docs <= 0:
        return 0.0
    doc_tokens = tokenize(_doc_text(doc))
    if not doc_tokens:
        return 0.0
    tf: dict[str, int] = {}
    for t in doc_tokens:
        tf[t] = tf.get(t, 0) + 1
    score = 0.0
    for qt in query_tokens:
        if qt not in tf:
            continue
        # smoothed idf
        idf = math.log(1.0 + (n_docs - df.get(qt, 0) + 0.5) / (df.get(qt, 0) + 0.5))
        score += (1.0 + math.log(tf[qt])) * max(idf, 0.0)
    return score


def _matched_lines(lines: Sequence[str], query_tokens: Sequence[str]) -> list[str]:
    out: list[str] = []
    qset = set(query_tokens)
    for line in lines:
        toks = set(tokenize(line))
        if toks & qset:
            out.append(line)
    return out


def search_twins(
    query: str,
    twins: Sequence[TwinDocument],
    *,
    limit: int = 20,
) -> list[TwinSearchHit]:
    """Rank ``twins`` against ``query``. Empty/whitespace query → empty list."""
    q = (query or "").strip()
    if not q:
        return []
    if limit <= 0:
        return []
    q_tokens = tokenize(q)
    if not q_tokens:
        return []
    corpus = list(twins)
    token_sets = [set(tokenize(_doc_text(d))) for d in corpus]
    df = _df(q_tokens, token_sets)
    n = len(corpus)
    hits: list[TwinSearchHit] = []
    for doc in corpus:
        s = score_twin(q_tokens, doc, df, n)
        if s <= 0.0:
            continue
        hits.append(
            TwinSearchHit(
                twin_id=doc.twin_id,
                parent_asset_id=doc.parent_asset_id,
                score=s,
                matched_insights=_matched_lines(doc.insights, q_tokens),
                matched_questions=_matched_lines(doc.questions, q_tokens),
                source_label=doc.source_label,
            )
        )
    hits.sort(key=lambda h: (-h.score, h.twin_id))
    return hits[:limit]


def search_store(
    store: TwinNotesStore,
    query: str,
    *,
    parent_asset_id: str | None = None,
    limit: int = 20,
) -> list[TwinSearchHit]:
    """Search one parent or all twin files under the store root."""
    if parent_asset_id:
        twins = store.list_for_parent(parent_asset_id)
    else:
        twins = []
        import json

        for path in sorted(store.root.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(raw, dict):
                continue
            parent = str(raw.get("parent_asset_id") or "")
            if parent:
                twins.extend(store.list_for_parent(parent))
    return search_twins(query, twins, limit=limit)


__all__ = [
    "TwinSearchHit",
    "search_store",
    "search_twins",
    "tokenize",
]
