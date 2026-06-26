"""Task-class taxonomy — a coarse, operator-legible prior on sub-questions.

STATUS: DRAFT. This taxonomy is provisional pending operator
ratification (an open question on the master spec). The five classes
below are the first cut; the operator may rename, merge, or split them
after seeing real decomposer output. Until ratified, ``unclassified``
is the honest escape hatch so nothing is silently force-fit into a
class the heuristic isn't confident about.

Why a taxonomy at all (and why here, not in the router)
------------------------------------------------------
The router (SPR-07) selects a provider/tier for a sub-question. Its
single best input — besides cost/latency estimates — is WHAT KIND of
question it is routing: a needle-in-a-haystack lookup wants a cheap
fast tier; a multi-hop synthesis wants a deep-reasoning tier. A
task-class label is that input. This module ships a COARSE prior (a
deterministic keyword heuristic) so the measurement record (SPR-02)
can carry a task_class field from day one — the router will later
replace this prior with its own real classification (SPR-07), but the
FIELD exists now so historical measurements are classifiable
retroactively and the router has something to learn from on day one.

Why the classes are mutually distinguishable by a WRITTEN rule
--------------------------------------------------------------
A taxonomy a reviewer can't apply consistently is vibes, not a
taxonomy. Each class below has a one-line definition + an example
question + a classification rule (in ``classify``) precise enough that
two reviewers handed the same five example questions assign the same
labels (or agree it's ``unclassified``). The rule is keyword/
heuristic — deliberately coarse, deliberately deterministic, and
deliberately documented as a PRIOR, not the router's judgment. Real
classification (semantic, calibrated) is SPR-07's job; this is the
cheap label that lets the measurement record be useful before SPR-07
ships.
"""

from __future__ import annotations

from enum import Enum


class TaskClass(str, Enum):
    """Coarse task-class prior for a research sub-question.

    A ``str, Enum`` (matching the codebase's ``ActionType`` idiom) so the
    value serializes to JSON as its string and a reader can compare
    against the string without importing the enum (forward-compat: an
    unknown class from a future version parses without crashing).

    Members (each: definition + example)
    ------------------------------------
    structured_extract:
        The answer is a specific field/value extractable from a known
        source by pattern or lookup — a number, a name, a date, a
        yes/no. The retrieval is the hard part; once found, the answer
        is mechanical.
        Example: "What was Anthropic's ARR as of 2024-12-31?"

    broad_gather:
        The answer requires assembling a broad survey of a space — many
        sources, no single canonical one, breadth valued over depth.
        Tolerance for partial coverage; the value is the aggregate.
        Example: "What are the main open-source vector databases and
        their differentiating features?"

    needle_in_haystack:
        The answer is a specific fact that exists but is buried in a
        large / hard-to-search corpus — finding it is the task, and the
        fact is small once found. Distinguished from
        ``structured_extract`` by the search difficulty (the value is in
        locating, not parsing).
        Example: "Which SEC filing first disclosed the Series E round?"

    multi_hop:
        The answer requires chaining two or more retrieval/reasoning
        steps where each step's output feeds the next — no single source
        answers it, and the hops are not independent (step 2's query
        depends on step 1's answer).
        Example: "Who is the current CEO of the company that acquired
        the startup whose Series B was led by Sequoia in 2019?"

    unclassified:
        The heuristic could not confidently assign one of the above.
        Exists so NOTHING is silently force-fit: an ``unclassified``
        record is an honest "the prior didn't fire" signal, which the
        router (SPR-07) can treat as "use real classification" rather
        than inheriting a wrong prior.
        Example: any question the heuristic's keywords don't match
        strongly enough (see ``classify`` thresholds).
    """

    STRUCTURED_EXTRACT = "structured_extract"
    BROAD_GATHER = "broad_gather"
    NEEDLE_IN_HAYSTACK = "needle_in_haystack"
    MULTI_HOP = "multi_hop"
    UNCLASSIFIED = "unclassified"


