# Operator-only gate actions

**Last touched 2026-07-02 (doc-truth pass — stale pointers/counts fixed; per-gate sections retain their original snapshot dates).**

The audit identified the binding gates blocking activation of substrate that
is tracked live in the quick-status table below (gates have been appended
since the original eight; the table, not this sentence, is the register) —
is already shipped in code. **Engineering cannot close these gates.** Each one
requires the operator (or an external party) to act. This document is the
checklist with minimum inputs and an explicit owner.

## Quick status (skip to detail below)

| Gate | Status | What it blocks |
|---|---|---|
| G1 retrieval-time legal gating | ✅ closed | — |
| G2 lawyer review | ❌ open | **All Stripe payouts; all external email; Trust Center publication** |
| G3 first publisher opt-in | ❌ open (gated by G2) | Stripe activation; first cohort outreach |
| G4 Lemon UI verdict | ✅ closed 2026-05-23 | (overtaken by Werner brand) |
| G5 dispatch tier verdict | ✅ closed 2026-05-23 | substrate fix now landed; re-run after fresh traffic produces real signal |
| G6 autoresearch Wedge 1 verdict | ⏳ open | Phase 8 enforcing + Wedges 2-4 |
| G7 six-month compounding demo | ⏳ calendar (~Nov 2026) | Multi-user pivot Sprint 22 |
| G8 Loop 3 unlock criteria | ⏳ data-bound | RLM + SFT + hosted RL track |
| G9 arXiv researcher-payout counsel/KYC | ❌ open (counsel) | arXiv SPR-07/08 (researcher identity + KYC/payout); merged to main (`8c0132f`, `7ae2318`) |
| G10 Stripe Press §9.10 publisher opt-in | ❌ open (operator BizDev) | The ONLY servable path for any in-copyright Stripe Press title; until granted, every Stripe Press title is gated/personal-read, never servable |
| G11 X no-training constraint | ✅ enforced in code / ⏳ standing operator duty | Keeping ALL BYOK X content (`personal_reading`, `social_thread`) out of every training/RL export — X dev terms forbid training on X data |
| G12 Bernays per-title copyright-renewal check | ❌ open (operator, per-title) | Making any 1927–1930 Bernays title servable — the in-copyright titles must NEVER be relabeled to a servable class without a per-title US renewal-records check |
| G13 Auth diagnostic matrix | ✅ closed 2026-06-02 | Login failure triage now points to `docs/diagnostics/auth-failure-mode-matrix.md`; do not conflate Layer A transport with Layer B allowlist silence |

**The quick table above is the status summary.** G11 combines code enforcement
with a standing operator duty, so its coarse closed classification must never
erase the duty preserved in the raw status.

## Highest-leverage next action

**Send G2 to counsel** — single binding blocker for everything Stripe-related,
Trust Center publication, AgentMail custom-domain upgrade, and the entire §9.10
publisher cohort track. Inputs at the G2 section below.

## Second-priority action

**Run 5–10 real investigations on `https://antiek.ai/`** — produces fresh data
for the §14.4 measurement, the §13.4 compounding-curve demonstration (G7), and
the §15.3 voice-latency assessment. Substrate is healthy now (the May 17-18
read-only-filesystem outage is resolved); operator usage is the bottleneck.

The binding gates, with their current state and the action required:

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

**Status:** ✅ CLOSED 2026-05-23
**Closure record:** `docs/decisions/g4-lemon-ui-verdict.md`

Rejected direct adoption of `@posthog/lemon-ui`; custom Lemon-flavored
primitives at `apps/reading/src/components/lemon/` chosen instead, with
Werner / Antarctic palette + sun-yellow outline per `de52534`. The TipTap
notebook editor ships against the custom primitives. The gate was overtaken
by the 2026-05-21 brand-redesign decision; this closure makes that
explicit.

---

## G5 — Dispatch tier-differentiation measurement verdict

