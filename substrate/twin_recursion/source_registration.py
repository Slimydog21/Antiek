"""Canonical graph-document declarations for recursive twin obligations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from runtime.db_lock import LockedConnection
from substrate.books.servability import is_servable_full_text, servability_of
from substrate.constants import (
    PERSONAL_READABLE_CONTENT_CLASSES,
    PERSONAL_READING_CONTENT_CLASS,
    SERVABLE_CONTENT_CLASSES,
)
from substrate.books.serve_guard import (
    LinkBackMissingError,
    _rights_context_from_metadata,
    serve_full_text_guarded,
)
from substrate.rights import T3BodyServeError, body_servable
from substrate.twin_note_taker import MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, AssetContent

from .ledger import SourceRevision, TwinRecursionLedger

ENVELOPE_SCHEMA = "antiek.twin-source-envelope.v1"
EnvelopeStatus = Literal[
    "eligible", "metadata_only", "requires_binding", "requires_enrichment",
    "requires_segmentation",
]
CoverageVerdict = Literal["unknown", "partial", "universal"]


class TwinSourceEnvelopeError(RuntimeError):
    """A graph document cannot be reconciled with its twin declaration."""


@dataclass(frozen=True)
class TwinSourceEnvelope:
    schema: str
    status: EnvelopeStatus
    account_id: str
    document_id: str
    title: str
    document_type: str
    body_sha256: str | None
    source_event_id: str
    source_hash: str | None
    reason: str | None

    def to_json(self) -> str:
        return _canonical_json(asdict(self))

    @classmethod
    def from_json(cls, value: str) -> TwinSourceEnvelope:
        try:
            raw = json.loads(value)
            envelope = cls(**raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise TwinSourceEnvelopeError("twin source envelope is malformed") from exc
        if envelope.to_json() != value:
            raise TwinSourceEnvelopeError("twin source envelope is not canonical")
        if envelope.schema != ENVELOPE_SCHEMA or envelope.status not in {
            "eligible", "metadata_only", "requires_binding", "requires_enrichment",
            "requires_segmentation",
        }:
            raise TwinSourceEnvelopeError("twin source envelope has unsupported semantics")
        if (envelope.status == "eligible") != (envelope.source_hash is not None):
            raise TwinSourceEnvelopeError("twin source envelope eligibility is inconsistent")
        return envelope


@dataclass(frozen=True)
class TwinSourceCoverage:
    account_id: str
    documents: int
    eligible: int
    metadata_only: int
    requires_binding: int
    requires_enrichment: int
    requires_segmentation: int
    registered: int
    verdict: CoverageVerdict


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_twin_source_envelope(
    *,
    document_id: str,
    title: str | None,
    raw_text: str | None,
    document_type: str,
    owner_user_id: str,
) -> TwinSourceEnvelope:
    """Derive the complete declaration from fields in one canonical document row."""
    exact_title = title or document_id
    body_sha = None if raw_text is None else _sha(raw_text)
    stripped_length = 0 if raw_text is None else len(raw_text.strip())
    event_material = _canonical_json(
        [ENVELOPE_SCHEMA, owner_user_id, document_id, exact_title, document_type, body_sha]
    )
    source_event_id = "evt-twin-source-" + _sha(event_material)[:40]
    if raw_text is None or stripped_length == 0:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA, "metadata_only", owner_user_id, document_id, exact_title,
            document_type, body_sha, source_event_id, None, "no_substantive_body",
        )
    if document_type == "multimedia_twin":
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA, "requires_binding", owner_user_id, document_id, exact_title,
            document_type, body_sha, source_event_id, None,
            "legacy_twin_requires_canonical_binding",
        )
    if stripped_length < MIN_CONTENT_CHARS:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA, "requires_enrichment", owner_user_id, document_id, exact_title,
            document_type, body_sha, source_event_id, None,
            "body_below_materializer_floor",
        )
    if len(raw_text) > MAX_CONTENT_CHARS:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA, "requires_segmentation", owner_user_id, document_id,
            exact_title, document_type, body_sha, source_event_id, None,
            "body_exceeds_materializer_limit",
        )
    asset = _asset(document_id, exact_title, raw_text, document_type, source_event_id)
    revision = SourceRevision(owner_user_id, asset)
    return TwinSourceEnvelope(
        ENVELOPE_SCHEMA, "eligible", owner_user_id, document_id, exact_title,
        document_type, body_sha, source_event_id, revision.source_hash, None,
    )


def _asset(document_id: str, title: str, raw_text: str, document_type: str,
           source_event_id: str) -> AssetContent:
    return AssetContent(
        asset_id=document_id,
        title=title,
        content_text=raw_text,
        content_class=document_type,
        source_event_ids=(source_event_id,),
    )


def _row_envelope(
    con: LockedConnection, row: tuple[Any, ...]
) -> tuple[TwinSourceEnvelope, str | None]:
    """Derive the twin declaration from a document row's current bytes.

    The served body is resolved through the same serve gate the twin
    projection consumes (``serve_full_text_guarded(owner=True)``). A body the
    serve gate REFUSES (taken-down, gated, or a rights-drift / link-back
    denial) is not an error for the DECLARATION: the envelope falls back to
    ``metadata_only`` with ``raw_text=None`` so the row stays verifiable
    (``verify_twin_source_envelopes`` recomputes through the same helper and
    only requires a body for ``eligible`` envelopes).
    """
    try:
        served = serve_full_text_guarded(con, str(row[0]), owner=True)
        raw_text = served.full_text
    except (T3BodyServeError, LinkBackMissingError):
        # Serve gate refuses this body (rights drift / missing link-back).
        # The declaration survives as metadata-only; the serve path still
        # refuses loudly — this is the envelope, not a serve.
        raw_text = None
    return _envelope_from_served(row, raw_text)


def _envelope_from_served(
    row: tuple[Any, ...], raw_text: str | None
) -> tuple[TwinSourceEnvelope, str | None]:
    envelope = build_twin_source_envelope(
        document_id=str(row[0]),
        title=None if row[1] is None else str(row[1]),
        raw_text=raw_text,
        document_type=str(row[2]),
        owner_user_id=str(row[3]),
    )
    return envelope, raw_text


def stamp_existing_document(
    con: LockedConnection, document_id: str, *, refresh: bool = False
) -> None:
    """Fill one legacy NULL declaration; reject drift unless refresh is explicit."""
    _require_locked(con)
    row = con.execute(
        "SELECT document_id,title,document_type,owner_user_id,twin_source_envelope "
        "FROM documents WHERE document_id=?",
        [document_id],
    ).fetchone()
    if row is None:
        raise KeyError(document_id)
    expected = _row_envelope(con, tuple(row[:4]))[0].to_json()
    if row[4] is not None and row[4] != expected and not refresh:
        raise TwinSourceEnvelopeError(
            f"document {document_id!r} twin declaration conflicts with stored bytes"
        )
    if row[4] != expected:
        con.execute(
            "UPDATE documents SET twin_source_envelope=? "
            "WHERE document_id=?",
            [expected, document_id],
        )


# Envelope backfill batch size. Committed per batch so a killed deploy (e.g.
# systemd TimeoutStartSec) never loses a whole corpus pass and never holds the
# DuckDB write transaction for the full backfill. 500 rows keeps a batch's
# UPDATE well under a second even on a multi-hundred-MB store.
_BACKFILL_BATCH_SIZE = 500


def backfill_twin_source_envelopes(con: LockedConnection) -> int:
    """Backfill all legacy rows under one caller-held graph write lock.

    Fast path: the serve fields (content_class, raw_text, metadata, taken_down)
    are preloaded in ONE query and the serve decision is replicated in pure
    Python via the same serve.py predicates, so the pass is O(n) queries total
    instead of ~3 queries per row (the previous implementation took ~50 minutes
    at ~26.5k documents on prod and held one write transaction the whole time).

    Updates commit in bounded batches; a crash mid-pass resumes on the next
    run because already-stamped rows are skipped (``IS NULL``).
    """
    _require_locked(con)
    rows = con.execute(
        """
        SELECT d.document_id, d.title, d.document_type, d.owner_user_id,
               d.raw_text, d.content_class, d.metadata,
               COALESCE(b.taken_down, FALSE) AS taken_down
        FROM documents d
        LEFT JOIN book_assets b ON d.document_id = b.document_id
        WHERE d.twin_source_envelope IS NULL
        ORDER BY d.document_id
        """
    ).fetchall()
    if not rows:
        return 0

    stamped = 0
    for start in range(0, len(rows), _BACKFILL_BATCH_SIZE):
        batch = rows[start : start + _BACKFILL_BATCH_SIZE]
        con.execute("BEGIN")
        try:
            for row in batch:
                envelope, _body = _envelope_from_served_fields(row)
                con.execute(
                    "UPDATE documents SET twin_source_envelope=? "
                    "WHERE document_id=? AND twin_source_envelope IS NULL",
                    [envelope.to_json(), str(row[0])],
                )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        stamped += len(batch)
    return stamped


def _envelope_from_served_fields(
    row: tuple[Any, ...],
) -> tuple[TwinSourceEnvelope, str | None]:
    """Replicate ``serve_full_text_guarded(owner=True)`` over a preloaded row.

    Row layout (must match the backfill SELECT):
      document_id, title, document_type, owner_user_id,
      raw_text, content_class, metadata, taken_down

    Mirrors serve.py's owner path + serve_guard's rights arm using the SAME
    predicates/constants, so a preloaded pass and the per-row gate cannot
    drift apart: taken-down wins, owner-personal-reading admits the body,
    servable admits the body, everything else yields ``metadata_only``; a
    body that fails the rights tier or the link-back invariant is also
    ``metadata_only`` (the serve gate still refuses it loudly — this is the
    declaration, not a serve). ``verify_twin_source_envelopes`` recomputes
    through ``_row_envelope`` and proves equality, so any future divergence
    between this fast path and the gate fails the audit loudly.
    """
    document_id = str(row[0])
    title = None if row[1] is None else str(row[1])
    document_type = str(row[2])
    owner_user_id = str(row[3])
    raw_text = row[4]
    content_class = row[5]
    metadata = row[6]
    taken_down = bool(row[7])

    body: str | None = None
    if not taken_down:
        status = servability_of(content_class, taken_down=taken_down)
        if (
            content_class == PERSONAL_READING_CONTENT_CLASS
            and content_class in PERSONAL_READABLE_CONTENT_CLASSES
        ) or is_servable_full_text(status) and content_class in SERVABLE_CONTENT_CLASSES:
            body = raw_text if isinstance(raw_text, str) else None
        # gated / denied classes: no body (metadata_only)
        if body is not None:
            ctx = _rights_context_from_metadata(metadata)
            if ctx.tier is not None and (
                not body_servable(ctx.tier)
                or ctx.arxiv_id is None
                or ctx.license_uri is None
            ):
                body = None

    envelope = build_twin_source_envelope(
        document_id=document_id,
        title=title,
        raw_text=body,
        document_type=document_type,
        owner_user_id=owner_user_id,
    )
    return envelope, body


def verify_twin_source_envelopes(
    con: LockedConnection, *, account_id: str | None = None
) -> tuple[TwinSourceEnvelope, ...]:
    """Prove every document has one exact declaration derived from current row bytes."""
    return tuple(envelope for envelope, _asset_value in _verified_rows(con, account_id))


def _verified_rows(
    con: LockedConnection, account_id: str | None
) -> list[tuple[TwinSourceEnvelope, AssetContent | None]]:
    _require_locked(con)
    query = (
        "SELECT document_id,title,document_type,owner_user_id,twin_source_envelope "
        "FROM documents"
    )
    params: list[str] = []
    if account_id is not None:
        query += " WHERE owner_user_id=?"
        params.append(account_id)
    rows = con.execute(query + " ORDER BY owner_user_id,document_id", params).fetchall()
    envelopes: list[tuple[TwinSourceEnvelope, AssetContent | None]] = []
    for row in rows:
        if row[4] is None:
            raise TwinSourceEnvelopeError(f"document {row[0]!r} lacks a twin declaration")
        persisted = TwinSourceEnvelope.from_json(str(row[4]))
        expected, guarded_body = _row_envelope(con, tuple(row[:4]))
        if persisted != expected:
            raise TwinSourceEnvelopeError(
                f"document {row[0]!r} conflicts with its twin declaration"
            )
        asset = None
        if persisted.status == "eligible":
            if guarded_body is None:
                raise TwinSourceEnvelopeError(
                    f"document {row[0]!r} lost owner-readable body authority"
                )
            asset = _asset(
                persisted.document_id, persisted.title, guarded_body,
                persisted.document_type, persisted.source_event_id,
            )
        envelopes.append((persisted, asset))
    return envelopes


def project_twin_sources(
    con: LockedConnection,
    ledger: TwinRecursionLedger,
    *,
    account_id: str,
) -> TwinSourceCoverage:
    """Idempotently project one account's verified eligible documents."""
    selected_rows = _verified_rows(con, account_id)
    selected = [envelope for envelope, _asset_value in selected_rows]
    snapshots = []
    for envelope, asset in selected_rows:
        if envelope.status == "eligible":
            assert asset is not None
            snapshots.append(ledger.register_source(SourceRevision(account_id, asset)))
    eligible = sum(envelope.status == "eligible" for envelope in selected)
    metadata_only = sum(envelope.status == "metadata_only" for envelope in selected)
    binding = sum(envelope.status == "requires_binding" for envelope in selected)
    enrichment = sum(envelope.status == "requires_enrichment" for envelope in selected)
    segmentation = sum(envelope.status == "requires_segmentation" for envelope in selected)
    if eligible == 0 and not (binding or enrichment or segmentation):
        verdict: CoverageVerdict = "unknown"
    elif binding or enrichment or segmentation:
        verdict = "partial"
    else:
        verdict = "universal" if all(snapshot.state == "ready" for snapshot in snapshots) else "partial"
    return TwinSourceCoverage(
        account_id, len(selected), eligible, metadata_only, binding, enrichment,
        segmentation, len(snapshots), verdict,
    )


def _require_locked(con: LockedConnection) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError("twin source registration requires a LockedConnection")


__all__ = [
    "ENVELOPE_SCHEMA",
    "TwinSourceCoverage",
    "TwinSourceEnvelope",
    "TwinSourceEnvelopeError",
    "backfill_twin_source_envelopes",
    "build_twin_source_envelope",
    "project_twin_sources",
    "stamp_existing_document",
    "verify_twin_source_envelopes",
]
