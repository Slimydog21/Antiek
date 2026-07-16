"""Atomic publication of canonical advisory twins into graph retrieval."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass

from runtime.db_lock import LockedConnection
from substrate.graph.ops import insert_chunk, insert_document

from .ledger import TwinIntegrityError, TwinRecursionLedger
from .source_registration import build_twin_source_envelope

PUBLICATION_SCHEMA = "antiek.canonical-twin-publication.v1"


class CanonicalTwinPublicationError(RuntimeError):
    """Graph publication is absent, substituted, or contradictory."""


@dataclass(frozen=True)
class CanonicalTwinPublicationResult:
    document_id: str
    chunk_id: str
    binding_id: str
    body_hash: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _chunk_id(binding_id: str, chunk_text: str) -> str:
    digest = hashlib.sha256(
        _canonical_json([PUBLICATION_SCHEMA, binding_id, chunk_text]).encode("utf-8")
    ).hexdigest()
    return "twin-chunk-" + digest


def publish_canonical_twin(
    con: LockedConnection,
    ledger: TwinRecursionLedger,
    *,
    binding_id: str,
    failure_injector: Callable[[str], None] | None = None,
) -> CanonicalTwinPublicationResult:
    """Publish one exact binding as one document and one unembedded chunk."""
    if type(con) is not LockedConnection:
        raise TypeError("publication requires the exact locked graph connection")
    if type(ledger) is not TwinRecursionLedger:
        raise TypeError("publication requires the exact canonical twin ledger")

    def checkpoint(name: str) -> None:
        if failure_injector is not None:
            failure_injector(name)

    with ledger.canonical_publication(binding_id) as publication:
        source_uri = f"antiek:twin-binding:{publication.binding_id}"
        chunk_id = _chunk_id(publication.binding_id, publication.chunk_text)
        metadata = _canonical_json(
            {
                "authority": "advisory_twin_v1",
                "binding_id": publication.binding_id,
                "body_hash": publication.body_hash,
                "chunk_id": chunk_id,
                "chunk_sha256": hashlib.sha256(
                    publication.chunk_text.encode("utf-8")
                ).hexdigest(),
                "completion_digest": publication.completion_digest,
                "schema": PUBLICATION_SCHEMA,
                "source_asset_id": publication.source_asset_id,
                "source_hash": publication.source_hash,
            }
        )
        envelope = build_twin_source_envelope(
            document_id=publication.twin_id,
            title=publication.title,
            raw_text=publication.rendered_html,
            document_type="canonical_twin",
            owner_user_id=publication.account_id,
        ).to_json()
        expected_document = (
            publication.twin_id,
            source_uri,
            publication.title,
            None,
            None,
            5,
            "canonical_twin",
            f"twin-{publication.source_asset_id}",
            publication.rendered_html,
            metadata,
            "personal_reading",
            None,
            publication.account_id,
            envelope,
        )
        expected_chunk = (
            chunk_id,
            publication.twin_id,
            0,
            "Advisory twin notes",
            publication.chunk_text,
            0,
        )
        con.execute("BEGIN TRANSACTION")
        try:
            document = con.execute(
                "SELECT document_id,source_uri,title,author,published_at,source_tier,"
                "document_type,investigation_id,raw_text,metadata,content_class,"
                "ip_holder_id,owner_user_id,twin_source_envelope FROM documents "
                "WHERE document_id=?",
                [publication.twin_id],
            ).fetchone()
            chunk = con.execute(
                "SELECT chunk_id,document_id,chunk_index,section_path,text,token_count "
                "FROM chunks WHERE chunk_id=?",
                [chunk_id],
            ).fetchone()
            document_chunks = con.execute(
                "SELECT chunk_id FROM chunks WHERE document_id=? ORDER BY chunk_id",
                [publication.twin_id],
            ).fetchall()
            if document_chunks not in ([], [(chunk_id,)]):
                raise CanonicalTwinPublicationError(
                    "canonical publication has unexpected retrieval chunks"
                )
            if document is None and chunk is None:
                insert_document(
                    con,
                    document_id=publication.twin_id,
                    source_tier=5,
                    document_type="canonical_twin",
                    source_uri=source_uri,
                    title=publication.title,
                    investigation_id=f"twin-{publication.source_asset_id}",
                    raw_text=publication.rendered_html,
                    metadata=metadata,
                    content_class="personal_reading",
                    owner_user_id=publication.account_id,
                )
                checkpoint("after_document_insert")
                insert_chunk(
                    con,
                    document_id=publication.twin_id,
                    chunk_index=0,
                    text=publication.chunk_text,
                    section_path="Advisory twin notes",
                    chunk_id=chunk_id,
                )
            elif document is None or chunk is None:
                raise CanonicalTwinPublicationError("publication document and chunk are not atomic")
            elif tuple(document) != expected_document or tuple(chunk) != expected_chunk:
                raise CanonicalTwinPublicationError("canonical publication substitution")
            checkpoint("before_publication_commit")
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        result = CanonicalTwinPublicationResult(
            publication.twin_id, chunk_id, publication.binding_id, publication.body_hash
        )
    # The source snapshot remains authoritative through COMMIT. A malformed
    # return value cannot turn a failed transaction into published state.
    if not result.document_id or not result.chunk_id:
        raise TwinIntegrityError("canonical publication result is malformed")
    return result


__all__ = [
    "CanonicalTwinPublicationError",
    "CanonicalTwinPublicationResult",
    "PUBLICATION_SCHEMA",
    "publish_canonical_twin",
]