**Status:** ✅ CLOSED 2026-05-23 (provisionally, with re-open trigger)
**Closure record:** `docs/decisions/dispatch-tier-verdict.md` + follow-up at
`docs/decisions/g5-dispatch-tier-verdict-followup.md`

### What the 2026-05-23 audit surfaced

1. **First closure attempt** returned `insufficient_data` with empty table.
   The analyzer was reading `created_at` but the substrate emits `emitted_at`.
   Fixed in commit `eeaf084`.
2. **Second attempt** returned `insufficient_data` with table populated:
   14 Hermes + 2 Opus synthesis calls, **zero verified** because production
   has never emitted a single `rubric.scored` event linked to a synthesis.
   `emit_rubric_scored` was test-only in the codebase.
3. **Self-grade fallback** (commit `38b13be`) had the analyzer read the
   synthesizer's own `implicit_recommendation` + `conviction_level` from
   `synthesize.delivered` events. New result: 13/14 + 2/2 verified, **zero
   passed** — every synthesis in the event log self-reported
   `insufficient_evidence` because chunk retrieval was failing with
   `OSError [Errno 30] read-only file system`.
4. **Filesystem investigation** showed the outage was bounded to
   ~2026-05-17 through 2026-05-18 and has since resolved. The substrate
   has been healthy since but no new investigations have been run on it.
5. **G5 architectural finding closure** (commit `7450ef1`): wired an
   inline `substrate/synthesis_rubric/` scorer into Loop 1's Phase 6 exit.
   Every synthesis from that commit forward emits a real `rubric.scored`
   event linked back via `synthesis_id`. The §14.4 measurement gate is
   wireable now.

### Re-open trigger

When the operator has run ≥5–10 real investigations on the now-healthy
substrate (after 2026-05-23), re-run:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@167.235.202.98 \
  '/opt/antiek/.venv/bin/python -m tools.dispatch_tier_verdict \
   --events /home/antiek/.antiek/research_events/ --since 2026-05-23'
```

Expect a real verdict (`keep_opus_primary` or `flip_to_hermes_primary`)
based on actual rubric scores, not the self-grade fallback.

The substrate fix is real and load-bearing — without it the §14.4 gate
would stay un-closeable forever. Until operator traffic populates fresh
events, the gate is provisionally closed against the broken-window
data with the substrate now ready for a clean re-measurement.

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

## G9 — arXiv researcher-payout counsel/KYC gate (SPR-07/08)

**Status:** ❌ OPEN
**Owner:** Operator + counsel
**Blocks:** The money-moving wave of the arXiv-ingest track — SPR-07 (researcher
identity + ORCID opt-in claim) and SPR-08 (KYC + Stripe Connect self-onboard
payout). Both are hard-blocked at the caffenagent run edge
(`~/specs/antiek-arxiv-ingest/.caffenagent/state.json`, status `BLOCKED-GATE`);
no autonomous code builds either until this closes. Distinct from G2/G3 — those
gate *publisher* payouts; this gates *researcher* payouts.
**Precondition:** The SPR-01 corpus census number (operator live-run of
`tools/arxiv_census.py` — network-gated; arXiv is still 429-rate-limited per the
ingestion-failures record).

### Inputs needed for counsel
- **GDPR lawful basis** for storing OpenAlex-derived author identity (ORCID /
  display name / byline position, `substrate/schemas/documents.py::EnrichedAuthor`)
  and for an ORCID-based opt-in claim flow. The SPR-06 accrual ledger keys
  `(arxiv_id, author_position)` and is internal-only — it records who is owed but
  *never contacts an author* (`substrate/payouts/ledger.py`, merged `8c0132f`).
- **arXiv API ToS on author-email use.** The SPR-09 contact guard is
  deny-by-default — *all* author-directed email is blocked until a claim exists
  (`substrate/payouts/contact_guard.py`, merged `7ae2318`).
- **KYC / tax obligations** for paying individual researchers (Stripe Connect
  self-onboard, SPR-08).

### Once closed
SPR-07 builds the ORCID-keyed claim flow over the existing `(arxiv_id,
author_position)` accrual ledger; SPR-08 wires KYC + Stripe Connect payout. The
internal accrual + tiered-serving + compliance substrate already shipped (arXiv
SPR-01..09 merged to main — `8c0132f`, `7ae2318`); only the money-movement is gated.

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

**Bottom line:** the quick-status table at the top is the live
closed/open register — a prose recount here drifted from its own table
within weeks (it said "8 gates" while the table held twelve). Per-gate
timing detail lives in the sections above.

---

## Operator Activities — Produce Traffic (cross-session breadcrumb)

**Engineering scope of the spec is essentially complete as of 2026-05-23.**
What's left is operator-bound action. Future-agent reading this section:
DO NOT propose more engineering until the bottlenecks below clear.

### Action queue, in priority order

1. **G2 — Send the lawyer the Kalshi-pattern template + Trust Center
   compliance copy.** Single binding blocker. Inputs above in the G2 section.
   Expected 2-week turnaround.

2. **Run 5–10 real investigations** on `https://antiek.ai/`. The substrate
   is healthy (the May 17-18 outage is resolved) but no fresh traffic has
   gone through since. Each investigation produces:
   - A `rubric.scored` event (substrate now emits this per commit `7450ef1`)
   - Data the §14.4 dispatch verdict re-runs against
   - Evidence-graph compounding toward G7's 6-month demonstration
   - Trajectory replay material for the operator-graded outcomes table

