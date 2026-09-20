# HANDOFF — attribution recursion (ads-settlement SPR-2)

Branch `lane/attribrecurse-20260920`, worktree `/tmp/lane-attribrecurse`, based on
`origin/main` at `ebc5996ad`.

## Step 0 — the gap was open

Verified before building, because the brief said it might be stale. It was not.

`substrate/attribution/compute.py::compute_attribution_for_synthesis` (:94) and
`algorithms.py::attribution_option_{a,b,c}` existed and were correct as far as they went:
they resolve a synthesis to a per-document **share vector** over the documents it sourced,
gated by §9.0, with each document's `ip_holder_id` attached. What did not exist anywhere
in the tree was the recursion — nothing split a metered attention-second across those
holders **plus the author**, nothing capped depth, nothing recorded an unattributed
remainder, and nothing on the System-1 side stamped a version at all. Greps for
`attention_second`, `ATTRIBUTION_ALGORITHM_VERSION` and `recurs` across `ad_inventory/`
confirm it: `frame_attention_accrual.py` stops at the in-frame `asset_id` and attributes a
synthesis as one asset, exactly as the spec says.

## What landed

`substrate/attribution/recursion.py` — one attention-second on a synthesis splits across
the `ip_holder_id` of every document it sourced, the author, and an explicit unattributed
remainder, summing to **exactly** one second. Integer units
(`UNITS_PER_ATTENTION_SECOND = 1_000_000`), largest-remainder with a key-deterministic
tie-break. Depth capped at 3 with cycle detection; every early exit emits a line for its
whole budget, so conservation holds by construction. New typed event
`synthesis.attribution.recursed` carries the canonical inputs, so `replay(inputs_json)`
reproduces the split with no database and no network.

Three decisions recorded in full, with what was rejected, in
`docs/decisions/attribution-recursion-author-share.md`:

- **Author share: fixed constant, 0.30, live**, behind `AUTHOR_SHARE_POLICY =
  "author-share-fixed-30-v1"`. The span-proportional alternative is not buildable:
  `ThesisComponent` declares `extra="forbid"` and has no epistemic-typing field, so no
  synthesis in the tree can carry the data. A tripwire test fails the day it lands.
  `claim_count` / `path_only_claim_count` are recorded per synthesis as the measurement
  that makes the switch cheap — they price nothing.
- **Depth: 3**, remainder explicit (`depth_cap`, `cycle_detected`, `owner_unknown`,
  `author_unresolved`, `synthesis_unresolved`). Never vanishes, never loops.
- **Versioning: a new constant, not a bump of `ATTRIBUTION_ALGORITHM_VERSION`.** That
  constant versions the §9.3 share math this lane does not touch, and the AFA decision
  doc reserves its next bump for the operator's unratified Option-C unification. Spending
  it here would destroy that signal. A split stamps `recursion_version`,
  `author_share_policy`, and `share_algorithm` + `share_algorithm_version` separately.
  No historical row is recomputed.

## The §9.3 divergence — operator gate, still open

`docs/decisions/afa-synthesis-attribution-canonical.md` already documents both
implementations (`substrate/attribution/` claim-iterating and §9.0-gating-aware;
`substrate/ad_inventory/attribution.py` chunk-iterating and wired to the durable audit
store) and escalates *which is canonical* to the operator. **Still unratified.**

Built against System 1, and it is safe whichever way it is ratified: it is the only one
that can resolve a `synthesis_id` through the provenance chain at all, it is the only
gating-aware one, the recursion consumes a share vector through a *named* algorithm and
records which priced it, and this lane writes no durable audit row and leaves
`ATTRIBUTION_ALGORITHM_VERSION` untouched. If Option C is ratified, the unified math
supplies the same vector and this layer does not change.

One new constant on the System-1 side: `ATTRIBUTION_SHARE_MATH_VERSION =
"attr-math-v1-substrate"`. Not a second version of one contract — the missing **label** on
a second implementation that already existed and stamped nothing.

## Money boundary

Nothing moves money and nothing can. Asserted, not assumed:

- `test_recursion_module_reaches_no_money_writer` — AST-blanks docstrings and comments,
  then fails if executable code names `accrue_escrow`, `escrow_balance_usd`,
  `attempt_disbursement`, `record_attribution`, `frame_attention_accruals`,
  `speak_accruals`, `stripe` or `payout`. Red-proven.
- `test_computing_a_split_moves_no_money` — runs the live path against a real DuckDB,
  asserts a holder was actually credited units (or the test proves nothing), then asserts
  every escrow balance is byte-identical and no ledger row appeared.
