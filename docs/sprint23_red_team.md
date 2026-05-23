# Sprint 23-24 — Anti-Gaming Layer Red-Team Report

**Status:** Template — to be filled in by an external red-team before Sprint 23-24 ship.

**Gate:** This document is the Sprint 23-24 §1 callout gate (c) artefact —
*"the anti-gaming layer passes a documented adversarial review."* If this
file does not exist, is not filed, or any of the three attack classes is
not documented as caught pre-payout, Sprints 23-24 do not ship.

**Author:** _[external red-team firm or independent reviewer; not the
operator]_

**Reviewed:** _[YYYY-MM-DD]_

**Substrate version under review:** _[git SHA of substrate/anti_gaming/
+ substrate/rev_share/ + tools/stripe_connect/payouts.py at review time]_

---

## §1 Scope and binding posture

This review is a precondition for Sprints 23-24 to ship lead-gen ads with
real rev-share routing. Per the doc's Phase 4 ads callout, three
pre-conditions gate the sprint; this report addresses condition (c).

Out of scope for this review:
- Sprint 22 multi-user pivot stability (condition (a); separate evidence)
- Sprint 22 accrual without rev-share routed (condition (b); separate evidence)
- Stripe Connect's own anti-fraud (provider-internal; not our substrate)

In scope:
- `substrate/anti_gaming/click_fraud.py` — UA + IP entropy + dwell-time signals
- `substrate/anti_gaming/view_fraud.py` — session-burst + short-dwell + repeat-impression signals
- `substrate/anti_gaming/attribution_fraud.py` — single-user dominance + chain-depth + cluster collusion
- `substrate/anti_gaming/detector.py` — composite verdict aggregation
- `tools/stripe_connect/payouts.py` — verdict → PASS/REVIEW/BLOCK gating

---

## §2 Attack classes the layer must catch

Three documented attack classes — derived from master-spec §9.2 and the
Sprint 23-24 doc deliverables. The red-team executes each against a
staging substrate seeded with realistic non-attacker traffic and reports
whether the payout pipeline catches the attack before money moves.

### Attack class A — Botnet view inflation

**Attacker objective:** drive ad impressions on attacker-controlled creator
pages to siphon ad revenue without legitimate views.

**Method:** instantiate a botnet of N headless browsers; each one
fetches the target creator's page and records an impression. Same UA
string OR same /24 subnet OR sub-200ms dwell.

**Expected substrate response:**
- `score_click_event` should detect low UA entropy when N ≥ 20 within window
- `score_click_event` should detect low IP-subnet entropy when sources share /24
- `score_view_event` should detect short_dwell on every impression
- Composite verdict should be BLOCK; `tools/stripe_connect/payouts.py`
  should drop the impression revenue with an audit-log entry

**Pass criterion:** _[fill in]_ — exactly zero payouts initiated;
operations_log records `op_type=payout_blocked` for each.

**Observed result:** _[to be filled in by red-team]_

**Verdict:** _[PASS / FAIL]_

### Attack class B — Attribution-graph injection

**Attacker objective:** inflate one creator's attribution share by
manufacturing long synthetic citation chains.

**Method:** create a synthesis pipeline that artificially extends the
chain depth from a target creator's chunk through N intermediate hops.
On payout, the target creator captures more share than they would on a
short legitimate chain.

**Expected substrate response:**
- `score_attribution_payout` should detect `deep_attribution_chain` when
  chain_depth > DEEP_CHAIN_THRESHOLD (8)
- Composite verdict should be REVIEW (or BLOCK if combined with other signals)
- `tools/stripe_connect/payouts.py` should escrow the line, not transfer

**Pass criterion:** _[fill in]_ — zero transfers; chain-depth signal
visible in the verdict; operator queue receives the line for manual review.

**Observed result:** _[to be filled in by red-team]_

**Verdict:** _[PASS / FAIL]_

### Attack class C — Multi-account self-attribution

**Attacker objective:** route revenue from N attacker-controlled consumer
accounts back to one attacker-controlled creator account, capturing
outsized rev-share without legitimate readership.

**Method:** spin up N consumer accounts; each one repeatedly cites the
target creator's content. Over a billing window, the target creator's
accrual is dominated by these N accounts.

**Expected substrate response:**
- `score_attribution_payout` should detect `single_consumer_dominance`
  when one consumer accounts for > SINGLE_USER_DOMINANCE_THRESHOLD (55%)
  of the creator's window accrual
- Composite verdict should be REVIEW (or BLOCK on threshold breach)
- `tools/stripe_connect/payouts.py` should escrow + operator queue

**Pass criterion:** _[fill in]_ — zero transfers; dominance signal
visible; operator queue notified.

**Observed result:** _[to be filled in by red-team]_

**Verdict:** _[PASS / FAIL]_

### Attack class D (optional but recommended) — Creator-cluster collusion

**Attacker objective:** a ring of M creators mutually cite each other,
artificially boosting each member's accrual.

**Method:** seed the substrate with M creator accounts. Each publishes
notes that cite the others. Run `detect_creator_cluster_collusion` over
the window.

**Expected substrate response:**
- `detect_creator_cluster_collusion` flags every member of the ring
  with `cluster_collusion` signal when the ratio crosses
  CLUSTER_COLLUSION_THRESHOLD (0.60) and the ring has ≥ 3 members
- Operator queue receives all ring members for manual review

**Pass criterion:** _[fill in]_ — ring of 3+ flagged; ratio ≥ 0.60.

**Observed result:** _[to be filled in by red-team]_

**Verdict:** _[PASS / FAIL]_

---

## §3 Calibration sensitivity

The detector thresholds (`REVIEW_THRESHOLD = 0.45`, `BLOCK_THRESHOLD = 0.75`,
`SINGLE_USER_DOMINANCE_THRESHOLD = 0.55`, etc.) are calibrated for the
adversarial review. The red-team should also test:

1. **False positive rate:** seed the substrate with N non-attacker
   sessions over the window. Report the share that get REVIEW or BLOCK
   verdicts. Target: ≤ 1% false-positive rate on REVIEW; ≤ 0.1% on BLOCK.
2. **Detection latency:** time from first attacker impression to BLOCK
   verdict firing. Target: ≤ 60 seconds for botnet attacks (the rolling
   window's natural propagation time).

**Observed FP rate:** _[fill in]_
**Observed detection latency:** _[fill in]_

---

## §4 Closing verdict

**All four attack classes caught pre-payout?** _[YES / NO]_

**False-positive rate within target?** _[YES / NO]_

**Detection latency within target?** _[YES / NO]_

**Recommended go/no-go for Sprint 23-24 ship:** _[GO / NO-GO]_

If NO-GO: specific calibration changes recommended _[fill in]_.

---

## §5 Operator follow-up

Upon GO verdict:
1. Operator counter-signs this report.
2. Operator opens Sprint 23-24 ship in the calendar.
3. The report is checked into `docs/` (this file) at the SHA observed in
   the substrate-version-under-review line.

Upon NO-GO verdict:
1. Operator schedules a remediation sprint addressing the recommended changes.
2. Re-review against this template once remediation lands.
3. Sprints 23-24 hold until a subsequent GO verdict is filed.

---

_Template: substrate/anti_gaming + substrate/rev_share + tools/stripe_connect/payouts.py
_landed locally in this session. Activation behind this binding gate per the
docs/sprint-breakdown.html Sprint 23-24 §1 callout._
