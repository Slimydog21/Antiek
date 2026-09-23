"""Demand-gate analysis (HPRJ SPR-08 M5).

Computes the verdict from raw events REPRODUCIBLY: same events in -> same
verdict out. The pre-registered criteria are immovable and the criteria doc's
commit hash is pinned here, so six months on "why did we sustain/retire?" is
answerable from one decision doc citing event data anyone can re-run.

Per `docs/decisions/form-factor-demand-gate-PREREGISTERED.md`:
SUSTAIN iff >= 1 admissible signal — {organic round-trip by a NON-operator,
third-party reader, agent-unprompted adoption}. Everything else (downloads,
opens, compliments) is IGNORED. No middle verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# The pre-registered criteria, pinned. NEVER change this hash; if the criteria
# doc is amended (it must not be after the window opens), the amendment is
# itself a finding recorded in the verdict — not a re-pin.
CRITERIA_DOC = "docs/decisions/form-factor-demand-gate-PREREGISTERED.md"
CRITERIA_COMMIT = "006e66f29fcc2723d09581488055b258b98466b4"

# The three admissible signal event types (the ONLY things that count).
ROUNDTRIP = "demand_gate.roundtrip_detected"
THIRD_PARTY_READER = "demand_gate.third_party_reader"
AGENT_UNPROMPTED = "demand_gate.agent_unprompted_adoption"
# Coverage, not signal: the neutral dual offer reaching a pinned tester.
EXPORT_OFFERED = "demand_gate.export_offered"

# Pre-registered: a fixed 2-week window, N pinned non-operator testers in [5, 15].
WINDOW = timedelta(days=14)
MIN_TESTERS, MAX_TESTERS = 5, 15

SUSTAIN = "SUSTAIN"
RETIRE = "RETIRE"


class GateNotRunnable(ValueError):
    """The window as supplied cannot produce a pre-registered verdict (bad
    window, bad tester set, or no instrumentation). This is NOT a middle
    verdict: it says the test did not happen, so neither template may be
    signed. Returning RETIRE here would report missing telemetry as a finding
    about demand."""


@dataclass(frozen=True)
class Verdict:
    verdict: str  # SUSTAIN | RETIRE
    counts: dict  # admissible-signal counts per category
    rationale: str
    criteria_commit: str = CRITERIA_COMMIT


def _norm(actor: object) -> str:
    return actor.strip().casefold() if isinstance(actor, str) else ""


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_tester(actor: object, testers: frozenset[str]) -> bool:
    return isinstance(actor, str) and actor in testers


def _stamp(value: object) -> datetime | None:
    """``emitted_at`` as an aware datetime, or None (undated, unparseable, or
    naive — none of which can be placed in the window honestly)."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value


