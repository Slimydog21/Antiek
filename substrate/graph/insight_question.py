"""DRW SPR-01 — promotion of insights and questions to graph nodes.

``promote_insight`` / ``promote_question`` are the **only** sanctioned
writers of ``node_type='insight'`` / ``'question'`` rows. They turn a
distilled note (``note.emerged``) or an identified question
(``question.identified``) into a first-class graph node — with an
embedding and provenance edges drawn from the controlled
``INSIGHT_QUESTION_RELATIONS`` vocabulary — so the rest of the Deep
Research Workspace can traverse, join, and similarity-search them.

Design choices (see also docs/decisions if promoted to canon):

* **Single writer.** Every node + its edges are written through
  ``runtime/db_lock.connect_write``. When the caller passes its own
  ``LockedConnection`` (the backfill, the SPR-02 promotion funnel) it
  owns the transaction boundary; when it does not, this module acquires
  a fresh write-locked connection and commits node+edges **atomically**
  so there is never a node-without-its-edges intermediate state.

* **Dedup identity = content hash of normalized text.** The node id is
  ``content_addressed_id(node_type, canonical_text)`` where
  ``canonical_text`` is the insight/question text lower-cased with
  whitespace collapsed and stripped. Re-emitting the same note (same
  text, modulo case/whitespace) resolves to the same node id; with
  ``on_conflict='ignore'`` that is a no-op — no duplicate row, no
  duplicate ``GRAPH_NODE_INSERTED`` event. The hash is SHA-256 truncated
  to 16 hex chars (64 bits). At the corpus scale this product targets
  (≤ 10^6 notes), the birthday-bound collision probability is
  ~N²/2^65 ≈ 3×10⁻⁸ — negligible, and a collision degrades to "two
  distinct insights share a node", caught downstream by text inequality,
  never silent corruption.

* **Provenance the schema can actually hold.** Edges are node→node, so
  the investigation an insight came from rides on the
  ``GRAPH_NODE_INSERTED`` event envelope's ``investigation_id`` and in
  node ``metadata``; the grounding document/chunk rides on the
  ``supported_by`` edge's own ``source_document_id`` / ``chunk_id``
  columns. A cited node that no longer exists (deleted claim) is a
  **dangling edge** — we skip it and record the skip in metadata rather
  than fail the whole promotion (tombstone-not-cascade policy).

Promotion from events is **opt-in** via the ``enabled`` flag on
``promote_from_note_event`` / ``promote_from_question_event``. SPR-03
owns the always-on trigger; this sprint only builds the path.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from contextlib import suppress
from typing import Any, TypeVar

T = TypeVar("T")

try:
    from ...constants import (
        DUCKDB_PATH,
        validate_insight_question_edge,
    )
    from ...runtime.db_lock import LockedConnection, connect_write
    from .ops import content_addressed_id, insert_edge, insert_node
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]
    from substrate.constants import (  # type: ignore[no-redef]
        DUCKDB_PATH,
        validate_insight_question_edge,
    )
    from substrate.graph.ops import (  # type: ignore[no-redef]
        content_addressed_id,
        insert_edge,
        insert_node,
    )


# insight/question live in the primary in-domain ("depth") graph — not
# the cross_domain connector layer nor the constraint layer.
_PROMOTION_GRAPH_SCOPE = "depth"

# Map the note-taker's ConfidenceLevel string onto an edge
# extraction_confidence float (the edges table needs a 0..1 number).
_CONFIDENCE_TO_FLOAT = {
    "high": 0.9,
    "moderate": 0.7,
    "low": 0.5,
    "unknown": 0.5,
}


def graph_db_path() -> str:
    """Resolve the canonical graph DB path. Honors the ``ANTIEK_DUCKDB_PATH``
    operator/test override first, then falls back to ``constants.DUCKDB_PATH``
    (``~`` expanded) — identical resolution to ``substrate.graph.default_db_path``,
    so the connect-our-own-connection writers here (promotion + living-note)
    target the *same* file the readers (default_db_path callers, the distill
    surface, the cascade routes) open. Without this, an environment that sets
    ANTIEK_DUCKDB_PATH would split the graph writer and readers across two
    files."""
    explicit = os.environ.get("ANTIEK_DUCKDB_PATH")
    if explicit:
        return os.path.expanduser(explicit)
    return os.path.expanduser(DUCKDB_PATH)


def canonical_text(text: str) -> str:
    """Normalization for dedup identity: lower-case, collapse internal
    whitespace, strip. Documented so a future maintainer can reproduce
    the identity decision rather than guess it. ``str.split()`` collapses
    every run of whitespace (incl. newlines/tabs) to single spaces."""
    return " ".join(text.lower().split())


def insight_node_id(text: str, *, identity_scope: str | None = None) -> str:
    """Deterministic node id for an insight with this (normalized) text."""
    identity = canonical_text(text)
    if identity_scope is not None:
        identity_scope = _identity_scope(identity_scope)
        identity = f"{identity_scope}:{identity}"
    return content_addressed_id("insight", identity)


def question_node_id(text: str, *, identity_scope: str | None = None) -> str:
    """Deterministic node id for a question with this (normalized) text."""
    identity = canonical_text(text)
    if identity_scope is not None:
        identity_scope = _identity_scope(identity_scope)
        identity = f"{identity_scope}:{identity}"
    return content_addressed_id("question", identity)


def _identity_scope(value: str) -> str:
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > 512 or any(byte < 32 or byte == 127 for byte in encoded):
        raise ValueError("identity_scope is invalid")
    return value


def _node_type_of(con: LockedConnection, node_id: str) -> str | None:
    row = con.execute(
        "SELECT node_type FROM nodes WHERE node_id = ? LIMIT 1", [node_id]
    ).fetchone()
    return row[0] if row else None


def _verify_private_node(
    con: LockedConnection,
    *,
    node_id: str,
    label: str,
    node_type: str,
    metadata: dict[str, Any],
    owner_user_id: str | None,
) -> None:
    if owner_user_id is None:
        return
    row = con.execute(
        "SELECT canonical_label, node_type, graph_scope, metadata, owner_user_id "
        "FROM nodes WHERE node_id=?",
        [node_id],
    ).fetchone()
    expected = (label, node_type, _PROMOTION_GRAPH_SCOPE, metadata, owner_user_id)
    actual = None if row is None else (row[0], row[1], row[2], json.loads(row[3]), row[4])
    if actual != expected:
        raise ValueError("private promoted graph node conflicts")


def _coerce_confidence_float(confidence: str) -> float:
    return _CONFIDENCE_TO_FLOAT.get(confidence, 0.5)


def _add_provenance_edges(
    con: LockedConnection,
    *,
    source_node_id: str,
    relation: str,
    targets: Sequence[str],
    emit_events: bool = True,
    owner_user_id: str | None = None,
    investigation_id: str,
    source_tier: int,
    extraction_confidence: float,
    source_document_id: str | None,
    chunk_id: str | None,
    event_sink: Callable[[Any], None] | None = None,
) -> tuple[list, list]:
    """Create ``relation`` edges from ``source_node_id`` to each target
    node, validating against the controlled vocabulary. Returns
    ``(written_edge_ids, skipped_dangling_targets)``. A target that does
    not exist is skipped (tombstone policy), not an error."""
    written: list = []
    dangling: list = []
    for target_id in targets:
        ttype = _node_type_of(con, target_id)
        if ttype is None:
            dangling.append(target_id)
            continue
        target_owner = con.execute(
            "SELECT owner_user_id FROM nodes WHERE node_id=?", [target_id]
        ).fetchone()[0]
        if owner_user_id is not None and target_owner not in (None, owner_user_id):
            raise ValueError("private graph edge target owner conflicts")
        # Loud failure if the caller wires an out-of-vocabulary edge.
        validate_insight_question_edge(relation, _node_type_of_source(relation), ttype)
        eid = insert_edge(
            con,
            source_node_id=source_node_id,
            target_node_id=target_id,
            relation=relation,
            source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            graph_scope=_PROMOTION_GRAPH_SCOPE,
            investigation_id=investigation_id,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            on_conflict="ignore",
            emit_event=emit_events,
            event_sink=event_sink,
        )
        written.append(eid)
    return written, dangling


def _node_type_of_source(relation: str) -> str:
    """The source node_type a relation originates from (insight or
    question), per the vocabulary."""
    from ..constants import _INSIGHT_QUESTION_RELATION_BY_NAME  # type: ignore
    spec = _INSIGHT_QUESTION_RELATION_BY_NAME.get(relation)
    if spec is None:
        raise ValueError(f"unknown insight/question relation {relation!r}")
    return spec.source_type


def _with_connection(  # noqa: UP047 - Python 3.11 support
    con: LockedConnection | None,
    purpose: str,
    fn: Callable[[LockedConnection], T],
) -> T:
    """Run ``fn(con)`` either on the caller's connection (caller owns the
    transaction) or on a fresh write-locked connection wrapped in an
    atomic BEGIN/COMMIT."""
    if con is not None:
        return fn(con)
    owned = connect_write(graph_db_path(), purpose=purpose)
    try:
        owned.execute("BEGIN")
        try:
            result = fn(owned)
            owned.execute("COMMIT")
            return result
        except Exception:
            with suppress(Exception):
                owned.execute("ROLLBACK")
            raise
    finally:
        owned.close()


def promote_insight(
    *,
    text: str,
    investigation_id: str,
    confidence: str = "unknown",
    supported_by: Sequence[str] = (),
    source_document_id: str | None = None,
    chunk_id: str | None = None,
    source_tier: int = 3,
    extraction_confidence: float | None = None,
    embedding_provider: Any = None,
    metadata: dict[str, Any] | None = None,
    source_kind: str | None = None,
    con: LockedConnection | None = None,
    dedup: bool = False,
    dedup_rate: Any = None,
    identity_scope: str | None = None,
    owner_user_id: str | None = None,
    emit_graph_events: bool = True,
) -> str:
    """Promote an insight to a first-class ``insight`` node. Returns the
    node id (stable, content-addressed — idempotent on re-promotion).

    AFF SPR-07: when ``dedup=True``, the candidate is run through
    ``substrate.unit_dedup.find_near_duplicate`` against the already-deposited
    insight units in its provenance scope BEFORE the row is inserted. On a match
    the row insert is SKIPPED and a ``duplicate_of`` edge to the surviving unit
    is recorded instead (carrying this candidate's provenance), and the returned
    node id is the SURVIVOR's — so a near-duplicate compounds onto the existing
    unit rather than bloating the graph with a new row. ``dedup`` is OFF by
    default so existing callers are unchanged. ``dedup_rate`` is an optional
    ``substrate.unit_dedup.DedupRate`` counter the path increments per attempt
    (linked or not) for the M5 dedup-rate metric.

    ``supported_by`` is a sequence of *node ids* (claims/entities) the
    insight rests on; each becomes a ``supported_by`` edge carrying
    ``source_document_id`` + ``chunk_id`` for the originating source.

    ``source_kind`` is the §9 provenance discriminator. A model-distilled
    insight (the ``note.emerged`` path) leaves it ``None`` — the absence is
    "model-emerged", the default shape. A *user-authored* insight (the
    in-book marginalia note, ``marginalia.noted``) passes
    ``source_kind="user"``, which is stamped into node metadata so the node
    can NEVER be conflated with a model-emerged one downstream. The chunk the
    note anchors to (``chunk_id``) is recorded on the node metadata too, so
    block_search resolves the per-book document the same way it does for a
    distilled insight.
    """
    nid = insight_node_id(text, identity_scope=identity_scope)
    edge_conf = (
        extraction_confidence
        if extraction_confidence is not None
        else _coerce_confidence_float(confidence)
    )

    def _do(c: LockedConnection) -> str:
        node_meta: dict[str, Any] = dict(metadata or {})
        node_meta.update(
            {
                "promoted_kind": "insight",
                "confidence": confidence,
                "canonical_text": canonical_text(text),
                # AFF SPR-04: stamp the deposit's investigation_id into node
                # metadata. The ``nodes`` table has no investigation_id column
                # (it rides the GRAPH_NODE_INSERTED event envelope), but a
                # marginalia insight has no ``supported_by`` edge to recover it
                # from — so without this mirror ``knowledge_unit_of`` would
                # project investigation_id='' for the marginalia path and SPR-07
                # dedup keyed on investigation scope would mis-bucket it. This
                # rides the existing metadata JSON payload — no event schema
                # change (EVENT_SCHEMA_VERSION not bumped by this change; canonical value is in events.py).
                "investigation_id": investigation_id,
            }
        )
        if identity_scope is not None:
            node_meta["identity_scope"] = identity_scope
        # §9 provenance discriminator. Stamped only when the caller asserts
        # one (the user-authored marginalia path). A model-emerged insight
        # carries no source_kind — the absence IS "model", and we never
        # invent a "user" label for a model note (nor the reverse).
        if source_kind is not None:
            node_meta["source_kind"] = source_kind
        # Grounding on the node itself (the supported_by edge also carries
        # it, but the living-note path resolves the note's document from node
        # metadata, and the distill surface reads grounding from the row).
        # block_search resolves the document via metadata.chunk_id, so a
        # marginalia note with no claim-node target still resolves its book.
        if source_document_id:
            node_meta.setdefault("source_document_id", source_document_id)
        if chunk_id:
            node_meta.setdefault("chunk_id", chunk_id)
        provider = embedding_provider or _default_provider()
        # AFF SPR-07 — link a near-duplicate instead of inserting a new row.
        if dedup:
            match = _dedup_check(
                c,
                node_type="insight",
                candidate_node_id=nid,
                candidate_text=text,
                investigation_id=investigation_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_tier=source_tier,
                extraction_confidence=edge_conf,
                provider=provider,
                dedup_rate=dedup_rate,
                emit_events=emit_graph_events,
            )
            if match is not None:
                # Linked, not stored: skip the row insert + provenance edges and
                # return the SURVIVOR's id. The survivor's row (and its §9.0
                # servability) is untouched.
                return match.existing_unit_id
        emb = provider.encode(text)
        insert_node(
            c,
            canonical_label=text,
            node_type="insight",
            graph_scope=_PROMOTION_GRAPH_SCOPE,
            investigation_id=investigation_id,
            embedding=emb,
            metadata=node_meta,
            node_id=nid,
            on_conflict="ignore",
            owner_user_id=owner_user_id,
            emit_event=emit_graph_events,
        )
        _verify_private_node(
            c,
            node_id=nid,
            label=text,
            node_type="insight",
            metadata=node_meta,
            owner_user_id=owner_user_id,
        )
        _written, dangling = _add_provenance_edges(
            c,
            source_node_id=nid,
            relation="supported_by",
            targets=supported_by,
            investigation_id=investigation_id,
            source_tier=source_tier,
            extraction_confidence=edge_conf,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            emit_events=emit_graph_events,
            owner_user_id=owner_user_id,
        )
        if dangling:
            _record_dangling(c, nid, "supported_by", dangling)
        return nid

    return _with_connection(con, "promote_insight", _do)


def promote_question(
    *,
    text: str,
    investigation_id: str,
    asks_about: Sequence[str] = (),
    resolved_by: Sequence[str] = (),
    anchor_region_id: str | None = None,
    source_document_id: str | None = None,
    chunk_id: str | None = None,
    source_tier: int = 3,
    extraction_confidence: float = 0.5,
    embedding_provider: Any = None,
    metadata: dict[str, Any] | None = None,
    con: LockedConnection | None = None,
    dedup: bool = False,
    dedup_rate: Any = None,
    identity_scope: str | None = None,
    owner_user_id: str | None = None,
    emit_graph_events: bool = True,
    event_sink: Callable[[Any], None] | None = None,
) -> str:
    """Promote a question to a first-class ``question`` node. Returns the
    node id (stable, content-addressed — idempotent on re-promotion).

    ``asks_about`` are node ids the question concerns; ``resolved_by`` are
    insight node ids that answer it.

    AFF SPR-07: ``dedup`` / ``dedup_rate`` behave exactly as in
    :func:`promote_insight` — a near-duplicate question links to the surviving
    question node (a ``duplicate_of`` self-edge) instead of inserting a row.
    Questions dedup against questions only (never against insights).
    """
    nid = question_node_id(text, identity_scope=identity_scope)

    def _do(c: LockedConnection) -> str:
        node_meta: dict[str, Any] = dict(metadata or {})
        node_meta.update(
            {
                "promoted_kind": "question",
                "canonical_text": canonical_text(text),
                # AFF SPR-04: stamp investigation_id into node metadata. A
                # question node grounds via asks_about/resolved_by (never
                # supported_by), so ``knowledge_unit_of`` cannot recover the
                # investigation from a supported_by edge — this mirror is the
                # single source the projection reads for the question path.
                # Rides the existing metadata JSON — no event schema bump.
                "investigation_id": investigation_id,
            }
        )
        if identity_scope is not None:
            node_meta["identity_scope"] = identity_scope
        if anchor_region_id:
            node_meta["anchor_region_id"] = anchor_region_id
        if source_document_id:
            node_meta.setdefault("source_document_id", source_document_id)
        # AFF SPR-04: mirror chunk_id onto the question node too (the insight
        # path already does at the marginalia branch). A question grounds via
        # asks_about/resolved_by, never supported_by, so ``knowledge_unit_of``
        # recovers its claim→chunk→doc grounding from metadata, not an edge —
        # without the chunk_id mirror a grounded question would be wrongly
        # rejected as ungrounded.
        if chunk_id:
            node_meta.setdefault("chunk_id", chunk_id)
        provider = embedding_provider or _default_provider()
        # AFF SPR-07 — link a near-duplicate question instead of inserting.
        if dedup:
            match = _dedup_check(
                c,
                node_type="question",
                candidate_node_id=nid,
                candidate_text=text,
                investigation_id=investigation_id,
                source_document_id=source_document_id,
                chunk_id=chunk_id,
                source_tier=source_tier,
                extraction_confidence=extraction_confidence,
                provider=provider,
                dedup_rate=dedup_rate,
                emit_events=emit_graph_events,
                event_sink=event_sink,
            )
            if match is not None:
                return match.existing_unit_id
        emb = provider.encode(text)
        insert_node(
            c,
            canonical_label=text,
            node_type="question",
            graph_scope=_PROMOTION_GRAPH_SCOPE,
            investigation_id=investigation_id,
            embedding=emb,
            metadata=node_meta,
            node_id=nid,
            on_conflict="ignore",
            owner_user_id=owner_user_id,
            emit_event=emit_graph_events,
            event_sink=event_sink,
        )
        _verify_private_node(
            c,
            node_id=nid,
            label=text,
            node_type="question",
            metadata=node_meta,
            owner_user_id=owner_user_id,
        )
        _w1, d1 = _add_provenance_edges(
            c, source_node_id=nid, relation="asks_about", targets=asks_about,
            investigation_id=investigation_id, source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            source_document_id=source_document_id, chunk_id=chunk_id,
            emit_events=emit_graph_events,
            owner_user_id=owner_user_id,
            event_sink=event_sink,
        )
        _w2, d2 = _add_provenance_edges(
            c, source_node_id=nid, relation="resolved_by", targets=resolved_by,
            investigation_id=investigation_id, source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            source_document_id=source_document_id, chunk_id=chunk_id,
            emit_events=emit_graph_events,
            owner_user_id=owner_user_id,
            event_sink=event_sink,
        )
        if d1:
            _record_dangling(c, nid, "asks_about", d1)
        if d2:
            _record_dangling(c, nid, "resolved_by", d2)
        return nid

    return _with_connection(con, "promote_question", _do)


# ---------------------------------------------------------------------------
# AFF SPR-07 — cross-investigation dedup: link a near-duplicate, don't re-store.
#
# Before a deposit inserts a new insight/question row, the deposit path may run
# the candidate through ``substrate.unit_dedup.find_near_duplicate`` against the
# already-deposited units IN ITS OWN node_type. On a match it records a
# ``duplicate_of`` edge to the surviving unit (carrying the candidate's primary
# doc/chunk grounding to the survivor; merging its ADDITIONAL supported_by links
# is a KNOWN GAP deferred to the always-on flip — see _link_duplicate) and SKIPS
# the row insert, so the graph compounds rather than bloats.
#
# Single-writer + §16 preserved: this runs on the SAME write-locked connection
# the deposit already holds (no new writer, no new query pattern beyond the
# reads ``_node_type_of``/``knowledge_unit_of`` already do), and the detector
# itself is pure (no DB). §9.0-safe: a ``duplicate_of`` link never touches the
# survivor's row, so its servability is unchanged by construction (the deposit
# tests assert this). The dedup is OPT-IN (``dedup=True``) so every existing
# caller is byte-for-byte unchanged; SPR-07's tests + a future always-on trigger
# turn it on.
# ---------------------------------------------------------------------------


def _dedup_check(
    con: LockedConnection,
    *,
    node_type: str,
    candidate_node_id: str,
    candidate_text: str,
    investigation_id: str,
    source_document_id: str | None,
    chunk_id: str | None,
    source_tier: int,
    extraction_confidence: float,
    provider: Any,
    dedup_rate: Any,
    emit_events: bool,
    event_sink: Callable[[Any], None] | None = None,
):
    """Run the candidate through the SPR-07 detector against scoped existing
    units; on a match, record the ``duplicate_of`` edge + count it; return the
    ``DuplicateMatch`` (or None). Increments ``dedup_rate`` once per attempt
    (linked or not). This is the ONE place the deposit path calls
    ``find_near_duplicate`` — once per candidate, before any insert."""
    from substrate.unit_dedup import CandidateUnit, find_near_duplicate

    existing = _scoped_existing_units(
        con,
        node_type=node_type,
        investigation_id=investigation_id,
        source_document_id=source_document_id,
    )
    candidate = CandidateUnit(
        text=candidate_text,
        retrieval_key=candidate_node_id,
        investigation_id=investigation_id,
        source_document_id=source_document_id,
    )
    match = find_near_duplicate(candidate, existing, embedding_provider=provider)
    if match is not None:
        _link_duplicate(
            con,
            survivor_id=match.existing_unit_id,
            candidate_node_id=candidate_node_id,
            candidate_text=candidate_text,
            node_type=node_type,
            investigation_id=investigation_id,
            source_tier=source_tier,
            extraction_confidence=extraction_confidence,
            source_document_id=source_document_id,
            chunk_id=chunk_id,
            match=match,
            emit_events=emit_events,
            event_sink=event_sink,
        )
    if dedup_rate is not None:
        dedup_rate.record(linked=match is not None)
    return match


def _scoped_existing_units(
    con: LockedConnection,
    *,
    node_type: str,
    investigation_id: str,
    source_document_id: str | None,
):
    """Read the already-deposited units in the candidate's provenance SCOPE
    (same investigation, or the same grounding document) and project them onto
    ``substrate.unit_dedup.ExistingUnit``. The detector's scope guard also
    re-checks scope per-pair, so an over-broad read here is safe — we narrow to
    the candidate's investigation_id (mirrored into node metadata at deposit)
    OR its source_document_id to keep the comparison set bounded.

    Reads the node id + canonical_label + the metadata-mirrored investigation_id
    and grounding doc (and the supported_by edge's source_document_id as a
    fallback). The candidate's own node id is never in this set (it is not
    inserted yet)."""
    import json as _json

    from substrate.unit_dedup import ExistingUnit

    rows = con.execute(
        "SELECT node_id, canonical_label, metadata FROM nodes "
        "WHERE node_type = ?",
        [node_type],
    ).fetchall()
    out = []
    for nid, label, meta_raw in rows:
        meta = {}
        if meta_raw:
            try:
                meta = _json.loads(meta_raw)
            except (TypeError, ValueError):
                meta = {}
        inv = meta.get("investigation_id") or ""
        doc = meta.get("source_document_id")
        if doc is None:
            edge = con.execute(
                "SELECT source_document_id FROM edges WHERE source_node_id = ? "
                "AND relation = 'supported_by' AND source_document_id IS NOT NULL "
                "LIMIT 1",
                [nid],
            ).fetchone()
            doc = edge[0] if edge else None
        # Only keep units that share the candidate's scope (the detector
        # re-checks, but narrowing here bounds the embedding work).
        in_scope = (investigation_id and inv == investigation_id) or (
            source_document_id is not None and doc == source_document_id
        )
        if not in_scope:
            continue
        out.append(
            ExistingUnit(
                unit_id=nid,
                text=label,
                retrieval_key=nid,  # node_id IS the SPR-04 retrieval key
                investigation_id=inv,
                source_document_id=doc,
            )
        )
    return out


def _link_duplicate(
    con: LockedConnection,
    *,
    survivor_id: str,
    candidate_node_id: str,
    candidate_text: str,
    node_type: str,
    investigation_id: str,
    source_tier: int,
    extraction_confidence: float,
    source_document_id: str | None,
    chunk_id: str | None,
    match,
    emit_events: bool,
    event_sink: Callable[[Any], None] | None,
) -> str:
    """Record a ``duplicate_of`` edge candidate -> survivor and return the
    edge id. The edge carries the candidate's PRIMARY grounding
    (``source_document_id`` / ``chunk_id``) so the survivor keeps a citation to
    the candidate's source, and stamps the dedup verdict (tier / cosine /
    key_type) into edge metadata for audit.

    KNOWN GAP (deferred to the always-on-flip sprint — see the §9.0/SPR-03-style
    ratification this dedup awaits): only the PRIMARY doc/chunk grounding is
    carried here; the candidate's ADDITIONAL ``supported_by`` claim-node edges
    are NOT yet merged onto the survivor. Harmless while dedup is opt-in/off in
    prod, but the flip MUST absorb the candidate's ``supported_by`` links first
    or the survivor's evidentiary base will be under-counted.

    CRITICAL: the candidate node was NOT inserted (that is the whole point —
    link, don't re-store), so the ``duplicate_of`` edge's SOURCE is the
    survivor's own node id too (a self-referential marker on the survivor that
    records "another deposit resolved here"), NOT a dangling reference to a
    never-written candidate node. We point source==target==survivor so both FK
    columns reference a real row; the candidate's identity rides edge metadata.

    Rides the existing GRAPH_EDGE_INSERTED ActionType (free-form relation) — no
    new event type, no schema bump.

    Edge id: derived from the SURVIVOR + relation + the CANDIDATE's node id, so
    two DISTINCT candidates that resolve to the same survivor produce two
    distinct ``duplicate_of`` edges (one per linked deposit — the dedup-rate
    counts them), while a literal re-emission of the SAME candidate text (same
    candidate_node_id) collapses idempotently via ``on_conflict='ignore'`` and
    is NOT double-counted."""
    from substrate.constants import DUPLICATE_OF_RELATION

    from .ops import content_addressed_id

    edge_id = content_addressed_id(
        "edge",
        f"{survivor_id}|{DUPLICATE_OF_RELATION}|{candidate_node_id}",
    )
    return insert_edge(
        con,
        source_node_id=survivor_id,
        target_node_id=survivor_id,
        relation=DUPLICATE_OF_RELATION,
        source_tier=source_tier,
        extraction_confidence=extraction_confidence,
        graph_scope=_PROMOTION_GRAPH_SCOPE,
        investigation_id=investigation_id,
        source_document_id=source_document_id,
        chunk_id=chunk_id,
        edge_id=edge_id,
        metadata={
            "duplicate_of": survivor_id,
            "candidate_node_id": candidate_node_id,
            "candidate_text": candidate_text,
            "candidate_investigation_id": investigation_id,
            "match_tier": match.tier,
            "match_cosine": match.cosine,
            "match_key_type": match.key_type,
        },
        on_conflict="ignore",
        emit_event=emit_events,
        event_sink=event_sink,
    )


def _record_dangling(con: LockedConnection, node_id: str, relation: str, targets: list) -> None:
    """Append skipped dangling targets into the node's metadata so the
    skip is auditable. Best-effort; failure here never fails promotion."""
    try:
        row = con.execute(
            "SELECT metadata FROM nodes WHERE node_id = ?", [node_id]
        ).fetchone()
        import json
        meta = {}
        if row and row[0]:
            try:
                meta = json.loads(row[0])
            except (TypeError, ValueError):
                meta = {}
        skipped = meta.get("skipped_dangling", {})
        skipped.setdefault(relation, [])
        for t in targets:
            if t not in skipped[relation]:
                skipped[relation].append(t)
        meta["skipped_dangling"] = skipped
        con.execute(
            "UPDATE nodes SET metadata = ? WHERE node_id = ?",
            [json.dumps(meta, default=str), node_id],
        )
    except Exception:  # pragma: no cover — metadata audit is best-effort
        pass


# ---------------------------------------------------------------------------
# Event → node wiring (opt-in; SPR-03 owns the always-on trigger)
# ---------------------------------------------------------------------------


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    """A trajectory row's payload is a dict (``trajectory`` already
    json.loads-es it). Tolerate a still-stringified payload defensively."""
    payload = event.get("payload")
    if isinstance(payload, str):
        import json
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    return payload if isinstance(payload, dict) else {}


def promote_from_note_event(
    event: dict[str, Any],
    *,
    con: LockedConnection | None = None,
    enabled: bool = False,
    embedding_provider: Any = None,
    emit_graph_events: bool = True,
) -> str | None:
    """Promote a single ``note.emerged`` event into an insight node.

    Opt-in: returns ``None`` unless ``enabled=True`` (SPR-03 flips the
    always-on switch). The note's ``source_event_ids`` are recorded in
    node metadata (they reference events, not nodes, so they cannot be
    ``supported_by`` edges); document/claim-node grounding is the job of
    richer callers that pass ``supported_by`` explicitly.
    """
    if not enabled:
        return None
    payload = _event_payload(event)
    text = payload.get("note_text")
    if not isinstance(text, str) or not text.strip():
        return None
    investigation_id = event.get("investigation_id") or payload.get("investigation_id") or ""
    return promote_insight(
        text=text.strip(),
        investigation_id=investigation_id,
        confidence=payload.get("confidence", "unknown"),
        metadata={
            "source_event_ids": payload.get("source_event_ids", []),
            "origin_event_id": event.get("event_id"),
            "origin_note_id": payload.get("note_id"),
        },
        embedding_provider=embedding_provider,
        emit_graph_events=emit_graph_events,
        con=con,
    )


def promote_from_question_event(
    event: dict[str, Any],
    *,
    con: LockedConnection | None = None,
    enabled: bool = False,
    embedding_provider: Any = None,
    emit_graph_events: bool = True,
) -> str | None:
    """Promote a single ``question.identified`` event into a question
    node. Opt-in (see :func:`promote_from_note_event`)."""
    if not enabled:
        return None
    payload = _event_payload(event)
    text = payload.get("question_text")
    if not isinstance(text, str) or not text.strip():
        return None
    investigation_id = event.get("investigation_id") or payload.get("investigation_id") or ""
    return promote_question(
        text=text.strip(),
        investigation_id=investigation_id,
        anchor_region_id=payload.get("anchor_region_id"),
        metadata={
            "origin_event_id": event.get("event_id"),
            "origin_question_id": payload.get("question_id"),
        },
        embedding_provider=embedding_provider,
        emit_graph_events=emit_graph_events,
        con=con,
    )


def promote_from_marginalia_event(
    event: dict[str, Any],
    *,
    con: LockedConnection | None = None,
    enabled: bool = False,
    embedding_provider: Any = None,
    emit_graph_events: bool = True,
) -> str | None:
    """Promote a single ``marginalia.noted`` event into a **user-authored**
    per-book insight node (Read SPR-07 M3).

    This is the in-book FloatMenu NOTE path: the reader highlights a passage
    and chooses "Note", emitting ``marginalia.noted`` (a §9-load-bearing
    user-sourced event). Before this, that note never became a graph node, so
    it was neither searchable nor visible in the ReadingCompanion. Here it
    becomes a first-class ``insight`` node so the one graph holds it — but it
    is kept DISTINCT from a model-emerged insight by stamping
    ``source_kind="user"`` into node metadata (the §9 no-conflation
    invariant: a model reply never inherits "user", a user note never inherits
    a model label). The node is grounded on its book via the event envelope's
    ``document_id`` and the selection's ``chunk_id`` (when one was resolved),
    so a later block_search returns the per-book note.

    The promoted node text is the user's ``note_text`` (their authored
    comment), not the ``excerpt`` (the highlighted span) — the excerpt is
    recorded in metadata as the anchor. Opt-in like the sibling paths (SPR-03
    owns the always-on trigger).

    §9.0 no-leak is preserved: ``marginalia.noted`` only ever carries the
    reader's OWN selection on a gate-served surface (the float-menu's
    outbound chokepoint already refuses a withheld selection upstream), so a
    withheld source's body never enters this node — we promote only what the
    event already legitimately holds.
    """
    if not enabled:
        return None
    payload = _event_payload(event)
    text = payload.get("note_text")
    if not isinstance(text, str) or not text.strip():
        return None
    investigation_id = event.get("investigation_id") or payload.get("investigation_id") or ""
    # The document the selection sits in rides the Event envelope; the chunk
    # (when the host resolved one) rides the payload. Either may be absent
    # (honest null), and that is recorded — never invented.
    document_id = event.get("document_id") or payload.get("document_id")
    chunk_id = payload.get("chunk_id")
    derived_revision_id = payload.get("derived_revision_id")
    derived_content_sha256 = payload.get("derived_content_sha256")
    derived_generation = payload.get("derived_generation")
    derived_grounding = (
        {
            "derived_revision_id": derived_revision_id,
            "derived_content_sha256": derived_content_sha256,
            "derived_generation": derived_generation,
        }
        if (
            isinstance(derived_revision_id, str)
            and re.fullmatch(r"rev_[0-9a-f]{32}", derived_revision_id)
            and isinstance(derived_content_sha256, str)
            and re.fullmatch(r"[0-9a-f]{64}", derived_content_sha256)
            and isinstance(derived_generation, int)
            and not isinstance(derived_generation, bool)
            and derived_generation >= 1
        )
        else {}
    )
    return promote_insight(
        text=text.strip(),
        investigation_id=investigation_id,
        # A marginalia note is the reader's own authorship — the §9 label is
        # pinned at the event and carried onto the node so the graph never
        # conflates it with a model-emerged insight.
        source_kind="user",
        source_document_id=document_id,
        chunk_id=chunk_id if isinstance(chunk_id, str) and chunk_id else None,
        metadata={
            "origin_event_id": event.get("event_id"),
            "origin_note_id": payload.get("note_id"),
            # The highlighted span the note hangs off (the reader's own words),
            # kept for the surface; the node label is the authored note_text.
            "excerpt": payload.get("excerpt"),
            **derived_grounding,
        },
        embedding_provider=embedding_provider,
        emit_graph_events=emit_graph_events,
        con=con,
    )


# ---------------------------------------------------------------------------
# AFF SPR-04 — assemble a deposited node into a KnowledgeUnitContract.
#
# The deposit path is UNCHANGED: promote_insight/promote_question still write
# node + provenance edges atomically through the single writer
# (``_with_connection`` → ``connect_write``), §16-preserving. This helper does
# NOT write — it READS what a deposit already produced (the content-addressed
# node_id, the supported_by edge's source_document_id/chunk_id, the chunk_id
# mirrored into node metadata at L267-270) and projects it onto the
# KnowledgeUnitContract shape so a consumer (or the conformance test) can prove
# a deposit carries every required field. The §9.0 servability tag is SOURCED
# from the existing classifier (``substrate.books.servability``) — we read its
# answer, never re-derive deny-by-default. groundedness_score is left None
# (SPR-08 fills it).
# ---------------------------------------------------------------------------


def servability_tag_for(content_class: str | None, *, taken_down: bool = False):
    """Read the §9.0 classifier's answer for a unit grounded on a source of
    this ``content_class`` and return a ``ServabilityTag``. This does NOT
    re-derive deny-by-default — it asks ``substrate.books.servability`` (the
    single source of the §9.0 mapping) and records the verdict. A None/unknown
    class resolves to a gated (non-servable) tag, exactly as the classifier
    decides. ``content_class`` is normalized to the contract's ``ContentClass``
    Literal only when it is one of the allowlisted full-text classes; otherwise
    it is recorded as None (unknown ⇒ non-servable)."""
    from substrate.books.servability import is_servable_full_text, servability_of
    from substrate.contracts.nodes import ServabilityTag
    from substrate.contracts.servable import FULL_TEXT_SERVABLE

    status = servability_of(content_class, taken_down=taken_down)
    serves = is_servable_full_text(status)
    # Type the recorded class against the contract Literal: only surface a
    # content_class the contract recognizes AND that is servable; anything
    # else (None, unknown, gated, taken_down) records None ⇒ non-servable.
    tag_class = status.value if (serves and status.value in FULL_TEXT_SERVABLE) else None
    return ServabilityTag(content_class=tag_class, serves_full_text=serves)


def knowledge_unit_of(
    con: LockedConnection,
    node_id: str,
    *,
    content_class: str | None = None,
    taken_down: bool = False,
    score_groundedness: bool = False,
):
    """Project a deposited insight/question node (already written by
    ``promote_insight``/``promote_question``) onto a ``KnowledgeUnitContract``.

    Reads the node row + its ``supported_by`` provenance edge from the SAME
    write-locked connection the deposit used (no new writer, no new query
    pattern beyond the reads ``_node_type_of`` already does). The provenance
    link is taken from the edge's ``source_document_id`` / ``chunk_id``, with a
    fallback to the node ``metadata`` mirror (L267-270) for the marginalia path
    that grounds on metadata.chunk_id without a claim-node target. Returns a
    validated ``KnowledgeUnitContract``; raises if the node carries no
    grounding (a unit with no chunk is not depositable as a knowledge unit).

    The §9.0 servability tag is the classifier's answer for ``content_class``
    (read, not re-derived).

    ``groundedness_score`` is left ``None`` by default — SPR-04 conformance
    depends on an unflagged projection leaving the slot empty (it is a slot, not
    a required signal). AFF SPR-08 fills it at projection time when
    ``score_groundedness=True``: the unit's cited chunk text is resolved with a
    SELECT on THIS SAME connection (no nested read connection, no new writer)
    and the shipped #27 lexical scorer
    (``substrate.eval.groundedness.score_claim``) scores the unit's text against
    that evidence. The lexical backend is deterministic, so a deposit-time score
    and a later re-score are identical — the gate (reuse_gate) may re-score
    lazily if the slot is still None without diverging."""
    import json

    from substrate.contracts.nodes import KnowledgeUnitContract, ProvenanceLink

    # ``nodes`` has no ``investigation_id`` column — per this module's docstring
    # the investigation rides the GRAPH_NODE_INSERTED event envelope and the
    # provenance edge, not the node row. So we read the node's identity/text
    # from the row and source investigation_id + grounding from the edge.
    row = con.execute(
        "SELECT node_type, canonical_label, metadata "
        "FROM nodes WHERE node_id = ? LIMIT 1",
        [node_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"no node {node_id!r} to assemble into a knowledge unit")
    node_type, text, meta_raw = row
    meta: dict[str, Any] = {}
    if meta_raw:
        try:
            meta = json.loads(meta_raw)
        except (TypeError, ValueError):
            meta = {}

    # Prefer the supported_by edge's grounding + investigation_id; fall back to
    # the node metadata mirror (the marginalia path records chunk_id/
    # source_document_id there) for the no-claim-node-target case.
    edge = con.execute(
        "SELECT source_document_id, chunk_id, investigation_id FROM edges "
        "WHERE source_node_id = ? AND relation = 'supported_by' "
        "AND chunk_id IS NOT NULL LIMIT 1",
        [node_id],
    ).fetchone()
    source_document_id = (edge[0] if edge else None) or meta.get("source_document_id")
    chunk_id = (edge[1] if edge else None) or meta.get("chunk_id")
    # investigation_id: prefer the supported_by edge (insight grounded on a
    # claim), fall back to the node metadata mirror that promote_insight/
    # promote_question now stamp at deposit (the marginalia + question paths
    # have no supported_by edge to recover it from). Empty/absent is a genuine
    # gap, not a tolerated default — fail LOUD here (AFF SPR-04 BLOCKER 2) so
    # SPR-07 never silently dedups a real deposit under a '' investigation.
    investigation_id = (edge[2] if edge else None) or meta.get("investigation_id")
    if not source_document_id or not chunk_id:
        raise ValueError(
            f"node {node_id!r} carries no claim→chunk→doc grounding "
            f"(source_document_id={source_document_id!r} chunk_id={chunk_id!r}); "
            "not assemblable as a knowledge unit"
        )
    if not investigation_id:
        raise ValueError(
            f"node {node_id!r} carries no investigation_id (neither on its "
            "supported_by edge nor in node metadata); a knowledge unit must "
            "be scoped to its deposit investigation (SPR-07 dedup keys on it). "
            "Ensure promote_insight/promote_question stamped investigation_id."
        )

    groundedness_score: float | None = None
    if score_groundedness:
        groundedness_score = _score_unit_groundedness(con, text, chunk_id)

    # Resolve the content-rights class from the source document when the caller
    # did not supply one. The funnel deposits notes with no supported_by claim
    # node, so the reuse retrieve path's supported_by-join yields a NULL
    # content_class; without this resolution every funnel-promoted unit is
    # flattened to deny-by-default GATED at projection time — starving the
    # flywheel's reuse half even though the unit is grounded on a servable
    # chunk (e.g. a public_domain book's insight is servable, not gated). A
    # read-only SELECT on this connection resolves it (§16-safe). content_class
    # stays None for documents with no/NULL content_class (unknown rights
    # remain deny-by-default — the correct posture).
    if content_class is None and source_document_id:
        doc_cc_row = con.execute(
            "SELECT content_class FROM documents WHERE document_id = ? LIMIT 1",
            [source_document_id],
        ).fetchone()
        if doc_cc_row is not None and doc_cc_row[0]:
            content_class = str(doc_cc_row[0])


    return KnowledgeUnitContract(
        node_id=node_id,
        node_type=node_type,
        text=text,
        investigation_id=investigation_id,  # guaranteed non-empty above
        confidence=meta.get("confidence", "unknown"),
        retrieval_key=node_id,
        provenance=ProvenanceLink(
            source_document_id=source_document_id, chunk_id=chunk_id
        ),
        servability=servability_tag_for(content_class, taken_down=taken_down),
        groundedness_score=groundedness_score,
    )


def _score_unit_groundedness(
    con: LockedConnection, unit_text: str, chunk_id: str | None
) -> float:
    """Score one knowledge unit's text against the text of the chunk it is
    grounded on, using the shipped #27 lexical entailment scorer.

    A knowledge unit IS one claim, so this calls ``score_claim`` directly (not
    the synthesis-level path). The cited chunk text is resolved with a SELECT on
    the SAME connection the projection already holds — no nested read
    connection, no second writer (§16). A unit whose chunk text cannot be
    resolved is scored against EMPTY evidence, which the #27 scorer floors at
    0.0 / not-supported — the no-evidence floor, preserved, not worked around."""
    from substrate.eval.groundedness import score_claim

    chunk_texts: list[str] = []
    if chunk_id:
        row = con.execute(
            "SELECT text FROM chunks WHERE chunk_id = ? LIMIT 1", [chunk_id]
        ).fetchone()
        if row and row[0] is not None:
            chunk_texts.append(str(row[0]))
    verdict = score_claim(
        unit_text, chunk_texts, cited_chunk_ids=[chunk_id] if chunk_id else []
    )
    return verdict.score


# ---------------------------------------------------------------------------
# Embedding provider — reuse the claim-embedding path, no new wiring
# ---------------------------------------------------------------------------


def _default_provider():
    """The same provider claims use. Imported lazily so a test can install
    a hash provider via ANTIEK_EMBEDDING_PROVIDER=hash without paying the
    sentence-transformers import at module load."""
    from processing.embedding import default_embedding_provider
    return default_embedding_provider()
