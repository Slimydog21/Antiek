"""Read-only surface over the continuous daemon's scored gaps (SPR-09).

The §7.3/§7.4 daemon already scans the event log, builds a ``GapRegistry``,
and scores each evidentiary gap (``orchestration.continuous.scoring``). This
module turns that *existing* output into plain-language "suggested next
researches" the product can render — and nothing more.

What this is NOT:
  - It does NOT re-compute scores with a different formula. It calls the
    daemon's own ``score_gap`` so the surface ranks gaps exactly the way the
    daemon would chase them. One scorer, one truth.
  - It does NOT spawn, reserve budget, or run the daemon. Building suggestions
    is a pure read of the event log; surfacing costs nothing (SPR-09's
    load-bearing invariant). The only spend is an explicit operator chase
    click, which goes through the existing capped launch path — not here.
  - It does NOT change the §7.4 caps. It imports ``MAX_CHASE_COUNT`` to honour
    the daemon's decay rule (a gap chased to exhaustion is not re-suggested),
    but it owns no cap of its own beyond a display count.

Dedupe (SPR-09 M2): a gap already chased — by the daemon OR by the operator —
is not re-suggested. We detect "already chased" two ways, both read-only:
  1. The daemon's decay: ``score_gap`` returns 0 once a gap has been chased
     ``MAX_CHASE_COUNT`` times, so it falls below ``min_score`` and drops out.
  2. The underlying-question match: any investigation whose START question
     normalizes to the gap's key is a chase of that gap (an operator following
     the thread, or a daemon-spawned chase). Such gaps are excluded so the
     surface never offers a thread the user already pulled.

Distinction (SPR-09 M3): daemon-spawned chases carry the daemon's
``spawn_policy_id`` ("continuous_daemon") on their start event. The product
reads that to badge a research as "found by the loop" — the ``policy_id`` is
translated, never shown. ``DAEMON_SPAWN_POLICY_ID`` is the single source of
that string so the surface and the daemon can't drift.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from substrate.event_log.events import default_events_dir, trajectory

from .daemon import DaemonConfig, _list_investigation_ids, scan_gaps
from .scoring import normalize_gap_description, score_gap

#: The policy_id a daemon-spawned chase carries on its start event. Mirrors
#: ``DaemonConfig.spawn_policy_id`` — kept here as the public, importable
#: constant the API layer translates into the "found by the loop" badge so the
#: surface and the daemon agree on one string.
DAEMON_SPAWN_POLICY_ID: str = DaemonConfig.spawn_policy_id

#: How many suggestions the surface shows by default. A flood of low-score
#: gaps must be ranked and capped, not dumped (rigor #3); this is a *display*
#: limit, not a daemon budget/cadence cap — it changes nothing about how or
#: when the daemon runs.
DEFAULT_MAX_SUGGESTIONS: int = 8


@dataclass(frozen=True)
class Suggestion:
    """One plain-language "thread worth chasing", derived from a scored gap.

    Carries only what the surface needs. ``score`` is the daemon's own score
    (for ranking — the surface does not show the number); ``source_*`` ground
    the suggestion in the research it came from so it reads as legible, not
    magical. The normalized gap key is the dedupe identity, opaque to the user.
    """

    #: Stable dedupe identity (the gap's normalized key). Opaque handle, never
    #: rendered — it is the "underlying question" the dedupe keys on.
    key: str
    #: The gap text, as the evidence_retriever phrased it — the plain-language
    #: thread. No "evidentiary_gap" / "chase score" / "policy_id" vocabulary.
    question: str
    #: Optional retrieval hint the gap carried ("check §14.4"), surfaced as
    #: context. None when the gap carried no hint.
    suggested_retrieval: str | None
    #: How many distinct researches surfaced this gap (the "many runs flagged
    #: this" signal), for an honest "seen across N researches" line.
    seen_in_research_count: int
    #: A representative source research id the gap came from, so the surface
    #: can link back to where the thread originated. None only if the registry
    #: somehow has no investigation_ids (defensive).
    source_investigation_id: str | None
    #: The daemon's own composite score (recency × co-occurrence ×
    #: interaction). Used only for ranking; never rendered.
    score: float


def _chased_question_keys(events_dir: str) -> set[str]:
    """Normalized-question keys of every research already launched.

    A research's START question (operator chase) or a leaf's ``sub_question``
    (cascade/daemon spawn) that normalizes to a gap's key means that gap has
    been pulled — by the operator or the loop. Returning the set lets the
    suggestion builder exclude already-chased gaps (dedupe on the underlying
    question), independent of the daemon's chase-count decay. Pure read.
    """
    keys: set[str] = set()
    for iid in _list_investigation_ids(events_dir):
        for ev in trajectory(iid, events_dir=events_dir):
            at = ev.get("action_type")
            if at not in (
                "investigation.start_requested",
                "investigation.spawned_from",
            ):
                continue
            payload = ev.get("payload") or {}
            text = (
                payload.get("question")
                or payload.get("sub_question")
                or payload.get("spawn_context")
                or ""
            )
            if text.strip():
                keys.add(normalize_gap_description(text))
    return keys


def build_suggestions(
    *,
    events_dir: str | None = None,
    max_suggestions: int = DEFAULT_MAX_SUGGESTIONS,
    min_score: float = 0.0,
    now: datetime | None = None,
) -> list[Suggestion]:
    """Read the daemon's scored gaps and return ranked plain-language
    suggestions. Read-only: scans the event log, scores with the daemon's own
    ``score_gap``, dedupes against already-chased gaps, ranks, and caps the
    count. Spawns nothing, reserves no budget, runs no daemon.

    Returns ``[]`` when there are no gaps (no daemon output / no keys to have
    produced any) — the honest empty state, never a fabricated thread.
    """
    resolved = events_dir or default_events_dir()
    if not os.path.isdir(resolved):
        return []

    # Two passes over the event log here are deliberate, not an oversight.
    # scan_gaps is the daemon's OWN scanner — reused verbatim so there is one
    # scorer and one truth, never re-implemented; _chased_question_keys reads the
    # launch history. Folding these into a single read would force either editing
    # the daemon's scan_gaps (which must stay §7.4-byte-unchanged) or
    # re-implementing gap scoring here (forking the one truth). Both are worse
    # than a second read at single-operator scale — do not "optimize" into either.
    registry = scan_gaps(events_dir=resolved)
    chased = _chased_question_keys(resolved)

    scored: list[Suggestion] = []
    for entry in registry.values():
        # Dedupe path 1 — the daemon's decay: a gap chased to exhaustion
        # scores 0 (and below min_score), so it drops out here without any
        # special-casing. We never re-suggest a worn-out branch.
        s = score_gap(entry, now=now)
        if s <= min_score:
            continue
        # Dedupe path 2 — the underlying-question match: a gap whose question
        # has already been launched (operator chase or daemon spawn) is not
        # offered again, even if the daemon hasn't recorded the chase against
        # this registry entry yet.
        if entry.normalized_key in chased:
            continue
        scored.append(
            Suggestion(
                key=entry.normalized_key,
                question=entry.gap_description,
                suggested_retrieval=entry.additional_retrieval_suggested,
                seen_in_research_count=entry.co_occurrence,
                source_investigation_id=(
                    entry.investigation_ids[0] if entry.investigation_ids else None
                ),
                score=s,
            )
        )

    # Rank by the daemon's score (descending), then cap the displayed count.
    scored.sort(key=lambda x: x.score, reverse=True)
    if max_suggestions >= 0:
        scored = scored[:max_suggestions]
    return scored


def policy_is_daemon(policy_id: str | None) -> bool:
    """Whether a research's ``policy_id`` marks it as daemon-spawned — the
    seam the surface translates into the "found by the loop" badge. Kept here
    (not inlined in the API) so the one string lives next to the daemon's own
    ``spawn_policy_id``."""
    return policy_id == DAEMON_SPAWN_POLICY_ID
