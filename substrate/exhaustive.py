"""substrate/exhaustive.py — exhaustive-match helper + canonical pattern.

ARE-03 paved road. The closed-set-variant + ``match`` + exhaustiveness
discipline from the Rust interview, expressed as the Antiek idiom that
future dispatch / ingestion / verifier variant types follow.

``typing.assert_never`` already gives the static guarantee: if a
``match`` over a closed Literal/Enum can reach the ``case _:`` arm with
a value mypy hasn't narrowed to ``Never``, mypy --strict errors. This
module adds two things on top:

1. ``assert_exhaustive`` — a thin wrapper that, IF somehow reached at
   runtime (e.g. a value snuck in from an untyped boundary that
   bypassed mypy), raises a clear, debuggable error naming the
   unexpected value + the match's context, instead of
   ``assert_never``'s bare AssertionError. The static guarantee is
   identical (the parameter is typed ``Never``); the runtime message is
   better.

2. The canonical pattern, documented + demonstrated, so a contributor
   adding a new closed-set variant type writes the same shape every
   time. See ``classify_reference_outcome`` below for the reference.

The discipline (the Rust "the compiler tells you everywhere to fix"
property): when you add a variant to a closed Literal/Enum, mypy
--strict flags EVERY match that switched on the old set and didn't
handle the new arm. That turns "I forgot to handle the new case in 3
places" from a production incident into a type error. Closed-set only —
open-set plug-in dispatches (adapter registries, role-program
registries) use a dict registry and intentionally do NOT get this
treatment.

Example (the canonical shape):

    >>> classify_reference_outcome("allowed")
    'proceed'
    >>> classify_reference_outcome("blocked")
    'halt'
    >>> classify_reference_outcome("held")
    'queue-for-review'
"""

from __future__ import annotations

from typing import Literal, Never, assert_never

__all__ = [
    "assert_exhaustive",
    "ReferenceOutcome",
    "classify_reference_outcome",
]


def assert_exhaustive(value: Never, *, context: str = "") -> Never:
    """Mark a ``match`` as exhaustive over a closed variant set.

    Place at the end of a match (in the ``case _:`` arm, or after the
    arms if you've handled every variant explicitly). Statically, mypy
    --strict errors if any variant is unhandled (the value won't be
    narrowed to ``Never``). At runtime — which should be unreachable if
    mypy passed — raises a clear error naming the unexpected value.

    ``context`` is an optional label (usually the function or the
    variant-type name) that makes the runtime error pinpoint which
    match was non-exhaustive.

    Why not just ``typing.assert_never``: identical static behavior, but
    ``assert_never``'s runtime AssertionError carries only the value's
    repr with no context. When an untyped boundary (a YAML config, a raw
    LLM string) sneaks an unexpected value past mypy, this message tells
    the operator exactly which match broke and that a variant was likely
    added without updating the match.
    """
    # Delegate to the stdlib for the static Never-narrowing guarantee;
    # the line below is unreachable when mypy passes. We still raise our
    # richer error first so the runtime message is useful, then keep the
    # assert_never call so static analyzers see the canonical sentinel.
    ctx = f" in {context}" if context else ""
    message = (
        f"non-exhaustive match{ctx}: unexpected value {value!r}. "
        f"A new variant was likely added without updating this match — "
        f"mypy --strict should have caught this at type-check time. "
        f"If this value came from an untyped boundary (config, raw LLM "
        f"output), validate it into the closed variant set at the "
        f"boundary instead of matching on a raw string."
    )
    raise AssertionError(message)
    assert_never(value)  # pragma: no cover  — canonical sentinel for analyzers


# ---------------------------------------------------------------------- #
# Canonical reference — the shape future closed-set variants follow.     #
#                                                                        #
# This is a DEMONSTRATION, not a real Antiek variant type. The real      #
# dispatch-tier / ingestion-source / verifier-outcome conversions are    #
# operator-gated (ARE-03 milestones 2-3) because they must reconcile     #
# with the existing dispatch-tier-verdict ADR + the ActionType union.    #
# This reference shows the pattern WITHOUT colliding with those.         #
# ---------------------------------------------------------------------- #

ReferenceOutcome = Literal["allowed", "blocked", "held"]


def classify_reference_outcome(outcome: ReferenceOutcome) -> str:
    """Reference exhaustive match over a closed 3-variant set.

    The canonical shape: one ``case`` per variant, then
    ``assert_exhaustive`` in the catch-all. Adding a fourth variant to
    ``ReferenceOutcome`` (say ``"escalated"``) makes mypy --strict error
    on this function until the new arm is handled — that's the guarantee.

    A contributor adding a real closed-set variant type copies this
    shape: define the Literal/Enum, write the match with one arm per
    variant, end with ``assert_exhaustive(value, context="<name>")``.
    """
    match outcome:
        case "allowed":
            return "proceed"
        case "blocked":
            return "halt"
        case "held":
            return "queue-for-review"
        case _:
            assert_exhaustive(outcome, context="classify_reference_outcome")
