"""Coordination API — read-only HTTP surface for gates + roadmap + source gate + cost + consent.

Thin adapter over :mod:`substrate.coordination`. Five GET endpoints, no writes:

  GET /coordination/gates     the gate ledger (a view over operator_gate_actions.md)
  GET /coordination/roadmap   the 45-sprint roadmap + DRW critical path +
                               dependency blockers + operator-action summary
  GET /coordination/source-gate the source census gate used by acquisition flows
  GET /coordination/cost      per-workflow + aggregate inference cost (SPR-07)
  GET /coordination/consent   per-IP-holder consent / escrow (accruing) / servability (SPR-07)

**Read-only is enforced, not promised (rigor #5).** This module imports only
read entry points (``load_gate_ledger`` / ``load_operator_actions`` /
``load_phase2_audit`` / ``load_engineering_deferrals`` / ``build_roadmap`` /
``build_loop3_coordination_view`` / ``build_source_gate_view`` / ``build_cost_view`` /
``build_consent_view``); there is no import of any writer (``connect_write``,
the escrow writer
``ip_holders.accrue_escrow``, the gate file's path for writing) and **no import
of any payout module** (``tools.stripe_connect.payouts``). There is
no POST/PUT/PATCH/DELETE route. The cost endpoint opens DuckDB ``read_only=True``
only to resolve Speak project economics context; the consent endpoint does the
same for escrow/servability state. A future maintainer (or auditor) confirms
"the coordination surface cannot change a gate, move escrow, or disburse a
payout" by the absence of any such path here — greppable, and asserted in
``tests/test_coordination_no_fork.py`` (gates/roadmap) and
``tests/test_cost_consent_no_disbursement.py`` (cost/consent, SPR-07).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Literal

import duckdb
from fastapi import FastAPI
from pydantic import BaseModel

from substrate.coordination.activation_view import (
    ReadActivationNextSession,
    ReadActivationView,
    build_read_activation_view,
    recommend_read_activation_next_session,
)
from substrate.coordination.consent_view import (
    ConsentView,
    IpHolderConsentRow,
    build_consent_view,
)
from substrate.coordination.cost_view import (
    CostView,
    WorkflowCost,
    build_cost_view,
    speak_policy_by_investigation_from_db,
)
from substrate.coordination.engineering_deferrals import (
    EngineeringDeferral,
    EngineeringDeferralsView,
    load_engineering_deferrals,
)
from substrate.coordination.gate_ledger import (
    Gate,
    GateLedger,
    load_gate_ledger,
)
from substrate.coordination.loop3_status import (
    Loop3CoordinationView,
    Loop3CriterionStatus,
    build_loop3_coordination_view,
)
from substrate.coordination.operator_actions import (
    OperatorAction,
    OperatorActionsView,
    load_operator_actions,
)
from substrate.coordination.phase2_audit import (
    Phase2AuditView,
    Phase2ExitCriteria,
    Phase2SprintScore,
    load_phase2_audit,
)
from substrate.coordination.roadmap import (
    ExecutionFocus,
    Roadmap,
    SprintRow,
    build_roadmap,
)
from substrate.coordination.source_gate_status import (
    SourceGateRow,
    SourceGateView,
    build_source_gate_view,
)
from substrate.research_bridge.dogfood_log import DOGFOOD_PROJECT_COUNT
from substrate.research_bridge.dogfood_readiness import (
    DogfoodReadiness,
    audit_dogfood_readiness,
)
from tools.lint.merge_age_gate import MAX_BEHIND, compute_distance

_REPO = Path(__file__).resolve().parents[3]

# ── Response shapes ──────────────────────────────────────────────────────────

class GateImpactResponse(BaseModel):
    product: str
    effect: str


class GateResponse(BaseModel):
    gate_id: str
    title: str
    status: str          # coarse bucket: closed | open | calendar | data_bound
    status_raw: str      # verbatim nuance from the source
    is_provisional: bool
    owner: str | None
    blocks: str | None
    closure_record: str | None  # docs/decisions/... path, if any
    impacts: list[GateImpactResponse]

    @classmethod
    def from_gate(cls, g: Gate) -> GateResponse:
        return cls(
            gate_id=g.gate_id,
            title=g.title,
            status=g.status.value,
            status_raw=g.status_raw,
            is_provisional=g.is_provisional,
            owner=g.owner,
            blocks=g.blocks,
            closure_record=g.closure_record,
            impacts=[
                GateImpactResponse(product=i.product.value, effect=i.effect)
                for i in g.impacts
            ],
        )


class GateLedgerResponse(BaseModel):
    """The full ledger. ``source_path`` makes explicit which canonical file this
    is a view over (it is read on every request — never cached as a fork)."""

    source_path: str
    gates: list[GateResponse]


class SprintResponse(BaseModel):
    spec: str
    spec_label: str
    sprint: int
    slug: str
    node_id: str
    status: str
    on_critical_path: bool
    blocked_on: list[str]
    unblocked: bool

    @classmethod
    def from_row(cls, s: SprintRow) -> SprintResponse:
        return cls(
            spec=s.spec,
            spec_label=s.spec_label,
            sprint=s.sprint,
            slug=s.slug,
            node_id=s.node_id,
            status=s.status.value,
            on_critical_path=s.on_critical_path,
            blocked_on=list(s.blocked_on),
            unblocked=s.unblocked,
        )


class RosterResponse(BaseModel):
    spec: str
    label: str
    directory: str
    count: int
    sprints: list[SprintResponse]


class SubstrateLayerResponse(BaseModel):
    name: str
    owner: str
    status: str


class DependencyBlockerResponse(BaseModel):
    node_id: str
    blocked_sprints: list[str]


class ExecutionFocusResponse(BaseModel):
    kind: Literal["dependency_blocker", "dependency_ready"]
    node_id: str
    blocked_sprints: list[str]

    @classmethod
    def from_focus(cls, focus: ExecutionFocus) -> ExecutionFocusResponse:
        return cls(
            kind=focus.kind,
            node_id=focus.node_id,
            blocked_sprints=[s.node_id for s in focus.blocked_sprints],
        )


class OperatorGateFocusResponse(BaseModel):
    """First still-open operator gate, derived from the canonical gate ledger.

    This is a small reference, not a forked gate row. It lets the roadmap say
    "structural dependencies are clear; this operator gate is now the next
    blocker" while gate state stays owned by ``docs/operator_gate_actions.md``.
    """

    gate_id: str
    title: str
    status: str
    status_raw: str
    owner: str | None
    blocks: str | None
    source_path: str

    @classmethod
    def from_gate(cls, gate: Gate, source_path: str) -> OperatorGateFocusResponse:
        return cls(
            gate_id=gate.gate_id,
            title=gate.title,
            status=gate.status.value,
            status_raw=gate.status_raw,
            owner=gate.owner,
            blocks=gate.blocks,
            source_path=source_path,
        )


class ReadActivationNextSessionResponse(BaseModel):
    source_path: str
    state: str
    next_action: str
    recommended_template: str | None
    append_command: str | None
    rationale: str
    remaining_requirements: dict[str, int]

    @classmethod
    def from_recommendation(
        cls,
        recommendation: ReadActivationNextSession,
    ) -> ReadActivationNextSessionResponse:
        return cls(
            source_path=recommendation.source_path,
            state=recommendation.state,
            next_action=recommendation.next_action,
            recommended_template=recommendation.recommended_template,
            append_command=recommendation.append_command,
            rationale=recommendation.rationale,
            remaining_requirements=dict(recommendation.remaining_requirements),
        )


class ReadActivationStatusResponse(BaseModel):
    source_path: str
    state: str
    total_sessions: int
    valid_sessions: int
    invalid_session_count: int
    live_provider_sessions: int
    citation_trace_sessions: int
    non_library_sessions: int
    final_verdict: str | None
    closure_ready: bool
    required_counts: dict[str, int]
    remaining_requirements: dict[str, int]
    failures: list[str]
    next_session: ReadActivationNextSessionResponse

    @classmethod
    def from_view(cls, view: ReadActivationView) -> ReadActivationStatusResponse:
        return cls(
            source_path=view.source_path,
            state=view.state,
            total_sessions=view.total_sessions,
            valid_sessions=view.valid_sessions,
            invalid_session_count=view.invalid_session_count,
            live_provider_sessions=view.live_provider_sessions,
            citation_trace_sessions=view.citation_trace_sessions,
            non_library_sessions=view.non_library_sessions,
            final_verdict=view.final_verdict,
            closure_ready=view.closure_ready,
            required_counts=dict(view.required_counts),
            remaining_requirements=dict(view.remaining_requirements),
            failures=list(view.failures),
            next_session=ReadActivationNextSessionResponse.from_recommendation(
                recommend_read_activation_next_session(view),
            ),
        )


class AdrbDogfoodStatusResponse(BaseModel):
    """Deep Research Bridge dogfood closure status.

    This is a read-only projection over the ADRB dogfood log, bridge substrate
    rows, metrics artifact, and verdict document. It does not initialize schema
    or create operator artifacts; missing evidence is data for the operator.
    """

    state: Literal["not_checked", "incomplete", "ready", "error"]
    closure_ready: bool
    dogfood_root: str
    operator_log_path: str
    metrics_path: str
    verdict_path: str
    expected_project_count: int
    complete_project_entries: int
    reconciled_sessions: int
    valid_wave4_candidates: int
    metrics_current: bool
    mode_a_verdict: str | None
    mode_b_verdict: str | None
    missing_requirements: list[str]
    error: str | None

    @classmethod
    def from_readiness(
        cls,
        readiness: DogfoodReadiness,
    ) -> AdrbDogfoodStatusResponse:
        return cls(
            state="ready" if readiness.ok else "incomplete",
            closure_ready=readiness.ok,
            dogfood_root=str(readiness.dogfood_root),
            operator_log_path=str(readiness.log_validation.operator_log_path),
            metrics_path=str(readiness.metrics_path),
            verdict_path=str(readiness.verdict_path),
            expected_project_count=DOGFOOD_PROJECT_COUNT,
            complete_project_entries=len(
                readiness.log_validation.complete_project_entries
            ),
            reconciled_sessions=len(readiness.reconciliation.sessions),
            valid_wave4_candidates=len(readiness.wave4_validation.candidates),
            metrics_current=readiness.metrics_artifact.current,
            mode_a_verdict=readiness.verdict_validation.mode_a_verdict,
            mode_b_verdict=readiness.verdict_validation.mode_b_verdict,
            missing_requirements=list(readiness.missing_requirements),
            error=None,
        )

    @classmethod
    def not_checked(cls) -> AdrbDogfoodStatusResponse:
        return cls(
            state="not_checked",
            closure_ready=False,
            dogfood_root="",
            operator_log_path="",
            metrics_path="",
            verdict_path="",
            expected_project_count=DOGFOOD_PROJECT_COUNT,
            complete_project_entries=0,
            reconciled_sessions=0,
            valid_wave4_candidates=0,
            metrics_current=False,
            mode_a_verdict=None,
            mode_b_verdict=None,
            missing_requirements=["ADRB dogfood readiness was not checked"],
            error=None,
        )

    @classmethod
    def from_error(
        cls,
        error: Exception,
    ) -> AdrbDogfoodStatusResponse:
        message = str(error) or type(error).__name__
        return cls(
            state="error",
            closure_ready=False,
            dogfood_root="",
            operator_log_path="",
            metrics_path="",
            verdict_path="",
            expected_project_count=DOGFOOD_PROJECT_COUNT,
            complete_project_entries=0,
            reconciled_sessions=0,
            valid_wave4_candidates=0,
            metrics_current=False,
            mode_a_verdict=None,
            mode_b_verdict=None,
            missing_requirements=[message],
            error=message,
        )


class BranchHealthResponse(BaseModel):
    """Current branch freshness against ``origin/main``.

    This reuses the merge-age gate's measurement logic but does not fetch,
    rebase, or mutate git state. Stale-base work stays visible to the operator
    instead of hiding behind otherwise-green product gates.
    """

    state: Literal["ok", "stale", "error"]
    branch: str
    head_sha: str
    origin_main_sha: str
    merge_base_distance: int | None
    max_behind: int
    message: str
    remediation: str
    error: str | None


def _git_text(*args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(_REPO), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()


def build_branch_health() -> BranchHealthResponse:
    """Build a read-only branch freshness view for Coordination/Settings."""

    try:
        branch = _git_text("branch", "--show-current") or "detached"
        head_sha = _git_text("rev-parse", "--short", "HEAD")
        origin_main_sha = _git_text("rev-parse", "--short", "origin/main")
        distance, err = compute_distance()
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        return BranchHealthResponse(
            state="error",
            branch="unknown",
            head_sha="unknown",
            origin_main_sha="unknown",
            merge_base_distance=None,
            max_behind=MAX_BEHIND,
            message=f"Branch freshness check failed: {message}",
            remediation="Fetch origin/main and rerun the merge-age gate.",
            error=message,
        )

    if distance is None:
        return BranchHealthResponse(
            state="error",
            branch=branch,
            head_sha=head_sha,
            origin_main_sha=origin_main_sha,
            merge_base_distance=None,
            max_behind=MAX_BEHIND,
            message=err,
            remediation="Fetch origin/main and rerun the merge-age gate.",
            error=err,
        )

    stale = distance > MAX_BEHIND
    return BranchHealthResponse(
        state="stale" if stale else "ok",
        branch=branch,
        head_sha=head_sha,
        origin_main_sha=origin_main_sha,
        merge_base_distance=distance,
        max_behind=MAX_BEHIND,
        message=(
            f"base is {distance} commits behind origin/main "
            f"(limit N={MAX_BEHIND})"
        ),
        remediation=(
            "run `git rebase origin/main`"
            if stale
            else "branch freshness is within the merge-age budget"
        ),
        error=None,
    )


class OperatorActionResponse(BaseModel):
    action_id: str
    title: str
    status: str
    status_raw: str
    blocks: str
    owner: str

    @classmethod
    def from_action(cls, action: OperatorAction) -> OperatorActionResponse:
        return cls(
            action_id=action.action_id,
            title=action.title,
            status=action.status.value,
            status_raw=action.status_raw,
            blocks=action.blocks,
            owner=action.owner,
        )


class OperatorActionsSummaryResponse(BaseModel):
    """Read-only summary of ``docs/OPERATOR_ACTIONS.md``.

    The full action state stays in the markdown quick table. This response only
    exposes counts plus the first not-closed and closeable items so product
    surfaces can show the operator what needs a human decision next.
    """

    source_path: str
    total_actions: int
    open_count: int
    closeable_count: int
    status_counts: dict[str, int]
    next_action: OperatorActionResponse | None
    closeable_action: OperatorActionResponse | None

    @classmethod
    def from_view(cls, view: OperatorActionsView) -> OperatorActionsSummaryResponse:
        closeable = view.closeable_actions()
        return cls(
            source_path=view.source_path,
            total_actions=len(view.actions),
            open_count=len(view.open_actions()),
            closeable_count=len(closeable),
            status_counts=view.status_counts(),
            next_action=(
                OperatorActionResponse.from_action(view.first_open())
                if view.first_open() is not None
                else None
            ),
            closeable_action=(
                OperatorActionResponse.from_action(closeable[0]) if closeable else None
            ),
        )


class Phase2SprintScoreResponse(BaseModel):
    sprint: str
    phases: int
    met: int
    partial: int
    unmet: int
    delta_vs_v3: str

    @classmethod
    def from_score(cls, score: Phase2SprintScore) -> Phase2SprintScoreResponse:
        return cls(
            sprint=score.sprint,
            phases=score.phases,
            met=score.met,
            partial=score.partial,
            unmet=score.unmet,
            delta_vs_v3=score.delta_vs_v3,
        )


class Phase2ExitCriteriaResponse(BaseModel):
    total: int
    met: int
    partial: int
    unmet: int
    note: str

    @classmethod
    def from_exit_criteria(
        cls,
        exit_criteria: Phase2ExitCriteria,
    ) -> Phase2ExitCriteriaResponse:
        return cls(
            total=exit_criteria.total,
            met=exit_criteria.met,
            partial=exit_criteria.partial,
            unmet=exit_criteria.unmet,
            note=exit_criteria.note,
        )


class Phase2AuditResponse(BaseModel):
    """Read-only Phase 2 audit summary.

    Roadmap dependency state is not the same as execution-audit state. This
    keeps the audit's own scorecard visible without creating another sprint
    status store.
    """

    source_path: str
    scorecard_source_path: str
    current_commit_evidence: str | None
    engineering_blocked_count: int | None
    status_summary: str | None
    next_action_ordering: list[str]
    sprint_scorecard: list[Phase2SprintScoreResponse]
    total_score: Phase2SprintScoreResponse | None
    exit_criteria: Phase2ExitCriteriaResponse | None

    @classmethod
    def from_view(cls, view: Phase2AuditView) -> Phase2AuditResponse:
        return cls(
            source_path=view.source_path,
            scorecard_source_path=view.scorecard_source_path,
            current_commit_evidence=view.current_commit_evidence,
            engineering_blocked_count=view.engineering_blocked_count,
            status_summary=view.status_summary,
            next_action_ordering=list(view.next_action_ordering),
            sprint_scorecard=[
                Phase2SprintScoreResponse.from_score(score)
                for score in view.sprint_scorecard
            ],
            total_score=(
                Phase2SprintScoreResponse.from_score(view.total_score)
                if view.total_score is not None
                else None
            ),
            exit_criteria=(
                Phase2ExitCriteriaResponse.from_exit_criteria(view.exit_criteria)
                if view.exit_criteria is not None
                else None
            ),
        )


class EngineeringDeferralResponse(BaseModel):
    deferral_id: str
    title: str
    status: str
    status_raw: str
    unlock_criterion: str | None
    blocks: str | None

    @classmethod
    def from_deferral(
        cls,
        deferral: EngineeringDeferral,
    ) -> EngineeringDeferralResponse:
        return cls(
            deferral_id=deferral.deferral_id,
            title=deferral.title,
            status=deferral.status.value,
            status_raw=deferral.status_raw,
            unlock_criterion=deferral.unlock_criterion,
            blocks=deferral.blocks,
        )


class EngineeringDeferralsSummaryResponse(BaseModel):
    """Read-only summary of ``docs/engineering_deferrals.md``.

    This is the "do not pre-build" companion to operator actions. It exposes
    counts and the first still-open deferral so agents see sequencing blockers
    in the same place as roadmap and gate status.
    """

    source_path: str
    total_deferrals: int
    open_count: int
    status_counts: dict[str, int]
    first_open: EngineeringDeferralResponse | None

    @classmethod
    def from_view(
        cls,
        view: EngineeringDeferralsView,
    ) -> EngineeringDeferralsSummaryResponse:
        first_open = view.first_open()
        return cls(
            source_path=view.source_path,
            total_deferrals=len(view.deferrals),
            open_count=len(view.open_deferrals()),
            status_counts=view.status_counts(),
            first_open=(
                EngineeringDeferralResponse.from_deferral(first_open)
                if first_open is not None
                else None
            ),
        )


class Loop3CriterionStatusResponse(BaseModel):
    criterion: str
    manual_met: bool
    evidence_passed: bool
    evidence_status: str
    evidence_summary: str

    @classmethod
    def from_status(
        cls,
        status: Loop3CriterionStatus,
    ) -> Loop3CriterionStatusResponse:
        return cls(
            criterion=status.criterion,
            manual_met=status.manual_met,
            evidence_passed=status.evidence_passed,
            evidence_status=status.evidence_status,
            evidence_summary=status.evidence_summary,
        )


class Loop3CoordinationResponse(BaseModel):
    criteria: list[Loop3CriterionStatusResponse]
    manual_met_count: int
    evidence_passed_count: int
    total_criteria: int
    all_criteria_met: bool
    all_evidence_passed: bool
    env_unlocked: bool
    fully_unlocked: bool
    first_failing_evidence: Loop3CriterionStatusResponse | None
    events_dir: str
    open_weight_policy_file: str

    @classmethod
    def from_view(cls, view: Loop3CoordinationView) -> Loop3CoordinationResponse:
        return cls(
            criteria=[
                Loop3CriterionStatusResponse.from_status(status)
                for status in view.criteria
            ],
            manual_met_count=view.manual_met_count,
            evidence_passed_count=view.evidence_passed_count,
            total_criteria=view.total_criteria,
            all_criteria_met=view.all_criteria_met,
            all_evidence_passed=view.all_evidence_passed,
            env_unlocked=view.env_unlocked,
            fully_unlocked=view.fully_unlocked,
            first_failing_evidence=(
                Loop3CriterionStatusResponse.from_status(view.first_failing_evidence)
                if view.first_failing_evidence is not None
                else None
            ),
            events_dir=view.events_dir,
            open_weight_policy_file=view.open_weight_policy_file,
        )


class SourceGateRowResponse(BaseModel):
    source: str
    blocked: bool
    failures: list[str]

    @classmethod
    def from_row(cls, row: SourceGateRow) -> SourceGateRowResponse:
        return cls(
            source=row.source,
            blocked=row.blocked,
            failures=list(row.failures),
        )


class SourceGateResponse(BaseModel):
    source_path: str
    state: str
    reference_source: str
    source_count: int
    blocked_count: int
    rows: list[SourceGateRowResponse]
    error: str | None

    @classmethod
    def from_view(cls, view: SourceGateView) -> SourceGateResponse:
        return cls(
            source_path=view.source_path,
            state=view.state,
            reference_source=view.reference_source,
            source_count=view.source_count,
            blocked_count=view.blocked_count,
            rows=[SourceGateRowResponse.from_row(row) for row in view.rows],
            error=view.error,
        )


class RoadmapResponse(BaseModel):
    total_sprints: int
    superseded_count: int
    superseded_note: str
    activation_note: str
    reconciliation: str
    critical_path: list[str]
    rosters: list[RosterResponse]
    unblocked_now: list[str]      # node ids
    dependency_blockers: list[DependencyBlockerResponse]
    execution_focus: ExecutionFocusResponse | None
    operator_gate_focus: OperatorGateFocusResponse | None
    read_activation: ReadActivationStatusResponse
    adrb_dogfood: AdrbDogfoodStatusResponse
    branch_health: BranchHealthResponse
    operator_actions: OperatorActionsSummaryResponse
    phase2_audit: Phase2AuditResponse
    engineering_deferrals: EngineeringDeferralsSummaryResponse
    loop3: Loop3CoordinationResponse | None
    source_gate: SourceGateResponse
    substrate_layers: list[SubstrateLayerResponse]

    @classmethod
    def from_roadmap(
        cls,
        rm: Roadmap,
        gate_ledger: GateLedger | None = None,
        read_activation: ReadActivationView | None = None,
        adrb_dogfood: AdrbDogfoodStatusResponse | None = None,
        branch_health: BranchHealthResponse | None = None,
        operator_actions: OperatorActionsView | None = None,
        phase2_audit: Phase2AuditView | None = None,
        engineering_deferrals: EngineeringDeferralsView | None = None,
        loop3: Loop3CoordinationView | None = None,
        source_gate: SourceGateView | None = None,
    ) -> RoadmapResponse:
        focus = rm.execution_focus()
        operator_focus = None
        if focus is None and gate_ledger is not None:
            open_gates = gate_ledger.open_gates()
            if open_gates:
                operator_focus = OperatorGateFocusResponse.from_gate(
                    open_gates[0],
                    gate_ledger.source_path,
                )
        return cls(
            total_sprints=rm.total_sprints,
            superseded_count=rm.superseded_count,
            superseded_note=rm.superseded_note,
            activation_note=rm.activation_note,
            reconciliation=rm.count_reconciliation(),
            critical_path=list(rm.critical_path),
            rosters=[
                RosterResponse(
                    spec=r.spec,
                    label=r.label,
                    directory=r.directory,
                    count=r.count,
                    sprints=[SprintResponse.from_row(s) for s in r.sprints],
                )
                for r in rm.rosters
            ],
            unblocked_now=[s.node_id for s in rm.unblocked_now()],
            dependency_blockers=[
                DependencyBlockerResponse(
                    node_id=b.node_id,
                    blocked_sprints=[s.node_id for s in b.blocked_sprints],
                )
                for b in rm.dependency_blockers()
            ],
            execution_focus=(
                ExecutionFocusResponse.from_focus(focus) if focus is not None else None
            ),
            operator_gate_focus=operator_focus,
            read_activation=ReadActivationStatusResponse.from_view(
                read_activation or build_read_activation_view()
            ),
            adrb_dogfood=adrb_dogfood or AdrbDogfoodStatusResponse.not_checked(),
            branch_health=branch_health or build_branch_health(),
            operator_actions=OperatorActionsSummaryResponse.from_view(
                operator_actions or load_operator_actions()
            ),
            phase2_audit=Phase2AuditResponse.from_view(
                phase2_audit or load_phase2_audit()
            ),
            engineering_deferrals=EngineeringDeferralsSummaryResponse.from_view(
                engineering_deferrals or load_engineering_deferrals()
            ),
            loop3=Loop3CoordinationResponse.from_view(loop3) if loop3 is not None else None,
            source_gate=SourceGateResponse.from_view(
                source_gate or build_source_gate_view()
            ),
            substrate_layers=[
                SubstrateLayerResponse(
                    name=layer.name,
                    owner=layer.owner,
                    status=layer.status,
                )
                for layer in rm.substrate_layers
            ],
        )


# ── SPR-07 cost-view response shapes ─────────────────────────────────────────

class WorkflowCostResponse(BaseModel):
    """One workflow's realized inference cost. ``raw_cost_usd`` is always real
    (summed ``DispatchCall.cost_usd``). ``margined_cost_usd`` is present only
    when the economics-matrix margin is built (``margin_status == 'applied'``);
    otherwise it is ``None`` and only the raw cost is shown — honesty #1, no
    fabricated margin on a money screen. Costs are stringified Decimals to avoid
    float drift across the wire."""

    workflow: str                     # research | read | write | speak | unmapped
    raw_cost_usd: str
    call_count: int
    remote_exec_cost_usd: str
    margin_status: str                # applied | stubbed
    margin_rate: str | None
    margined_cost_usd: str | None
    margin_note: str

    @classmethod
    def from_workflow_cost(cls, w: WorkflowCost) -> WorkflowCostResponse:
        return cls(
            workflow=w.workflow.value,
            raw_cost_usd=str(w.raw_cost_usd),
            call_count=w.call_count,
            remote_exec_cost_usd=str(w.remote_exec_cost_usd),
            margin_status=w.margin_status.value,
            margin_rate=str(w.margin_rate) if w.margin_rate is not None else None,
            margined_cost_usd=(
                str(w.margined_cost_usd) if w.margined_cost_usd is not None else None
            ),
            margin_note=w.margin_note,
        )


class CostViewResponse(BaseModel):
    """Per-workflow + aggregate realized inference cost. ``aggregate_raw_cost_usd``
    equals the sum of the per-workflow raw costs by construction (no double
    count, no dropped workflow). Idle ⇒ every figure ``"0"`` — not fabricated."""

    per_workflow: list[WorkflowCostResponse]
    aggregate_raw_cost_usd: str
    aggregate_call_count: int
    aggregate_remote_exec_cost_usd: str
    has_unmapped_spend: bool
    events_dir: str

    @classmethod
    def from_cost_view(cls, cv: CostView) -> CostViewResponse:
        return cls(
            per_workflow=[
                WorkflowCostResponse.from_workflow_cost(w) for w in cv.per_workflow
            ],
            aggregate_raw_cost_usd=str(cv.aggregate_raw_cost_usd),
            aggregate_call_count=cv.aggregate_call_count,
            aggregate_remote_exec_cost_usd=str(cv.aggregate_remote_exec_cost_usd),
            has_unmapped_spend=cv.has_unmapped_spend(),
            events_dir=cv.events_dir,
        )


# ── SPR-07 consent-view response shapes ──────────────────────────────────────

class DisbursementGateResponse(BaseModel):
    """Why an accrued balance is NOT disbursable. ``disbursable`` is always
    ``False`` on this surface — there is no field a client can set to flip it,
    and no endpoint that performs disbursement. ``label`` is the operator-facing
    string ("accruing — disbursement gated on G2+G3")."""

    disbursable: bool                 # always False
    open_gate_ids: list[str]          # subset of {G2, G3} currently open
    holder_claimed: bool
    fully_unlocked: bool
    label: str


class IpHolderConsentResponse(BaseModel):
    ip_holder_id: str
    display_name: str
    status: str                       # opt-in state-machine state
    escrow_balance_usd: str           # accruing; "0" is an honest zero
    gate: DisbursementGateResponse
    serves_full_text: bool | None     # None when servability isn't surfaced
    servability_note: str | None

    @classmethod
    def from_row(cls, r: IpHolderConsentRow) -> IpHolderConsentResponse:
        return cls(
            ip_holder_id=r.ip_holder_id,
            display_name=r.display_name,
            status=r.status,
            escrow_balance_usd=str(r.escrow_balance_usd),
            gate=DisbursementGateResponse(
                disbursable=r.gate.disbursable,
                open_gate_ids=list(r.gate.open_gate_ids),
                holder_claimed=r.gate.holder_claimed,
                fully_unlocked=r.gate.fully_unlocked,
                label=r.gate.label,
            ),
            serves_full_text=r.serves_full_text,
            servability_note=r.servability_note,
        )


class EscrowReportResponse(BaseModel):
    """The read-only escrow aggregation (``compute_publisher_escrow``). All
    figures in integer cents. ``total_escrow_paid_cents`` is honestly ``0`` —
    no payout has run (disbursement is gated)."""

    pre_onboarded: int
    invited: int
    claimed: int
    opted_out: int
    claim_rate: float
    total_escrow_accrued_cents: int
    total_escrow_paid_cents: int
    unclaimed_escrow_cents: int
    publishers_with_nontrivial_accrual: int


class ConsentViewResponse(BaseModel):
    """Per-IP-holder consent / escrow (accruing) / servability + the escrow
    report. ``any_disbursable`` is ``False`` while either legal gate is open —
    the property an auditor checks ("did anyone get paid before the legal
    gate?"). ``disbursement_gates_open`` is read live from the SPR-05 ledger."""

    holders: list[IpHolderConsentResponse]
    escrow_report: EscrowReportResponse
    disbursement_gates_open: list[str]
    total_escrow_accruing_usd: str
    any_disbursable: bool
    gate_source_path: str

    @classmethod
    def from_consent_view(cls, cv: ConsentView) -> ConsentViewResponse:
        rep = cv.escrow_report
        return cls(
            holders=[IpHolderConsentResponse.from_row(h) for h in cv.holders],
            escrow_report=EscrowReportResponse(
                pre_onboarded=rep.status_counts.pre_onboarded,
                invited=rep.status_counts.invited,
                claimed=rep.status_counts.claimed,
                opted_out=rep.status_counts.opted_out,
                claim_rate=rep.status_counts.claim_rate,
                total_escrow_accrued_cents=rep.total_escrow_accrued_cents,
                total_escrow_paid_cents=rep.total_escrow_paid_cents,
                unclaimed_escrow_cents=rep.unclaimed_escrow_cents,
                publishers_with_nontrivial_accrual=rep.publishers_with_nontrivial_accrual,
            ),
            disbursement_gates_open=list(cv.disbursement_gates_open),
            total_escrow_accruing_usd=str(cv.total_escrow_accruing_usd),
            any_disbursable=cv.any_disbursable,
            gate_source_path=cv.gate_source_path,
        )


def _resolve_db_path() -> str:
    """The substrate DB path — resolved the same way the other read-only
    endpoints do (``creator_payouts``). Imported lazily so importing this
    module does not pull the graph package at module load."""
    from substrate.graph import default_db_path, ensure_initialized

    path = default_db_path()
    ensure_initialized(path)
    return path


def _build_adrb_dogfood_status(db_path: str) -> AdrbDogfoodStatusResponse:
    try:
        return AdrbDogfoodStatusResponse.from_readiness(
            audit_dogfood_readiness(db_path)
        )
    except Exception as exc:  # pragma: no cover - exact DB error varies by DuckDB
        return AdrbDogfoodStatusResponse.from_error(exc)


# ── Routes (GET-only — no writer imported, no mutating verb) ─────────────────

def register_coordination_routes(app: FastAPI) -> None:
    """Mount the read-only coordination routes. Pattern matches
    ``register_federation_routes``. There is deliberately NO POST/PUT/PATCH/
    DELETE here — gate state changes only in the operator's source file."""

    @app.get(
        "/coordination/gates",
        response_model=GateLedgerResponse,
        tags=["coordination"],
    )
    async def get_gates() -> GateLedgerResponse:
        """The gate ledger — read fresh from docs/operator_gate_actions.md on
        every request. A view, never a fork."""
        ledger: GateLedger = load_gate_ledger()
        return GateLedgerResponse(
            source_path=ledger.source_path,
            gates=[GateResponse.from_gate(g) for g in ledger.gates],
        )

    @app.get(
        "/coordination/roadmap",
        response_model=RoadmapResponse,
        tags=["coordination"],
    )
    async def get_roadmap() -> RoadmapResponse:
        """The cross-spec roadmap — 45 sprints reconciled from the real roster
        files + SPR-01's dependency DAG, DRW critical path explicit, dependency
        blockers and execution focus derived from dependency state."""
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            loop3 = build_loop3_coordination_view(con)
        finally:
            con.close()
        return RoadmapResponse.from_roadmap(
            build_roadmap(),
            load_gate_ledger(),
            build_read_activation_view(),
            _build_adrb_dogfood_status(db),
            build_branch_health(),
            load_operator_actions(),
            load_phase2_audit(),
            load_engineering_deferrals(),
            loop3,
            build_source_gate_view(),
        )

    @app.get(
        "/coordination/source-gate",
        response_model=SourceGateResponse,
        tags=["coordination"],
    )
    async def get_source_gate() -> SourceGateResponse:
        """The source-onboarding gate — read fresh from reports/source_census.json
        so acquisition surfaces can show the exact gate without loading the full
        roadmap. A missing census is an honest no-op state, not a failure."""
        return SourceGateResponse.from_view(build_source_gate_view())

    @app.get(
        "/coordination/cost",
        response_model=CostViewResponse,
        tags=["coordination"],
    )
    async def get_cost() -> CostViewResponse:
        """Per-workflow + aggregate realized inference cost — summed from the
        canonical ``DispatchCall`` event log (incl. SPR-02 remote-exec). Margins
        applied only where the economics matrix is built and contextualized;
        honestly stubbed otherwise. Idle ⇒ every figure ``"0"``. Read-only — no
        cost is written and no money moves."""
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            speak_context = speak_policy_by_investigation_from_db(con)
        finally:
            con.close()
        return CostViewResponse.from_cost_view(
            build_cost_view(speak_policy_by_investigation=speak_context)
        )

    @app.get(
        "/coordination/consent",
        response_model=ConsentViewResponse,
        tags=["coordination"],
    )
    async def get_consent() -> ConsentViewResponse:
        """Per-IP-holder consent / escrow (accruing, gated on G2+G3 read from the
        SPR-05 ledger) / servability (SPR-03 seam). Accrual ≠ disbursement: every
        balance is labeled, ``any_disbursable`` is ``False`` while a legal gate is
        open, and a zero-buyer balance is honestly ``"0"``. Read-only — the
        DuckDB connection is opened ``read_only=True``; no escrow write, no payout
        path."""
        db = _resolve_db_path()
        con = duckdb.connect(db, read_only=True)
        try:
            view = build_consent_view(con)
        finally:
            con.close()
        return ConsentViewResponse.from_consent_view(view)