def compute_verdict(
    events: list[dict],
    *,
    operator_user_id: str,
    tester_ids: frozenset[str] | set[str],
    window_start: datetime,
    window_end: datetime,
) -> Verdict:
    """Map raw events to the verdict, over the pre-registered window and the
    N testers pinned before it opened. Download/open/compliment events are
    ignored entirely (they measure 'nicer app', not 'new format').

    Admission is an ALLOWLIST, never an operator denylist (the n=1 confound —
    the operator loving the artifacts is not evidence; exact-match exclusion
    let '', 'OPERATOR' and ' operator' through as organic demand):

    - round-trip: re-imported by a pinned tester AND exported by a pinned
      tester AND no operator-equivalent id among its exporters (criterion 1:
      "exported by a non-operator"; an ``exported_by`` naming the operator is
      ambiguous provenance, which is not that).
    - third-party reader / agent-unprompted: hand-documented observations, so
      they must name the tool/agent, name who (not the operator, compared
      case- and whitespace-insensitively), and cite an ``evidence_ref`` the
      signed verdict can point at.
    - every signal must carry an aware ``emitted_at`` inside the window.

    Raises ``GateNotRunnable`` when the window, the tester set, or the
    instrumentation cannot support a verdict — including zero in-window
    ``export_offered`` events to pinned testers, which means the offer never
    reached anyone and a RETIRE would be vacuous."""
    op = _norm(operator_user_id)
    if not op:
        raise GateNotRunnable("operator_user_id is blank")
    testers = frozenset(tester_ids)
    if not MIN_TESTERS <= len(testers) <= MAX_TESTERS:
        raise GateNotRunnable(
            f"{len(testers)} pinned testers; the pre-registered N is in "
            f"[{MIN_TESTERS}, {MAX_TESTERS}]"
        )
    if any(not _nonblank(t) or _norm(t) == op for t in testers):
        raise GateNotRunnable("tester_ids holds a blank id or the operator")
    if len({_norm(t) for t in testers}) != len(testers):
        raise GateNotRunnable(
            "tester_ids holds case/whitespace variants of one id; N counts people, "
            "not spellings"
        )
    if window_start.tzinfo is None or window_end.tzinfo is None:
        raise GateNotRunnable("window bounds must be timezone-aware")
    if window_end - window_start != WINDOW:
        raise GateNotRunnable(
            f"window is {window_end - window_start}, pre-registered is {WINDOW} "
            "fixed; an extension is a finding to record, not a parameter"
        )

    def in_window(e: dict) -> bool:
        ts = _stamp(e.get("emitted_at"))
        return ts is not None and window_start <= ts < window_end

    windowed = [e for e in events if in_window(e)]

    offers = [
        e
        for e in windowed
        if e.get("action_type") == EXPORT_OFFERED and _is_tester(e.get("user_id"), testers)
    ]
    if not offers:
        raise GateNotRunnable(
            "no in-window export_offered event reached a pinned tester; the "
            "window was not instrumented, so no verdict (RETIRE included) holds"
        )

    def documented(e: dict, who_key: str) -> bool:
        actor = e.get("user_id")
        return (
            _nonblank(e.get(who_key))
            and _nonblank(e.get("evidence_ref"))
            and _nonblank(actor)
            and _norm(actor) != op
        )

    organic_roundtrips = [
        e
        for e in windowed
        if e.get("action_type") == ROUNDTRIP
        and _is_tester(e.get("user_id"), testers)
        and isinstance(e.get("exported_by"), (list, tuple))
        and any(_is_tester(x, testers) for x in e["exported_by"])
        and not any(_norm(x) == op for x in e["exported_by"])
    ]
    third_party = [
        e for e in windowed
        if e.get("action_type") == THIRD_PARTY_READER and documented(e, "tool")
    ]
    agent = [
        e for e in windowed
        if e.get("action_type") == AGENT_UNPROMPTED and documented(e, "agent")
    ]

    counts = {
        "organic_roundtrip": len(organic_roundtrips),
        "third_party_reader": len(third_party),
        "agent_unprompted": len(agent),
    }
    total_admissible = sum(counts.values())

    if total_admissible >= 1:
        return Verdict(
            verdict=SUSTAIN,
            counts=counts,
            rationale=(
                f"{total_admissible} admissible signal(s) observed "
                f"({counts}); per the pre-registered criteria this sustains."
            ),
        )
    return Verdict(
        verdict=RETIRE,
        counts=counts,
        rationale=(
            f"{len(offers)} export offer(s) reached pinned testers in the window "
            "and no admissible signal was observed (operator round-trips, "
            "downloads, opens, and compliments do not count); the form-factor "
            "framing is retired in writing. The projection layer stands on its own."
        ),
    )


__all__ = [
    "AGENT_UNPROMPTED",
    "CRITERIA_COMMIT",
    "EXPORT_OFFERED",
    "RETIRE",
    "ROUNDTRIP",
    "SUSTAIN",
    "THIRD_PARTY_READER",
    "GateNotRunnable",
    "Verdict",
    "compute_verdict",
]
