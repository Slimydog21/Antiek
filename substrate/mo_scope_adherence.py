"""Midnight Oil scope adherence — did the run stay within its declared goals?

Operator vision (ask #13): *"...autonomous research sub-agent swarm mode called
'midnight oil' where users can engage in a deep research without needing to be in
the workstation; all they need to do is set a time of work and goals (and the
system provides the user a recommended price ceiling to approve) then the agent
goes off to execute that task."* The operator sets a LIST of goals and walks away.
``goal_delivery`` (#1938) answers the POSITIVE question: did the findings address
the goals (coverage)? But the operator also needs the NEGATIVE complement: did the
run introduce findings OUTSIDE its declared goals (off-scope drift)? An unattended
run that delivers every goal yet wanders into unrequested territory is a CONTROL
FAILURE: it spent budget on work the operator did not ask for, and its off-scope
findings may pull the knowledge graph in directions the operator never intended.
For a "without needing to be in the workstation" mode, off-scope drift is exactly
the kind of runaway the operator cannot catch live.

**Genuinely distinct (positive coverage vs negative drift — the load-bearing
split).** ``goal_delivery`` (#1938) measures the FORWARD question: for each GOAL,
did findings cover it (recall over goals). THIS measures the BACKWARD question:
for each FINDING, does it trace to a goal (precision over findings). The two are
the precision/recall duality applied to the goal↔finding relationship — the SAME
axis-space split as twin_fidelity (#1954, precision) vs twin_coverage (#1964,
recall) and synthesis_grounding (#1942, ←) vs insight_novelty (#1958, →). A run
can deliver high goal-coverage AND drift off-scope (it addressed every goal PLUS
produced extra unrequested findings) — coverage sees the first, scope-adherence
sees the second. Both facts matter for an operator trusting unattended mode.

**The measurement (hard to vary).** Given the operator-declared ``goals`` and the
run's ``findings``:

* Tokenise each goal and finding into distinctive content terms (glue +
  interrogatives stripped — the lexical floor shared across all quality modules).
* Build the ``goal_term_pool`` = the union of ALL goals' distinctive terms (the
  scope boundary — everything the operator asked about).
* A finding is ``on_scope`` if it has at least ``min_goal_overlap`` distinctive
  terms in common with the goal pool (default 1 — at least one shared content
  term); otherwise ``off_scope`` (its content traces to no declared goal — drift).
* ``on_scope_ratio = on_scope / measurable`` (``None`` when zero measurable
  findings — defer, never ``0.0``/``1.0``).
* ``off_scope_findings`` — the specific drift findings (auditable: exactly which
  findings wandered).

The verdict:

* zero measurable findings → ``unknown`` (run produced no content — defer, never
  fabricated as on/off-scope).
* ``on_scope_ratio >= adherence_threshold`` (default 0.85) → ``on_scope`` (the
  run stayed within its goals — control held).
* ``on_scope_ratio < adherence_threshold`` and ``> 0`` → ``drifted`` (some
  findings on-scope, but a meaningful share wandered — partial control failure).
* ``on_scope_ratio == 0.0`` → ``fully_off_scope`` (every finding traces to no
  goal — total runaway: the run did not address any declared goal at all).

**The backward-compatibility honesty (load-bearing).** A finding that is
off-scope is NOT automatically wrong — it may be a serendipitous discovery, a
necessary precondition, or a correction of a flawed goal. This axis reports
off-scope as a CONTROL/DRIFT signal (the run did work the operator didn't
request), never as a truth verdict (the off-scope finding may be valuable).
``goal_delivery`` (#1938) carries the "did the goals get met" lane; this carries
the "did the run stay in its lane" lane. The operator, returning from an
unattended run, decides whether an off-scope finding is a gift (keep it) or a
waste (discard it and tighten the goals next time).

**All-glue findings (zero distinctive terms)** are NOT measurable: a finding with
no content words cannot be tested for term overlap with the goal pool. These are
excluded from both numerator and denominator and carried as an
``unmeasurable_count`` for honesty (never fabricated as off-scope — fabricating
drift from a finding with no measurable content would conflate "unmeasurable"
with "wandered").

**Lexical floor, not semantic (load-bearing).** No stemming, no synonymy. A
finding that is ON-TOPIC but uses entirely different vocabulary than the goals may
score as off-scope — that is the SAME conservative direction as twin_coverage
(#1964) and source_corroboration (#1966): this detector prefers flagging a
rephrased on-topic finding (false positive — the operator confirms it belongs)
over certifying on-scope a finding that merely happens to share a content word
with a goal (false negative — that would hide real drift behind a phony match).
A semantic relevance check confirms downstream.

**Honesty rules (load-bearing):**

* ``on_scope_ratio`` is ``None`` when zero measurable findings (defer — never
  ``0.0`` or ``1.0``).
* All-glue findings excluded from the ratio (carried as ``unmeasurable_count``)
  — never fabricated as off-scope.
* ``off_scope_findings`` lists the specific drift (auditable — exactly which
  findings the operator should review).
* Off-scope is a CONTROL/DRIFT signal, never a truth verdict (an off-scope
  finding may be valuable).
* ``min_goal_overlap`` of 0 is rejected (zero overlap = every finding with any
  goal term passes, even a single shared glue word — that defeats the test;
  ``>= 1`` is the floor).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** The ``midnight_oil`` package is not on
frozen origin/main (so importing ``goal_delivery`` would break the bar on frozen
main). This module takes plain ``list[str]`` goals + findings (the route layer
adapts: it reads the frozen goals from the launch brief and the findings from the
run's research artifact).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DEFAULT_ADHERENCE_THRESHOLD: float = 0.85
_DEFAULT_MIN_GOAL_OVERLAP: int = 1

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "been", "being", "am",
        "of", "to", "in", "on", "at", "by", "for", "with", "from",
        "into", "onto", "upon", "over", "under", "between", "through",
        "during", "before", "after", "above", "below", "up", "down",
        "out", "off", "about", "against", "as", "than", "then",
        "and", "or", "but", "nor", "so", "yet", "if", "because",
        "while", "where", "when", "how", "what", "which", "who", "whom",
        "why", "will", "would", "shall", "should", "can", "could", "may",
        "might", "must", "not", "no", "yes", "also", "very", "just",
        "only", "more", "most", "some", "any", "all", "each", "every",
        "other", "such", "own", "same", "too", "do", "does", "did",
        "it", "its", "they", "them", "their", "we", "us", "our",
        "you", "your", "he", "she", "his", "her", "i", "me", "my", "s",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+")


def _distinctive_terms(text: str) -> frozenset[str]:
    """Lowercase content words (glue + interrogatives stripped). Lexical floor."""
    return frozenset(
        tok for tok in _WORD_RE.findall(text.lower()) if tok not in _STOP_WORDS
    )


class ScopeAdherenceError(ValueError):
    """A scope-adherence input violates a load-bearing invariant."""


@dataclass(frozen=True)
class FindingScope:
    """One finding's scope verdict against the declared goals. Advisory, pure."""

    finding: str
    verdict: str  # on_scope | off_scope | unmeasurable
    goal_overlap_count: int  # distinctive terms shared with the goal pool


