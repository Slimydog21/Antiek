# Error-seam selection — Ousterhout Ch. 10 "define errors out of existence" (AOD SPR-03)

**Date:** 2026-07-01. Data-driven from SPR-01 `ranking.json` + SPR-02 `leaks.json`,
then hand-confirmed. Error-proneness score = (raise + except AST nodes) ×
SPR-01 `rank_score`, over unfenced `kind=normal` modules.

## Top error-prone unfenced seams (score)

| score | raise | except | rank_score | module |
|------:|------:|-------:|-----------:|--------|
| 3.697 | 6 | 2 | 0.462 | `substrate/graph/ops.py` — **SPR-04 owns it** (file-disjoint) |
| 2.713 | 3 | 8 | 0.247 | `substrate/graph/retrieval_substrate.py` |
| 2.655 | 5 | 8 | 0.204 | `substrate/graph/insight_question.py` |
| 1.694 | 3 | 2 | 0.339 | `substrate/graph/search.py` |
| 1.535 | 2 | 6 | 0.192 | `substrate/context_pack/knowledge_reuse.py` |
| 1.314 | 3 | 18 | 0.063 | `substrate/graph/rlm_tools.py` |
| 1.014 | 4 | 0 | 0.254 | `substrate/rights/register.py` |
| 0.908 | 1 | 4 | 0.182 | `substrate/source_throttle.py` |

## Selected seams (all category-(a) definable-out, all unfenced)

One coherent Ousterhout move across three sites: **a request for ≤0 results is a
defined empty result, not an error.** Each module already returns the same empty
shape for a sibling condition (empty document-scope / empty prompt), so this
*removes an inconsistency* rather than inventing a new behavior.

| # | seam | error removed | defined behavior |
|---|------|---------------|------------------|
| 1 | `graph/search.py` `search()` `top_k<1` | `ValueError("top_k must be >= 1")` | returns `{query, top_k, results: [], node_matches: []}` |
| 2 | `graph/retrieval_substrate.py` `DuckDbVssSubstrate._vss_query()` `top_k<1` | same `ValueError` | same empty result (the vss-active path — must match `search()`, which the brute-force + fallback paths already use) |
| 3 | `books/curate.py` `curate_reading_list()` `limit<1` | `ValueError("limit must be >= 1")` | returns `[]` (already the empty-prompt behavior) |

The two retrieval paths (`search()` for brute-force/fallback, `_vss_query()` for
vss-active) are changed together so a ≤0 top_k behaves identically regardless of
whether the HNSW index is loaded — otherwise the redesign would leave an
observable difference between backends.

## Must-stay rejects (fairness #2 — recorded so the selection is defensible)

These raises are genuine precondition/programmer/system errors, NOT definable-out:

- `graph/search.py` / `retrieval_substrate.py` / `curate.py` — `EmbeddingModel.encode returned N dims != model.dimension` → a broken model **contract** (programmer error); a caller cannot recover, must fix the model. Keep.
- `rights/register.py` — all four raises are documented intentional guards: the `content_class` typo raise ("raise loudly rather than silently gate", per the module header), the "insert the document before registering rights" ordering precondition, and the **security guard** `escrow-excluded by construction` (a verifier-critic found this path open at `b25b275` — silently no-op'ing it would re-open a money-routing hole). Keep all.
- `books/meta_reading.py` — `budget_for` range raises could be *clamped*, but clamping silently caps a user's reading-length request; the raise surfaces "your request is out of bounds" info the UI wants. The unknown-unit raise is a programmer error. Keep.
- `dp_shuffler/shuffler.py` — `epsilon <= 0` → a differential-privacy guarantee is undefined for ε≤0; defining it out would violate the §16 DP invariant. Keep.
- `ip_holders/__init__.py` — `accrue_escrow amount must be positive` → a financial invariant; accruing ≤0 money is a real bug, not a defined no-op. Keep.
- `graph/traverse.py` — `node not found` (start-label lookup miss) is a *candidate* definable-out (traverse-from-absent → empty), but the miss is inside a private `label→node_id` resolver used by several public functions with no existing test coverage; a correct define-out means redesigning at the public-function level. Deferred to a focused pass — not rushed here.

## Verification (filled after milestones 4–6)

- Characterization tests green BEFORE (assert current raises): see `tests/test_define_errors_out_characterization.py`.
- Defined-behavior tests green AFTER (assert empty result, no raise).
- Call-site simplification: 0 call sites passed `top_k<1`/`limit<1` and 0 caught these ValueErrors → no dead handling to remove (the guard was a never-triggered "should never happen"; removing the error variant closes a latent-unhandled-path with zero caller churn).
- SPR-01 ratio for the three modules: ≤ pre-change (recorded post-run).
- Full suite green before/after.
