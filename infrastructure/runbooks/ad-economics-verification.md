# Ad-economics end-to-end verification (SPR-11)

**Status: the capstone verification of the per-second ad-economics chain.**
This runbook tells the operator how to reproduce, from scratch, the proof that
the Antiek money story is reconcilable to the cent, traceable from any escrow
entry back to the second and asset that produced it, and structurally incapable
of disbursing a dollar while the G2/G3 legal gate is open.

It verifies the COMPOSITION of already-shipped economics modules. It builds no
new economics. The harness drives the real chain:

```
auction (SPR-10 select_ad) prices the window
  → per-second frame attention (SPR-05 weigh_second, eligibility-filtered)
    → accrue_window (persists accrual + house rows, routes per-asset → escrow)
      → ip_holders.accrue_escrow  (the ONE sanctioned escrow writer)
  → explain_asset_earning (SPR-04) traces a cent back to second→chunk→asset
  + contributor.attempt_disbursement is CALLED and asserted BLOCKED
    (rigor #3 — prove the negative; money does NOT move)
```

> **This is NOT literal prod traffic.** There is no SPR-08 prod corpus in this
> tree. The harness runs over a small, deterministic, faithful **prod-shaped
> fixture** (real content classes, real publishers-as-`pre_onboarded` holders,
> realistic per-second visibility). The value is proving the modules COMPOSE
> and reconcile — not measuring real revenue. Every number below is fixture
> output. When a real corpus exists, re-point the harness's `_build_corpus()`
> at it; the assertions are corpus-agnostic.

---

## How to run

```bash
# the harness + auditable report (idempotent; safe to re-run)
.venv/bin/python tools/verify_ad_economics.py

# the e2e assertions
.venv/bin/python -m pytest tests/test_ad_economics_e2e.py -q
```

The harness exits non-zero if conservation, traceability, the safety valve, or
idempotency fails. It is read-only against any recorded corpus; every DB write
goes through the single-writer lock (`runtime.db_lock.connect_write`).

---

## What each milestone proves (and the exact assertion)

| M | Claim | Proven by |
|---|---|---|
| M1 | the chain runs through the ACTUAL modules, no mocks; idempotent | every session has a real `WindowAccrual` whose `batch_ref` starts `frame-batch-`, a real `select_ad` pick, and `replay().identical`; re-accrue → escrow unchanged |
| M2 | conservation to the cent + 70/30 from constants | `Σ contributor + Σ house == Σ ad value` (run + per-window); split read from `payout.CREATOR_REV_SHARE`/`PLATFORM_CUT`; all amounts ≥ 0 |
| M3 | traceability amount→chunk→asset→holder, reconciles | each holder's escrow traces via `explain_asset_earning` + the frame accrual rows to the EXACT accrued cents (`trace_reconciles=True`); per-chunk sums to asset total |
| M4 | eligibility gate read, not re-derived | `user_owned` earns $0 even alone (whole window → house); `restricted_pending_opt_in` earns to escrow while NOT in `FULL_TEXT_SERVABLE`; verdicts come from `monetization_eligible` |
| M5 | house-second pocket is an explicit line | a zero-eligible window writes a `house_seconds` row, no contributor accrues; `Σ house` recomputed independently equals the report and reconciles into M2 |
| M6 | safety valve: escrow accrues, NOTHING disburses | escrow lands on `pre_onboarded` holders (no notification); `attempt_disbursement` raises `DisbursementBlocked`; `ANTIEK_STRIPE_PROVIDER != real`; no `tools/stripe_connect/` import; report states `disbursed: $0 (G2/G3 open)` |

---

## Reconciliation note (rigor #1 — honesty)

Conservation holds **to the cent**: `Σ contributor ($0.38) + Σ house ($0.02) ==
Σ ad value ($0.40)`.