3. **G6 — Run ≥20 synthesizer prompt mutations** locally via
   `tools.prompt_autoresearch.runner`, pipe outcomes to
   `tools.prompt_autoresearch.verdict.compute_verdict`. Substrate ready.

4. **§15.3 — Rate the voice-interview latency 1-5** on a real interview.
   No infrastructure change needed; just run the interview surface end-to-end.

5. **D17 ingest — retrieval spot-check per connector** — after each live ingest
   batch passes `personal-lane.md` + `corpus_audit`, run
   `infrastructure/runbooks/retrieval-gate-closure.md` §2 (VSS +
   `GET /chunks` withhold). Halt ingest on failure. RG-06 verified 2026-06-02;
   `docs/decisions/retrieval-gate-closure.md`.

6. **MCP server external registration** — Claude Desktop registration per
   `infrastructure/runbooks/antiek-memory-mcp.md`. Single config-file edit.

7. **AgentMail custom-domain upgrade** — deferred per
   `docs/decisions/agentmail-custom-domain-deferral.md` until the same day
   as G2 closure (no point spending $20/mo on cosmetics for operator-only
   email).

8. **Re-publish Trust Center** with G2-cleared compliance copy — scaffold
   at `docs/trust_center_public.md` has `[OPERATOR + LAWYER]` brackets.

### After G2 + G3 close

These auto-cascade once G2 and G3 are checked:

- Stripe Connect real activation: `ANTIEK_STRIPE_PROVIDER=real` +
  `STRIPE_SECRET_KEY` on the VM. `RealStripeProvider` is shipped and tested.
- First-cohort publisher emails sent via AgentMail.
- Trust Center publication goes live (operator + lawyer paragraph fills).

### Continuous services on prod (no further setup needed)

- `antiek.service` — FastAPI + Loop 1 orchestrator. Now emits
  `rubric.scored` after every Phase 6 synthesis (§14.4 substrate fix).
- `antiek-continuous-research.service` — §7.3/§7.4 daemon. Scans
  evidentiary gaps every 60s, spawn-budgeted at $5/day per §16. Live since
  2026-05-23T16:35Z.

### §9 provenance + economics, surfaced — status (Product Depth SPR-10, 2026-05-26)

DOCUMENTATION ONLY — this note closes/changes NO gate. **G2 and G3 stay
OPEN.** SPR-10 surfaced the §9 layer honestly, up to the gate, never across
it:

