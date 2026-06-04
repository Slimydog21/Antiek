"""The reality-contact ratio (RCR) — a PURE function over the SPR-01 ledger.

SPR-01 emitted ``ledger.json``: per test-file verdicts plus, for every file, a
``subsystem_labels`` map keyed by CORE module name with values drawn from
``{"reality", "theater", "indeterminate"}`` (a ``mixed`` verdict expands into
per-subsystem ``reality`` for the cores it runs for real and ``theater`` for the
cores it mocks). This module turns those labels into one number — overall and
per subsystem — and NOTHING else: no I/O, no imports of any product/CORE module,
no knowledge of where the ledger lives. It is handed the already-parsed ledger
dict and returns numbers. That purity is load-bearing: the scoreboard must be
incapable of the inflation it measures, so the arithmetic lives here where it can
be pinned to hand-built inputs.

DEFINITIONS (defensibility — quote these in SPR-04's baseline / SPR-06's record)
--------------------------------------------------------------------------------
For each CORE subsystem ``S``:

  * ``claiming(S)``  = number of ledger files whose ``subsystem_labels`` contains
                       ``S`` at all. A file "claims" a core when it imports/touches
                       that core, regardless of whether it then runs it for real,
                       mocks it (``theater``), or leaves the classifier unable to
                       decide (``indeterminate``). n-a files — those with NO core
                       label — are NEVER in any ``claiming`` count, which is why
                       padding the suite with n-a tests cannot move RCR.
  * ``reality(S)``   = of those, the count with ``subsystem_labels[S] == "reality"``.
  * ``theater(S)``   = count with ``subsystem_labels[S] == "theater"``.
  * ``indet(S)``     = count with ``subsystem_labels[S] == "indeterminate"``.
  * ``RCR(S)``       = ``reality(S) / claiming(S)``  (``None`` when ``claiming(S) == 0``).

CONSERVATIVE INDETERMINATE HANDLING (honesty)
---------------------------------------------
``indeterminate`` labels count toward ``claiming`` (the denominator) but NOT
toward ``reality`` (the numerator). The classifier reaches ``indeterminate`` when
it cannot prove the core ran for real — so crediting it as reality would be the
self-flattery this whole instrument exists to kill. An indeterminate label can
therefore only ever HOLD RCR DOWN or LEAVE IT FLAT; it can never raise it. It is
reported in its own column, never folded into ``reality``.

HEADLINE AGGREGATION RULE — claiming-count-weighted (NOT a mean of ratios)
--------------------------------------------------------------------------
The headline RCR is::

    headline = sum(reality(S) for all S) / sum(claiming(S) for all S)

i.e. one reality-labelled (file, subsystem) claim over one claim, pooled across
every subsystem. Equivalently it is the ``claiming(S)``-weighted average of the
per-subsystem ``RCR(S)``. We DELIBERATELY reject a naive ``mean(RCR(S) over S)``:
that gives a subsystem with 2 claiming files the same vote as one with 84, so a
single perfect-but-tiny subsystem would flatter (or a tiny bad one would tank)
the headline out of proportion to how much of the suite it represents. The pooled
claim-weighted ratio answers the actually-useful question — "of all the core-
claiming (file, subsystem) pairs in the suite, what fraction make real contact?"
— and is the denominator SPR-04 should freeze a baseline against.

NOTE: a file that claims K subsystems contributes K (file, subsystem) claims to
the pooled counts (each at its own per-subsystem label). This is intentional: the
unit of "a claim" is a (file, subsystem) pair, not a file, because a single file
can make real contact with one core while mocking another.

BLIND SPOT (carried, never computed here): a HIGH RCR is NOT "the suite is real."
Provider/LLM mocks are BOUNDARY by design, and the dominant fake-the-LLM pattern
in this codebase is dependency injection, which is invisible to the classifier —
so DI-stubbed tests are counted ``reality``. The caveat lives in the ledger's
``known_blind_spots`` block; the CLI prints it adjacent to the number. This module
does not soften the number; the number is honest only WITH that caveat attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# The label values SPR-01's classifier emits inside ``subsystem_labels``.
# A "reality" label is the ONLY one that lands in the numerator; every other
# value (theater, indeterminate, or any future value) counts toward claiming
# but never toward reality — fail-safe so an unknown label can never inflate RCR.
REALITY_LABEL = "reality"
THEATER_LABEL = "theater"
INDETERMINATE_LABEL = "indeterminate"


@dataclass(frozen=True)
class SubsystemRCR:
    """RCR for one CORE subsystem, with the raw counts behind it.

    ``rcr`` is ``None`` exactly when ``claiming == 0`` (no file claims this core,
    so the ratio is undefined — reported as ``n/a``, never as ``0.0`` or ``1.0``,
    so an unclaimed subsystem cannot silently move the headline either way).
    """

    subsystem: str
    claiming: int
    reality: int
    theater: int
    indeterminate: int
    # Any claim whose label is none of reality/theater/indeterminate. Zero under
    # SPR-01's current contract (it emits exactly those three); captured so an
    # unrecognized label can never sit silently in the `claiming` denominator with
    # no column to explain it — it surfaces instead of quietly lowering RCR.
    other: int
    rcr: float | None


@dataclass(frozen=True)
class RealityContactMetric:
    """The full metric reading: per-subsystem rows + the claim-weighted headline.

    ``headline_rcr`` is ``None`` exactly when ``total_claiming == 0`` (an empty or
    n-a-only ledger has no core claims, so there is no ratio to report).
    """

    per_subsystem: tuple[SubsystemRCR, ...]
    total_claiming: int
    total_reality: int
    total_theater: int
    total_indeterminate: int
    total_other: int
    headline_rcr: float | None


def _iter_subsystem_labels(ledger: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten the ledger into (subsystem, label) claim pairs — one per core a
    file touches. A file claiming K cores yields K pairs. n-a files (no labels)
    contribute nothing, which is the structural reason n-a padding is inert."""
    pairs: list[tuple[str, str]] = []
    for entry in ledger.get("files", []):
        labels = entry.get("subsystem_labels") or {}
        for subsystem, label in labels.items():
            pairs.append((subsystem, str(label)))
    return pairs


