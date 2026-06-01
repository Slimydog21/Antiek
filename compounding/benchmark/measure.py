"""AFF SPR-09 M3 — cost-to-resolve measurement from the shipped accounting.

Reads ONE investigation's typed event-log trajectory and produces its
cost-to-resolve vector. Every field is read off the trajectory that production
already writes — there is NO home-grown token meter here (the no-home-grown-meter
verification gate over this package returns nothing).

The unit of cost is the SAME number production bills against: each
``dispatch.call`` event carries a ``cost_usd`` computed by the single
``_compute_cost_usd`` at ``substrate/dispatch/router.py:228`` ("One place
computes cost. Adapters do not."). We sum that field. A delta computed on a
re-derived pricing table would not be comparable to production and is rejected
by the spec; this module references ``cost_usd`` and ``_compute_cost_usd`` only.

Field sourcing (OPERATOR_INPUTS §2, verified against main):

  * ``token_cost_usd``         — Σ ``payload.cost_usd`` over ``dispatch.call``.
  * ``input_tokens`` /
    ``output_tokens``          — Σ over ``dispatch.call`` payloads.
  * ``sources_fetched``        — count of ``connector.delivered`` +
                                 ``evidence.retrieve.delivered`` events.
  * ``wall_ms``                — ``max(emitted_at) − min(emitted_at)`` over the
                                 trajectory (ISO-8601 Z), cross-checked against
                                 summed ``latency_ms`` and reported alongside.
  * ``novel_insight_yield``    — count of ``graph.node.inserted`` events.
  * ``redundant_rederivations``— see ``count_redundant_rederivations``: node ids
                                 are content-addressed, so a re-emit of an
                                 already-seeded node yields the same id and NO new
                                 insert. The signal is the gap between insert
                                 *attempts* and *distinct* inserted ids — derived
                                 from the seeded set, not from a bespoke counter.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from substrate.event_log import trajectory as _trajectory
except ImportError:  # pragma: no cover — direct-script fallback
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from substrate.event_log import trajectory as _trajectory  # type: ignore[no-redef]


# Action-type string constants — read from the trajectory rows, which carry the
# ``ActionType`` enum *values* (events.py). Named here so the measurement reads
# like the §2 sourcing table; they are the same strings the enum emits.
ACTION_DISPATCH_CALL = "dispatch.call"
ACTION_CONNECTOR_DELIVERED = "connector.delivered"
ACTION_EVIDENCE_RETRIEVE_DELIVERED = "evidence.retrieve.delivered"
ACTION_GRAPH_NODE_INSERTED = "graph.node.inserted"
_SOURCE_ACTIONS = frozenset({ACTION_CONNECTOR_DELIVERED, ACTION_EVIDENCE_RETRIEVE_DELIVERED})


@dataclass(frozen=True)
class CostToResolve:
    """One arm-run's measured cost-to-resolve. All six §2 metrics + the
    cross-check fields. Plain floats/ints so the artifact serializes directly."""

    token_cost_usd: float
    input_tokens: int
    output_tokens: int
    sources_fetched: int
    wall_ms: float
    novel_insight_yield: int
    redundant_rederivations: int
    # Cross-check, not headline: summed per-call latency. Reported so a reviewer
    # can see whether wall-clock (span) and worked-time (Σ latency) agree.
    summed_latency_ms: int = 0
    dispatch_calls: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_emitted_at(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 ``emitted_at`` (the event log writes ``...Z``).
    Returns None for a missing/unparseable timestamp so a partial trajectory
    degrades gracefully rather than crashing the measurement."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:  # pragma: no cover — defensive against legacy rows
        return None


def _payload(row: Dict[str, Any]) -> Dict[str, Any]:
    p = row.get("payload")
    return p if isinstance(p, dict) else {}


def measure_trajectory(
    rows: Sequence[Dict[str, Any]],
    *,
    seeded_node_ids: Optional[Iterable[str]] = None,
) -> CostToResolve:
    """Compute the cost-to-resolve vector from a list of trajectory rows.

    ``seeded_node_ids`` (the warm/irrelevant arm's pre-seeded node ids) lets the
    redundant-rederivation count be exact: a ``graph.node.inserted`` whose
    ``node_id`` is already in the seeded set is a re-derivation the warm graph
    should have short-circuited (content-addressed id collision). For the cold
    arm — which has no seed — the seeded set is empty and the count is 0.

    Pure over its input rows: deterministic, no I/O. A unit test feeds a
    synthetic trajectory of known events and asserts exact counts (M3
    acceptance)."""
    seeded = set(seeded_node_ids or ())

    token_cost = 0.0
    input_tokens = 0
    output_tokens = 0
    summed_latency = 0
    dispatch_calls = 0
    sources = 0
    inserted_ids: List[str] = []
    times: List[datetime] = []

    for row in rows:
        action = row.get("action_type")
        ts = _parse_emitted_at(row.get("emitted_at"))
        if ts is not None:
            times.append(ts)

        if action == ACTION_DISPATCH_CALL:
            p = _payload(row)
            # cost_usd is the field _compute_cost_usd populated; summed here,
            # never re-derived from tokens × price.
            token_cost += float(p.get("cost_usd", 0.0) or 0.0)
            input_tokens += int(p.get("input_tokens", 0) or 0)
            output_tokens += int(p.get("output_tokens", 0) or 0)
            summed_latency += int(p.get("latency_ms", 0) or 0)
            dispatch_calls += 1
        elif action in _SOURCE_ACTIONS:
            sources += 1
        elif action == ACTION_GRAPH_NODE_INSERTED:
            nid = _payload(row).get("node_id")
            if nid is not None:
                inserted_ids.append(str(nid))

    wall_ms = 0.0
    if len(times) >= 2:
        wall_ms = (max(times) - min(times)).total_seconds() * 1000.0

    # A content-addressed re-emit of an already-seeded node produces no NEW
    # insert event (insert_node short-circuits on conflict), so an emitted insert
    # whose id is in the seeded set means the loop tried to re-store something the
    # graph already had — the re-derivation signal. ``novel_insight_yield`` counts
    # only the inserts that landed a node NOT already seeded.
    novel = [nid for nid in inserted_ids if nid not in seeded]
    redundant = len(inserted_ids) - len(novel)

    return CostToResolve(
        token_cost_usd=round(token_cost, 10),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        sources_fetched=sources,
        wall_ms=round(wall_ms, 3),
        novel_insight_yield=len(novel),
        redundant_rederivations=redundant,
        summed_latency_ms=summed_latency,
        dispatch_calls=dispatch_calls,
    )


def measure_investigation(
    investigation_id: str,
    *,
    events_dir: Optional[str] = None,
    seeded_node_ids: Optional[Iterable[str]] = None,
) -> CostToResolve:
    """Read an investigation's trajectory off the event log and measure it.

    Thin wrapper over :func:`measure_trajectory` that does the one I/O read via
    the shipped ``substrate.event_log.trajectory`` (Parquet-if-sealed, else
    JSONL) — the same read path analytics use, not a bespoke reader."""
    rows = _trajectory(investigation_id, events_dir=events_dir)
    return measure_trajectory(rows, seeded_node_ids=seeded_node_ids)


# The metric names a delta is computed over. ``token_cost_usd`` is the headline
# (§2); the rest are corroborating / diagnostic. Ordered so the artifact + the
# README read the same.
METRIC_NAMES: tuple[str, ...] = (
    "token_cost_usd",
    "sources_fetched",
    "wall_ms",
    "novel_insight_yield",
    "redundant_rederivations",
)
