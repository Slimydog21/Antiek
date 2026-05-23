# Sprint 23-24 — Red-Team Report (Internal Baseline Evidence)

**Status:** Operator-produced internal baseline. NOT a substitute for
the external red-team review the Sprint 23-24 §1 gate (c) requires.
The external firm runs the same harness (or stronger attacks) and
files `docs/sprint23_red_team.md`; this file is the operator's
substrate-self-test artefact, demonstrating the harness works and
catching obvious regressions BEFORE the external engagement.

**Generated:** 2026-05-21

**Substrate version under test:** `dc05cde+phase2_scaffold`
(uncommitted; HEAD = `dc05cde`, plus the Phase 2 substrate scaffold
landed locally this session — `substrate/anti_gaming/`,
`substrate/rev_share/`, `tools/stripe_connect/payouts.py`)

**Harness used:** `substrate.anti_gaming.red_team.run_red_team_report`
with `fp_sample_size=1000`.

---

## §1 Overall verdict — internal baseline

**GO** — all four attack classes caught at the expected verdict level
or stronger; FP rate within the calibration targets. This satisfies
the operator-side check; gate (c) STILL requires an external firm to
re-run (or strengthen) these tests and file the binding
`docs/sprint23_red_team.md`.

---

## §2 Attack-class results

### Attack A — Botnet view inflation

- **Expected verdict:** `block`
- **Observed verdict:** `block`
- **Signals fired:** `fast_dwell`, `low_ua_entropy`, `low_ip_entropy`, `short_dwell`
- **Samples scored:** 50 / **blocked-or-reviewed:** 50
- **Verdict:** **PASS**

Method: 50-bot fleet, all sharing a Mozilla UA string + the 203.0.113.0/24
subnet + 50ms dwell. The composite verdict fires all four expected
click+view signals once the entropy window builds up
(MIN_WINDOW_SAMPLES = 8).

### Attack B — Attribution-graph injection

- **Expected verdict:** `review`
- **Observed verdict:** `review`
- **Signals fired:** `deep_attribution_chain`
- **Samples scored:** 1 / **blocked-or-reviewed:** 1
- **Verdict:** **PASS**

Method: synthetic citation chain of depth 12 (the threshold is 8).
`score_attribution_payout` fires the deep-chain signal; the verdict
escrows the line rather than transferring.

### Attack C — Multi-account self-attribution

- **Expected verdict:** `review`
- **Observed verdict:** `review`
- **Signals fired:** `single_consumer_dominance`
- **Samples scored:** 1 / **blocked-or-reviewed:** 1
- **Verdict:** **PASS**

Method: one consumer accounting for 85% of a creator's window accrual
(threshold is 55%). The verdict escrows; operator queue receives the
line.

### Attack D — Creator-cluster collusion

- **Expected verdict:** `review`
- **Observed verdict:** `block`  *(stronger than expected — over-catch
  passes the gate)*
- **Signals fired:** `cluster_collusion`
- **Samples scored:** 3 ring members / **blocked-or-reviewed:** 3
- **Verdict:** **PASS**

Method: 3-creator ring routing 85% of outbound attribution among
themselves (threshold ratio 0.60). Every ring member flagged. The
ring-internal-numerator fix (this session) ensures non-ring
recipients in the denominator don't dilute the ratio.

---

## §3 False-positive calibration

- **Samples scored:** 1000 legitimate sessions
- **REVIEW rate:** 0.0000 (target ≤ 0.0100)
- **BLOCK rate:** 0.0000 (target ≤ 0.0010)
- **FP rate acceptable:** **True**

Method: 1000 synthesised legitimate sessions, each with unique UA +
unique /24 + dwell 3-8s + view-dwell 1.5-3.5s + impression every 5s
+ chain depth 2-5. Zero false positives at either verdict level. The
substrate's calibration leaves comfortable headroom above the
documented targets.

---

## §4 What this does NOT establish

Per master-spec §1 of `docs/sprint23_red_team.md`:

1. **This is operator-self-test, not external.** Gate (c) requires
   `docs/sprint23_red_team.md` filed by an external red-team firm.
   This file is preparation evidence: it shows the harness works and
   the substrate's current calibration would pass *if the external
   firm reused these attacks unmodified*. External firms typically
   strengthen attacks; the substrate must hold up.

2. **No production traffic was scored.** All attacks + all FP samples
   are synthesised inside the harness. Production-trace replay is a
   stronger evidence form and is recommended once Sprint 17-21 ship
   produces real ad-impression traces.

3. **The other two Sprint 23-24 §1 gates are independent:**
   (a) Sprint 22 multi-user pivot stability — NOT MET (Sprint 22 not
       even committed)
   (b) one creator + one publisher accruing — NOT MET (zero creators
       and zero accrued publishers in substrate today)

4. **Bypassing this file does not unlock Sprint 23-24.** Gate (c) is
   binding; an operator-only file IS not the gate (c) artefact, by
   the spec's own discipline. This file is the operator's evidence
   that the substrate is *ready for the external review to begin*.

---

## §5 Recommended next operator actions

1. Address gate (a): commit + push Sprint 17-21 substrate; ship Sprint 22.
2. Address gate (b): once Sprint 22 ships, run the creator + publisher
   accrual loop on a small cohort.
3. Schedule the external red-team engagement; provide them this file
   + harness reproducibility instructions.
4. The external firm files `docs/sprint23_red_team.md` per the §1
   template; THAT file unlocks gate (c).
