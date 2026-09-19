"""Synthesis archive (Researchmaxx spec §E; architecture_notes §4).

This module is the SOLE writer to the ``syntheses`` table. The
discipline is preserved from Researchmaxx — every synthesis MUST flow
through ``archive_synthesis`` so the substrate manifest, the typed
events, and the constraint-check result land together as one atomic
unit.

What landed in Sprint 2 Day 3-4 (this migration):

- The pure helpers: ``new_synthesis_id``, ``compute_manifest_counts``,
  ``serialize_json_field``.
- The emit helpers: ``emit_synthesis_archived``,
  ``emit_substrate_manifest_written``.
- The ``ArchiveInputs`` dataclass that captures the
  ``archive_synthesis`` argument shape so the eventual DB-writing
  function has a stable signature.

What is DEFERRED (lands when ``substrate/init_db.py`` migrates the
``syntheses`` and ``synthesis_substrate_manifest`` tables):

- The actual ``archive_synthesis(con, inputs) -> str`` function that
  writes the row + manifest in a transaction. Today's stub
  ``archive_synthesis_via_db`` raises ``NotImplementedError`` with a
  clear message — failing loudly is correct until the schema exists.
- The ``load_synthesis`` reader.
- The ``manifest_at_time`` GraphAtTime fallback path.

The emit helpers DON'T require the DB — they only need
``substrate/event_log/``. Roles can call them today to log
``SYNTHESIS_ARCHIVED`` events even though the DB write isn't wired up;
that means RL trajectory capture works ahead of the DB migration.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any


def _to_naive_utc(ts: datetime) -> datetime:
    """Normalize a datetime for DuckDB storage. DuckDB TIMESTAMP is
    tz-naive; tz-aware inputs get stored as local-time wall clock
    (a footgun). Convention: every persistence boundary normalizes
    to naive UTC so comparisons across read/write stay consistent."""
    if ts.tzinfo is not None:
        return ts.astimezone(UTC).replace(tzinfo=None)
    return ts


try:
    from ...event_log import emit_typed, trajectory
    from ...schemas import (
        SubstrateManifestWrittenPayload,
        SynthesisArchivedPayload,
        SynthesisRecommendation,
        SynthesisStatus,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed, trajectory  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        SubstrateManifestWrittenPayload,
        SynthesisArchivedPayload,
        SynthesisRecommendation,
        SynthesisStatus,
    )


# Entity kinds the substrate manifest knows about. Order matters for
# downstream analytics consumers that diff counts across kinds.
MANIFEST_ENTITY_KINDS: tuple[str, ...] = ("document", "chunk", "node", "edge")

_ARCHIVE_REQUESTS_SQL = """
CREATE TABLE IF NOT EXISTS synthesis_archive_requests (
    synthesis_id TEXT PRIMARY KEY REFERENCES syntheses(synthesis_id),
    manifest_request_fingerprint TEXT NOT NULL
)
"""


class SynthesisArchiveConflict(ValueError):
    """A deterministic synthesis id was reused for different archive content."""


def _same_archive_material(stored: tuple[Any, ...], desired: list[Any]) -> bool:
    """Compare immutable synthesis content while ignoring retry timestamp drift."""
    if stored[:7] != tuple(desired[:7]):
        return False
    return all(
        (json.loads(left) if left is not None else None)
        == (json.loads(right) if right is not None else None)
        for left, right in zip(stored[7:], desired[7:], strict=True)
    )


def _manifest_request_fingerprint(inputs: ArchiveInputs) -> str:
    normalized = {
        "document": sorted(set(inputs.document_ids)),
        "chunk": sorted(set(inputs.chunk_ids)),
        "node": sorted(set(inputs.node_ids)),
        "edge": sorted(set(inputs.edge_ids)),
    }
    if inputs.source_synthesis_event_id is not None:
        normalized["source_synthesis_event_id"] = inputs.source_synthesis_event_id
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def new_synthesis_id() -> str:
    """Allocate a fresh synthesis_id. Stable UUIDv4 — same format the
    Researchmaxx pipeline uses, so a migrated trajectory's
    synthesis_ids are still recognizable."""
    return str(uuid.uuid4())


def authorized_synthesis_id(authority: Any, logical_key: str) -> str:
    """Derive an opaque physical id inside one exact graph authority."""
    from substrate.graph.tenancy import graph_key
    from substrate.investigation_tenancy import InvestigationAuthority

    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("authorized synthesis identity requires InvestigationAuthority")
    if (
        not isinstance(logical_key, str)
        or not logical_key
        or logical_key != logical_key.strip()
        or len(logical_key) > 256
    ):
        raise ValueError("authorized synthesis logical key is invalid")
    digest = sha256(
        b"antiek-synthesis-authority-v1\0"
        + bytes.fromhex(graph_key(authority))
        + b"\0"
        + logical_key.encode()
    ).hexdigest()[:32]
    return f"syn-{digest}"


def serialize_json_field(obj: Any) -> str | None:
    """Render an object to its on-disk JSON column form. Validates
    pre-existing strings (raises if they're not valid JSON) so a bug
    upstream surfaces here rather than at SELECT time.

    Mirrors the Researchmaxx ``_as_json`` helper bit-identically so a
    cross-system replay produces equivalent column values."""
    if obj is None:
        return None
    if isinstance(obj, str):
        json.loads(obj)  # validate; raises on malformed input
        return obj
    return json.dumps(obj, default=str)


def compute_manifest_counts(
    *,
    document_ids: Iterable[str] = (),
    chunk_ids: Iterable[str] = (),
    node_ids: Iterable[str] = (),
    edge_ids: Iterable[str] = (),
) -> dict[str, int]:
    """Build the ``counts_by_kind`` mapping for a substrate manifest.

    Callers pass the validated, deduplicated entity sets that will be written,
    so emitted telemetry describes the durable manifest rather than requested
    identifiers that may not exist in the graph."""
    return {
        "document": sum(1 for _ in document_ids),
        "chunk": sum(1 for _ in chunk_ids),
        "node": sum(1 for _ in node_ids),
        "edge": sum(1 for _ in edge_ids),
    }


# ---------------------------------------------------------------------------
# Inputs dataclass — stable signature for the eventual DB writer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchiveInputs:
    """The argument shape ``archive_synthesis`` accepts. Frozen so a
    caller can't mutate it between validation and write."""

    target_question: str
    synthesis_timestamp: datetime
    status: SynthesisStatus
    implicit_recommendation: SynthesisRecommendation

    # Substantive role outputs (Decomposer → Synthesizer). Each is JSON-
    # serialized into its own column by the DB writer. ``Any`` rather
    # than typed Pydantic for now — the role-output schemas land in
    # Sprint 3-4 during the orchestrate.py extraction.
    decomposition: Any | None = None
    evidence: Any | None = None
    parameters: Any | None = None
    substrate: Any | None = None
    thesis: Any | None = None
    thesis_text: str | None = None

    # Trajectory + audit metadata.
    agent_trace: Any | None = None
    constraint_history: Any | None = None
    constraint_check_result: Any | None = None
    # Exact synthesize.delivered event whose immutable output is archived.
    source_synthesis_event_id: str | None = None

    # Model version stamp per role — feeds the typed payload's
    # model_versions field.
    model_versions: Mapping[str, str] = field(default_factory=dict)

    # Preserve raw retrieval identities so the archive can validate provenance
    # against durable graph relationships instead of trusting derived adjacency.
    chunk_ids: tuple[str, ...] = ()
    edge_ids: tuple[str, ...] = ()
    # Explicit overrides for the derived ids — used by tests and by
    # ingest paths that already know the full set without a DB join.
    document_ids: tuple[str, ...] = ()
    node_ids: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


def emit_synthesis_archived(
    *,
    investigation_id: str,
    synthesis_id: str,
    inputs: ArchiveInputs,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a SYNTHESIS_ARCHIVED event. Returns the event_id.

    Call this AFTER the syntheses row is committed (so we never
    advertise an archive that doesn't exist on disk). The current
    Researchmaxx code emits SUBSTRATE_MANIFEST_WRITTEN only; in Antiek
    we emit BOTH — the high-level archive event AND the manifest event
    — so consumers can filter by ``action_type = 'synthesis.archived'``
    without parsing payload."""
    thesis_text = inputs.thesis_text or ""
    return emit_typed(
        investigation_id,
        SynthesisArchivedPayload(
            target_question=inputs.target_question,
            synthesis_timestamp=inputs.synthesis_timestamp,
            status=inputs.status,
            implicit_recommendation=inputs.implicit_recommendation,
            model_versions=dict(inputs.model_versions),
            thesis_token_count=_estimate_token_count(thesis_text),
            has_constraint_check_result=inputs.constraint_check_result is not None,
        ),
        synthesis_id=synthesis_id,
        parent_event_id=parent_event_id,
        role="synthesizer",
    )


def emit_substrate_manifest_written(
    *,
    investigation_id: str,
    synthesis_id: str,
    synthesis_timestamp: datetime,
    counts_by_kind: Mapping[str, int],
    parent_event_id: str | None = None,
) -> str | None:
    """Emit SUBSTRATE_MANIFEST_WRITTEN. ``counts_by_kind`` is the
    input-cardinality breakdown from ``compute_manifest_counts``."""
    total = sum(counts_by_kind.values())
    return emit_typed(
        investigation_id,
        SubstrateManifestWrittenPayload(
            synthesis_timestamp=synthesis_timestamp,
            manifest_rows_written=total,
            counts_by_kind=dict(counts_by_kind),
        ),
        synthesis_id=synthesis_id,
        parent_event_id=parent_event_id,
        role="synthesizer",
    )


def _emit_synthesis_archived_authorized(
    authority: Any,
    synthesis_id: str,
    inputs: ArchiveInputs,
    *,
    parent_event_id: str | None = None,
) -> str:
    from substrate.event_log import emit_typed_authorized_strict

    return emit_typed_authorized_strict(
        authority,
        SynthesisArchivedPayload(
            target_question=inputs.target_question,
            synthesis_timestamp=inputs.synthesis_timestamp,
            status=inputs.status,
            implicit_recommendation=inputs.implicit_recommendation,
            model_versions=dict(inputs.model_versions),
            thesis_token_count=_estimate_token_count(inputs.thesis_text or ""),
            has_constraint_check_result=inputs.constraint_check_result is not None,
        ),
        synthesis_id=synthesis_id,
        parent_event_id=parent_event_id,
        role="synthesizer",
    )


def _emit_manifest_authorized(
    authority: Any,
    synthesis_id: str,
    inputs: ArchiveInputs,
    counts: Mapping[str, int],
    *,
    parent_event_id: str | None,
) -> str:
    from substrate.event_log import emit_typed_authorized_strict

    return emit_typed_authorized_strict(
        authority,
        SubstrateManifestWrittenPayload(
            synthesis_timestamp=inputs.synthesis_timestamp,
            manifest_rows_written=sum(counts.values()),
            counts_by_kind=dict(counts),
        ),
        synthesis_id=synthesis_id,
        parent_event_id=parent_event_id,
        role="synthesizer",
    )


def _stage_archive_events(
    con: Any,
    authority: Any,
    synthesis_id: str,
    inputs: ArchiveInputs,
    counts: Mapping[str, int],
) -> None:
    from substrate.event_log import prepare_typed_event, trajectory_authorized
    from substrate.synthesis_event_outbox import (
        stable_synthesis_event_id,
        stage_synthesis_event,
    )

    rows = trajectory_authorized(authority)
    archived = next(
        (
            row
            for row in rows
            if row.get("synthesis_id") == synthesis_id
            and row.get("action_type") == "synthesis.archived"
        ),
        None,
    )
    archive_event_id = (
        archived["event_id"]
        if archived is not None
        else stable_synthesis_event_id(authority, synthesis_id, "synthesis.archived")
    )
    if archived is None:
        archive_event = prepare_typed_event(
            authority.investigation_id,
            SynthesisArchivedPayload(
                target_question=inputs.target_question,
                synthesis_timestamp=inputs.synthesis_timestamp,
                status=inputs.status,
                implicit_recommendation=inputs.implicit_recommendation,
                model_versions=dict(inputs.model_versions),
                thesis_token_count=_estimate_token_count(inputs.thesis_text or ""),
                has_constraint_check_result=(inputs.constraint_check_result is not None),
            ),
            event_id=archive_event_id,
            parent_event_id=inputs.source_synthesis_event_id,
            synthesis_id=synthesis_id,
            role="synthesizer",
            # Keep both stamps in the same fractional ISO-8601 shape because
            # trajectory ordering is intentionally lexical for JSON rows.
            emitted_at=inputs.synthesis_timestamp + timedelta(microseconds=1),
        )
        stage_synthesis_event(con, authority, archive_event)
    manifest_exists = any(
        row.get("synthesis_id") == synthesis_id
        and row.get("action_type") == "synthesis.substrate_manifest.written"
        and row.get("parent_event_id") == archive_event_id
        for row in rows
    )
    if not manifest_exists:
        manifest_event = prepare_typed_event(
            authority.investigation_id,
            SubstrateManifestWrittenPayload(
                synthesis_timestamp=inputs.synthesis_timestamp,
                manifest_rows_written=sum(counts.values()),
                counts_by_kind=dict(counts),
            ),
            event_id=stable_synthesis_event_id(
                authority,
                synthesis_id,
                "synthesis.substrate_manifest.written",
            ),
            parent_event_id=archive_event_id,
            synthesis_id=synthesis_id,
            role="synthesizer",
            emitted_at=inputs.synthesis_timestamp + timedelta(microseconds=2),
        )
        stage_synthesis_event(con, authority, manifest_event)


def _reconcile_archive_events(con: Any, authority: Any) -> None:
    from substrate.synthesis_event_outbox import reconcile_synthesis_events

    reconcile_synthesis_events(con, authority)


def _ensure_archive_events(
    *,
    investigation_id: str,
    synthesis_id: str,
    inputs: ArchiveInputs,
    counts: Mapping[str, int],
    authority: Any | None = None,
) -> None:
    """Repair either append-only event when a committed archive is replayed."""
    if authority is None:
        rows = trajectory(investigation_id)
    else:
        from substrate.event_log import trajectory_authorized

        rows = trajectory_authorized(authority)
    archived = next(
        (
            row
            for row in rows
            if row.get("synthesis_id") == synthesis_id
            and row.get("action_type") == "synthesis.archived"
        ),
        None,
    )
    archive_event_id = archived.get("event_id") if archived is not None else None
    if archived is None:
        if authority is None:
            archive_event_id = emit_synthesis_archived(
                investigation_id=investigation_id,
                synthesis_id=synthesis_id,
                inputs=inputs,
            )
        else:
            archive_event_id = _emit_synthesis_archived_authorized(authority, synthesis_id, inputs)
    has_manifest_event = any(
        row.get("synthesis_id") == synthesis_id
        and row.get("action_type") == "synthesis.substrate_manifest.written"
        and row.get("parent_event_id") == archive_event_id
        for row in rows
    )
    if not has_manifest_event:
        if authority is None:
            emit_substrate_manifest_written(
                investigation_id=investigation_id,
                synthesis_id=synthesis_id,
                synthesis_timestamp=inputs.synthesis_timestamp,
                counts_by_kind=counts,
                parent_event_id=archive_event_id,
            )
        else:
            _emit_manifest_authorized(
                authority,
                synthesis_id,
                inputs,
                counts,
                parent_event_id=archive_event_id,
            )


def _estimate_token_count(text: str) -> int:
    """Cheap chars/4 heuristic — same convention as
    ``substrate.context_pack.DefaultTokenCounter``. For billing-accurate
    counts the caller can pass the real model tokenizer's result by
    constructing the payload directly."""
    if not text:
        return 0
    return max(1, (len(text) + 3) // 4)


# ---------------------------------------------------------------------------
# DB writer (Sprint 10 day 4-5)
# ---------------------------------------------------------------------------


def _authorized_document_ids(con: Any, authority: Any, ids: Iterable[str]) -> set[str]:
    requested = tuple(dict.fromkeys(ids))
    from substrate.legal_gate.read import archive_document_ids_compatibility

    return archive_document_ids_compatibility(
        con,
        requested,
        authority=authority,
        enforce=True,
    )


def _authorized_chunk_ids(con: Any, authority: Any, ids: Iterable[str]) -> set[str]:
    requested = tuple(dict.fromkeys(ids))
    from substrate.legal_gate.read import archive_chunk_ids_compatibility

    return archive_chunk_ids_compatibility(
        con,
        requested,
        authority=authority,
        enforce=True,
    )


def _authorized_edge_ids(con: Any, authority: Any, ids: Iterable[str]) -> set[str]:
    requested = tuple(dict.fromkeys(ids))
    if not requested:
        return set()
    placeholders = ",".join("?" for _ in requested)
    rows = con.execute(
        "SELECT edge_id, account_digest, investigation_digest, "
        "source_document_id, chunk_id FROM edges WHERE edge_id IN (" + placeholders + ")",
        list(requested),
    ).fetchall()
    admitted: set[str] = set()
    public_candidates: list[tuple[str, str | None, str | None]] = []
    for edge_id, account_digest, investigation_digest, document_id, chunk_id in rows:
        if (
            account_digest == authority.account_digest
            and investigation_digest == authority.investigation_digest
        ):
            admitted.add(edge_id)
        elif account_digest is None and investigation_digest is None:
            public_candidates.append((edge_id, document_id, chunk_id))
    public_documents = _authorized_document_ids(
        con,
        authority,
        (row[1] for row in public_candidates if row[1] is not None),
    )
    public_chunks = _authorized_chunk_ids(
        con,
        authority,
        (row[2] for row in public_candidates if row[2] is not None),
    )
    admitted.update(
        edge_id
        for edge_id, document_id, chunk_id in public_candidates
        if document_id in public_documents or chunk_id in public_chunks
    )
    return admitted


def _authorized_node_ids(con: Any, authority: Any, ids: Iterable[str]) -> set[str]:
    requested = tuple(dict.fromkeys(ids))
    if not requested:
        return set()
    placeholders = ",".join("?" for _ in requested)
    member_rows = con.execute(
        "SELECT n.node_id FROM nodes n JOIN investigation_node_memberships m "
        "ON m.node_id = n.node_id WHERE n.node_id IN ("
        + placeholders
        + ") AND m.account_digest = ? AND m.investigation_digest = ?",
        [
            *requested,
            authority.account_digest,
            authority.investigation_digest,
        ],
    ).fetchall()
    admitted = {row[0] for row in member_rows}
    candidates = sorted(set(requested) - admitted)
    if not candidates:
        return admitted
    from substrate.legal_gate.read import archive_node_provenance_compatibility

    documents_by_node = archive_node_provenance_compatibility(
        con,
        tuple(candidates),
        authority=authority,
        enforce=True,
    )
    admitted_documents = _authorized_document_ids(
        con,
        authority,
        (
            document_id
            for document_ids in documents_by_node.values()
            for document_id in document_ids
        ),
    )
    admitted.update(
        node_id
        for node_id, document_ids in documents_by_node.items()
        if document_ids and document_ids <= admitted_documents
    )
    return admitted


def archive_synthesis_via_db(
    con: Any,
    inputs: ArchiveInputs,
    *,
    investigation_id: str,
    synthesis_id: str | None = None,
    _authority: Any | None = None,
) -> str:
    """Write a syntheses row + its substrate manifest, then emit
    ``SYNTHESIS_ARCHIVED`` and ``SUBSTRATE_MANIFEST_WRITTEN``.

    Architecture_notes §4: this is the SOLE writer to the syntheses
    table. Pass a ``runtime.db_lock.LockedConnection`` — the
    only-writer invariant requires every DDL+DML pass through the
    same coordinator.

    The DB writes happen inside a transaction so a manifest failure
    rolls back the syntheses row. Events fire AFTER commit so we
    never advertise an archive that doesn't exist on disk. An exact replay of
    an existing immutable synthesis is a no-op and emits no duplicate events;
    changed content must use a new synthesis id."""
    try:
        from ..runtime.db_lock import LockedConnection  # type: ignore[import-not-found]
    except ImportError:
        from runtime.db_lock import LockedConnection  # type: ignore[no-redef]
    if not isinstance(con, LockedConnection):
        raise TypeError(
            "archive_synthesis_via_db requires a LockedConnection "
            "(architecture_notes §4 only-writer invariant). Use "
            "runtime.db_lock.connect_write(db_path)."
        )

    if _authority is not None:
        from substrate.graph.tenancy import initialize_graph_authority
        from substrate.investigation_streams import resolve_investigation_stream
        from substrate.investigation_tenancy import InvestigationAuthority

        if not isinstance(_authority, InvestigationAuthority):
            raise TypeError("authorized synthesis archive requires InvestigationAuthority")
        if investigation_id != _authority.investigation_id:
            raise ValueError("authorized synthesis archive crosses investigation")
        resolve_investigation_stream(_authority)
        from substrate.event_log import require_event_persistence

        require_event_persistence()
        initialize_graph_authority(con, _authority)
    sid = synthesis_id or new_synthesis_id()
    con.execute(_ARCHIVE_REQUESTS_SQL)
    request_fingerprint = _manifest_request_fingerprint(inputs)
    json_values = [
        serialize_json_field(dict(inputs.model_versions)),
        serialize_json_field(inputs.decomposition),
        serialize_json_field(inputs.evidence),
        serialize_json_field(inputs.parameters),
        serialize_json_field(inputs.substrate),
        serialize_json_field(inputs.thesis),
        serialize_json_field(inputs.agent_trace),
        serialize_json_field(inputs.constraint_history),
        serialize_json_field(inputs.constraint_check_result),
    ]
    material_values = [
        investigation_id,
        inputs.target_question,
        inputs.status,
        inputs.implicit_recommendation,
        inputs.thesis_text,
        _estimate_token_count(inputs.thesis_text or ""),
        inputs.constraint_check_result is not None,
        *json_values,
    ]
    stored = con.execute(
        "SELECT investigation_id, target_question, status, "
        "implicit_recommendation, thesis_text, thesis_token_count, "
        "has_constraint_check_result, model_versions, decomposition, evidence, "
        "parameters, substrate, thesis, agent_trace, constraint_history, "
        "constraint_check_result, synthesis_timestamp, account_digest, "
        "investigation_digest "
        "FROM syntheses WHERE synthesis_id = ?",
        [sid],
    ).fetchone()
    if stored is not None and not _same_archive_material(stored[:16], material_values):
        raise SynthesisArchiveConflict(f"synthesis_id {sid!r} already identifies different content")
    if stored is not None:
        expected_authority = (
            (None, None)
            if _authority is None
            else (_authority.account_digest, _authority.investigation_digest)
        )
        if tuple(stored[17:19]) != expected_authority:
            raise SynthesisArchiveConflict(
                f"synthesis_id {sid!r} belongs to different graph authority"
            )
    # Exclude missing identities so immutable counts and telemetry cannot claim
    # provenance that was never durably present.
    real_document_ids: set[str] = set()
    if inputs.document_ids:
        from substrate.legal_gate.read import archive_document_ids_compatibility

        real_document_ids = archive_document_ids_compatibility(
            con,
            tuple(inputs.document_ids),
            authority=_authority,
            enforce=(
                _authority is not None or os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1"
            ),
        )
    real_chunk_ids: set[str] = set()
    if inputs.chunk_ids:
        from substrate.legal_gate.read import archive_chunk_ids_compatibility

        real_chunk_ids = archive_chunk_ids_compatibility(
            con,
            tuple(inputs.chunk_ids),
            authority=_authority,
            enforce=(
                _authority is not None or os.environ.get("ANTIEK_LEGAL_READ_ENFORCEMENT") == "1"
            ),
        )
    real_edge_ids: set[str] = set()
    if inputs.edge_ids:
        ph = ",".join("?" for _ in inputs.edge_ids)
        rows = con.execute(
            f"SELECT edge_id FROM edges WHERE edge_id IN ({ph})",
            list(inputs.edge_ids),
        ).fetchall()
        real_edge_ids = {r[0] for r in rows}
        if _authority is not None:
            real_edge_ids = _authorized_edge_ids(con, _authority, real_edge_ids)

    if isinstance(inputs.substrate, dict) and inputs.substrate.get("schema_version") == 3:
        from substrate.source_coverage import (
            ArchivedSourceCoverageEnvelope,
            validate_archived_claim_support,
        )

        validate_archived_claim_support(
            ArchivedSourceCoverageEnvelope.model_validate(inputs.substrate),
            inputs.thesis,
            manifest_chunk_ids=real_chunk_ids,
        )

    real_explicit_node_ids: set[str] = set()
    if inputs.node_ids:
        ph = ",".join("?" for _ in inputs.node_ids)
        rows = con.execute(
            f"SELECT node_id FROM nodes WHERE node_id IN ({ph})",
            list(inputs.node_ids),
        ).fetchall()
        real_explicit_node_ids = {r[0] for r in rows}
        if _authority is not None:
            real_explicit_node_ids = _authorized_node_ids(con, _authority, real_explicit_node_ids)

    # Resolve adjacency from stored relationships so callers cannot fabricate a
    # node's participation by supplying an unrelated chunk or edge identifier.
    effective_node_ids = set(real_explicit_node_ids)
    if real_chunk_ids:
        ph = ",".join("?" for _ in real_chunk_ids)
        node_rows = con.execute(
            "SELECT node_id FROM nodes "
            "WHERE json_extract_string(try_cast(metadata AS JSON), '$.chunk_id') "
            f"IN ({ph})",
            sorted(real_chunk_ids),
        ).fetchall()
        effective_node_ids.update(r[0] for r in node_rows)
        edge_rows = con.execute(
            f"SELECT source_node_id, target_node_id FROM edges WHERE chunk_id IN ({ph})",
            sorted(real_chunk_ids),
        ).fetchall()
        effective_node_ids.update(node_id for row in edge_rows for node_id in row if node_id)
    if real_edge_ids:
        ph = ",".join("?" for _ in real_edge_ids)
        edge_rows = con.execute(
            f"SELECT source_node_id, target_node_id FROM edges WHERE edge_id IN ({ph})",
            sorted(real_edge_ids),
        ).fetchall()
        effective_node_ids.update(node_id for row in edge_rows for node_id in row if node_id)
    if _authority is not None:
        effective_node_ids = _authorized_node_ids(con, _authority, effective_node_ids)

    manifest_groups = (
        ("document", sorted(real_document_ids)),
        ("chunk", sorted(real_chunk_ids)),
        ("node", sorted(effective_node_ids)),
        ("edge", sorted(real_edge_ids)),
    )
    counts = compute_manifest_counts(
        document_ids=real_document_ids,
        chunk_ids=real_chunk_ids,
        node_ids=effective_node_ids,
        edge_ids=real_edge_ids,
    )

    desired_manifest = {(kind, entity_id) for kind, ids in manifest_groups for entity_id in ids}
    if stored is not None:
        current_manifest = {
            (kind, entity_id)
            for kind, entity_id in con.execute(
                "SELECT entity_kind, entity_id FROM synthesis_substrate_manifest "
                "WHERE synthesis_id = ?",
                [sid],
            ).fetchall()
        }
        if current_manifest != desired_manifest:
            raise SynthesisArchiveConflict(
                f"synthesis_id {sid!r} already identifies a different manifest"
            )
        stored_request = con.execute(
            "SELECT manifest_request_fingerprint FROM synthesis_archive_requests "
            "WHERE synthesis_id = ?",
            [sid],
        ).fetchone()
        if stored_request is None:
            con.execute(
                "INSERT INTO synthesis_archive_requests "
                "(synthesis_id, manifest_request_fingerprint) VALUES (?, ?)",
                [sid, request_fingerprint],
            )
        elif stored_request[0] != request_fingerprint:
            raise SynthesisArchiveConflict(
                f"synthesis_id {sid!r} already identifies a different manifest request"
            )
        stored_timestamp = stored[16]
        replay_inputs = replace(
            inputs,
            synthesis_timestamp=stored_timestamp.replace(tzinfo=UTC),
        )
        if _authority is None:
            _ensure_archive_events(
                investigation_id=investigation_id,
                synthesis_id=sid,
                inputs=replay_inputs,
                counts=counts,
            )
        else:
            _stage_archive_events(con, _authority, sid, replay_inputs, counts)
            _reconcile_archive_events(con, _authority)
        return sid

    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO syntheses ("
            " synthesis_id, investigation_id, target_question, "
            " synthesis_timestamp, status, implicit_recommendation,"
            " thesis_text, thesis_token_count, has_constraint_check_result,"
            " model_versions, decomposition, evidence, parameters,"
            " substrate, thesis, agent_trace, constraint_history,"
            " constraint_check_result"
            ", account_digest, investigation_digest"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                sid,
                investigation_id,
                inputs.target_question,
                _to_naive_utc(inputs.synthesis_timestamp),
                inputs.status,
                inputs.implicit_recommendation,
                inputs.thesis_text,
                _estimate_token_count(inputs.thesis_text or ""),
                inputs.constraint_check_result is not None,
                *json_values,
                _authority.account_digest if _authority is not None else None,
                _authority.investigation_digest if _authority is not None else None,
            ],
        )
        con.execute(
            "INSERT INTO synthesis_archive_requests "
            "(synthesis_id, manifest_request_fingerprint) VALUES (?, ?)",
            [sid, request_fingerprint],
        )
        for kind, ids in manifest_groups:
            for eid in ids:
                con.execute(
                    "INSERT OR IGNORE INTO synthesis_substrate_manifest "
                    "(synthesis_id, entity_kind, entity_id) VALUES (?, ?, ?)",
                    [sid, kind, eid],
                )
        if _authority is not None:
            _stage_archive_events(con, _authority, sid, inputs, counts)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    if _authority is None:
        _ensure_archive_events(
            investigation_id=investigation_id,
            synthesis_id=sid,
            inputs=inputs,
            counts=counts,
        )
    else:
        _reconcile_archive_events(con, _authority)
    return sid


def archive_synthesis_authorized(
    con: Any,
    authority: Any,
    inputs: ArchiveInputs,
    *,
    logical_key: str = "terminal",
) -> str:
    """Archive one private synthesis without accepting scalar ownership."""
    sid = authorized_synthesis_id(authority, logical_key)
    return archive_synthesis_via_db(
        con,
        inputs,
        investigation_id=authority.investigation_id,
        synthesis_id=sid,
        _authority=authority,
    )


# ---------------------------------------------------------------------------
# DB reader
# ---------------------------------------------------------------------------


def load_synthesis(
    con: Any,
    synthesis_id: str,
    *,
    _authority: Any | None = None,
) -> ArchivedSynthesisRow | None:
    """Read one syntheses row. Returns the full hydrated record (or
    ``None`` when the id is unknown). ``con`` may be a read-only
    duckdb connection or a ``LockedConnection`` — reads don't need
    the write lock."""
    where = "synthesis_id = ?"
    params: list[Any] = [synthesis_id]
    if _authority is not None:
        from substrate.graph.tenancy import assert_graph_authority_read
        from substrate.investigation_tenancy import InvestigationAuthority

        if not isinstance(_authority, InvestigationAuthority):
            raise TypeError("authorized synthesis load requires InvestigationAuthority")
        assert_graph_authority_read(con, _authority)
        where += " AND account_digest = ? AND investigation_digest = ?"
        params.extend([_authority.account_digest, _authority.investigation_digest])
    row = con.execute(
        "SELECT synthesis_id, synthesis_timestamp, target_question, "
        "status, implicit_recommendation, thesis_text, "
        "model_versions, decomposition, evidence, parameters, "
        "substrate, thesis, agent_trace, constraint_history, "
        "constraint_check_result, investigation_id, account_digest, "
        "investigation_digest "
        "FROM syntheses WHERE " + where,
        params,
    ).fetchone()
    if row is None:
        return None
    manifest_rows = con.execute(
        "SELECT entity_kind, entity_id FROM synthesis_substrate_manifest WHERE synthesis_id = ?",
        [synthesis_id],
    ).fetchall()
    manifest: dict[str, list[str]] = {k: [] for k in MANIFEST_ENTITY_KINDS}
    for kind, eid in manifest_rows:
        manifest.setdefault(kind, []).append(eid)
    counts = {k: len(v) for k, v in manifest.items()}

    def _maybe_json(raw: str | None) -> Any:
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    return ArchivedSynthesisRow(
        synthesis_id=row[0],
        synthesis_timestamp=(row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])),
        target_question=row[2],
        status=row[3],
        implicit_recommendation=row[4],
        thesis_text=row[5],
        model_versions=_maybe_json(row[6]) or {},
        decomposition=_maybe_json(row[7]),
        evidence=_maybe_json(row[8]),
        parameters=_maybe_json(row[9]),
        substrate=_maybe_json(row[10]),
        thesis=_maybe_json(row[11]),
        agent_trace=_maybe_json(row[12]),
        constraint_history=_maybe_json(row[13]),
        constraint_check_result=_maybe_json(row[14]),
        investigation_id=row[15],
        substrate_manifest=manifest,
        substrate_manifest_counts=counts,
    )


def load_synthesis_authorized(
    con: Any,
    authority: Any,
    synthesis_id: str,
) -> ArchivedSynthesisRow | None:
    """Load children only after the exact parent authority predicate succeeds."""
    return load_synthesis(con, synthesis_id, _authority=authority)


@dataclass(frozen=True)
class ArchivedSynthesisRow:
    """What ``load_synthesis`` returns. Superset of
    ``ArchivedSynthesis`` (backtest input shape) — carries the full
    role outputs too so other consumers (cohort analytics, the
    weekly report dashboard) can read without re-querying."""

    synthesis_id: str
    synthesis_timestamp: str
    target_question: str
    status: str
    implicit_recommendation: str | None
    thesis_text: str | None
    model_versions: dict[str, str]
    decomposition: Any
    evidence: Any
    parameters: Any
    substrate: Any
    thesis: Any
    agent_trace: Any
    constraint_history: Any
    constraint_check_result: Any
    investigation_id: str | None
    substrate_manifest: dict[str, list[str]] = field(default_factory=dict)
    substrate_manifest_counts: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# SPR-DRL-19 — batch source-coverage qualification resolver
# ---------------------------------------------------------------------------


def resolve_source_coverage_qualifications(
    con: Any,
    authority: Any,
    source_investigation_ids: frozenset[str],
) -> dict[str, Any | None]:
    """Batch-resolve archive rows for unique source investigations.

    Derives deterministic terminal synthesis IDs for each source investigation
    under the given account/root authority, then reads all matching syntheses
    rows in ONE bounded SQL statement. Returns each raw substrate envelope, or
    ``None`` when no terminal archive or coverage envelope exists.

    One query, stable deduplication, exact account + investigation predicates,
    bounded inputs, no manifest reads, no scalar unscoped compatibility reader.
    """
    from substrate.investigation_tenancy import InvestigationAuthority

    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("resolve_source_coverage_qualifications requires InvestigationAuthority")
    if not source_investigation_ids:
        return {}
    if len(source_investigation_ids) > 100:
        raise ValueError("source coverage qualification batch exceeds 100 investigations")

    # Derive deterministic terminal synthesis IDs for each unique source
    # investigation under the exact account/root. Each source investigation
    # gets its own InvestigationAuthority so the graph key (and thus synthesis
    # ID) is scoped to that investigation — Alice's inv-X and Bob's inv-X
    # produce different synthesis IDs because their graph keys differ.
    synthesis_id_to_source: dict[str, tuple[str, str]] = {}
    for src_inv_id in sorted(source_investigation_ids):
        source_auth = InvestigationAuthority(authority.account_id, src_inv_id, authority.root)
        sid = authorized_synthesis_id(source_auth, "terminal")
        synthesis_id_to_source[sid] = (
            src_inv_id,
            source_auth.investigation_digest,
        )

    if not synthesis_id_to_source:
        return {}

    # ONE bounded SQL statement — fetch only the columns we need.
    predicates: list[str] = []
    params: list[Any] = []
    for synthesis_id, (_source_id, investigation_digest) in synthesis_id_to_source.items():
        predicates.append("(synthesis_id = ? AND account_digest = ? AND investigation_digest = ?)")
        params.extend([synthesis_id, authority.account_digest, investigation_digest])
    query = (
        "SELECT synthesis_id, substrate, investigation_id, investigation_digest "
        "FROM syntheses WHERE " + " OR ".join(predicates)
    )
    rows = con.execute(query, params).fetchall()

    def _maybe_json(raw: str | None) -> Any:
        if raw is None:
            return None
        if not isinstance(raw, str):
            return raw
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("source coverage archive contains invalid JSON") from exc

    loaded: dict[str, Any | None] = {src_id: None for src_id in source_investigation_ids}
    for synthesis_id, substrate_raw, inv_id, inv_digest in rows:
        expected = synthesis_id_to_source.get(synthesis_id)
        if expected is None:
            continue
        source_inv_id, expected_digest = expected
        if inv_id != source_inv_id or inv_digest != expected_digest:
            raise ValueError("source coverage archive authority mismatch")
        loaded[source_inv_id] = _maybe_json(substrate_raw)
    return loaded
