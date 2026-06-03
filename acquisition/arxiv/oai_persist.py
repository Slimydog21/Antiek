"""Persist harvested OAI-PMH records into the documents store (SPR-01 M3/M5).

This is the substrate-write half the harvest was missing: the OAI-PMH stream
(``acquisition.arxiv.oai_pmh``) produces a census, but a census is a count, not
a corpus. M5 ("full metadata corpus present IN THE DB") and M3 ("re-ingesting an
id UPDATES, never duplicates") both require the metadata to actually LAND as
rows, keyed by ``arxiv_id``, through the single-writer path.

What this writes — and deliberately what it does NOT:

  * It writes ONE ``documents`` row per LIVE record, with the stable doc id
    ``doc-arxiv-<sanitized_id>`` (the same id ``acquisition.arxiv.adapter``
    mints, so the metadata row and any later full-text ingest of the same paper
    are the SAME row, not two). The arXiv id is the stable upsert key: re-running
    a harvest UPDATES the row in place, it never inserts a duplicate.

  * ``content_class`` is the deny-by-default GATED FLOOR
    (``GATED_DEFAULT_CONTENT_CLASS`` = ``restricted_pending_opt_in``) for EVERY
    record, regardless of license. This is metadata-only: there is NO body yet
    (the abstract/PDF full text is SPR-04's job — this module fetches and stores
    NO PDF). A bodyless row is never servable, so it lands at the gated floor and
    SPR-04 promotes it to its license-derived class when (and only when) it
    actually ingests a servable body. Deny-by-default is enforced at the write,
    not hoped for at the read.

  * The AUTHORITATIVE rights anchor is preserved now so SPR-04 doesn't re-fetch
    it: the OAI ``<license>`` URI (``record.license_uri``), the resolved tier,
    and a human-readable ``license_basis`` ride in ``documents.metadata`` (the
    TEXT-JSON column). The license is read from arXiv's own per-paper element —
    never inferred from anything else.

  * DELETED tombstones (``record.deleted``) carry no metadata; they are SKIPPED
    here (they still advance the harvest window — that is the sync's concern, not
    the corpus's). A future SPR may soft-delete the matching row; today a
    tombstone is simply not a corpus row.

Layering: this module lives in ``acquisition`` (which legitimately imports
``substrate``), mirroring ``substrate.books.ingest``'s note that the acquisition
layer orchestrates the substrate write — substrate never reaches up into
acquisition. Every write goes through ``runtime.db_lock.connect_write`` (the
only-writer invariant, architecture_notes §2.3).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from runtime.db_lock import LockedConnection, connect_write
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import _maybe_json
from substrate.schemas.documents import ArxivOaiRecord

from .adapter import arxiv_doc_id
from .licenses import license_basis_string, resolve_license

# arXiv preprints are academic but unrefereed → tier 3 (matches the adapter's
# DEFAULT_ARXIV_SOURCE_TIER). The metadata row carries the same tier the
# full-text ingest would, so SPR-04 doesn't re-decide it.
DEFAULT_ARXIV_OAI_SOURCE_TIER = 3

# The document_type for an OAI-harvested metadata-only row. Matches the
# adapter's full-text/abstract path ("academic_paper") so the metadata row and a
# later body ingest of the same id describe the same document_type, not two.
_OAI_DOCUMENT_TYPE = "academic_paper"


@dataclass(frozen=True)
class OaiPersistResult:
    """Tally of one persistence pass over a harvest stream.

    ``inserted`` + ``updated`` is the number of LIVE records that landed as rows;
    ``skipped_deleted`` is the tombstone count (excluded from the corpus by
    construction). The split between inserted/updated is what makes the M3
    idempotency claim checkable: a second pass over the same ids reports
    ``inserted == 0`` and ``updated == N``.
    """

    inserted: int = 0
    updated: int = 0
    skipped_deleted: int = 0

    @property
    def persisted(self) -> int:
        """Live rows written (new + refreshed) this pass."""
        return self.inserted + self.updated


def _record_metadata(record: ArxivOaiRecord) -> dict:
    """The provenance + rights payload stamped into ``documents.metadata``.

    Carries the AUTHORITATIVE OAI ``<license>`` URI, the resolved census tier,
    and a self-explaining ``license_basis`` — so SPR-04 can promote the gated
    floor to the license-derived servable class WITHOUT re-harvesting, and a
    reviewer can read the rights decision off the row."""
    resolution = resolve_license(record.license_uri)
    return {
        "source": "arxiv_oai_pmh",
        "arxiv_id": record.arxiv_id,
        "oai_datestamp": record.datestamp,
        "categories": list(record.categories),
        # The rights anchor — arXiv's own per-paper element, copied verbatim.
        "license_uri": record.license_uri,
        "license_basis": license_basis_string(resolution),
        "rights_tier": record.tier.value,
        # Recorded for SPR-04: the class this row WOULD carry once it has a
        # servable body. Today the row stays at the gated floor (no body).
        "license_content_class": resolution.content_class,
    }


def persist_oai_record(con: LockedConnection, record: ArxivOaiRecord) -> bool:
    """UPSERT one LIVE OAI record into ``documents``, keyed by arxiv_id.

    Returns ``True`` if a NEW row was inserted, ``False`` if an existing row
    was updated. Deleted tombstones must be filtered by the caller — this
    function assumes a live record.

    Idempotency is REAL: the doc id is ``arxiv_doc_id(record.arxiv_id)`` (stable
    across runs), so a re-ingest of the same id finds the existing row and
    UPDATEs its mutable fields (title, source_uri, metadata) in place rather than
    inserting a second row. ``content_class`` is the deny-by-default gated floor
    on both insert and update — a metadata-only row is never servable, and the
    floor never moves here (SPR-04 owns promotion), so the indexed-gate-column
    UPDATE dance is never needed.
    """
    if record.deleted:
        raise ValueError(
            f"persist_oai_record received a tombstone ({record.arxiv_id!r}); "
            "filter deleted records before calling (they are not corpus rows)."
        )

    document_id = arxiv_doc_id(record.arxiv_id)
    source_uri = f"https://arxiv.org/abs/{record.arxiv_id}"
    metadata_json = _maybe_json(_record_metadata(record))

    exists = con.execute(
        "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
    ).fetchone() is not None

    if exists:
        # Refresh the mutable, non-indexed columns. content_class is left at the
        # gated floor it was inserted with (and is unchanged here), so no
        # FK-index drop/recreate is required.
        con.execute(
            "UPDATE documents SET title = ?, source_uri = ?, metadata = ? "
            "WHERE document_id = ?",
            [record.title, source_uri, metadata_json, document_id],
        )
        return False

    con.execute(
        "INSERT INTO documents "
        "(document_id, source_uri, title, source_tier, document_type, "
        " metadata, content_class) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            document_id,
            source_uri,
            record.title,
            DEFAULT_ARXIV_OAI_SOURCE_TIER,
            _OAI_DOCUMENT_TYPE,
            metadata_json,
            GATED_DEFAULT_CONTENT_CLASS,
        ],
    )
    return True


def persist_oai_records(
    records: Iterable[ArxivOaiRecord],
    *,
    db_path: str | None = None,
) -> OaiPersistResult:
    """UPSERT a whole harvest stream into ``documents`` under ONE write lock.

    The entire pass runs inside a single ``connect_write`` critical section so a
    multi-page backfill serializes against any other writer exactly once (not
    per-record), matching the single-writer invariant and the throttle's
    single-stream assumption. Deleted tombstones are skipped; live records are
    upserted by arxiv_id.

    ``db_path`` defaults to the resolved graph DB (honoring
    ``ANTIEK_DUCKDB_PATH`` for tests). The schema is ensured first so the very
    first harvest on a fresh box creates the file + tables.
    """
    resolved = ensure_initialized(db_path or default_db_path())

    inserted = updated = skipped = 0
    with connect_write(resolved, purpose="acquisition/arxiv_oai") as con:
        for record in records:
            if record.deleted:
                skipped += 1
                continue
            if persist_oai_record(con, record):
                inserted += 1
            else:
                updated += 1

    return OaiPersistResult(
        inserted=inserted, updated=updated, skipped_deleted=skipped
    )