def compute_metric(ledger: dict[str, Any]) -> RealityContactMetric:
    """Compute the RCR metric from a parsed SPR-01 ledger dict. Pure: no I/O.

    The set of CORE subsystems reported is the union of (a) the ledger's declared
    ``core_modules`` and (b) any subsystem actually appearing in a label — so a
    declared-but-unclaimed core still shows (as ``claiming=0``, ``rcr=None``), and
    a label naming a non-declared subsystem can never be silently dropped.
    """
    pairs = _iter_subsystem_labels(ledger)

    declared = list(ledger.get("core_modules") or [])
    subsystems = sorted({s for s, _ in pairs} | set(declared))

    rows: list[SubsystemRCR] = []
    total_claiming = total_reality = total_theater = total_indeterminate = total_other = 0
    for s in subsystems:
        labels = [label for sub, label in pairs if sub == s]
        claiming = len(labels)
        reality = sum(1 for label in labels if label == REALITY_LABEL)
        theater = sum(1 for label in labels if label == THEATER_LABEL)
        indeterminate = sum(1 for label in labels if label == INDETERMINATE_LABEL)
        # Everything left over: a label the contract does not name. By
        # construction claiming == reality + theater + indeterminate + other, so
        # no claim can vanish from the denominator unexplained.
        other = claiming - reality - theater - indeterminate
        rcr = (reality / claiming) if claiming else None
        rows.append(
            SubsystemRCR(
                subsystem=s,
                claiming=claiming,
                reality=reality,
                theater=theater,
                indeterminate=indeterminate,
                other=other,
                rcr=rcr,
            )
        )
        total_claiming += claiming
        total_reality += reality
        total_theater += theater
        total_indeterminate += indeterminate
        total_other += other

    # Claiming-count-weighted headline == pooled reality-claims / total-claims.
    # (See the module docstring for why this beats a naive mean of ratios.)
    headline = (total_reality / total_claiming) if total_claiming else None

    return RealityContactMetric(
        per_subsystem=tuple(rows),
        total_claiming=total_claiming,
        total_reality=total_reality,
        total_theater=total_theater,
        total_indeterminate=total_indeterminate,
        total_other=total_other,
        headline_rcr=headline,
    )
