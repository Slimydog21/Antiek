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


# ---------------------------------------------------------------------------
# Read-only gate report. Lets the operator SEE what's blocking Speak's
# activation and HOW to close each gate — WITHOUT this module ever closing
# one. Closing a gate is an out-of-band operator action (a counsel
# decision, a KYC step, a deliberate env flip), never a code path. There
# is intentionally no "close_gate()" here: the whole safety architecture
# (consent-before-publish, accrue-not-disburse, single-operator) rests on
# these staying operator-owned.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateInfo:
    id: str             # e.g. "G2+G3", "G7", "G8"
    capability: str     # what closing the gate unlocks
    satisfied: bool     # is that capability unlocked right now?
    env_flag: str       # the operator-owned signal that reflects closure
    while_blocked: str  # what Speak refuses while the gate is open
    operator_closure: str  # the out-of-band action that closes it (NOT code)


def _loop3_unlocked() -> bool:
    return os.environ.get("ANTIEK_LOOP3_UNLOCKED", "").strip() == "1"


def gate_report() -> list[GateInfo]:
    """Per-gate status for the operator's activation view. Read-only:
    reflects the operator-owned signals; never mutates them."""
    pub = public_publishing_allowed()
    dis = disbursement_allowed()
    return [
        GateInfo(
            id="G2+G3",
            capability="Public publishing — a biography served in Read's corpus with the ad-border",
            satisfied=pub.allowed,
            env_flag="ANTIEK_SPEAK_PUBLIC_PUBLISHING",
            while_blocked="public publish is refused; private-never-published works",
            operator_closure=(
                "G2: counsel reviews interview consent + biography publishing "
                "(defamation / right-of-publicity / consent). G3: publisher + "
                "subject opt-in. Then the operator sets the flag. Not legal "
                "advice; G2 is the binding gate."
            ),
        ),
        GateInfo(
            id="G2+G3",
            capability="Contributor disbursement — money leaving escrow to contributors",
            satisfied=dis.allowed,
            env_flag="ANTIEK_STRIPE_PROVIDER=real",
            while_blocked="shares accrue to escrow; no payout path exists (accrue-not-disburse)",
            operator_closure=(
                "counsel sign-off + Stripe Connect KYC/onboarding; operator "
                "flips ANTIEK_STRIPE_PROVIDER=real. With zero ad buyers there "
                "is $0 to disburse regardless."
            ),
        ),
        GateInfo(
            id="G7",
            capability="Public interview ecosystem — open contribution by non-invited contributors",
            satisfied=_truthy("ANTIEK_SPEAK_PUBLIC_ECOSYSTEM"),
            env_flag="ANTIEK_SPEAK_PUBLIC_ECOSYSTEM",
            while_blocked="invitees are sources, not accounts; open public contribution is refused",
            operator_closure=(
                "the Sprint-22 multi-user pivot (~Nov 2026). Premature "
                "multi-user destroys the single-operator moat + risks graph "
                "contamination; operator decision, not code."
            ),
        ),
        GateInfo(
            id="G8",
            capability="RL-tuned interviewer — an interviewer that LEARNS to ask better questions",
            satisfied=_loop3_unlocked(),
            env_flag="ANTIEK_LOOP3_UNLOCKED",
            while_blocked="the interviewer is context-conditioned only; trajectory harvest is refused",
            operator_closure=(
                "Loop-3 unlock criteria pass (trajectory volume + validated "
                "reward) AND the operator sets ANTIEK_LOOP3_UNLOCKED=1 to "
                "authorize training. Capture works now; training does not."
            ),
        ),
    ]

