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
  what's unblocked-now from the dependency state — with the DRW critical path
  (``drw:1 → drw:3 → drw:10``) surfaced explicitly.

* :mod:`substrate.coordination.cost_view` aggregates realized ``DispatchCall``
  inference cost per workflow + in aggregate (incl. SPR-02 remote-exec), reading
  the canonical event log; margins applied only where the economics matrix is
  built, else honestly stubbed (SPR-07).

* :mod:`substrate.coordination.consent_view` surfaces per-IP-holder consent /
  escrow (accruing, gated on G2+G3 read from the gate ledger) / servability
  (the SPR-03 seam) — accrual ≠ disbursement, with NO disbursement path (SPR-07).

The binding rule for the whole package: **integration, not duplication — the
ledger is a view over the source, never a second gate store.** If the operator
edits the gate file or a roster changes, the dashboard reflects it on next read.
"""

from __future__ import annotations

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
from .gate_ledger import (
    Gate,
    GateImpact,
    GateLedger,
    GateStatus,
    Product,
    load_gate_ledger,
    parse_gate_ledger,
)
from .roadmap import (
    Roadmap,
    SpecRoster,
    SprintRow,
    SprintStatus,
    build_roadmap,
)

__all__ = [
    # gate ledger
    "Gate",
    "GateImpact",
    "GateLedger",
    "GateStatus",
    "Product",
    "load_gate_ledger",
    "parse_gate_ledger",
    # roadmap
    "Roadmap",
    "SprintRow",
    "SprintStatus",
    "SpecRoster",
    "build_roadmap",
    # cost view (SPR-07)
    "CostView",
    "MarginStatus",
    "Workflow",
    "WorkflowCost",
    "build_cost_view",
    "workflow_for_role",
    # consent view (SPR-07)
    "ConsentView",
    "DisbursementGate",
    "IpHolderConsentRow",
    "build_consent_view",
]