One honest subtlety the report surfaces (and now states in prose in the
CONSERVATION block): `Σ contributor accrual ($0.38)` is LARGER than
`Σ escrow-by-holder ($0.34)`, a `$0.04` gap. This is correct, not a leak. The
gap is exactly one asset: `doc-open-cc` (source-declared-open) accrues `$0.04`
to the `frame_attention_accruals` ledger but has **no `ip_holder_id`**, so it
credits no escrow balance — there is no holder to pay. (`doc-pd-lecture` is also
unmapped, but its per-second apportionment rounds to `$0.00` under
largest-remainder against the higher-weighted `doc-mit-quantum` in its window,
so it does NOT contribute to the gap.) Unmapped-but-eligible assets earn into
the ledger so the window conserves, while escrow-by-holder sums only the mapped
publishers. The conservation invariant is on the ACCRUAL ledger, not on escrow
— exactly as designed (`accrue_window` only calls `accrue_escrow` for asset
lines with a known holder and amount > 0).

---

## Safety valve (rigor #3 — the negative is proven, not assumed)

- The real `substrate.speak.gate_status.disbursement_allowed()` returns
  `allowed=False` (default `ANTIEK_STRIPE_PROVIDER=mock`).
- `substrate.speak.contributor.attempt_disbursement(...)` is CALLED and raises
  `DisbursementBlocked` — the harness does not merely refrain from calling.
- Independently, every earning holder is `pre_onboarded`. `ip_holders.claim()`
  (the ONLY transition that unlocks payout) is never called, so even if the
  gate were open, status alone blocks the payout.
- No module under `tools/stripe_connect/` is imported or invoked.
- The G2/G3 gate is **not** closed, flipped, simulated, or bypassed by this
  sprint. Closing it is an operator action gated on counsel sign-off (see
  `docs/operator_gate_actions.md`).

---

## Recorded report (fixture run)

`ipholder-*` surrogate keys are random per run; the economic substance is
deterministic and reproducible (asserted by
`test_report_reconciles_and_is_reproducible`).

