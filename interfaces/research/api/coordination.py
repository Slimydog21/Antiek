"""Coordination API — read-only HTTP surface for gates + roadmap + cost + consent.

Thin adapter over :mod:`substrate.coordination`. Four GET endpoints, no writes:

  GET /coordination/gates     the gate ledger (a view over operator_gate_actions.md)
  GET /coordination/roadmap   the 45-sprint roadmap + DRW critical path + unblocked-now
  GET /coordination/cost      per-workflow + aggregate inference cost (SPR-07)
  GET /coordination/consent   per-IP-holder consent / escrow (accruing) / servability (SPR-07)

**Read-only is enforced, not promised (rigor #5).** This module imports only
read entry points (``load_gate_ledger`` / ``build_roadmap`` / ``build_cost_view`` /
``build_consent_view``); there is no import of any writer (``connect_write``, the
escrow writer ``ip_holders.accrue_escrow``, the gate file's path for writing) and
**no import of any payout module** (``tools.stripe_connect.payouts``). There is
no POST/PUT/PATCH/DELETE route. The consent endpoint opens its DuckDB connection
``read_only=True``. A future maintainer (or auditor) confirms "the coordination
surface cannot change a gate, move escrow, or disburse a payout" by the absence
of any such path here — greppable, and asserted in
``tests/test_coordination_no_fork.py`` (gates/roadmap) and
``tests/test_cost_consent_no_disbursement.py`` (cost/consent, SPR-07).
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from runtime.db_lock import connect_read
from substrate.coordination.consent_view import (
    ConsentView,
    IpHolderConsentRow,
    build_consent_view,
)
from substrate.coordination.cost_view import (
    CostView,
    WorkflowCost,
    build_cost_view,
)
from substrate.coordination.gate_ledger import (
    Gate,
    GateLedger,
    load_gate_ledger,
)
from substrate.coordination.roadmap import (
    Roadmap,
    SprintRow,
    build_roadmap,
)

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


class RoadmapResponse(BaseModel):
    total_sprints: int
    superseded_count: int
    superseded_note: str
    reconciliation: str
    critical_path: list[str]
    rosters: list[RosterResponse]
    unblocked_now: list[str]      # node ids
    substrate_layers: list[SubstrateLayerResponse]

    @classmethod
    def from_roadmap(cls, rm: Roadmap) -> RoadmapResponse:
        return cls(
            total_sprints=rm.total_sprints,
            superseded_count=rm.superseded_count,
            superseded_note=rm.superseded_note,
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
            substrate_layers=[
                SubstrateLayerResponse(
                    name=layer.name, owner=layer.owner, status=layer.status
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
        files + SPR-01's dependency DAG, DRW critical path explicit, unblocked-
        now derived from dependency state."""
        return RoadmapResponse.from_roadmap(build_roadmap())

    @app.get(
        "/coordination/cost",
        response_model=CostViewResponse,
        tags=["coordination"],
    )
    async def get_cost() -> CostViewResponse:
        """Per-workflow + aggregate realized inference cost — summed from the
        canonical ``DispatchCall`` event log (incl. SPR-02 remote-exec). Margins
        applied only where the economics matrix is built; honestly stubbed
        otherwise. Idle ⇒ every figure ``"0"``. Read-only — no cost is written
        and no money moves."""
        return CostViewResponse.from_cost_view(build_cost_view())

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
        con = connect_read(db)
        try:
            view = build_consent_view(con)
        finally:
            con.close()
        return ConsentViewResponse.from_consent_view(view)
