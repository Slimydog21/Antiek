"""Explicit preview and optimistic acceptance of evidence synthesis into native Write."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from html import escape
from typing import Any

from runtime.db_lock import connect_read, connect_write

from .authority import InterviewAccountAuthority
from .composition_execution import _prompt, _render, _validated_result
from .evidence_bundle_synthesis import get_evidence_bundle_synthesis_proposal
from .write_acceptance import (
    WriteAcceptanceConflict,
    WriteEditDecision,
    _edit_native_private_write,
    _read_document,
    _validated_edit_html,
)


@dataclass(frozen=True)
class EvidenceSynthesisAcceptancePreview:
    write_document_id: str
    project_id: str
    bundle_id: str
    proposal_id: str
    execution_run_id: str
    base_revision: int
    base_html_sha256: str
    result_html_sha256: str
    proposed_html: str
    proposed_html_sha256: str
    preview_sha256: str


@dataclass(frozen=True)
class EvidenceSynthesisAcceptanceDecision:
    acceptance_id: str
    proposal_id: str
    bundle_id: str
    execution_run_id: str
    receipt_sha256: str
    edit: WriteEditDecision


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _execution(con: Any, authority: InterviewAccountAuthority, proposal: Any) -> dict[str, str]:
    row = con.execute(
        "SELECT run_id, state, prompt_sha256, route_sha256, raw_result_json, "
        "raw_result_sha256, result_html, result_html_sha256, provider, model, "
        "dispatch_event_id, receipt_prompt_sha256 FROM "
        "interview_composition_execution_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND proposal_id = ?",
        [authority.account_digest, authority.account_id, proposal.proposal_id],
    ).fetchone()
    if row is None:
        raise ValueError("evidence synthesis execution not found")
    expected_prompt = _sha(_prompt(proposal, proposal.inputs))
    if (str(row[1]) != "ready_for_review" or row[4] is None or row[5] is None
            or row[6] is None or row[7] is None
            or _sha(str(row[4])) != str(row[5])
            or _sha(str(row[6])) != str(row[7])
            or expected_prompt != str(row[2]) or expected_prompt != str(row[11])
            or str(row[8]) != proposal.provider_id or str(row[9]) != proposal.model_id
            or not isinstance(row[10], str) or not str(row[10]).strip()
            or re.fullmatch(r"[0-9a-f]{64}", str(row[3])) is None):
        raise WriteAcceptanceConflict("evidence synthesis execution receipt is not ready")
    try:
        regenerated = _render(
            _validated_result(str(row[4]), proposal, proposal.inputs),
            proposal, proposal.inputs,
        )
    except (ValueError, json.JSONDecodeError) as exc:
        raise WriteAcceptanceConflict("evidence synthesis execution receipt is corrupt") from exc
    if regenerated != str(row[6]):
        raise WriteAcceptanceConflict("evidence synthesis execution receipt is corrupt")
    return {
        "run_id": str(row[0]), "prompt_sha256": str(row[2]),
        "route_sha256": str(row[3]), "result_html": str(row[6]),
        "result_html_sha256": str(row[7]),
        "raw_result_json": str(row[4]), "raw_result_sha256": str(row[5]),
    }


def _preview(
    authority: InterviewAccountAuthority, document: Any, proposal: Any,
    execution: dict[str, str], *, preview_secret: str,
) -> EvidenceSynthesisAcceptancePreview:
    if document.origin_kind != "owner_native":
        raise WriteAcceptanceConflict("synthesis acceptance requires an owner-native manuscript")
    if not isinstance(preview_secret, str) or len(preview_secret.encode()) < 32:
        raise ValueError("synthesis acceptance preview authority is unavailable")
    closing = re.search(r"</article>\s*$", document.body_html, re.IGNORECASE)
    if closing is None:
        raise WriteAcceptanceConflict("owner-native manuscript has no append boundary")
    section = _synthesis_section(proposal, execution)
    proposed = document.body_html[:closing.start()] + section + document.body_html[closing.start():]
    proposed, proposed_sha = _validated_edit_html(proposed, base_html=document.body_html)
    material = {
        "schema_version": 1, "account_digest": authority.account_digest,
        "write_document_id": document.write_document_id, "project_id": document.project_id,
        "bundle_id": proposal.bundle_id, "proposal_id": proposal.proposal_id,
        "execution_run_id": execution["run_id"], "base_revision": document.revision,
        "base_html_sha256": document.body_sha256,
        "source_manifest_sha256": proposal.source_manifest_sha256,
        "source_content_sha256": proposal.source_content_sha256,
        "source_receipt_sha256": proposal.source_receipt_sha256,
        "prompt_sha256": execution["prompt_sha256"], "route_sha256": execution["route_sha256"],
        "result_html_sha256": execution["result_html_sha256"],
        "proposed_html_sha256": proposed_sha,
    }
    preview_sha = hmac.new(
        preview_secret.encode(), _canonical(material).encode(), hashlib.sha256,
    ).hexdigest()
    return EvidenceSynthesisAcceptancePreview(
        write_document_id=document.write_document_id, project_id=document.project_id,
        bundle_id=proposal.bundle_id, proposal_id=proposal.proposal_id,
        execution_run_id=execution["run_id"], base_revision=document.revision,
        base_html_sha256=str(document.body_sha256),
        result_html_sha256=execution["result_html_sha256"], proposed_html=proposed,
        proposed_html_sha256=proposed_sha, preview_sha256=preview_sha,
    )


def _synthesis_section(proposal: Any, execution: dict[str, str]) -> str:
    return (
        '<section data-antiek-synthesis-acceptance="true" '
        f'data-proposal-id="{escape(proposal.proposal_id, quote=True)}" '
        f'data-bundle-id="{escape(proposal.bundle_id, quote=True)}" '
        f'data-run-id="{escape(execution["run_id"], quote=True)}" '
        f'data-result-html-sha256="{escape(execution["result_html_sha256"], quote=True)}">'
        '<header><h2>Evidence synthesis</h2><p>Model-assisted analysis; '
        'relationships and citations remain source-bound.</p></header>'
        f'{execution["result_html"]}</section>'
    )


def preview_evidence_synthesis_acceptance(
    db_path: str, authority: InterviewAccountAuthority, *, proposal_id: str,
    write_document_id: str, base_revision: int, base_html_sha256: str,
    preview_secret: str, source_revalidator: Callable[[Any, Any], None],
) -> EvidenceSynthesisAcceptancePreview:
    with connect_read(db_path) as con:
        proposal = get_evidence_bundle_synthesis_proposal(con, authority, proposal_id=proposal_id)
        source_revalidator(con, proposal)
        document = _read_document(con, authority, write_document_id)
        if (proposal.write_document_id != write_document_id
                or proposal.project_id != document.project_id):
            raise ValueError("evidence synthesis proposal not found")
        if document.revision != base_revision or document.body_sha256 != base_html_sha256:
            raise WriteAcceptanceConflict("stale private Write revision")
        return _preview(
            authority, document, proposal, _execution(con, authority, proposal),
            preview_secret=preview_secret,
        )


def apply_evidence_synthesis_acceptance(
    db_path: str, authority: InterviewAccountAuthority, *, proposal_id: str,
    write_document_id: str, mutation_key: str, base_revision: int,
    base_html_sha256: str, preview_sha256: str, proposed_html_sha256: str,
    preview_secret: str, source_revalidator: Callable[[Any, Any], None],
) -> EvidenceSynthesisAcceptanceDecision:
    for value, label in ((base_html_sha256, "base hash"), (preview_sha256, "preview hash"),
                         (proposed_html_sha256, "proposed HTML hash")):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"synthesis acceptance {label} is invalid")
    if not isinstance(mutation_key, str) or not mutation_key.strip() or len(mutation_key) > 512:
        raise ValueError("synthesis acceptance mutation key is invalid")
    request_sha = _sha(_canonical({
        "schema_version": 1, "proposal_id": proposal_id,
        "write_document_id": write_document_id, "base_revision": base_revision,
        "base_html_sha256": base_html_sha256, "preview_sha256": preview_sha256,
        "proposed_html_sha256": proposed_html_sha256,
    }))
    with connect_write(db_path, purpose="interview/write_synthesis_accept", log_on_close=False) as con:
        replay = con.execute(
            "SELECT e.event_id, e.write_document_id, e.project_id, e.base_revision, "
            "e.revision, e.body_sha256, e.request_sha256, a.acceptance_id, a.bundle_id, "
            "a.execution_run_id, a.receipt_sha256 FROM interview_write_native_events_authority e "
            "JOIN interview_write_synthesis_acceptances_authority a ON "
            "a.account_digest = e.account_digest AND a.native_event_id = e.event_id "
            "WHERE e.account_digest = ? AND e.owner_user_id = ? AND e.mutation_key = ?",
            [authority.account_digest, authority.account_id, mutation_key],
        ).fetchone()
        if replay is not None:
            if str(replay[6]) != request_sha:
                raise WriteAcceptanceConflict("private Write edit key was reused with different input")
            proposal = get_evidence_bundle_synthesis_proposal(
                con, authority, proposal_id=proposal_id,
            )
            source_revalidator(con, proposal)
            execution = _execution(con, authority, proposal)
            if (str(replay[1]) != proposal.write_document_id
                    or str(replay[2]) != proposal.project_id
                    or str(replay[8]) != proposal.bundle_id
                    or str(replay[9]) != execution["run_id"]):
                raise WriteAcceptanceConflict("synthesis acceptance replay is corrupt")
            _read_document(con, authority, str(replay[1]))
            return EvidenceSynthesisAcceptanceDecision(
                acceptance_id=str(replay[7]), proposal_id=proposal_id,
                bundle_id=str(replay[8]), execution_run_id=str(replay[9]),
                receipt_sha256=str(replay[10]), edit=WriteEditDecision(
                    event_id=str(replay[0]), write_document_id=str(replay[1]),
                    project_id=str(replay[2]), prior_revision=int(replay[3]),
                    revision=int(replay[4]), body_sha256=str(replay[5]), replayed=True,
                    operation="synthesis_accept",
                ),
            )
        proposal = get_evidence_bundle_synthesis_proposal(con, authority, proposal_id=proposal_id)
        source_revalidator(con, proposal)
        document = _read_document(con, authority, write_document_id)
        if (proposal.write_document_id != write_document_id
                or proposal.project_id != document.project_id):
            raise ValueError("evidence synthesis proposal not found")
        if document.revision != base_revision or document.body_sha256 != base_html_sha256:
            raise WriteAcceptanceConflict("stale private Write revision")
        execution = _execution(con, authority, proposal)
        accepted = con.execute(
            "SELECT acceptance_id FROM interview_write_synthesis_acceptances_authority "
            "WHERE account_digest = ? AND owner_user_id = ? AND proposal_id = ?",
            [authority.account_digest, authority.account_id, proposal.proposal_id],
        ).fetchone()
        if accepted is not None:
            raise WriteAcceptanceConflict("evidence synthesis was already accepted")
        preview = _preview(
            authority, document, proposal, execution, preview_secret=preview_secret,
        )
        if (preview.preview_sha256 != preview_sha256
                or preview.proposed_html_sha256 != proposed_html_sha256):
            raise WriteAcceptanceConflict("synthesis acceptance preview is stale")
        acceptance_id = "ivwsa-" + _sha(
            authority.account_digest + "\0" + mutation_key + "\0" + request_sha
        )[:32]
        companion: dict[str, object] = {
            "acceptance_id": acceptance_id, "proposal_id": proposal.proposal_id,
            "bundle_id": proposal.bundle_id, "execution_run_id": execution["run_id"],
            "source_manifest_sha256": proposal.source_manifest_sha256,
            "source_content_sha256": proposal.source_content_sha256,
            "source_receipt_sha256": proposal.source_receipt_sha256,
            "prompt_sha256": execution["prompt_sha256"], "route_sha256": execution["route_sha256"],
            "result_html_sha256": execution["result_html_sha256"],
            "preview_sha256": preview.preview_sha256,
        }
        edit = _edit_native_private_write(
            con, authority, document, mutation_key=mutation_key, request_sha=request_sha,
            base_revision=base_revision, base_body_sha256=base_html_sha256,
            body_html=preview.proposed_html, summary=None, operation="edit",
            target_revision=None, target_body_sha256=None,
            synthesis_acceptance=companion,
        )
        receipt = con.execute(
            "SELECT receipt_sha256 FROM interview_write_synthesis_acceptances_authority "
            "WHERE account_digest = ? AND acceptance_id = ?",
            [authority.account_digest, acceptance_id],
        ).fetchone()
        return EvidenceSynthesisAcceptanceDecision(
            acceptance_id=acceptance_id, proposal_id=proposal.proposal_id,
            bundle_id=proposal.bundle_id, execution_run_id=execution["run_id"],
            receipt_sha256=str(receipt[0]), edit=WriteEditDecision(
                **{**edit.__dict__, "operation": "synthesis_accept"}
            ),
        )


__all__ = [
    "EvidenceSynthesisAcceptanceDecision", "EvidenceSynthesisAcceptancePreview",
    "apply_evidence_synthesis_acceptance", "preview_evidence_synthesis_acceptance",
]