- **Provenance ("whose work grounds this").** A servable source's named-source
  render now carries the IP holder ("from *Title*, published by X") where one
  is resolved; a null owner stays honest ("unknown owner", never invented).
  Surfaced in `compute_attribution_for_synthesis` (document_ip_holders +
  status), the `GET /attribution/synthesis/{id}` response, and the
  `GET /chunks/{id}` endpoint.
- **§9.0 gating on the surfaced path.** A `restricted_pending_opt_in` document
  no longer surfaces into an attribution-triggering synthesis — no share, no
  title, no owner (closed a real leak; proven by
  `tests/test_provenance_economics_surfaced.py`). The chunk endpoint withholds
  a restricted source's owner with its body (protected attribution).
- **Accrual view (`apps/reading/src/modes/Economics/AccrualView.tsx`).** Shows
  what WOULD be owed per contributor (default Option B per §9.3) + the escrow
  accrual, every figure labelled not-yet-paid; today's balance is honestly
  $0 (Phase 1 monetisation is the §9.0.1 token model, not IP payouts). Opt-in
  only: a `pre_onboarded` holder reads as escrow-eligible-on-opt-in, never
  "money waiting" against an unconsenting rights holder.
- **NO money path.** There is no disburse / payout / Stripe / publish path on
  any surfaced module; the one money-adjacent control ("Try a payout") refuses
  with the open-gate reason (G2 + G3) and moves nothing. Verified against a
  live attempt (test), not by inspection alone.

**No-key behaviour:** without provider keys, attribution can't compute → the
accrual view shows the honest no-result state (AIActionFailure: "the model
provider isn't configured"), never a fabricated owed amount.

**What the keyed use-gate (full first-run capture) needs — OPERATOR-bound:**
real provider keys set on prod (the same `register_default_providers`
credentials gate the rest of the AI is on, per the 2026-05-25 UI note). With
keys: read a synthesis → see whose work grounds a claim → open the accrual
view → see "would be owed, not yet paid" → attempt a payout → get the honest
G2/G3 refusal. The disbursement that this view refuses stays gated G2 (lawyer)
+ G3 (publisher opt-in) above — SPR-10 did not touch either.

### Living Roadmap — the four-product interaction layer shipped to prod (2026-05-28)

DOCUMENTATION ONLY — this note closes/changes NO gate. **G2, G3, G7, and G8
stay OPEN.** The Living Roadmap run (15 sprints) shipped to `main` and prod and
was verified live; it turned the AI on across the four surfaces and built the
new interaction primitives, all behind the existing gates.

- **Merged + deployed.** PR #16 (`a94d357`, the 15-sprint chain) + PR #15
  (`d463c9e`, the D13 reconcile) are on `main`. Backend deployed via
  `ansible-playbook playbooks/deploy.yml --skip-tags frontend`; frontend
  auto-deployed via Cloudflare Pages. **Verified live:** prod `/health` reports
  `schema_version: 23` (was 16 on the pre-run base `76c2002` — the dispositive
  new-code marker) and `antiek.ai` serves HTTP 200.
- **What's live now.** Research (home + plan-mode), Read (library + reader +
  talk-to-book + meta-reading + personal-doc-space), Write (block-canvas →
  outline → X-ray), and Speak (public/private feed + AI-graded payout +
  compounding interviewer + biography template). Per-sprint rationale:
  `docs/decisions/spr-09-write-canvas-xray-rewrite.md`,
  `docs/decisions/spr-10-ai-graded-payout.md`,
  `docs/decisions/spr-11-biography-template-not-graph.md`,
  `docs/decisions/spr-13-personal-space-and-filing.md` (+ the SPR-0x docs).
