r"""Book acquisition budget planner — pre-purchase projection + affordability gate.

Operator vision (ask #5): *"I want to read books, and I am okay with buying a digital
book if there is no pdf online so build the marketplace functionality and also the
seamless port so that book gets hosted in my account on Antiek."* Buying books is a
SPEND category. The book-purchase-transport decision spec (invariant #5) requires:
*"Pre-purchase projection gates on ``would_exceed_budget``; no acquisition bypasses the
budget/consent gate."* This module is that gate's pure computation — the decision-
independent atom that ANY transport channel (1A operator-external checkout, 1B store-API,
1C PCI) calls before an acquisition proceeds. It answers: given the operator's acquisition
budget, current spend, and a candidate batch of books (each with a price, a DRM status, and
a priority), what can the budget absorb — and what must be deferred?

**Genuinely distinct from the budget surface (load-bearing):**

* ``midnight_oil/budget_ledger`` (#720/#1000): a RUN-TIME reserve/settle ledger for
  autonomous research-run spend (LLM role costs during a Midnight Oil run). THIS is
  CONTENT-PURCHASE spend (buying books to host in the library) — a different spend
  category with a different lifecycle (one-time purchase, not metered API consumption).
* ``budget_browserbase`` / ``search/exa/budget``: per-source INFRASTRUCTURE spend caps
  (Browserbase scrape cost, Exa search cost). THIS is the operator's CONTENT budget —
  buying books, not paying for scraping infrastructure.
* ``budget/projection`` (#1838): forward LLM PROMPT-cost projection (token cost of a
  proposed prompt). THIS is book-PURCHASE cost — a different artifact entirely.
* ``ceiling_accuracy`` (#1968): did the RECOMMENDED Midnight Oil cost ceiling match
  actual (backward calibration). THIS is forward content-acquisition affordability.

None measures book-acquisition purchase cost against the operator's content budget. This
is the only gate that answers: *"can I afford this batch of books right now?"*

**The measurement (hard to vary).**

For a candidate batch of book acquisitions (each ``book_id``, ``price_usd_cents`` >= 0,
``drm_free`` bool, ``priority`` int where higher = more desired):

1. ``remaining_budget = budget_limit - current_period_spend`` (can be negative if
   over-spent — then only free books are affordable).
2. ``batch_total = Σ price`` over all candidates.
3. If ``batch_total <= remaining_budget`` → the FULL BATCH is affordable (every book
   fits). Verdict ``batch_affordable``.
4. Otherwise → GREEDY SELECTION by the spec's preference order to maximize coverage
   within the remaining budget:
   * **DRM-free first** (spec invariant #3: *"prefer DRM-free sources"* — a DRM-locked
     book requires the operator to re-acquire DRM-free or open in the store's reader, so
     a DRM-free candidate is always preferred when both are affordable).
   * then **higher priority** (the operator's declared desire order).
   * then **lower price** (more coverage per dollar).
   * then ``book_id`` ascending (deterministic tiebreak).
   Each selected book consumes from the running remaining; the rest are **deferred**
   (with an honest reason: ``exceeds_remaining``).
5. ``would_exceed_budget = batch_total > remaining_budget`` (the full batch does not fit).

**Key properties (load-bearing):**

* A FREE book (``price == 0``) is ALWAYS affordable regardless of remaining budget — it
  worsens no overspend. This is the one case where a book clears the gate with zero or
  negative remaining.
* The planner PROPOSES, the operator DECIDES. ``authority = "advisory"`` — this gate
  never auto-acquires. The transport adapter (post the operator's 1A/1B/1C decision)
  checks ``would_exceed_budget`` and demands explicit operator consent before proceeding
  (the MO #1000 recommend→approve→run pattern, applied to acquisition).
* Greedy selection is a HEURISTIC (not optimal knapsack) — it is honest about this: the
  affordable set is a sound (fits-the-budget) proposal, not a provably-maximal one. The
  operator can override the ordering. A cheaper optimal solver would hide behind
  complexity for marginal gain; the greedy ordering is auditable and matches the spec's
  stated preference (DRM-free → priority → price).
* DRM-free preference is the spec's HARD RULE (invariant #3), not a tunable — a DRM-free
  book always sorts before a DRM-locked one at equal priority because the spec refuses to
  port DRM-locked files.

**Measured fields:**

* ``remaining_budget`` — ``budget_limit - current_spend`` (can be negative).
* ``batch_total`` — sum of all candidate prices.
* ``would_exceed_budget`` — does the full batch exceed remaining.
* ``affordable_count`` / ``deferred_count`` — the greedy-partitioned counts.
* ``projected_remaining_after_affordable`` — what the budget drops to if the affordable
  set is acquired (the post-purchase balance).
* ``affordable_books`` — the greedy-selected set, in acquisition order (auditable).
* ``deferred_books`` — the rest, each with ``reason`` (auditable — why it was deferred).
* ``cheapest_affordable_price`` / ``priciest_affordable_price`` — the affordable set's
  price range (auditable).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero candidates -> ``no_candidates`` (trivial — nothing to plan; not an error).
* ``batch_total <= remaining_budget`` -> ``batch_affordable`` (every book fits — acquire
  all; the strongest signal).
* ``affordable_count >= 1`` but batch does not fully fit -> ``partial_affordable`` (the
  greedy covered some, deferred the rest — the common case).
* ``affordable_count == 0`` and ``batch_total > 0`` -> ``none_affordable`` (remaining
  budget cannot absorb any paid book — honest defer of the whole batch).
- ``batch_total == 0`` -> ``all_free`` (every candidate is free — no budget consumed; a
  distinct honest state from ``batch_affordable`` which implies real spend that fits).

**DESCRIPTIVE NOT NORMATIVE:** ``batch_affordable`` does NOT mean "buy them all" — the
operator still consents per-book (a book that fits the budget may still be unwanted).
``none_affordable`` does NOT mean "bad" — it means the budget is exhausted and the
operator must raise it, wait for the next period, or acquire only free sources. The gate
reports affordability, not desire.

**Honesty rules (load-bearing):**

* ``no_candidates`` is a trivial base case (``would_exceed_budget = False``, all counts
  zero, ``projected_remaining_after = remaining_budget``) — never fabricated.
* ``all_free`` (batch_total 0) is distinct from ``batch_affordable`` (real spend that
  fits) — both fit, but ``all_free`` consumes no budget.
* ``none_affordable`` carries ``would_exceed_budget = True`` and honest zero
  ``affordable_count`` — distinct from ``no_candidates`` (nothing to evaluate).
* ``deferred_books.reason`` is auditable (``exceeds_remaining`` — the book's price
  exceeded the running remaining after greedy picks).
* Negative ``remaining_budget`` (over-spent) is handled honestly: only free books clear;
  every paid book is deferred.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no clock, no
  mutation, no DB.
* ``authority`` is always ``"advisory"``; import-free of off-main siblings (plain
  ``CandidateAcquisition`` inputs; the transport adapter adapts 1:1 post-decision).

**Spec reference:** ``.infinite/sprint-briefs/book-purchase-transport-decision-spec.md``
invariants #3 (DRM-free preference) and #5 (pre-purchase projection gate). This module
is decision-independent: it works for transport 1A, 1B, or 1C — the channel choice is the
operator's, the affordability math is not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "AffordableBook",
    "BookAcquisitionBudgetError",
    "BookAcquisitionBudgetReport",
    "CandidateAcquisition",
    "DeferredBook",
    "plan_book_acquisition_budget",
]


@dataclass(frozen=True)
class CandidateAcquisition:
    """One book the operator is considering acquiring (a planner input).

    ``price_usd_cents`` >= 0 (0 = free/public-domain — always affordable).
    ``drm_free`` — True if the source offers a DRM-free file (portable to HTML); False
    if DRM-locked (spec invariant #3: prefer DRM-free).
    ``priority`` — the operator's declared desire (higher = more wanted).
    """

    book_id: str
    price_usd_cents: int
    drm_free: bool
    priority: int


@dataclass(frozen=True)
class AffordableBook:
    """A book the budget can absorb, in greedy acquisition order. Auditable."""

    book_id: str
    price_usd_cents: int
    drm_free: bool
    priority: int


@dataclass(frozen=True)
class DeferredBook:
    """A book the budget cannot absorb right now. Auditable.

    ``reason`` is ``exceeds_remaining`` — the book's price exceeded the running
    remaining budget after the greedy selection consumed what it could.
    """

    book_id: str
    price_usd_cents: int
    drm_free: bool
    priority: int
    reason: str


@dataclass(frozen=True)
class BookAcquisitionBudgetReport:
    """The pre-purchase affordability plan for a candidate batch. Advisory, pure."""

    remaining_budget: int  # budget_limit - current_spend; can be negative
    batch_total: int  # sum of all candidate prices
    would_exceed_budget: bool  # batch_total > remaining_budget
    affordable_count: int
    deferred_count: int
    projected_remaining_after_affordable: int  # remaining - sum(affordable prices)
    affordable_books: tuple[AffordableBook, ...]
    deferred_books: tuple[DeferredBook, ...]
    cheapest_affordable_price: int | None  # None when nothing affordable
    priciest_affordable_price: int | None
    verdict: str  # no_candidates | all_free | batch_affordable | partial_affordable | none_affordable
    notes: tuple[str, ...]
    authority: str = "advisory"


class BookAcquisitionBudgetError(ValueError):
    """A book-acquisition-budget input violates a load-bearing invariant."""


def plan_book_acquisition_budget(
    candidates: Sequence[CandidateAcquisition],
    *,
    budget_limit_usd_cents: int,
    current_period_spend_usd_cents: int,
) -> BookAcquisitionBudgetReport:
    """Plan the affordability of a candidate book-acquisition batch.

    ``candidates`` are the books under consideration (each with price, DRM status,
    priority). ``budget_limit_usd_cents`` is the operator's content-acquisition budget
    for the period. ``current_period_spend_usd_cents`` is what has already been spent
    this period. Returns a :class:`BookAcquisitionBudgetReport` with the greedy
    affordability partition and the pre-purchase projection.

    Pure: no DB, no LLM, no clock, no mutation.
    """
    if budget_limit_usd_cents < 0:
        raise BookAcquisitionBudgetError(
            f"budget_limit_usd_cents must be >= 0, got {budget_limit_usd_cents!r}"
        )
    if current_period_spend_usd_cents < 0:
        raise BookAcquisitionBudgetError(
            f"current_period_spend_usd_cents must be >= 0, got "
            f"{current_period_spend_usd_cents!r}"
        )
    for cand in candidates:
        if cand.price_usd_cents < 0:
            raise BookAcquisitionBudgetError(
                f"price_usd_cents must be >= 0, got {cand.price_usd_cents!r} "
                f"for book {cand.book_id!r}"
            )
        if not cand.book_id.strip():
            raise BookAcquisitionBudgetError(
                "book_id must be a non-empty string"
            )

    remaining = budget_limit_usd_cents - current_period_spend_usd_cents

    if not candidates:
        return BookAcquisitionBudgetReport(
            remaining_budget=remaining,
            batch_total=0,
            would_exceed_budget=False,
            affordable_count=0,
            deferred_count=0,
            projected_remaining_after_affordable=remaining,
            affordable_books=(),
            deferred_books=(),
            cheapest_affordable_price=None,
            priciest_affordable_price=None,
            verdict="no_candidates",
            notes=(
                "no candidate acquisitions to plan; the gate is trivially clear "
                "(nothing to acquire)",
            ),
        )

    batch_total = sum(c.price_usd_cents for c in candidates)

    # Greedy preference order per spec invariants #3 (DRM-free first) + priority + price.
    ordered = sorted(
        candidates,
        key=lambda c: (not c.drm_free, -c.priority, c.price_usd_cents, c.book_id),
    )

    affordable: list[AffordableBook] = []
    deferred: list[DeferredBook] = []
    running = remaining
    for cand in ordered:
        # A free book (price 0) is always affordable regardless of remaining.
        if cand.price_usd_cents == 0 or cand.price_usd_cents <= running:
            affordable.append(
                AffordableBook(
                    book_id=cand.book_id,
                    price_usd_cents=cand.price_usd_cents,
                    drm_free=cand.drm_free,
                    priority=cand.priority,
                )
            )
            running -= cand.price_usd_cents
        else:
            deferred.append(
                DeferredBook(
                    book_id=cand.book_id,
                    price_usd_cents=cand.price_usd_cents,
                    drm_free=cand.drm_free,
                    priority=cand.priority,
                    reason="exceeds_remaining",
                )
            )

    affordable_count = len(affordable)
    deferred_count = len(deferred)
    would_exceed = batch_total > remaining
    projected_after = remaining - sum(a.price_usd_cents for a in affordable)

    affordable_prices = [a.price_usd_cents for a in affordable]
    cheapest = min(affordable_prices) if affordable_prices else None
    priciest = max(affordable_prices) if affordable_prices else None

    if batch_total == 0:
        verdict = "all_free"
    elif not would_exceed:
        verdict = "batch_affordable"
    elif affordable_count >= 1:
        verdict = "partial_affordable"
    else:
        verdict = "none_affordable"

    notes: list[str] = [
        "book-acquisition budget planner — pre-purchase affordability gate (asks #5/#8); "
        "the decision-independent atom any transport channel (1A/1B/1C) calls before an "
        "acquisition proceeds; spec invariant #5: no acquisition bypasses the budget/"
        "consent gate; midnight_oil budget_ledger #720 is RUN-TIME research spend, "
        "budget_browserbase is INFRA scrape cost, budget/projection #1838 is PROMPT "
        "token cost — none measures CONTENT-purchase affordability (this)",
        "greedy selection by spec preference (DRM-free first per invariant #3, then "
        "priority desc, then price asc, then book_id) — a sound fits-the-budget "
        "proposal, not a provably-optimal knapsack; the operator approves each "
        "acquisition (advisory, consent-gated — never auto-acquires)",
    ]
    if remaining < 0:
        notes.append(
            f"OVER-SPENT: current spend exceeds budget by {-remaining} cents — remaining "
            f"is negative; only free books (price 0) clear the gate, every paid book is "
            f"deferred"
        )
    if verdict == "all_free":
        notes.append(
            f"all {affordable_count} candidate(s) are free (price 0) — no budget consumed; "
            f"a distinct state from batch_affordable (which implies real spend that fits)"
        )
    elif verdict == "batch_affordable":
        notes.append(
            f"full batch affordable: batch_total {batch_total} <= remaining {remaining}; "
            f"all {affordable_count} book(s) clear the gate (projected remaining after "
            f"acquisition {projected_after})"
        )
    elif verdict == "partial_affordable":
        notes.append(
            f"partial: {affordable_count} affordable, {deferred_count} deferred "
            f"(exceeds_remaining); batch_total {batch_total} > remaining {remaining}; "
            f"greedy covered {cheapest}-{priciest} cent range, projected remaining after "
            f"affordable set {projected_after}"
        )
    else:
        notes.append(
            f"none affordable: remaining budget {remaining} cannot absorb any paid book "
            f"in the batch (all {deferred_count} deferred); acquire only free sources, "
            f"raise the budget, or wait for the next period"
        )

    return BookAcquisitionBudgetReport(
        remaining_budget=remaining,
        batch_total=batch_total,
        would_exceed_budget=would_exceed,
        affordable_count=affordable_count,
        deferred_count=deferred_count,
        projected_remaining_after_affordable=projected_after,
        affordable_books=tuple(affordable),
        deferred_books=tuple(deferred),
        cheapest_affordable_price=cheapest,
        priciest_affordable_price=priciest,
        verdict=verdict,
        notes=tuple(notes),
        authority="advisory",
    )
