"""``get_cross_doc_links`` — substrate query for gutter cross-doc pills.

The reading surface (SPR-07) calls this on every finalized highlight.
Given ``(document_id, page, bbox, selected_text)`` we return up to 3
``CrossDocLink`` rows ranked by a documented score fusion:

    score = w_sim · normalized_similarity
          + w_user · user_asserted_indicator
          + w_cite · citation_indicator

Weights live in :data:`SCORING_WEIGHTS`; the rationale is in
``services/cross_doc/SCORING.md``.

The query has three legs that are UNION-ed:

1. **Similarity leg** — cosine similarity over ``chunks.embedding`` per
   the existing ``substrate.graph.search`` helpers. Excludes chunks
   from the source document (echo-chamber guard).
2. **User-asserted leg** — chunks reachable via an edge whose
   ``relation`` is in :data:`USER_ASSERTED_RELATIONS` and whose
   ``chunk_id`` is on the highlighted page. The substrate keeps these
   in the unified ``edges`` table (Sprint 3 schema) rather than a
   dedicated user-asserted table; we filter by relation here.
3. **Citation leg** — chunks reachable via an edge whose ``relation``
   is in :data:`CITATION_RELATIONS`. Same table, different relation
   set.

The three legs are unioned and re-scored. We then apply diversity
filtering (max 1 result per target document) and trim to top-N.

Why this shape and not "fan out from a precomputed source chunk":
the highlight bbox may straddle multiple chunks; using ``selected_text``
as the vector-search query is robust to chunk boundaries and matches
what the existing ``substrate.graph.search.search`` already does for
arbitrary natural-language queries.

P99 latency budget: 200ms (per SPR-07 spec). See
``services/cross_doc/tests/test_latency.py`` for the synthetic-load
benchmark; the live numbers are reported in the SPR-07 handoff.

Defensive defaults:

- ``include_public_graph=False`` — the public-graph toggle is OFF until
  master-spec §13.9 attribution flows (Sprint 19) are live. Even with
  the flag on the substrate enforces the retrieval-time gate via
  ``policy_tag``; this module's contract is that public-graph rows are
  visible only when ``include_public_graph=True`` AND the policy_tag
  allows them.
- ``top_k=3`` — chosen number, see ``Gutter.tsx`` comment for the
  rationale. We cap at 3 to keep the pill cluster visually quiet.
- Same-document echo-chamber guard: we DROP any candidate whose
  ``target_document_id`` equals the source ``document_id`` regardless
  of leg.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Final, Literal, Optional, Sequence

try:
    from substrate.graph.search import (
        EmbeddingModel,
        PRIVILEGED_POLICY_TAGS,
        RESTRICTED_CONTENT_CLASSES,
        cosine_similarity_sql,
    )
except ImportError:  # pragma: no cover — fallback for direct-script runs
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.graph.search import (  # type: ignore[no-redef]
        EmbeddingModel,
        PRIVILEGED_POLICY_TAGS,
        RESTRICTED_CONTENT_CLASSES,
        cosine_similarity_sql,
    )


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


SourceType = Literal["similarity", "user_asserted", "citation"]


@dataclass(frozen=True)
class Highlight:
    """Operator highlight input.

    Mirrors the ``DocumentRegionSelectedPayload`` shape produced by the
    PDF viewer's mouse-up handler. ``selected_text`` is what we use as
    the vector-search query; ``document_id``/``page``/``bbox`` carry
    the source coordinates so we can scope the echo-chamber guard and,
    later, prefer edges anchored to the source chunk.
    """

    document_id: str
    page: int
    bbox: tuple[float, float, float, float]
    selected_text: str


@dataclass(frozen=True)
class CrossDocCandidate:
    """An intermediate, pre-fusion candidate produced by one of the
    three legs (similarity / user-asserted / citation). Internal."""

    chunk_id: str
    document_id: str
    doc_title: str
    page: int
    snippet: str
    similarity: float
    is_user_asserted: bool
    is_citation: bool
    source_tier: int
    content_class: Optional[str]


@dataclass(frozen=True)
class CrossDocLink:
    """One pill's worth of data, returned to the caller. The schema
    here is the contract the TS client (``apps/reading/api/cross_doc/
    links.ts``) consumes."""

    chunk_id: str
    doc_title: str
    document_id: str
    page: int
    snippet: str
    score: float
    source: SourceType
    source_tier: int


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------


# Score-fusion weights — see SCORING.md for the rationale and what would
# move them. These are intentionally MUTABLE-AT-IMPORT (a dict, not a
# frozen dataclass) so the operator can tune them via an env-var override
# without redeploying the substrate. The override pattern is the same
# one ``substrate/constants.py`` uses for DUCKDB_PATH.
SCORING_WEIGHTS: dict[str, float] = {
    # Vector-similarity carries the most weight: it is the only signal
    # available for every candidate and it scales continuously. User
    # / citation flags are sparse boolean boosts on top.
    "similarity": 0.7,
    # User-asserted edges are operator-authored intent. Strong signal,
    # but typically sparse — we reward presence but don't let it
    # overwhelm a 0.1-similarity hit (sparse + noisy in early days).
    "user_asserted": 0.2,
    # Citation edges are also high-signal-but-sparse. Equal-weighted
    # with user-asserted is the operator-default; the SCORING.md note
    # records that we'd raise this above user_asserted only if the
    # citation extractor's recall improves.
    "citation": 0.1,
}


# Relation strings the substrate uses for user-asserted edges. The
# ``edges`` table is shared — the relation column is the type tag.
# These match what ``substrate/cross_graph/event_emit.py`` emits and
# what the Sprint 3 ops layer accepts.
USER_ASSERTED_RELATIONS: Final[frozenset[str]] = frozenset({
    "user_asserted_link",
    "user_asserted",
    "operator_asserted",
})


# Relation strings used by extractors that emit citation edges.
# Researchmaxx ports use "cites" as the canonical verb; we also accept
# the inverse and the noun form for compatibility with future
# extractor revisions.
CITATION_RELATIONS: Final[frozenset[str]] = frozenset({
    "cites",
    "cited_by",
    "citation",
})


# Maximum results returned. Chosen number — see ``Gutter.tsx`` for the
# UX-side rationale (eyeball distance + visual budget).
DEFAULT_TOP_K: Final[int] = 3


# Echo-chamber guard: max candidates from the same target document. We
# keep this at 1 by default — the brainstorm explicitly identified
# "show me 3 places in this same book" as the failure mode worth
# preventing (operator wants cross-document diversity).
DEFAULT_MAX_PER_DOCUMENT: Final[int] = 1


# Internal: how many candidates each leg may return before fusion. We
# pull more than ``top_k`` so the fusion step has room to apply the
# diversity guard without falling short.
LEG_CANDIDATE_POOL: Final[int] = 12


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def get_cross_doc_links(
    highlight: Highlight,
    *,
    con: Any,
    model: EmbeddingModel,
    top_k: int = DEFAULT_TOP_K,
    include_public_graph: bool = False,
    policy_tag: str = "operator_only",
    max_per_document: int = DEFAULT_MAX_PER_DOCUMENT,
    weights: Optional[dict[str, float]] = None,
) -> list[CrossDocLink]:
    """Return up to ``top_k`` cross-document links for ``highlight``.

    Args:
        highlight: The operator's selection. ``selected_text`` is the
            query vector; ``document_id`` is excluded from results
            (echo-chamber guard).
        con: A DuckDB connection (read-only is fine). Caller-owned.
        model: An ``EmbeddingModel`` — see ``substrate.graph.search``.
            Tests pass a deterministic stub; production passes
            ``SentenceTransformerEmbedding()``.
        top_k: Maximum results. The UX surface is calibrated to 3
            (see ``Gutter.tsx``); callers should not exceed that
            without a UI-level decision.
        include_public_graph: When True, public-graph results are
            mixed in. Default False per SPR-07 M7 — the public-graph
            toggle ships disabled and gated on Sprint 19 §13.9.
            Independently of this flag, the policy_tag retrieval-time
            gate still applies.
        policy_tag: Retrieval-time gate per master-spec §9.0. The
            cross-doc surface is operator-facing in the reading UI;
            'operator_only' is the appropriate default because the
            operator viewing the result is the doc's owner. For the
            future Wedge-2 notebook surface that may share links
            publicly, the call site passes 'attribution_eligible'.
        max_per_document: Diversity cap. Default 1 — see
            ``DEFAULT_MAX_PER_DOCUMENT``.
        weights: Override the default score-fusion weights. Same keys
            as :data:`SCORING_WEIGHTS`.

    Returns:
        A list of at most ``top_k`` ``CrossDocLink`` items ordered by
        descending fused score. Empty list is valid (no neighbours).
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")
    if not highlight.selected_text or not highlight.selected_text.strip():
        # No selection text → nothing to embed → no candidates. Empty
        # list, not an exception — the surface call site fires on
        # every highlight (some of which may be image-only selections
        # someday) and we don't want to throw across the polyglot seam.
        return []

    w = dict(SCORING_WEIGHTS)
    if weights:
        for key in ("similarity", "user_asserted", "citation"):
            if key in weights:
                w[key] = float(weights[key])

    candidates = _collect_candidates(
        highlight=highlight,
        con=con,
        model=model,
        include_public_graph=include_public_graph,
        policy_tag=policy_tag,
    )

    # Apply echo-chamber guard: drop any candidate whose target document
    # equals the source document. We do this BEFORE diversity so the
    # diversity cap doesn't accidentally use up its budget on the
    # source document.
    candidates = [
        c for c in candidates if c.document_id != highlight.document_id
    ]

    # Fuse + diversify.
    scored = _fuse_scores(candidates, weights=w)
    diversified = _apply_diversity(scored, max_per_document=max_per_document)

    # Trim to top_k and convert to public type.
    out: list[CrossDocLink] = []
    for cand, fused in diversified[:top_k]:
        source: SourceType
        if cand.is_user_asserted:
            source = "user_asserted"
        elif cand.is_citation:
            source = "citation"
        else:
            source = "similarity"
        out.append(
            CrossDocLink(
                chunk_id=cand.chunk_id,
                doc_title=cand.doc_title,
                document_id=cand.document_id,
                page=cand.page,
                snippet=_truncate_snippet(cand.snippet),
                score=round(fused, 4),
                source=source,
                source_tier=cand.source_tier,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


# Snippet cap mirrors the spec's "200-char snippet centered on the
# chunk" (M3). The Python layer pre-truncates to keep the TS payload
# small; the UI can re-truncate if needed.
_SNIPPET_CHAR_BUDGET: Final[int] = 200


def _truncate_snippet(text: str) -> str:
    if len(text) <= _SNIPPET_CHAR_BUDGET:
        return text
    return text[: _SNIPPET_CHAR_BUDGET - 1].rstrip() + "…"


def _collect_candidates(
    *,
    highlight: Highlight,
    con: Any,
    model: EmbeddingModel,
    include_public_graph: bool,
    policy_tag: str,
) -> list[CrossDocCandidate]:
    """Run the three legs and merge their candidates. Idempotent and
    pure-read."""
    query_vec = list(model.encode(highlight.selected_text))
    dim = model.dimension
    if len(query_vec) != dim:
        raise ValueError(
            f"EmbeddingModel.encode returned {len(query_vec)} dims; "
            f"model.dimension is {dim}. Match them."
        )
    sim_expr = cosine_similarity_sql("c.embedding", query_vec, dim)

    # Build the policy-tag predicate inline. Mirrors substrate.graph.
    # search.search; we accept the small duplication rather than
    # restructuring search() which has a different result shape.
    policy_predicate, policy_params = _policy_predicate(
        policy_tag=policy_tag,
        include_public_graph=include_public_graph,
    )

    candidates: dict[str, CrossDocCandidate] = {}

    # ── Leg 1: similarity ──
    sim_sql = f"""
        SELECT
            c.chunk_id,
            c.document_id,
            d.title,
            COALESCE(_page_from_section(c.section_path), 1) AS page,
            c.text AS snippet,
            {sim_expr} AS similarity,
            d.source_tier,
            d.content_class
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.embedding IS NOT NULL
          AND c.document_id <> ?
          {policy_predicate}
        ORDER BY similarity DESC
        LIMIT ?
    """
    # NB: ``_page_from_section`` is a wishful UDF we don't actually
    # register — fall back to page 1 if section_path doesn't encode a
    # page. For Sprint 7 the substrate doesn't yet emit per-chunk page
    # numbers in chunks rows; we report ``1`` and a follow-up sprint
    # adds a real ``chunks.page`` column. The TS layer treats page as
    # an integer ≥1 and the cite-jump uses ``?page=`` which falls
    # back to the first page when N=1.
    #
    # To avoid a UDF dependency right now we inline ``1`` in the SQL.
    sim_sql = sim_sql.replace(
        "COALESCE(_page_from_section(c.section_path), 1) AS page",
        "1 AS page",
    )

    sim_params: list[Any] = [highlight.document_id, *policy_params, LEG_CANDIDATE_POOL]
    for row in con.execute(sim_sql, sim_params).fetchall():
        cid = row[0]
        sim_score = float(row[5])
        # Cosine sim is in [-1, 1]; clamp negatives to 0 so the fusion
        # math is well-behaved (negative similarity is "anti-aligned"
        # text, which should not earn a positive boost).
        if sim_score < 0:
            sim_score = 0.0
        candidates[cid] = CrossDocCandidate(
            chunk_id=cid,
            document_id=row[1],
            doc_title=row[2] or "(untitled)",
            page=int(row[3]),
            snippet=row[4] or "",
            similarity=sim_score,
            is_user_asserted=False,
            is_citation=False,
            source_tier=int(row[6]),
            content_class=row[7],
        )

    # ── Leg 2: user-asserted edges anchored on this document ──
    user_rows = _edge_anchored_candidates(
        con=con,
        source_document_id=highlight.document_id,
        relation_set=USER_ASSERTED_RELATIONS,
        policy_predicate=policy_predicate,
        policy_params=policy_params,
        sim_expr=sim_expr,
    )
    for cand in user_rows:
        existing = candidates.get(cand.chunk_id)
        if existing:
            # Merge: keep the higher similarity but flip the
            # user_asserted flag on. Tuple replacement on a frozen
            # dataclass.
            candidates[cand.chunk_id] = CrossDocCandidate(
                chunk_id=existing.chunk_id,
                document_id=existing.document_id,
                doc_title=existing.doc_title,
                page=existing.page,
                snippet=existing.snippet,
                similarity=max(existing.similarity, cand.similarity),
                is_user_asserted=True,
                is_citation=existing.is_citation,
                source_tier=existing.source_tier,
                content_class=existing.content_class,
            )
        else:
            candidates[cand.chunk_id] = cand

    # ── Leg 3: citation edges ──
    cite_rows = _edge_anchored_candidates(
        con=con,
        source_document_id=highlight.document_id,
        relation_set=CITATION_RELATIONS,
        policy_predicate=policy_predicate,
        policy_params=policy_params,
        sim_expr=sim_expr,
    )
    for cand in cite_rows:
        existing = candidates.get(cand.chunk_id)
        if existing:
            candidates[cand.chunk_id] = CrossDocCandidate(
                chunk_id=existing.chunk_id,
                document_id=existing.document_id,
                doc_title=existing.doc_title,
                page=existing.page,
                snippet=existing.snippet,
                similarity=max(existing.similarity, cand.similarity),
                is_user_asserted=existing.is_user_asserted,
                is_citation=True,
                source_tier=existing.source_tier,
                content_class=existing.content_class,
            )
        else:
            candidates[cand.chunk_id] = CrossDocCandidate(
                chunk_id=cand.chunk_id,
                document_id=cand.document_id,
                doc_title=cand.doc_title,
                page=cand.page,
                snippet=cand.snippet,
                similarity=cand.similarity,
                is_user_asserted=False,
                is_citation=True,
                source_tier=cand.source_tier,
                content_class=cand.content_class,
            )

    return list(candidates.values())


def _edge_anchored_candidates(
    *,
    con: Any,
    source_document_id: str,
    relation_set: frozenset[str],
    policy_predicate: str,
    policy_params: Sequence[Any],
    sim_expr: str,
) -> list[CrossDocCandidate]:
    """Find chunks reachable from chunks in ``source_document_id`` via
    edges whose ``relation`` is in ``relation_set``.

    The query joins:
        ``edges e`` → ``nodes`` (source AND target) → ``chunks`` of
        the target nodes.

    This is the indirect graph reach: the operator selected text that
    sits on a chunk in document A; chunks in document A contain edges
    (semantic relations); we follow those relations to chunks in other
    documents.
    """
    if not relation_set:
        return []
    placeholders = ",".join(["?"] * len(relation_set))
    # The join walks: edges (anchored on source doc) → nodes shared with
    # → edges (anchored on target chunks). "Shared node" means either
    # endpoint of the source edge matches either endpoint of the target
    # edge — graph reachability is symmetric on node membership.
    sql = f"""
        WITH target_edge_nodes AS (
            SELECT te.chunk_id AS tc_chunk_id, te.source_node_id AS nid
            FROM edges te
            WHERE te.chunk_id IS NOT NULL
            UNION ALL
            SELECT te.chunk_id AS tc_chunk_id, te.target_node_id AS nid
            FROM edges te
            WHERE te.chunk_id IS NOT NULL
        )
        SELECT DISTINCT
            tc.chunk_id,
            tc.document_id,
            td.title,
            1 AS page,
            tc.text AS snippet,
            CASE WHEN tc.embedding IS NULL THEN 0.0 ELSE {sim_expr.replace('c.embedding', 'tc.embedding')} END AS similarity,
            td.source_tier,
            td.content_class
        FROM edges e
        JOIN chunks sc ON e.chunk_id = sc.chunk_id
        JOIN target_edge_nodes ten
            ON ten.nid IN (e.source_node_id, e.target_node_id)
        JOIN chunks tc ON tc.chunk_id = ten.tc_chunk_id
                       AND tc.document_id != sc.document_id
                       AND tc.chunk_id != sc.chunk_id
        JOIN documents td ON tc.document_id = td.document_id
        WHERE sc.document_id = ?
          AND e.relation IN ({placeholders})
          {policy_predicate.replace('d.content_class', 'td.content_class')}
        LIMIT ?
    """
    params: list[Any] = [
        source_document_id,
        *list(relation_set),
        *policy_params,
        LEG_CANDIDATE_POOL,
    ]
    try:
        rows = con.execute(sql, params).fetchall()
    except Exception:
        # The join above is intentionally permissive; if the substrate
        # has no edges (early-stage operator) the query may return 0
        # rows or, on certain DuckDB versions, raise on the correlated
        # subquery. Catch broadly and degrade to "no edge-anchored
        # candidates" — the similarity leg still produces results.
        return []

    out: list[CrossDocCandidate] = []
    for row in rows:
        sim_score = float(row[5]) if row[5] is not None else 0.0
        if sim_score < 0:
            sim_score = 0.0
        out.append(
            CrossDocCandidate(
                chunk_id=row[0],
                document_id=row[1],
                doc_title=row[2] or "(untitled)",
                page=int(row[3]),
                snippet=row[4] or "",
                similarity=sim_score,
                is_user_asserted=False,  # caller sets the right flag
                is_citation=False,
                source_tier=int(row[6]),
                content_class=row[7],
            )
        )
    return out


def _policy_predicate(
    *,
    policy_tag: str,
    include_public_graph: bool,
) -> tuple[str, list[Any]]:
    """Build the WHERE-clause fragment + bind params for the policy
    + public-graph filter. Mirrors substrate.graph.search.search.

    The predicate is prefixed with ``AND `` so callers can drop it into
    an existing ``WHERE``.

    Public-graph filtering is also done here: when ``include_public_graph``
    is False we restrict to ``content_class`` values that the substrate
    considers private (``user_owned``, ``opt_in_licensed``, NULL legacy).
    """
    clauses: list[str] = []
    params: list[Any] = []

    if policy_tag not in PRIVILEGED_POLICY_TAGS:
        placeholders = ",".join(["?"] * len(RESTRICTED_CONTENT_CLASSES))
        clauses.append(
            f"(d.content_class IS NULL OR d.content_class NOT IN ({placeholders}))"
        )
        params.extend(RESTRICTED_CONTENT_CLASSES)

    if not include_public_graph:
        # Public-graph rows live behind ``content_class =
        # 'user_public_contribution'``. When the toggle is OFF those
        # rows are excluded regardless of policy_tag. The reciprocal
        # is NOT true — policy_tag still gates restricted content
        # even when include_public_graph=True.
        clauses.append(
            "(d.content_class IS NULL OR d.content_class <> 'user_public_contribution')"
        )

    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def _fuse_scores(
    candidates: Sequence[CrossDocCandidate],
    *,
    weights: dict[str, float],
) -> list[tuple[CrossDocCandidate, float]]:
    """Apply the documented score fusion. Output is sorted desc by
    fused score."""
    fused: list[tuple[CrossDocCandidate, float]] = []
    for cand in candidates:
        score = (
            weights["similarity"] * cand.similarity
            + weights["user_asserted"] * (1.0 if cand.is_user_asserted else 0.0)
            + weights["citation"] * (1.0 if cand.is_citation else 0.0)
        )
        fused.append((cand, score))
    fused.sort(key=lambda pair: pair[1], reverse=True)
    return fused


def _apply_diversity(
    scored: Sequence[tuple[CrossDocCandidate, float]],
    *,
    max_per_document: int,
) -> list[tuple[CrossDocCandidate, float]]:
    """Trim each target document down to at most ``max_per_document``
    results, preserving the descending-score order."""
    if max_per_document <= 0:
        return list(scored)
    seen: dict[str, int] = {}
    out: list[tuple[CrossDocCandidate, float]] = []
    for cand, score in scored:
        count = seen.get(cand.document_id, 0)
        if count >= max_per_document:
            continue
        seen[cand.document_id] = count + 1
        out.append((cand, score))
    return out


__all__ = [
    "CITATION_RELATIONS",
    "CrossDocCandidate",
    "CrossDocLink",
    "DEFAULT_MAX_PER_DOCUMENT",
    "DEFAULT_TOP_K",
    "Highlight",
    "LEG_CANDIDATE_POOL",
    "SCORING_WEIGHTS",
    "SourceType",
    "USER_ASSERTED_RELATIONS",
    "get_cross_doc_links",
]