- **AI live on prod (observed).** `/health` shows 5 registered dispatch
  providers (`anthropic, deepseek, hermes, openrouter, xiaomi`) — the
  credentials gate the §9/SPR-10 note above treats as operator-bound is
  satisfied for dispatch, so the keyed first-run capture (read a synthesis →
  accrual view → honest G2/G3 payout refusal) is actionable now. (OpenAI/TTS
  key status not separately confirmed; absent it, voice TTS degrades honestly.)
- **Payout mechanism built BEHIND the gates.** Living Roadmap SPR-10 added the
  AI-graded interview payout (`substrate/speak/payout_verifier.py`): a
  verifier-shaped grader (honestly labelled a prompt-rubric, not a trained
  grader) routes a passing transcript's payout via §9 contribution measurement
  into ESCROW only — `release_payout` never calls `attempt_disbursement`, which
  still refuses pre-G2/G3. Requester-cannot-deny is structural. No money path;
  no gate touched.
- **Two PROPOSED resolutions await operator sign-off** (shipped behind visible
  "proposed — sign-off pending" banners, reversible): the auto-notebook concept
  (`docs/decisions/spr-06-auto-notebook-proposed.md`) and the meta-reading
  Research↔Read boundary (`docs/decisions/spr-08-meta-reading-boundary.md`).
  Ratify or redirect each; the build reverts to a soft default if withheld.

**New operator-discretion items from this run:**
- Mint the visual baselines for the new shell/home/mascot: `cd apps/reading &&
  npm run visualtest:update` (SPR-12 deferred this so it wouldn't enshrine a
  pre-fix render).
