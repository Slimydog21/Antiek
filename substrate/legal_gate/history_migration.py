"""Conservative, explicit-claim migration for legacy document custody."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from runtime.db_lock import LockedConnection
from substrate.graph.ops import seal_existing_admitted_state
from substrate.investigation_streams import resolve_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority

from .admission import ProvenanceClass, admit_staged_document
from .policy_store import account_policy_authority


@dataclass(frozen=True)
class LegacyDocumentClaim:
    document_id: str
    provenance_class: ProvenanceClass
    citation_ref: str
    canonical_url: str = ""
    title: str = ""
    author: str = ""
    source_corpus: str = ""


@dataclass(frozen=True)
class MigrationCensus:
    run_id: str
    candidate_count: int
    admitted_count: int
    quarantined_count: int
    state: Literal["dry_run", "completed", "rolled_back"]


def _claims_payload(claims: tuple[LegacyDocumentClaim, ...]) -> str:
    rows = [
        {
            "document_id": claim.document_id,
            "provenance_class": claim.provenance_class,
            "citation_digest": hashlib.sha256(claim.citation_ref.encode()).hexdigest(),
            "canonical_url_digest": hashlib.sha256(claim.canonical_url.encode()).hexdigest(),
            "title_digest": hashlib.sha256(claim.title.encode()).hexdigest(),
            "author_digest": hashlib.sha256(claim.author.encode()).hexdigest(),
            "source_corpus": claim.source_corpus,
        }
        for claim in sorted(claims, key=lambda item: item.document_id)
    ]
    return json.dumps(rows, sort_keys=True, separators=(",", ":"))


def _identity(authority: InvestigationAuthority, claims: tuple[LegacyDocumentClaim, ...]):
    claim_hash = hashlib.sha256(_claims_payload(claims).encode()).hexdigest()
    run_hash = hashlib.sha256(
        f"{authority.account_digest}\0{authority.investigation_digest}\0{claim_hash}".encode()
    ).hexdigest()
    return f"lhm-{run_hash[:32]}", claim_hash


def _candidates(con: LockedConnection, authority: InvestigationAuthority):
    return con.execute(
        "SELECT document_id, raw_text, source_uri, title, author, document_type "
        "FROM documents WHERE investigation_id = ? "
        "AND (owner_user_id IS NULL OR owner_user_id = ?) ORDER BY document_id",
        [authority.investigation_id, authority.account_id],
    ).fetchall()


def migrate_legacy_documents(
    con: LockedConnection,
    authority: InvestigationAuthority,
    *,
    claims: tuple[LegacyDocumentClaim, ...] = (),
    apply: bool = False,
    at: datetime | None = None,
) -> MigrationCensus:
    """Quarantine unknown history; admit only exact, cited operator claims."""
    if not isinstance(con, LockedConnection):
        raise TypeError("legal history migration requires LockedConnection")
    resolve_investigation_stream(authority)
    if len({claim.document_id for claim in claims}) != len(claims):
        raise ValueError("legacy document claims must be unique")
    if any(not claim.citation_ref.strip() for claim in claims):
        raise ValueError("legacy document claims require a citation")
    run_id, claim_hash = _identity(authority, claims)
    candidates = _candidates(con, authority)
    claim_by_id = {claim.document_id: claim for claim in claims}
    admitted = 0
    quarantined = 0
    if not apply:
        for document_id, raw_text, *_ in candidates:
            claim = claim_by_id.get(document_id)
            if claim is None or not isinstance(raw_text, str):
                quarantined += 1
            elif claim.provenance_class == "external_network":
                quarantined += 1  # dry-run cannot overclaim a policy verdict
            else:
                admitted += 1
        return MigrationCensus(run_id, len(candidates), admitted, quarantined, "dry_run")

    migration_at = (at or datetime.now(UTC)).astimezone(UTC)
    existing_run = con.execute(
        "SELECT claim_set_sha256, state, admitted_count, quarantined_count "
        "FROM legal_history_migration_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if existing_run is not None:
        if existing_run[0] != claim_hash:
            raise RuntimeError("legacy migration identity collision")
        if existing_run[1] == "completed":
            return MigrationCensus(
                run_id, len(candidates), int(existing_run[2]), int(existing_run[3]), "completed"
            )
        if existing_run[1] == "rolled_back":
            raise RuntimeError("rolled-back legacy migration requires a new claim set")
    else:
        con.execute(
            "INSERT INTO legal_history_migration_runs "
            "(run_id, account_digest, investigation_digest, claim_set_sha256, state, started_at) "
            "VALUES (?, ?, ?, ?, 'applying', ?)",
            [
                run_id,
                authority.account_digest,
                authority.investigation_digest,
                claim_hash,
                migration_at.isoformat(),
            ],
        )

    policy_authority = account_policy_authority(authority)
    for document_id, raw_text, source_uri, stored_title, stored_author, _document_type in candidates:
        if con.execute(
            "SELECT 1 FROM legal_history_migration_rows WHERE run_id = ? AND document_id = ?",
            [run_id, document_id],
        ).fetchone():
            continue
        claim = claim_by_id.get(document_id)
        digest = hashlib.sha256(str(raw_text or "").encode()).hexdigest()
        disposition = "quarantined"
        reason = "unknown_legacy_provenance"
        receipt_id = None
        evaluated_receipt_id = None
        receipt_created = False
        if claim is not None and isinstance(raw_text, str):
            before = set(
                row[0]
                for row in con.execute(
                    "SELECT receipt_id FROM legal_document_admissions WHERE account_digest = ? "
                    "AND investigation_digest = ? AND document_id = ?",
                    [authority.account_digest, authority.investigation_digest, document_id],
                ).fetchall()
            )
            decision = admit_staged_document(
                con,
                policy_authority,
                investigation_digest=authority.investigation_digest,
                document_id=document_id,
                provenance_class=claim.provenance_class,
                canonical_url=claim.canonical_url or str(source_uri or ""),
                title=claim.title or str(stored_title or ""),
                author=claim.author or str(stored_author or ""),
                source_corpus=claim.source_corpus,
                content_sha256=digest,
                at=migration_at,
            )
            evaluated_receipt_id = decision.receipt_id
            receipt_created = evaluated_receipt_id not in before
            if decision.decision == "allow":
                seal_existing_admitted_state(
                    con,
                    authority,
                    admission_receipt_id=decision.receipt_id,
                    admitted_content_sha256=digest,
                    document_id=document_id,
                )
                disposition = "admitted"
                reason = "explicit_cited_legacy_claim"
                receipt_id = decision.receipt_id
            else:
                reason = f"policy:{decision.reason_code or 'denied'}"
        con.execute(
            "INSERT INTO legal_history_migration_rows "
            "(run_id, account_digest, investigation_digest, document_id, "
            "source_content_sha256, requested_provenance, citation_digest, disposition, "
            "reason_code, admission_receipt_id, evaluated_receipt_id, receipt_created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                run_id,
                authority.account_digest,
                authority.investigation_digest,
                document_id,
                digest,
                None if claim is None else claim.provenance_class,
                None
                if claim is None
                else hashlib.sha256(claim.citation_ref.encode()).hexdigest(),
                disposition,
                reason,
                receipt_id,
                evaluated_receipt_id,
                receipt_created,
            ],
        )

    admitted, quarantined = con.execute(
        "SELECT count(*) FILTER (WHERE disposition = 'admitted'), "
        "count(*) FILTER (WHERE disposition = 'quarantined') "
        "FROM legal_history_migration_rows WHERE run_id = ?",
        [run_id],
    ).fetchone()
    con.execute(
        "UPDATE legal_history_migration_runs SET state = 'completed', admitted_count = ?, "
        "quarantined_count = ?, completed_at = ? WHERE run_id = ?",
        [int(admitted), int(quarantined), datetime.now(UTC).isoformat(), run_id],
    )
    return MigrationCensus(run_id, len(candidates), int(admitted), int(quarantined), "completed")


def rollback_legacy_migration(
    con: LockedConnection,
    authority: InvestigationAuthority,
    run_id: str,
) -> MigrationCensus:
    row = con.execute(
        "SELECT account_digest, investigation_digest, admitted_count, quarantined_count, state "
        "FROM legal_history_migration_runs WHERE run_id = ?",
        [run_id],
    ).fetchone()
    if row is None or row[:2] != (authority.account_digest, authority.investigation_digest):
        raise RuntimeError("legacy migration is unavailable")
    if row[4] == "rolled_back":
        return MigrationCensus(run_id, int(row[2]) + int(row[3]), 0, 0, "rolled_back")
    receipts = con.execute(
        "SELECT evaluated_receipt_id FROM legal_history_migration_rows "
        "WHERE run_id = ? AND receipt_created = TRUE AND evaluated_receipt_id IS NOT NULL",
        [run_id],
    ).fetchall()
    for (receipt_id,) in receipts:
        con.execute(
            "DELETE FROM legal_document_custody_seals WHERE receipt_id = ?",
            [receipt_id],
        )
        con.execute(
            "DELETE FROM legal_chunk_manifest_seals WHERE receipt_id = ?",
            [receipt_id],
        )
        con.execute(
            "DELETE FROM legal_chunk_admissions WHERE receipt_id = ?",
            [receipt_id],
        )
        con.execute("DELETE FROM legal_document_admissions WHERE receipt_id = ?", [receipt_id])
    con.execute("DELETE FROM legal_history_migration_rows WHERE run_id = ?", [run_id])
    con.execute(
        "UPDATE legal_history_migration_runs SET state = 'rolled_back', admitted_count = 0, "
        "quarantined_count = 0, completed_at = ? WHERE run_id = ?",
        [datetime.now(UTC).isoformat(), run_id],
    )
    return MigrationCensus(run_id, int(row[2]) + int(row[3]), 0, 0, "rolled_back")
