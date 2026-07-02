# Operator Actions — Living Index

**Audience:** every agent (Claude Code, future Claude variants, any
other LLM agent) that works in this repo. **Purpose:** a single
place to track work that is operator-only — work that engineering
substrate cannot execute on its own.

If you are an agent and you discover an operator-only blocker
while working, **append a new section to this file** following the
schema below. Do NOT remove sections; mark them closed instead.
Do NOT execute these actions yourself — flag them and stop.

This file is paired with:
- `docs/operator_gate_actions.md` — the original 8-gate framing
  (G1-G8) for Phase 2 activation
- `docs/phase2_execution_audit_v4_2026_05_23.md` — the current
  exhaustive audit (supersedes v3; v3 §7's item count is stale — at
  least three of its "unexecuted" items are verifiably shipped on main:
  the `/trust-center/*` routes in `interfaces/research/api/app.py`,
  `interfaces/research/api/creator_payouts.py`, and
  `substrate/ad_inventory/advertiser_onboarding.py`)
- `docs/sprint-breakdown.html` — canonical Phase 2 deliverable list

---

## Schema for a new entry

Every operator-only action follows the same shape:

```markdown
### OA-NNN — Short title

**Status:** OPEN | IN_PROGRESS | CLOSED | DEFERRED
**Owner:** Operator | Operator + counsel | Operator + bank | Operator + external firm
**Blocks:** What this prevents from shipping
**Surfaced by:** Agent name / session / commit SHA that identified this
**First flagged:** YYYY-MM-DD

#### What the operator needs to do

(specific steps; references to substrate code that's ready)

#### Inputs needed before acting

(what artefacts / decisions / context the operator needs assembled)

#### Once closed

(what artefact the operator commits to mark the action complete)

#### Cross-references

(spec sections + integration specs + prior gate docs)
```

`OA-NNN` is a stable identifier — never reused. New entries take the
next free number. Track the counter at the bottom of this file.

---

## Quick status table

| ID | Title | Status | Blocks | Owner |
|---|---|---|---|---|
| OA-001 | Lawyer review of Kalshi-pattern notification template (G2) | OPEN | All Stripe payouts; first publisher outreach | Operator + counsel |
| OA-002 | First publisher affirmatively opted in (G3) | OPEN | All Stripe payouts | Operator + publisher |
| OA-003 | Six-month operator-graph compounding demonstration (G7) | OPEN | Sprint 22 multi-user pivot | Operator |
| OA-004 | Loop 3 unlock criteria — five sub-gates (G8) | OPEN | All RLM + SFT + hosted RL | Operator |
| OA-005 | Autoresearch Wedge 1 ratification (G6 / §15.6) | AWAITING OPERATOR TEST | Phase 8 enforcing + Wedges 2-4 | Operator |
| OA-006 | Auth vendor selection (Clerk vs Supabase) | OPEN | Sprint 22 entire | Operator |
| OA-007 | Stripe Connect real activation (MockProvider → RealProvider) | OPEN | Sprints 23-24 entire | Operator + Stripe |
| OA-008 | External red-team firm engagement (Sprint 23-24 gate (c)) | OPEN | Sprints 23-24 entire | Operator + external firm |
| OA-009 | Phase 1 (Sprints 17-21) committed + pushed + deployed | PARTIALLY DONE | Phase 2 entire | Operator |
| OA-010 | Integration-revert pattern resolved | OPEN | Substrate → API → UI integration | Operator + infra |
| OA-011 | KMS keys provisioned in production | OPEN | Per-user encryption at rest | Operator + cloud |
| OA-012 | Postgres catalog deployed (DuckLake Stage 1) | OPEN | Sprint 22 substrate stage transition | Operator + DBA |
| OA-013 | Trust Center publicly published at antiek.ai/trust | OPEN | Sprint 22 §13.7 deliverable | Operator + ops |
| OA-014 | Segregated regulated escrow accounts opened | OPEN | §16.2 "no commingled escrow funds" | Operator + counsel + bank |
| OA-015 | First-cohort publisher notification emails sent | OPEN (waits on OA-001) | Sprint 19 first-cohort outreach | Operator + Resend |
| OA-016 | Three paying advertisers signed (Sprints 23-24 exit) | OPEN | Sprint 23-24 exit criterion | Operator (sales) |
| OA-017 | Legal counsel signoff on §9.5 KYC + 1099 posture | OPEN | Sprint 23-24 Phase 6 | Operator + counsel |
| OA-018 | Federation partner instance found (Sprint 30+ Thread 1) | OPEN | Sprint 30+ Thread 1 | Operator |
| OA-019 | SOC 2 PURSUE/DEFER decision recorded | OPEN | Sprint 25+ Phase 6 conditional | Operator |
| OA-020 | Sprint 18 retrieval-time gating production deploy verified | OPEN | Activation of substrate-side G1 close | Operator + ops |

