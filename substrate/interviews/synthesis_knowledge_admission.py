"""Explicit admission of accepted synthesis units into a private graph scope."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from runtime.db_lock import connect_read, connect_write
from substrate.graph.insight_question import (
    canonical_text,
    insight_node_id,
    promote_insight_authorized,
    promote_question_authorized,
    question_node_id,
)
from substrate.graph.tenancy import graph_key, has_node_membership
from substrate.investigation_tenancy import InvestigationAuthority

from .authority import InterviewAccountAuthority
from .composition_execution import _validated_result
from .evidence_bundle_synthesis import get_evidence_bundle_synthesis_proposal
from .evidence_synthesis_acceptance import _execution
from .write_acceptance import WriteAcceptanceConflict, _read_document


class SynthesisKnowledgeAdmissionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class SynthesisKnowledgeCandidate:
    unit_index: int
    kind: Literal["insight", "question"]
    text: str


@dataclass(frozen=True)
class SynthesisKnowledgePreviewItem:
    ordinal: int
    unit_index: int
    kind: Literal["insight", "question"]
    original_text_sha256: str
    admitted_text: str
    admitted_text_sha256: str
    canonical_text: str
    graph_node_id: str
    disposition: Literal["created", "reused"]
    evidence: tuple[dict[str, object], ...]
    evidence_sha256: str
    item_receipt_sha256: str


@dataclass(frozen=True)
class SynthesisKnowledgePreview:
    acceptance_id: str
    proposal_id: str
    target_investigation_id: str
    target_investigation_digest: str
    item_manifest_sha256: str
    preview_sha256: str
    items: tuple[SynthesisKnowledgePreviewItem, ...]


@dataclass(frozen=True)
class SynthesisKnowledgeAdmission:
    admission_id: str
    acceptance_id: str
    target_investigation_id: str
    receipt_sha256: str
    replayed: bool
    items: tuple[SynthesisKnowledgePreviewItem, ...]


@dataclass(frozen=True)
class SynthesisKnowledgeSourceUnit:
    unit_index: int
    text: str
    original_text_sha256: str
    evidence: tuple[dict[str, object], ...]


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _receipt(value: dict[str, object]) -> str:
    return _sha(_canonical({"schema_version": 1, **value}))


def _acceptance(
    con: Any, authority: InterviewAccountAuthority, *, acceptance_id: str,
    proposal_id: str, write_document_id: str,
) -> tuple[dict[str, object], Any, dict[str, str], dict[str, Any]]:
    document = _read_document(con, authority, write_document_id)
    row = con.execute(
        "SELECT acceptance_id, native_event_id, native_event_sha256, proposal_id, "
        "bundle_id, execution_run_id, revision, html_sha256, prompt_sha256, route_sha256, "
        "result_html_sha256, receipt_sha256, project_id FROM "
        "interview_write_synthesis_acceptances_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND acceptance_id = ?",
        [authority.account_digest, authority.account_id, acceptance_id],
    ).fetchone()
    if row is None or str(row[3]) != proposal_id:
        raise ValueError("synthesis knowledge source not found")
    proposal = get_evidence_bundle_synthesis_proposal(con, authority, proposal_id=proposal_id)
    execution = _execution(con, authority, proposal)
    if (proposal.write_document_id != write_document_id
            or proposal.project_id != document.project_id
            or str(row[4]) != proposal.bundle_id
            or str(row[5]) != execution["run_id"]
            or int(row[6]) < 2 or int(row[6]) > document.revision
            or str(row[8]) != execution["prompt_sha256"]
            or str(row[9]) != execution["route_sha256"]
            or str(row[10]) != execution["result_html_sha256"]
            or str(row[12]) != document.project_id):
        raise WriteAcceptanceConflict("synthesis knowledge source receipt is corrupt")
    structured = _validated_result(execution["raw_result_json"], proposal, proposal.inputs)
    return ({
        "acceptance_id": str(row[0]), "native_event_id": str(row[1]),
        "native_event_sha256": str(row[2]), "proposal_id": str(row[3]),
        "bundle_id": str(row[4]), "execution_run_id": str(row[5]),
        "revision": int(row[6]), "body_sha256": str(row[7]),
        "prompt_sha256": str(row[8]), "route_sha256": str(row[9]),
        "result_html_sha256": str(row[10]), "acceptance_receipt_sha256": str(row[11]),
        "project_id": str(row[12]), "write_document_id": write_document_id,
    }, proposal, execution, structured)


def _validated_candidates(
    candidates: Sequence[SynthesisKnowledgeCandidate], structured: dict[str, Any],
    proposal: Any,
) -> tuple[dict[str, object], ...]:
    if not 1 <= len(candidates) <= 32:
        raise ValueError("synthesis knowledge selection must contain 1 to 32 items")
    seen: set[int] = set()
    inputs = {str(item["unit_id"]): item for item in proposal.inputs}
    values: list[dict[str, object]] = []
    for ordinal, candidate in enumerate(candidates):
        if (not isinstance(candidate.unit_index, int) or candidate.unit_index < 0
                or candidate.unit_index >= len(structured["units"])
                or candidate.unit_index in seen):
            raise ValueError("synthesis knowledge unit selection is invalid")
        if candidate.kind not in {"insight", "question"}:
            raise ValueError("synthesis knowledge kind is invalid")
        if (not isinstance(candidate.text, str) or candidate.text != candidate.text.strip()
                or not candidate.text or len(candidate.text) > 20_000):
            raise ValueError("synthesis knowledge text is invalid")
        seen.add(candidate.unit_index)
        output = structured["units"][candidate.unit_index]
        evidence: list[dict[str, object]] = []
        for unit_id in output["evidence_unit_ids"]:
            source = inputs[str(unit_id)]
            evidence.append({
                "evidence_unit_id": str(unit_id),
                "relationship": str(source["relationship"]),
                "operator_label": source["operator_label"],
                "citation_receipt_sha256": str(source["citation_receipt_sha256"]),
                "source_asset_id": str(source["source_asset_id"]),
                "claim_id": str(source["claim_id"]),
                "source_document_id": str(source["source_document_id"]),
                "chunk_ids": list(source["chunk_ids"]),
                "source_content_sha256": str(source["source_content_sha256"]),
                "excerpt_sha256": str(source["excerpt_sha256"]),
            })
        values.append({
            "ordinal": ordinal, "unit_index": candidate.unit_index,
            "kind": candidate.kind, "original_text": str(output["prose"]),
            "admitted_text": candidate.text, "evidence": evidence,
        })
    return tuple(values)


def _source_units(structured: dict[str, Any], proposal: Any) -> tuple[SynthesisKnowledgeSourceUnit, ...]:
    inputs = {str(item["unit_id"]): item for item in proposal.inputs}
    units: list[SynthesisKnowledgeSourceUnit] = []
    for unit_index, output in enumerate(structured["units"]):
        evidence = tuple({
            "evidence_unit_id": str(unit_id),
            "relationship": str(inputs[str(unit_id)]["relationship"]),
            "operator_label": inputs[str(unit_id)]["operator_label"],
            "citation_receipt_sha256": str(inputs[str(unit_id)]["citation_receipt_sha256"]),
            "source_asset_id": str(inputs[str(unit_id)]["source_asset_id"]),
            "claim_id": str(inputs[str(unit_id)]["claim_id"]),
            "source_document_id": str(inputs[str(unit_id)]["source_document_id"]),
            "chunk_ids": list(inputs[str(unit_id)]["chunk_ids"]),
            "source_content_sha256": str(inputs[str(unit_id)]["source_content_sha256"]),
            "excerpt_sha256": str(inputs[str(unit_id)]["excerpt_sha256"]),
        } for unit_id in output["evidence_unit_ids"])
        text = str(output["prose"])
        units.append(SynthesisKnowledgeSourceUnit(
            unit_index=unit_index, text=text, original_text_sha256=_sha(text),
            evidence=evidence,
        ))
    return tuple(units)


def list_synthesis_knowledge_candidates(
    db_path: str, authority: InterviewAccountAuthority, *, acceptance_id: str,
    proposal_id: str, write_document_id: str,
    source_revalidator: Callable[[Any, Any], None],
) -> tuple[SynthesisKnowledgeSourceUnit, ...]:
    with connect_read(db_path) as con:
        _acceptance_value, proposal, _execution_value, structured = _acceptance(
            con, authority, acceptance_id=acceptance_id, proposal_id=proposal_id,
            write_document_id=write_document_id,
        )
        source_revalidator(con, proposal)
        return _source_units(structured, proposal)


def _preview(
    con: Any, *, acceptance: dict[str, object], proposal: Any,
    execution: dict[str, str], structured: dict[str, Any],
    target: InvestigationAuthority, candidates: Sequence[SynthesisKnowledgeCandidate],
    preview_secret: str,
) -> SynthesisKnowledgePreview:
    if not isinstance(preview_secret, str) or len(preview_secret.encode()) < 32:
        raise ValueError("synthesis knowledge preview authority is unavailable")
    values = _validated_candidates(candidates, structured, proposal)
    items: list[SynthesisKnowledgePreviewItem] = []
    for value in values:
        kind = str(value["kind"])
        text = str(value["admitted_text"])
        node_id = insight_node_id(text) if kind == "insight" else question_node_id(text)
        member = con.execute(
            "SELECT 1 FROM investigation_node_memberships WHERE account_digest = ? "
            "AND investigation_digest = ? AND node_id = ? LIMIT 1",
            [target.account_digest, target.investigation_digest, node_id],
        ).fetchone() is not None
        evidence_json = _canonical(value["evidence"])
        item_value: dict[str, object] = {
            "acceptance_id": acceptance["acceptance_id"], "ordinal": value["ordinal"],
            "unit_index": value["unit_index"], "kind": kind,
            "original_text_sha256": _sha(str(value["original_text"])),
            "admitted_text_sha256": _sha(text), "graph_node_id": node_id,
            "node_disposition": "reused" if member else "created",
            "evidence_sha256": _sha(evidence_json),
        }
        items.append(SynthesisKnowledgePreviewItem(
            ordinal=int(value["ordinal"]), unit_index=int(value["unit_index"]),
            kind=kind, original_text_sha256=str(item_value["original_text_sha256"]),
            admitted_text=text, admitted_text_sha256=str(item_value["admitted_text_sha256"]),
            canonical_text=canonical_text(text), graph_node_id=node_id,
            disposition=item_value["node_disposition"], evidence=tuple(value["evidence"]),
            evidence_sha256=str(item_value["evidence_sha256"]),
            item_receipt_sha256=_receipt(item_value),
        ))
    manifest = [{
        "ordinal": item.ordinal, "unit_index": item.unit_index, "kind": item.kind,
        "original_text_sha256": item.original_text_sha256,
        "admitted_text_sha256": item.admitted_text_sha256,
        "graph_node_id": item.graph_node_id, "node_disposition": item.disposition,
        "evidence_sha256": item.evidence_sha256,
        "item_receipt_sha256": item.item_receipt_sha256,
    } for item in items]
    manifest_sha = _sha(_canonical(manifest))
    preview_value = {
        **acceptance, "raw_result_sha256": execution["raw_result_sha256"],
        "target_investigation_id": target.investigation_id,
        "target_investigation_digest": target.investigation_digest,
        "target_graph_key": graph_key(target), "item_manifest_sha256": manifest_sha,
    }
    preview_sha = hmac.new(
        preview_secret.encode(), _canonical(preview_value).encode(), hashlib.sha256,
    ).hexdigest()
    return SynthesisKnowledgePreview(
        acceptance_id=str(acceptance["acceptance_id"]),
        proposal_id=str(acceptance["proposal_id"]),
        target_investigation_id=target.investigation_id,
        target_investigation_digest=target.investigation_digest,
        item_manifest_sha256=manifest_sha, preview_sha256=preview_sha, items=tuple(items),
    )


def preview_synthesis_knowledge_admission(
    db_path: str, authority: InterviewAccountAuthority, *, acceptance_id: str,
    proposal_id: str, write_document_id: str, target: InvestigationAuthority,
    candidates: Sequence[SynthesisKnowledgeCandidate], preview_secret: str,
    source_revalidator: Callable[[Any, Any], None],
) -> SynthesisKnowledgePreview:
    if target.account_id != authority.account_id:
        raise ValueError("synthesis knowledge target not found")
    with connect_read(db_path) as con:
        acceptance, proposal, execution, structured = _acceptance(
            con, authority, acceptance_id=acceptance_id, proposal_id=proposal_id,
            write_document_id=write_document_id,
        )
        source_revalidator(con, proposal)
        return _preview(
            con, acceptance=acceptance, proposal=proposal, execution=execution,
            structured=structured, target=target, candidates=candidates,
            preview_secret=preview_secret,
        )


def _stored_items(
    con: Any, *, authority: InterviewAccountAuthority, target: InvestigationAuthority,
    admission_id: str, acceptance_id: str,
) -> tuple[SynthesisKnowledgePreviewItem, ...]:
    rows = con.execute(
        "SELECT ordinal, unit_index, kind, original_text_sha256, admitted_text, "
        "admitted_text_sha256, graph_node_id, node_disposition, evidence_json, "
        "evidence_sha256, item_receipt_sha256 FROM "
        "interview_synthesis_knowledge_admission_items_authority WHERE "
        "account_digest = ? AND owner_user_id = ? AND admission_id = ? "
        "AND acceptance_id = ? ORDER BY ordinal",
        [authority.account_digest, authority.account_id, admission_id, acceptance_id],
    ).fetchall()
    items: list[SynthesisKnowledgePreviewItem] = []
    for ordinal, row in enumerate(rows):
        try:
            evidence = json.loads(str(row[8]))
        except json.JSONDecodeError as exc:
            raise SynthesisKnowledgeAdmissionConflict(
                "synthesis knowledge item receipt is corrupt"
            ) from exc
        item_value: dict[str, object] = {
            "acceptance_id": acceptance_id, "ordinal": int(row[0]),
            "unit_index": int(row[1]), "kind": str(row[2]),
            "original_text_sha256": str(row[3]),
            "admitted_text_sha256": str(row[5]), "graph_node_id": str(row[6]),
            "node_disposition": str(row[7]), "evidence_sha256": str(row[9]),
        }
        expected_node = (
            insight_node_id(str(row[4])) if str(row[2]) == "insight"
            else question_node_id(str(row[4]))
        )
        if (int(row[0]) != ordinal or str(row[2]) not in {"insight", "question"}
                or _sha(str(row[4])) != str(row[5])
                or _sha(_canonical(evidence)) != str(row[9])
                or expected_node != str(row[6])
                or str(row[7]) not in {"created", "reused"}
                or _receipt(item_value) != str(row[10])
                or not has_node_membership(con, target, node_id=str(row[6]))):
            raise SynthesisKnowledgeAdmissionConflict(
                "synthesis knowledge item receipt is corrupt"
            )
        items.append(SynthesisKnowledgePreviewItem(
            ordinal=ordinal, unit_index=int(row[1]), kind=str(row[2]),
            original_text_sha256=str(row[3]), admitted_text=str(row[4]),
            admitted_text_sha256=str(row[5]), canonical_text=canonical_text(str(row[4])),
            graph_node_id=str(row[6]), disposition=str(row[7]), evidence=tuple(evidence),
            evidence_sha256=str(row[9]), item_receipt_sha256=str(row[10]),
        ))
    if not items:
        raise SynthesisKnowledgeAdmissionConflict("synthesis knowledge admission is incomplete")
    return tuple(items)


def _batch_value(
    *, admission_id: str, mutation_key_sha256: str,
    acceptance: dict[str, object], execution: dict[str, str],
    target: InvestigationAuthority, item_count: int, item_manifest_sha256: str,
    request_sha256: str, preview_sha256: str,
) -> dict[str, object]:
    return {
        "admission_id": admission_id, **acceptance,
        "raw_result_sha256": execution["raw_result_sha256"],
        "target_investigation_id": target.investigation_id,
        "target_investigation_digest": target.investigation_digest,
        "target_graph_key": graph_key(target), "item_count": item_count,
        "item_manifest_sha256": item_manifest_sha256,
        "mutation_key_sha256": mutation_key_sha256,
        "request_sha256": request_sha256, "preview_sha256": preview_sha256,
    }


def apply_synthesis_knowledge_admission(
    db_path: str, authority: InterviewAccountAuthority, *, acceptance_id: str,
    proposal_id: str, write_document_id: str, target: InvestigationAuthority,
    candidates: Sequence[SynthesisKnowledgeCandidate], preview_sha256: str,
    mutation_key: str, preview_secret: str,
    source_revalidator: Callable[[Any, Any], None], embedding_provider: Any = None,
) -> SynthesisKnowledgeAdmission:
    if target.account_id != authority.account_id:
        raise ValueError("synthesis knowledge target not found")
    if re.fullmatch(r"[0-9a-f]{64}", preview_sha256 or "") is None:
        raise ValueError("synthesis knowledge preview hash is invalid")
    if not isinstance(mutation_key, str) or not mutation_key.strip() or len(mutation_key) > 512:
        raise ValueError("synthesis knowledge mutation key is invalid")
    request_sha = _sha(_canonical({
        "acceptance_id": acceptance_id, "proposal_id": proposal_id,
        "write_document_id": write_document_id,
        "target_investigation_id": target.investigation_id,
        "items": [candidate.__dict__ for candidate in candidates],
        "preview_sha256": preview_sha256,
    }))
    with connect_write(db_path, purpose="interview/synthesis_knowledge_admit", log_on_close=False) as con:
        con.execute("BEGIN")
        try:
            acceptance, proposal, execution, structured = _acceptance(
                con, authority, acceptance_id=acceptance_id, proposal_id=proposal_id,
                write_document_id=write_document_id,
            )
            source_revalidator(con, proposal)
            replay = con.execute(
                "SELECT admission_id, request_sha256, receipt_sha256, acceptance_id, "
                "proposal_id, write_document_id, target_investigation_id, "
                "target_investigation_digest, target_graph_key, item_count, "
                "item_manifest_sha256, preview_sha256, mutation_key_sha256, "
                "acceptance_receipt_sha256, native_event_id, native_event_sha256, "
                "project_id, revision, body_sha256, bundle_id, execution_run_id, "
                "prompt_sha256, route_sha256, raw_result_sha256, result_html_sha256 FROM "
                "interview_synthesis_knowledge_admissions_authority WHERE account_digest = ? "
                "AND owner_user_id = ? AND mutation_key = ?",
                [authority.account_digest, authority.account_id, mutation_key],
            ).fetchone()
            if replay is not None:
                if (str(replay[1]) != request_sha or str(replay[3]) != acceptance_id
                        or str(replay[4]) != proposal_id
                        or str(replay[5]) != write_document_id
                        or str(replay[6]) != target.investigation_id
                        or str(replay[7]) != target.investigation_digest
                        or str(replay[8]) != graph_key(target)):
                    raise SynthesisKnowledgeAdmissionConflict(
                        "synthesis knowledge key was reused with different input"
                    )
                stored = _stored_items(
                    con, authority=authority, target=target, admission_id=str(replay[0]),
                    acceptance_id=acceptance_id,
                )
                if int(replay[9]) != len(stored):
                    raise SynthesisKnowledgeAdmissionConflict(
                        "synthesis knowledge admission is incomplete"
                    )
                stored_manifest = [{
                    "ordinal": item.ordinal, "unit_index": item.unit_index,
                    "kind": item.kind, "original_text_sha256": item.original_text_sha256,
                    "admitted_text_sha256": item.admitted_text_sha256,
                    "graph_node_id": item.graph_node_id,
                    "node_disposition": item.disposition,
                    "evidence_sha256": item.evidence_sha256,
                    "item_receipt_sha256": item.item_receipt_sha256,
                } for item in stored]
                manifest_sha = _sha(_canonical(stored_manifest))
                stored_acceptance = {
                    "acceptance_id": str(replay[3]), "native_event_id": str(replay[14]),
                    "native_event_sha256": str(replay[15]), "proposal_id": str(replay[4]),
                    "bundle_id": str(replay[19]), "execution_run_id": str(replay[20]),
                    "revision": int(replay[17]), "body_sha256": str(replay[18]),
                    "prompt_sha256": str(replay[21]), "route_sha256": str(replay[22]),
                    "result_html_sha256": str(replay[24]),
                    "acceptance_receipt_sha256": str(replay[13]),
                    "project_id": str(replay[16]), "write_document_id": str(replay[5]),
                }
                batch_value = _batch_value(
                    admission_id=str(replay[0]), mutation_key_sha256=str(replay[12]),
                    acceptance=stored_acceptance,
                    execution={**execution, "raw_result_sha256": str(replay[23])},
                    target=target, item_count=len(stored), item_manifest_sha256=manifest_sha,
                    request_sha256=str(replay[1]), preview_sha256=str(replay[11]),
                )
                if (stored_acceptance != acceptance or manifest_sha != str(replay[10])
                        or str(replay[11]) != preview_sha256
                        or str(replay[12]) != _sha(mutation_key)
                        or str(replay[23]) != execution["raw_result_sha256"]
                        or _receipt(batch_value) != str(replay[2])):
                    raise SynthesisKnowledgeAdmissionConflict(
                        "synthesis knowledge batch receipt is corrupt"
                    )
                con.execute("ROLLBACK")
                return SynthesisKnowledgeAdmission(
                    admission_id=str(replay[0]), acceptance_id=acceptance_id,
                    target_investigation_id=target.investigation_id,
                    receipt_sha256=str(replay[2]), replayed=True, items=stored,
                )
            requested_indexes = [candidate.unit_index for candidate in candidates]
            if requested_indexes:
                placeholders = ", ".join("?" for _ in requested_indexes)
                already = con.execute(
                    "SELECT unit_index FROM "
                    "interview_synthesis_knowledge_admission_items_authority WHERE "
                    "account_digest = ? AND owner_user_id = ? AND acceptance_id = ? "
                    f"AND unit_index IN ({placeholders}) LIMIT 1",
                    [authority.account_digest, authority.account_id, acceptance_id,
                     *requested_indexes],
                ).fetchone()
                if already is not None:
                    raise SynthesisKnowledgeAdmissionConflict(
                        "synthesis knowledge unit was already admitted"
                    )
            preview = _preview(
                con, acceptance=acceptance, proposal=proposal, execution=execution,
                structured=structured, target=target, candidates=candidates,
                preview_secret=preview_secret,
            )
            if preview.preview_sha256 != preview_sha256:
                raise SynthesisKnowledgeAdmissionConflict("synthesis knowledge preview is stale")
            graph_scope_key = graph_key(target)
            admission_id = "ivska-" + _sha(
                authority.account_digest + "\0" + mutation_key + "\0" + request_sha
            )[:32]
            for item in preview.items:
                if item.disposition == "created":
                    metadata = {
                        "origin": "accepted_synthesis_knowledge_admission",
                        "epistemic_status": "model_proposed_operator_admitted",
                        "acceptance_id": acceptance_id, "proposal_id": proposal_id,
                        "admission_id": admission_id, "result_unit_index": item.unit_index,
                        "evidence_sha256": item.evidence_sha256,
                    }
                    writer = (
                        promote_insight_authorized if item.kind == "insight"
                        else promote_question_authorized
                    )
                    kwargs: dict[str, object] = {
                        "text": item.admitted_text, "con": con, "metadata": metadata,
                        "source_document_id": str(item.evidence[0]["source_document_id"]),
                    }
                    if embedding_provider is not None:
                        kwargs["embedding_provider"] = embedding_provider
                    if item.kind == "insight":
                        kwargs["confidence"] = "unknown"
                    node_id = writer(target, **kwargs)
                    if node_id != item.graph_node_id:
                        raise SynthesisKnowledgeAdmissionConflict(
                            "synthesis knowledge graph identity changed"
                        )
                elif not has_node_membership(con, target, node_id=item.graph_node_id):
                    raise SynthesisKnowledgeAdmissionConflict(
                        "synthesis knowledge graph membership changed"
                    )
                con.execute(
                    "INSERT INTO interview_synthesis_knowledge_admission_items_authority "
                    "(account_digest, admission_id, owner_user_id, acceptance_id, ordinal, "
                    "unit_index, kind, original_text_sha256, admitted_text, "
                    "admitted_text_sha256, graph_node_id, node_disposition, evidence_json, "
                    "evidence_sha256, item_receipt_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, "
                    "?, ?, ?, ?, ?, ?)",
                    [authority.account_digest, admission_id, authority.account_id,
                     acceptance_id, item.ordinal, item.unit_index, item.kind,
                     item.original_text_sha256, item.admitted_text, item.admitted_text_sha256,
                     item.graph_node_id, item.disposition, _canonical(item.evidence),
                     item.evidence_sha256, item.item_receipt_sha256],
                )
            mutation_key_sha = _sha(mutation_key)
            batch_value = _batch_value(
                admission_id=admission_id, mutation_key_sha256=mutation_key_sha,
                acceptance=acceptance, execution=execution, target=target,
                item_count=len(preview.items),
                item_manifest_sha256=preview.item_manifest_sha256,
                request_sha256=request_sha, preview_sha256=preview.preview_sha256,
            )
            receipt_sha = _receipt(batch_value)
            con.execute(
                "INSERT INTO interview_synthesis_knowledge_admissions_authority "
                "(account_digest, admission_id, owner_user_id, acceptance_id, "
                "acceptance_receipt_sha256, native_event_id, native_event_sha256, "
                "write_document_id, project_id, revision, body_sha256, proposal_id, bundle_id, "
                "execution_run_id, prompt_sha256, route_sha256, raw_result_sha256, "
                "result_html_sha256, target_investigation_id, target_investigation_digest, "
                "target_graph_key, item_count, item_manifest_sha256, mutation_key, "
                "mutation_key_sha256, request_sha256, preview_sha256, receipt_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?)",
                [authority.account_digest, admission_id, authority.account_id, acceptance_id,
                 acceptance["acceptance_receipt_sha256"], acceptance["native_event_id"],
                 acceptance["native_event_sha256"], write_document_id, acceptance["project_id"],
                 acceptance["revision"], acceptance["body_sha256"], proposal_id,
                 acceptance["bundle_id"], acceptance["execution_run_id"],
                 acceptance["prompt_sha256"], acceptance["route_sha256"],
                 execution["raw_result_sha256"], acceptance["result_html_sha256"],
                 target.investigation_id, target.investigation_digest, graph_scope_key,
                 len(preview.items), preview.item_manifest_sha256, mutation_key,
                 mutation_key_sha, request_sha, preview.preview_sha256, receipt_sha],
            )
            con.execute("COMMIT")
            return SynthesisKnowledgeAdmission(
                admission_id=admission_id, acceptance_id=acceptance_id,
                target_investigation_id=target.investigation_id,
                receipt_sha256=receipt_sha, replayed=False, items=preview.items,
            )
        except Exception:
            if con.transaction_active:
                con.execute("ROLLBACK")
            raise


__all__ = [
    "SynthesisKnowledgeAdmission", "SynthesisKnowledgeAdmissionConflict",
    "SynthesisKnowledgeCandidate", "SynthesisKnowledgePreview",
    "SynthesisKnowledgeSourceUnit", "apply_synthesis_knowledge_admission",
    "list_synthesis_knowledge_candidates", "preview_synthesis_knowledge_admission",
]
