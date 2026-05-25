"""Speak — the G2/G3 legal-gate status seam (deny-by-default).

Two operator-owned gates block Speak's money + public-publishing paths
(master-spec §9.0; docs/operator_gate_actions.md):

  • G2 — lawyer review (covers interview consent + biography publishing)
  • G3 — publisher / contributor opt-in

Neither is a code change to close — they are operator actions. So this
module does NOT decide whether the gates are *closed*; it reads the
operator-controlled signal and **denies by default**, exactly like the
legal-gate placeholder (``ANTIEK_LEGAL_GATE_PLACEHOLDER_ACKED``) and the
Stripe provider (``ANTIEK_STRIPE_PROVIDER`` defaults to ``mock`` until
G2+G3 close). The point is that no Speak code path can accidentally
publish publicly or disburse money before the operator has consciously
flipped the signal post-counsel.

This is not legal advice; G2 counsel review is the binding gate. This
seam makes the system *defensible* and keeps the private, never-
published path open now.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GateStatus:
    allowed: bool
    reason: str


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def public_publishing_allowed() -> GateStatus:
    """Whether a Speak project may be published PUBLICLY.

    Gated on G2 (lawyer review of interview consent + biography
    publishing) and G3 (opt-in). Denies unless the operator has set
    ``ANTIEK_SPEAK_PUBLIC_PUBLISHING=1`` — which they only do after
    counsel sign-off. The default (unset) is refusal."""
    if _truthy("ANTIEK_SPEAK_PUBLIC_PUBLISHING"):
        return GateStatus(True, "operator enabled public publishing post-G2/G3")
    return GateStatus(
        False,
        "public publishing of a Speak biography is gated on the legal gate "
        "(G2 lawyer review + G3 opt-in); private-never-published is the safe "
        "default. Operator enables via ANTIEK_SPEAK_PUBLIC_PUBLISHING after "
        "counsel sign-off. This is not legal advice; G2 is the binding gate.",
    )


def disbursement_allowed() -> GateStatus:
    """Whether contributor escrow may actually DISBURSE money.

    Reuses the system-wide signal: the Stripe provider is ``mock`` until
    G2+G3 close (``ANTIEK_STRIPE_PROVIDER=real``). Accrual is always
    allowed; only the payout is gated. With zero ad buyers there is $0
    regardless — this gate is the structural guarantee that no pre-gate
    payout path exists."""
    provider = os.environ.get("ANTIEK_STRIPE_PROVIDER", "mock").strip().lower()
    if provider == "real":
        return GateStatus(True, "Stripe provider is 'real' (operator flipped post-G2/G3)")
    return GateStatus(
        False,
        "disbursement is gated on G2/G3 (ANTIEK_STRIPE_PROVIDER=mock by "
        "default); contribution shares accrue to escrow but no money routes "
        "until the legal gate clears.",
    )
