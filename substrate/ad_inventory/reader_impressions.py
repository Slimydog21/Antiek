"""Reader impression + attention recording (SPR-05 M4).

The honesty layer of the economics engine. SPR-09's accrual is only as
truthful as these records, so the definitions are precise and the
inflation paths are closed:

- **Impression** = a slot fill was rendered into the viewport for a given
  reading position. Counted at most ONCE per (session, slot) — the
  deterministic ``slot_id`` (SPR-05 M1) makes a re-render a no-op, not a
  second impression.
- **Attention** = the slot stayed continuously visible for at least
  ``READER_ATTENTION_DWELL_MS`` WHILE the tab was focused. Dwell
  accumulated while the tab is idle/backgrounded does NOT count — this is
  the rule the spec's "attention not while idle" gate tests.

A house fill (zero-buyer) still produces an impression record with
``revenue_usd_cents = 0``: the attention-share ledger exists from v1, but
it resolves to $0 revenue (no invented money — rigor #1).
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.constants import READER_ATTENTION_DWELL_MS

from .reader_slots import SlotFill


@dataclass(frozen=True)
class ReaderImpression:
    """One recorded impression of a slot fill in a reading session.

    ``impression_id`` is deterministic from (session_id, slot_id) so the
    accrual reconciliation in SPR-09 can dedup re-renders by id.
    ``counted_attention`` is the audited answer to "did this earn
    attention-share" — True only when the focused-dwell rule was met."""

    impression_id: str
    session_id: str
    document_id: str
    slot_id: str
    page_index: int
    fill_kind: str  # 'ad' | 'house'
    revenue_usd_cents: int
    focused_dwell_ms: int
    counted_attention: bool


def _impression_id(session_id: str, slot_id: str) -> str:
    # Deterministic → re-render of the same slot in the same session is the
    # same impression, never a second one (the double-count guard).
    return f"imp:{session_id}:{slot_id}"


def record_impression(
    *,
    session_id: str,
    fill: SlotFill,
    focused_dwell_ms: int = 0,
    tab_focused: bool = True,
) -> ReaderImpression:
    """Record one impression of ``fill`` in ``session_id``.

    ``focused_dwell_ms`` is the dwell the FRONTEND already attributed to
    focused, foregrounded time (the client is responsible for not
    accumulating dwell while ``visibilitychange`` says hidden). This
    function applies the substrate-side rule on top: attention counts only
    when ``tab_focused`` is True AND focused dwell ≥ the threshold. Passing
    ``tab_focused=False`` (tab backgrounded at record time) forces
    attention to 0 regardless of dwell — the idle-exclusion belt to the
    client's suspenders.
    """
    if focused_dwell_ms < 0:
        raise ValueError(f"focused_dwell_ms must be >= 0, got {focused_dwell_ms}")
    counted = tab_focused and focused_dwell_ms >= READER_ATTENTION_DWELL_MS
    eff_dwell = focused_dwell_ms if tab_focused else 0
    return ReaderImpression(
        impression_id=_impression_id(session_id, fill.slot.slot_id),
        session_id=session_id,
        document_id=fill.slot.document_id,
        slot_id=fill.slot.slot_id,
        page_index=fill.slot.page_index,
        fill_kind=fill.kind,
        revenue_usd_cents=int(fill.revenue_usd_cents),
        focused_dwell_ms=eff_dwell,
        counted_attention=counted,
    )


def record_raw_impression(
    *,
    session_id: str,
    document_id: str,
    slot_id: str,
    page_index: int,
    fill_kind: str,
    revenue_usd_cents: int,
    focused_dwell_ms: int = 0,
    tab_focused: bool = True,
) -> ReaderImpression:
    """Build a ReaderImpression from the raw fields a browser posts.

    Identical attention rule to :func:`record_impression`, but takes the
    flat fields the HTTP layer receives instead of a ``SlotFill``. The
    client's own opinion of "did this earn attention" is NEVER trusted —
    ``counted_attention`` is recomputed here from the focused-dwell rule,
    and a backgrounded tab forces it to 0. This is the server-side belt to
    the client's suspenders against inflated attention.
    """
    if focused_dwell_ms < 0:
        raise ValueError(f"focused_dwell_ms must be >= 0, got {focused_dwell_ms}")
    counted = tab_focused and focused_dwell_ms >= READER_ATTENTION_DWELL_MS
    eff_dwell = focused_dwell_ms if tab_focused else 0
    return ReaderImpression(
        impression_id=_impression_id(session_id, slot_id),
        session_id=session_id,
        document_id=document_id,
        slot_id=slot_id,
        page_index=int(page_index),
        fill_kind=fill_kind,
        revenue_usd_cents=int(revenue_usd_cents),
        focused_dwell_ms=eff_dwell,
        counted_attention=counted,
    )


def dedup_impressions(impressions: list[ReaderImpression]) -> list[ReaderImpression]:
    """Collapse impressions to one per ``impression_id`` (one per
    session+slot), keeping the record with the most focused dwell. This is
    the reconciliation primitive SPR-09 uses so re-emitted impressions
    can't inflate accrual."""
    best: dict[str, ReaderImpression] = {}
    for imp in impressions:
        prev = best.get(imp.impression_id)
        if prev is None or imp.focused_dwell_ms > prev.focused_dwell_ms:
            best[imp.impression_id] = imp
    return list(best.values())


def total_revenue_cents(impressions: list[ReaderImpression]) -> int:
    """Sum of revenue across deduped impressions. Zero-buyer sessions
    return 0 — the honest answer, not a fabricated balance."""
    return sum(i.revenue_usd_cents for i in dedup_impressions(impressions))
