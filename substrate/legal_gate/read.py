"""Owner-scoped, revocation-aware reads over admitted document bytes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.investigation_tenancy import InvestigationAuthority

from .admission import require_allowed_receipt
from .policy_store import LegalPolicyDenied, account_policy_authority


@dataclass(frozen=True)
class ReadableAdmission:
    receipt_id: str
    document_id: str
    content_sha256: str
    provenance_class: str


_REPLACEMENT_TOKEN = object()


@dataclass(frozen=True, init=False)
class DocumentReplacementCapability:
    """Exact prior revision authorized for one content-bound replacement."""

    account_digest: str
    investigation_digest: str
    document_id: str
    prior_receipt_id: str
    prior_content_sha256: str
    next_content_sha256: str
    _token: object

    def __init__(
        self,
        *,
        authority: InvestigationAuthority,
        document_id: str,
        prior_receipt_id: str,
        prior_content_sha256: str,
        next_content_sha256: str,
        _token: object,
    ) -> None:
        if _token is not _REPLACEMENT_TOKEN:
            raise LegalPolicyDenied("document replacement capability must be minted")
        object.__setattr__(self, "account_digest", authority.account_digest)
        object.__setattr__(self, "investigation_digest", authority.investigation_digest)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "prior_receipt_id", prior_receipt_id)
        object.__setattr__(self, "prior_content_sha256", prior_content_sha256)
        object.__setattr__(
            self, "next_content_sha256", next_content_sha256.removeprefix("sha256:")
        )
        object.__setattr__(self, "_token", _token)


@dataclass(frozen=True)
class UrlReplacementChunk:
    chunk_id: str
    chunk_index: int
    section_path: str | None
    text: str
    embedding: Any
    token_count: int


@dataclass(frozen=True)
class UrlReplacementOverride:
    chunk_id: str
    original_tier: int
    override_tier: int
    reason: str
    set_at: Any
    set_by: str | None


@dataclass(frozen=True)
class UrlReplacementArchive:
    document: tuple[tuple[str, Any], ...]
    chunks: tuple[UrlReplacementChunk, ...]
    referenced_chunk_ids: frozenset[str]
    referenced_document_edge_ids: frozenset[str]
    overrides: tuple[UrlReplacementOverride, ...]

    def document_value(self, name: str) -> Any:
        return dict(self.document)[name]


def authorize_document_replacement(
    con: Any,
    authority: InvestigationAuthority,
    document_id: str,
    *,
    next_content_sha256: str,
) -> DocumentReplacementCapability:
    """Mint replacement authority only from an exact current admitted revision."""
    digest = next_content_sha256.removeprefix("sha256:").lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError("replacement content hash must be a full SHA-256 digest")
    document = read_document(con, authority, document_id)
    # Replacement authority covers the complete admitted revision, not merely
    # its document row. A substituted, missing, or unmanifested chunk makes the
    # old revision ineligible before any new receipt can be written.
    read_chunks(con, authority, document_id)
    prior_digest = __import__("hashlib").sha256(document["raw_text"].encode()).hexdigest()
    return DocumentReplacementCapability(
        authority=authority,
        document_id=document_id,
        prior_receipt_id=str(document["legal_admission_receipt_id"]),
        prior_content_sha256=prior_digest,
        next_content_sha256=digest,
        _token=_REPLACEMENT_TOKEN,
    )


def require_document_replacement_capability(
    capability: DocumentReplacementCapability,
    authority: InvestigationAuthority,
    document_id: str,
    next_content_sha256: str,
) -> None:
    """Reject forged, cross-owner, cross-investigation, or retargeted capability."""
    if (
        not isinstance(capability, DocumentReplacementCapability)
        or capability._token is not _REPLACEMENT_TOKEN
        or capability.account_digest != authority.account_digest
        or capability.investigation_digest != authority.investigation_digest
        or capability.document_id != document_id
        or capability.next_content_sha256
        != next_content_sha256.removeprefix("sha256:").lower()
    ):
        raise LegalPolicyDenied("document replacement is unavailable")


def consume_document_replacement_capability(
    con: Any,
    capability: DocumentReplacementCapability,
    authority: InvestigationAuthority,
    document_id: str,
    next_content_sha256: str,
) -> ReadableAdmission:
    """Revalidate the exact old revision immediately before replacement."""
    require_document_replacement_capability(
        capability, authority, document_id, next_content_sha256
    )
    admission = readable_admission(con, authority, document_id)
    if (
        admission.receipt_id != capability.prior_receipt_id
        or admission.content_sha256 != capability.prior_content_sha256
    ):
        raise LegalPolicyDenied("document replacement is unavailable")
    document = read_document(con, authority, document_id)
    if __import__("hashlib").sha256(document["raw_text"].encode()).hexdigest() != (
        capability.prior_content_sha256
    ):
        raise LegalPolicyDenied("document replacement is unavailable")
    return admission


def document_custody_exists(con: Any, document_id: str) -> bool:
    """Reveal only collision presence, never ownership, policy, or bytes."""
    if not document_id:
        raise ValueError("document_id is required")
    return (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [document_id]
        ).fetchone()
        is not None
    )


def url_replacement_archive(
    con: Any,
    capability: DocumentReplacementCapability,
    authority: InvestigationAuthority,
    document_id: str,
    next_content_sha256: str,
) -> UrlReplacementArchive:
    """Return one exact, revalidated old revision for atomic archival."""
    consume_document_replacement_capability(
        con, capability, authority, document_id, next_content_sha256
    )
    document = read_document(con, authority, document_id)
    admitted_chunks = read_chunks(con, authority, document_id)
    ids = tuple(str(chunk["chunk_id"]) for chunk in admitted_chunks)
    embeddings: dict[str, Any] = {}
    referenced: frozenset[str] = frozenset()
    overrides: tuple[UrlReplacementOverride, ...] = ()
    document_edge_ids = frozenset(
        str(row[0])
        for row in con.execute(
            "SELECT edge_id FROM edges WHERE source_document_id = ? AND chunk_id IS NULL",
            [document_id],
        ).fetchall()
    )
    if ids:
        placeholders = ",".join("?" for _ in ids)
        embeddings = {
            str(row[0]): row[1]
            for row in con.execute(
                f"SELECT chunk_id, embedding FROM chunks WHERE chunk_id IN ({placeholders})",
                list(ids),
            ).fetchall()
        }
        referenced = frozenset(
            str(row[0])
            for row in con.execute(
                f"SELECT chunk_id FROM edges WHERE chunk_id IN ({placeholders}) "
                f"UNION SELECT chunk_id FROM chunk_tier_overrides "
                f"WHERE chunk_id IN ({placeholders})",
                [*ids, *ids],
            ).fetchall()
        )
        overrides = tuple(
            UrlReplacementOverride(
                chunk_id=str(row[0]),
                original_tier=int(row[1]),
                override_tier=int(row[2]),
                reason=str(row[3]),
                set_at=row[4],
                set_by=str(row[5]) if row[5] is not None else None,
            )
            for row in con.execute(
                "SELECT chunk_id, original_tier, override_tier, reason, set_at, set_by "
                f"FROM chunk_tier_overrides WHERE chunk_id IN ({placeholders})",
                list(ids),
            ).fetchall()
        )
    chunks = tuple(
        UrlReplacementChunk(
            chunk_id=str(chunk["chunk_id"]),
            chunk_index=int(chunk["chunk_index"]),
            section_path=chunk["section_path"],
            text=str(chunk["text"]),
            embedding=embeddings.get(str(chunk["chunk_id"])),
            token_count=int(chunk["token_count"]),
        )
        for chunk in admitted_chunks
    )
    fields = (
        "document_id",
        "source_uri",
        "title",
        "author",
        "published_at",
        "source_tier",
        "document_type",
        "investigation_id",
        "raw_text",
        "metadata",
        "content_class",
        "ip_holder_id",
        "owner_user_id",
        "legal_admission_receipt_id",
    )
    return UrlReplacementArchive(
        document=tuple((field, document.get(field)) for field in fields),
        chunks=chunks,
        referenced_chunk_ids=referenced,
        referenced_document_edge_ids=document_edge_ids,
        overrides=overrides,
    )


def url_legacy_replacement_archive(
    con: Any, document_id: str
) -> UrlReplacementArchive | None:
    """Centralized custody snapshot for authority-free compatibility writes."""
    document = read_document_compatibility(
        con, document_id, authority=None, enforce=False
    )
    if document is None:
        return None
    legacy_chunks = read_chunks_compatibility(
        con, document_id, authority=None, enforce=False
    )
    ids = tuple(str(chunk["chunk_id"]) for chunk in legacy_chunks)
    embeddings: dict[str, Any] = {}
    referenced: frozenset[str] = frozenset()
    overrides: tuple[UrlReplacementOverride, ...] = ()
    if ids:
        placeholders = ",".join("?" for _ in ids)
        embeddings = {
            str(row[0]): row[1]
            for row in con.execute(
                f"SELECT chunk_id, embedding FROM chunks WHERE chunk_id IN ({placeholders})",
                list(ids),
            ).fetchall()
        }
        referenced = frozenset(
            str(row[0])
            for row in con.execute(
                f"SELECT chunk_id FROM edges WHERE chunk_id IN ({placeholders}) "
                f"UNION SELECT chunk_id FROM chunk_tier_overrides "
                f"WHERE chunk_id IN ({placeholders})",
                [*ids, *ids],
            ).fetchall()
        )
        overrides = tuple(
            UrlReplacementOverride(
                chunk_id=str(row[0]),
                original_tier=int(row[1]),
                override_tier=int(row[2]),
                reason=str(row[3]),
                set_at=row[4],
                set_by=str(row[5]) if row[5] is not None else None,
            )
            for row in con.execute(
                "SELECT chunk_id, original_tier, override_tier, reason, set_at, set_by "
                f"FROM chunk_tier_overrides WHERE chunk_id IN ({placeholders})",
                list(ids),
            ).fetchall()
        )
    document_edge_ids = frozenset(
        str(row[0])
        for row in con.execute(
            "SELECT edge_id FROM edges WHERE source_document_id = ? AND chunk_id IS NULL",
            [document_id],
        ).fetchall()
    )
    chunks = tuple(
        UrlReplacementChunk(
            chunk_id=str(chunk["chunk_id"]),
            chunk_index=int(chunk["chunk_index"]),
            section_path=chunk["section_path"],
            text=str(chunk["text"]),
            embedding=embeddings.get(str(chunk["chunk_id"])),
            token_count=int(chunk["token_count"]),
        )
        for chunk in legacy_chunks
    )
    return UrlReplacementArchive(
        document=tuple(document.items()),
        chunks=chunks,
        referenced_chunk_ids=referenced,
        referenced_document_edge_ids=document_edge_ids,
        overrides=overrides,
    )


def document_investigation_hint(con: Any, document_id: str) -> str | None:
    """Return only the scalar needed to mint authority; it grants no read."""
    row = con.execute(
        "SELECT investigation_id FROM documents WHERE document_id = ?", [document_id]
    ).fetchone()
    return str(row[0]) if row is not None and row[0] else None


def chunk_investigation_hint(con: Any, chunk_id: str) -> str | None:
    """Return only a chunk's investigation identifier; it grants no bytes."""
    row = con.execute(
        "SELECT d.investigation_id FROM chunks c JOIN documents d "
        "ON c.document_id = d.document_id WHERE c.chunk_id = ?",
        [chunk_id],
    ).fetchone()
    return str(row[0]) if row is not None and row[0] else None


