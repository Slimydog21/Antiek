"""Midnight Oil goal-delivery — did the unattended run answer its goals?

Operator vision (ask #13): *"...autonomous research sub-agent swarm mode called
'midnight oil' where users can engage in a deep research without needing to be in
the workstation; all they need to do is set a time of work and goals (and the
system provides the user a recommended price ceiling to approve) then the agent
goes off to execute that task."* The trust loop is complete: the cost estimator
names the ceiling, the planner schedules phases, the gate authorizes per phase,
the ledger tracks actuals, the launch brief (#1876) FREEZES the goals +
ceiling as an immutable mandate, and the run receipt (#1867) reconciles budget /
phases / completion on return. But the receipt answers *"did the swarm honor the
ceiling and finish its phases?"* — it does NOT answer *"did the research actually
address the goals the operator set?"* THIS module is that measurement: the
goal-delivery accountability surface the operator sees when they return from an
unattended run.

**Distinct from the run receipt (#1867).** The receipt is PROCESS fidelity
(budget, phases, stopping reason). This is CONTENT fidelity (did the findings
address the goals). An over-budget run that nailed every goal and an in-budget
run that addressed none are different failures; the receipt sees the first, this
sees the second. Both feed the operator's trust in unattended mode.

**Distinct from problem_question_coverage (#1929).** That module measures one
canonical problem question against one artifact's output. Midnight Oil is
MULTI-GOAL: the operator sets a LIST of goals, each needs its own delivery
verdict, and the operator needs to see WHICH goals were met and which weren't.
The per-goal verdict (met / partial / unmet) and the unmet-goals list are the
multi-goal decomposition #1929's single-score design does not express.

**The score (hard to vary).** For each goal, delivery coverage is the fraction of
the goal's DISTINCTIVE terms (non-stop-word, de-duplicated, normalized) that
appear in the run's findings. Each goal gets a graduated verdict:
  * ``met`` — coverage >= ``met_threshold`` (default 0.80)
  * ``partial`` — ``partial_threshold`` <= coverage < ``met_threshold``
  * ``unmet`` — coverage < ``partial_threshold`` (default 0.40)
``overall_delivery`` is the mean of per-goal coverage (each goal weighted equally
— the operator set them, they all matter). The ``unmet_goals`` list is the
ACCOUNTABILITY SURFACE: the operator sees concretely which goals the run did not
deliver on, with the unmatched terms for each.

**Honest scope (load-bearing).** This is a LEXICAL floor, not semantic delivery —
the same honesty principle as #1929. A goal can be lexically covered (its terms
appear) without the research truly engaging it; semantic delivery is an LLM-judge
concern, declared out of scope in the notes. NO stemming (``scale`` != ``scales``)
and NO synonymy (``impact`` != ``affect``): a stemmer/synonym map would mask an
undelivered goal behind a false match; pure tokenization surfaces it. This is
the right floor for an unattended run the operator was not watching — it errs
toward surfacing gaps, not hiding them.

**Honesty rules (load-bearing):**
* A goal with no distinctive terms (empty / stop-words only) is ``unmeasurable``
  and EXCLUDED from the overall mean — delivery of a goal with no signal words is
  unknown, never fabricated to 0 or coerced to met.
* A run with no findings text (empty swarm output) makes every measurable goal
  ``unmet`` — nothing was delivered.
* ``brief_id`` is carried through so the verdict is traceable to the frozen
  mandate (#1876) the goals came from — the operator can always see WHICH brief's
  goals this delivery report measures.
* Deterministic and pure: same goals + findings -> same report. No LLM, no
  network, no clock, no mutation. ``authority`` is always ``"advisory"``.
* Every goal's verdict is carried through (auditable): the coverage, matched and
  unmatched terms, and state are on the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[a-z0-9]+")

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
        "of", "to", "in", "on", "for", "with", "and", "or", "but", "not",
        "this", "that", "these", "those", "it", "its", "as", "at", "by",
        "from", "into", "than", "then", "so", "such", "do", "does", "did",
        "will", "would", "can", "could", "should", "may", "might", "must",
        "what", "which", "who", "whom", "how", "when", "where", "why",
        "about", "between", "through", "during", "above", "below", "over",
        "under", "again", "further", "there", "here", "all", "any", "both",
        "each", "few", "more", "most", "other", "some", "no", "nor", "only",
        "own", "same", "very", "just", "if", "because", "while", "until",
    }
)

_DEFAULT_MET_THRESHOLD: float = 0.80
_DEFAULT_PARTIAL_THRESHOLD: float = 0.40


class GoalDeliveryError(ValueError):
    """A goal-delivery input violates a load-bearing invariant."""


@dataclass(frozen=True)
class GoalDeliveryVerdict:
    """One goal's delivery verdict from the run's findings. Auditable."""

    goal: str
    goal_index: int
    state: str  # "met" | "partial" | "unmet" | "unmeasurable"
    coverage: float  # matched/total distinctive terms in [0,1]; 0.0 if unmeasurable
    matched_terms: tuple[str, ...]
    unmatched_terms: tuple[str, ...]


@dataclass(frozen=True)
class RunDeliveryReport:
    """The MO run's goal-delivery accountability surface. Advisory, pure."""

    brief_id: str  # the frozen mandate (#1876) the goals came from
    goal_count: int
    verdicts: tuple[GoalDeliveryVerdict, ...]
    met_count: int
    partial_count: int
    unmet_count: int
    unmeasurable_count: int
    overall_delivery: float  # mean of measurable goals' coverage in [0,1]; 0.0 if none measurable
    measured_goal_count: int  # goals with distinctive terms (met + partial + unmet)
    unmet_goals: tuple[GoalDeliveryVerdict, ...]  # the accountability surface
    notes: tuple[str, ...]
    authority: str = "advisory"


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _distinctive_terms(text: str) -> list[str]:
    """Lowercased non-stop-word tokens, de-duplicated, order-preserving.

    Mirrors the lexical-floor approach of #1929 problem_question_coverage: stop-
    words are stripped so the coverage measures the goal's signal words, not its
    grammar. Documented mirror — if #1929's stop-word set changes, the drift is
    visible (both must agree on what counts as a goal's distinctive terms).
    """
    seen: set[str] = set()
    terms: list[str] = []
    for tok in _tokenize(text):
        if tok in _STOP_WORDS or tok in seen:
            continue
        seen.add(tok)
        terms.append(tok)
    return terms


