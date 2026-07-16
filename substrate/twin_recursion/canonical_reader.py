"""Owner-only read projection for canonical advisory twins."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from substrate.books.html_sanitizer import (
    is_trusted_sanitized,
    sanitize_book_html,
    sanitized_html_provenance,
)

from .canonical_publication import LEGACY_PUBLICATION_SCHEMA, PUBLICATION_SCHEMA
from .ledger import TwinRecursionLedger
from .source_registration import build_twin_source_envelope


class CanonicalTwinReaderNotFound(LookupError):
    """Uniform denial for absent, unauthorized, or unverifiable twins."""


@dataclass(frozen=True)
class CanonicalTwinReaderView:
    document_id: str
    source_asset_id: str
    source_hash: str
    title: str
    html_fragment: str
    authority: Literal["advisory"] = "advisory"
    authority_label: str = "AI-generated advisory notes; verify against sources"
    shareable: Literal[False] = False


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _chunk_id(binding_id: str, chunk_text: str) -> str:
    digest = hashlib.sha256(
        _canonical_json([LEGACY_PUBLICATION_SCHEMA, binding_id, chunk_text]).encode()
    ).hexdigest()
    return "twin-chunk-" + digest


def _exact_text(value: object, field: str) -> str:
    if type(value) is not str or not value or len(value) > 512:
        raise ValueError(f"{field} must be an exact bounded non-empty string")
    return value


class CanonicalTwinReader:
    """Verify canonical lifecycle and graph commitments before serving HTML."""

    def __init__(self, con: Any, ledger: TwinRecursionLedger):
        if type(ledger) is not TwinRecursionLedger:
            raise TypeError("reader requires the exact canonical twin ledger")
        self._con = con
        self._ledger = ledger

    def read_by_source(
        self, *, owner_id: str, source_asset_id: str, source_hash: str
    ) -> CanonicalTwinReaderView:
        owner_id = _exact_text(owner_id, "owner_id")
        source_asset_id = _exact_text(source_asset_id, "source_asset_id")
        source_hash = _exact_text(source_hash, "source_hash")
        rows = self._con.execute(
            "SELECT document_id,source_uri,title,author,published_at,source_tier,"
            "document_type,investigation_id,raw_text,metadata,content_class,ip_holder_id,"
            "owner_user_id,twin_source_envelope FROM documents WHERE owner_user_id=? "
            "AND document_type='canonical_twin' ORDER BY document_id",
            [owner_id],
        ).fetchall()
        matches: list[tuple[Any, ...]] = []
        for row in rows:
            try:
                metadata = json.loads(row[9])
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if (
                type(metadata) is dict
                and metadata.get("schema") == PUBLICATION_SCHEMA
                and metadata.get("authority") == "advisory_twin_v1"
                and metadata.get("source_asset_id") == source_asset_id
                and metadata.get("source_hash") == source_hash
            ):
                matches.append((*row, metadata))
        if len(matches) != 1:
            raise CanonicalTwinReaderNotFound("canonical twin unavailable")
        row = matches[0]
        metadata = row[14]
        expected_keys = {
            "authority", "binding_id", "body_hash", "chunk_id", "chunk_sha256",
            "completion_digest", "content_sanitized", "content_sanitizer_version",
            "schema", "source_asset_id", "source_hash",
        }
        if (
            set(metadata) != expected_keys
            or not is_trusted_sanitized(metadata)
            or _canonical_json(metadata) != row[9]
        ):
            raise CanonicalTwinReaderNotFound("canonical twin unavailable")
        binding_id = metadata.get("binding_id")
        if type(binding_id) is not str:
            raise CanonicalTwinReaderNotFound("canonical twin unavailable")
        try:
            with self._ledger.canonical_publication(binding_id) as publication:
                chunk_id = _chunk_id(binding_id, publication.chunk_text)
                chunks = self._con.execute(
                    "SELECT chunk_id,chunk_index,section_path,text,token_count FROM chunks "
                    "WHERE document_id=? ORDER BY chunk_id",
                    [publication.twin_id],
                ).fetchall()
                expected_chunk = (
                    chunk_id, 0, "Advisory twin notes", publication.chunk_text, 0
                )
                expected_metadata = {
                    "authority": "advisory_twin_v1",
                    "binding_id": publication.binding_id,
                    "body_hash": publication.body_hash,
                    "chunk_id": chunk_id,
                    "chunk_sha256": hashlib.sha256(publication.chunk_text.encode()).hexdigest(),
                    "completion_digest": publication.completion_digest,
                    "schema": PUBLICATION_SCHEMA,
                    "source_asset_id": publication.source_asset_id,
                    "source_hash": publication.source_hash,
                }
                expected_metadata.update(sanitized_html_provenance())
                sanitized_html = sanitize_book_html(publication.rendered_html)
                envelope = build_twin_source_envelope(
                    document_id=publication.twin_id,
                    title=publication.title,
                    raw_text=sanitized_html,
                    document_type="canonical_twin",
                    owner_user_id=publication.account_id,
                ).to_json()
                expected_document = (
                    publication.twin_id,
                    f"antiek:twin-binding:{binding_id}",
                    publication.title,
                    None,
                    None,
                    5,
                    "canonical_twin",
                    f"twin-{publication.source_asset_id}",
                    sanitized_html,
                    _canonical_json(expected_metadata),
                    "personal_reading",
                    None,
                    owner_id,
                    envelope,
                )
                if (
                    publication.account_id != owner_id
                    or publication.source_asset_id != source_asset_id
                    or publication.source_hash != source_hash
                    or tuple(row[:14]) != expected_document
                    or metadata != expected_metadata
                    or chunks != [expected_chunk]
                ):
                    raise CanonicalTwinReaderNotFound("canonical twin unavailable")
                return CanonicalTwinReaderView(
                    document_id=publication.twin_id,
                    source_asset_id=source_asset_id,
                    source_hash=source_hash,
                    title=publication.title,
                    html_fragment=sanitized_html,
                )
        except CanonicalTwinReaderNotFound:
            raise
        except Exception as exc:
            raise CanonicalTwinReaderNotFound("canonical twin unavailable") from exc


__all__ = ["CanonicalTwinReader", "CanonicalTwinReaderNotFound", "CanonicalTwinReaderView"]
