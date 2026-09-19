"""Crash-safe execution boundary for staged private composition proposals."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from runtime.db_lock import connect_read, connect_write
from substrate.midnight_oil.budget_ledger import (
    BudgetLedger,
    CallNotDispatched,
    UnknownCallOutcome,
)

from .authority import InterviewAccountAuthority
from .composition import get_private_draft
from .composition_proposals import get_proposal
from .evidence_bundle_synthesis import get_evidence_bundle_synthesis_proposal

ROLE = "composition_writer"


class CompositionExecutionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderCompositionResult:
    raw_json: str
    provider: str
    model: str
    actual_cents: int
    dispatch_event_id: str
    prompt_sha256: str


class CompositionExecutor(Protocol):
    @property
    def route_sha256(self) -> str: ...

    def execute(
        self, *, prompt: str, provider: str, model: str, idempotency_key: str
    ) -> ProviderCompositionResult: ...


@dataclass(frozen=True)
class CompositionExecution:
    proposal_id: str
    attempt_id: str
    run_id: str
    state: str
    prompt_sha256: str
    route_sha256: str
    hold_id: str | None
    actual_cents: int | None
    result_html: str | None
    result_html_sha256: str | None
    rejection_reason: str | None


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _row(con: Any, authority: InterviewAccountAuthority, proposal_id: str) -> tuple[Any, ...] | None:
    row = con.execute(
        "SELECT proposal_id, attempt_id, run_id, state, prompt_sha256, route_sha256, "
        "hold_id, actual_cents, result_html, result_html_sha256, rejection_reason "
        "FROM interview_composition_execution_authority WHERE account_digest = ? "
        "AND owner_user_id = ? AND proposal_id = ?",
        [authority.account_digest, authority.account_id, proposal_id],
    ).fetchone()
    return None if row is None else tuple(row)


def _from_row(row: tuple[Any, ...]) -> CompositionExecution:
    return CompositionExecution(
        proposal_id=str(row[0]), attempt_id=str(row[1]), run_id=str(row[2]),
        state=str(row[3]), prompt_sha256=str(row[4]), route_sha256=str(row[5]),
        hold_id=None if row[6] is None else str(row[6]),
        actual_cents=None if row[7] is None else int(row[7]),
        result_html=None if row[8] is None else str(row[8]),
        result_html_sha256=None if row[9] is None else str(row[9]),
        rejection_reason=None if row[10] is None else str(row[10]),
    )


def _proposal_source(
    con: Any, authority: InterviewAccountAuthority, proposal_id: str,
) -> tuple[Any, Any]:
    if proposal_id.startswith("ivbp-"):
        proposal = get_evidence_bundle_synthesis_proposal(
            con, authority, proposal_id=proposal_id,
        )
        return proposal, proposal.inputs
    proposal = get_proposal(con, authority, proposal_id=proposal_id)
    return proposal, get_private_draft(con, authority, draft_id=proposal.draft_id)


def get_execution(
    db_path: str, authority: InterviewAccountAuthority, *, proposal_id: str,
    source_revalidator: Callable[[Any, Any], None] | None = None,
) -> CompositionExecution:
    with connect_read(db_path) as con:
        proposal, _source = _proposal_source(con, authority, proposal_id)
        if _is_bundle(proposal):
            if source_revalidator is None:
                raise ValueError("evidence synthesis custody revalidator is required")
            source_revalidator(con, proposal)
        row = _row(con, authority, proposal.proposal_id)
        if row is None:
            raise ValueError("composition execution not found")
        result = _from_row(row)
        receipt = con.execute(
            "SELECT state, raw_result_json, raw_result_sha256 FROM "
            "interview_composition_execution_authority WHERE account_digest = ? "
            "AND proposal_id = ?",
            [authority.account_digest, proposal_id],
        ).fetchone()
        if receipt[0] in {"provider_returned", "rejected", "ready_for_review"} and (
            receipt[1] is None or receipt[2] is None or _sha(str(receipt[1])) != str(receipt[2])
        ):
            raise CompositionExecutionConflict("composition provider checkpoint integrity failed")
        if result.result_html is not None and _sha(result.result_html) != result.result_html_sha256:
            raise CompositionExecutionConflict("composition result HTML integrity failed")
        return result


def _is_bundle(proposal: Any) -> bool:
    return proposal.proposal_id.startswith("ivbp-")


def _prompt(proposal: Any, source: Any) -> str:
    if _is_bundle(proposal):
        return _canonical({
            "schema_version": 1, "source_kind": "evidence_bundle",
            "instruction": proposal.instruction,
            "provider_id": proposal.provider_id, "model_id": proposal.model_id,
            "source_manifest_sha256": proposal.source_manifest_sha256,
            "source_content_sha256": proposal.source_content_sha256,
            "evidence": [{
                "evidence_unit_id": unit["unit_id"],
                "relationship": unit["relationship"],
                "operator_label": unit["operator_label"],
                "source_title": unit["source_title"],
                "citation_receipt_sha256": unit["citation_receipt_sha256"],
                "source_document_id": unit["source_document_id"],
                "excerpt_text": unit["excerpt_text"],
            } for unit in source],
            "output_contract": {
                "schema_version": 1, "title": "string", "lead": "string",
                "units": [{
                    "evidence_unit_ids": ["evidence-1"], "prose": "string",
                }],
            },
            "host_rules": {
                "relationships_are_operator_authored": True,
                "preserve_disagreement": True,
                "all_evidence_units_must_be_referenced_exactly_once": True,
                "model_must_not_return_html_citations_or_provenance": True,
            },
        })
    return _canonical({
        "schema_version": 1, "instruction": proposal.instruction,
        "source_manifest_sha256": source.manifest_sha256,
        "claims": [{"claim_id": c["claim_id"], "text": c["text"],
                    "verification": c["verification"]} for c in source.manifest["claims"]],
        "output_contract": {"schema_version": 1, "title": "string", "lead": "string",
                            "units": [{"claim_ids": ["claim-id"], "prose": "string"}]},
    })


def _validated_result(raw: str, proposal: Any, source: Any) -> dict[str, Any]:
    if not isinstance(raw, str) or len(raw) > 200_000:
        raise ValueError("provider composition result is invalid")
    value = json.loads(raw)
    if not isinstance(value, dict) or set(value) != {"schema_version", "title", "lead", "units"}:
        raise ValueError("provider composition result shape is invalid")
    if value["schema_version"] != 1:
        raise ValueError("provider composition result schema is invalid")
    for key, limit in (("title", 500), ("lead", 20_000)):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > limit:
            raise ValueError(f"provider composition {key} is invalid")
    units = value["units"]
    if not isinstance(units, list) or not 1 <= len(units) <= 500:
        raise ValueError("provider composition units are invalid")
    membership_key = "evidence_unit_ids" if _is_bundle(proposal) else "claim_ids"
    known = (
        {str(unit["unit_id"]) for unit in source}
        if _is_bundle(proposal)
        else {str(c["claim_id"]) for c in source.manifest["claims"]}
    )
    seen: set[str] = set()
    for unit in units:
        if not isinstance(unit, dict) or set(unit) != {membership_key, "prose"}:
            raise ValueError("provider composition unit shape is invalid")
        ids, prose = unit[membership_key], unit["prose"]
        if (not isinstance(ids, list) or not ids or len(ids) > 100
                or any(not isinstance(cid, str) or cid not in known for cid in ids)
                or len(set(ids)) != len(ids) or seen.intersection(ids)):
            raise ValueError("provider composition claim membership is invalid")
        if not isinstance(prose, str) or not prose.strip() or len(prose) > 20_000:
            raise ValueError("provider composition prose is invalid")
        seen.update(ids)
    if _is_bundle(proposal) and seen != known:
        raise ValueError("provider composition must preserve every evidence unit")
    return value


def _render(value: dict[str, Any], proposal: Any, source: Any) -> str:
    if _is_bundle(proposal):
        by_id = {str(unit["unit_id"]): unit for unit in source}
        sections: list[str] = []
        for output in value["units"]:
            evidence = "".join(
                '<article class="evidence-source" data-evidence-unit-id="'
                + html.escape(unit_id, quote=True) + '" data-relationship="'
                + html.escape(str(by_id[unit_id]["relationship"]), quote=True) + '">'
                + '<header><h3>' + html.escape(str(by_id[unit_id]["source_title"]))
                + '</h3><p>Operator relationship: '
                + html.escape(str(by_id[unit_id]["relationship"])) + '</p>'
                + ('' if by_id[unit_id]["operator_label"] is None else
                   '<p>Operator framing: '
                   + html.escape(str(by_id[unit_id]["operator_label"])) + '</p>')
                + '</header><blockquote data-citation-receipt-sha256="'
                + html.escape(str(by_id[unit_id]["citation_receipt_sha256"]), quote=True)
                + '" data-source-document-id="'
                + html.escape(str(by_id[unit_id]["source_document_id"]), quote=True)
                + '" data-source-content-sha256="'
                + html.escape(str(by_id[unit_id]["source_content_sha256"]), quote=True)
                + '" data-excerpt-sha256="'
                + html.escape(str(by_id[unit_id]["excerpt_sha256"]), quote=True) + '"><p>'
                + html.escape(str(by_id[unit_id]["excerpt_text"]))
                + '</p></blockquote></article>'
                for unit_id in output["evidence_unit_ids"]
            )
            sections.append(
                '<section class="ai-prose" data-evidence-unit-ids="'
                + html.escape(" ".join(output["evidence_unit_ids"]), quote=True)
                + '"><p>' + html.escape(output["prose"]) + '</p>' + evidence + '</section>'
            )
        return (
            '<article data-antiek-evidence-synthesis="'
            + html.escape(proposal.proposal_id, quote=True)
            + '"><header><h1>' + html.escape(value["title"]) + '</h1><p>'
            + html.escape(value["lead"])
            + '</p><p>AI prose for private review; evidence relationships remain '
              'operator-authored.</p></header>' + "".join(sections) + '</article>'
        )
    units = "".join(
        '<section class="ai-prose" data-claim-ids="'
        + html.escape(" ".join(unit["claim_ids"]), quote=True) + '"><p>'
        + html.escape(unit["prose"]) + "</p></section>" for unit in value["units"]
    )
    supplement = (
        '<section class="ai-composition" aria-label="AI composition proposal"><h2>'
        + html.escape(value["title"]) + "</h2><p>" + html.escape(value["lead"])
        + "</p>" + units + "</section>"
    )
    marker = "</header>"
    if marker not in source.body_html:
        raise ValueError("source composition HTML marker is missing")
    return source.body_html.replace(marker, marker + supplement, 1)


def _finalize(
    db_path: str, authority: InterviewAccountAuthority, proposal_id: str,
    source_revalidator: Callable[[Any, Any], None] | None = None,
) -> CompositionExecution:
    with connect_write(db_path, purpose="interview/composition_finalize", log_on_close=False) as con:
        proposal, source = _proposal_source(con, authority, proposal_id)
        if _is_bundle(proposal) and source_revalidator is None:
            raise ValueError("evidence synthesis custody revalidator is required")
        raw = con.execute(
            "SELECT raw_result_json, raw_result_sha256, actual_cents, provider, model, "
            "receipt_prompt_sha256, dispatch_event_id "
            "FROM interview_composition_execution_authority "
            "WHERE account_digest = ? AND proposal_id = ? AND state = 'provider_returned'",
            [authority.account_digest, proposal_id],
        ).fetchone()
        if raw is None:
            raise CompositionExecutionConflict("provider result is not ready to finalize")
        try:
            raw_json = str(raw[0])
            if _sha(raw_json) != str(raw[1]):
                raise ValueError("provider composition checkpoint integrity failed")
            if int(raw[2]) > proposal.projected_max_cents:
                raise ValueError("provider composition exceeded projected maximum")
            if str(raw[3]) != proposal.provider_id or str(raw[4]) != proposal.model_id:
                raise ValueError("composition provider route is outside approval")
            if source_revalidator is not None:
                source_revalidator(con, proposal)
            expected_prompt_sha = _sha(_prompt(proposal, source))
            if str(raw[5]) != expected_prompt_sha:
                raise ValueError("composition provider prompt receipt does not match")
            if not isinstance(raw[6], str) or not str(raw[6]).strip():
                raise ValueError("composition dispatch receipt is missing")
            value = _validated_result(raw_json, proposal, source)
            result_html = _render(value, proposal, source)
            result_sha, state, reason = _sha(result_html), "ready_for_review", None
        except (ValueError, json.JSONDecodeError) as exc:
            result_html, result_sha, state, reason = None, None, "rejected", str(exc)[:500]
        con.execute(
            "UPDATE interview_composition_execution_authority SET state = ?, result_html = ?, "
            "result_html_sha256 = ?, rejection_reason = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE account_digest = ? AND proposal_id = ? AND state = 'provider_returned'",
            [state, result_html, result_sha, reason, authority.account_digest, proposal_id],
        )
        return _from_row(_row(con, authority, proposal_id))  # type: ignore[arg-type]


def execute_proposal(
    db_path: str,
    authority: InterviewAccountAuthority,
    *,
    proposal_id: str,
    attempt_id: str,
    route_sha256: str,
    executor: CompositionExecutor,
    source_revalidator: Callable[[Any, Any], None] | None = None,
    crash_after_checkpoint: bool = False,
) -> CompositionExecution:
    if not attempt_id or attempt_id != attempt_id.strip() or len(attempt_id) > 512:
        raise ValueError("composition attempt id is invalid")
    if len(route_sha256) != 64:
        raise ValueError("composition route hash is invalid")
    bytes.fromhex(route_sha256)
    if getattr(executor, "route_sha256", None) != route_sha256:
        raise ValueError("composition route is not boot-attested")
    with connect_read(db_path) as con:
        proposal, source = _proposal_source(con, authority, proposal_id)
        if _is_bundle(proposal):
            if source_revalidator is None:
                raise ValueError("evidence synthesis custody revalidator is required")
            source_revalidator(con, proposal)
        existing = _row(con, authority, proposal_id)
        if existing is not None:
            prior = _from_row(existing)
            if prior.attempt_id != attempt_id or prior.route_sha256 != route_sha256:
                raise CompositionExecutionConflict("composition execution attempt conflicts")
            if prior.state in {"ready_for_review", "rejected", "call_not_dispatched"}:
                return prior
            raise CompositionExecutionConflict("composition execution requires reconciliation")
        prompt = _prompt(proposal, source)
        prompt_sha = _sha(prompt)
        run_id = "ivrun-" + _sha(authority.account_digest + "\0" + proposal_id)[:32]
    ledger = BudgetLedger(db_path)
    ledger.ensure_schema()
    # A hold with no operation row can only come from process death between
    # reserve_call and the pre-dispatch after_hold callback.  The callback is
    # what precedes executor invocation, so absence is positive no-call proof.
    with connect_read(db_path) as con:
        orphan_holds = con.execute(
            "SELECT h.hold_id FROM midnight_oil_call_holds h "
            "LEFT JOIN interview_composition_execution_authority e ON e.run_id = h.run_id "
            "WHERE h.run_id = ? AND h.role = ? AND h.state = 'open' "
            "AND e.run_id IS NULL",
            [run_id, ROLE],
        ).fetchall()
    for orphan in orphan_holds:
        ledger.release_proven_not_dispatched(str(orphan[0]))
    try:
        ledger.reserve(
            run_id, proposal.approved_ceiling_cents,
            {ROLE: proposal.approved_ceiling_cents},
        )
    except Exception as exc:
        raise CompositionExecutionConflict("composition call was not dispatched") from exc

    claimed_hold_id: str | None = None

    def after_hold(hold: Any) -> None:
        nonlocal claimed_hold_id
        with connect_write(
            db_path, purpose="interview/composition_claim", log_on_close=False
        ) as con:
            current_proposal, current_source = _proposal_source(
                con, authority, proposal_id,
            )
            if source_revalidator is not None:
                source_revalidator(con, current_proposal)
            if (_sha(_prompt(current_proposal, current_source)) != prompt_sha
                    or getattr(executor, "route_sha256", None) != route_sha256):
                raise CallNotDispatched("composition authority changed before dispatch")
            if _row(con, authority, proposal_id) is not None:
                raise CallNotDispatched("composition execution was already claimed")
            con.execute(
                "INSERT INTO interview_composition_execution_authority "
                "(account_digest, proposal_id, owner_user_id, attempt_id, run_id, state, "
                "prompt_sha256, route_sha256, hold_id) "
                "VALUES (?, ?, ?, ?, ?, 'dispatching', ?, ?, ?)",
                [authority.account_digest, proposal_id, authority.account_id, attempt_id,
                 run_id, prompt_sha, route_sha256, hold.hold_id],
            )
            claimed_hold_id = hold.hold_id

    def call() -> tuple[ProviderCompositionResult, int]:
        # Last possible current-authority check.  CallNotDispatched is the
        # only exception that proves the provider was not invoked.
        try:
            with connect_write(
                db_path, purpose="interview/composition_pre_dispatch",
                log_on_close=False,
            ) as con:
                current_proposal, current_source = _proposal_source(
                    con, authority, proposal_id,
                )
                if source_revalidator is not None:
                    source_revalidator(con, current_proposal)
                if _sha(_prompt(current_proposal, current_source)) != prompt_sha:
                    raise ValueError("composition authority changed")
        except Exception as exc:
            raise CallNotDispatched("composition authority changed before dispatch") from exc
        result = executor.execute(
            prompt=prompt, provider=proposal.provider_id, model=proposal.model_id,
            idempotency_key=attempt_id,
        )
        if not isinstance(result, ProviderCompositionResult):
            raise TypeError("composition executor returned an invalid result")
        if type(result.actual_cents) is not int or result.actual_cents < 0:
            raise ValueError("composition actual cost is invalid")
        return result, result.actual_cents

    def checkpoint(result: ProviderCompositionResult, actual_cents: int) -> None:
        with connect_write(db_path, purpose="interview/composition_checkpoint", log_on_close=False) as con:
            if claimed_hold_id is None:
                raise CompositionExecutionConflict("composition budget hold is missing")
            con.execute(
                "UPDATE interview_composition_execution_authority SET state = 'provider_returned', "
                "hold_id = ?, provider = ?, model = ?, actual_cents = ?, dispatch_event_id = ?, "
                "raw_result_json = ?, raw_result_sha256 = ?, receipt_prompt_sha256 = ?, "
                "updated_at = CURRENT_TIMESTAMP "
                "WHERE account_digest = ? AND proposal_id = ? AND state = 'dispatching'",
                [claimed_hold_id, result.provider, result.model, actual_cents,
                 result.dispatch_event_id, result.raw_json, _sha(result.raw_json),
                 result.prompt_sha256,
                 authority.account_digest, proposal_id],
            )
        if crash_after_checkpoint:
            raise RuntimeError("injected crash after provider checkpoint")

    try:
        ledger.guarded_call(
            run_id, ROLE, proposal.projected_max_cents, call,
            after_hold=after_hold, before_settle=checkpoint,
        )
    except CallNotDispatched:
        with connect_write(db_path, purpose="interview/composition_not_dispatched", log_on_close=False) as con:
            con.execute(
                "UPDATE interview_composition_execution_authority SET state = 'call_not_dispatched', "
                "rejection_reason = 'provider call was not dispatched', "
                "updated_at = CURRENT_TIMESTAMP WHERE account_digest = ? AND proposal_id = ?",
                [authority.account_digest, proposal_id],
            )
        raise
    except UnknownCallOutcome as exc:
        with connect_write(db_path, purpose="interview/composition_unknown", log_on_close=False) as con:
            con.execute(
                "UPDATE interview_composition_execution_authority SET state = CASE "
                "WHEN raw_result_json IS NULL THEN 'reconcile_required' ELSE state END, "
                "hold_id = ?, updated_at = CURRENT_TIMESTAMP WHERE account_digest = ? "
                "AND proposal_id = ?",
                [exc.hold.hold_id, authority.account_digest, proposal_id],
            )
        raise CompositionExecutionConflict("composition execution requires reconciliation") from exc
    return _finalize(db_path, authority, proposal_id, source_revalidator)


def reconcile_checkpointed(
    db_path: str, authority: InterviewAccountAuthority, *, proposal_id: str,
    source_revalidator: Callable[[Any, Any], None] | None = None,
) -> CompositionExecution:
    current = get_execution(
        db_path, authority, proposal_id=proposal_id,
        source_revalidator=source_revalidator,
    )
    if current.state != "provider_returned" or current.hold_id is None or current.actual_cents is None:
        raise CompositionExecutionConflict("composition execution is not checkpoint-reconcilable")
    con = connect_read(db_path)
    try:
        hold_state = con.execute(
            "SELECT state FROM midnight_oil_call_holds WHERE hold_id = ?", [current.hold_id]
        ).fetchone()
    finally:
        con.close()
    if hold_state is None:
        raise CompositionExecutionConflict("composition budget hold is missing")
    if str(hold_state[0]) == "unknown":
        BudgetLedger(db_path).resolve_unknown(current.hold_id, current.actual_cents)
    elif str(hold_state[0]) != "settled":
        raise CompositionExecutionConflict("composition budget hold is not reconcilable")
    return _finalize(db_path, authority, proposal_id, source_revalidator)


__all__ = [
    "CompositionExecution", "CompositionExecutionConflict", "CompositionExecutor",
    "ProviderCompositionResult", "execute_proposal", "get_execution", "reconcile_checkpointed",
]
