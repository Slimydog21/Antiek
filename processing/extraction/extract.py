"""LLM extraction — chunks → typed nodes + attributed edges.

Migrated from Researchmaxx ``extract.py`` (605 LOC source → ~280 LOC
here after removing the OpenRouter call (routed through Antiek
dispatch instead), the batch-CLI machinery (acquisition surface
concern), and the tier_override integration (lands when
middleware/source_tier wiring matures)).

Sprint 3 Day 4-5: completes the substrate triangle — chunks land via
the wrestling bridge (Day 2-3), the grounder consumes them (Day 3-4),
extraction promotes chunks into typed graph nodes + attributed edges
ready for the cross-doc linking work in Sprint 5.

What's here:

- ``EXTRACTION_SYSTEM_PROMPT`` — the role-tail prompt. Tightened to
  match Antiek's 9-value NodeType Literal (Researchmaxx's "concept" /
  "market" / "technology" map to "entity" with a metadata note).
- ``ExtractedNode`` + ``ExtractedEdge`` dataclasses for the parsed
  LLM output before it goes through ``substrate/graph/ops``.
- ``parse_extraction_response`` — JSON-tolerant parser, same code-fence
  / prose-preamble handling as wrestling + grounding.
- ``extract_from_chunk`` — the pipeline. Reads chunk text, dispatches
  parameter_extractor role, parses, writes nodes+edges via ops
  (each emits its own GRAPH_NODE_INSERTED / GRAPH_EDGE_INSERTED
  typed event).

What's deferred:

- Batch extraction CLI (``extract_for_document``) — Sprint 5
  acquisition-layer work.
- Tier-override persistence — when middleware/source_tier wiring
  matures.
- LLM-driven tier adjustment hook — same.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

try:
    from ...substrate.dispatch import ProviderError, dispatch
    from ...substrate.event_log import emit_typed
    from ...substrate.graph import (
        default_db_path,
        ensure_initialized,
        insert_edge,
        insert_node,
    )
    from ...processing.embedding import (
        EmbeddingProvider,
        default_embedding_provider,
    )
    from ...runtime.db_lock import connect_read, connect_write
    from ...interfaces.research.api.wrestling import _extract_json_object  # JSON helper
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))  # project root
    from substrate.dispatch import ProviderError, dispatch  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.graph import (  # type: ignore[no-redef]
        default_db_path,
        ensure_initialized,
        insert_edge,
        insert_node,
    )
    from processing.embedding import (  # type: ignore[no-redef]
        EmbeddingProvider,
        default_embedding_provider,
    )
    from runtime.db_lock import connect_read, connect_write  # type: ignore[no-redef]
    from interfaces.research.api.wrestling import _extract_json_object  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


# The node types document *extraction* can produce. This is a strict
# SUBSET of substrate.schemas.NodeType: the two DRW SPR-01 additions
# ('insight', 'question') are first-class node types, but they are
# promoted only from the note-taker path (note.emerged /
# question.identified), never emitted by chunk extraction — the extractor
# reads sources, it does not distil insights. The invariant the test
# enforces is therefore ANTIEK_NODE_TYPES ⊆ NodeType (no extracted value
# the payload would reject), not equality.
# Researchmaxx's "concept" / "market" / "technology" map to "entity" with a
# metadata note recording the original extracted type so a future expansion
# of NodeType can recover it.
ANTIEK_NODE_TYPES: frozenset[str] = frozenset({
    "entity", "organization", "person", "property",
    "metric", "mechanism", "claim", "method", "constraint",
})

# Reasonable starting graph_scope for chunk-derived extractions. The
# Connector role (Sprint 4+) decides scope per-node based on cross-domain
# analysis; until then, every extracted node lands in cross_domain (the
# widest scope, allowed by every traversal).
DEFAULT_GRAPH_SCOPE = "cross_domain"

# Default source_tier when the chunk's document doesn't specify. Tier 4
# (general tech press) is the conservative default per
# substrate.constants.SOURCE_TYPES.
DEFAULT_SOURCE_TIER = 4


EXTRACTION_SYSTEM_PROMPT = """You are a knowledge extraction engine. Your job is
to read a text chunk and extract structured nodes and edges for a knowledge
graph.

## Node types (closed set — pick the closest match)

| node_type   | When to use                                                  |
|-------------|--------------------------------------------------------------|
| entity      | A specific thing, concept, technology, market, or product    |
| organization| A company, lab, institution, government body                 |
| person      | A named individual                                           |
| property    | An attribute of an entity (founded date, location, size)     |
| metric      | A specific quantitative value, range, or benchmark           |
| mechanism   | A causal process, physical/economic constraint, "how it works"|
| claim       | A non-trivial assertion about the world                      |
| method      | A repeatable procedure, technique, algorithm                 |
| constraint  | A binding limit (regulatory, physical, economic, technical)  |

## Relation types (open vocabulary; prefer precise verbs)