**Total OPEN:** 19 (1 partially done, 1 awaiting operator test). One
entry is closeable today (OA-005); a few are achievable within weeks
(OA-001 → OA-002 → OA-015 chain); the longest-pole items (OA-003 G7
compounding, OA-004 G8 Loop 3) are ≥ 6 months out.

---

## Detailed entries

### OA-001 — Lawyer review of Kalshi-pattern notification template (G2)

**Status:** OPEN
**Owner:** Operator + counsel
**Blocks:** All Stripe payouts; first publisher outreach (OA-015)
**Surfaced by:** Phase 2 audit v1; binding per master-spec §15.9 + §9.0
**First flagged:** 2026-05-22

#### What the operator needs to do

The Kalshi-pattern notification template at
`substrate/ip_holders/__init__.py` (`NOTIFICATION_EMAIL_TEMPLATE`) and
the `ip_holders` state machine documented at §9.10 must be reviewed
by counsel **before any notification email sends**. Engage a copyright
+ commercial-speech-experienced firm; budget 2 weeks for turnaround.

#### Inputs needed before acting

1. Plain-English summary of the §9.10 architecture (pre-onboarded
   escrow, opt-in-only payout activation, costless 30-day opt-out,
   segregated regulated accounts).
2. The rendered template — produce by running:
   ```bash
   ./.venv/bin/python -c "
   from substrate.ip_holders import IpHolder, render_notification_email
   from datetime import datetime, timezone
   h = IpHolder(
     ip_holder_id='mit-press', display_name='MIT Press',
     contact_email='legal@mitpress.mit.edu',
     status='pre_onboarded', escrow_balance_usd=0.0,
     created_at=datetime.now(timezone.utc).isoformat(),
   )
   print(render_notification_email(h))
   "
   ```
3. Bartz v. Anthropic settlement context — $1.5B precedent that
   makes pre-payout exposure (takedown) materially less expensive
   than post-payout exposure (Bartz-level damages on a contemporary
   monetary transaction).
4. Hachette v. Internet Archive context — Second Circuit ruling
   killing the structural fair-use argument.

#### Once closed

Commit `docs/decisions/g2-lawyer-review.md` recording the date and
the lawyer's name + firm. Mark OA-001 status: CLOSED. Sprint 19
first-cohort outreach (OA-015) can then proceed.

#### Cross-references

- Master-spec §9.0, §9.10, §15.9
- Operator gate G2 (`docs/operator_gate_actions.md`)
- v3 audit §7 item #44, #45, #77

---

### OA-002 — First publisher affirmatively opted in (G3)

**Status:** OPEN
**Owner:** Operator (outreach) + publisher (decision)
**Blocks:** All Stripe payouts
**Surfaced by:** Phase 2 audit v1; binding per master-spec §9.0
**First flagged:** 2026-05-22

#### What the operator needs to do

After OA-001 closes, run the first-cohort notification flow:

1. Pre-onboard MIT Press / Cambridge University Press / Princeton
   University Press via `POST /publishers` (this only adds the
   `pre_onboarded` row — no email sent yet).
2. Transition each to `invited` via `POST /publishers/{id}/notify`
   (this is the operator action that sends the notification email).
3. Wait for at least one publisher to claim via
   `POST /publishers/{id}/claim`.
4. **First successful claim closes OA-002.**

