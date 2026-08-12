# attribution-math-v2 — the published split order

**Version id:** `attribution-math-v2`  
**Module:** `substrate/ad_inventory/attribution_math.py`  
**Wired into:** `substrate/ad_inventory/frame_attention_accrual.py`  
**Mandate:** AFA-S5 / PR #118 §7.1-S5  
**Scope:** escrow accrual only — never disbursement, never Stripe, never real ad serving.

---

## Why this exists

Before S5, the frame-attention pipeline conserved **100%** of eligible-second
value to contributors and only pocketed true house-seconds (no eligible asset
in frame). The structural 70/30 creator/platform cut lived solely on the
impression path in `payout.py` and was deliberately deferred for frames
(`frame_attention_accrual.py` historical L12).

After S5 a single versioned pipeline composes six stages under one id. The
cut is taken at the **pool boundary**, not at disbursement, so statements
(AFA-S6) can show each payee's true effective rate at close without interim
overstatement — the "trust the dashboard" failure mode this program kills.

## The six stages

Order is load-bearing (defended by counterfactual tests, not narrative).

| # | Stage | What it does | Version pin |
|---|---|---|---|
| 1 | **Carve-outs** | Licensed pre-pool fractions (document → fraction + payee). Registry ships **empty**; the mechanism is the deliverable. Deducted before pooling. | `carve-out-registry-v1` |
| 2 | **Platform cut** | 70/30 at the pool boundary. Creator pool = `int(post_carve × CREATOR_REV_SHARE)`; platform gets the remainder. Constants from `payout.py` (`CREATOR_REV_SHARE=0.70`, `PLATFORM_CUT=0.30`). | `platform-cut-70-30-v1` |
| 3 | **Filtered weights** | Re-normalize post-S2 (classify+caps) survivor weights. Invalid attention is out of both numerator and denominator. | `frame-weight-v2` |
| 4 | **Composition** | Apportion creator pool across assets; expand synthesis share vectors when present. Identity (asset = payee unit) when S3 is dormant. | `composition-identity-v1` |
| 5 | **Rights / T1 / author gates** | `monetization_eligible(content_class)` + `ads_allowed(resolve_tier(license_uri))` for arXiv papers + author split via `equal_split` / `author-split-equal-v1`. Failures route to residuals with reason codes. | `holder-gates-t1+author-split-equal-v1` |
| 6 | **UNATTRIBUTED bucket** | Everything unresolvable → `UNATTRIBUTED_RIGHTS_BUCKET` (`__unattributed__`) with stable reason codes. Never a black box. | `unattributed-bucket-v1` |

### Conservation identity (integer equality, no tolerances)

```
Σ creator payees
+ platform cut
+ carve-outs
+ unattributed
+ house_seconds
== window_value_cents
```

Every stage also conserves locally: `input_cents == output_cents + routed_cents`.

### House-seconds vs the platform cut

House-seconds (no eligible asset in frame) already belong to the platform.
The 70/30 cut applies only to the **eligible pool** (`window − house_seconds`).
Cutting house-seconds again would misstate the effective rate on statements.

### Pool scope (OQ-2)

`pool_scope: "global" | "per-reader"`, default **`"global"`** (index.html
decision log — coincident with per-reader until multi-user). Per-reader bounds
an attacker's damage to their own contribution (sybil rationale). Sprint-22
multi-user is the operator ratification moment. The parameter participates in
the params fingerprint.

## Constants (composed, not renegotiated)

| Constant | Value | Source |
|---|---|---|
| `CREATOR_REV_SHARE` | `0.70` | `substrate/ad_inventory/payout.py` |
| `PLATFORM_CUT` | `0.30` | `substrate/ad_inventory/payout.py` |
| `SPLIT_POLICY_VERSION` | `author-split-equal-v1` | `substrate/payouts/split.py` |
| `UNATTRIBUTED_RIGHTS_BUCKET` | `__unattributed__` | `substrate/constants.py` |
| `FRAME_WEIGHTING_VERSION` | `frame-weight-v2` | `substrate/ad_inventory/frame_attention.py` |
| `FRAME_TELEMETRY_SCHEMA_VERSION` | `frame-telemetry-v2` | `substrate/ad_inventory/frame_attention.py` |

Renegotiating any of these is operator territory. This module **composes**
them under one version id; it does not change them.

## Version policy (shrink-only / append-only — AFA-S6 spirit)

1. **Row stamp:** every new `frame_attention_accruals` / `house_seconds` row
   carries `attribution_math_version = "attribution-math-v2"`.
2. **Era separation:** pre-S5 rows have `NULL`/empty version and replay under
   the old 100%-to-contributors meaning. Never rewrite history.
3. **Bump rule:** changing ANY stage parameter, constant, order, or reason-code
   semantics requires a new composed id (`attribution-math-v3`, …). The
   version-completeness test asserts that a params fingerprint changes when
   any knob is mutated.
4. **Shrink-only baselines:** lint baselines and golden fixtures are edited
   shrink-only, never re-minted without rationale.
5. **Append-only ledger:** accrual rows are never updated in place; a changed
   batch is a new `batch_ref`.

## Residual reason codes

| Code | Meaning |
|---|---|
| `carve_out` | Licensed pre-pool deduction |
| `platform_cut` | Platform's 30% at pool boundary |
| `ineligible_content_class` | Failed `monetization_eligible` |
| `rights_tier_not_t1` | `ads_allowed(tier)` false (T2/T3) |
| `no_resolvable_holder` | No `ip_holder_id` and no authors |
| `no_attributable_authors` | `n_authors` produced empty split |
| `empty_creator_pool` | Creator pool with zero survivor weights |
| `house_seconds` | No eligible asset in frame |
| `unattributed` | Generic residual |

## What this is not

- Not a disbursement path. Accrual ≠ pay-out stays.
- Not a second money surface. Single escrow writer (`ip_holders.accrue_escrow`).
- Not a real carve-out deal registry population (operator/licensing act).
- Not statements / Merkle roots / monthly close (AFA-S6).
- Not a change to the author-split policy, the 70/30 ratio, the $50 cap, or
  the KYC floor.

## How to call it

```python
from substrate.ad_inventory.attribution_math import (
    ATTRIBUTION_MATH_VERSION,
    AssetCandidate,
    run_pipeline,
)

result = run_pipeline(
    window_value_cents=1000,  # server-minted (AFA-S1)
    candidates=[
        AssetCandidate(
            asset_id="doc-a",
            weight=1.0,
            content_class="public_domain",
            ip_holder_id="holder-1",
        ),
    ],
    house_seconds_cents=0,
)
assert result.conserves()
assert result.attribution_math_version == "attribution-math-v2"
```

The live accrual path (`aggregate_window` / `accrue_window`) applies the
platform cut via `_apply_published_split` after the per-second filter+weight
engine, stamps `ATTRIBUTION_MATH_VERSION` on every row, and keeps the
window-level conservation identity:

```
Σ asset cents + house cents == window ad value cents
```
