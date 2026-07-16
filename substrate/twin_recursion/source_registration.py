"""Canonical graph-document declarations for recursive twin obligations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Literal

from runtime.db_lock import LockedConnection
from substrate.books.html_sanitizer import is_trusted_sanitized, sanitize_book_html
from substrate.twin_note_taker import MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, AssetContent

from .ledger import SourceRevision, TwinLedgerError, TwinRecursionLedger
from .segmentation import build_segmentation_manifest
from .segmentation_ledger import TwinSegmentationLedger

ENVELOPE_SCHEMA = "antiek.twin-source-envelope.v1"
EnvelopeStatus = Literal[
    "eligible",
    "metadata_only",
    "requires_binding",
    "requires_enrichment",
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
            "eligible",
            "metadata_only",
            "requires_binding",
            "requires_enrichment",
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
    segmentation_registered: int
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
            ENVELOPE_SCHEMA,
            "metadata_only",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "no_substantive_body",
        )
    if document_type in {"multimedia_twin", "canonical_twin"}:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "requires_binding",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            (
                "canonical_twin_is_derived"
                if document_type == "canonical_twin"
                else "legacy_twin_requires_canonical_binding"
            ),
        )
    if stripped_length < MIN_CONTENT_CHARS:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "requires_enrichment",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "body_below_materializer_floor",
        )
    if len(raw_text) > MAX_CONTENT_CHARS:
        return TwinSourceEnvelope(
            ENVELOPE_SCHEMA,
            "requires_segmentation",
            owner_user_id,
            document_id,
            exact_title,
            document_type,
            body_sha,
            source_event_id,
            None,
            "body_exceeds_materializer_limit",
        )
    asset = _asset(document_id, exact_title, raw_text, document_type, source_event_id)
    revision = SourceRevision(owner_user_id, asset)
    return TwinSourceEnvelope(
        ENVELOPE_SCHEMA,
        "eligible",
        owner_user_id,
        document_id,
        exact_title,
        document_type,
        body_sha,
        source_event_id,
        revision.source_hash,
        None,
    )


def _asset(
    document_id: str, title: str, raw_text: str, document_type: str, source_event_id: str
) -> AssetContent:
    return AssetContent(
        asset_id=document_id,
        title=title,
        content_text=raw_text,
        content_class=document_type,
        source_event_ids=(source_event_id,),
    )


def _row_envelope(row: tuple[Any, ...]) -> TwinSourceEnvelope:
    return build_twin_source_envelope(
        document_id=str(row[0]),
        title=None if row[1] is None else str(row[1]),
        raw_text=None if row[2] is None else str(row[2]),
        document_type=str(row[3]),
        owner_user_id=str(row[4]),
    )


def stamp_existing_document(con: LockedConnection, document_id: str) -> None:
    """Fill one legacy NULL declaration from stored bytes; exact rows are no-ops."""
    _require_locked(con)
    row = con.execute(
        "SELECT document_id,title,raw_text,document_type,owner_user_id,twin_source_envelope "
        "FROM documents WHERE document_id=?",
        [document_id],
    ).fetchone()
    if row is None:
        raise KeyError(document_id)
    expected = _row_envelope(tuple(row[:5])).to_json()
    if row[5] is None:
        con.execute(
            "UPDATE documents SET twin_source_envelope=? "
            "WHERE document_id=? AND twin_source_envelope IS NULL",
            [expected, document_id],
        )


def backfill_twin_source_envelopes(con: LockedConnection) -> int:
    """Backfill all legacy rows under one caller-held graph write lock."""
    _require_locked(con)
    rows = con.execute(
        "SELECT document_id,title,raw_text,document_type,owner_user_id "
        "FROM documents WHERE twin_source_envelope IS NULL ORDER BY document_id"
    ).fetchall()
    con.execute("BEGIN")
    try:
        for row in rows:
            con.execute(
                "UPDATE documents SET twin_source_envelope=? "
                "WHERE document_id=? AND twin_source_envelope IS NULL",
                [_row_envelope(tuple(row)).to_json(), str(row[0])],
            )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return len(rows)


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
        "SELECT document_id,title,raw_text,document_type,owner_user_id,twin_source_envelope "
        "FROM documents"
    )
    params: list[str] = []
    if account_id is not None:
        query += " WHERE owner_user_id=?"
        params.append(account_id)
    rows = con.execute(query + " ORDER BY owner_user_id,document_id", params).fetchall()
    envelopes: list[tuple[TwinSourceEnvelope, AssetContent | None]] = []
    for row in rows:
        if row[5] is None:
            raise TwinSourceEnvelopeError(f"document {row[0]!r} lacks a twin declaration")
        persisted = TwinSourceEnvelope.from_json(str(row[5]))
        expected = _row_envelope(tuple(row[:5]))
        if persisted != expected:
            raise TwinSourceEnvelopeError(
                f"document {row[0]!r} conflicts with its twin declaration"
            )
        asset = None
        if persisted.status in {"eligible", "requires_segmentation"}:
            raw_text = str(row[2])
            asset = _asset(
                persisted.document_id,
                persisted.title,
                raw_text,
                persisted.document_type,
                persisted.source_event_id,
            )
        envelopes.append((persisted, asset))
    return envelopes


def project_twin_sources(
    con: LockedConnection,
    ledger: TwinRecursionLedger,
    segmentation_ledger: TwinSegmentationLedger,
    *,
    account_id: str,
) -> TwinSourceCoverage:
    """Idempotently project one account's verified eligible documents."""
    selected_rows = _verified_rows(con, account_id)
    selected = [envelope for envelope, _asset_value in selected_rows]
    snapshots = []
    segmentation_snapshots = []
    verified_derived = 0
    for envelope, asset in selected_rows:
        if envelope.status == "eligible":
            assert asset is not None
            snapshots.append(ledger.register_source(SourceRevision(account_id, asset)))
        elif envelope.status == "requires_segmentation":
            assert asset is not None
            manifest = build_segmentation_manifest(account_id=account_id, asset=asset)
            segmentation_snapshots.append(
                segmentation_ledger.register(manifest, account_id=account_id, asset=asset)
            )
        elif (
            envelope.status == "requires_binding"
            and envelope.reason == "canonical_twin_is_derived"
            and _verify_canonical_twin_publication(con, ledger, envelope)
        ):
            verified_derived += 1
    eligible = sum(envelope.status == "eligible" for envelope in selected)
    metadata_only = sum(envelope.status == "metadata_only" for envelope in selected)
    binding = sum(envelope.status == "requires_binding" for envelope in selected)
    binding -= verified_derived
    enrichment = sum(envelope.status == "requires_enrichment" for envelope in selected)
    segmentation = sum(envelope.status == "requires_segmentation" for envelope in selected)
    if eligible == 0 and not (binding or enrichment or segmentation):
        verdict: CoverageVerdict = "unknown"
    elif binding or enrichment or segmentation:
        verdict = "partial"
    else:
        verdict = (
            "universal" if all(snapshot.state == "ready" for snapshot in snapshots) else "partial"
        )
    return TwinSourceCoverage(
        account_id,
        len(selected),
        eligible,
        metadata_only,
        binding,
        enrichment,
        segmentation,
        len(snapshots),
        len(segmentation_snapshots),
        verdict,
    )


