"""Anchor a Dialogue thread to a passage ``Region`` and persist it to the graph
through the SINGLE sanctioned writer (antiek-reader SPR-06, M3 + M4).

WHAT THIS OWNS
==============
A FloatMenu Dialogue thread is bound to the exact highlighted span via SPR-01's
``Region{document_id, block_id, char_start?, char_end?}`` and stored as a
queryable graph node so it survives reload (replacing ``TalkToBook``'s
``sessionStorage``-only persistence for the shared path).

DESIGN DECISIONS (rigor #5 — logged here so a maintainer finds the "why" in the
code, not a chat):

* NODE TYPE = ``question``. The closed ``NodeType`` taxonomy
  (``substrate.schemas.events.NodeType``) has no "thread"/"dialogue" type, and
  adding one would touch the DB CHECK + the codegen surface (out of scope, and
  the spec says REUSE not invent). A reader highlighting a passage and opening
  a Dialogue *is asking about that passage*, so the ``question`` node — which
  ``substrate.graph.insight_question.promote_question`` already supports with an
  ``anchor_region_id`` + ``source_document_id`` + ``chunk_id`` — is the honest
  fit. WHAT WOULD REVERSE THIS: if a Dialogue thread needs to be queried as a
  distinct kind (e.g. a "my conversations" surface that must exclude research
  questions), add a dedicated ``NodeType`` + migration; until then the
  ``promoted_kind`` metadata marker (``"passage_dialogue"``) distinguishes it.

* ANCHOR IDENTITY = the ``Region``, content-addressed. The thread's node id is
  derived from ``thread_node_id(region)`` — a SHA-256 over the canonical region
  tuple — so RE-OPENING THE SAME HIGHLIGHT REATTACHES THE SAME THREAD (M3
  acceptance) instead of minting a new empty one, and two threads over the SAME
  span collapse to one node (idempotent ``on_conflict="ignore"``). Two threads
  over OVERLAPPING-BUT-DIFFERENT spans get DIFFERENT ids (different char range)
  — they are different anchors, correctly distinct.

* ANCHOR CHAR-RANGE SEMANTICS (rigor #5 — so a future re-extraction can
  re-anchor rather than orphan): ``char_start`` / ``char_end`` are 0-based,
  HALF-OPEN-style offsets *into the block's own text* (the same coordinate
  system SPR-01's ``Region`` and ``DocumentRegionSelectedPayload`` use), NOT
  into the whole document and NOT pixel coordinates. The thread also stores the
  highlighted ``excerpt`` text verbatim, so if the document is re-paginated or
  re-extracted and the char offsets drift, the anchor can be RE-LOCATED by
  quote (the excerpt) and degrade VISIBLY ("passage moved") rather than be
  silently lost. The UI owns the re-location; this module owns the durable
  record (excerpt + region) that makes re-location possible.

SINGLE-WRITER INVARIANT: all writes go through ``substrate.graph.ops.insert_node``,
which asserts a write-locked connection (``runtime.db_lock``) and emits the
``GRAPH_NODE_INSERTED`` typed event. This module NEVER opens a second write
path. We call ``insert_node`` directly (rather than
``insight_question.promote_question``) because the thread's node id must be
content-addressed on the REGION (so re-opening the same span reattaches the same
thread even if the excerpt text changed under re-extraction) — whereas
``promote_question`` content-addresses on the question TEXT. Same writer, same
node table, same event; just the region-stable identity the anchor needs.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from substrate.contracts.reading_surface import AnchoredNote, Region

# The thread is a ``question`` node (a reader highlighting a passage to open a
# Dialogue is asking about it). See the module docstring's node-type decision.
_THREAD_NODE_TYPE = "question"
# The thread lives in the depth graph scope (the same scope promote_question
# uses for promoted reading nodes) — it is a depth-graph artifact, not a
# cross-domain or constraint node.
_THREAD_GRAPH_SCOPE = "depth"


def thread_node_id(region: Region) -> str:
    """Stable, content-addressed id for the Dialogue thread anchored to
    ``region``. Same region tuple → same id (re-open reattaches; idempotent).

    The canonical tuple is ``document_id|block_id|char_start|char_end`` with the
    OPTIONAL char range rendered as ``-`` when whole-block, so a whole-block
    region and a sub-block region over the same block get distinct ids (they are
    different anchors). The ``question-`` prefix matches the node's actual
    ``NodeType`` so the id is self-describing in the graph."""
    cs = "-" if region.char_start is None else str(region.char_start)
    ce = "-" if region.char_end is None else str(region.char_end)
    canonical = f"{region.document_id}|{region.block_id}|{cs}|{ce}"
    h = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"question-{h}"


@dataclass(frozen=True)
class AnchoredThread:
    """The durable record of a persisted Dialogue thread: its graph ``node_id``,
    the ``Region`` it is anchored to, and the verbatim ``excerpt`` (so a future
    re-extraction can re-anchor by quote). ``AnchoredNote`` is the contract
    return; this carries the extra excerpt the re-location needs."""

    node_id: str
    region: Region
    excerpt: str


def anchor_thread(
    *,
    region: Region,
    excerpt: str,
    investigation_id: str,
    con: Any | None = None,
) -> AnchoredThread:
    """Anchor a Dialogue thread to ``region`` and persist it as a graph
    ``question`` node through the SINGLE sanctioned writer. Idempotent on the
    region (re-open reattaches the same node). Returns the durable record.

    ``excerpt`` is the reader's OWN highlighted text (user-sourced) — it is
    stored as the node's canonical label so the thread is human-readable in the
    graph and re-locatable by quote after re-pagination/re-extraction.

    ``con`` is an OPTIONAL pre-opened write-locked connection (the endpoint
    passes one inside its ``connect_write`` block); when omitted, a fresh write-
    locked connection is opened + closed through ``runtime.db_lock`` — still the
    single writer, never a second path.
    """
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import graph_db_path
    from substrate.graph.ops import insert_node

    nid = thread_node_id(region)
    # The label IS the highlighted passage (user-sourced, re-locatable by quote).
    # A degenerate empty excerpt still anchors (label falls back to the region),
    # so a whole-block region with no extracted text never silently drops.
    label = excerpt.strip() or f"passage @ {region.document_id}/{region.block_id}"

    metadata: dict[str, Any] = {
        # Distinguishes a passage-Dialogue thread from a research question on the
        # same ``question`` node type (the reverse-decision marker above).
        "promoted_kind": "passage_dialogue",
        "investigation_id": investigation_id,
        # ``block_id`` is the chunk the selection lands in — the provenance chain
        # claim→chunk→document the graph already models, mirrored on metadata so
        # a grounded-thread query recovers it without an edge.
        "source_document_id": region.document_id,
        "chunk_id": region.block_id,
        # The Region's own char-anchor identity (so a consumer can map node→region).
        "anchor_region_id": nid,
        # The full Region, so a consumer reconstructs the anchor without parsing
        # the node id. char_start/char_end are block-relative offsets (see the
        # module docstring's anchor-semantics paragraph).
        "region": {
            "document_id": region.document_id,
            "block_id": region.block_id,
            "char_start": region.char_start,
            "char_end": region.char_end,
        },
        # The verbatim excerpt for quote-based re-location after re-extraction.
        "anchor_excerpt": excerpt,
    }

    def _do(c: Any) -> None:
        insert_node(
            c,
            canonical_label=label,
            node_type=_THREAD_NODE_TYPE,
            graph_scope=_THREAD_GRAPH_SCOPE,
            investigation_id=investigation_id,
            # No embedding: a Dialogue thread is retrieved by its Region/node id,
            # not by vector similarity — so we pay no embedding cost and stay off
            # any network in test (insert_node accepts embedding=None).
            embedding=None,
            metadata=metadata,
            node_id=nid,
            # Idempotent on the Region: re-opening the same span reattaches the
            # same node, no duplicate row, no duplicate event (M3).
            on_conflict="ignore",
        )

    if con is not None:
        _do(con)
    else:
        with connect_write(graph_db_path(), purpose="dialogue/anchor-thread") as owned:
            _do(owned)
    return AnchoredThread(node_id=nid, region=region, excerpt=excerpt)


def to_anchored_note(thread: AnchoredThread) -> AnchoredNote:
    """The SPR-01 contract return: a thread persisted to a region IS an
    ``AnchoredNote{node_id, region}``. The endpoint returns this so the client
    contract is the pinned contract type, not a sprint-local shape."""
    return AnchoredNote(node_id=thread.node_id, region=thread.region)