Examples: ``develops``, ``competes_with``, ``supplies``, ``uses``, ``enables``,
``constrains``, ``contradicts``, ``supports``, ``has_property``,
``measured_at``, ``founded_in``, ``led_by``, ``raised``, ``causes``,
``correlates_with``, ``depends_on``.

## Confidence calibration (REQUIRED on every edge)

| score | Standard                                                       |
|-------|----------------------------------------------------------------|
| 1.0   | explicitly stated in the chunk                                 |
| 0.8   | strongly implied                                               |
| 0.6   | reasonably inferred                                            |
| 0.4   | weakly suggested                                               |
| 0.2   | speculative                                                    |

## Rules

1. ``node_type`` MUST be one of the 9 values above. If the natural label
   is "market" or "concept" or "technology", use ``entity`` and put the
   original label in ``description``.
2. Skip trivial nodes — every noun is not a node. Focus on things
   USEFUL for reasoning about technology, markets, investments, and
   competitive dynamics.
3. Edge ``source`` and ``target`` must reference ``node_id`` values you
   declared in the same response. Don't reference outside nodes.
4. If the chunk contains nothing extractable, return empty arrays.

Respond with JSON only — no prose before or after, no markdown fences:

{
  "nodes": [
    {"node_id": "<local id>", "node_type": "<one of 9>",
     "canonical_label": "<primary name>", "description": "<brief>",
     "confidence": <0.0..1.0>}
  ],
  "edges": [
    {"source_node_id": "<local id>", "target_node_id": "<local id>",
     "relation": "<verb_or_relation>", "confidence": <0.0..1.0>}
  ]
}
""".strip()


# ---------------------------------------------------------------------------
# Parsed-output types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractedNode:
    local_id: str  # the LLM's identifier (used to wire edges)
    node_type: str  # validated against ANTIEK_NODE_TYPES; falls back to "entity"
    canonical_label: str
    description: str = ""
    confidence: float = 0.6
    original_type: Optional[str] = None  # set when we coerced concept/market/technology → entity


@dataclass(frozen=True)
class ExtractedEdge:
    source_local_id: str
    target_local_id: str
    relation: str
    confidence: float


@dataclass(frozen=True)
class ExtractionResult:
    chunk_id: str
    nodes_written: int = 0
    edges_written: int = 0
    nodes_skipped: int = 0  # malformed or referencing missing nodes
    edges_skipped: int = 0
    extracted_nodes: tuple[ExtractedNode, ...] = field(default_factory=tuple)
    extracted_edges: tuple[ExtractedEdge, ...] = field(default_factory=tuple)
    # node_id of each successfully written node (for downstream linking).
    written_node_ids: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _normalize_node_type(raw: Any) -> tuple[str, Optional[str]]:
    """Returns ``(antiek_type, original_if_coerced)``. Coerces
    Researchmaxx's "concept" / "market" / "technology" to "entity"
    with the original recorded in metadata."""
    if not isinstance(raw, str):
        return "entity", str(raw) if raw is not None else None
    lowered = raw.strip().lower()
    if lowered in ANTIEK_NODE_TYPES:
        return lowered, None
    # Coercion table for the common Researchmaxx values that don't
    # map directly. Anything else also becomes "entity" with the
    # original preserved.
    return "entity", lowered or None


def _clamp_confidence(raw: Any, default: float = 0.6) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, v))


def parse_extraction_response(text: str) -> tuple[list[ExtractedNode], list[ExtractedEdge]]:
    """Parse the LLM's JSON response into typed ExtractedNode +
    ExtractedEdge lists. Tolerates malformed input (returns empty
    lists rather than raising)."""
    obj = _extract_json_object(text)
    if obj is None:
        return [], []

    raw_nodes = obj.get("nodes") or []
    raw_edges = obj.get("edges") or []

    nodes: list[ExtractedNode] = []
    if isinstance(raw_nodes, list):
        for rn in raw_nodes:
            if not isinstance(rn, dict):
                continue
            local_id = rn.get("node_id")
            label = rn.get("canonical_label")
            if not isinstance(local_id, str) or not isinstance(label, str):
                continue
            if not local_id.strip() or not label.strip():
                continue
            ntype, original = _normalize_node_type(rn.get("node_type"))
            nodes.append(ExtractedNode(
                local_id=local_id.strip(),
                node_type=ntype,
                canonical_label=label.strip(),
                description=str(rn.get("description") or "").strip(),
                confidence=_clamp_confidence(rn.get("confidence")),
                original_type=original,
            ))

    declared = {n.local_id for n in nodes}
    edges: list[ExtractedEdge] = []
    if isinstance(raw_edges, list):
        for re in raw_edges:
            if not isinstance(re, dict):
                continue
            src = re.get("source_node_id")
            tgt = re.get("target_node_id")
            rel = re.get("relation")
            if not isinstance(src, str) or not isinstance(tgt, str):
                continue
            if not isinstance(rel, str) or not rel.strip():
                continue
            # An edge that references undeclared nodes is malformed —
            # drop it rather than letting the FK violation surface
            # downstream.
            if src not in declared or tgt not in declared:
                continue
            edges.append(ExtractedEdge(
                source_local_id=src,
                target_local_id=tgt,
                relation=rel.strip(),
                confidence=_clamp_confidence(re.get("confidence")),
            ))
    return nodes, edges


# ---------------------------------------------------------------------------
# Extraction pipeline
# ---------------------------------------------------------------------------


def _read_chunk(db_path: str, chunk_id: str) -> Optional[tuple[str, Optional[str], int]]:
    """Look up ``(text, document_id, source_tier)`` for a chunk_id.
    Returns None when the chunk doesn't exist."""
    con = connect_read(db_path)
    try:
        row = con.execute(
            "SELECT c.text, c.document_id, d.source_tier "
            "FROM chunks c JOIN documents d ON c.document_id = d.document_id "
            "WHERE c.chunk_id = ?",
            [chunk_id],
        ).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    return str(row[0]), (row[1] if row[1] is not None else None), int(row[2])


