"""``substrate.coordination`` — the read-only coordination layer (antiek-unified SPR-05).

One operator surface for "what's blocked and why." Two views, both **derived on
read** from canonical sources this package never writes:

* :mod:`substrate.coordination.gate_ledger` parses ``docs/operator_gate_actions.md``
  — the single source of gate truth — into a typed ledger, and pairs each gate
  with a per-product impact map (which of Research/Read/Write/Speak it blocks
  and how). It is a VIEW: it never stores a second copy of gate state, and there
  is no write path back to the markdown.

* :mod:`substrate.coordination.roadmap` ingests the five live specs' sprint
  rosters (DRW 10 + Read 9 + Write 9 + Speak 9 + unified 8 = 45; the shell's 6
  are superseded, not counted) plus SPR-01's ``dependency_map`` DAG, and computes
  the dependency-ready set (serialized as ``unblocked_now`` for the existing API)
  — with the DRW critical path (``drw:1 → drw:3 → drw:10``) surfaced explicitly.

* :mod:`substrate.coordination.cost_view` aggregates realized ``DispatchCall``
  inference cost per workflow + in aggregate (incl. SPR-02 remote-exec), reading
  the canonical event log; margins applied only where the economics matrix is
  built, else honestly stubbed (SPR-07).

* :mod:`substrate.coordination.consent_view` surfaces per-IP-holder consent /
  escrow (accruing, gated on G2+G3 read from the gate ledger) / servability
  (the SPR-03 seam) — accrual ≠ disbursement, with NO disbursement path (SPR-07).

* :mod:`substrate.coordination.activation_view` surfaces the Read activation
  dogfood counters from ``reports/read-dogfood.jsonl`` using the same validator
  as ``tools.activation.read_dogfood``. It is status only; the CLI + operator
  verdict remain the closure authority.

* :mod:`substrate.coordination.operator_actions` surfaces the broader OA-001+
  operator-only living index from ``docs/OPERATOR_ACTIONS.md`` as read-only
  status, so counsel/publisher/deploy tasks do not live only in prose.

* :mod:`substrate.coordination.phase2_audit` surfaces the Phase 2 audit
  scorecard + v5 reconciliation as read-only status, so sprint-level execution
  truth is visible beside roadmap dependency state.

* :mod:`substrate.coordination.engineering_deferrals` surfaces the explicit
  "do not pre-build" deferral ledger from ``docs/engineering_deferrals.md``.

* :mod:`substrate.coordination.loop3_status` summarizes the G8/Loop-3 manual
  checklist plus verifier evidence without mutating or authorizing training.

* :mod:`substrate.coordination.source_gate_status` surfaces the source-onboarding
  corpus-value kill-gate without writing the operator-produced census.

The binding rule for the whole package: **integration, not duplication — the
ledger is a view over the source, never a second gate store.** If the operator
edits the gate file or a roster changes, the dashboard reflects it on next read.
"""

from __future__ import annotations

from .activation_view import (
    ReadActivationView,
    build_read_activation_view,
    default_read_dogfood_log_path,
)
from .consent_view import (
    ConsentView,
    DisbursementGate,
    IpHolderConsentRow,
    build_consent_view,
)
from .cost_view import (
    CostView,
    MarginStatus,
    Workflow,
    WorkflowCost,
    build_cost_view,
    workflow_for_role,
)
from .engineering_deferrals import (
    DeferralStatus,
    EngineeringDeferral,
    EngineeringDeferralsView,
    load_engineering_deferrals,
    parse_engineering_deferrals,
)
from .gate_ledger import (
    Gate,
    GateImpact,
    GateLedger,
    GateStatus,
    Product,
    load_gate_ledger,
    parse_gate_ledger,
)
from .loop3_status import (
    Loop3CoordinationView,
    Loop3CriterionStatus,
    build_loop3_coordination_view,
)
from .operator_actions import (
    OperatorAction,
    OperatorActionsView,
    OperatorActionStatus,
    load_operator_actions,
    parse_operator_actions,
)
from .phase2_audit import (
    Phase2AuditView,
    Phase2ExitCriteria,
    Phase2SprintScore,
    load_phase2_audit,
    parse_phase2_audit,
    parse_phase2_scorecard,
)
from .roadmap import (
    DependencyBlocker,
    Roadmap,
    SpecRoster,
    SprintRow,
    SprintStatus,
    build_roadmap,
)
from .source_gate_status import (
    SourceGateRow,
    SourceGateView,
    build_source_gate_view,
)

__all__ = [
    # activation view
    "ReadActivationView",
    "build_read_activation_view",
    "default_read_dogfood_log_path",
    # gate ledger
    "Gate",
    "GateImpact",
    "GateLedger",
    "GateStatus",
    "Product",
    "load_gate_ledger",
    "parse_gate_ledger",
    # loop 3 status
    "Loop3CoordinationView",
    "Loop3CriterionStatus",
    "build_loop3_coordination_view",
    # operator actions
    "OperatorAction",
    "OperatorActionStatus",
    "OperatorActionsView",
    "load_operator_actions",
    "parse_operator_actions",
    # phase 2 audit
    "Phase2AuditView",
    "Phase2ExitCriteria",
    "Phase2SprintScore",
    "load_phase2_audit",
    "parse_phase2_audit",
    "parse_phase2_scorecard",
    # roadmap
    "DependencyBlocker",
    "Roadmap",
    "SprintRow",
    "SprintStatus",
    "SpecRoster",
    "build_roadmap",
    # source gate
    "SourceGateRow",
    "SourceGateView",
    "build_source_gate_view",
    # cost view (SPR-07)
    "CostView",
    "MarginStatus",
    "Workflow",
    "WorkflowCost",
    "build_cost_view",
    "workflow_for_role",
    # engineering deferrals
    "DeferralStatus",
    "EngineeringDeferral",
    "EngineeringDeferralsView",
    "load_engineering_deferrals",
    "parse_engineering_deferrals",
    # consent view (SPR-07)
    "ConsentView",
    "DisbursementGate",
    "IpHolderConsentRow",
    "build_consent_view",
]
