"""Gap-scoring + decay logic for the continuous daemon.

Per master-spec §7.3, each evidentiary_gap is scored along three
dimensions:

  - **Recency** — newer gaps weighted higher (exponential decay over
    days since the gap was emitted).
  - **Co-occurrence** — a gap appearing across multiple investigations
    is more valuable to chase than a one-off.
  - **Operator interaction signal** — gaps that the operator has
    highlighted (e.g., expressed as a parked question, manually
    promoted) get a multiplier. The substrate's existing
    ``question.identified`` event log is the proxy here.

Per §7.4 cost-runaway mitigation:

  - **Decay** — if a gap has been chased ≥``MAX_CHASE_COUNT`` times
    across the daemon's history with no resolution, its score drops
    to zero so the daemon stops re-spawning it.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

# ── Tuning constants ──────────────────────────────────────────────────


#: How many times a gap can be chased before its score decays to 0.
#: Per master-spec §7.4: "if an investigation produces only gaps that
#: have already been chased ≥3 times across the daemon's history,
#: halt that branch."
MAX_CHASE_COUNT: int = 3

#: Recency half-life in days. A gap emitted exactly this long ago
#: scores 0.5 on the recency axis; older gaps decay further.
RECENCY_HALF_LIFE_DAYS: float = 3.0

#: Co-occurrence floor — a gap seen only once gets the minimum
#: co-occurrence score (1.0). Each additional sighting multiplies the
#: co-occurrence axis up to ``CO_OCCURRENCE_CAP``.
CO_OCCURRENCE_CAP: int = 10

#: Multiplier on the operator-interaction axis when ``interaction_count``
#: is non-zero (the operator has visibly engaged with this gap).
INTERACTION_BOOST: float = 1.5


# ── Public types ──────────────────────────────────────────────────────


@dataclass
class GapEntry:
    """One unique gap observed across the event log.

    The daemon collapses identical gap descriptions (after
    normalization) into a single entry, accumulating the sources
    (investigation_ids) and the chase history. ``investigation_ids``
    is ordered by first-sighting time; ``chase_count`` is how many
    times the daemon (or operator) spawned an investigation against
    this gap."""

    normalized_key: str
    gap_description: str
    additional_retrieval_suggested: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    investigation_ids: list[str] = field(default_factory=list)
    chase_count: int = 0
    interaction_count: int = 0

    @property
    def co_occurrence(self) -> int:
        """Distinct investigations that surfaced this gap."""
        return len(set(self.investigation_ids))


@dataclass
class GapRegistry:
    """In-memory registry of all observed gaps. Built by scanning the
    event log; consumed by the daemon's spawn-selection loop."""

    entries: dict[str, GapEntry] = field(default_factory=dict)

    def observe(
        self,
        *,
        gap_description: str,
        additional_retrieval_suggested: str | None,
        investigation_id: str,
        emitted_at: datetime,
    ) -> GapEntry:
        """Record one gap sighting. Returns the (possibly updated)
        entry. Idempotent on (gap_description, investigation_id) —
        seeing the same gap twice in the same investigation does not
        double-count co-occurrence."""
        key = normalize_gap_description(gap_description)
        existing = self.entries.get(key)
        if existing is None:
            entry = GapEntry(
                normalized_key=key,
                gap_description=gap_description,
                additional_retrieval_suggested=additional_retrieval_suggested,
                first_seen_at=emitted_at,
                last_seen_at=emitted_at,
                investigation_ids=[investigation_id],
            )
            self.entries[key] = entry
            return entry
        # Update last-seen timestamp + investigation list (deduped).
        if emitted_at > existing.last_seen_at:
            existing.last_seen_at = emitted_at
        if investigation_id not in existing.investigation_ids:
            existing.investigation_ids.append(investigation_id)
        # Update retrieval suggestion if the new sighting carries one
        # and we didn't have one before — first non-empty wins.
        if (
            additional_retrieval_suggested
            and not existing.additional_retrieval_suggested
        ):
            existing.additional_retrieval_suggested = additional_retrieval_suggested
        return existing

    def mark_chased(self, normalized_key: str) -> None:
        """Increment chase count after the daemon spawns an
        investigation against this gap. Caller responsible for keying
        on ``normalized_key`` (use ``normalize_gap_description`` first
        if you have raw text)."""
        entry = self.entries.get(normalized_key)
        if entry is not None:
            entry.chase_count += 1

    def mark_interaction(self, normalized_key: str, *, count: int = 1) -> None:
        """Increment operator-interaction count (e.g., parked question,
        operator manually flagged). Bumps the interaction axis of the
        gap's score."""
        entry = self.entries.get(normalized_key)
        if entry is not None:
            entry.interaction_count += count

    def __len__(self) -> int:
        return len(self.entries)

    def values(self) -> Iterable[GapEntry]:
        return self.entries.values()


# ── Scoring functions ─────────────────────────────────────────────────


def normalize_gap_description(text: str) -> str:
    """Collapse a gap_description into a stable identity key.

    The substrate emits gap_description as free text from the
    evidence_retriever role. To detect "same gap" across investigations,
    we lowercase, collapse whitespace, and hash the first 200 chars.
    The hash is short (16 chars) so it's readable in logs but unlikely
    to collide across the ~thousands of gaps a real graph generates.
    """
    if not text:
        return "<empty>"
    collapsed = " ".join(text.lower().split())
    truncated = collapsed[:200]
    return hashlib.sha256(truncated.encode("utf-8")).hexdigest()[:16]


def _recency_score(emitted_at: datetime, *, now: datetime | None = None) -> float:
    """Exponential decay over days since emission. Returns [0, 1]."""
    ref = now or datetime.now(UTC)
    # Ensure timezone-aware comparison. If naive, treat as UTC.
    if emitted_at.tzinfo is None:
        emitted_at = emitted_at.replace(tzinfo=UTC)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=UTC)
    delta_days = max(0.0, (ref - emitted_at).total_seconds() / 86400.0)
    # exp(ln(2) * -delta / half_life) — half-life decay.
    return math.exp(-math.log(2.0) * delta_days / RECENCY_HALF_LIFE_DAYS)


def _co_occurrence_score(co_count: int) -> float:
    """Log-scale score on co-occurrence count. Returns [0, 1]."""
    if co_count <= 0:
        return 0.0
    capped = min(co_count, CO_OCCURRENCE_CAP)
    return math.log(1 + capped) / math.log(1 + CO_OCCURRENCE_CAP)


def _interaction_score(interaction_count: int) -> float:
    """Operator interaction is binary-ish: any > 0 yields the boost."""
    return INTERACTION_BOOST if interaction_count > 0 else 1.0


def score_gap(entry: GapEntry, *, now: datetime | None = None) -> float:
    """Composite score for a single gap. Returns 0.0 if the gap has
    been chased ≥ MAX_CHASE_COUNT times (decay rule, §7.4).

    Otherwise: ``recency * co_occurrence * interaction_multiplier``.
    The multiplicative form means a "stale gap nobody else hit" can't
    out-score a "fresh gap many runs flagged", which matches the
    operator's intuition about what to chase next.
    """
    if entry.chase_count >= MAX_CHASE_COUNT:
        return 0.0
    r = _recency_score(entry.last_seen_at, now=now)
    c = _co_occurrence_score(entry.co_occurrence)
    i = _interaction_score(entry.interaction_count)
    return r * c * i
