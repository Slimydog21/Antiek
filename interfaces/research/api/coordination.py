"""Coordination API — read-only HTTP surface for the gate ledger + roadmap (SPR-05 M3).

Thin adapter over :mod:`substrate.coordination`. Two GET endpoints, no writes:

  GET /coordination/gates     the gate ledger (a view over operator_gate_actions.md)
  GET /coordination/roadmap   the 45-sprint roadmap + DRW critical path + unblocked-now

**Read-only is enforced, not promised (rigor #5).** This module imports only the
read entry points (``load_gate_ledger`` / ``build_roadmap``); there is no import
of any writer (``connect_write``, an escrow writer, the gate file's path for
writing) and no POST/PUT/PATCH/DELETE route. A future maintainer confirms "the
coordination surface cannot change a gate" by the absence of any such path here
— greppable, and asserted in ``tests/test_coordination_no_fork.py`` for the
substrate modules this adapter wraps.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

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
    def from_gate(cls, g: Gate) -> "GateResponse":
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
    def from_row(cls, s: SprintRow) -> "SprintResponse":
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
    def from_roadmap(cls, rm: Roadmap) -> "RoadmapResponse":
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
                SubstrateLayerResponse(name=l.name, owner=l.owner, status=l.status)
                for l in rm.substrate_layers
            ],
        )


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