Expected timeline: 4-8 weeks per cohort. Universities respond on
quarter-cycle. Avoid Big Five publishers in first cohort
(Hachette-v-Internet-Archive plaintiff group; aggressive litigation
postures).

#### Once closed

The `ip_holders.status = 'claimed'` row IS the closure artefact.
Mark OA-002 status: CLOSED. OA-015 closes simultaneously.

#### Cross-references

- Master-spec §9.10 first-cohort strategy
- Operator gate G3
- v3 audit §7 item #72

---

### OA-003 — Six-month operator-graph compounding demonstration (G7)

**Status:** OPEN (~Nov 2026 earliest)
**Owner:** Operator (publish + demonstrate)
**Blocks:** Sprint 22 multi-user pivot
**Surfaced by:** Phase 2 audit v1; binding per master-spec §13.4
**First flagged:** 2026-05-22

#### What the operator needs to do

Per §13.4: premature multi-user destroys the moat that multi-user is
supposed to monetize via graph contamination. Six months of
operator-graph accumulation showing the compounding curve is the
minimum demonstration period. Four criteria all need to be true:

1. **Investigation count:** ≥ 100 investigations completed in the
   production substrate.
2. **Cross-investigation reuse:** ≥ 20% of new investigations cite a
   chunk first ingested in a prior investigation (substrate
   compounding metric).
3. **Visible artifacts published:** ≥ 3 substantial research outputs
   (memo, chapter, brief) published under any byline from Antiek
   syntheses — the §9.0.1 / §13.4 growth-motion thesis.
4. **Peer-discovery signal:** ≥ 1 unsolicited inquiry from a peer
   asking what tool produced the published outputs.

#### Once closed

Commit `docs/decisions/g7-compounding-demonstration.md` with the four
metrics. Mark OA-003 status: CLOSED. Sprint 22 multi-user pivot can
then proceed (closes OA-006 dependency).

#### Cross-references

- Master-spec §13.4 (binding), §9.0.1, §15.9
- Operator gate G7
- v3 audit §7 item #70
- This is the single most upstream block on Phase 2

---

### OA-004 — Loop 3 unlock criteria (G8)

**Status:** OPEN (Q1 2027 earliest)
**Owner:** Operator (after substrate accumulation)
**Blocks:** All RLM + SFT + hosted RL work
**Surfaced by:** Phase 2 audit v1; binding per `docs/loop_3_unlock_criteria.md`
**First flagged:** 2026-05-22

#### What the operator needs to do

Five sub-gates, all five must clear:

1. Trajectory volume: ≥ N graded outcomes (likely ~500 per role)
2. SFT readiness: dataset shape validated; cleanup pipeline exists
3. Validated reward: reward function audit complete; correlates
   with operator judgment under blinded review
4. Open-weight justification: clear reason to fine-tune open-weight
   over continuing closed-weight routing
5. Eval headroom: clear margin between current performance and
   operator-acceptability target that fine-tuning could close

The substrate at `substrate/loop_3/unlock_gate.py` checks each. When
all five return True, `ANTIEK_LOOP_3_UNLOCKED=1` becomes valid.

#### Once closed

`ANTIEK_LOOP_3_UNLOCKED=1` env var set in production deployment.
Mark OA-004 status: CLOSED.

#### Cross-references

- `docs/loop_3_unlock_criteria.md`
- Operator gate G8
- v3 audit §7 cross-cutting block

---

### OA-005 — Autoresearch Wedge 1 ratification (G6 / §15.6)

**Status:** AWAITING OPERATOR TEST
**Owner:** Operator
**Blocks:** Phase 8 enforcing mode + autoresearch Wedges 2-4
**Surfaced by:** Phase 2 audit v1; binding per master-spec §15.6
**First flagged:** 2026-05-22

#### What the operator needs to do

The local-only prompt-autoresearch runner is at
`tools/prompt_autoresearch/`. The operator runs ≥ 20 mutations
against the synthesizer's golden traces and closes the gate with:

