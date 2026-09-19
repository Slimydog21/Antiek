"""Atomic, owner-scoped legal admission receipts for staged documents."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from runtime.db_lock import LockedConnection

from .policy_store import (
    LegalPolicyAuthority,
    LegalPolicyDenied,
    evaluate_document,
    policy_snapshot,
)

ProvenanceClass = Literal["external_network", "internal_operator", "user_authored"]


@dataclass(frozen=True)
class DocumentAdmission:
    receipt_id: str
    decision: Literal["allow", "deny"]
    policy_snapshot_sha256: str
    matched_event_ids: tuple[str, ...]
    reason_code: str | None


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def chunk_manifest_seal_values(
    *,
    receipt_id: str,
    document_id: str,
    account_digest: str,
    investigation_digest: str,
    rows: list[tuple[object, ...]],
) -> tuple[int, str, str]:
    """Return deterministic count, manifest root, and owner-bound seal."""
    canonical_rows = [
        {
            "chunk_id": str(row[0]),
            "chunk_index": int(row[1]),
            "section_path": row[2],
            "token_count": int(row[3]),
            "text_sha256": str(row[4]),
        }
        for row in rows
    ]
    encoded = json.dumps(
        canonical_rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    manifest_sha256 = hashlib.sha256(encoded.encode()).hexdigest()
    seal_payload = json.dumps(
        {
            "account_digest": account_digest,
            "document_id": document_id,
            "investigation_digest": investigation_digest,
            "manifest_sha256": manifest_sha256,
            "receipt_id": receipt_id,
            "chunk_count": len(canonical_rows),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        len(canonical_rows),
        manifest_sha256,
        hashlib.sha256(seal_payload.encode()).hexdigest(),
    )


def document_custody_seal_values(
    *,
    receipt_id: str,
    document_id: str,
    account_digest: str,
    investigation_digest: str,
    state: dict[str, object],
) -> tuple[str, str]:
    """Commit immutable custody metadata without exposing it in receipts."""
    encoded = json.dumps(
        state, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )
    state_sha256 = hashlib.sha256(encoded.encode()).hexdigest()
    seal_payload = json.dumps(
        {
            "account_digest": account_digest,
            "document_id": document_id,
            "investigation_digest": investigation_digest,
            "state_sha256": state_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return state_sha256, hashlib.sha256(seal_payload.encode()).hexdigest()


def _authority_fingerprint(authority: LegalPolicyAuthority) -> str:
    fingerprint = authority.global_capability_fingerprint
    if authority.account_digest is None or fingerprint is None or len(fingerprint) != 64:
        raise LegalPolicyDenied("document admission requires authenticated account authority")
    return fingerprint


def _receipt_fingerprint(row: dict[str, str | None]) -> str:
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def admit_staged_document(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    investigation_digest: str,
    document_id: str,
    provenance_class: ProvenanceClass,
    canonical_url: str = "",
    title: str = "",
    author: str = "",
    source_corpus: str = "",
    content_sha256: str,
    at: datetime,
) -> DocumentAdmission:
    """Decide and append a receipt inside the caller's write transaction.

    External content requires an explicit account allow under the exact snapshot.
    Internal/operator and user-authored content are classified explicitly and do
    not inherit network restrictions accidentally.
    """
    if not isinstance(con, LockedConnection):
        raise TypeError("document admission requires a LockedConnection")
    authority_fingerprint = _authority_fingerprint(authority)
    digest = content_sha256.removeprefix("sha256:").lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("content_sha256 must be a full SHA-256 digest")
    if at.tzinfo is None:
        raise ValueError("admission time must be timezone-aware")

    snapshot = policy_snapshot(con, authority, at=at)
    if provenance_class == "external_network":
        verdict = evaluate_document(
            snapshot,
            url=canonical_url,
            title=title,
            author=author,
            source_corpus=source_corpus,
            content_sha256=digest,
        )
        decision: Literal["allow", "deny"] = "allow" if verdict.decision == "allow" else "deny"
        matched = verdict.matched_event_ids
        reason = verdict.reason_code or (
            "no_explicit_external_allow" if verdict.decision == "no_decision" else None
        )
    else:
        decision = "allow"
        matched = ()
        reason = provenance_class

    metadata = {
        "author": author,
        "source_corpus": source_corpus,
        "title": title,
    }
    admitted_at = at.astimezone(UTC).isoformat()
    row: dict[str, str | None] = {
        "account_digest": authority.account_digest,
        "investigation_digest": investigation_digest,
        "document_id": document_id,
        "provenance_class": provenance_class,
        "canonical_url_digest": _digest_text(canonical_url),
        "metadata_digest": _digest_text(
            json.dumps(metadata, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        ),
        "content_sha256": digest,
        "decision": decision,
        "policy_snapshot_sha256": snapshot.snapshot_sha256,
        "matched_event_ids_json": json.dumps(list(matched), separators=(",", ":")),
        "reason_code": reason,
        "authority_fingerprint": authority_fingerprint,
        "admitted_at": admitted_at,
    }
    fingerprint = _receipt_fingerprint(row)
    receipt_id = f"lda-{fingerprint[:32]}"
    existing = con.execute(
        "SELECT receipt_fingerprint FROM legal_document_admissions WHERE receipt_id = ?",
        [receipt_id],
    ).fetchone()
    if existing is not None:
        if existing != (fingerprint,):
            raise LegalPolicyDenied("legal admission receipt identity collision")
        return DocumentAdmission(receipt_id, decision, snapshot.snapshot_sha256, matched, reason)
    con.execute(
        "INSERT INTO legal_document_admissions "
        "(receipt_id, account_digest, investigation_digest, document_id, "
        "provenance_class, canonical_url_digest, metadata_digest, content_sha256, "
        "decision, policy_snapshot_sha256, matched_event_ids_json, reason_code, "
        "authority_fingerprint, admitted_at, receipt_fingerprint) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [receipt_id, *row.values(), fingerprint],
    )
    return DocumentAdmission(receipt_id, decision, snapshot.snapshot_sha256, matched, reason)


def require_allowed_receipt(
    con: LockedConnection,
    authority: LegalPolicyAuthority,
    *,
    receipt_id: str,
    document_id: str,
    investigation_digest: str,
    content_sha256: str,
) -> None:
    """Verify the complete authenticated receipt and current policy snapshot."""
    expected_content = content_sha256.removeprefix("sha256:").lower()
    authority_fingerprint = _authority_fingerprint(authority)
    row = con.execute(
        "SELECT account_digest, investigation_digest, document_id, provenance_class, "
        "canonical_url_digest, metadata_digest, content_sha256, decision, "
        "policy_snapshot_sha256, matched_event_ids_json, reason_code, "
        "authority_fingerprint, admitted_at, receipt_fingerprint "
        "FROM legal_document_admissions WHERE receipt_id = ? "
        "AND account_digest = ? AND investigation_digest = ? AND document_id = ?",
        [
            receipt_id,
            authority.account_digest,
            investigation_digest,
            document_id,
        ],
    ).fetchone()
    if row is None or row[7] != "allow" or row[6] != expected_content:
        raise LegalPolicyDenied("document has no allowed owner-scoped admission")
    fields = (
        "account_digest", "investigation_digest", "document_id", "provenance_class",
        "canonical_url_digest", "metadata_digest", "content_sha256", "decision",
        "policy_snapshot_sha256", "matched_event_ids_json", "reason_code",
        "authority_fingerprint", "admitted_at",
    )
    canonical = dict(zip(fields, row[:13], strict=True))
    fingerprint = _receipt_fingerprint(canonical)
    if row[11] != authority_fingerprint or row[13] != fingerprint:
        raise LegalPolicyDenied("legal admission receipt authentication failed")
    if receipt_id != f"lda-{fingerprint[:32]}":
        raise LegalPolicyDenied("legal admission receipt identity failed")
    admitted_at = datetime.fromisoformat(str(row[12]))
    current = policy_snapshot(con, authority, at=datetime.now(UTC))
    snapshot_stale = row[3] == "external_network" and current.snapshot_sha256 != row[8]
    if snapshot_stale or admitted_at > datetime.now(UTC):
        raise LegalPolicyDenied("legal admission receipt is stale")
