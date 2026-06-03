"""Consent / servability / IP-holder view — the other half of SPR-07 (M2/M3).

The operator's permissions question: "what am I accruing, who consented, what's
servable, and what is gated." This module answers it as a **read-only view** over
the canonical sources, forking none:

* **Escrow + opt-in state machine** — ``substrate.ip_holders`` (the five-state
  lifecycle ``pre_onboarded → invited → claimed → opted_out``; ``accrue_escrow``
  is the single escrow-BALANCE writer, ``SET escrow_balance_usd = … + ?``). This
  view calls ``ip_holders.list_all`` / ``ip_holders.get`` to READ rows; it never
  calls ``accrue_escrow`` (that is the attribution pipeline's job) and never a
  payout path (diligence #5 — proven absent by the no-disbursement test).

* **Escrow report** — ``substrate.marketplace_metrics.publisher_escrow.compute_publisher_escrow``,
  the read-only aggregation (claim rate, unclaimed escrow). This is the REPORT we
  surface; it is not the writer (the SPR-01 first-draft naming of it as "the
  single escrow writer" was corrected in SPR-03 — the writer is
  ``ip_holders.accrue_escrow``; see ``docs/decisions/tech-stack-ledger.md`` and
  the ``AccrualContract`` docstring).

* **Gate state** — ``substrate.coordination.gate_ledger.load_gate_ledger`` for
  G2 (lawyer review) + G3 (publisher opt-in). The view reads the gate state from
  the SPR-05 ledger; it does NOT re-derive or hardcode it. If the operator edits
  the gate file, the next render flips the labels.

* **Servability** — the SPR-03 seam ``substrate.seams.servability_gate``
  (``serves_full_text`` / ``gate_speak_derived_entry``) over the
  ``ServableEntryContract``. Deny-by-default; a ``speak_derived`` entry serves
  full text only when its Speak publish gate passed. (Read's ``substrate.books``
  serving layer is unmerged on this base — by composing against the *contracts +
  seam* we read the real servability rule without coupling to Read internals.)

The load-bearing invariant this view exists to make legible:
**accrual ≠ disbursement.** Escrow balances accrue from day one — even with zero
buyers, in which case a balance is honestly ``$0`` (not a fabricated number).
Disbursement is hard-gated on G2 **and** G3, both currently open. This view
therefore stamps every escrow balance with a :class:`DisbursementGate` carrying
``disbursable=False`` and the open gates blocking it. **There is no disbursement
path in this module** — no import of ``tools.stripe_connect.payouts`` and no call
that moves money. A future auditor confirms "did anyone get paid before the legal
gate?" by the proven absence of such a path (the no-disbursement test).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from substrate.contracts.servable import ServableEntryContract
from substrate.coordination.gate_ledger import (
    GateLedger,
    GateStatus,
    load_gate_ledger,
)
from substrate.ip_holders import IpHolder
from substrate.ip_holders import list_all as _list_ip_holders
from substrate.marketplace_metrics.publisher_escrow import (
    PublisherEscrowReport,
    compute_publisher_escrow,
)
from substrate.seams.servability_gate import serves_full_text

# Gates that block ESCROW DISBURSEMENT. Both must be CLOSED before any payout.
# Read from the SPR-05 ledger — these ids are the lookup keys, not the state.
_DISBURSEMENT_GATE_IDS: tuple[str, ...] = ("G2", "G3")

# The opt-in state that unlocks the payout path in the ip_holders state machine
# (``ip_holders.claim`` transitions invited → claimed). Surfaced so the view can
# show *both* gates: the platform-wide legal gate (G2/G3) AND the per-holder
# claim state. Disbursement needs the legal gate closed AND the holder claimed.
_PAYOUT_ENABLING_STATUS: str = "claimed"


@dataclass(frozen=True)
class DisbursementGate:
    """Why an accrued escrow balance is NOT disbursable. ``disbursable`` is
    fixed ``False`` here — the view has no path to make it True (that is a gate
    decision + a per-holder claim, neither of which this read-only surface can
    perform). ``open_gate_ids`` is read live from the SPR-05 ledger.

    The label is the operator-facing string the UI renders verbatim:
    "accruing — disbursement gated on G2+G3"."""

    disbursable: bool                 # always False in this view
    open_gate_ids: tuple[str, ...]    # subset of {G2, G3} currently open
    holder_claimed: bool              # per-holder: has this holder claimed?
    label: str

    @property
    def fully_unlocked(self) -> bool:
        """Disbursement would require: both legal gates closed AND the holder
        claimed. This view can *report* that condition; it cannot act on it."""
        return (not self.open_gate_ids) and self.holder_claimed


@dataclass(frozen=True)
class IpHolderConsentRow:
    """One IP holder's consent + escrow + (where applicable) servability,
    derived on read. ``escrow_balance_usd`` is the live balance from the
    ip_holders row — ``$0`` is an honest zero (zero buyers ⇒ zero accrual ⇒
    a real ``0`` balance, never fabricated)."""

    ip_holder_id: str
    display_name: str
    status: str                       # the opt-in state-machine state
    escrow_balance_usd: Decimal       # live, accruing; $0 is honest
    gate: DisbursementGate
    # servability of this holder's content, when a servable entry is supplied.
    serves_full_text: bool | None = None
    servability_note: str | None = None


@dataclass(frozen=True)
class ConsentView:
    """The full consent/escrow/servability surface. A VIEW — derived on read,
    stores nothing, writes nothing, disburses nothing.

    ``escrow_report`` is the read-only aggregation
    (``compute_publisher_escrow``). ``disbursement_gates_open`` is the live
    G2/G3 state from the SPR-05 ledger; while it is non-empty NOTHING is
    disbursable regardless of any holder's claim state."""

    holders: tuple[IpHolderConsentRow, ...]
    escrow_report: PublisherEscrowReport
    disbursement_gates_open: tuple[str, ...]
    gate_source_path: str

    @property
    def total_escrow_accruing_usd(self) -> Decimal:
        """Sum of all holders' accruing escrow. Zero-buyer ⇒ ``Decimal('0')``."""
        return sum((h.escrow_balance_usd for h in self.holders), Decimal("0"))

    @property
    def any_disbursable(self) -> bool:
        """True only if some holder is fully unlocked. By design this is False
        while either legal gate is open — the assertion the auditor checks."""
        return any(h.gate.fully_unlocked for h in self.holders)