def readable_admission(
    con: Any,
    authority: InvestigationAuthority,
    document_id: str,
) -> ReadableAdmission:
    """Return the newest valid receipt, or reveal no custody details."""
    if not isinstance(authority, InvestigationAuthority):
        raise TypeError("legal document read requires InvestigationAuthority")
    if not document_id:
        raise ValueError("document_id is required")
    policy_authority = account_policy_authority(authority)
    rows = con.execute(
        "SELECT receipt_id, content_sha256, provenance_class "
        "FROM legal_document_admissions WHERE account_digest = ? "
        "AND investigation_digest = ? AND document_id = ? AND decision = 'allow' "
        "ORDER BY admitted_at DESC, created_at DESC, receipt_id DESC LIMIT 1",
        [authority.account_digest, authority.investigation_digest, document_id],
    ).fetchall()
    if not rows:
        raise LegalPolicyDenied("document is unavailable")
    receipt_id, content_sha256, provenance_class = rows[0]
    try:
        require_allowed_receipt(
            con,
            policy_authority,
            receipt_id=receipt_id,
            document_id=document_id,
            investigation_digest=authority.investigation_digest,
            content_sha256=content_sha256,
        )
    except (LegalPolicyDenied, ValueError, TypeError) as exc:
        raise LegalPolicyDenied("document is unavailable") from exc
    return ReadableAdmission(
        receipt_id=receipt_id,
        document_id=document_id,
        content_sha256=content_sha256,
        provenance_class=provenance_class,
    )