```bash
./.venv/bin/python -c "
from tools.prompt_autoresearch.verdict import compute_verdict, render_verdict_markdown
from <your-runner-results> import outcomes
v = compute_verdict('synthesizer', outcomes)
md = render_verdict_markdown(v)
print(md)
" > docs/decisions/autoresearch-wedge-1-verdict.md
```

The verdict module enforces the four-criterion Lutke-gap test:
≥ 20 mutations, ≥ 40% acceptance, ≥ 0.05 mean delta, no
sub-metric regression on grounding or sector vocab.

#### Once closed

If RATIFY → Phase 8 gate flips shadow → enforcing (Sprint 21).
If REJECT → Phase 8 stays unconditional; Wedges 2-4 fall off
roadmap. Both outcomes are defensible per §15.6.

#### Cross-references

- Master-spec §15.6
- Operator gate G6
- `tools/prompt_autoresearch/`

---

### OA-006 — Auth vendor selection (Clerk vs Supabase)

**Status:** OPEN
**Owner:** Operator
**Blocks:** Sprint 22 multi-user pivot entire
**Surfaced by:** Phase 2 audit v1; Sprint 22 §2 Phase 1
**First flagged:** 2026-05-22

#### What the operator needs to do

Sprint 22 names "auth (Clerk or Supabase)" but doesn't pick. The
two have materially different KYC properties + scope-mapping
ergonomics for the Antiek Memory MCP per-user resources. Pick one,
then:
1. Sign up to the vendor's account
2. Configure OAuth providers
3. Wire the callback endpoint into `interfaces/research/api/app.py`
4. Add the session middleware
5. Wire the sign-up/sign-in UI pages into `apps/reading/src/modes/Login/`

#### Once closed

Commit `docs/decisions/oa-006-auth-vendor.md` with the choice + the
sign-up date. Mark OA-006 status: CLOSED.

#### Cross-references

- Sprint 22 §2 Phase 1 in `docs/sprint-breakdown.html`
- v3 audit §7 items #1, #2, #3, #4, #5

---

### OA-007 — Stripe Connect real activation (MockProvider → RealProvider)

**Status:** OPEN
**Owner:** Operator + Stripe
**Blocks:** Sprints 23-24 entire (creator payouts; advertiser checkout)
**Surfaced by:** Phase 2 audit v1; gated on OA-001 + OA-002
**First flagged:** 2026-05-22

#### What the operator needs to do

Gated on OA-001 (lawyer review) + OA-002 (first publisher claim).
Once both close:

1. Set up the Stripe production account (live mode, not test).
2. Complete Stripe Connect onboarding for the platform.
3. Configure webhook endpoints + signing secrets.
4. Set `STRIPE_API_KEY` + `STRIPE_WEBHOOK_SECRET` in production env.
5. Flip the substrate config: `tools/stripe_connect/providers.py`
   currently defaults to `MockStripeProvider`; production wires
   `RealStripeProvider` once the API keys are available.

#### Once closed

A successful test transfer (against a fixture creator account in
live mode, then immediately reversed) is the closure proof. Mark
OA-007 status: CLOSED.

#### Cross-references

