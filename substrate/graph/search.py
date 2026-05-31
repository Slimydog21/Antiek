"""Vector search over the knowledge graph.

Ported from Researchmaxx ``search.py`` (231 LOC source → ~190 LOC here
after dropping the as-of temporal filter and inlining the embedding
model load behind an injectable Protocol).

What's here:

- ``cosine_similarity_sql`` — produces the DuckDB expression that
  computes cosine similarity against a chunk's embedding column. Pure
  SQL fragment, no dependencies.
- ``EmbeddingModel`` Protocol — minimal contract: ``encode(text) ->
  list[float]``. Tests inject a deterministic stub; production uses
  ``SentenceTransformerEmbedding`` which wraps ``sentence-transformers``.
- ``search(con, query, *, model, top_k, ...)`` — top-k chunks by
  cosine similarity, optionally with associated edges and connected
  nodes, optionally tier-filtered.
- ``search_nodes_by_label(con, query)`` — companion ILIKE search for
  node labels (the Researchmaxx ``node_matches`` array).

Deferred from the Researchmaxx version:

- ``as_of`` temporal filter — depends on ``graph_at_time`` which
  hasn't migrated. Add as an optional argument when temporal querying
  comes online.
- Embedding model auto-load from ``EMBEDDING_MODEL`` env var — too
  much hidden behavior; force callers to pass the model explicitly.
  ``SentenceTransformerEmbedding`` factory provided as a convenience.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional, Protocol, Sequence

try:
    from ...runtime.db_lock import connect_read
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import connect_read  # type: ignore[no-redef]

# The deny-by-default servability polarity is owned by the book full-text
# path (substrate/books/servability.py). The chunk/search gate below routes
# its full-text servability decision through that single predicate rather
# than re-implementing the polarity here — see search()'s §9.0 gate.
try:
    from ..books.servability import (
        is_content_class_servable_full_text,
        servable_full_text_content_classes,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    from substrate.books.servability import (  # type: ignore[no-redef]
        is_content_class_servable_full_text,
        servable_full_text_content_classes,
    )


# ---------------------------------------------------------------------------
# EmbeddingModel — injectable for tests
# ---------------------------------------------------------------------------


class EmbeddingModel(Protocol):
    """Minimal contract: encode a single string to a fixed-length
    float vector. Tests pass a deterministic stub; production wraps
    a sentence-transformers ``SentenceTransformer`` (see
    ``SentenceTransformerEmbedding`` below)."""

    dimension: int

    def encode(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedding:
    """Default production EmbeddingModel — wraps sentence-transformers.

    Lazy-imports the dependency so the rest of substrate/graph/ works
    in environments where the model isn't installed (tests using a
    stub, dev environments doing schema-only work)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import-not-found]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "sentence-transformers not installed. Run "
                "`pip install sentence-transformers` or pass a custom "
                "EmbeddingModel."
            ) from exc
        self._model = SentenceTransformer(model_name)
        self.dimension = int(self._model.get_sentence_embedding_dimension() or 384)

    def encode(self, text: str) -> list[float]:
        vec = self._model.encode([text])[0]
        return [float(x) for x in vec]


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def cosine_similarity_sql(
    embedding_col: str,
    query_vec: Sequence[float],
    dim: int,
) -> str:
    """Generate the DuckDB cosine-similarity expression for
    ``embedding_col`` against ``query_vec``.

    Inlines the query vector into the SQL string as a FLOAT[dim] cast,
    matching the Researchmaxx approach. This is safe because
    ``query_vec`` is always a numeric list under our control (not user
    input), and DuckDB's array casting validates the shape."""
    vec_str = "[" + ",".join(repr(float(x)) for x in query_vec) + "]"
    return (
        f"(list_dot_product({embedding_col}, {vec_str}::FLOAT[{dim}]) / "
        f" (sqrt(list_dot_product({embedding_col}, {embedding_col})) * "
        f"  sqrt(list_dot_product({vec_str}::FLOAT[{dim}], {vec_str}::FLOAT[{dim}]))))"
    )


# ---------------------------------------------------------------------------
# Public search API
# ---------------------------------------------------------------------------


