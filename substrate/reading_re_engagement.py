r"""Reading re-engagement — does the reader return to an asset across sessions?

Operator vision (ask #2): *"I want to read books or papers (and engage with it in
the same way I would the research workstation)..."* The deepest reading engagement
is not a single sitting — it is RETURNING. A reader who opens a paper once and never
comes back has either finished cleanly or skimmed-and-abandoned (indistinguishable
from a one-pass metric). A reader who returns across multiple sessions is
DEEPLY ENGAGED: wrestling with a hard passage, cross-referencing over days,
re-reading after a highlight spawned research, or building on the asset iteratively.
That cross-session return signal is the strongest behavioral marker of genuine
engagement — and NOTHING measures it. The existing reading axes are all WITHIN one
session: ``reading_flow_continuity`` (#1983) tracks progress-vs-jump ordering,
``reading_engagement_distribution`` (#1998) tracks per-section touch concentration,
``reading_passage_coverage`` (#1987) tracks document-extent engaged. All see ONE
session's interior. Re-engagement sees ACROSS sessions — the temporal return pattern
that distinguishes a wrestled-with asset from a one-pass skim.

**Genuinely distinct from every reading axis (load-bearing):**

* ``reading_flow_continuity`` (#1983): WITHIN one session, did the reader progress
  linearly or jump around (section-ordering pattern)? This measures ACROSS sessions,
  did the reader come BACK at all (session-return pattern). Different time axis.
* ``reading_engagement_distribution`` (#1998): WITHIN one session, is attention spread
  or clustered on a hot section (per-section touch concentration)? This measures
  ACROSS sessions, how many times the asset was re-opened (per-asset session count).
* ``reading_passage_coverage`` (#1987): WITHIN one session, what FRACTION of the
  document was engaged (extent)? This measures ACROSS sessions, did engagement
  RECUR at all (return vs one-pass).

A reader can show perfect within-session flow (#1983), broad coverage (#1987), and
even attention (#1998) in a SINGLE sitting yet never return (THIS ``single_session``)
— a complete one-pass read indistinguishable from a skim by any within-session axis.
Only the cross-session return count separates them. The within-session axes and
re-engagement are independent: both must be measured to know whether an asset was
truly wrestled with over time.

**The measurement (hard to vary).** Given the sequence of session-start timestamps
for a single asset (the route layer supplies per-asset reading-session opens, sorted
ascending), measure the cross-session return pattern:

* ``session_count`` — distinct reading sessions that touched the asset.
* ``return_count`` = ``session_count - 1`` when ``session_count >= 1`` — every session
  AFTER the first is a return. ``0`` for a single session (honest: no returns).
* ``return_rate`` = ``return_count / session_count`` — the fraction of sessions that
  are returns (``0.0`` for one session — no returns; approaches ``1.0`` for many
  returns). ``None`` only when ``session_count == 0`` (defer — never fabricated).
* ``engagement_span_days`` = (last session - first session) in days — the calendar
  window over which the asset stayed alive in the reader's attention. ``None`` when
  ``session_count < 2`` (one session has no span — a point, not a window).
* ``mean_inter_session_gap_days`` = mean of gaps between consecutive sessions — the
  reader's engagement CADENCE (how often they return). ``None`` when < 2 sessions.
* ``max_inter_session_gap_days`` = longest gap between consecutive sessions — the
  longest the reader stayed away (potential dormancy / abandonment signal).
  ``None`` when < 2 sessions.
* ``session_starts`` — the timestamps verbatim (auditable: the operator sees the full
  return pattern, no black-box engagement).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero sessions -> ``unknown`` (no engagement recorded — defer, never fabricated).
* exactly one session -> ``single_session`` (a lone sitting — no return to measure;
  honest base case distinct from ``unknown`` which has no sessions at all).
* exactly two sessions -> ``returned`` (came back ONCE — the minimal return; the
  reader re-opened the asset at least once).
* ``session_count >= recurring_threshold`` (default ``3``) -> ``recurring`` (deep
  multi-session engagement — the reader returned repeatedly; the strongest behavioral
  marker that the asset was wrestled with over time. A REAL measured verdict, NOT the
  default).

**DESCRIPTIVE NOT NORMATIVE:** ``single_session`` does NOT mean "bad" — the reader
may have completed a clean one-pass read (finished, absorbed, moved on); a paper
fully digested in one sitting is a success, not a defect. ``recurring`` does NOT mean
"good" — the reader may be re-struggling with a hard passage they cannot absorb
(re-reading without progress), or repeatedly lost. The operator judges whether the
return pattern reflects productive iterative engagement or frustrated stalling. This
axis surfaces the FACT of cross-session return; it does not prescribe the right count.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero sessions are supplied.
* ``single_session`` is its own honest base case (one session present — distinct from
  ``unknown`` which has none). ``return_count`` is ``0`` here (an honest measured
  zero), ``return_rate`` is ``0.0`` (honest — no returns), but the inter-session gap
  / span metrics are ``None`` (a single point has no gap/span — defer, never ``0.0``).
* ``recurring`` is a REAL measured verdict (>= threshold sessions), never the default
  — ``unknown`` and ``single_session`` are the defer/base states.
* ``return_rate`` is bounded ``[0.0, 1.0)`` by construction (return_count < session_count).
* absolute threshold (session COUNT, not normalized to document length or time): a
  3-session return is 3 sessions whether the asset is 2 pages or 200; normalizing would
  obscure the raw behavioral signal.
* ``engagement_span`` / inter-session gaps require ``session_count >= 2`` (a point has
  no span — deferred honestly, never fabricated ``0.0`` days).
* sessions are de-duplicated by timestamp (a repeated identical open is one session,
  not many — mirrors the edge-dedup discipline of the graph axes).
* out-of-order timestamps are sorted (sessions are temporal events; the route layer
  may supply them in any order — deterministic sort makes the measure reproducible).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain ``datetime`` inputs; route layer adapts 1:1
  from the reading-session open log).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "ReadingReEngagementReport",
    "measure_reading_re_engagement",
]

_DEFAULT_RECURRING_THRESHOLD = 3
_DAYS_PER_SECOND = 1.0 / 86400.0


@dataclass(frozen=True)
class ReadingReEngagementReport:
    """The cross-session re-engagement surface for one reading asset. Advisory, pure."""

    session_count: int
    return_count: int
    return_rate: float | None
    engagement_span_days: float | None
    mean_inter_session_gap_days: float | None
    max_inter_session_gap_days: float | None
    session_starts: tuple[datetime, ...]
    recurring_threshold: int
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_reading_re_engagement(
    session_starts: Sequence[datetime],
    *,
    recurring_threshold: int = _DEFAULT_RECURRING_THRESHOLD,
) -> ReadingReEngagementReport:
    r"""Measure the cross-session re-engagement pattern for one reading asset.

    ``session_starts`` are the reading-session open timestamps for a single asset
    (the route layer supplies these from the reading-session log). Returns a
    :class:`ReadingReEngagementReport` with return pattern and verdict.

    Raises:
        ValueError: if ``recurring_threshold < 2`` (recurring needs at least a return).
    """
    if recurring_threshold < 2:
        raise ValueError(
            f"recurring_threshold must be >= 2; got {recurring_threshold}"
        )

    # De-duplicate identical timestamps (a repeated open is one session) then sort.
    unique = sorted(set(session_starts))
    session_count = len(unique)

    if session_count == 0:
        return ReadingReEngagementReport(
            session_count=0,
            return_count=0,
            return_rate=None,
            engagement_span_days=None,
            mean_inter_session_gap_days=None,
            max_inter_session_gap_days=None,
            session_starts=(),
            recurring_threshold=recurring_threshold,
            verdict="unknown",
            notes=("no reading sessions recorded — re-engagement unmeasurable",),
        )

    return_count = session_count - 1
    return_rate = return_count / session_count

    if session_count == 1:
        return ReadingReEngagementReport(
            session_count=1,
            return_count=0,
            return_rate=0.0,
            engagement_span_days=None,
            mean_inter_session_gap_days=None,
            max_inter_session_gap_days=None,
            session_starts=(unique[0],),
            recurring_threshold=recurring_threshold,
            verdict="single_session",
            notes=(
                "one reading session — no return to measure (the reader opened "
                "the asset once); may be a clean one-pass completion or an "
                "abandoned skim, indistinguishable from a single-session metric",
            ),
        )

    gaps_seconds = [
        (unique[i] - unique[i - 1]).total_seconds() for i in range(1, session_count)
    ]
    span_days = (unique[-1] - unique[0]).total_seconds() * _DAYS_PER_SECOND
    mean_gap_days = (sum(gaps_seconds) / len(gaps_seconds)) * _DAYS_PER_SECOND
    max_gap_days = max(gaps_seconds) * _DAYS_PER_SECOND

    verdict = (
        "recurring"
        if session_count >= recurring_threshold
        else "returned"
    )

    note_parts: list[str] = [
        f"{session_count} session(s), {return_count} return(s); return_rate "
        f"{return_rate:.2f}, span {span_days:.2f} day(s), mean gap "
        f"{mean_gap_days:.2f} day(s), max gap {max_gap_days:.2f} day(s)",
        "re-engagement measures CROSS-SESSION return — did the reader come back "
        "to this asset over time? ORTHOGONAL to the within-session reading axes: "
        "reading_flow_continuity #1983 (progress-vs-jump ordering), "
        "reading_engagement_distribution #1998 (per-section touch concentration), "
        "reading_passage_coverage #1987 (document extent) — all see ONE session's "
        "interior; this sees ACROSS sessions, the temporal return pattern that "
        "distinguishes a wrestled-with asset from a one-pass skim",
    ]
    if verdict == "single_session":
        note_parts.append(
            "single_session: one session present, no return — honest base case "
            "distinct from unknown (no sessions); a clean one-pass read is "
            "indistinguishable from an abandoned skim by within-session metrics"
        )
    elif verdict == "returned":
        note_parts.append(
            "returned: the reader came back ONCE — minimal re-engagement; the "
            "asset drew at least one repeat visit"
        )
    else:  # recurring
        note_parts.append(
            "recurring: the reader returned repeatedly across sessions — the "
            "strongest behavioral marker of deep engagement (wrestling with a "
            "hard passage, cross-referencing over days, building iteratively); "
            "DESCRIPTIVE not normative (may also be re-struggling without progress)"
        )
    note_parts.append(
        f"verdict {verdict}: recurring_threshold {recurring_threshold} sessions; "
        "DESCRIPTIVE not normative — single_session may be a clean completion; "
        "recurring may be frustrated re-struggling; the operator judges productive "
        "iterative engagement vs stalling"
    )

    return ReadingReEngagementReport(
        session_count=session_count,
        return_count=return_count,
        return_rate=return_rate,
        engagement_span_days=span_days,
        mean_inter_session_gap_days=mean_gap_days,
        max_inter_session_gap_days=max_gap_days,
        session_starts=tuple(unique),
        recurring_threshold=recurring_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
