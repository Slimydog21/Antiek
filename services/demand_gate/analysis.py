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

# The pre-registered criteria, pinned. NEVER change this hash; if the criteria
# doc is amended (it must not be after the window opens), the amendment is
# itself a finding recorded in the verdict — not a re-pin.
CRITERIA_DOC = "docs/decisions/form-factor-demand-gate-PREREGISTERED.md"
CRITERIA_COMMIT = "006e66f29fcc2723d09581488055b258b98466b4"

# The three admissible signal event types (the ONLY things that count).
ROUNDTRIP = "demand_gate.roundtrip_detected"
THIRD_PARTY_READER = "demand_gate.third_party_reader"
AGENT_UNPROMPTED = "demand_gate.agent_unprompted_adoption"

SUSTAIN = "SUSTAIN"
RETIRE = "RETIRE"


@dataclass(frozen=True)
class Verdict:
    verdict: str  # SUSTAIN | RETIRE
    counts: dict  # admissible-signal counts per category
    rationale: str
    criteria_commit: str = CRITERIA_COMMIT


def compute_verdict(events: list[dict], *, operator_user_id: str) -> Verdict:
    """Map raw events to the verdict. ``operator_user_id`` is excluded from
    round-trip counting (the documented n=1 confound — the operator loving the
    artifacts is not evidence). Download/open/compliment events are ignored
    entirely (they measure 'nicer app', not 'new format')."""
    organic_roundtrips = [
        e
        for e in events
        if e.get("action_type") == ROUNDTRIP
        and e.get("user_id") != operator_user_id  # NON-operator only
    ]
    third_party = [e for e in events if e.get("action_type") == THIRD_PARTY_READER]
    agent = [e for e in events if e.get("action_type") == AGENT_UNPROMPTED]

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
            "no admissible signal observed (operator round-trips, downloads, "
            "opens, and compliments do not count); the form-factor framing is "
            "retired in writing. The projection layer stands on its own."
        ),
    )


__all__ = [
    "AGENT_UNPROMPTED",
    "CRITERIA_COMMIT",
    "RETIRE",
    "ROUNDTRIP",
    "SUSTAIN",
    "THIRD_PARTY_READER",
    "Verdict",
    "compute_verdict",
]