# Policy tags privileged to bypass the §9.0 chunk gate. Per master-spec
# §9.0 retrieval-time gating: a privileged tag skips the deny-by-default
# allowlist ENTIRELY (it serves NULL/unknown AND restricted), so it is the
# operator-only personal-research path where fair use is robust. The default
# policy_tag for any ad-attributable surface is 'attribution_eligible' —
# which does NOT bypass the gate.
#
# STAGE-SAFETY (SPR-03): a privileged tag is a §9.0 WIDENING enforced, in PR
# #29, only by call-site discipline. To make it code-enforced, search()
# additionally requires callers requesting a privileged tag to present the
# PRIVILEGED_CALLER_TOKEN sentinel below; a money/ad-path caller that lacks
# the token cannot reach a privileged tag (it raises) — see
# tests/test_servability_polarity.py::test_money_path_caller_cannot_bypass_gate.
PRIVILEGED_POLICY_TAGS: frozenset[str] = frozenset({
    "private_research",
    "operator_only",
})

# The unforgeable in-process sentinel an operator-only caller must pass to
# search() to USE a privileged policy_tag. It is a module-private object, not
# a string, so it cannot be reconstructed from config / user input / an event
# payload — only code that imports this symbol (the operator-only grounder
# path) can present it. A caller that requests a privileged tag without it
# raises PrivilegedPolicyTagError; this is the code-enforced half of the §9.0
# stage-safety guard (OPERATOR_INPUTS §3 item 5).
PRIVILEGED_CALLER_TOKEN: object = object()


class PrivilegedPolicyTagError(PermissionError):
    """Raised when a caller requests a privileged policy_tag (one that
    bypasses the §9.0 chunk gate) without presenting PRIVILEGED_CALLER_TOKEN.

    The privileged bypass WIDENS §9.0 access (it serves NULL/unknown AND
    restricted content), so it is restricted to the operator-only grounder
    entrypoint. An attribution / ad / money-path caller cannot reach it: it
    has no access to the token, and passing the privileged tag string alone
    is rejected here rather than silently honoured."""


# The named restricted-content vocabulary (master-spec §9.0 / §9.10).
#
# RESTRICTED_CONTENT_CLASSES is the GATED-BUT-PUBLIC class
# (restricted_pending_opt_in): a copyrighted-but-public work whose body is
# withheld pending a rights-holder opt-in, but which DOES accrue ad revenue to
# escrow. It is the exact mirror of constants.GATED_DEFAULT_CONTENT_CLASS (the
# write side names the same gate state) — do NOT add personal_reading here.
#
# SPR-03: this is NO LONGER the search-gate's polarity. The non-privileged
# chunk gate is now a deny-by-default ALLOWLIST routed through the owned
# servability predicate (see search()), so it denies NULL/unknown without
# consulting this set. The constant is retained because it is the canonical
# name of the restricted class — imported by substrate/attribution/compute.py
# (the akb money-path, out of this sprint's scope) and asserted by
# tests/test_retrieval_time_gate.py — and because the privileged-bypass
# semantics still reason about "the restricted class". It is a vocabulary
# anchor, not the enforcement polarity.
RESTRICTED_CONTENT_CLASSES: frozenset[str] = frozenset({
    "restricted_pending_opt_in",
})

# Content classes that are OWNER-ONLY: the owner reads them in full on a
# privileged path, but they NEVER surface on a non-privileged (public /
# attribution-eligible) retrieval. personal_reading (the Personal-Reading Lane
# SPR-01 fourth rights state) is the only member: it is the owner's private
# third-party reading (a fetched essay / transcript / tweet) with no rights basis
# to serve publicly and — unlike restricted_pending_opt_in — no escrow economics
# at all (it never earns). It is kept as a SEPARATE set from
# RESTRICTED_CONTENT_CLASSES on purpose: the two gate states have OPPOSITE
# monetization semantics (restricted EARNS to escrow; personal_reading earns
# nothing), and RESTRICTED_CONTENT_CLASSES carries the documented contract that
# it equals the write-side GATED_DEFAULT_CONTENT_CLASS. Both sets are excluded on
# the same non-privileged branch below, so personal_reading is filtered out of
# the public chunk-search gate while remaining retrievable on the privileged
# (private_research / operator_only) owner path. What would reverse this choice:
# if personal_reading ever needed distinct policy_tag gating from
# restricted_pending_opt_in (e.g. a tag privileged for one but not the other),
# the separate set already supports it; folding them together would not.
PERSONAL_ONLY_CONTENT_CLASSES: frozenset[str] = frozenset({
    "personal_reading",
})

# The full set of content classes withheld from a non-privileged retrieval —
# the union of the gated-but-public class and the owner-only class. Both are
# excluded on the public branch; only the PRIVILEGED_POLICY_TAGS bypass.
_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES: frozenset[str] = (
    RESTRICTED_CONTENT_CLASSES | PERSONAL_ONLY_CONTENT_CLASSES
)