- Master-spec §9.5
- `tools/stripe_connect/payouts.py` (this session's `RevSharePayoutRouter`)
- v3 audit §7 items #30, #76

---

### OA-008 — External red-team firm engagement (Sprint 23-24 gate (c))

**Status:** OPEN
**Owner:** Operator + external firm
**Blocks:** Sprints 23-24 ship
**Surfaced by:** Phase 2 audit v1; Sprint 23-24 §1 callout gate (c)
**First flagged:** 2026-05-22

#### What the operator needs to do

The Sprint 23-24 §1 binding callout requires *"the anti-gaming
layer passes a documented adversarial review."* This is gate (c)
of the Phase 4 ads gate. The internal-baseline harness exists
(see `substrate/anti_gaming/red_team.py` + the report at
`docs/sprint23_red_team_internal_baseline.md`) but the binding
artefact must be filed by an external firm.

1. Engage a security-research firm (Trail of Bits / NCC Group /
   similar). Provide them:
   - `docs/sprint23_red_team_internal_baseline.md` (internal baseline)
   - `substrate/anti_gaming/` (the substrate under test)
   - `tools/stripe_connect/payouts.py` (verdict → payout integration)
2. They run their own adversarial review (typically strengthens
   the four attack classes + adds their own).
3. They file `docs/sprint23_red_team.md` per the template at the
   same path.

Budget: $15-30K for a focused 2-week engagement.

#### Once closed

`docs/sprint23_red_team.md` exists, filed by an external firm,
with verdict GO. Mark OA-008 status: CLOSED.

#### Cross-references

- Master-spec §9.2, §9.7
- Sprint 23-24 §1 callout gate (c)
- `docs/sprint23_red_team.md` (template — to be filled by firm)
- v3 audit §7 items #34, #35

---

### OA-009 — Phase 1 (Sprints 17-21) committed + pushed + deployed

**Status:** PARTIALLY DONE
**Owner:** Operator
**Blocks:** Phase 2 entire (Sprint 22 cannot start until Phase 1 ships)
**Surfaced by:** Phase 2 audit v1
**First flagged:** 2026-05-22

#### What the operator needs to do

Per `docs/sprint-breakdown.html` cover §1 status legend, Sprints 17-21
are documented as "scaffold landed locally · NOT committed · not yet
visible on the website." Since v1 audit, parallel commits have
landed many Sprint 17-21 features on `main` (continuous daemon, AI
sidecar, export formats, interview transcript pipeline, etc.) — so
this entry is now PARTIALLY DONE.

Remaining:
1. Verify all Sprint 17-21 substrate is on `main` (git log audit).
2. Run `ansible-playbook deploy.yml` for the Hetzner VM.
3. Verify `antiek.ai` + `api.antiek.ai` are serving the post-Sprint-21
   binary.

#### Once closed

A `curl https://api.antiek.ai/health` returning the expected
post-Sprint-21 shape + a `https://app.antiek.ai/marketplace` route
returning 200 (or whatever the deployed app's URL structure is)
constitutes proof. Mark OA-009 status: CLOSED.

#### Cross-references

- `docs/sprint-breakdown.html` cover § 1
- v3 audit §7 item #74

---

### OA-010 — Integration-revert pattern resolved

**Status:** OPEN
**Owner:** Operator + infrastructure
**Blocks:** Substrate → API → UI integration for every Phase 2 module
**Surfaced by:** Phase 2 audit v2 §6.2; observed across multiple sessions
**First flagged:** 2026-05-22

#### What the operator needs to do

Three tracked files keep getting reverted between agent sessions:
- `interfaces/research/api/app.py` — my API endpoint additions
  (`/trust-center` registry wiring, `/marketplace/snapshot`,
  `/me/payouts`, `/operator/advertiser-campaigns`,
  `/operator/payouts/dashboard`) never persist
- `tools/stripe_connect/__init__.py` — re-exports for `RevSharePayoutRouter`,
  `route_impression_revenue`, `export_tax_year` revert
- `apps/reading/src/App.tsx` — route registrations for new React
  modes revert

**Diagnosis:** parallel commits on the branch (sometimes 8+ between
sessions) include design-token sync work that touches these files;
those commits overwrite agent-session edits.

**What the operator needs to investigate:**
1. Is there a pre-commit hook or linter pass auto-rewriting these files?
2. Are the parallel commits coming from a script (the lostpixel /
   design-token / brand sync pipeline)?
3. Could the substrate edits be moved to NEW files (under new module
   names) that the parallel commits don't touch?

**Tactical workaround already deployed:** the session-substrate
work lives in NEW dirs (`substrate/quality_gate/`,
`substrate/voice_style/`, etc.) which survive the revert. The API
+ UI integration layer needs a similar architectural decoupling —
e.g., a new `interfaces/research/api/phase2_router.py` that mounts
a sub-router into the FastAPI app, where `app.py`'s only edit is a
single `app.include_router(phase2_router)` line that's less prone
to overwrite.

#### Once closed

A session can edit `app.py` (or the new sub-router) + commit + return
in a fresh session and find the edit still present. Mark OA-010
status: CLOSED.

#### Cross-references

- Phase 2 audit v2 §6.2
- v3 audit §7 item #75

---

### OA-011 — KMS keys provisioned in production

**Status:** OPEN
**Owner:** Operator + cloud provider
**Blocks:** Per-user encryption at rest (§13.6 Stage 1+ requirement)
**Surfaced by:** Phase 2 audit v1; binding per master-spec §13.6
**First flagged:** 2026-05-22

#### What the operator needs to do

The `KMSStubKeyProvider` at
`substrate/graph_per_user/key_provider.py` is production-shaped —
it accepts any AWS-KMS-compatible client at construction time. To
activate:

1. Pick a cloud KMS (AWS KMS / GCP Cloud KMS / HashiCorp Vault).
2. Provision a master key with the alias prefix `alias/antiek-graph-`.
3. Set the cloud credentials in production env vars.
4. Wire `KMSStubKeyProvider(client=boto3.client('kms'))` (or equivalent)
   into the per-user storage lifecycle in production.

#### Once closed

A successful `kp.generate_data_key(graph_id="test-graph")` call in
production that round-trips a wrapped key is the closure proof.
Commit `docs/decisions/oa-011-kms-deployed.md`. Mark OA-011 CLOSED.

#### Cross-references

- Master-spec §13.6
- `substrate/graph_per_user/key_provider.py` (this session)
- v3 audit §7 item #7

---

### OA-012 — Postgres catalog deployed (DuckLake Stage 1)

**Status:** OPEN
**Owner:** Operator + DBA
**Blocks:** Sprint 22 substrate Stage 0 → 1 transition
**Surfaced by:** Phase 2 audit v1; binding per master-spec §13.6
**First flagged:** 2026-05-22

#### What the operator needs to do

The DuckLake catalog primitive at `substrate/ducklake/catalog.py`
ships with `SqliteCatalogBackend` as a stand-in. Production wires
Postgres. To activate:

1. Provision a Postgres 16+ instance (Hetzner / RDS / Cloud SQL).
2. Run the catalog table migration (the schema is in
   `SqliteCatalogBackend.__post_init__`; port the DDL to Postgres).
3. Write a `PostgresCatalogBackend` that conforms to the same
   `CatalogBackend` Protocol.
4. Point `DuckLakeCatalog` at the new backend in production.

#### Once closed

A successful `catalog.register(user_id="test-user", db_path=...)` +
`catalog.lookup("test-user")` round-trip against Postgres is the
proof. Mark OA-012 CLOSED.

#### Cross-references

- Master-spec §13.6 substrate transition matrix
- `substrate/ducklake/` (this session)
- v3 audit §7 item #14

---

### OA-013 — Trust Center publicly published at antiek.ai/trust

**Status:** OPEN
**Owner:** Operator + ops
**Blocks:** Sprint 22 §13.7 deliverable
**Surfaced by:** Phase 2 audit v1; Sprint 22 Phase 7
**First flagged:** 2026-05-22

#### What the operator needs to do

The React Trust Center component at
`apps/reading/src/modes/TrustCenter/` exists; the route `/trust` in
`App.tsx` is un-gated (auth bypass for the public surface). What's
missing:

1. Verify the production deploy serves `/trust` (Cloudflare Pages or
   the operator's equivalent).
2. Verify that the `/trust-center` API endpoint reads from the
   live `substrate/trust_center/build_publication()` (this needs
   OA-010 resolved to keep the app.py wiring landed).
3. Make the `/trust` route reachable from `antiek.ai/trust` (or
   whatever the production domain is).

#### Once closed

A non-authenticated `curl https://antiek.ai/trust` returns the Trust
Center HTML. Mark OA-013 CLOSED.

#### Cross-references

- Master-spec §13.7
- v3 audit §7 item #22

---

### OA-014 — Segregated regulated escrow accounts opened

**Status:** OPEN
**Owner:** Operator + counsel + bank
**Blocks:** §16.2 "no commingled escrow funds" binding REJECT
**Surfaced by:** Phase 2 audit v1; binding per master-spec §16.2
**First flagged:** 2026-05-22

#### What the operator needs to do

Per §16.2: *"No commingled escrow funds. Cash only, segregated
regulated accounts at a real fiduciary institution. Mechanically
distinct from operating funds."*

1. Engage a fiduciary institution (Mercury / Brex / a regional
   bank with escrow services).
2. Open a segregated account specifically for IP-holder escrow.
3. Document the mechanical separation (account-number reference)
   in `tools/stripe_connect/accounts.py::segregated_account_ref`.

#### Once closed

A live segregated-account number recorded in production secret
storage + referenced by the operations log. Commit
`docs/decisions/oa-014-escrow-account.md`. Mark OA-014 CLOSED.

#### Cross-references

- Master-spec §16.2
- v3 audit §7 item #78

---

### OA-015 — First-cohort publisher notification emails sent

**Status:** OPEN (waits on OA-001)
**Owner:** Operator + Resend
**Blocks:** Sprint 19 first-cohort outreach
**Surfaced by:** Phase 2 audit v1; binding per master-spec §9.10
**First flagged:** 2026-05-22

#### What the operator needs to do

After OA-001 (lawyer review) closes:

1. Pre-onboard the first three publishers (MIT Press, Cambridge UP,
   Princeton UP) — see OA-002 step 1.
2. Configure Resend (or another transactional email provider) with
   a `noreply@antiek.ai` (or similar) sender domain verified via
   DKIM/SPF.
3. For each publisher, transition `pre_onboarded → invited` AND
   send the notification email via Resend.
4. The email payload is what counsel reviewed in OA-001.

#### Once closed

`ip_holders` rows for the three universities are in `invited` state
with `notification_sent_at` timestamps populated. Mark OA-015
CLOSED.

#### Cross-references

- Master-spec §9.10 first-cohort sequencing
- v3 audit §7 item #73

---

### OA-016 — Three paying advertisers signed (Sprints 23-24 exit)

**Status:** OPEN
**Owner:** Operator (sales motion)
**Blocks:** Sprints 23-24 exit criterion ("≥ 3 paying advertisers, monthly run-rate > $5K")
**Surfaced by:** Phase 2 audit v1; Sprint 23-24 §4 exit criterion 2
**First flagged:** 2026-05-22

#### What the operator needs to do

Per Sprint 23-24 Phase 5: *"Manual sales motion for the first wave
of advertisers. Vertical SaaS, consulting firms, recruiting
platforms targeted by topic. Operator-driven; tooling stays light."*

1. Identify vertical SaaS + consulting + recruiting prospects whose
   target audience matches Antiek's research-reader profile.
2. Run manual sales conversations.
3. Close ≥ 3 paying advertisers at a combined monthly run-rate >
   $5K.

#### Once closed

Three `advertiser_campaigns` rows in the substrate with `status =
'active'` and aggregate `daily_budget_cents × 30 ≥ 500_000`. Mark
OA-016 CLOSED.

#### Cross-references

- Sprint 23-24 §2 Phase 5 + §4 exit criterion 2
- v3 audit §7 items #40, #41

---

### OA-017 — Legal counsel signoff on §9.5 KYC + 1099 posture

**Status:** OPEN
**Owner:** Operator + counsel (possibly same counsel as OA-001)
**Blocks:** Sprint 23-24 Phase 6
**Surfaced by:** Phase 2 audit v1; Sprint 23-24 §4 exit criterion 6
**First flagged:** 2026-05-22

#### What the operator needs to do

Per §9.5: *"KYC + 1099 reporting + ToS: 1-2 months of compliance
work alone, depending on jurisdiction. The operator is in Saudi
Arabia; Antiek as a US-incorporated entity simplifies some of this
but adds complexity to the operator's tax situation."*

1. Engage counsel with US tax + KYC experience.
2. Review the Stripe Connect KYC flow + the 1099 reporting trigger
   (any creator above the §9.5 $10/mo threshold).
3. Sign off on the Terms of Service for creator accounts.

#### Once closed

Commit `docs/decisions/oa-017-kyc-1099-signoff.md` with counsel's
name + firm + date. Mark OA-017 CLOSED.

#### Cross-references

- Master-spec §9.5
- v3 audit §7 items #44, #45

---

### OA-018 — Federation partner instance found

**Status:** OPEN
**Owner:** Operator
**Blocks:** Sprint 30+ Thread 1 (federation)
**Surfaced by:** Phase 2 audit v1; binding per Sprint 30+ §1 callout
**First flagged:** 2026-05-22

#### What the operator needs to do

The federation substrate at `substrate/federation/` is ready
(signed-resource-pull protocol, sign/verify, slice negotiation).
What's missing is a partner instance — another organization running
Antiek (or an Antiek-protocol-compatible substrate) willing to
negotiate a slice exchange.

1. Identify candidate partner organizations.
2. Negotiate the slice exchange terms (topic_scope, license, key
   exchange).
3. Exchange verifying-key fingerprints with the partner.
4. Pin their key in the partner's substrate registry; they pin
   yours.

#### Once closed

A successful first slice exchange documented in
`docs/decisions/oa-018-federation-first-exchange.md`. Mark OA-018
CLOSED.

#### Cross-references

- Sprint 30+ §1 callout + Thread 1
- `substrate/federation/` (this session-adjacent)
- v3 audit §7 items #60, #61, #62, #63

---

### OA-019 — SOC 2 PURSUE/DEFER decision recorded

**Status:** OPEN
**Owner:** Operator
**Blocks:** Sprint 25+ Phase 6 (conditional)
**Surfaced by:** Phase 2 audit v1; binding per master-spec §13.7
**First flagged:** 2026-05-22

#### What the operator needs to do

Per §13.7: *"SOC 2 Type II becomes relevant later ONLY if Antiek
ever enters enterprise procurement workflows."* The default verdict
is DEFER unless ≥ 1 enterprise deal is blocked on SOC 2.

1. Review current enterprise procurement pipeline (likely zero).
2. Decide PURSUE or DEFER.
3. Commit `docs/soc2_decision.md` filled in per the template.

#### Once closed

`docs/soc2_decision.md` populated with the decision + cited signal.
Mark OA-019 CLOSED.

#### Cross-references

- Master-spec §13.7
- `docs/soc2_decision.md` template
- v3 audit §7 item #53

---

### OA-020 — Sprint 18 retrieval-time gating production deploy verified

**Status:** OPEN
**Owner:** Operator + ops
**Blocks:** Activation of substrate-side G1 close (binding per §15.9)
**Surfaced by:** Phase 2 audit v3 §1; G1 substrate closed but deploy unverified
**First flagged:** 2026-05-23

#### What the operator needs to do

The retrieval-time policy_tag gating substrate is shipped at
`substrate/graph/search.py` (PRIVILEGED_POLICY_TAGS +
RESTRICTED_CONTENT_CLASSES). G1 in the operator-gate-actions doc is
marked CLOSED at substrate level, but the §15.9 binding *"in
production"* clause requires verifying the deployed binary runs the
gating SQL.

1. SSH to the production VM.
2. Run a synthetic retrieval test with a `restricted_pending_opt_in`
   document and policy_tag = `attribution_eligible`.
3. Verify the SQL excludes the restricted document.
4. Commit `docs/decisions/oa-020-retrieval-gate-deployed.md`.

#### Once closed

Mark OA-020 CLOSED. Combined with OA-002 closing, this clears the
Sprint 18 legal gate for Stripe Connect activation.

#### Cross-references

- Master-spec §15.9 binding clause
- `substrate/graph/search.py`
- v3 audit §7 item #71

---

## Appending new entries — for future agents

When you (any agent) discover a new operator-only blocker:

1. Check the quick-status table above for duplicates.
2. Assign the next free `OA-NNN` (current counter: **OA-020**;
   next free: **OA-021**).
3. Fill in the schema at the top of this file.
4. Add a row to the quick-status table.
5. Bump the counter line below.
6. Commit alongside the change that surfaced the blocker so the
   commit message can reference the OA-NNN.

**DO NOT execute these actions yourself.** They are operator-only
by design. Flagging is the substrate-side contribution; closure is
not.

---

**Counter:** next-free OA = OA-021. Last updated: 2026-05-23 by
the Phase 2 audit v3 session.