# ── Gate reading (from the SPR-05 ledger — never hardcoded) ──────────────────

def _open_disbursement_gates(ledger: GateLedger) -> tuple[str, ...]:
    """Which of {G2, G3} are OPEN, read from the SPR-05 ledger. A gate is
    blocking iff its coarse status is not CLOSED (the ``is_open_family``
    property). Read live — if the operator closes G2 in the source file, this
    shrinks on the next call."""
    open_ids: list[str] = []
    for gid in _DISBURSEMENT_GATE_IDS:
        try:
            gate = ledger.by_id(gid)
        except KeyError:
            # A gate the canonical file no longer names: treat as open (fail
            # safe — never assume a disbursement gate is closed by its absence).
            open_ids.append(gid)
            continue
        if gate.status is not GateStatus.CLOSED:
            open_ids.append(gid)
    return tuple(open_ids)


def _disbursement_gate_for(
    *,
    open_gate_ids: tuple[str, ...],
    holder_status: str,
) -> DisbursementGate:
    """Build the per-holder disbursement gate. ``disbursable`` is always False
    in this surface; the label states the gated reality the spec mandates."""
    holder_claimed = holder_status == _PAYOUT_ENABLING_STATUS
    if open_gate_ids:
        gates = "+".join(open_gate_ids)
        label = f"accruing — disbursement gated on {gates}"
    elif not holder_claimed:
        # Legal gate closed but this holder has not claimed — still no payout.
        label = "accruing — legal gate clear; awaiting publisher claim"
    else:
        # Both legal gates closed AND holder claimed. Disbursement would be
        # *eligible* — but it is still not performed here (this surface has no
        # payout path). The label says so plainly.
        label = "accruing — eligible for disbursement (operator-only; not performed here)"
    return DisbursementGate(
        disbursable=False,
        open_gate_ids=open_gate_ids,
        holder_claimed=holder_claimed,
        label=label,
    )