def chunk_full_text_servable(content_class: Optional[str]) -> bool:
    """The chunk/search §9.0 verdict for a ``content_class`` on a
    non-privileged retrieval path: may this class's full text appear in
    search results?

    Exactly the predicate the SQL gate in :func:`search` enforces
    (``content_class IN servable_full_text_content_classes()``), exposed as
    a pure function so the cross-path polarity test can assert chunk-path
    and book-path agreement class-by-class without spinning up a DuckDB.
    It delegates to the owned predicate in
    ``substrate/books/servability.py``; there is no second polarity here.
    NULL and unrecognised classes are DENIED (deny-by-default)."""
    return is_content_class_servable_full_text(content_class)


def search(
    con: Any,
    query: str,
    *,
    model: EmbeddingModel,
    top_k: int = 5,
    source_tier_max: Optional[int] = None,
    document_id: Optional[str] = None,
    document_ids: Optional[Sequence[str]] = None,
    with_edges: bool = False,
    policy_tag: str = "attribution_eligible",
    privileged_caller: object = None,
) -> dict:
    """Vector search over ``chunks.embedding``. Returns top-``k``
    chunks ordered by cosine similarity desc.

    Args:
        con: A DuckDB connection (read-only is fine).
        query: The natural-language query.
        model: An ``EmbeddingModel`` — production passes
            ``SentenceTransformerEmbedding()``; tests pass a stub.
        top_k: Max results.
        source_tier_max: Filter to chunks whose document has source_tier
            ``<=`` this value (lower = higher trust per
            ``substrate.constants.TIER_HIGHEST``). Use 2 to restrict to
            primary + peer-reviewed; None for no tier filter.
        document_id: Scope to chunks belonging to a single document.
            Used by the grounder to check claims against the document
            the user was wrestling, not the whole corpus.
        document_ids: Scope to chunks belonging to ANY document in this
            set (a single ``document_id IN (?,?,..)`` clause). This is the
            Read SPR-08 meta-reading "owned corpus" scope: synthesis over
            a bounded set of owned books ranks all their chunks by global
            similarity in ONE gated query, rather than iterating per-doc
            and re-merging (which would re-rank after the fact and risk
            applying the §9.0 gate inconsistently). When both
            ``document_id`` and ``document_ids`` are given, the single id
            is appended to the set (the union of the two scopes). An empty
            set is treated as "no documents in scope" → no results (an
            honest empty, never the whole corpus).
        with_edges: When True, attach the edges sourced from each
            returned chunk plus the nodes those edges connect.
        policy_tag: Retrieval-time gate per master-spec §9.0 + Personal-Reading
            Lane SPR-01. For the default 'attribution_eligible' (Sprint 18+
            ad-attribution path) — and any non-privileged tag — the §9.0 gate
            is a deny-by-default ALLOWLIST routed through the owned servability
            predicate: only a content_class that resolves to full-text-servable
            is returned, so NULL / unknown / restricted_pending_opt_in AND the
            owner-only personal_reading class are ALL excluded (personal_reading
            is not a servable class, so the allowlist withholds it from the
            public / attribution-eligible read exactly as the prior denylist
            did — the owner's private third-party reading must never reach a
            monetized / public read). When ``policy_tag`` is in
            PRIVILEGED_POLICY_TAGS ({"private_research", "operator_only"}) the
            gate is BYPASSED entirely (NULL/unknown, restricted AND
            personal_reading are returned — the owner's full-read path) — but a
            privileged tag additionally REQUIRES ``privileged_caller`` (see
            below). The Sprint 18 legal gate (master §15.9) is non-negotiable:
            payouts on an ungated graph are explicitly forbidden by §16.2.
        privileged_caller: The PRIVILEGED_CALLER_TOKEN sentinel. REQUIRED when
            ``policy_tag`` is a privileged tag; a privileged tag requested
            without it raises ``PrivilegedPolicyTagError``. This is the
            code-enforced §9.0 stage-safety guard: the privileged bypass
            WIDENS access, so only the operator-only grounder entrypoint
            (which imports + passes the token) may use it. A money / ad /
            attribution caller has no access to the token and so CANNOT reach
            a privileged tag, even by passing the tag string.

    Returns:
        ``{"query": ..., "top_k": ..., "results": [...], "node_matches": []}``
        — same shape as the Researchmaxx version so downstream
        consumers don't need adapter code.

    Raises:
        PrivilegedPolicyTagError: a privileged ``policy_tag`` was requested
            without the ``privileged_caller`` token.
    """
    if top_k < 1:
        raise ValueError(f"top_k must be >= 1, got {top_k}")

    # §9.0 stage-safety guard (SPR-03): a privileged policy_tag bypasses the
    # gate, which WIDENS access — so it is code-restricted to callers holding
    # the operator-only PRIVILEGED_CALLER_TOKEN. A money/ad-path caller that
    # passes the tag string but not the token is rejected here, never silently
    # granted the bypass.
    if policy_tag in PRIVILEGED_POLICY_TAGS and privileged_caller is not PRIVILEGED_CALLER_TOKEN:
        raise PrivilegedPolicyTagError(
            f"policy_tag={policy_tag!r} bypasses the §9.0 chunk gate and may "
            "be used ONLY by the operator-only grounder path, which must pass "
            "search.PRIVILEGED_CALLER_TOKEN as privileged_caller. Refusing to "
            "serve restricted / NULL-provenance content to an unprivileged "
            "caller (§9.0 deny-by-default)."
        )

    # Union the single-id scope into the set scope (a caller may pass
    # either or both). An EXPLICITLY-EMPTY set means "no documents in
    # scope" — return nothing rather than silently widening to the whole
    # corpus (the meta-reading owned-corpus scope must never leak past its
    # bound). `document_ids is None` ⇒ no set filter at all.
    scoped_ids: Optional[list[str]] = None
    if document_ids is not None:
        scoped_ids = list(dict.fromkeys(document_ids))  # de-dup, keep order
        if document_id is not None and document_id not in scoped_ids:
            scoped_ids.append(document_id)
        if not scoped_ids:
            return {
                "query": query,
                "top_k": top_k,
                "results": [],
                "node_matches": [],
            }

    query_vec = list(model.encode(query))
    dim = model.dimension
    if len(query_vec) != dim:
        raise ValueError(
            f"EmbeddingModel.encode returned {len(query_vec)} dims; "
            f"model.dimension is {dim}. Match them."
        )

    sim_expr = cosine_similarity_sql("c.embedding", query_vec, dim)

    sql = f"""
        SELECT
            c.chunk_id, c.section_path, c.text, c.token_count,
            c.document_id, c.chunk_index,
            d.title, d.source_tier, d.document_type,
            {sim_expr} AS similarity
        FROM chunks c
        JOIN documents d ON c.document_id = d.document_id
        WHERE c.embedding IS NOT NULL
    """
    params: list[Any] = []
    if scoped_ids is not None:
        placeholders = ",".join("?" for _ in scoped_ids)
        sql += f" AND c.document_id IN ({placeholders})"
        params.extend(scoped_ids)
    elif document_id is not None:
        sql += " AND c.document_id = ?"
        params.append(document_id)
    if source_tier_max is not None:
        sql += " AND d.source_tier <= ?"
        params.append(int(source_tier_max))
    # §9.0 retrieval-time gate — deny-by-default (SPR-03) + Personal-Reading
    # Lane SPR-01.
    #
    # The non-privileged retrieval path serves a chunk's parent document
    # only when its content_class resolves to FULL-TEXT-SERVABLE through
    # the owned predicate in substrate/books/servability.py
    # (is_content_class_servable_full_text == is_servable_full_text(
    # servability_of(content_class))). NULL and any unrecognised
    # content_class collapse to GATED_METADATA_ONLY there and are absent
    # from the derived allowlist — so they are DENIED, the same verdict the
    # book full-text path reaches over the same column. This replaced the
    # earlier fail-open denylist (an OR-NULL-or-NOT-IN-restricted clause),
    # under which a NULL/unknown class *passed*. §9.0 is deny-by-default
    # for a legal reason: unknown provenance is legally indistinguishable
    # from restricted (Hachette v. Internet Archive, 2d Cir. 2024; Bartz v.
    # Anthropic), so it must deny.
    #
    # The owner-only personal_reading class (Personal-Reading Lane SPR-01)
    # is likewise withheld here: it is not a servable content_class, so the
    # allowlist excludes it from the public / attribution-eligible read
    # exactly as the prior _NON_PRIVILEGED_EXCLUDED denylist did — the
    # owner's private third-party reading remains retrievable only on the
    # privileged (private_research / operator_only) owner path below. So the
    # allowlist polarity SUBSUMES the personal_reading exclusion the denylist
    # provided, while additionally closing the NULL/unknown hole.
    #
    # Legacy carve-out: NONE NEEDED. The previous OR-NULL clause
    # grandfathered every legacy chunk whose content_class was never
    # populated — exactly the blanket NULL/unknown fail-open §9.0 forbids,
    # not a finite enumerable set, so it cannot be expressed as a named,
    # auditable carve-out. The read-side allowlist here composes with the
    # write-side insert_document deny-by-default guard (substrate/graph/
    # ops.py) that stops fresh third-party ingests landing NULL — defense in
    # depth, both layers deny NULL. The legitimate legacy concern is honoured
    # the only defensible way: the Sprint 18 ip_holders backfill populates
    # content_class for genuinely-servable legacy documents (public_domain
    # / open / opt-in), after which they re-enter the allowlist on
    # provenance, not on a NULL hole. Until a document carries an
    # established servable class it stays gated.
    if policy_tag not in PRIVILEGED_POLICY_TAGS:
        servable_classes = sorted(servable_full_text_content_classes())
        placeholders = ",".join("?" for _ in servable_classes)
        sql += f" AND d.content_class IN ({placeholders})"
        params.extend(servable_classes)
    sql += " ORDER BY similarity DESC LIMIT ?"
    params.append(int(top_k))

    rows = con.execute(sql, params).fetchall()

    results: list[dict] = []
    for (
        chunk_id, section, text, tokens, doc_id, chunk_index,
        title, tier, dtype, sim,
    ) in rows:
        item: dict[str, Any] = {
            "chunk_id": chunk_id,
            "section_path": section,
            "chunk_text": text[:500] + ("…" if text and len(text) > 500 else ""),
            "token_count": tokens,
            # document_id + chunk_index let a citation jump back to the
            # source: the Read surface maps section_path ("Page N") → a
            # reader page (page_index_from_section_path), and falls back to
            # the document when no page resolves (honest, never invented).
            "document_id": doc_id,
            "chunk_index": chunk_index,
            "document_title": title,
            "source_tier": tier,
            "document_type": dtype,
            "similarity": round(float(sim), 4),
        }
        if with_edges:
            item["edges"], item["nodes"] = _fetch_edges_and_nodes(con, chunk_id)
        results.append(item)

    return {
        "query": query,
        "top_k": top_k,
        "results": results,
        "node_matches": search_nodes_by_label(con, query, limit=10),
    }


