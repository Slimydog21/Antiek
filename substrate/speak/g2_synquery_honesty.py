"""G2 counsel + Synquery honesty envelope (no invented partnership / payout).

Public source of truth for:

- **G2 counsel** — lawyer review gates public Speak publishing + disbursement
  (with G3 opt-in). Deny-by-default; operator flip only post-counsel.
- **Synquery** — expert-network partnership (§11.6) is **not live** until the
  operator enables ``ANTIEK_SYNQUERY_ENABLED`` after creation-surface PMF.
  Default = gated; no invented partnership or booking UI as "connected."
- **Money model** — ``accrue_escrow_now_disburse_after_legal_review`` (spr-10,
  afa-escrow, speak residual-100). Accrual ≠ paid today.

Cite: docs/decisions/speak-residual-100-2026-09-18.md;
docs/decisions/spr-10-ai-graded-payout.md;
docs/decisions/afa-escrow-double-credit.md;
docs/decisions/g2-synquery-honesty-2026-09-19.md;
master-product-spec §11.6.
"""

from __future__ import annotations

from typing import Any

from substrate.contracts.anti_ek_honesty import assert_g2_synquery_honesty_shape
from substrate.speak import gate_status as _gs

SPEAK_RESIDUAL_REF = "docs/decisions/speak-residual-100-2026-09-18.md"
SPR10_REF = "docs/decisions/spr-10-ai-graded-payout.md"
AFA_ESCROW_REF = "docs/decisions/afa-escrow-double-credit.md"
G2_SYNQUERY_REF = "docs/decisions/g2-synquery-honesty-2026-09-19.md"
SPEC_SYNQUERY_REF = "docs/master-product-spec.md §11.6"

MONEY_MODEL = "accrue_escrow_now_disburse_after_legal_review"

G2_REQUIRES: tuple[str, ...] = (
    "counsel_sign_off",
    "g3_contributor_opt_in",
    "operator_enable_public_publishing",
    "operator_stripe_real_only_after_counsel",
)

SYNQUERY_REQUIRES: tuple[str, ...] = (
    "creation_surface_pmf_signal",
    "operator_enable_synquery_flag",
    "no_invented_partnership",
    "transcript_ingest_as_interview_source",
)


def _synquery_live() -> bool:
    try:
        from tools.synquery.client import feature_flag_enabled

        return bool(feature_flag_enabled())
    except Exception:
        return False


def g2_synquery_honesty() -> dict[str, Any]:
    """Pure honesty envelope for Trust Center + Speak opportunities.

    Never invents partnership status or flips disbursement. Reads live
    gate_status + Synquery feature flag; defaults deny.
    """
    pub = _gs.public_publishing_allowed()
    disb = _gs.disbursement_allowed()
    syn_live = _synquery_live()
    payload = {
        "surface": "speak_economics",
        "g2_counsel_gated": not pub.allowed,
        "g3_opt_in_gated": not pub.allowed,  # same operator flip post G2+G3
        "public_publishing": "live" if pub.allowed else "gated_G2_G3",
        "disbursement": (
            "live" if disb.allowed else "gated_G2_G3_accrue_escrow_only"
        ),
        "disbursement_allowed": bool(disb.allowed),
        "public_publishing_allowed": bool(pub.allowed),
        "money_model": MONEY_MODEL,
        # False while disbursement is GATED — provable, no money can move.
        # None once the operator flips it: this envelope is deliberately
        # DB-free ("Pure honesty envelope" above) and cannot see the payouts
        # ledger, so it does not know whether anything was paid. It used to
        # emit a bare False, which is a claim it cannot support and fails in
        # the worst direction — telling a contributor they were not paid when
        # they may have been. Unknown is the honest value; the ledger is the
        # place that can answer it.
        "paid_today": False if not disb.allowed else None,
        "synquery_partnership": "live" if syn_live else "gated",
        "synquery_gated": not syn_live,
        "g2_requires": list(G2_REQUIRES),
        "synquery_requires": list(SYNQUERY_REQUIRES),
        "decision_refs": [
            SPEAK_RESIDUAL_REF,
            SPR10_REF,
            AFA_ESCROW_REF,
            G2_SYNQUERY_REF,
            SPEC_SYNQUERY_REF,
        ],
    }
    assert_g2_synquery_honesty_shape(payload)
    return payload


__all__ = [
    "AFA_ESCROW_REF",
    "G2_REQUIRES",
    "G2_SYNQUERY_REF",
    "MONEY_MODEL",
    "SPEAK_RESIDUAL_REF",
    "SPR10_REF",
    "SPEC_SYNQUERY_REF",
    "SYNQUERY_REQUIRES",
    "g2_synquery_honesty",
]
