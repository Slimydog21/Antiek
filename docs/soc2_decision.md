# Sprint 25+ — SOC 2 Type II Pursue/Defer Decision

**Status:** Template — to be filled in at Sprint 25+ when the
enterprise-procurement signal is evaluated.

**Discipline:** Per master-spec §13.7, SOC 2 Type II is **conditional**
on enterprise demand. Sprint 25+ is when substrate hygiene becomes mature
enough to fund a real observation window if procurement opens. The
decision is binary: pursue OR defer. The substrate-controls work from
Sprint 18 stays valuable either way — SOC 2 is monetisation of existing
discipline, not new engineering investment.

**Author:** _[operator]_

**Decided:** _[YYYY-MM-DD]_

**Cited evidence:**
- Latest `/marketplace/snapshot` output: _[link or paste]_
- Cumulative enterprise procurement conversations: _[count + summary]_
- Substrate hygiene readiness: _[link to Sprint 18 trust-controls
  scaffolding evidence]_

---

## §1 Verdict

**Decision: _[PURSUE / DEFER]_**

---

## §2 The procurement-signal threshold

Per master-spec §13.7, the trigger for SOC 2 pursuit is:

> *"Enterprise procurement opens. At least one credible deal blocked
> on SOC 2 Type II attestation, or a documented pipeline of ≥ 3 such
> deals."*

**Current measurement:**
- Deals blocked on SOC 2 specifically: _[count, with deal IDs/refs]_
- Pipeline of SOC-2-gated prospects: _[count]_
- Estimated annual contract value at risk if SOC 2 not pursued:
  $_[amount]_
- Comparison: SOC 2 Type II first-report cost (Drata / Secureframe
  + auditor): ~$30–60K + 6 months of operator + counsel attention

**Cost vs. value:**
- If ACV at risk > 3× first-year SOC 2 cost: PURSUE
- If ACV at risk < 2× first-year cost OR no deals are blocked: DEFER

---

## §3 Substrate readiness

The substrate-controls scaffolded in Sprint 18 (§13.10) become the
SOC 2 evidence chain. Pre-existing controls — re-evaluated for
SOC-2-ready evidence:

| Control | Sprint 18 scaffold | SOC-2-ready evidence | Status |
|---------|--------------------|-----------------------|--------|
| Encryption at rest (per-graph KMS) | ✓ designed in | _[need to verify KMS integration is live]_ | _[ready / gap]_ |
| Access logging (append-only) | ✓ in code | _[need: log retention period documented]_ | _[ready / gap]_ |
| Change management | ✓ CI gates on schema | _[need: change-approval workflow document]_ | _[ready / gap]_ |
| Vulnerability scanning | ✓ Dependabot/Snyk | _[need: SLA on critical-CVE remediation]_ | _[ready / gap]_ |
| Backup testing | ✓ quarterly drill | _[need: restore-success log]_ | _[ready / gap]_ |
| Retrieval-time policy_tag gating | ✓ SQL-WHERE level | _[need: audit trail for policy-tag bypasses]_ | _[ready / gap]_ |

**Substrate readiness verdict:** _[READY / GAPS REMAIN]_

If gaps remain: the SOC 2 pursuit absorbs the remediation work into
its scope. Don't pursue SOC 2 with the intention of "we'll close the
gaps as we go" — auditors don't accept that posture.

---

## §4 If PURSUE

Sequenced plan, gated on operator + counsel signoff at each step:

1. **Vendor selection** — Drata vs. Secureframe vs. Vanta vs.
   build-in-house. Decision: _[fill in]_. Decision factors: _[fill in]_.
2. **Auditor selection** — _[firm name, A-2/CPA credentials, prior
   experience with AI/ML platforms]_
3. **Observation window opens** — _[YYYY-MM-DD]_
4. **Observation window closes** — _[YYYY-MM-DD; default = 6 months later]_
5. **Report delivered** — _[expected YYYY-MM-DD]_

Cost estimate at signing: _$[total]_
Cost estimate at delivery (Type II first report): _$[total]_

---

## §5 If DEFER

Document the specific signal that's missing, so the next quarterly
review knows what changed:

**Why DEFER now:** _[fill in — usually one of "no enterprise demand
signal yet" or "demand signal present but ACV below cost threshold"]_

**Renewal date:** _[YYYY-MM-DD; default = +1 quarter]_

**What would flip this to PURSUE:** _[fill in — specific deal pipeline
threshold, or specific blocked deal]_

**Substrate hygiene maintenance:** continues regardless. The Sprint 18
trust-controls scaffold stays under the same maintenance discipline so
that PURSUE at a future date doesn't require a "catch up the substrate"
sprint.

---

## §6 Cross-references

- Master-spec §13.7 — Trust posture + SOC 2 conditional triggering
- Sprint 18 (`docs/sprint-breakdown.html` → S18 §3) — substrate trust controls
- Sprint 25+ (`docs/sprint-breakdown.html` → S25+ §2 SOC 2 phase)
- `substrate/trust_center/` — publication payload showing current
  control posture (consumed by `/trust-center` endpoint)

---

_Template: paired with the Sprint 25+ §2 SOC 2 conditional phase.
A filed decision (PURSUE or DEFER) IS the deliverable. An absent file
means the gate has not been evaluated this quarter._
