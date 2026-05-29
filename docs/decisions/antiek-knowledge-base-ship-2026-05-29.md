# Antiek Knowledge Base — shipped to production (2026-05-29)

**Date:** 2026-05-29
**Branch:** `akb/ship` → `main` (PR #18 `af3ed16`, then caddy follow-up PR #19 `5413fdc`)
**Source spec:** `~/specs/antiek-knowledge-base/` (htmlspec; executed via `/caffenagent`)
**Status:** Live in production. `origin/main` at `5413fdc`; backend deployed to the Hetzner VM and verified live; frontend live on Cloudflare Pages. **No operator gate closed.**

## What this doc records — and why it has to exist

A future agent reading `acquisition/openaccess/`, `acquisition/arxiv/`,
`substrate/ad_inventory/auction_*.py`, `tools/verify_ad_economics.py`, and the
SPR-09 `/library` + `/api/ad/*` routes will find a substantial, live
ad-economics + rights-aware-corpus system and reasonably wonder: *is money
moving?* The answer this document fixes in place: **no.** The mechanism is
built, deployed, and verified — and it is deliberately wired to disburse
**$0** while G2 and G3 stay open. The live ad surface is not active payouts;
do not mistake one for the other.

## What shipped

Two tracks landed together — rights-aware corpus acquisition, and the
all-window per-second ad-economics mechanism. Each sprint was built, critiqued,
and sharpened (≥1 round) in its own worktree, then merged `--no-ff` onto
`akb/integration`; that branch was rebuilt as `akb/ship` (with the post-merge
fixes below) and merged to `main`.

| Sprint | Delivers | Merge (on `akb/integration`, all in `af3ed16`) |
|---|---|---|
| SPR-01 | Public-domain corpus ingestion (Gutenberg + archive.org) | `ac98215` |
| SPR-02 | arXiv ingestion + per-paper license capture | `3b1df6e` |
| SPR-03 | Open-access aggregator connectors (OpenAlex/Unpaywall/PMC/DOAJ) + shared license core | `1968d32` |
| SPR-04 | Monetization eligibility + attribution trust | `f034c4e` |
| REM-CC0 | Remap CC0 → `public_domain`, source-declared CC off `opt_in_licensed` | `bb42670` |
| SPR-05 | Per-second frame-attention engine (accrual + house seconds) | `25f2151` |
| SPR-06 | App-shell restructure (bottom nav · igloo home · Werner waddler) | `4bdf827` |
| SPR-07 | All-window Times-Square ad border | `8b3094a` |
| SPR-08 | Corpus-quality gate + cross-source dedup + ingest orchestrator | `472143f` |
| SPR-09 | Library + reader inside the ad border (`/library`, `/api/ad/*`) | `51c188d` |
| SPR-10 | Axon-style learned ad auction (features/scorer/ranker/A·B/retrain runbook) | `046200b` |
| SPR-11 | End-to-end per-second ad-economics verification (capstone) | `a5667fe` |

Per-sprint detail (milestones, gate results, critic rounds) lives in the run
ledger at `~/specs/antiek-knowledge-base/.caffenagent/run-ledger.md` — not
reproduced here.

## The load-bearing invariant: built, verified, disbursing nothing

The capstone (`tools/verify_ad_economics.py` + `tests/test_ad_economics_e2e.py`)
composes the real chain — auction-priced window → per-second frame attention →
eligibility filter → accrual → escrow → trace → the real
`contributor.attempt_disbursement` — over a prod-shaped fixture corpus, and
asserts the disbursement gate **raises `DisbursementBlocked`**. It proves the
negative: no Stripe path is imported or invoked, and the run reconciles to the
cent with $0 leaving escrow. `substrate/ad_inventory/payout.py` and
`tools/stripe_connect/` are untouched by this work. G2/G3 remain the sole
gate on any payout, exactly as `operator_gate_actions.md` describes.

## Verified live

After the backend deploy, the SPR-09 routes answer from the backend (not the
SPA fallback) and are correctly auth-gated: `GET /library`, `GET /api/ad/fill`,
and `POST /api/ad/frame-telemetry` each return `401 operator_auth_required`
JSON for an unauthenticated caller (deny-by-default per §9.0). `/health`
reports the provider set. The frontend serves a fresh Cloudflare Pages build.

## Post-merge fixes folded into the ship

- `6068ced` + `d6e1708` — `fix(§14.4)`: scope the research-tier override off
  the schema default so the Opus synthesizer isn't silently displaced; regen
  generated types + update the tier-default contract test.
- `45baf8c` — `fix(ci)`: declare `hypothesis` as a dev dependency (the SPR-04
  property suite aborted CI at collection without it).
- `13cd246` (PR #19, `5413fdc`) — `fix(caddy)`: proxy SPR-09 `/library` +
  `/api/ad/*` to uvicorn; they were being served the SPA. See
  `docs/decisions/deploy-from-matching-checkout.md` for the deploy-hygiene
  finding this surfaced.
- `7db5d88` — SPR-11 test made order-independent (PRcrouch Phase II): the
  no-stripe-import check scanned process-global `sys.modules`, which sibling
  stripe suites pollute; it now probes a fresh subprocess. Stronger, not
  weakened — the invariant (the harness imports no `tools.stripe_connect`) is
  the same; the verification no longer depends on suite ordering.

## What is explicitly NOT closed

- **G2 (lawyer review) and G3 (first publisher opt-in)** stay ❌ open. This
  ship changed neither, by design. All payouts remain blocked.
- **No engineering deferral (`engineering_deferrals.md` D1–D14) closes.** D7
  (Sprint 25+ programmatic ads at scale) is the nearest neighbour but is gated
  on D1 (multi-user) + a live creator cohort; AKB shipped the *mechanism*, not
  the scale activation, and touches neither unlock condition.

## Files (entry points; not exhaustive)

- `acquisition/openaccess/{openalex,unpaywall,doaj}.py`, `acquisition/arxiv/` — SPR-02/03 acquisition
- `substrate/ad_inventory/auction_{features,model,ranker}.py` — SPR-10 learned auction
- `tools/verify_ad_economics.py`, `tests/test_ad_economics_e2e.py` — SPR-11 capstone harness
- `infrastructure/runbooks/ad-economics-verification.md` — operator runbook + recorded report
- `interfaces/research/api/{library,ad_routes}.py` — SPR-09 routes (registered in `app.py`)