# Keyword signals per class. Ordered by the classification rule's priority
# (multi_hop first — its signal is the most specific and should win over
# broad_gather when both fire). Kept as plain lowercase substrings so the
# rule is grep-able and a reviewer can audit exactly which words trigger
# which class. The lists are intentionally short: a long keyword list is a
# disguised classifier (and the router's job, not this prior's).
_MULTI_HOP_SIGNALS = (
    "who is the current",      # chains "who is X" -> "X acquired Y" -> ...
    "company that acquired",   # explicit acquisition-chain hop
    "startup whose",           # hop through a funding event to an entity
    "then who",                # explicit sequential chaining
    "as a result of which",    # causal chain
    "led to",
)

_NEEDLE_SIGNALS = (
    "which filing",            # specific document locator
    "first disclosed",         # temporal-ordinal locator in a corpus
    "where exactly",           # pinpoint locator
    "buried in",
    "find the",                # imperative locate-a-specific-thing
    "which sec filing",
)

_STRUCTURED_SIGNALS = (
    "what was",                # extract a specific past value
    "as of",                   # point-in-time value extract
    "how many",                # count extract
    "what is the current",     # current-value extract (single hop)
    "list the",                # bounded enumeration from a known set
    "date of",
    "revenue",
    "arr",
    "valuation",
)

_BROAD_SIGNALS = (
    "what are the main",       # survey the space
    "what are the different",  # comparative survey
    "overview of",
    "landscape",
    "survey of",
    "all the",
    "compare",
)


def _lower(s: str) -> str:
    return s.lower().strip()


def _count_hits(text: str, signals: tuple[str, ...]) -> int:
    """How many distinct signal phrases appear in ``text``."""
    return sum(1 for s in signals if s in text)


def classify(sub_question: str) -> TaskClass:
    """Assign a coarse ``TaskClass`` prior to a sub-question.

    DETERMINISTIC. A keyword/heuristic rule, NOT semantic classification
    — document this when wiring: real classification (calibrated,
    embedding-based, or LLM-judged) is the router's job in SPR-07. This
    is the cheap prior that lets the measurement record carry a
    task_class from day one.

    Rule (priority order — first match wins, most-specific first):

    1. multi_hop: if the question contains a chaining signal
       (``"company that acquired"``, ``"who is the current"``, etc.) —
       these phrases structurally imply a hop chain.
    2. needle_in_haystack: if it contains a locator signal
       (``"which filing"``, ``"first disclosed"``, ``"find the"``)
       — these imply the task is locating a specific buried fact.
    3. structured_extract: if it contains a value-extract signal
       (``"what was"``, ``"as of"``, ``"how many"``, ``"arr"``) —
       these imply a mechanical extract from a located source.
    4. broad_gather: if it contains a survey signal
       (``"what are the main"``, ``"overview of"``, ``"landscape"``)
       — these imply a breadth-valued survey.
    5. unclassified: if no signal fires OR the top two classes tie
       (ambiguous — the prior declines rather than guess).

    The priority order resolves overlaps deterministically: a question
    like "What was the revenue of the company that acquired X" hits both
    ``structured_extract`` (``"what was"``, ``"revenue"``) and
    ``multi_hop`` (``"company that acquired"``) — multi_hop wins because
    the chaining is the structurally dominant feature (the revenue is
    the leaf, the chain is the task).

    Args:
        sub_question: the sub-question text (the same string passed to
            ``ResearchProvider.answer``).

    Returns:
        A ``TaskClass``. Never raises — an unclassifiable question
        returns ``UNCLASSIFIED``, which is the honest escape hatch.
    """
    if not sub_question or not sub_question.strip():
        return TaskClass.UNCLASSIFIED

    text = _lower(sub_question)

    # Priority order: most-specific (chaining) first, least-specific
    # (survey) last. First hit wins.
    if _count_hits(text, _MULTI_HOP_SIGNALS) >= 1:
        return TaskClass.MULTI_HOP
    if _count_hits(text, _NEEDLE_SIGNALS) >= 1:
        return TaskClass.NEEDLE_IN_HAYSTACK
    if _count_hits(text, _STRUCTURED_SIGNALS) >= 1:
        return TaskClass.STRUCTURED_EXTRACT
    if _count_hits(text, _BROAD_SIGNALS) >= 1:
        return TaskClass.BROAD_GATHER

    # No signal fired — honest escape hatch. The router (SPR-07) will
    # classify for real; the prior declines rather than force-fit.
    return TaskClass.UNCLASSIFIED


__all__ = ["TaskClass", "classify"]
