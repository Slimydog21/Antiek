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
from datetime import UTC, datetime
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


def _ensure_archive_events(
    *,
    investigation_id: str,
    synthesis_id: str,
    inputs: ArchiveInputs,
    counts: Mapping[str, int],
) -> None:
    """Repair either append-only event when a committed archive is replayed."""
    rows = trajectory(investigation_id)
    archived = next(
        (
            row for row in rows
            if row.get("synthesis_id") == synthesis_id
            and row.get("action_type") == "synthesis.archived"
        ),
        None,
    )
    archive_event_id = archived.get("event_id") if archived is not None else None
    if archived is None:
        archive_event_id = emit_synthesis_archived(
            investigation_id=investigation_id,
            synthesis_id=synthesis_id,
            inputs=inputs,
        )
    has_manifest_event = any(
        row.get("synthesis_id") == synthesis_id
        and row.get("action_type") == "synthesis.substrate_manifest.written"
        and row.get("parent_event_id") == archive_event_id
        for row in rows
    )
    if not has_manifest_event:
        emit_substrate_manifest_written(
            investigation_id=investigation_id,
            synthesis_id=synthesis_id,
            synthesis_timestamp=inputs.synthesis_timestamp,
            counts_by_kind=counts,
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


def archive_synthesis_via_db(
    con: Any,
    inputs: ArchiveInputs,
    *,
    investigation_id: str,
    synthesis_id: str | None = None,
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
        "constraint_check_result, synthesis_timestamp "
        "FROM syntheses WHERE synthesis_id = ?",
        [sid],
    ).fetchone()
    if stored is not None and not _same_archive_material(stored[:-1], material_values):
        raise SynthesisArchiveConflict(
            f"synthesis_id {sid!r} already identifies different content"
        )
    stored_request = con.execute(
        "SELECT manifest_request_fingerprint FROM synthesis_archive_requests "
        "WHERE synthesis_id = ?",
        [sid],
    ).fetchone()
    if stored is not None and stored_request is not None:
        if stored_request[0] != request_fingerprint:
            raise SynthesisArchiveConflict(
                f"synthesis_id {sid!r} already identifies a different manifest request"
            )
        manifest_rows = con.execute(
            "SELECT entity_kind, entity_id FROM synthesis_substrate_manifest "
            "WHERE synthesis_id = ?",
            [sid],
        ).fetchall()
        counts = {
            kind: sum(1 for row_kind, _ in manifest_rows if row_kind == kind)
            for kind in MANIFEST_ENTITY_KINDS
        }
        replay_inputs = replace(
            inputs,
            synthesis_timestamp=stored[-1].replace(tzinfo=UTC),
        )
        _ensure_archive_events(
            investigation_id=investigation_id,
            synthesis_id=sid,
            inputs=replay_inputs,
            counts=counts,
        )
        return sid

    # Exclude missing identities so immutable counts and telemetry cannot claim
    # provenance that was never durably present.
    real_document_ids: set[str] = set()
    if inputs.document_ids:
        ph = ",".join("?" for _ in inputs.document_ids)
        rows = con.execute(
            f"SELECT document_id FROM documents WHERE document_id IN ({ph})",
            list(inputs.document_ids),
        ).fetchall()
        real_document_ids = {r[0] for r in rows}
    real_chunk_ids: set[str] = set()
    if inputs.chunk_ids:
        ph = ",".join("?" for _ in inputs.chunk_ids)
        rows = con.execute(
            f"SELECT chunk_id FROM chunks WHERE chunk_id IN ({ph})",
            list(inputs.chunk_ids),
        ).fetchall()
        real_chunk_ids = {r[0] for r in rows}
    real_edge_ids: set[str] = set()
    if inputs.edge_ids:
        ph = ",".join("?" for _ in inputs.edge_ids)
        rows = con.execute(
            f"SELECT edge_id FROM edges WHERE edge_id IN ({ph})",
            list(inputs.edge_ids),
        ).fetchall()
        real_edge_ids = {r[0] for r in rows}

    real_explicit_node_ids: set[str] = set()
    if inputs.node_ids:
        ph = ",".join("?" for _ in inputs.node_ids)
        rows = con.execute(
            f"SELECT node_id FROM nodes WHERE node_id IN ({ph})",
            list(inputs.node_ids),
        ).fetchall()
        real_explicit_node_ids = {r[0] for r in rows}

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
            "SELECT source_node_id, target_node_id FROM edges "
            f"WHERE chunk_id IN ({ph})",
            sorted(real_chunk_ids),
        ).fetchall()
        effective_node_ids.update(
            node_id for row in edge_rows for node_id in row if node_id
        )
    if real_edge_ids:
        ph = ",".join("?" for _ in real_edge_ids)
        edge_rows = con.execute(
            "SELECT source_node_id, target_node_id FROM edges "
            f"WHERE edge_id IN ({ph})",
            sorted(real_edge_ids),
        ).fetchall()
        effective_node_ids.update(
            node_id for row in edge_rows for node_id in row if node_id
        )

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

    desired_manifest = {
        (kind, entity_id) for kind, ids in manifest_groups for entity_id in ids
    }
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
        con.execute(
            "INSERT INTO synthesis_archive_requests "
            "(synthesis_id, manifest_request_fingerprint) VALUES (?, ?)",
            [sid, request_fingerprint],
        )
        stored_timestamp = stored[-1]
        replay_inputs = replace(
            inputs,
            synthesis_timestamp=stored_timestamp.replace(tzinfo=UTC),
        )
        _ensure_archive_events(
            investigation_id=investigation_id,
            synthesis_id=sid,
            inputs=replay_inputs,
            counts=counts,
        )
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
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise

    _ensure_archive_events(
        investigation_id=investigation_id,
        synthesis_id=sid,
        inputs=inputs,
        counts=counts,
    )
    return sid


# ---------------------------------------------------------------------------
# DB reader
# ---------------------------------------------------------------------------


def load_synthesis(
    con: Any, synthesis_id: str,
) -> ArchivedSynthesisRow | None:
    """Read one syntheses row. Returns the full hydrated record (or
    ``None`` when the id is unknown). ``con`` may be a read-only
    duckdb connection or a ``LockedConnection`` — reads don't need
    the write lock."""
    row = con.execute(
        "SELECT synthesis_id, synthesis_timestamp, target_question, "
        "status, implicit_recommendation, thesis_text, "
        "model_versions, decomposition, evidence, parameters, "
        "substrate, thesis, agent_trace, constraint_history, "
        "constraint_check_result, investigation_id "
        "FROM syntheses WHERE synthesis_id = ?",
        [synthesis_id],
    ).fetchone()
    if row is None:
        return None
    manifest_rows = con.execute(
        "SELECT entity_kind, entity_id FROM synthesis_substrate_manifest "
        "WHERE synthesis_id = ?",
        [synthesis_id],
    ).fetchall()
    manifest: dict[str, list[str]] = {
        k: [] for k in MANIFEST_ENTITY_KINDS
    }
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
        synthesis_timestamp=(
            row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1])
        ),
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
