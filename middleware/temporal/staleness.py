"""Staleness rule (Researchmaxx spec §D.3).

Pure-function temporal layer: given a graph edge's relation and age,
decide whether it should be flagged for refresh. The TTL per claim
class lives in ``substrate.constants.STALENESS_TTL_DAYS`` so tuning is
one-file and traceable.

Stale flags are **advisory** — they queue the entity for refresh in the
next investigation that touches it, NOT auto-invalidate the claim.
That asymmetry is by design (architecture_notes §4).

Migrated from
``~/.hermes/skills/research/graph-research-substrate/scripts/staleness.py``
(2026-05-16). The pure rule logic and emit helpers land here; the
DB-touching ``scan()`` is deferred until the ``edges`` and
``stale_flags`` tables exist in Antiek.
"""

from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass

try:
    from ...constants import RELATION_TO_CLAIM_CLASS, STALENESS_TTL_DAYS
    from ...event_log import emit_typed
    from ...schemas import StalenessFlaggedPayload, StalenessResolvePayload
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        RELATION_TO_CLAIM_CLASS,
        STALENESS_TTL_DAYS,
    )
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        StalenessFlaggedPayload,
        StalenessResolvePayload,
    )


# ---------------------------------------------------------------------------
# Pure rule logic
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StalenessVerdict:
    """Result of evaluating one edge for staleness. ``is_stale`` is the
    binary outcome. ``claim_class`` is None when the relation isn't
    classifiable — in that case the edge is skipped (not flagged).
    """

    is_stale: bool
    claim_class: str | None
    ttl_days: int | None
    age_days: int


def classify_relation(relation: str | None) -> str | None:
    """Map a graph relation string → claim_class key in STALENESS_TTL_DAYS.
    Returns None when no mapping is known (heuristic substring match
    handled here for slight variations like ``raised_series_a``)."""
    if not relation:
        return None
    rel = relation.lower().strip()
    if rel in RELATION_TO_CLAIM_CLASS:
        return RELATION_TO_CLAIM_CLASS[rel]
    # Substring fallback so suffixed variants are caught.
    for key, cls in RELATION_TO_CLAIM_CLASS.items():
        if key in rel:
            return cls
    return None


def evaluate_staleness(relation: str | None, age_days: int) -> StalenessVerdict:
    """Decide whether an edge with the given relation and age is stale.

    Returns a ``StalenessVerdict``. The scanner walks edges, calls this
    once per edge, and emits ``GRAPH_STALENESS_FLAGGED`` for each
    verdict where ``is_stale`` is True.
    """
    if age_days < 0:
        raise ValueError(f"age_days must be non-negative, got {age_days}")

    claim_class = classify_relation(relation)
    if claim_class is None:
        return StalenessVerdict(
            is_stale=False, claim_class=None, ttl_days=None, age_days=age_days,
        )
    ttl = STALENESS_TTL_DAYS[claim_class]
    return StalenessVerdict(
        is_stale=age_days > ttl,
        claim_class=claim_class,
        ttl_days=ttl,
        age_days=age_days,
    )


# ---------------------------------------------------------------------------
# Event emit helpers
# ---------------------------------------------------------------------------


def new_flag_id() -> str:
    """Allocate a fresh stable id for a stale flag. Mirrors the original
    Researchmaxx flag_id format (uuid4)."""
    return str(uuid.uuid4())


def emit_staleness_flagged(
    *,
    investigation_id: str,
    flag_id: str,
    edge_id: str,
    relation: str,
    claim_class: str,
    ttl_days: int,
    age_days: int,
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a GRAPH_STALENESS_FLAGGED event. Returns event_id."""
    return emit_typed(
        investigation_id,
        StalenessFlaggedPayload(
            flag_id=flag_id,
            edge_id=edge_id,
            relation=relation,
            claim_class=claim_class,
            ttl_days=ttl_days,
            age_days=age_days,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",  # the closest role catalog match; staleness scanner runs as a system role
    )


def emit_staleness_resolve(
    *,
    investigation_id: str,
    flag_id: str,
    entity_kind: str,
    entity_id: str,
    status: str,
    notes: str = "",
    parent_event_id: str | None = None,
) -> str | None:
    """Emit a STALENESS_RESOLVE event when a flag is resolved.

    ``status`` must be one of {"refreshed", "confirmed_stale", "dismissed"}
    (enforced by the Pydantic Literal on StalenessResolvePayload).
    ``entity_kind`` is currently always 'edge' but the Literal allows
    'node' for future expansion.
    """
    return emit_typed(
        investigation_id,
        StalenessResolvePayload(
            flag_id=flag_id,
            entity_kind=entity_kind,  # type: ignore[arg-type]
            entity_id=entity_id,
            status=status,  # type: ignore[arg-type]
            notes=notes,
        ),
        parent_event_id=parent_event_id,
        role="tier_assigner",
    )