def readable_document_ids(
    con: Any,
    authority: InvestigationAuthority,
    *,
    candidate_ids: list[str] | tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Resolve readable IDs without returning denied-row metadata."""
    if candidate_ids is None:
        rows = con.execute(
            "SELECT DISTINCT document_id FROM legal_document_admissions "
            "WHERE account_digest = ? AND investigation_digest = ? AND decision = 'allow'",
            [authority.account_digest, authority.investigation_digest],
        ).fetchall()
        candidates = [row[0] for row in rows]
    else:
        candidates = list(dict.fromkeys(candidate_ids))
    readable: list[str] = []
    for document_id in candidates:
        try:
            readable_admission(con, authority, document_id)
        except LegalPolicyDenied:
            continue
        readable.append(document_id)
    return tuple(readable)


def read_document(
    con: Any,
    authority: InvestigationAuthority,
    document_id: str,
) -> dict[str, Any]:
    admission = readable_admission(con, authority, document_id)
    row = con.execute(
        "SELECT source_uri, title, author, published_at, source_tier, document_type, "
        "investigation_id, raw_text, metadata, content_class, ip_holder_id, owner_user_id "
        "FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    from substrate.constants import SERVABLE_CONTENT_CLASSES

    custody_seal = con.execute(
        "SELECT state_sha256, seal_fingerprint FROM legal_document_custody_seals "
        "WHERE document_id = ?",
        [document_id],
    ).fetchone()
    from .admission import document_custody_seal_values

    fields = (
        "source_uri",
        "title",
        "author",
        "published_at",
        "source_tier",
        "document_type",
        "investigation_id",
        "raw_text",
        "metadata",
        "content_class",
        "ip_holder_id",
        "owner_user_id",
    )
    expected_custody_seal = (
        document_custody_seal_values(
            receipt_id=admission.receipt_id,
            document_id=document_id,
            account_digest=authority.account_digest,
            investigation_digest=authority.investigation_digest,
            state=dict(zip(fields, row, strict=True)),
        )
        if row is not None
        else None
    )

    globally_readable_classes = SERVABLE_CONTENT_CLASSES - {"user_owned"}
    if (
        row is None
        or custody_seal != expected_custody_seal
        or not isinstance(row[7], str)
        or str(row[6] or "") != authority.investigation_id
        or (
            row[11] is not None
            and str(row[11]) != authority.account_id
            and row[9] not in globally_readable_classes
        )
    ):
        raise LegalPolicyDenied("document is unavailable")
    import hashlib

    if hashlib.sha256(row[7].encode()).hexdigest() != admission.content_sha256:
        raise LegalPolicyDenied("document is unavailable")
    return {
        "document_id": document_id,
        "source_uri": row[0],
        "title": row[1],
        "author": row[2],
        "published_at": row[3],
        "source_tier": row[4],
        "document_type": row[5],
        "investigation_id": row[6],
        "raw_text": row[7],
        "metadata": row[8],
        "content_class": row[9],
        "ip_holder_id": row[10],
        "owner_user_id": row[11],
        "legal_admission_receipt_id": admission.receipt_id,
    }


def read_document_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> dict[str, Any] | None:
    """Central migration seam for callers that still support legacy fixtures.

    New/enforced product reads always delegate to :func:`read_document`.
    The unenforced branch exists only until Sprint 4 removes the compatibility
    mode; keeping it inside this audited module prevents raw SQL from spreading.
    """
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return None
        try:
            return read_document(con, authority, document_id)
        except LegalPolicyDenied:
            return None
    row = con.execute(
        "SELECT source_uri, title, author, published_at, source_tier, document_type, "
        "investigation_id, raw_text, metadata, content_class, ip_holder_id, owner_user_id "
        "FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    return {
        "document_id": document_id,
        "source_uri": row[0],
        "title": row[1],
        "author": row[2],
        "published_at": row[3],
        "source_tier": row[4],
        "document_type": row[5],
        "investigation_id": row[6],
        "raw_text": row[7],
        "metadata": row[8],
        "content_class": row[9],
        "ip_holder_id": row[10],
        "owner_user_id": row[11],
        "legal_admission_receipt_id": None,
    }


def read_document_metadata_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> dict[str, Any] | None:
    """Read only gate and metadata fields, never document body bytes."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return None
        try:
            document = read_document(con, authority, document_id)
        except LegalPolicyDenied:
            return None
        return {
            "document_id": document_id,
            "content_class": document["content_class"],
            "metadata": document["metadata"],
        }
    row = con.execute(
        "SELECT content_class, metadata FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    return {"document_id": document_id, "content_class": row[0], "metadata": row[1]}


def read_document_metadata_value_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[bool, Any]:
    """Read only metadata, including from legacy minimal document schemas."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return False, None
        try:
            return True, read_document(con, authority, document_id)["metadata"]
        except LegalPolicyDenied:
            return False, None
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ?", [document_id]
    ).fetchone()
    return (True, row[0]) if row is not None else (False, None)


def read_document_ip_holder_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> str | None:
    """Resolve only attribution ownership through the migration seam."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return None
        try:
            document = read_document(con, authority, document_id)
        except LegalPolicyDenied:
            return None
        value = document["ip_holder_id"]
    else:
        row = con.execute(
            "SELECT ip_holder_id FROM documents WHERE document_id = ?",
            [document_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"document_id {document_id!r} not found in documents table")
        value = row[0]
    return str(value) if value else None


def graph_edge_staleness_rows_compatibility(
    con: Any,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
    investigation_id: str,
    limit: int | None,
) -> tuple[tuple[Any, ...], ...]:
    """Project temporal edge evidence without exposing document content."""
    params: list[Any] = []
    if enforce:
        if (
            not isinstance(authority, InvestigationAuthority)
            or authority.investigation_id != investigation_id
        ):
            return ()
        sql = (
            "SELECT e.edge_id, e.relation, e.valid_from, e.extracted_at, d.published_at "
            "FROM edges e LEFT JOIN documents d ON d.document_id = e.source_document_id "
            "WHERE e.valid_until IS NULL AND e.investigation_id = ? "
            "ORDER BY e.edge_id ASC"
        )
        params.append(investigation_id)
    else:
        sql = (
            "SELECT e.edge_id, e.relation, e.valid_from, e.extracted_at, d.published_at "
            "FROM edges e LEFT JOIN documents d ON d.document_id = e.source_document_id "
            "WHERE e.valid_until IS NULL ORDER BY e.edge_id ASC"
        )
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return tuple(con.execute(sql, params).fetchall())


def speak_derived_document_ids_compatibility(
    con: Any,
    project_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[str, ...]:
    """Resolve active Speak-derived book ids without projecting their bodies."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return ()
        resolved: list[str] = []
        for document_id in readable_document_ids(con, authority):
            try:
                document = read_document(con, authority, document_id)
            except LegalPolicyDenied:
                continue
            book = book_serve_document_compatibility(
                con, document_id, authority=authority, enforce=True
            )
            if (
                book is not None
                and book["book_registered"]
                and not book["taken_down"]
                and _speak_metadata_matches(document["metadata"], project_id)
            ):
                resolved.append(document_id)
        return tuple(resolved)
    return tuple(
        str(row[0])
        for row in con.execute(
            "SELECT d.document_id FROM documents d JOIN book_assets b "
            "ON b.document_id = d.document_id "
            "WHERE json_extract_string(d.metadata, '$.project_id') = ? "
            "AND json_extract_string(d.metadata, '$.provenance_class') = "
            "'speak_derived' AND COALESCE(b.taken_down, FALSE) = FALSE",
            [project_id],
        ).fetchall()
    )


def _speak_metadata_matches(raw: Any, project_id: str) -> bool:
    import json

    try:
        metadata = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return False
    return bool(
        isinstance(metadata, dict)
        and metadata.get("project_id") == project_id
        and metadata.get("provenance_class") == "speak_derived"
    )


def corpus_audit_missing_basis_ids(
    con: Any,
    *,
    servable_classes: tuple[str, ...],
    document_types: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Project only ids that violate the corpus license-basis invariant."""
    class_marks = ", ".join("?" for _ in servable_classes)
    params: list[Any] = []
    type_clause = ""
    if document_types is not None:
        type_marks = ", ".join("?" for _ in document_types)
        type_clause = f"d.document_type IN ({type_marks}) AND "
        params.extend(document_types)
    params.extend(servable_classes)
    return tuple(
        str(row[0])
        for row in con.execute(
            "SELECT d.document_id FROM documents d LEFT JOIN book_assets b "
            "ON d.document_id = b.document_id WHERE "
            + type_clause
            + f"d.content_class IN ({class_marks}) AND "
            "(b.license_basis IS NULL OR TRIM(b.license_basis) = '') "
            "ORDER BY d.document_id",
            params,
        ).fetchall()
    )


def corpus_audit_document_ids_by_class(
    con: Any, content_class: str
) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in con.execute(
            "SELECT document_id FROM documents WHERE content_class = ? "
            "ORDER BY document_id",
            [content_class],
        ).fetchall()
    )


def corpus_audit_training_export_ids(
    con: Any, table: str, content_class: str
) -> tuple[str, ...]:
    escaped = table.replace('"', '""')
    return tuple(
        str(row[0])
        for row in con.execute(
            f'SELECT e.document_id FROM "{escaped}" e JOIN documents d '
            "ON d.document_id = e.document_id WHERE d.content_class = ? "
            "ORDER BY e.document_id",
            [content_class],
        ).fetchall()
    )


def corpus_audit_servable_basis_rows(
    con: Any, servable_classes: tuple[str, ...]
) -> tuple[tuple[Any, Any], ...]:
    marks = ", ".join("?" for _ in servable_classes)
    return tuple(
        con.execute(
            "SELECT d.document_id, b.license_basis FROM documents d "
            "JOIN book_assets b ON d.document_id = b.document_id "
            f"WHERE d.content_class IN ({marks}) ORDER BY d.document_id",
            list(servable_classes),
        ).fetchall()
    )


def corpus_audit_identity_rows(con: Any) -> tuple[tuple[Any, ...], ...]:
    return tuple(
        con.execute(
            "SELECT document_id, source_uri, title, author, raw_text, metadata "
            "FROM documents ORDER BY document_id"
        ).fetchall()
    )


def corpus_audit_extraction_rows(con: Any) -> tuple[tuple[Any, Any], ...]:
    return tuple(
        con.execute(
            "SELECT document_id, raw_text FROM documents ORDER BY document_id"
        ).fetchall()
    )


def corpus_audit_dangling_ip_holder_ids(con: Any) -> tuple[str, ...]:
    return tuple(
        str(row[0])
        for row in con.execute(
            "SELECT document_id FROM documents WHERE ip_holder_id IS NOT NULL "
            "AND ip_holder_id NOT IN (SELECT ip_holder_id FROM ip_holders)"
        ).fetchall()
    )


def corpus_audit_summary_rows(
    con: Any, servable_classes: tuple[str, ...]
) -> tuple[int, int, int, int, tuple[tuple[Any, Any], ...]]:
    total_docs = int(con.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
    total_chunks = int(con.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])
    marks = ", ".join("?" for _ in servable_classes)
    servable = int(
        con.execute(
            f"SELECT COUNT(*) FROM documents WHERE content_class IN ({marks})",
            list(servable_classes),
        ).fetchone()[0]
    )
    gated = int(
        con.execute(
            "SELECT COUNT(*) FROM documents WHERE content_class IS NULL OR "
            f"content_class NOT IN ({marks})",
            list(servable_classes),
        ).fetchone()[0]
    )
    by_source = tuple(
        con.execute(
            "SELECT COALESCE(source_uri, '(unknown)'), COUNT(*) FROM documents "
            "GROUP BY 1 ORDER BY 2 DESC, 1"
        ).fetchall()
    )
    return total_docs, total_chunks, servable, gated, by_source


def read_chunks(
    con: Any,
    authority: InvestigationAuthority,
    document_id: str,
) -> tuple[dict[str, Any], ...]:
    document = read_document(con, authority, document_id)
    rows = con.execute(
        "SELECT c.chunk_id, c.chunk_index, c.section_path, c.text, c.token_count, "
        "a.chunk_index, a.section_path, a.token_count, a.text_sha256 "
        "FROM legal_chunk_admissions a LEFT JOIN chunks c ON a.chunk_id = c.chunk_id "
        "AND c.document_id = a.document_id WHERE a.receipt_id = ? "
        "AND a.document_id = ? AND a.document_id = ? "
        "ORDER BY c.chunk_index, c.chunk_id",
        [document["legal_admission_receipt_id"], document_id, document_id],
    ).fetchall()
    import hashlib

    seal = con.execute(
        "SELECT chunk_count, manifest_sha256, seal_fingerprint "
        "FROM legal_chunk_manifest_seals WHERE receipt_id = ? AND document_id = ?",
        [document["legal_admission_receipt_id"], document_id],
    ).fetchone()
    from .admission import chunk_manifest_seal_values

    manifest_rows = [
        (row[0], row[5], row[6], row[7], row[8])
        for row in rows
        if row[0] is not None
    ]
    expected_seal = chunk_manifest_seal_values(
        receipt_id=str(document["legal_admission_receipt_id"]),
        document_id=document_id,
        account_digest=authority.account_digest,
        investigation_digest=authority.investigation_digest,
        rows=manifest_rows,
    )

    if seal != expected_seal or any(
        row[0] is None
        or not isinstance(row[3], str)
        or hashlib.sha256(row[3].encode()).hexdigest() != row[8]
        or int(row[1]) != int(row[5])
        or row[2] != row[6]
        or int(row[4]) != int(row[7])
        for row in rows
    ):
        raise LegalPolicyDenied("document is unavailable")
    return tuple(
        {
            "chunk_id": row[0],
            "chunk_index": int(row[1]),
            "section_path": row[2],
            "text": row[3],
            "token_count": int(row[4]),
        }
        for row in rows
    )


def read_chunks_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[dict[str, Any], ...]:
    """Return the canonical chunk shape through the migration seam."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return ()
        try:
            return read_chunks(con, authority, document_id)
        except LegalPolicyDenied:
            return ()
    rows = con.execute(
        "SELECT chunk_id, chunk_index, section_path, text, token_count "
        "FROM chunks WHERE document_id = ? ORDER BY chunk_index, chunk_id",
        [document_id],
    ).fetchall()
    return tuple(
        {
            "chunk_id": row[0],
            "chunk_index": int(row[1]),
            "section_path": row[2],
            "text": row[3],
            "token_count": int(row[4]),
        }
        for row in rows
    )


def read_chunk_ids_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[str, ...]:
    """Resolve only ordered chunk identifiers, without legacy body bytes."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return ()
        try:
            return tuple(
                str(chunk["chunk_id"])
                for chunk in read_chunks(con, authority, document_id)
            )
        except LegalPolicyDenied:
            return ()
    return tuple(
        str(row[0])
        for row in con.execute(
            "SELECT chunk_id FROM chunks WHERE document_id = ? ORDER BY chunk_index",
            [document_id],
        ).fetchall()
    )


def read_chunk(
    con: Any,
    authority: InvestigationAuthority,
    chunk_id: str,
) -> dict[str, Any]:
    """Resolve one chunk only after its owning document passes legal read."""
    row = con.execute(
        "SELECT document_id FROM chunks WHERE chunk_id = ?", [chunk_id]
    ).fetchone()
    if row is None:
        raise LegalPolicyDenied("document is unavailable")
    for chunk in read_chunks(con, authority, str(row[0])):
        if chunk["chunk_id"] == chunk_id:
            return {**chunk, "document_id": str(row[0])}
    raise LegalPolicyDenied("document is unavailable")


def read_chunk_compatibility(
    con: Any,
    chunk_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[Any, ...] | None:
    """Return the API chunk projection through the migration seam."""
    if not enforce:
        return con.execute(
            "SELECT c.chunk_id, c.text, c.section_path, c.token_count, "
            "c.document_id, d.title, d.source_tier, d.content_class, "
            "COALESCE(b.taken_down, FALSE), h.display_name, h.status, "
            "d.investigation_id FROM chunks c "
            "JOIN documents d ON c.document_id = d.document_id "
            "LEFT JOIN book_assets b ON d.document_id = b.document_id "
            "LEFT JOIN ip_holders h ON d.ip_holder_id = h.ip_holder_id "
            "WHERE c.chunk_id = ?",
            [chunk_id],
        ).fetchone()
    if not isinstance(authority, InvestigationAuthority):
        return None
    try:
        chunk = read_chunk(con, authority, chunk_id)
        document = read_document(con, authority, str(chunk["document_id"]))
    except LegalPolicyDenied:
        return None
    book = con.execute(
        "SELECT COALESCE(taken_down, FALSE) FROM book_assets WHERE document_id = ?",
        [document["document_id"]],
    ).fetchone()
    holder = (
        con.execute(
            "SELECT display_name, status FROM ip_holders WHERE ip_holder_id = ?",
            [document["ip_holder_id"]],
        ).fetchone()
        if document["ip_holder_id"]
        else None
    )
    return (
        chunk["chunk_id"],
        chunk["text"],
        chunk["section_path"],
        chunk["token_count"],
        document["document_id"],
        document["title"],
        document["source_tier"],
        document["content_class"],
        bool(book[0]) if book is not None else False,
        holder[0] if holder is not None else None,
        holder[1] if holder is not None else None,
        document["investigation_id"],
    )


def read_chunk_texts_compatibility(
    con: Any,
    chunk_ids: list[str] | tuple[str, ...] | None,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> dict[str, str]:
    """Resolve evaluation text without exposing denied or substituted chunks.

    Enforced callers must provide an investigation authority and an explicit,
    bounded set of candidate IDs.  The legacy all-chunks projection remains
    centralized here solely for the offline harness compatibility window.
    """
    if enforce:
        if not isinstance(authority, InvestigationAuthority) or not chunk_ids:
            return {}
        resolved: dict[str, str] = {}
        for chunk_id in dict.fromkeys(str(value) for value in chunk_ids):
            try:
                chunk = read_chunk(con, authority, chunk_id)
            except LegalPolicyDenied:
                continue
            resolved[chunk_id] = str(chunk["text"])
        return resolved
    if chunk_ids:
        ids = list(dict.fromkeys(str(value) for value in chunk_ids))
        placeholders = ",".join("?" for _ in ids)
        rows = con.execute(
            f"SELECT chunk_id, text FROM chunks WHERE chunk_id IN ({placeholders})",
            ids,
        ).fetchall()
    else:
        rows = con.execute("SELECT chunk_id, text FROM chunks").fetchall()
    return {
        str(chunk_id): str(chunk_text)
        for chunk_id, chunk_text in rows
        if chunk_text is not None
    }


def list_documents_compatibility(
    con: Any,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
    source_tier: int | None,
    investigation_id: str | None,
    limit: int,
) -> tuple[tuple[Any, ...], ...]:
    """List document projections without preloading denied rows in strict mode."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return ()
        rows: list[tuple[Any, ...]] = []
        for document_id in readable_document_ids(con, authority):
            try:
                document = read_document(con, authority, document_id)
            except LegalPolicyDenied:
                continue
            if source_tier is not None and int(document["source_tier"]) != source_tier:
                continue
            if investigation_id is not None and document["investigation_id"] != investigation_id:
                continue
            rows.append(
                (
                    document_id,
                    document["title"],
                    document["source_uri"],
                    document["document_type"],
                    document["source_tier"],
                    document["investigation_id"],
                    document["content_class"],
                    document["ip_holder_id"],
                )
            )
        return tuple(sorted(rows, key=lambda row: str(row[0]), reverse=True)[:limit])
    clauses: list[str] = []
    params: list[Any] = []
    if source_tier is not None:
        clauses.append("source_tier = ?")
        params.append(source_tier)
    if investigation_id is not None:
        clauses.append("investigation_id = ?")
        params.append(investigation_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)
    return tuple(
        con.execute(
            "SELECT document_id, title, source_uri, document_type, source_tier, "
            "investigation_id, content_class, ip_holder_id FROM documents"
            + where
            + " ORDER BY document_id DESC LIMIT ?",
            params,
        ).fetchall()
    )


def list_document_metadata_compatibility(
    con: Any,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[tuple[str, Any], ...]:
    """Project document ids plus metadata through the audited migration seam.

    This supports metadata-only acquisition rows that predate legal admission.
    Strict callers receive only fully readable documents; the unenforced branch
    remains centralized here so corpus scanners cannot grow raw custody reads.
    """
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return ()
        rows: list[tuple[str, Any]] = []
        for document_id in readable_document_ids(con, authority):
            try:
                document = read_document(con, authority, document_id)
            except LegalPolicyDenied:
                continue
            rows.append((document_id, document["metadata"]))
        return tuple(rows)
    return tuple(con.execute("SELECT document_id, metadata FROM documents").fetchall())


def search_block_projections_compatibility(
    con: Any,
    *,
    like: str,
    limit: int,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[tuple[Any, ...], ...]:
    """Search palette projections without joining denied document metadata."""
    if not enforce:
        return tuple(
            con.execute(
                "SELECT n.node_id, n.canonical_label, n.node_type, n.metadata, "
                "d.title, d.source_tier, d.document_id, NULL FROM nodes n "
                "LEFT JOIN chunks c ON CAST(json_extract_string(n.metadata, '$.chunk_id') "
                "AS VARCHAR) = c.chunk_id "
                "LEFT JOIN documents d ON c.document_id = d.document_id "
                "WHERE n.canonical_label ILIKE ? ORDER BY n.created_at DESC LIMIT ?",
                [like, limit],
            ).fetchall()
        )
    if not isinstance(authority, InvestigationAuthority):
        return ()
    candidates = con.execute(
        "SELECT n.node_id, n.canonical_label, n.node_type, n.metadata, m.role "
        "FROM nodes n JOIN investigation_node_memberships m ON n.node_id = m.node_id "
        "WHERE n.canonical_label ILIKE ? AND m.account_digest = ? "
        "AND m.investigation_digest = ? ORDER BY n.created_at DESC LIMIT ?",
        [like, authority.account_digest, authority.investigation_digest, limit],
    ).fetchall()
    import json

    visible: list[tuple[Any, ...]] = []
    for node_id, label, node_type, metadata, role in candidates:
        try:
            parsed = json.loads(metadata) if isinstance(metadata, str) else metadata or {}
        except (TypeError, ValueError):
            parsed = {}
        chunk_id = parsed.get("chunk_id") if isinstance(parsed, dict) else None
        document_id = None
        if chunk_id:
            chunk_row = con.execute(
                "SELECT document_id FROM chunks WHERE chunk_id = ?", [str(chunk_id)]
            ).fetchone()
            document_id = str(chunk_row[0]) if chunk_row is not None else None
        if document_id is None:
            if role == "note":
                visible.append((node_id, label, node_type, metadata, None, None, None, role))
            continue
        try:
            document = read_document(con, authority, document_id)
        except LegalPolicyDenied:
            continue
        visible.append(
            (
                node_id,
                label,
                node_type,
                metadata,
                document["title"],
                document["source_tier"],
                document_id,
                role,
            )
        )
    return tuple(visible)


def resolve_asset_gates_compatibility(
    con: Any,
    asset_ids: set[str],
    *,
    authorities: dict[str, InvestigationAuthority],
    enforce: bool,
) -> dict[str, tuple[str | None, str | None]]:
    """Resolve monetization gate metadata only for readable assets."""
    if enforce:
        result: dict[str, tuple[str | None, str | None]] = {}
        for asset_id in sorted(asset_ids):
            authority = authorities.get(asset_id)
            if authority is None:
                continue
            try:
                document = read_document(con, authority, asset_id)
            except LegalPolicyDenied:
                continue
            result[asset_id] = (document["content_class"], document["ip_holder_id"])
        return result
    if not asset_ids:
        return {}
    placeholders = ",".join("?" for _ in asset_ids)
    rows = con.execute(
        f"SELECT document_id, content_class, ip_holder_id FROM documents "
        f"WHERE document_id IN ({placeholders})",
        sorted(asset_ids),
    ).fetchall()
    return {r[0]: (r[1], r[2]) for r in rows}


def read_legacy_chunk_text(con: Any, chunk_id: str) -> str | None:
    """Compatibility-only scalar for handlers disabled under enforcement."""
    row = con.execute("SELECT text FROM chunks WHERE chunk_id = ?", [chunk_id]).fetchone()
    return str(row[0]) if row is not None and row[0] is not None else None


def knowledge_unit_source_compatibility(
    con: Any,
    document_id: str,
    chunk_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[str | None, str | None]:
    """Return rights class and exact evidence text for a projected unit."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return None, None
        try:
            document = read_document(con, authority, document_id)
            chunk = read_chunk(con, authority, chunk_id)
        except LegalPolicyDenied:
            return None, None
        if chunk["document_id"] != document_id:
            return None, None
        return document["content_class"], str(chunk["text"])
    document = con.execute(
        "SELECT content_class FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    chunk = con.execute(
        "SELECT text FROM chunks WHERE chunk_id = ? LIMIT 1", [chunk_id]
    ).fetchone()
    return (
        str(document[0]) if document is not None and document[0] else None,
        str(chunk[0]) if chunk is not None and chunk[0] is not None else None,
    )


def book_serve_document_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> dict[str, Any] | None:
    """Resolve book-serving fields only after the document read is admitted."""
    document = read_document_compatibility(
        con, document_id, authority=authority, enforce=enforce
    )
    if document is None:
        return None
    book = con.execute(
        "SELECT COALESCE(taken_down, FALSE), COALESCE(page_count, 0), toc_json "
        "FROM book_assets WHERE document_id = ?",
        [document_id],
    ).fetchone()
    return {
        **document,
        "book_registered": book is not None,
        "taken_down": bool(book[0]) if book is not None else False,
        "page_count": int(book[1]) if book is not None else 0,
        "toc_json": book[2] if book is not None else None,
    }


def book_asset_rows_compatibility(
    con: Any,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
    document_id: str | None = None,
    servable_only: bool = False,
    include_taken_down: bool = False,
    limit: int = 200,
) -> list[tuple[Any, ...]]:
    """Project book metadata without joining unadmitted document rows."""
    book_columns = (
        "document_id, page_count, pagination_scheme, cover_uri, toc_json, "
        "provenance, license_basis, taken_down, taken_down_at, takedown_reason, "
        "pre_takedown_content_class"
    )
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return []
        sql = f"SELECT {book_columns} FROM book_assets"
        params: list[Any] = []
        clauses: list[str] = []
        if document_id is not None:
            clauses.append("document_id = ?")
            params.append(document_id)
        if not include_taken_down:
            clauses.append("taken_down = FALSE")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(1 if document_id is not None else int(limit))
        rows = con.execute(sql, params).fetchall()
        from substrate.constants import SERVABLE_CONTENT_CLASSES

        projected: list[tuple[Any, ...]] = []
        for row in rows:
            try:
                document = read_document(con, authority, str(row[0]))
            except LegalPolicyDenied:
                continue
            if servable_only and document["content_class"] not in SERVABLE_CONTENT_CLASSES:
                continue
            projected.append(
                (
                    row[0],
                    document["title"],
                    document["author"],
                    document["content_class"],
                    document["ip_holder_id"],
                    *row[1:],
                )
            )
        return projected
    sql = (
        "SELECT b.document_id, d.title, d.author, d.content_class, d.ip_holder_id, "
        "b.page_count, b.pagination_scheme, b.cover_uri, b.toc_json, b.provenance, "
        "b.license_basis, b.taken_down, b.taken_down_at, b.takedown_reason, "
        "b.pre_takedown_content_class FROM book_assets b "
        "JOIN documents d ON b.document_id = d.document_id"
    )
    clauses = []
    params = []
    if document_id is not None:
        clauses.append("b.document_id = ?")
        params.append(document_id)
    if not include_taken_down:
        clauses.append("b.taken_down = FALSE")
    if servable_only:
        from substrate.constants import SERVABLE_CONTENT_CLASSES

        placeholders = ",".join("?" for _ in SERVABLE_CONTENT_CLASSES)
        clauses.append(f"d.content_class IN ({placeholders})")
        params.extend(sorted(SERVABLE_CONTENT_CLASSES))
        clauses.append("b.taken_down = FALSE")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY b.created_at DESC LIMIT ?"
    params.append(1 if document_id is not None else int(limit))
    return con.execute(sql, params).fetchall()


def attribution_sources_compatibility(
    con: Any,
    chunk_ids: set[str],
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Resolve cited chunk ownership and attribution metadata legally."""
    if not chunk_ids:
        return {}, {}
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return {}, {}
        chunk_to_document: dict[str, str] = {}
        documents: dict[str, dict[str, Any]] = {}
        for chunk_id in sorted(chunk_ids):
            try:
                chunk = read_chunk(con, authority, chunk_id)
                document_id = str(chunk["document_id"])
                document = documents.get(document_id) or read_document(
                    con, authority, document_id
                )
            except LegalPolicyDenied:
                continue
            chunk_to_document[chunk_id] = document_id
            documents[document_id] = document
        return chunk_to_document, documents
    placeholders = ",".join("?" for _ in chunk_ids)
    chunk_rows = con.execute(
        f"SELECT chunk_id, document_id FROM chunks WHERE chunk_id IN ({placeholders})",
        sorted(chunk_ids),
    ).fetchall()
    chunk_to_document = {str(row[0]): str(row[1]) for row in chunk_rows}
    document_ids = sorted(set(chunk_to_document.values()))
    if not document_ids:
        return chunk_to_document, {}
    placeholders = ",".join("?" for _ in document_ids)
    document_rows = con.execute(
        f"SELECT document_id, source_tier, title, content_class, ip_holder_id "
        f"FROM documents WHERE document_id IN ({placeholders})",
        document_ids,
    ).fetchall()
    return chunk_to_document, {
        str(row[0]): {
            "document_id": str(row[0]),
            "source_tier": row[1],
            "title": row[2],
            "content_class": row[3],
            "ip_holder_id": row[4],
        }
        for row in document_rows
    }


def archive_document_ids_compatibility(
    con: Any,
    ids: tuple[str, ...],
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> set[str]:
    """Resolve archive document identities through the active read policy."""
    if not ids:
        return set()
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return set()
        return set(readable_document_ids(con, authority, candidate_ids=ids))
    placeholders = ",".join("?" for _ in ids)
    params: list[Any] = list(ids)
    sql = f"SELECT document_id FROM documents WHERE document_id IN ({placeholders})"
    if isinstance(authority, InvestigationAuthority):
        from substrate.constants import SERVABLE_CONTENT_CLASSES

        classes = sorted(SERVABLE_CONTENT_CLASSES - {"user_owned"})
        class_placeholders = ",".join("?" for _ in classes)
        sql += f" AND (owner_user_id = ? OR content_class IN ({class_placeholders}))"
        params.extend([authority.account_id, *classes])
    return {str(row[0]) for row in con.execute(sql, params).fetchall()}


def archive_chunk_ids_compatibility(
    con: Any,
    ids: tuple[str, ...],
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> set[str]:
    """Resolve archive chunk identities, preserving exact admitted manifests."""
    if not ids:
        return set()
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return set()
        admitted: set[str] = set()
        for chunk_id in ids:
            try:
                read_chunk(con, authority, chunk_id)
            except LegalPolicyDenied:
                continue
            admitted.add(chunk_id)
        return admitted
    placeholders = ",".join("?" for _ in ids)
    rows = con.execute(
        f"SELECT chunk_id, document_id FROM chunks WHERE chunk_id IN ({placeholders})",
        list(ids),
    ).fetchall()
    if not isinstance(authority, InvestigationAuthority):
        return {str(row[0]) for row in rows}
    documents = archive_document_ids_compatibility(
        con,
        tuple(str(row[1]) for row in rows),
        authority=authority,
        enforce=False,
    )
    return {str(row[0]) for row in rows if str(row[1]) in documents}


def archive_node_provenance_compatibility(
    con: Any,
    node_ids: tuple[str, ...],
    *,
    authority: InvestigationAuthority,
    enforce: bool,
) -> dict[str, set[str]]:
    """Resolve node provenance documents, filtering every strict source read."""
    if not node_ids:
        return {}
    placeholders = ",".join("?" for _ in node_ids)
    rows = con.execute(
        "SELECT n.node_id, c.document_id FROM nodes n JOIN chunks c ON "
        "c.chunk_id = json_extract_string(n.metadata, '$.chunk_id') "
        f"WHERE n.node_id IN ({placeholders}) UNION ALL "
        "SELECT n.node_id, e.source_document_id FROM nodes n JOIN edges e ON "
        "(e.source_node_id = n.node_id OR e.target_node_id = n.node_id) "
        f"WHERE n.node_id IN ({placeholders}) AND e.source_document_id IS NOT NULL "
        "UNION ALL SELECT n.node_id, c.document_id FROM nodes n JOIN edges e ON "
        "(e.source_node_id = n.node_id OR e.target_node_id = n.node_id) "
        "JOIN chunks c ON c.chunk_id = e.chunk_id "
        f"WHERE n.node_id IN ({placeholders})",
        [*node_ids, *node_ids, *node_ids],
    ).fetchall()
    documents_by_node: dict[str, set[str]] = {}
    for node_id, document_id in rows:
        if document_id is None:
            continue
        if enforce:
            try:
                read_document(con, authority, str(document_id))
            except LegalPolicyDenied:
                continue
        documents_by_node.setdefault(str(node_id), set()).add(str(document_id))
    return documents_by_node


def keyword_search_chunks_compatibility(
    con: Any,
    keywords: list[str],
    *,
    top_k: int,
    authority: InvestigationAuthority | None,
    enforce: bool,
    legacy_policy_tag: str,
) -> list[dict[str, Any]]:
    """Lexical prompt retrieval with exact chunk validation in strict mode."""
    if not keywords:
        return []
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return []
        hits: list[dict[str, Any]] = []
        for document_id in readable_document_ids(con, authority):
            try:
                document = read_document(con, authority, document_id)
                chunks = read_chunks(con, authority, document_id)
            except LegalPolicyDenied:
                continue
            for chunk in chunks:
                lowered = chunk["text"].lower()
                hit_count = sum(keyword in lowered for keyword in keywords)
                if not hit_count:
                    continue
                hits.append(
                    {
                        **chunk,
                        "chunk_text": chunk["text"],
                        "document_title": document["title"],
                        "source_tier": document["source_tier"],
                        "document_type": document["document_type"],
                        "hit_count": hit_count,
                    }
                )
        hits.sort(
            key=lambda item: (
                -int(item["hit_count"]),
                int(item["source_tier"]),
                -int(item["token_count"]),
                str(item["chunk_id"]),
            )
        )
        return hits[:top_k]
    from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause

    where = " OR ".join(["LOWER(c.text) LIKE ?" for _ in keywords])
    params = [f"%{keyword}%" for keyword in keywords]
    score_expr = " + ".join(
        ["(CASE WHEN LOWER(c.text) LIKE ? THEN 1 ELSE 0 END)" for _ in keywords]
    )
    gate_sql, gate_params = non_privileged_chunk_sql_clause(
        table_alias="d", policy_tag=legacy_policy_tag
    )
    rows = con.execute(
        f"SELECT c.chunk_id, c.section_path, c.text, c.token_count, d.title, "
        f"d.source_tier, d.document_type, ({score_expr}) AS hit_count "
        f"FROM chunks c JOIN documents d ON c.document_id = d.document_id "
        f"WHERE ({where}){gate_sql} ORDER BY hit_count DESC, d.source_tier ASC, "
        f"c.token_count DESC LIMIT ?",
        params + params + gate_params + [top_k],
    ).fetchall()
    columns = (
        "chunk_id",
        "section_path",
        "chunk_text",
        "token_count",
        "document_title",
        "source_tier",
        "document_type",
        "hit_count",
    )
    return [dict(zip(columns, row, strict=True)) for row in rows]


def select_substantive_chunk_compatibility(
    con: Any,
    document_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> str | None:
    """Choose a substantive grounding chunk, validating its manifest strictly."""
    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return None
        try:
            chunks = read_chunks(con, authority, document_id)
        except LegalPolicyDenied:
            return None
        eligible = [
            chunk
            for chunk in chunks
            if 400 <= len(chunk["text"]) <= 4000
            and all(
                marker not in chunk["text"].lower()
                for marker in ("bibliography", "references", "index")
            )
            and not chunk["text"].lower().startswith(("## page", "chapter ", "contents"))
        ]
        eligible.sort(key=lambda chunk: (-len(chunk["text"]), str(chunk["chunk_id"])))
        return str(eligible[0]["chunk_id"]) if eligible else None
    row = con.execute(
        "SELECT chunk_id FROM chunks WHERE document_id = ? "
        "AND length(text) BETWEEN 400 AND 4000 "
        "AND text NOT ILIKE '%bibliography%' AND text NOT ILIKE '%references%' "
        "AND text NOT ILIKE '%index%' AND text NOT ILIKE '## Page%' "
        "AND text NOT ILIKE 'chapter %' AND text NOT ILIKE 'contents%' "
        "ORDER BY length(text) DESC LIMIT 1",
        [document_id],
    ).fetchone()
    return str(row[0]) if row is not None and row[0] is not None else None


def validate_cited_chunk_compatibility(
    con: Any,
    *,
    chunk_id: str,
    document_id: str,
    content_sha256: str,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> str:
    """Return ``valid``, ``missing``, or ``invalid`` for a cited chunk."""
    import hashlib

    if enforce:
        if not isinstance(authority, InvestigationAuthority):
            return "invalid"
        try:
            item = read_chunk(con, authority, chunk_id)
        except LegalPolicyDenied:
            return "invalid"
        if item["document_id"] != document_id:
            return "invalid"
        text = item["text"]
    else:
        row = con.execute(
            "SELECT text FROM chunks WHERE chunk_id = ? AND document_id = ? LIMIT 1",
            [chunk_id, document_id],
        ).fetchone()
        if row is None:
            return "missing"
        text = str(row[0])
    return (
        "valid"
        if len(content_sha256) == 64
        and hashlib.sha256(str(text).encode("utf-8")).hexdigest() == content_sha256
        else "invalid"
    )


def legacy_knowledge_reuse_rows(
    con: Any, *, similarity_sql: str, limit: int
) -> list[tuple[Any, ...]]:
    """Compatibility-only global reuse scan, centralized for Sprint 4 removal."""
    return con.execute(
        f"SELECT node_id, content_class_of_unit.content_class, "
        f"content_class_of_unit.taken_down, similarity FROM ("
        f"SELECT node_id, {similarity_sql} AS similarity FROM nodes "
        f"WHERE node_type IN ('insight', 'question') AND embedding IS NOT NULL "
        f"ORDER BY similarity DESC, node_id ASC LIMIT ?) AS ranked LEFT JOIN ("
        f"SELECT e.source_node_id AS nid, d.content_class, "
        f"COALESCE(b.taken_down, FALSE) AS taken_down FROM edges e "
        f"JOIN documents d ON e.source_document_id = d.document_id "
        f"LEFT JOIN book_assets b ON d.document_id = b.document_id "
        f"WHERE e.relation = 'supported_by' AND e.source_document_id IS NOT NULL"
        f") AS content_class_of_unit ON ranked.node_id = content_class_of_unit.nid",
        [limit],
    ).fetchall()


def legacy_monitor_titles(con: Any, document_ids: list[str]) -> list[tuple[Any, ...]]:
    placeholders = ",".join("?" for _ in document_ids)
    return con.execute(
        f"SELECT title FROM documents WHERE document_id IN ({placeholders})",
        document_ids,
    ).fetchall()


def legacy_monitor_embeddings(
    con: Any, document_ids: list[str]
) -> list[tuple[Any, ...]]:
    placeholders = ",".join("?" for _ in document_ids)
    return con.execute(
        f"SELECT embedding FROM chunks WHERE document_id IN ({placeholders}) "
        f"AND embedding IS NOT NULL",
        document_ids,
    ).fetchall()


def legacy_monitor_items(
    con: Any,
    *,
    last_seen_at: str,
    centroid: list[float] | None,
    centroid_dim: int | None,
    content_class: str,
    top_k: int,
) -> list[tuple[Any, ...]]:
    if centroid is not None and centroid_dim:
        from substrate.graph.search import cosine_similarity_sql

        similarity = cosine_similarity_sql("c.embedding", centroid, centroid_dim)
        return con.execute(
            f"SELECT d.document_id, d.title, d.raw_text, d.acquired_at, "
            f"MAX({similarity}) AS similarity FROM documents d JOIN chunks c "
            f"ON c.document_id = d.document_id WHERE d.content_class = ? "
            f"AND d.acquired_at > ? AND c.embedding IS NOT NULL GROUP BY "
            f"d.document_id, d.title, d.raw_text, d.acquired_at "
            f"ORDER BY similarity DESC LIMIT ?",
            [content_class, last_seen_at, top_k],
        ).fetchall()
    return con.execute(
        "SELECT document_id, title, raw_text, acquired_at, NULL FROM documents "
        "WHERE content_class = ? AND acquired_at > ? "
        "ORDER BY acquired_at DESC LIMIT ?",
        [content_class, last_seen_at, top_k],
    ).fetchall()


def graph_edge_projections_compatibility(
    con: Any,
    *,
    where_sql: str,
    params: list[Any],
    limit: int,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> list[tuple[Any, ...]]:
    """Resolve graph edges; strict mode never preloads denied evidence bytes."""
    if not enforce:
        return con.execute(
            "SELECT e.edge_id, e.source_node_id, sn.canonical_label, "
            "e.target_node_id, tn.canonical_label, e.relation, e.graph_scope, "
            "e.investigation_id, e.extraction_confidence, e.valid_from, "
            "e.valid_until, e.chunk_id, c.text, c.section_path, "
            "COALESCE(c.document_id, e.source_document_id), d.title, d.author, "
            "e.source_tier, d.content_class, d.ip_holder_id FROM edges e "
            "JOIN nodes sn ON sn.node_id = e.source_node_id "
            "JOIN nodes tn ON tn.node_id = e.target_node_id "
            "LEFT JOIN chunks c ON c.chunk_id = e.chunk_id "
            "LEFT JOIN documents d ON d.document_id = "
            "COALESCE(c.document_id, e.source_document_id) WHERE "
            + where_sql
            + " ORDER BY e.extraction_confidence DESC, e.extracted_at DESC LIMIT ?",
            [*params, limit],
        ).fetchall()
    if not isinstance(authority, InvestigationAuthority):
        return []
    base_rows = con.execute(
        "SELECT e.edge_id, e.source_node_id, sn.canonical_label, "
        "e.target_node_id, tn.canonical_label, e.relation, e.graph_scope, "
        "e.investigation_id, e.extraction_confidence, e.valid_from, "
        "e.valid_until, e.chunk_id, e.source_document_id, e.source_tier "
        "FROM edges e JOIN nodes sn ON sn.node_id = e.source_node_id "
        "JOIN nodes tn ON tn.node_id = e.target_node_id WHERE "
        + where_sql
        + " ORDER BY e.extraction_confidence DESC, e.extracted_at DESC LIMIT ?",
        [*params, limit],
    ).fetchall()
    result: list[tuple[Any, ...]] = []
    for row in base_rows:
        chunk = None
        document = None
        if row[11] is not None:
            try:
                chunk = read_chunk(con, authority, str(row[11]))
                document = read_document(con, authority, str(chunk["document_id"]))
            except LegalPolicyDenied:
                continue
            if row[12] is not None and str(row[12]) != document["document_id"]:
                continue
        elif row[12] is not None:
            try:
                document = read_document(con, authority, str(row[12]))
            except LegalPolicyDenied:
                continue
        result.append(
            (
                *row[:12],
                None if chunk is None else chunk["text"],
                None if chunk is None else chunk["section_path"],
                None if document is None else document["document_id"],
                None if document is None else document["title"],
                None if document is None else document["author"],
                row[13],
                None if document is None else document["content_class"],
                None if document is None else document["ip_holder_id"],
            )
        )
    return result


def document_exists_for_owner_compatibility(
    con: Any,
    document_id: str,
    *,
    owner_user_id: str,
    enforce: bool,
) -> bool:
    """Resolve canonical-source existence without exposing foreign metadata."""
    if enforce:
        investigation_id = document_investigation_hint(con, document_id)
        if not investigation_id:
            return False
        authority = InvestigationAuthority(owner_user_id, investigation_id)
        try:
            read_document(con, authority, document_id)
        except LegalPolicyDenied:
            return False
        return True
    return (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? AND "
            "(owner_user_id IS NULL OR owner_user_id = ?)",
            [document_id, owner_user_id],
        ).fetchone()
        is not None
    )


def legacy_research_paste_row(con: Any, document_id: str) -> tuple[Any, ...] | None:
    return con.execute(
        "SELECT rp.document_id, rp.source, rp.raw_sha256, d.raw_text "
        "FROM research_pastes rp JOIN documents d ON d.document_id = rp.document_id "
        "WHERE rp.document_id = ?",
        [document_id],
    ).fetchone()


def legacy_document_exists(con: Any, document_id: str) -> bool:
    return (
        con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1", [document_id]
        ).fetchone()
        is not None
    )


def legacy_version_document_row(con: Any, document_id: str) -> tuple[Any, ...] | None:
    return con.execute(
        "SELECT document_type, source_tier, source_uri, title, raw_text, "
        "investigation_id, ip_holder_id, content_class, metadata "
        "FROM documents WHERE document_id = ?",
        [document_id],
    ).fetchone()


def legacy_document_version_rows(con: Any, root: str) -> list[tuple[Any, ...]]:
    return con.execute(
        "SELECT document_id, metadata FROM documents "
        "WHERE document_id = ? OR metadata LIKE ?",
        [root, f'%"version_root": "{root}"%'],
    ).fetchall()


def legacy_chunk_document_projection(con: Any, chunk_id: str) -> tuple[Any, ...] | None:
    return con.execute(
        "SELECT c.document_id, d.title, d.source_tier FROM chunks c "
        "LEFT JOIN documents d ON c.document_id = d.document_id "
        "WHERE c.chunk_id = ? LIMIT 1",
        [chunk_id],
    ).fetchone()


def legacy_document_title_tier(con: Any, document_id: str) -> tuple[Any, ...] | None:
    return con.execute(
        "SELECT title, source_tier FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()


def legacy_chunk_document_id(con: Any, chunk_id: str) -> str | None:
    row = con.execute(
        "SELECT document_id FROM chunks WHERE chunk_id = ?", [chunk_id]
    ).fetchone()
    return str(row[0]) if row is not None and row[0] is not None else None


def legacy_document_content_class(con: Any, document_id: str) -> str | None:
    row = con.execute(
        "SELECT content_class FROM documents WHERE document_id = ?", [document_id]
    ).fetchone()
    return str(row[0]) if row is not None and row[0] is not None else None


def legacy_speak_public_feed(con: Any) -> list[tuple[Any, ...]]:
    return con.execute(
        "SELECT p.project_id, ip.title, p.subject_ref, p.subject_status, "
        "p.invitation_mode, (SELECT count(*) FROM interviews i "
        "WHERE i.project_id = p.project_id), "
        "(SELECT arg_max(d.document_id, sp.published_at) FROM documents d "
        "JOIN book_assets b ON b.document_id = d.document_id "
        "JOIN speak_publications sp ON sp.publication_id = "
        "json_extract_string(d.metadata, '$.publication_id') "
        "WHERE sp.project_id = p.project_id AND sp.served = TRUE "
        "AND sp.taken_down = FALSE AND json_extract_string(" 
        "d.metadata, '$.provenance_class') = 'speak_derived' "
        "AND COALESCE(b.taken_down, FALSE) = FALSE) FROM speak_projects p "
        "JOIN interview_projects ip ON ip.project_id = p.project_id "
        "WHERE p.publish_intent = 'will_be_public' ORDER BY p.created_at DESC"
    ).fetchall()


def legacy_notebook_chunk_tiers(con: Any, chunk_ids: list[str]) -> list[int]:
    placeholders = ", ".join("?" for _ in chunk_ids)
    return [
        int(row[0])
        for row in con.execute(
            f"SELECT d.source_tier FROM chunks c JOIN documents d "
            f"ON d.document_id = c.document_id WHERE c.chunk_id IN ({placeholders})",
            chunk_ids,
        ).fetchall()
    ]


def legacy_public_graph_source_tiers(
    con: Any, chunk_ids: tuple[str, ...]
) -> dict[str, int | None]:
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = con.execute(
        f"SELECT c.chunk_id, d.source_tier FROM chunks c LEFT JOIN documents d "
        f"ON d.document_id = c.document_id WHERE c.chunk_id IN ({placeholders})",
        list(chunk_ids),
    ).fetchall()
    return {
        str(chunk_id): int(tier) if tier is not None else None
        for chunk_id, tier in rows
    }


def read_synthesis_manifest_chunks(
    con: Any,
    synthesis_id: str,
    *,
    authority: InvestigationAuthority | None,
    enforce: bool,
) -> tuple[tuple[Any, ...], ...]:
    """Resolve synthesis sources without preloading forbidden document bytes.

    The compatibility branch is deliberately centralized here while historic
    fixtures are migrated. Under enforcement, only manifest identifiers are
    selected first; every chunk and its document metadata then comes through
    the receipt-, owner-, and policy-aware read functions above.
    """
    if not enforce:
        return tuple(
            con.execute(
                "SELECT m.entity_id, c.document_id, d.title, d.content_class, "
                "d.ip_holder_id, c.text, COALESCE(b.taken_down, FALSE) "
                "FROM synthesis_substrate_manifest m "
                "JOIN chunks c ON c.chunk_id = m.entity_id "
                "JOIN documents d ON d.document_id = c.document_id "
                "LEFT JOIN book_assets b ON b.document_id = d.document_id "
                "WHERE m.synthesis_id = ? AND m.entity_kind = 'chunk' "
                "ORDER BY m.entity_id",
                [synthesis_id],
            ).fetchall()
        )
    if not isinstance(authority, InvestigationAuthority):
        return ()
    manifest_rows = con.execute(
        "SELECT entity_id FROM synthesis_substrate_manifest "
        "WHERE synthesis_id = ? AND entity_kind = 'chunk' ORDER BY entity_id",
        [synthesis_id],
    ).fetchall()
    resolved: list[tuple[Any, ...]] = []
    for (chunk_id,) in manifest_rows:
        try:
            chunk = read_chunk(con, authority, str(chunk_id))
            document = read_document(con, authority, str(chunk["document_id"]))
        except LegalPolicyDenied:
            continue
        book = con.execute(
            "SELECT COALESCE(taken_down, FALSE) FROM book_assets WHERE document_id = ?",
            [document["document_id"]],
        ).fetchone()
        resolved.append(
            (
                chunk["chunk_id"],
                document["document_id"],
                document["title"],
                document["content_class"],
                document["ip_holder_id"],
                chunk["text"],
                bool(book[0]) if book is not None else False,
            )
        )
    return tuple(resolved)
