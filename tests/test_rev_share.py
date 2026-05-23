"""Rev-share tests (Sprint 23-24 + Sprint 25+ mixed attribution + §9.5 rollover)."""

from __future__ import annotations

import pytest

from substrate.rev_share import (
    MINIMUM_PAYOUT_USD_CENTS,
    NOTICE_MONTH,
    ROLLOVER_CEILING_MONTHS,
    MixedAttributionInput,
    RolloverLedger,
    accrue,
    apply_creator_ratio,
    is_forfeitable,
    settle_or_rollover,
    split_mixed_attribution,
    split_platform_vs_ip,
)
from substrate.rev_share.rollover import RolloverState


# ── 30/70 + creator ratio ─────────────────────────────────────────


def test_split_platform_vs_ip_30_70():
    platform, ip = split_platform_vs_ip(10_000)
    # IP-holder pool = 7000, platform = 3000.
    assert ip == 7000
    assert platform == 3000
    assert platform + ip == 10_000


def test_split_platform_vs_ip_handles_zero():
    assert split_platform_vs_ip(0) == (0, 0)


def test_apply_creator_ratio_70_of_ip_pool():
    creator, publisher = apply_creator_ratio(7000)
    assert creator == 4900  # 0.70 of 7000
    assert publisher == 2100
    assert creator + publisher == 7000


def test_no_double_spend_chain():
    """Verify the full chain: ad → platform + IP pool → creator + publisher."""
    total = 10_000
    platform, ip = split_platform_vs_ip(total)
    creator, publisher = apply_creator_ratio(ip)
    assert platform + creator + publisher == total


# ── Mixed attribution ─────────────────────────────────────────────


def test_mixed_attribution_split_proportional():
    inp = MixedAttributionInput(
        impression_id="imp-1",
        ip_holder_pool_cents=7000,
        attribution_shares={"doc-A": 0.6, "doc-B": 0.4},
        document_to_recipient={
            "doc-A": ("creator", "u-1"),
            "doc-B": ("publisher", "ip-1"),
        },
    )
    result = split_mixed_attribution(inp)
    lines = {(l.kind, l.recipient_ref): l.amount_cents for l in result.lines}
    assert lines[("creator", "u-1")] == 4200
    assert lines[("publisher", "ip-1")] == 2800
    # Sum cannot exceed input pool.
    assert sum(l.amount_cents for l in result.lines) + result.unallocated_cents == 7000


def test_mixed_attribution_aggregates_same_recipient():
    """Two docs from the same publisher aggregate into one line."""
    inp = MixedAttributionInput(
        impression_id="imp-1",
        ip_holder_pool_cents=7000,
        attribution_shares={"doc-A": 0.3, "doc-B": 0.3, "doc-C": 0.4},
        document_to_recipient={
            "doc-A": ("publisher", "ip-1"),
            "doc-B": ("publisher", "ip-1"),  # same publisher
            "doc-C": ("creator", "u-1"),
        },
    )
    result = split_mixed_attribution(inp)
    pub_lines = [l for l in result.lines if l.kind == "publisher"]
    assert len(pub_lines) == 1
    assert pub_lines[0].recipient_ref == "ip-1"
    assert set(pub_lines[0].contributing_doc_ids) == {"doc-A", "doc-B"}


def test_mixed_attribution_no_overflow_to_unknown():
    """A doc with no recipient entry is silently dropped — no double-spend."""
    inp = MixedAttributionInput(
        impression_id="imp-1",
        ip_holder_pool_cents=7000,
        attribution_shares={"doc-A": 0.5, "doc-unknown": 0.5},
        document_to_recipient={"doc-A": ("creator", "u-1")},
    )
    result = split_mixed_attribution(inp)
    total_lines = sum(l.amount_cents for l in result.lines)
    # doc-A took 3500; the unknown 3500 lands in unallocated.
    assert total_lines == 3500
    assert result.unallocated_cents == 3500


def test_mixed_attribution_zero_pool():
    inp = MixedAttributionInput(
        impression_id="imp-1",
        ip_holder_pool_cents=0,
        attribution_shares={"doc-A": 1.0},
        document_to_recipient={"doc-A": ("creator", "u-1")},
    )
    result = split_mixed_attribution(inp)
    assert result.lines == ()
    assert result.unallocated_cents == 0


# ── Rollover ledger ──────────────────────────────────────────────


def test_below_threshold_rolls_over():
    ledger = RolloverLedger()
    accrue(ledger, recipient_ref="u-1", cents=500, current_month_index=100)
    state, settled = settle_or_rollover(ledger, recipient_ref="u-1", current_month_index=100)
    assert settled == 0
    assert state == RolloverState.ACCRUING
    assert ledger.entry_for("u-1").balance_cents == 500


def test_above_threshold_settles():
    ledger = RolloverLedger()
    accrue(ledger, recipient_ref="u-1", cents=MINIMUM_PAYOUT_USD_CENTS + 100, current_month_index=100)
    state, settled = settle_or_rollover(ledger, recipient_ref="u-1", current_month_index=100)
    assert state == RolloverState.SETTLED
    assert settled == MINIMUM_PAYOUT_USD_CENTS + 100
    assert ledger.entry_for("u-1").balance_cents == 0


def test_notice_at_month_9():
    ledger = RolloverLedger()
    accrue(ledger, recipient_ref="u-1", cents=500, current_month_index=100)
    state, _ = settle_or_rollover(ledger, recipient_ref="u-1", current_month_index=100 + NOTICE_MONTH)
    assert state == RolloverState.NOTICE_SENT


def test_forfeit_at_month_12():
    ledger = RolloverLedger()
    accrue(ledger, recipient_ref="u-1", cents=500, current_month_index=100)
    state, settled = settle_or_rollover(
        ledger,
        recipient_ref="u-1",
        current_month_index=100 + ROLLOVER_CEILING_MONTHS,
    )
    assert state == RolloverState.FORFEITED
    assert settled == 500
    assert ledger.entry_for("u-1").balance_cents == 0


def test_is_forfeitable_predicate():
    ledger = RolloverLedger()
    accrue(ledger, recipient_ref="u-1", cents=500, current_month_index=100)
    entry = ledger.entry_for("u-1")
    assert not is_forfeitable(entry, current_month_index=100)
    assert not is_forfeitable(entry, current_month_index=100 + 5)
    assert is_forfeitable(entry, current_month_index=100 + ROLLOVER_CEILING_MONTHS)


def test_accrual_resumes_after_settle():
    """After settlement, a new accrual restarts the months-held clock."""
    ledger = RolloverLedger()
    accrue(ledger, recipient_ref="u-1", cents=MINIMUM_PAYOUT_USD_CENTS, current_month_index=100)
    settle_or_rollover(ledger, recipient_ref="u-1", current_month_index=100)
    accrue(ledger, recipient_ref="u-1", cents=300, current_month_index=105)
    entry = ledger.entry_for("u-1")
    assert entry.accrual_started_month == 105
    assert entry.balance_cents == 300
