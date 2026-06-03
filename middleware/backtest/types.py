"""Backtest input/output dataclasses.

Mirrors Researchmaxx ``scripts/backtest.py`` shapes. As with cohort,
the DB-touching pieces (``graph_at_time.diff_between`` +
``archive.load_synthesis``) are deferred to the slice that wires
``substrate/init_db.py`` to the syntheses/edges/chunk_tier_overrides
tables. The pure pieces ship now so the schema and the bridge can
proceed in parallel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ArchivedSynthesis:
    """The fields ``backtest()`` reads off an archived synthesis row.

    Mirrors the output of the upstream ``archive.load_synthesis``;
    Sprint 5+ extracts that loader to ``middleware/archive/``."""

    synthesis_id: str
    synthesis_timestamp: str
    target_question: str
    status: str
    implicit_recommendation: str | None
    substrate_manifest: dict[str, Any] = field(default_factory=dict)
    substrate_manifest_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SupersededEdge:
    """One cited edge that has since been superseded."""

    edge_id: str
    superseded_by: str | None
    valid_until: str
    source: str
    target: str
    relation: str


@dataclass(frozen=True)
class ChunkTierChange:
    """One cited chunk that has since been re-tiered downward."""

    chunk_id: str
    original_tier: int
    override_tier: int
    reason: str
    set_at: str


@dataclass(frozen=True)
class BacktestReport:
    """The shape ``backtest()`` returns. JSON-serializable through
    ``dataclasses.asdict``; the operator CLI renders it to markdown."""

    synthesis_id: str
    synthesis_timestamp: str
    target_question: str
    status: str
    implicit_recommendation: str | None
    substrate_manifest_counts: dict[str, int]
    added_edges_since: int
    superseded_edges_since: int
    cited_edges_now_superseded: tuple[SupersededEdge, ...]
    chunks_retired_downward: tuple[ChunkTierChange, ...]
    outcomes: tuple[dict[str, Any], ...]

    @property
    def load_bearing_edges_invalidated(self) -> int:
        return len(self.cited_edges_now_superseded)

    @property
    def cited_chunks_demoted(self) -> int:
        return len(self.chunks_retired_downward)

    @property
    def outcomes_recorded(self) -> int:
        return len(self.outcomes)