def _verdict_for_goal(
    goal: str,
    goal_index: int,
    findings_vocab: set[str],
    met_threshold: float,
    partial_threshold: float,
) -> GoalDeliveryVerdict:
    terms = _distinctive_terms(goal)
    if not terms:
        return GoalDeliveryVerdict(
            goal=goal,
            goal_index=goal_index,
            state="unmeasurable",
            coverage=0.0,
            matched_terms=(),
            unmatched_terms=(),
        )
    matched = [t for t in terms if t in findings_vocab]
    unmatched = [t for t in terms if t not in findings_vocab]
    coverage = len(matched) / len(terms)
    if coverage >= met_threshold:
        state = "met"
    elif coverage >= partial_threshold:
        state = "partial"
    else:
        state = "unmet"
    return GoalDeliveryVerdict(
        goal=goal,
        goal_index=goal_index,
        state=state,
        coverage=coverage,
        matched_terms=tuple(sorted(matched)),
        unmatched_terms=tuple(sorted(unmatched)),
    )


def score_goal_delivery(
    *,
    brief_id: str,
    goals: list[str],
    findings_text: str,
    met_threshold: float = _DEFAULT_MET_THRESHOLD,
    partial_threshold: float = _DEFAULT_PARTIAL_THRESHOLD,
) -> RunDeliveryReport:
    """Measure how well a Midnight Oil run's findings delivered on its goals.

    ``brief_id`` is the frozen mandate (#1876) the goals came from. ``goals`` is
    the operator's list of goals (as frozen in the brief). ``findings_text`` is
    the run's findings (insight texts + synthesis, joined by the caller). Returns
    a :class:`RunDeliveryReport` with per-goal verdicts, the overall delivery
    score, and the unmet-goals accountability surface.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not brief_id.strip():
        raise GoalDeliveryError(
            "brief_id must be non-empty (the goals' frozen mandate is load-bearing)"
        )
    if not goals:
        raise GoalDeliveryError(
            "at least one goal is required; cannot measure delivery against nothing"
        )
    if not met_threshold or not 0.0 < met_threshold <= 1.0:
        raise GoalDeliveryError(
            f"met_threshold must be in (0.0, 1.0], got {met_threshold!r}"
        )
    if (
        not partial_threshold
        or not 0.0 < partial_threshold < met_threshold
    ):
        raise GoalDeliveryError(
            f"partial_threshold must be in (0.0, met_threshold), got "
            f"{partial_threshold!r} (met_threshold={met_threshold!r})"
        )

    findings_vocab = set(_tokenize(findings_text))

    verdicts = [
        _verdict_for_goal(
            goal=goal,
            goal_index=idx,
            findings_vocab=findings_vocab,
            met_threshold=met_threshold,
            partial_threshold=partial_threshold,
        )
        for idx, goal in enumerate(goals)
    ]

    measurable = [v for v in verdicts if v.state != "unmeasurable"]
    met = [v for v in measurable if v.state == "met"]
    partial = [v for v in measurable if v.state == "partial"]
    unmet = [v for v in measurable if v.state == "unmet"]
    unmeasurable = [v for v in verdicts if v.state == "unmeasurable"]

    overall = sum(v.coverage for v in measurable) / len(measurable) if measurable else 0.0

    notes: list[str] = [
        "overall_delivery is the mean of MEASURABLE goals' coverage (goals with "
        "distinctive terms); unmeasurable goals are excluded, not penalized",
        "delivery is a LEXICAL floor, not semantic — a goal's terms can appear "
        "without the research truly engaging it; semantic delivery is an "
        "LLM-judge concern, out of scope",
    ]
    if not measurable:
        notes.append(
            "no goal has distinctive terms; delivery is unmeasurable (defer to "
            "the operator's own review of the findings)"
        )
    else:
        notes.append(
            f"overall delivery {overall:.0%}: {len(met)} met, {len(partial)} "
            f"partial, {len(unmet)} unmet (of {len(measurable)} measurable goals)"
        )
    if unmeasurable:
        notes.append(
            f"{len(unmeasurable)} goal(s) unmeasurable (no distinctive terms "
            "after stop-word removal)"
        )
    if unmet:
        notes.append(
            f"ACCOUNTABILITY: {len(unmet)} unmet goal(s) — the run did not "
            "deliver on these: " + "; ".join(
                f"[{v.goal_index}] {v.goal}" for v in unmet
            )
        )

    return RunDeliveryReport(
        brief_id=brief_id,
        goal_count=len(goals),
        verdicts=tuple(verdicts),
        met_count=len(met),
        partial_count=len(partial),
        unmet_count=len(unmet),
        unmeasurable_count=len(unmeasurable),
        overall_delivery=overall,
        measured_goal_count=len(measurable),
        unmet_goals=tuple(unmet),
        notes=tuple(notes),
    )


__all__ = [
    "GoalDeliveryError",
    "GoalDeliveryVerdict",
    "RunDeliveryReport",
    "score_goal_delivery",
]
