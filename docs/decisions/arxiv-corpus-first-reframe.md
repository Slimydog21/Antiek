# arXiv corpus-first reframe + the source-onboarding kill-gate (2026-05-31)

**Decision date:** 2026-05-31 (egghead audit + operator-delegated reframe of `~/specs/antiek-arxiv-ingest/`).
**Status:** ✅ Partially shipped. **P3 — the wired corpus-value source-onboarding kill-gate — merged to `main` as `abde67e` (PR #42).** The cross-source rights chokepoint (P1) is built + green but HELD on `caffen/reframe-p1`, unmerged, pending the §9.0 reconciliation below.
**Owner:** arXiv-ingest reframe (post-PR-#34 ship). Architecture: `~/specs/antiek-arxiv-ingest/ARCHITECTURE-corpus-reframe.md`; run ledger: `~/specs/antiek-arxiv-ingest/.caffenagent/reframe-run.json`.
**Gate:** the reframe DEMOTES the researcher-payout headline; it does **not** close G9 (counsel/KYC). G9 stays open and is now even less load-bearing — payouts are a dormant, gated, symbolic future feature; the SPR-06 accrual ledger is preserved but surfaces no money rail.

## The decision

The arXiv initiative was re-founded from *"ad-monetized arXiv reading → researcher payouts"* to **"a legally-clean, continuously-synced arXiv corpus feeding Antiek's Research / Read / Write / Speak products."** The payout headline is dead on three independent structural walls (egghead audit, 2026-05-31):

1. **License** — only ~10% of arXiv carries a redistributable CC license (Common Pile, from arXiv's own S3: ~321k / 3.05M).
2. **ToU (dispositive, census-independent)** — arXiv's API ToU bars serving e-prints from your servers regardless of license and mandates link-back. No census number moves this wall.
3. **Economics** — ~$0.05–0.30 / paper / yr to a researcher after split, below Stripe minimums; the reference class (Academia.edu / ResearchGate) is unprofitable.

The compliance substrate that already shipped (PR #34: host-global rate governor, deny-by-default T1/T2/T3 serve gate, source-agnostic tiering) is genuine craft and is **preserved and generalized**. Payouts demote; **no payout code is deleted.**

## What shipped — P3 (finding #2: the wired kill-gate)

PR #42 (`abde67e`) replaces the spec's PROSE "measure before build" stop-rule with a **machine-checked CI gate**:

- `tools/source_census.py` — the `SourceCensus` JSON contract + PROVISIONAL corpus-value thresholds (metadata-complete ≥95% / linkback-resolvable ≥99% / dedup-overlap <20%; `t1_pct` / `open_pct` are REPORTED but **advisory** — the corpus's worth is feeding products, not ad %) + the gate predicate. Deny-by-default: empty / NaN / out-of-range / missing-field / non-object census entries all FAIL at parse or predicate.
- `tools/lint/source_gate.py` — the CLI gate (exit 1 to BLOCK; fails closed on an invalid census), wired into `.github/workflows/ci.yml` as a **no-op until a census exists**, enforcing the moment one lands. It blocks onboarding any source AFTER arXiv below the bar.
- `tests/test_source_gate.py` — 25 tests. The arXiv reference source is THRESHOLD-exempt but still structurally gated (`total>0`, finite) and unique. An independent verifier-critic returned FIX-BEFORE-SHIP; all findings were sharpened (NaN-reject, narrowed-but-visible arXiv exemption, CI-wired, range/non-object reject) and re-verified.

It is CI/CLI-only — no prod-runtime surface imports it, so there is **no backend deploy**; the gate is live as a `main` CI step (the #42 merge CI run was green).

## What is deferred — P3b (see `engineering_deferrals.md` D17)

The census **producer** — `compute_source_census(con, source)` over the real corpus (via the one `substrate.dedup` identity ladder) + the committed `reports/source_census.json` — is operator-gated: it needs the prod corpus + an **unbanned arXiv ingest window**. The gate is a no-op until then; the thresholds are PROVISIONAL until calibrated on the first real census.

## What is HELD — the §9.0 three-front reconciliation

P1 (a unified `substrate/rights/register.py::register_source_document` chokepoint that `register_book` delegates to — reframe finding #5) is built and green (the full 5100-test suite passes) on `caffen/reframe-p1` (`03b0aaa` = `b25b275` chokepoint + `f3ef912` sharpen + `03b0aaa` delegation) but is **deliberately NOT merged.** It collides with two other parallel §9.0 efforts that both rewrite `substrate/graph/search.py` + the content_class vocabulary:

- **`personal-lane/integration`** — adds the 4th rights state `personal_reading` (owner-read only; non-servable / non-attributable / non-trainable) + connector deny-by-default. Its operator gate-actions (G10 / G11 / G12) are already on `main`.
- **PR #38** (`aff-spr-03-sec90`) — "§9.0 servability **polarity** unification", STAGED behind the G2 legal gate.

P1's `VALID_CONTENT_CLASSES` was built off `ebfb36a` and lacks `personal_reading`, so it is forward-incompatible with a post-personal-lane `main` (it would raise on a `personal_reading` document). Opening it as a third competing §9.0 PR was therefore declined.

**Reconciliation (operator-sequenced):** land the §9.0 rights work first, then rebase `caffen/reframe-p1` to adopt `personal_reading` into the registrar vocabulary and fold the chokepoint over personal-lane's `graph/ops.py` write-side default (one home for cross-source deny-by-default). P2 (the legacy NULL-content_class grandfather flip in `search.py` — still open even on personal-lane's gate) and P5 (chunk-level provenance for citation) build on the reconciled base. The full plan is `~/specs/antiek-arxiv-ingest/.caffenagent/reframe-run.json` → `RECONCILIATION_REQUIRED_2026_05_31`.