def _verify_canonical_twin_publication(
    con: LockedConnection,
    ledger: TwinRecursionLedger,
    envelope: TwinSourceEnvelope,
) -> bool:
    row = con.execute(
        "SELECT raw_text,metadata FROM documents WHERE document_id=? "
        "AND owner_user_id=? AND document_type='canonical_twin'",
        [envelope.document_id, envelope.account_id],
    ).fetchone()
    if row is None or row[0] is None or row[1] is None:
        return False
    try:
        metadata = json.loads(str(row[1]))
        if (
            type(metadata) is not dict
            or set(metadata)
            != {
                "authority",
                "binding_id",
                "body_hash",
                "chunk_id",
                "chunk_sha256",
                "completion_digest",
                "content_sanitized",
                "content_sanitizer_version",
                "schema",
                "source_asset_id",
                "source_hash",
            }
            or _canonical_json(metadata) != str(row[1])
            or metadata["schema"] != "antiek.canonical-twin-publication.v2"
            or metadata["authority"] != "advisory_twin_v1"
            or not is_trusted_sanitized(metadata)
        ):
            return False
        chunks = con.execute(
            "SELECT chunk_id,chunk_index,section_path,text,token_count FROM chunks "
            "WHERE document_id=? ORDER BY chunk_id",
            [envelope.document_id],
        ).fetchall()
        if len(chunks) != 1:
            return False
        chunk = chunks[0]
        if (
            chunk[0] != metadata["chunk_id"]
            or chunk[1] != 0
            or chunk[2] != "Advisory twin notes"
            or type(chunk[3]) is not str
            or _sha(str(chunk[3])) != metadata["chunk_sha256"]
            or chunk[4] != 0
        ):
            return False
        with ledger.canonical_publication(str(metadata["binding_id"])) as publication:
            if (
                publication.account_id != envelope.account_id
                or publication.twin_id != envelope.document_id
                or sanitize_book_html(publication.rendered_html) != str(row[0])
                or publication.body_hash != metadata["body_hash"]
                or publication.completion_digest != metadata["completion_digest"]
                or publication.source_asset_id != metadata["source_asset_id"]
                or publication.source_hash != metadata["source_hash"]
            ):
                return False
            verified_binding_id = publication.binding_id
            verified_twin_id = publication.twin_id
        child = ledger.register_materialized_twin(verified_binding_id)
        return child.asset_id == verified_twin_id and not child.twinnable
    except (json.JSONDecodeError, KeyError, TypeError, ValueError, TwinLedgerError):
        return False


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
