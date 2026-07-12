"""Per-API-key usage ledger — the actuals substrate for the budget bar (ask #8).

The operator's Settings vision (ask #8/#9/#10): *"...a bar of how much usage has
been used on that API key given the limit I set in my budget in settings."* On
main, budget accounting is a single **global** daily cap
(`orchestration/continuous/budget.DaemonBudget`); there is no per-key tracking.
This module is the pure per-key actuals aggregator the Settings bar and the
model-selection decision tree consume.

**Complementary, not overlapping, with #1838.** `substrate/budget/projection.py`
(`project_budget`) answers *"what would this one prompt cost going forward?"* —
a **forward estimate** over a `CostBand`. This module answers *"how much has
each key actually spent so far?"* — the **accumulated actuals** that feed
`BudgetState.spent_usd`. The two compose: ``ledger_state`` → per-key
``KeyUsage`` → ``BudgetState`` → ``project_budget``.

**Pure — no I/O.** A pure aggregator over the events it is handed. The caller is
responsible for windowing (passing only the events that fall in the active
period); the ledger never invents a time window. This is the honesty keystone:
the ledger reports exactly what it was given, nothing more.

**Honesty rules (load-bearing), mirroring ``projection.py``:**
  * A key with **no cap set** → ``cap_usd``/``remaining_usd``/``usage_pct`` are
    ``None`` and ``status == "no_cap"``. Never fabricates a cap.
  * Spend is always **known** to a pure function (it sums the events it holds),
    so ``spent_usd`` is a real number — ``0.0`` when a key has no events is
    honest ("you have spent nothing"), NOT a fabricated unknown. The ``None``
    unknown-spend case is an I/O concern (no ledger wired), outside this module.
  * **Negative cost is impossible** in a forward-only ledger — rejected. (A
    refund/correction is a different event shape, out of scope for v1.) Defend
    the invariant rather than silently dropping or flipping a sign.
  * ``by_model`` attributes spend only to events that name a model; events with
    ``model is None`` are counted in ``spent_usd`` / ``event_count`` but excluded
    from ``by_model`` (``sum(by_model.values())`` may be ``< spent_usd``). No
    magic sentinel string; no fabricated attribution.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


class UsageLedgerError(ValueError):
    """A usage event or cap violates a load-bearing invariant."""


@dataclass(frozen=True)
class UsageEvent:
    """One recorded spend against a key. ``cost_usd`` must be >= 0.

    ``model`` / ``recorded_at`` / token counts are optional metadata; the ledger
    does not depend on them for totals. ``recorded_at`` is an opaque ISO string
    the caller chooses — the pure ledger does not parse or window on it.
    """

    key_id: str
    cost_usd: float
    model: str | None = None
    recorded_at: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


@dataclass(frozen=True)
class KeyCap:
    """The operator-set spend limit for one key. ``cap_usd is None`` = unset.

    ``period`` is a display-only label ("daily"/"weekly"/"monthly"/"all_time");
    the pure ledger does not filter by it (the caller windows the events).
    """

    key_id: str
    cap_usd: float | None = None
    period: str = "all_time"


@dataclass(frozen=True)
class KeyUsage:
    """Aggregated actuals for one key. Every ``None`` is an honest unknown."""

    key_id: str
    spent_usd: float
    cap_usd: float | None
    cap_known: bool
    remaining_usd: float | None
    usage_pct: float | None
    status: str  # "no_cap" | "under" | "at_cap" | "over"
    event_count: int
    by_model: dict[str, float] = field(default_factory=dict)


def _validate_cost(cost: float) -> float:
    if cost < 0:
        raise UsageLedgerError(
            f"usage event cost_usd must be >= 0 (got {cost}); a forward-only "
            "ledger cannot represent negative spend"
        )
    return cost


def _validate_cap(cap_usd: float | None) -> float | None:
    if cap_usd is None:
        return None
    if cap_usd < 0:
        raise UsageLedgerError(
            f"key cap_usd must be >= 0 (got {cap_usd}); a budget cannot be negative"
        )
    return cap_usd


def _status_for(spent: float, cap: float | None) -> tuple[str, float | None, float | None]:
    """Return (status, remaining_usd, usage_pct) for a known spend vs a cap.

    ``remaining_usd`` is honest even when negative (overdrawn) — the operator
    sees exactly how far past the cap the key has gone, not a clamped zero.
    """
    if cap is None:
        return "no_cap", None, None
    remaining = cap - spent
    pct = (spent / cap * 100.0) if cap > 0 else (100.0 if spent > 0 else 0.0)
    if spent > cap:
        return "over", remaining, pct
    if spent == cap:
        return "at_cap", remaining, pct
    return "under", remaining, pct


def ledger_state(
    events: Iterable[UsageEvent],
    caps: Mapping[str, KeyCap] | Iterable[KeyCap],
) -> list[KeyUsage]:
    """Aggregate events into per-key actuals, joined against the cap table.

    Returns one ``KeyUsage`` per key mentioned in *either* events or caps, sorted
    by ``key_id`` (deterministic — no dict-order or input-order dependence). A
    key with a cap but no events appears (spent ``0.0``); a key with events but
    no cap appears (``status == "no_cap"``).

    Pure: validates every cost/cap, sums, and computes status. Raises
    ``UsageLedgerError`` on a negative cost or cap — never silently coerces.
    """
    cap_table: dict[str, KeyCap] = {}
    cap_iter = caps.values() if isinstance(caps, Mapping) else caps
    for cap in cap_iter:
        _validate_cap(cap.cap_usd)
        cap_table[cap.key_id] = cap

    spent_by_key: dict[str, float] = defaultdict(float)
    count_by_key: dict[str, int] = defaultdict(int)
    model_by_key: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for event in events:
        _validate_cost(event.cost_usd)
        spent_by_key[event.key_id] += event.cost_usd
        count_by_key[event.key_id] += 1
        if event.model is not None:
            model_by_key[event.key_id][event.model] += event.cost_usd

    all_keys = sorted(set(spent_by_key) | set(cap_table))
    results: list[KeyUsage] = []
    for key_id in all_keys:
        spent = spent_by_key.get(key_id, 0.0)
        cap = cap_table.get(key_id)
        cap_usd = cap.cap_usd if cap is not None else None
        status, remaining, pct = _status_for(spent, cap_usd)
        results.append(
            KeyUsage(
                key_id=key_id,
                spent_usd=spent,
                cap_usd=cap_usd,
                cap_known=cap_usd is not None,
                remaining_usd=remaining,
                usage_pct=pct,
                status=status,
                event_count=count_by_key.get(key_id, 0),
                by_model=dict(model_by_key.get(key_id, {})),
            )
        )
    return results


def project_key_after_event(current: KeyUsage, event: UsageEvent) -> KeyUsage:
    """Return the key's projected state after one additional event lands.

    Pure forward check on actuals (the actuals analogue of #1838's
    ``project_budget``). Useful for *"if I run this prompt now, where does the
    bar land?"* before the event is recorded. The event's ``key_id`` must match
    ``current.key_id`` — projecting an event onto the wrong key is a caller bug,
    not a silent merge.
    """
    if event.key_id != current.key_id:
        raise UsageLedgerError(
            f"event key_id {event.key_id!r} does not match key usage "
            f"{current.key_id!r}; project_key_after_event is per-key"
        )
    _validate_cost(event.cost_usd)
    spent = current.spent_usd + event.cost_usd
    status, remaining, pct = _status_for(spent, current.cap_usd)
    by_model = dict(current.by_model)
    if event.model is not None:
        by_model[event.model] = by_model.get(event.model, 0.0) + event.cost_usd
    return KeyUsage(
        key_id=current.key_id,
        spent_usd=spent,
        cap_usd=current.cap_usd,
        cap_known=current.cap_known,
        remaining_usd=remaining,
        usage_pct=pct,
        status=status,
        event_count=current.event_count + 1,
        by_model=by_model,
    )


def to_budget_state(usage: KeyUsage) -> tuple[float | None, float | None, bool, bool]:
    """Adapt a ``KeyUsage`` to #1838's ``BudgetState`` constructor fields.

    Returns ``(daily_cap_usd, spent_usd, cap_known, spent_known)`` so a caller
    can build ``BudgetState(...)``, then ``project_budget(state, cost_band)`` for
    the forward prompt-cost projection on top of this key's actuals. ``spent`` is
    always known to the ledger, so ``spent_known`` is always ``True`` here.
    """
    return usage.cap_usd, usage.spent_usd, usage.cap_known, True


__all__ = [
    "UsageLedgerError",
    "UsageEvent",
    "KeyCap",
    "KeyUsage",
    "ledger_state",
    "project_key_after_event",
    "to_budget_state",
]
