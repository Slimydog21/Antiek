# Operator-only gate actions

**Generated 2026-05-22 as a companion to the master-spec audit.**

The audit identified eight binding gates blocking activation of substrate that
is already shipped in code. **Engineering cannot close these gates.** Each one
requires the operator (or an external party) to act. This document is the
checklist with minimum inputs and an explicit owner.

The eight gates, with their current state and the action required:

---

## G1 — Retrieval-time legal gating in production

**Status:** ✅ **CLOSED**

Already enforced at the SQL-WHERE level in `substrate/graph/search.py`. No
operator action required. Closed by commits c111200 and prior.

---

## G2 — Lawyer review of Kalshi-pattern publisher notification template

**Status:** ❌ OPEN
**Owner:** Operator + counsel
**Blocks:** All Stripe payouts; first publisher outreach

The Kalshi-pattern notification template at `substrate/ip_holders/__init__.py`
(`NOTIFICATION_EMAIL_TEMPLATE`) and the `ip_holders` state-machine documented
at §9.10 must be reviewed by counsel **before any notification email sends**.

### Inputs needed for the lawyer

1. **Plain-English summary of the §9.10 architecture** — pre-onboarded escrow
   pattern, opt-in-only payout activation, costless 30-day opt-out, segregated
   regulated accounts.
2. **The template itself** — render once with a fixture publisher:
   ```bash
   ./.venv/bin/python -c "
   from substrate.ip_holders import IpHolder, render_notification_email
   from datetime import datetime, timezone
   h = IpHolder(
     ip_holder_id='mit-press',
     display_name='MIT Press',
     contact_email='legal@mitpress.mit.edu',
     status='pre_onboarded',
     escrow_balance_usd=0.0,
     created_at=datetime.now(timezone.utc).isoformat(),
   )
   print(render_notification_email(h))
   "
   ```
3. **Bartz v. Anthropic settlement context** — the $1.5B precedent that
   makes pre-payout exposure (takedown) materially less expensive than
   post-payout exposure (Bartz-level damages on a contemporary monetary
   transaction).
4. **Hachette v. Internet Archive context** — the Second Circuit ruling
   killing the structural fair-use argument.

### What the lawyer signs off on

- Template wording is defensible under current US copyright + commercial
  speech doctrine.
- The opt-in-only payout gate is sufficient to convert pre-payout exposure
  into a "we will pay you for prospective use" posture per §9.0.
- The 30-day costless opt-out is sufficient under Judge Chin's rejection
  of opt-out-by-default in the Google Books precedent.

### Once closed

Commit a one-line decision note at `docs/decisions/g2-lawyer-review.md`
recording the date and the lawyer's name + firm. Sprint 19 first-cohort
outreach can then proceed.

---

## G3 — At least one publisher affirmatively opted in

**Status:** ❌ OPEN
**Owner:** Operator (outreach) + publisher (decision)
**Blocks:** All Stripe payouts

Per §9.0: payouts gate strictly on publisher opt-in. The Sprint 19 plan
sequences MIT Press → Cambridge University Press → Princeton University
Press first; Big Five last per §9.10.

### Action sequence after G2 closes

1. Operator runs the first-cohort notification flow:
   ```bash
   # On the VM (or local with API_BASE pointed at prod):
   curl -sS -X POST https://api.antiek.ai/publishers \
     -H "Cookie: ANTIEK_SESSION=$YOUR_COOKIE" \
     -H "Content-Type: application/json" \
     -d '{"display_name": "MIT Press", "contact_email": "...", ...}'
   ```
2. For each publisher row, transition `pre_onboarded → invited` via:
   ```
   POST /publishers/{id}/notify
   ```
3. Send the notification email (Resend, once G2 is closed).
4. Wait for the publisher to claim:
   ```
   POST /publishers/{id}/claim
   ```
5. **First successful claim closes G3.** Sprint 18 → Sprint 19 transition
   can proceed; Stripe Connect activation flips from mock to real.