@dataclass(frozen=True)
class ScopeAdherenceReport:
    """An unattended run's scope-adherence profile. Advisory, pure."""

    on_scope_count: int
    off_scope_count: int
    unmeasurable_count: int
    on_scope_ratio: float | None  # on_scope/measurable; None if zero measurable
    off_scope_ratio: float | None
    goal_pool_size: int  # total distinctive terms across all goals
    finding_scopes: tuple[FindingScope, ...]
    off_scope_findings: tuple[str, ...]  # the specific drift findings
    adherence_threshold: float
    min_goal_overlap: int
    verdict: str  # on_scope | drifted | fully_off_scope | unknown
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_scope_adherence(
    goals: list[str],
    findings: list[str],
    *,
    adherence_threshold: float = _DEFAULT_ADHERENCE_THRESHOLD,
    min_goal_overlap: int = _DEFAULT_MIN_GOAL_OVERLAP,
) -> ScopeAdherenceReport:
    """Measure whether an unattended run's findings stayed within its declared goals.

    ``goals`` are the operator-declared research goals (the scope boundary).
    ``findings`` are the run's research findings (the route layer reads these from
    the run's research artifact insights). Returns a
    :class:`ScopeAdherenceReport` with per-finding scope verdicts + the overall
    on-scope ratio + the drift findings.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if not goals:
        raise ScopeAdherenceError(
            "at least one goal is required to define the scope boundary"
        )
    if not 0.0 <= adherence_threshold <= 1.0:
        raise ScopeAdherenceError(
            f"adherence_threshold must be in [0,1], got {adherence_threshold!r}"
        )
    if min_goal_overlap < 1:
        raise ScopeAdherenceError(
            f"min_goal_overlap must be >= 1, got {min_goal_overlap!r}"
        )

    goal_pool: set[str] = set()
    for goal in goals:
        if not goal or not goal.strip():
            raise ScopeAdherenceError("goals must be non-empty strings")
        goal_pool |= _distinctive_terms(goal)

    per_finding: list[FindingScope] = []
    on_scope = 0
    off_scope = 0
    unmeasurable = 0
    off_scope_findings: list[str] = []

    for finding in findings:
        if not finding or not finding.strip():
            raise ScopeAdherenceError("findings must be non-empty strings")
        terms = _distinctive_terms(finding)
        if not terms:
            per_finding.append(
                FindingScope(
                    finding=finding,
                    verdict="unmeasurable",
                    goal_overlap_count=0,
                )
            )
            unmeasurable += 1
            continue
        overlap_count = len(terms & goal_pool)
        if overlap_count >= min_goal_overlap:
            verdict = "on_scope"
            on_scope += 1
        else:
            verdict = "off_scope"
            off_scope += 1
            off_scope_findings.append(finding)
        per_finding.append(
            FindingScope(
                finding=finding,
                verdict=verdict,
                goal_overlap_count=overlap_count,
            )
        )

    measurable = on_scope + off_scope
    on_scope_ratio = on_scope / measurable if measurable else None
    off_scope_ratio = off_scope / measurable if measurable else None

    if on_scope_ratio is None:
        verdict = "unknown"
    elif on_scope_ratio == 0.0:
        verdict = "fully_off_scope"
    elif on_scope_ratio >= adherence_threshold:
        verdict = "on_scope"
    else:
        verdict = "drifted"

    notes: list[str] = [
        "scope adherence measures whether an unattended Midnight Oil run's findings "
        "stayed WITHIN its declared goals — the NEGATIVE complement to goal_delivery "
        "#1938 (which asks the POSITIVE: did findings address the goals). "
        "goal_delivery = recall over goals (forward); this = precision over findings "
        "(backward). The precision/recall duality of the goal-finding relationship, "
        "same split as twin_fidelity #1954 (precision) vs twin_coverage #1964 (recall)",
        "a finding is on_scope if it shares >= min_goal_overlap distinctive terms "
        "with the goal pool (the union of all goals' content words = the scope "
        "boundary); otherwise off_scope (its content traces to no declared goal = "
        "drift). on_scope_ratio = on_scope / measurable findings",
        "verdict: on_scope (>= threshold, control held), drifted (< threshold but > "
        "0, partial control failure — some findings wandered), fully_off_scope (0%, "
        "total runaway — no finding addresses any goal), unknown (no measurable "
        "findings — defer, never fabricated)",
        "off-scope is a CONTROL/DRIFT signal, never a truth verdict — an off-scope "
        "finding may be a serendipitous discovery, necessary precondition, or "
        "correction of a flawed goal; the operator decides gift vs waste on return. "
        "goal_delivery carries the 'goals met' lane; this carries the 'stayed in "
        "lane' lane",
        "lexical floor (no stemming/synonymy): an on-topic finding using different "
        "vocabulary than the goals may score off-scope — prefers flagging a rephrased "
        "on-topic finding (false positive) over certifying on-scope a finding that "
        "merely shares a content word (false negative); all-glue findings excluded "
        "(carried as unmeasurable_count, never fabricated as off-scope); a semantic "
        "relevance check confirms downstream",
    ]
    ratio_str = f"{on_scope_ratio:.0%}" if on_scope_ratio is not None else "n/a"
    notes.append(
        f"verdict {verdict}: on_scope_ratio {ratio_str} "
        f"({on_scope} on_scope, {off_scope} off_scope, {unmeasurable} unmeasurable "
        f"of {len(findings)} finding(s)); goal_pool_size {len(goal_pool)}; "
        f"{off_scope} drift finding(s); threshold "
        f"{adherence_threshold:.0%}"
    )

    return ScopeAdherenceReport(
        on_scope_count=on_scope,
        off_scope_count=off_scope,
        unmeasurable_count=unmeasurable,
        on_scope_ratio=on_scope_ratio,
        off_scope_ratio=off_scope_ratio,
        goal_pool_size=len(goal_pool),
        finding_scopes=tuple(per_finding),
        off_scope_findings=tuple(off_scope_findings),
        adherence_threshold=adherence_threshold,
        min_goal_overlap=min_goal_overlap,
        verdict=verdict,
        notes=tuple(notes),
    )