- `test_recursion_is_not_a_sanctioned_escrow_caller` — the single-escrow-writer seam's
  allow-list must not name this module, so wiring settlement later takes a deliberate edit
  in front of a reviewer.

Every split records `gate`, today always `display`. The resolver is named
`DisplayGatedProvenanceResolver` on purpose: it inherits `compute.py`'s §9.0 gate, which
withholds `restricted_pending_opt_in` — right for a surface, wrong for an earn path where
that class must keep accruing to escrow under §9.10. A settlement path needs an
`EarnGatedProvenanceResolver` excluding only `personal_reading`.

## Not wired, deliberately

`frame_attention_accrual.py` was **not** changed. The AFA doc's steps 2–4 stay dormant
until a synthesis surface carries `data-akb-asset-id` (SPR-1) and until the §9.3 canonical
math is ratified, and wiring the split into the money path before §9.0 closes is exactly
what the money boundary forbids. The primitive, its event and its replay contract are
complete and callable; `compute_recursive_attribution(synthesis_id, emit_event=True)` is
the entry point.

## Findings for whoever takes SPR-3

1. **`syntheses` carries no owner, and neither does the event envelope.** The author leg
   has no subject for most syntheses. The resolver falls back to the single
   `owner_user_id` across the documents ingested under the same `investigation_id` and
   returns `None` on disagreement — those units become an explicit `author_unresolved`
   line, never a guess. Making the leg real means writing `owner_user_id` on `syntheses`
   at deposit time; historical rows cannot be backfilled.
2. **`_largest_remainder_cents` (ad_inventory) breaks ties in dict-insertion order.**
   Harmless inside `attribution_audit.replay()` (canonical-JSON rebuild), latent in
   `aggregate_window`, which builds weights in batch order. Narrow money-path
   nondeterminism; `apportion_units` here does not have it.
3. **Adding an `ActionType` breaks the reading app.**
   `apps/reading/src/modes/ResearchWorkstation/narrateEvent.ts` declares
   `Record<ActionTypeValue, NarrationRule>` and its test asserts full catalogue coverage.
   The brief did not mention this and nothing on the substrate side points at it; a new
   event type without a row is a TypeScript error plus a red vitest. Row added
   (suppressed). Anyone adding an event type must do the same.

## Commands run, with real output

```
$ .venv/bin/python -m pytest tests/test_attribution_recursion.py -q
37 passed in 1.90s

$ .venv/bin/python -m pytest tests/test_attribution_recursion.py tests/test_attribution.py \
    tests/test_codegen.py tests/test_attribution_audit.py \
    tests/test_seam_single_escrow_writer.py tests/test_contracts_conformance.py \
    tests/test_conformance_gate.py -q
116 passed, 1 warning in 9.93s

$ .venv/bin/python -m ruff check --output-format=concise <touched files>
All checks passed!

$ .venv/bin/python -m tools.lints.declared_bar enforce ruff \
    --baseline-file tools/lints/baselines/declared_ruff.json
declared-bar ruff exit=0

$ .venv/bin/python -m mypy --strict substrate/attribution/recursion.py \
    | grep '^substrate/attribution/recursion.py'
(no output — zero findings in the new module; the 242 errors mypy reports are
 pre-existing, in 50 other files it follows imports into, all baselined)

$ .venv/bin/python tools/codegen/emit_types.py --stdout \
    | diff - apps/reading/src/generated/types.ts
TS in sync

$ .venv/bin/python tools/codegen/check_conformance.py
OK: 11 contracts conform (2 real impl, 9 stub); DRW sprint-lock resolves every
downstream citation; chunk provenance policy aligned (personal_reading non-citable).

$ .venv/bin/python -m tools.lint.reachability_gate_py \
    --baseline tools/lints/baselines/reachability_py.json
exit 0  (3 pre-existing stale entries reported, unrelated to this lane)
```

Two red-proofs, both restored afterwards: subtracting one unit from the author leg reds
`test_one_second_splits_across_sources_and_author_and_conserves` on `conserves()`;
inserting the literal `accrue_escrow` into executable code reds
`test_recursion_module_reaches_no_money_writer`.

## Not done

- Frontend `vitest` / `tsc` were not run — `apps/reading/node_modules` is absent and the
  brief forbids `npm install`. The narration row was added by reading the map and its
  coverage test; a CI frontend job is the real verification.
- No API route surfaces the split. Adding one is a live surface change and was outside
  the done-bar.
- `frame_attention_accrual.py` is untouched (see "Not wired, deliberately").