- Two PRE-EXISTING test flakes (NOT introduced here; flag to stabilize):
  `apps/reading/src/components/ai/aiActionsEventBridge.test.ts` (vitest, passes
  7/7 in isolation) and `tests/test_magic_link_auth.py::test_magic_link_rejects_tampered_token`
  (pytest, passes in isolation; the last-base64-char tamper on a timestamped
  token doesn't always change the signature).
- Deploy reminder: the backend deploys with `--skip-tags frontend` — the
  `deploy.yml` frontend play builds from the LOCAL working tree (so it inherits
  uncommitted parallel-session WIP); the frontend ships via Pages-from-`main`.

### Personal-Reading Lane — shipped to prod (2026-06-01)

DOCUMENTATION ONLY — this note changes NO money gate. The 10-sprint
Personal-Reading Lane (the §9.0 fix that adds a fourth rights state,
`personal_reading`: owner-readable, never served / attributed / trained) merged
to `main` as **PR #43 (merge `9aeb2c9`, `EVENT_SCHEMA_VERSION` 24→27)** and was
**deployed live** on 2026-06-01 (`ansible-playbook backup.yml` → R2, then
`deploy.yml`). Verified live at `https://api.antiek.ai/health`:
`schema_version: 27` + `build_sha: 9aeb2c9` (= `origin/main` tip).

- **Three operator gate-actions this lane added** are recorded above:
  **G10** (Stripe Press §9.10 opt-in), **G11** (X no-training standing duty),
  **G12** (Bernays per-title renewal check). All operator-only; the lane code is
  done.
- **The live-ingest steps are deferred** to an operator ingest window —
  `engineering_deferrals.md` **D17** (SPR-04 Gutenberg/archive.org · SPR-05 live
  PG · SPR-06 real Substack subscriptions · SPR-08 X BYOK live smoke). The lane
  is dormant-correct + auditable-empty on prod until then; go-live procedure is
  `infrastructure/runbooks/personal-lane.md` (audit-gated).
- **Retrieval spot-check after each connector ingest (RG-06, 2026-06-02):**
  after `corpus_audit` exits 0 for that batch, run
  `infrastructure/runbooks/retrieval-gate-closure.md` §2 — VSS @
  `attribution_eligible` must not return `personal_reading`; `GET /chunks/{id}`
  must withhold body. **Halt ingest** on failure (do not note-and-continue).
  Preflight lint + RG-05 tests: same runbook §0. Evidence:
  `docs/decisions/retrieval-gate-closure.md`.
- **Standing mechanical backstops** (no operator action): the
  `corpus_audit.py` lane checks (`third_party_servable`,
  `personal_reading_nonattributable`, `personal_reading_not_in_training`) + the
  two-sided serve gate (write-side deny-by-default `graph/ops.py`, read-side
  exclusion `graph/search.py`).
- The `test_magic_link_rejects_tampered_token` flake noted above is the same
  pre-existing order-flake this run also hit on CI — not introduced by the lane
  (0-line auth diff); belongs to whoever owns auth. (PRcrouch also re-ran a
  pre-existing `test_arxiv_audit` order-flake that fails on `main` itself; both
  point at the deferred suite-parallelization CI-infra task in
  `docs/decisions/ci-pytest-timeout.md`.)

### Reference docs for cross-session continuity

- `docs/operator_gate_actions.md` — this file. Update on every gate
  status change.
- `docs/decisions/` — one file per closed gate, named `gN-<slug>.md`.
- `docs/sprint_track_reconciliation.md` — resolves the master-spec
  Sprint 11→22 sequence vs the UI-redesign Sprint 0→12 sequence.
- `docs/trust_center_public.md` — public-facing scaffold; awaits G2.
- `infrastructure/runbooks/*.md` — deployment + activation flows.

---

## Personal-Reading Lane operator gate-actions (SPR-10, 2026-05-31)

These three are **operator-only** — engineering cannot close them. They are the
no-code asks that bound the personal-reading lane's lawful content. Each is
recorded here so a future agent does not try to "fix" it in code (the lane code
is already done; these are BizDev / legal / per-title facts only). The standing
mechanical backstops for the lane live in `substrate/corpus_audit.py` (the
`third_party_servable`, `personal_reading_nonattributable`, and
`personal_reading_not_in_training` checks) and the go-live procedure is
`infrastructure/runbooks/personal-lane.md` (audit-gated).

---

## G10 — Stripe Press §9.10 publisher opt-in

**Status:** ❌ OPEN
**Owner:** Operator (BizDev — phone/email Stripe Press / Stripe BizDev)
**Blocks:** Serving ANY in-copyright Stripe Press title. Until a §9.10 publisher
opt-in is granted, every Stripe Press title is **lane 2/3 only** (gated
`restricted_pending_opt_in`, or `personal_reading` for an owner-fetched copy) —
**never** a servable class.

The §9.10 publisher opt-in flow (the same pre-onboarded-escrow + opt-in-only
mechanism G2/G3 gate for the general publisher cohort) is the **sole servable
path** for an in-copyright Stripe Press book. The operator phones/emails Stripe
BizDev to request that opt-in; until it is granted and the publisher claims,
the title's `content_class` must stay gated or `personal_reading`.

**Read-only ≠ redistribution license.** "Free to read online" (e.g. *Poor
Charlie's Almanack* on Stripe Press's own site) is a read-only courtesy by the
publisher — it is **not** a grant of a redistribution license to Antiek. An
owner who reads it lands it `personal_reading` (their private reading, never
served to others); it does NOT become servable just because it is free to read
on the publisher's site. Only the §9.10 opt-in makes a Stripe Press title
servable.

### What would close it
A signed §9.10 publisher opt-in from Stripe Press + the publisher's claim
(the same `pre_onboarded → invited → claimed` flow as G3). On claim, the
specific opted-in titles may move from gated to `opt_in_licensed` (servable).
Record the date + the titles in `docs/decisions/g10-stripe-press-opt-in.md`.

---

## G11 — X (Twitter) no-training constraint

**Status:** ✅ enforced in code / ⏳ standing operator duty
**Owner:** Operator / agent (keep it standing — never relax it)
**Blocks:** Nothing today (no training/RL export exists); it is the **standing
constraint** that any future training/RL export MUST honour.

X's developer terms **forbid training on X data.** All BYOK X content the owner
ingests through their own X API key lands `content_class='personal_reading'`,
`document_type='social_thread'`, and MUST be excluded from **every** training /
RL export. This is enforced two ways and they must both stay true:

1. **In code (already done):** `personal_reading` is a member of
   `NON_TRAINABLE_CONTENT_CLASSES` (`substrate/constants.py`), and the standing
   audit check **`personal_reading_not_in_training`** (`substrate/corpus_audit.py`,
   SPR-10 M1.c) is the mechanical backstop — it scans every declared training/RL
   export surface (`TRAINING_EXPORT_TABLES`) and fails the corpus if any
   `personal_reading` document_id appears. It is a **forward-guard** today
   because no real training/RL export builder exists yet (verified
   2026-05-31). **The human-readable counterpart of that check is this entry.**
2. **Operator duty (standing):** the day a real training/RL export builder is
   built, that sprint MUST register its source table/view name in
   `substrate.corpus_audit.TRAINING_EXPORT_TABLES` (and only there) so the
   `personal_reading_not_in_training` check guards the live export — and the
   operator must confirm the audit still exits 0 before that export ships. Do
   not build an export that selects all of `documents` naively; that is the
   exact bug the check exists to catch.

BYOK X keys are encrypted at rest, scoped to the owning user, and never logged /
never in the event log (`runtime/byok/`); this entry is the no-training half of
that BYOK discipline.

---

## G12 — Bernays per-title copyright-renewal follow-on

**Status:** ❌ OPEN (per-title, only if the operator wants more Bernays titles servable)
**Owner:** Operator (per-title US copyright-renewal-records check)
**Blocks:** Making any additional (1927–1930) Bernays title servable.

The Edward Bernays corpus splits cleanly into public-domain (servable) and
in-copyright (never servable without a per-title check):

**Servable today — public domain, exact bases:**
- *Crystallizing Public Opinion* (1923) — US public domain; Project Gutenberg
  #61364. `content_class='public_domain'` with that basis.
- *Propaganda* (1928) — US public domain as of 2024-01-01 (95-year term elapsed).
  `content_class='public_domain'` with that basis.

**In-copyright — NEVER relabel to a servable class:**
- *Public Relations* (1945) — renewal **RE0000069553** → © through ~2040.
- *The Engineering of Consent* (1947/1955).
- *Biography of an Idea* (1965).

The rule: an in-copyright Bernays title may be `personal_reading` (an owner's
private reading) or gated, but it must **NEVER** be relabeled to a servable
class. If the operator wants any 1927–1930 Bernays title made servable (some may
have lapsed into the public domain depending on renewal status), the **gate is a
per-title US copyright-renewal-records check** (Stanford Copyright Renewal
Database / Catalog of Copyright Entries) confirming the title was not renewed.
Only a confirmed non-renewal moves a title to `public_domain` (servable); a
title with a live renewal stays gated/personal-read.

### What would close it (per title)
A per-title renewal-records check result recorded in
`docs/decisions/g12-bernays-renewal-<title-slug>.md`, with the renewal number
(or confirmed absence) and the resulting `content_class`. Until then the
in-copyright titles stay non-servable; the standing `corpus_audit`
`servable_without_basis` check fails go-live on any servable title lacking a real
basis.

---

## G13 — Auth diagnostic matrix for login failure triage

**Status:** ✅ CLOSED 2026-06-02
**Closure record:** `docs/diagnostics/auth-failure-mode-matrix.md`

Login failure triage now points to the auth failure-mode matrix
(`docs/diagnostics/auth-failure-mode-matrix.md`), which enumerates every
observed `failure_id` across three layers (A: transport, B: policy, OPS:
operations) with discriminant commands, expected outputs, and fix owners. The
matrix includes the impossibility lemma proving `B-POLICY-ALLOWLIST-SILENT`
cannot produce the "Failed to fetch" symptom — preventing Layer A/B
conflation in future triage. No operator action required; no product block.