# ── Servability (SPR-03 seam — deny-by-default) ──────────────────────────────

def _servability_for_entry(
    entry: ServableEntryContract,
    *,
    publish_gate_passed: bool,
) -> tuple[bool, str]:
    """Resolve one servable entry through the SPR-03 seam. Returns
    ``(serves_full_text, note)``. Deny-by-default; a ``speak_derived`` entry
    serves full text only when its Speak publish gate passed."""
    serves = serves_full_text(entry, publish_gate_passed=publish_gate_passed)
    if entry.taken_down:
        note = "taken down — not servable"
    elif entry.content_class == "platform_authored" and entry.provenance_class == "speak_derived":
        note = (
            "speak-derived — serves full text only after Speak's publish gate"
            f" ({'passed' if publish_gate_passed else 'not passed'})"
        )
    elif serves:
        note = f"{entry.content_class} — serves full text"
    else:
        note = f"{entry.content_class} — full text gated (deny-by-default)"
    return serves, note


# ── The builder ───────────────────────────────────────────────────────────────

def build_consent_view(
    con: Any,
    *,
    gate_ledger: GateLedger | None = None,
    servable_entries: dict[str, ServableEntryContract] | None = None,
    speak_publish_gate_passed: dict[str, bool] | None = None,
) -> ConsentView:
    """Derive the consent/escrow/servability view on read.

    ``con`` is a DuckDB connection (read-only use here — only SELECTs via
    ``ip_holders.list_all``). ``gate_ledger`` defaults to the live SPR-05 ledger
    (``load_gate_ledger``); pass a parsed fixture to test the G2/G3 toggle.
    ``servable_entries`` maps ``ip_holder_id → ServableEntryContract`` for the
    holders whose content servability we surface (Read's serving layer is
    unmerged; where no entry is supplied servability is ``None`` — an honest
    "not surfaced here", not a fabricated value)."""
    ledger = gate_ledger if gate_ledger is not None else load_gate_ledger()
    open_gates = _open_disbursement_gates(ledger)
    entries = servable_entries or {}
    passed = speak_publish_gate_passed or {}

    holders_raw: list[IpHolder] = _list_ip_holders(con)

    rows: list[IpHolderConsentRow] = []
    status_rows: list[tuple[str, str]] = []
    accrual_cents: dict[str, int] = {}
    for h in holders_raw:
        gate = _disbursement_gate_for(open_gate_ids=open_gates, holder_status=h.status)

        serves: bool | None = None
        note: str | None = None
        entry = entries.get(h.ip_holder_id)
        if entry is not None:
            serves, note = _servability_for_entry(
                entry, publish_gate_passed=passed.get(h.ip_holder_id, False)
            )

        rows.append(
            IpHolderConsentRow(
                ip_holder_id=h.ip_holder_id,
                display_name=h.display_name,
                status=h.status,
                escrow_balance_usd=h.escrow_balance_usd,
                gate=gate,
                serves_full_text=serves,
                servability_note=note,
            )
        )
        status_rows.append((h.ip_holder_id, h.status))
        # Quantize the live Decimal USD balance to integer cents for the report
        # (the report works in cents; the balance writer stores Decimal USD).
        accrual_cents[h.ip_holder_id] = int(
            (h.escrow_balance_usd * Decimal("100")).to_integral_value()
        )

    report = compute_publisher_escrow(
        publisher_status_rows=status_rows,
        publisher_accrual_cents=accrual_cents,
        # No money has been paid — disbursement is gated. Honest zeroes, not a
        # fabricated paid-out figure. (There is no paid-cents source to read
        # because no payout has run; surfacing 0 is the truthful value.)
        publisher_paid_cents={ip_id: 0 for ip_id in accrual_cents},
    )

    return ConsentView(
        holders=tuple(rows),
        escrow_report=report,
        disbursement_gates_open=open_gates,
        gate_source_path=ledger.source_path,
    )


__all__ = [
    "DisbursementGate",
    "IpHolderConsentRow",
    "ConsentView",
    "build_consent_view",
]