### Expected timeline

Realistic: 4-8 weeks per publisher cohort. Universities respond on
quarter-cycle. Big Five expect 3-6 months even after MIT Press has signed.

---

## G4 — Lemon UI operator visual eye-test

**Status:** ❌ OPEN (overtaken by events)
**Owner:** Operator
**Blocks:** Full TipTap editor expansion in Sprint 18 (largely moot now)

The Sprint 17 spike doc at `docs/sprints/sprint17-lemon-ui-spike.md`
evaluated `@posthog/lemon-ui` against four gates: bundle size <80KB,
TypeScript strict, Tailwind interop, aesthetic fit (researcher's-notebook
vs SaaS-dashboard).

**This gate was overtaken by the de52534 brand-redesign decision.** The
operator chose to ship custom Lemon-flavored primitives (`apps/reading/src/
components/lemon/`) with the Werner / Antarctic palette + sun-yellow outline
instead of adopting `@posthog/lemon-ui` wholesale. The TipTap notebook
editor is shipping against the custom primitives.

### Action

Commit a one-line decision note at `docs/decisions/g4-lemon-ui-verdict.md`
recording: "REJECTED `@posthog/lemon-ui` direct adoption. Custom
`src/components/lemon/` primitives chosen, sun-yellow outlined per
de52534 brand bible. Closed 2026-05-21." Then mark G4 closed.

---

## G5 — Dispatch tier-differentiation measurement verdict

**Status:** ⏳ MEASUREMENT WINDOW ACTIVE
**Owner:** Operator (run the analyzer at window close)
**Blocks:** Sprint 20 verdict; downstream cost models

The synthesizer tier has been pinned to Opus 4.7 via OpenRouter primary
since Sprint 17. After ≥14 days of live traffic, the operator runs:

```bash
./.venv/bin/python -m tools.dispatch_tier_verdict \
    --events ~/.antiek/events/ \
    --since 2026-05-08 \
    --output docs/decisions/dispatch-tier-verdict.md
```

The analyzer (committed today, `tools/dispatch_tier_verdict/`) produces
the verdict markdown. If Grok-4.3 stays within 5pp of Opus on overall
pass rate → flip back to Hermes for cost. Otherwise → keep Opus.

### Once closed

Commit the produced markdown; update `substrate/dispatch/config.yaml`
synthesis tier if the verdict is `flip_to_hermes_primary`.

---

## G6 — Autoresearch Wedge 1 ratification (the Lutke-gap test)

**Status:** ⏳ AWAITING OPERATOR TEST
**Owner:** Operator (run the verdict at end of mutation cohort)
**Blocks:** Phase 8 enforcing mode + autoresearch Wedges 2-4

The local-only prompt-autoresearch runner is at `tools/prompt_autoresearch/`.
The operator runs ≥20 mutations against the synthesizer's golden traces
and then closes the gate with:

```bash
./.venv/bin/python -c "
from tools.prompt_autoresearch.verdict import compute_verdict, render_verdict_markdown
from <your-runner-results> import outcomes
v = compute_verdict('synthesizer', outcomes)
md = render_verdict_markdown(v)
print(md)
" > docs/decisions/autoresearch-wedge-1-verdict.md
```

The verdict module (committed today, `tools/prompt_autoresearch/verdict.py`)
enforces the four-criterion Lutke-gap test: ≥20 mutations, ≥40% acceptance,
≥0.05 mean delta, no sub-metric regression on grounding or sector vocab.

### Once closed

If RATIFY → Phase 8 gate flips shadow → enforcing (Sprint 21).
If REJECT → Phase 8 stays unconditional; Wedges 2-4 fall off the roadmap.
Both outcomes are defensible per §15.6.

---

## G7 — Six months of solo-operator compounding demonstration

**Status:** ❌ OPEN (earliest closure ~Nov 2026)
**Owner:** Operator (publish + demonstrate)
**Blocks:** Multi-user pivot (Sprint 22)