```
==============================================================================
ANTIEK AD-ECONOMICS — END-TO-END VERIFICATION REPORT (SPR-11)
==============================================================================

SOURCE: faithful PROD-SHAPED FIXTURE corpus (NOT literal prod traffic).
        No SPR-08 prod corpus exists in this worktree; this run proves the
        COMPOSITION of the real modules reconciles, not real revenue figures.

-- SESSIONS (auction-priced → per-second frame → accrual) ------------------
window              lens       secs  ad_slot           ad_value   contrib    house  rec
win-read-001        read         12  inv-quantum-a        $0.10     $0.10    $0.00  OK
win-research-002    research     20  inv-defense-a        $0.24     $0.24    $0.00  OK
win-write-003       write         8  inv-history-a        $0.04     $0.04    $0.00  OK
win-read-004        read          6  inv-quantum-a        $0.02     $0.00    $0.02  OK

-- PER-ASSET ACCRUAL (the per-second engine output) -------------------------
  win-read-001           doc-mit-quantum            $0.10  holder=ipholder-XXX
  win-read-001           doc-pd-lecture             $0.00  holder=(unmapped/no-holder)
  win-research-002       doc-cup-gated              $0.20  holder=ipholder-XXX
  win-research-002       doc-open-cc                $0.04  holder=(unmapped/no-holder)
  win-write-003          doc-princeton-hist         $0.04  holder=ipholder-XXX

-- ELIGIBILITY DECISIONS (read via monetization_eligible) -------------------
  doc-mit-quantum        content_class='opt_in_licensed'              -> EARNS
  doc-pd-lecture         content_class='public_domain'                -> EARNS
  doc-user-notes         content_class='user_owned'                   -> EARNS $0
  doc-cup-gated          content_class='restricted_pending_opt_in'    -> EARNS
  doc-open-cc            content_class='source_declared_open'         -> EARNS
  doc-princeton-hist     content_class='opt_in_licensed'              -> EARNS
  doc-only-private       content_class='user_owned'                   -> EARNS $0

-- ESCROW BY HOLDER (servable-vs-pre_onboarded) -----------------------------
  Princeton University Press            $0.04  [pre_onboarded (held)]
  Cambridge University Press            $0.20  [pre_onboarded (held)]
  MIT Press                             $0.10  [pre_onboarded (held)]

-- TRACEABILITY (amount -> chunk -> asset -> holder) ------------------------
  Princeton University Press (pre_onboarded) escrow=$0.04 trace_reconciles=True
      doc-princeton-hist     eligible=True frame_accrued=$0.04 chunks=['ch-ph-1']
  Cambridge University Press (pre_onboarded) escrow=$0.20 trace_reconciles=True
      doc-cup-gated          eligible=True frame_accrued=$0.20 chunks=['ch-cg-1']
  MIT Press (pre_onboarded) escrow=$0.10 trace_reconciles=True
      doc-mit-quantum        eligible=True frame_accrued=$0.10 chunks=['ch-mq-1']

-- HOUSE SECONDS POCKETED (platform; no contributor) ------------------------
  total house seconds value: $0.02
      win-read-004               $0.02  reason=no_eligible_asset_in_frame

-- ATTRIBUTION ALGORITHM A/B (read-only; operator picks) --------------------
  active default: claim_confidence_times_source_tier
  document                     A       B       C
  doc-cup-gated            0.200   0.266   0.259
  doc-mit-quantum          0.200   0.352   0.333
  doc-open-cc              0.200   0.039   0.074
  doc-pd-lecture           0.200   0.094   0.111
  doc-princeton-hist       0.200   0.250   0.222

-- CONSERVATION (rigor #1: report the truth, do not fudge) ------------------
  total ad value      : $0.40
  Σ contributor accrual: $0.38
  Σ house seconds     : $0.02
  contributor + house  : $0.40
  CONSERVES TO THE CENT: True (per-window: True)
  Σ escrow-by-holder   : $0.34
    NOTE: Σ contributor accrual exceeds Σ escrow-by-holder by $0.04 — eligible asset(s) with NO ip_holder accrue to the ledger but credit no escrow: doc-open-cc ($0.04). Conservation is on the accrual ledger, not escrow. Not a leak (see runbook).
  rev split (read from payout.py): creator=0.70 platform=0.30 sums_to_1=True
  all amounts non-negative: True

-- SAFETY VALVE (rigor #3: prove money does NOT move) -----------------------
  disbursement_allowed(): allowed=False
    reason: disbursement is gated on G2/G3 (ANTIEK_STRIPE_PROVIDER=mock by default); contribution shares accrue to escrow but no money routes until the legal gate clears.
  attempt_disbursement(): blocked=True
    via: substrate.speak.contributor.attempt_disbursement -> DisbursementBlocked
    blocked_reason: disbursement is gated on G2/G3 (ANTIEK_STRIPE_PROVIDER=mock by default); contribution shares accrue to escrow but no money routes until the legal gate clears.
  holder status independently blocks payout (no claim()): True
  no Stripe path under tools/stripe_connect/ invoked: True

  >>> disbursed: $0 (G2/G3 open) <<<

==============================================================================
OVERALL: VERIFIED — money story reproduces and the valve holds
==============================================================================

IDEMPOTENCY (re-accrue identical batches in same DB): OK — no double accrual
```

---

## A/B note (read-only — operator picks the production algorithm)

The A/B block runs all three §9.3 attribution algorithms over the period's
cited chunks via `attribution_audit.compare_algorithms`. Option A
(equal-split) is flat at 0.200; Options B (confidence × tier) and C
(load-bearing) diverge because the fixture gives each asset a distinct
confidence/tier/load-bearing profile. The active default is **Option B**
(`claim_confidence_times_source_tier`). This surface compares; it does not
decide — the production choice is the operator's (master-spec §9.3).

## Files

- `tools/verify_ad_economics.py` — the harness + report (runnable standalone)
- `tests/test_ad_economics_e2e.py` — the e2e assertions (M1–M6)
- This runbook — operator reproduction guide + recorded report

This sprint touches NOTHING under `substrate/ad_inventory/payout.py` or
`tools/stripe_connect/` (`git diff --stat` on both is empty).