def extract_from_chunk(
    *,
    chunk_id: str,
    investigation_id: str,
    db_path: Optional[str] = None,
    embedder: Optional[EmbeddingProvider] = None,
    parent_event_id: Optional[str] = None,
) -> ExtractionResult:
    """The pipeline. Read chunk text → dispatch parameter_extractor →
    parse → write nodes + edges (each emits its own GRAPH_*_INSERTED
    typed event).

    Idempotent via ``on_conflict='ignore'`` on every insert — same
    chunk re-extracted produces no duplicate rows and no duplicate
    events. The semantic-equivalent node from a different chunk does
    get a distinct edge (chunk_id is folded into the edge's content
    hash) which is the correct attribution behavior.
    """
    resolved_db = db_path or default_db_path()
    ensure_initialized(resolved_db)

    fetched = _read_chunk(resolved_db, chunk_id)
    if fetched is None:
        return ExtractionResult(chunk_id=chunk_id)
    text, document_id, source_tier = fetched
    tier = source_tier if source_tier is not None else DEFAULT_SOURCE_TIER

    # Dispatch the extractor.
    full_prompt = EXTRACTION_SYSTEM_PROMPT + "\n\nChunk ID: " + chunk_id + "\n\n## Text\n" + text
    try:
        result = dispatch(
            full_prompt,
            "parameter_extractor",
            investigation_id=investigation_id,
            parent_event_id=parent_event_id,
        )
        response_text = result.text
    except (ProviderError, KeyError):
        # No provider / provider failed → no nodes/edges this round.
        # Returning an empty result is the right posture; a retry can
        # re-run extraction without changing the chunk row.
        return ExtractionResult(chunk_id=chunk_id)

    nodes, edges = parse_extraction_response(response_text)
    if not nodes:
        return ExtractionResult(chunk_id=chunk_id)

    # Resolve the embedder for node-label embeddings.
    emb = embedder if embedder is not None else default_embedding_provider()

    con = connect_write(resolved_db, purpose="extraction.write_nodes_edges")
    written_node_ids: dict[str, str] = {}
    nodes_written = 0
    nodes_skipped = 0
    edges_written = 0
    edges_skipped = 0
    try:
        for n in nodes:
            try:
                node_metadata: dict[str, Any] = {
                    "chunk_id": chunk_id,
                    "extraction_confidence": n.confidence,
                    "description": n.description,
                }
                if n.original_type:
                    node_metadata["original_node_type"] = n.original_type
                node_id = insert_node(
                    con,
                    canonical_label=n.canonical_label,
                    node_type=n.node_type,
                    graph_scope=DEFAULT_GRAPH_SCOPE,
                    investigation_id=investigation_id,
                    embedding=emb.encode(n.canonical_label),
                    metadata=node_metadata,
                    parent_event_id=parent_event_id,
                    on_conflict="ignore",
                )
                written_node_ids[n.local_id] = node_id
                nodes_written += 1
            except Exception:  # pragma: no cover — defensive
                nodes_skipped += 1

        for e in edges:
            src_global = written_node_ids.get(e.source_local_id)
            tgt_global = written_node_ids.get(e.target_local_id)
            if not src_global or not tgt_global:
                edges_skipped += 1
                continue
            try:
                insert_edge(
                    con,
                    source_node_id=src_global,
                    target_node_id=tgt_global,
                    relation=e.relation,
                    source_tier=int(tier),
                    extraction_confidence=e.confidence,
                    graph_scope=DEFAULT_GRAPH_SCOPE,
                    investigation_id=investigation_id,
                    chunk_id=chunk_id,
                    source_document_id=document_id,
                    parent_event_id=parent_event_id,
                    on_conflict="ignore",
                )
                edges_written += 1
            except Exception:  # pragma: no cover — defensive
                edges_skipped += 1
    finally:
        con.close()

    return ExtractionResult(
        chunk_id=chunk_id,
        nodes_written=nodes_written,
        edges_written=edges_written,
        nodes_skipped=nodes_skipped,
        edges_skipped=edges_skipped,
        extracted_nodes=tuple(nodes),
        extracted_edges=tuple(edges),
        written_node_ids=written_node_ids,
    )