Per §13.4: premature multi-user destroys the moat that multi-user is
supposed to monetize via graph contamination. Six months of operator-graph
accumulation showing the compounding curve is the minimum demonstration
period.

### What counts as demonstration

1. **Investigation count:** ≥100 investigations completed in the production
   substrate.
2. **Cross-investigation reuse:** ≥20% of new investigations cite a chunk
   that was first ingested in a prior investigation (substrate compounding
   metric).
3. **Visible artifacts published:** ≥3 substantial research outputs
   (memo, chapter, brief) published under any byline from Antiek
   syntheses — the §9.0.1 / §13.4 growth-motion thesis.
4. **Peer-discovery signal:** ≥1 unsolicited inquiry from a peer asking
   what tool produced the published outputs.

### Once closed

Commit a status doc at `docs/decisions/g7-compounding-demonstration.md`
with the four metrics. Sprint 22 multi-user pivot can then proceed
(Clerk/Supabase auth + per-user DuckDB + Trust Center).

---

## G8 — Loop 3 unlock criteria (five sub-gates)

**Status:** ❌ OPEN (none of the five checked)
**Owner:** Operator (after substrate accumulation)
**Blocks:** All RLM + SFT + hosted RL work

The five criteria in `docs/loop_3_unlock_criteria.md`:

1. **Trajectory volume:** ≥ N graded outcomes (operator-defined N; likely
   ~500 per role).
2. **SFT readiness:** dataset shape validated; cleanup pipeline exists.
3. **Validated reward:** reward function audit complete; correlates with
   operator judgment under blinded review.
4. **Open-weight justification:** clear reason to fine-tune open-weight
   over continuing closed-weight routing.
5. **Eval headroom:** clear margin between current performance and
   operator-acceptability target that fine-tuning could plausibly close.

### What does NOT happen until G8 closes

Per §16 and §16.1: no SFT loop, no verifiers env for training (substrate-
eval envs are different), no hosted-RL plumbing. Hosted `prime rl run`
strictly DEFERRED.

### Once closed

The unlock substrate at `substrate/loop_3/unlock_gate.py` checks each
criterion. When all five return True, the env-var `ANTIEK_LOOP_3_UNLOCKED=1`
becomes valid and the RLM-1..RLM-5 work + the autoresearch Wedge 4 local
SFT loop become unblocked.

---

## §15 Strategic open questions still open

Six of the nine §15 questions remain open (G2, G3, G4, G6, G7, G8 above
each correspond to one). The remaining three:

- **§15.2 Browser-extension distribution** — sideloaded Chrome ships; Web
  Store path not started. Operator decision: ship to Web Store when there
  are ≥3 active users, else stay sideloaded.
- **§15.3 Voice interview latency** — async ~3-5s shipped; the formal
  "operator acceptable rhythm" measurement has not been done. Operator
  should run a 5-minute interview and rate the latency 1-5.
- **§15.4 Competitive durability** — no scheduled answer; revisit when
  Sprint 22 multi-user pivot closes.

---

## Calendar

The earliest realistic full-activation date assuming the operator moves
on G2 + G3 immediately:

- **G2 lawyer review** — 2 weeks (counsel turnaround)
- **G3 first publisher opt-in** — 4-8 weeks after G2 closes
- **G5 dispatch verdict** — closeable today (window has been open since Sprint 17)
- **G6 autoresearch verdict** — closeable today if the operator has run mutations
- **G7 compounding demo** — ~Nov 2026 earliest
- **G8 Loop 3 unlock** — gated by G6 + ≥500 graded outcomes; ≥3 months out

**Bottom line:** of the 8 gates, **3 can close this week** (G4, G5, G6),
**2 close this month with effort** (G2, G3), **1 closes in late 2026** (G7),
**1 closes Q1 2027 at the earliest** (G8). G1 is already closed.