def _fetch_edges_and_nodes(con: Any, chunk_id: str) -> tuple[list[dict], list[dict]]:
    """Helper for ``with_edges=True``: returns the edges sourced from
    a chunk and the nodes those edges connect."""
    edge_rows = con.execute(
        """
        SELECT e.edge_id, e.source_node_id, e.target_node_id, e.relation,
               e.extraction_confidence, e.source_tier,
               n1.canonical_label AS source_label,
               n2.canonical_label AS target_label
        FROM edges e
        JOIN nodes n1 ON e.source_node_id = n1.node_id
        JOIN nodes n2 ON e.target_node_id = n2.node_id
        WHERE e.chunk_id = ?
        LIMIT 20
        """,
        [chunk_id],
    ).fetchall()

    edges = [
        {
            "edge_id": e[0],
            "source": {"id": e[1], "label": e[6]},
            "target": {"id": e[2], "label": e[7]},
            "relation": e[3],
            "confidence": round(float(e[4]), 3),
            "source_tier": e[5],
        }
        for e in edge_rows
    ]

    node_ids = {e[1] for e in edge_rows} | {e[2] for e in edge_rows}
    nodes: list[dict] = []
    if node_ids:
        placeholders = ",".join(["?"] * len(node_ids))
        node_rows = con.execute(
            f"""
            SELECT node_id, node_type, canonical_label
            FROM nodes
            WHERE node_id IN ({placeholders})
            LIMIT 30
            """,
            list(node_ids),
        ).fetchall()
        nodes = [
            {"node_id": n[0], "node_type": n[1], "label": n[2]}
            for n in node_rows
        ]
    return edges, nodes


def search_nodes_by_label(con: Any, query: str, limit: int = 10) -> list[dict]:
    """ILIKE search over ``nodes.canonical_label``. Used as a companion
    to vector search for label-direct hits — "PsiQuantum" as a query
    should find the PsiQuantum node even if no chunk embedding is
    closer than another."""
    rows = con.execute(
        """
        SELECT node_id, node_type, canonical_label
        FROM nodes
        WHERE canonical_label ILIKE ?
        LIMIT ?
        """,
        [f"%{query}%", int(limit)],
    ).fetchall()
    return [
        {"node_id": r[0], "node_type": r[1], "label": r[2]}
        for r in rows
    ]


def open_read(db_path: str) -> Any:
    """Convenience: open a read-only connection. Same as
    ``runtime.db_lock.connect_read`` — exposed here so search.py is
    the one-stop import for read-side graph queries."""
    return connect_read(db_path)
