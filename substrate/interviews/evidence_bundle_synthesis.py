"""Private, budget-pinned synthesis intent over a verified Write evidence bundle.

This module deliberately has no provider or dispatch capability.  It freezes the
exact legally re-resolved prompt substrate; execution remains a separate gate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection

from .authority import InterviewAccountAuthority
from .composition_proposals import validate_proposal_inputs
from .write_acceptance import EvidenceBundleItem


class EvidenceBundleSynthesisConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class EvidenceBundleSynthesisProposal:
    proposal_id: str
    bundle_id: str
    write_document_id: str
    project_id: str
    revision: int
    base_revision: int
    source_manifest_sha256: str
    source_content_sha256: str
    source_receipt_sha256: str
    provider_id: str
    model_id: str
    projected_max_cents: int
    approved_ceiling_cents: int
    instruction: str
    state: str
    inputs: tuple[dict[str, object], ...]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _authority_receipt_sha(value: dict[str, object]) -> str:
    return _sha(_canonical({"schema_version": 1, **value}))


def _text(value: str, label: str, limit: int = 512) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > limit:
        raise ValueError(f"evidence synthesis {label} is invalid")
    return value


def _bundle_row(
    con: Any, authority: InterviewAccountAuthority, bundle_id: str
) -> tuple[Any, ...]:
    row = con.execute(
        "SELECT bundle_id, write_document_id, project_id, native_event_id, "
        "native_event_sha256, revision, item_count, manifest_sha256, receipt_sha256 "
        "FROM interview_write_evidence_bundles_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND bundle_id = ?",
        [authority.account_digest, authority.account_id, bundle_id],
    ).fetchone()
    if row is None:
        raise ValueError("evidence synthesis bundle not found")
    return tuple(row)


def _verified_inputs(
    con: Any,
    authority: InterviewAccountAuthority,
    *,
    bundle: tuple[Any, ...],
    items: tuple[EvidenceBundleItem, ...],
) -> tuple[tuple[dict[str, object], ...], str, str]:
    rows = con.execute(
        "SELECT ordinal, relationship, operator_label, citation_receipt_sha256, "
        "source_asset_id, claim_id, source_document_id, chunk_ids_json, source_title, "
        "source_content_sha256, excerpt_sha256, unit_receipt_sha256 FROM "
        "interview_write_evidence_bundle_units_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND bundle_id = ? ORDER BY ordinal",
        [authority.account_digest, authority.account_id, str(bundle[0])],
    ).fetchall()
    if len(rows) != int(bundle[6]) or len(items) != len(rows) or not 2 <= len(rows) <= 32:
        raise EvidenceBundleSynthesisConflict("evidence synthesis bundle is incomplete")
    frozen: list[dict[str, object]] = []
    for ordinal, (row, item) in enumerate(zip(rows, items, strict=True)):
        try:
            chunks = json.loads(str(row[7]))
        except json.JSONDecodeError as exc:
            raise EvidenceBundleSynthesisConflict(
                "evidence synthesis bundle unit is corrupt"
            ) from exc
        source = item.source
        receipt_value = {
            "bundle_id": str(bundle[0]), "ordinal": ordinal,
            "relationship": str(row[1]),
            "operator_label": None if row[2] is None else str(row[2]),
            "citation_receipt_sha256": str(row[3]), "source_asset_id": str(row[4]),
            "claim_id": str(row[5]), "source_document_id": str(row[6]),
            "chunk_ids": chunks, "source_title": str(row[8]),
            "source_content_sha256": str(row[9]), "excerpt_sha256": str(row[10]),
        }
        expected = (
            int(row[0]) == ordinal
            and str(row[1]) == item.relationship
            and (None if row[2] is None else str(row[2])) == item.operator_label
            and str(row[3]) == source.citation_receipt_sha256
            and str(row[4]) == source.source_asset_id
            and str(row[5]) == source.claim_id
            and str(row[6]) == source.source_document_id
            and chunks == list(source.chunk_ids)
            and str(row[8]) == source.source_title
            and str(row[9]) == source.source_content_sha256
            and str(row[10]) == _sha(source.excerpt_text)
            and _authority_receipt_sha(receipt_value) == str(row[11])
        )
        if not expected:
            raise EvidenceBundleSynthesisConflict(
                "evidence synthesis source no longer matches bundle"
            )
        frozen.append({
            "ordinal": ordinal,
            "unit_id": f"evidence-{ordinal + 1}",
            "relationship": item.relationship,
            "operator_label": item.operator_label,
            "citation_receipt_sha256": source.citation_receipt_sha256,
            "source_asset_id": source.source_asset_id,
            "claim_id": source.claim_id,
            "source_document_id": source.source_document_id,
            "chunk_ids": list(source.chunk_ids),
            "source_title": source.source_title,
            "source_content_sha256": source.source_content_sha256,
            "excerpt_text": source.excerpt_text,
            "excerpt_sha256": _sha(source.excerpt_text),
        })
    public_manifest = [
        {key: value for key, value in unit.items() if key not in {"excerpt_text", "unit_id"}}
        for unit in frozen
    ]
    manifest_sha = _sha(_canonical(public_manifest))
    content_sha = _sha(_canonical(frozen))
    if manifest_sha != str(bundle[7]):
        raise EvidenceBundleSynthesisConflict("evidence synthesis manifest is corrupt")
    return tuple(frozen), manifest_sha, content_sha


def _from_row(row: tuple[Any, ...], inputs: tuple[dict[str, object], ...]) -> EvidenceBundleSynthesisProposal:
    return EvidenceBundleSynthesisProposal(
        proposal_id=str(row[0]), bundle_id=str(row[1]), write_document_id=str(row[2]),
        project_id=str(row[3]), revision=int(row[4]), base_revision=int(row[5]),
        source_manifest_sha256=str(row[6]), source_content_sha256=str(row[7]),
        source_receipt_sha256=str(row[8]), provider_id=str(row[9]), model_id=str(row[10]),
        projected_max_cents=int(row[11]), approved_ceiling_cents=int(row[12]),
        instruction=str(row[13]), state=str(row[14]), inputs=inputs,
    )


def get_evidence_bundle_synthesis_proposal(
    con: Any, authority: InterviewAccountAuthority, *, proposal_id: str
) -> EvidenceBundleSynthesisProposal:
    row = con.execute(
        "SELECT proposal_id, bundle_id, write_document_id, project_id, revision, "
        "base_revision, source_manifest_sha256, source_content_sha256, "
        "source_receipt_sha256, provider_id, model_id, projected_max_cents, "
        "approved_ceiling_cents, instruction, state FROM "
        "interview_evidence_bundle_synthesis_proposals_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND proposal_id = ?",
        [authority.account_digest, authority.account_id, proposal_id],
    ).fetchone()
    if row is None:
        raise ValueError("evidence synthesis proposal not found")
    bundle = _bundle_row(con, authority, str(row[1]))
    if (str(bundle[1]) != str(row[2]) or str(bundle[2]) != str(row[3])
            or str(bundle[7]) != str(row[6]) or str(bundle[8]) != str(row[8])):
        raise EvidenceBundleSynthesisConflict("evidence synthesis bundle receipt changed")
    bundle_units = con.execute(
        "SELECT ordinal, relationship, operator_label, citation_receipt_sha256, "
        "source_asset_id, claim_id, source_document_id, chunk_ids_json, source_title, "
        "source_content_sha256, excerpt_sha256, unit_receipt_sha256 FROM "
        "interview_write_evidence_bundle_units_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND bundle_id = ? ORDER BY ordinal",
        [authority.account_digest, authority.account_id, str(row[1])],
    ).fetchall()
    current_manifest: list[dict[str, object]] = []
    for expected, unit in enumerate(bundle_units):
        try:
            chunks = json.loads(str(unit[7]))
        except json.JSONDecodeError as exc:
            raise EvidenceBundleSynthesisConflict("evidence synthesis bundle is corrupt") from exc
        value: dict[str, object] = {
            "bundle_id": str(bundle[0]), "ordinal": int(unit[0]),
            "relationship": str(unit[1]),
            "operator_label": None if unit[2] is None else str(unit[2]),
            "citation_receipt_sha256": str(unit[3]), "source_asset_id": str(unit[4]),
            "claim_id": str(unit[5]), "source_document_id": str(unit[6]),
            "chunk_ids": chunks, "source_title": str(unit[8]),
            "source_content_sha256": str(unit[9]), "excerpt_sha256": str(unit[10]),
        }
        if int(unit[0]) != expected or _authority_receipt_sha(value) != str(unit[11]):
            raise EvidenceBundleSynthesisConflict("evidence synthesis bundle is corrupt")
        current_manifest.append({k: v for k, v in value.items() if k != "bundle_id"})
    bundle_receipt = {
        "bundle_id": str(bundle[0]), "write_document_id": str(bundle[1]),
        "project_id": str(bundle[2]), "native_event_id": str(bundle[3]),
        "native_event_sha256": str(bundle[4]), "operation": "evidence_bundle",
        "revision": int(bundle[5]), "item_count": len(bundle_units),
        "manifest_sha256": str(bundle[7]),
        "preview_sha256": str(con.execute(
            "SELECT preview_sha256 FROM interview_write_evidence_bundles_authority "
            "WHERE account_digest = ? AND bundle_id = ?",
            [authority.account_digest, str(bundle[0])],
        ).fetchone()[0]),
    }
    if (len(bundle_units) != int(bundle[6])
            or _sha(_canonical(current_manifest)) != str(bundle[7])
            or _authority_receipt_sha(bundle_receipt) != str(bundle[8])):
        raise EvidenceBundleSynthesisConflict("evidence synthesis bundle is corrupt")
    unit_rows = con.execute(
        "SELECT ordinal, relationship, operator_label, citation_receipt_sha256, "
        "source_asset_id, claim_id, source_document_id, chunk_ids_json, source_title, "
        "source_content_sha256, excerpt_text, excerpt_sha256, input_receipt_sha256 "
        "FROM interview_evidence_bundle_synthesis_inputs_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND proposal_id = ? ORDER BY ordinal",
        [authority.account_digest, authority.account_id, proposal_id],
    ).fetchall()
    inputs: list[dict[str, object]] = []
    for expected, unit in enumerate(unit_rows):
        try:
            chunks = json.loads(str(unit[7]))
        except json.JSONDecodeError as exc:
            raise EvidenceBundleSynthesisConflict("evidence synthesis input is corrupt") from exc
        value: dict[str, object] = {
            "ordinal": int(unit[0]), "unit_id": f"evidence-{int(unit[0]) + 1}",
            "relationship": str(unit[1]),
            "operator_label": None if unit[2] is None else str(unit[2]),
            "citation_receipt_sha256": str(unit[3]), "source_asset_id": str(unit[4]),
            "claim_id": str(unit[5]), "source_document_id": str(unit[6]),
            "chunk_ids": chunks, "source_title": str(unit[8]),
            "source_content_sha256": str(unit[9]), "excerpt_text": str(unit[10]),
            "excerpt_sha256": str(unit[11]),
        }
        if (int(unit[0]) != expected or _sha(str(unit[10])) != str(unit[11])
                or _sha(_canonical(value)) != str(unit[12])):
            raise EvidenceBundleSynthesisConflict("evidence synthesis input is corrupt")
        inputs.append(value)
    public = [
        {k: v for k, v in item.items() if k not in {"excerpt_text", "unit_id"}}
        for item in inputs
    ]
    if (len(inputs) != int(bundle[6]) or _sha(_canonical(public)) != str(row[6])
            or _sha(_canonical(inputs)) != str(row[7])):
        raise EvidenceBundleSynthesisConflict("evidence synthesis input ledger is corrupt")
    return _from_row(tuple(row), tuple(inputs))


def create_evidence_bundle_synthesis_proposal(
    con: LockedConnection,
    authority: InterviewAccountAuthority,
    *,
    bundle_id: str,
    write_document_id: str,
    project_id: str,
    mutation_key: str,
    base_revision: int,
    instruction: str,
    provider_id: str,
    model_id: str,
    projected_max_cents: int,
    approved_ceiling_cents: int,
    allowed_model_pairs: frozenset[tuple[str, str]],
    hydrated_items: tuple[EvidenceBundleItem, ...],
) -> EvidenceBundleSynthesisProposal:
    if not isinstance(con, LockedConnection):
        raise TypeError("evidence synthesis proposal requires a LockedConnection")
    bundle_id, mutation_key = _text(bundle_id, "bundle id"), _text(mutation_key, "mutation key")
    write_document_id = _text(write_document_id, "Write document id")
    project_id = _text(project_id, "project id")
    validate_proposal_inputs(
        base_revision=base_revision, instruction=instruction, provider_id=provider_id,
        model_id=model_id, projected_max_cents=projected_max_cents,
        approved_ceiling_cents=approved_ceiling_cents,
        allowed_model_pairs=allowed_model_pairs,
    )
    bundle = _bundle_row(con, authority, bundle_id)
    if str(bundle[1]) != write_document_id or str(bundle[2]) != project_id:
        raise ValueError("evidence synthesis bundle not found")
    inputs, manifest_sha, content_sha = _verified_inputs(
        con, authority, bundle=bundle, items=hydrated_items,
    )
    request = {
        "schema_version": 1, "source_kind": "evidence_bundle", "bundle_id": bundle_id,
        "write_document_id": write_document_id, "project_id": project_id,
        "base_revision": base_revision,
        "source_manifest_sha256": manifest_sha, "source_content_sha256": content_sha,
        "source_receipt_sha256": str(bundle[8]), "instruction": instruction,
        "provider_id": provider_id, "model_id": model_id,
        "projected_max_cents": projected_max_cents,
        "approved_ceiling_cents": approved_ceiling_cents,
    }
    request_sha = _sha(_canonical(request))
    replay = con.execute(
        "SELECT request_sha256, proposal_id FROM "
        "interview_evidence_bundle_synthesis_proposals_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND mutation_key = ?",
        [authority.account_digest, authority.account_id, mutation_key],
    ).fetchone()
    if replay is not None:
        if str(replay[0]) != request_sha:
            raise EvidenceBundleSynthesisConflict(
                "evidence synthesis key was reused with different input"
            )
        return get_evidence_bundle_synthesis_proposal(
            con, authority, proposal_id=str(replay[1])
        )
    latest = con.execute(
        "SELECT coalesce(max(revision), 0) FROM "
        "interview_evidence_bundle_synthesis_proposals_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND bundle_id = ?",
        [authority.account_digest, authority.account_id, bundle_id],
    ).fetchone()
    if int(latest[0]) != base_revision:
        raise EvidenceBundleSynthesisConflict("stale evidence synthesis proposal revision")
    revision = base_revision + 1
    proposal_id = "ivbp-" + _sha(
        f"antiek-bundle-synthesis-v1\0{authority.account_digest}\0{mutation_key}\0{request_sha}"
    )[:32]
    con.execute("BEGIN TRANSACTION")
    try:
        con.execute(
            "INSERT INTO interview_evidence_bundle_synthesis_proposals_authority "
            "(account_digest, proposal_id, bundle_id, write_document_id, project_id, "
            "owner_user_id, mutation_key, request_sha256, revision, base_revision, "
            "source_manifest_sha256, source_content_sha256, source_receipt_sha256, "
            "provider_id, model_id, projected_max_cents, approved_ceiling_cents, instruction) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [authority.account_digest, proposal_id, bundle_id, str(bundle[1]), str(bundle[2]),
             authority.account_id, mutation_key, request_sha, revision, base_revision,
             manifest_sha, content_sha, str(bundle[8]), provider_id, model_id,
             projected_max_cents, approved_ceiling_cents, instruction],
        )
        for unit in inputs:
            receipt_sha = _sha(_canonical(unit))
            con.execute(
                "INSERT INTO interview_evidence_bundle_synthesis_inputs_authority "
                "(account_digest, proposal_id, owner_user_id, ordinal, relationship, "
                "operator_label, citation_receipt_sha256, source_asset_id, claim_id, "
                "source_document_id, chunk_ids_json, source_title, source_content_sha256, "
                "excerpt_text, excerpt_sha256, input_receipt_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [authority.account_digest, proposal_id, authority.account_id,
                 unit["ordinal"], unit["relationship"], unit["operator_label"],
                 unit["citation_receipt_sha256"], unit["source_asset_id"], unit["claim_id"],
                 unit["source_document_id"], _canonical(unit["chunk_ids"]),
                 unit["source_title"], unit["source_content_sha256"], unit["excerpt_text"],
                 unit["excerpt_sha256"], receipt_sha],
            )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return get_evidence_bundle_synthesis_proposal(con, authority, proposal_id=proposal_id)


def assert_evidence_bundle_synthesis_custody(
    proposal: EvidenceBundleSynthesisProposal,
    hydrated_items: tuple[EvidenceBundleItem, ...],
) -> None:
    if len(hydrated_items) != len(proposal.inputs):
        raise EvidenceBundleSynthesisConflict("evidence synthesis custody changed")
    for frozen, current in zip(proposal.inputs, hydrated_items, strict=True):
        source = current.source
        if not (
            frozen["relationship"] == current.relationship
            and frozen["operator_label"] == current.operator_label
            and frozen["citation_receipt_sha256"] == source.citation_receipt_sha256
            and frozen["source_asset_id"] == source.source_asset_id
            and frozen["claim_id"] == source.claim_id
            and frozen["source_document_id"] == source.source_document_id
            and frozen["chunk_ids"] == list(source.chunk_ids)
            and frozen["source_title"] == source.source_title
            and frozen["source_content_sha256"] == source.source_content_sha256
            and frozen["excerpt_text"] == source.excerpt_text
            and frozen["excerpt_sha256"] == _sha(source.excerpt_text)
        ):
            raise EvidenceBundleSynthesisConflict("evidence synthesis custody changed")


__all__ = [
    "EvidenceBundleSynthesisConflict", "EvidenceBundleSynthesisProposal",
    "assert_evidence_bundle_synthesis_custody",
    "create_evidence_bundle_synthesis_proposal", "get_evidence_bundle_synthesis_proposal",
]
