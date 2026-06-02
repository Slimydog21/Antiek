# SPR-03 — §9.0 servability polarity reconciliation (chunk + book, ONE owned predicate)

**Decision date:** 2026-05-31
**Status:** ⏳ STAGED, NOT MERGED. The §9.0 servability unification is composed onto live `origin/main` (@ `4a7c674`) on the staged SPR-03 branch. It **merges ONLY behind the operator's §9.0 / G2–G3 legal gate** (CLAUDE.md invariant #4). The agent stages; the operator merges. No code path merges this automatically.
**Scope:** Reconciles the two contradictory §9.0 polarities over `documents.content_class` into ONE owned deny-by-default predicate, routes both the chunk-search path and the book full-text path through it, adds a code-enforced stage-safety guard for the privileged grounder bypass, and flips the `section-9-0-servability-polarity` invariant to `@guarded` **on the staged branch only**. The attribution money-path (`compute.py` / `payout.py` / Stripe) is **untouched** — out of scope, and a separate §9.0 decision for the operator.

---

## The bug this fixes (verified on main @ 4a7c674)

Over the single column `documents.content_class`, main carried **two opposite polarities**:

- `substrate/graph/search.py` §9.0 chunk gate was a **fail-open DENYLIST**:
  `AND (d.content_class IS NULL OR d.content_class NOT IN (RESTRICTED_CONTENT_CLASSES))`.
  A `NULL` or unrecognised `content_class` **PASSED** and was served on the
  attribution-eligible (ad/money) retrieval surface.
- `substrate/books/servability.py` was a **deny-by-default ALLOWLIST**:
  `servability_of(None) ⇒ GATED_METADATA_ONLY`, so `NULL`/unknown/restricted is
  **DENIED** full text.

Two polarities over one column = the §9.0 bug. The denylist is the fail-open hole.

## What SPR-03 composes (the canonical PR #29 design, applied to current main)

1. **ONE owned predicate.** `substrate/books/servability.py` now exposes
   `is_content_class_servable_full_text(content_class)` (NULL/unknown/restricted ⇒ `False`)
   and a DERIVED allowlist `servable_full_text_content_classes()`. An import-time assert
   pins `servable_full_text_content_classes() == set(SERVABLE_CONTENT_CLASSES)` so a
   regression in the predicate cannot silently widen the search allowlist.
2. **The chunk gate routes through it.** `search.py`'s §9.0 gate is now a deny-by-default
   ALLOWLIST: `AND d.content_class IN (servable_full_text_content_classes())`. The denylist
   polarity is REMOVED. `NULL ⇒ DENIED`, the same verdict the book path reaches over the
   same column. `RESTRICTED_CONTENT_CLASSES` is retained as a vocabulary anchor (it is
   imported by the out-of-scope `compute.py` and named in tests), but it is no longer the
   enforcement polarity.
3. **The grounder bypass (an honest WIDENING).** `interfaces/research/api/grounding.py`
   now calls `search()` with `policy_tag="private_research"`. Wrestling-loaded documents
   start with `content_class=NULL`; under deny-by-default the default
   `attribution_eligible` tag would return zero chunks for every freshly-wrestled document
   and break grounding. The privileged tag skips the §9.0 gate entirely. **This is NOT
   "restoring prior behavior"**: it WIDENS access — it re-admits `NULL` AND ALSO admits
   `restricted_pending_opt_in`, which the grounder's old default tag denied. The widening
   is bounded to the operator's single wrestled document (the grounder's search is
   `document_id`-scoped) on an operator-only, non-attribution path.

## Canonical: #29 NULL-DENIED over SPR-08 NULL-GRANDFATHER

A parallel Foundation effort (**SPR-08**, commit `d7b5d29`, "§9.0 servability polarity
unification — chunk+book+ATTRIBUTION") reached the OPPOSITE answer on the same gate. Its
chunk gate is `AND (d.content_class IS NULL OR d.content_class IN (CHUNK_SERVABLE_CONTENT_CLASSES))`
— i.e. it **KEEPS NULL servable** via a named `legacy_chunk_grandfathered` carve-out, and
it ALSO hardens the money/attribution path (`substrate/attribution/compute.py`).

**SPR-03 ratifies #29's NULL-DENIED as canon.** SPR-08's NULL-grandfather is rejected as
the fail-open hole:

- **Steelman the NULL-grandfather (fairly):** the in-tree corpus predates the
  `content_class` backfill; most legacy documents have `content_class=NULL` not because
  their rights are unknown but because nobody has labelled them yet. Denying all of them
  breaks continuity — research over the existing corpus suddenly returns nothing for
  unlabelled-but-legitimate documents, and the Sprint-16 telemetry (which the gate's
  original comment cited) ran on exactly this pre-gate data.
- **The answer:** a corpus-wide NULL-grandfather is precisely the blanket fail-open §9.0
  forbids. Unknown provenance is **legally indistinguishable from restricted** — *Hachette
  v. Internet Archive* (2d Cir. 2024) killed structural fair use for aggregate-and-serve,
  and *Bartz v. Anthropic* (~$1.5B) priced post-serve damages far above the cost of
  pre-serve gating. A NULL hole on the **attribution-eligible / money surface** is the
  exact §9.0 exposure the legal gate exists to block. The legitimate continuity need is met
  two ways that do NOT re-open the money surface: (a) the doc-scoped `private_research`
  grounder bypass keeps the operator's personal-research path working, and (b) the Sprint-18
  `ip_holders` `content_class` backfill re-admits genuinely-servable legacy documents on
  PROVENANCE (public_domain / open / opt-in), not on a NULL hole. A NULL-grandfather cannot
  be expressed as a finite, auditable, named carve-out — it matches arbitrary unknown
  provenance — so SPR-03 records **carve-out: NONE NEEDED**.
- **SPR-08's compute.py money-path hardening is a SEPARATE decision.** SPR-03 deliberately
  leaves `compute.py` untouched (out of scope). Whether the attribution money-path gets the
  deny-by-default hardening SPR-08 did is its own §9.0 / Sprint-18 call for the operator —
  NOT closed by this PR. Do not ratify two contradictory §9.0 gates.

## The §9.0 legal-gate boundary (agent stages, operator merges)

This change touches the strategically-consequential §9 layer (CLAUDE.md invariant #4: G1
closed, G2/G3 open). Per `OPERATOR_INPUTS.md §3`, the operator chose STAGE-ONLY: the agent
produces a green, ready PR; the operator makes the legal/strategy calls and merges. Items
the operator still owns (the checklist is mirrored verbatim in the docstring of
`tests/test_servability_polarity.py` for sign-off):

- Confirm deny-by-default is the desired production posture (item 1).
- Confirm prod can tolerate `NULL ⇒ DENIED` before the Sprint-18 backfill (item 2) — an
  empirical + legal call no code can make.
- Ratify the grounder WIDENING explicitly (items 5–6), not as a no-op.
- Decide separately whether `compute.py` gets SPR-08's deny-by-default hardening (item 7).

## Stage-safety guard — the privileged bypass is now CODE-ENFORCED (a real guard)

`OPERATOR_INPUTS.md §3` flagged (critic major) that "post-state is a strict subset" is
**false on the grounder path**: `private_research ∈ PRIVILEGED_POLICY_TAGS` skips the §9.0
gate entirely, and in PR #29 that bypass is protected ONLY by call-site discipline +
`document_id` scope — a future caller passing `private_research` on a money/ad path would
skip the gate.

**SPR-03 implemented the recommended REAL code guard (option a), not merely a documenting
test:** `search()` now requires a caller requesting any privileged `policy_tag` to present
`search.PRIVILEGED_CALLER_TOKEN` — a module-private `object()` sentinel (not a string, so it
cannot be reconstructed from config / an event payload / the tag name). A privileged tag
requested without the token raises `PrivilegedPolicyTagError`. Only code that imports the
token (the operator-only grounder entrypoint, `grounding.py`) can present it.

Tests (`tests/test_servability_polarity.py`):
- `test_money_path_caller_cannot_bypass_gate` — a money/ad-path stand-in that passes the
  privileged tag STRING but lacks the token is REJECTED; it cannot serve NULL/restricted
  content via the bypass.
- `test_operator_grounder_path_may_use_bypass_with_token` — positive control: WITH the
  token, the privileged path serves NULL AND restricted (the intentional, ratified
  widening), proving the guard gates on the TOKEN, not the string.
- `test_token_is_not_a_reconstructable_string` — the token is an object sentinel, not a
  forgeable string.

**Residual gap (honest):** the guard is an *in-process* sentinel. It code-prevents an
in-process caller from using the bypass without the token, which is strictly stronger than
PR #29's call-site discipline. It does NOT (and cannot, at this layer) prevent a future
developer from importing the token into a money-path module — that remains a code-review /
boundary-lint concern (the boundary builder owns `owner_boundary_check.py` in a parallel
branch). The real money path (`substrate/attribution/compute.py`) does NOT call `search()`
with a privileged tag at all — it filters `RESTRICTED_CONTENT_CLASSES` directly — so today
there is no money-path caller of the bypass to begin with. The operator should ratify the
grounder widening (checklist item 5) with this scope in mind.

## Non-vacuity — the keystone seed-and-catch (the proof has teeth)

The `section-9-0-servability-polarity` guard is
`tests/test_servability_polarity.py::test_live_null_and_unknown_denied_on_both_paths`,
which runs the REAL `search()` SQL gate against a real DuckDB seeded one-document-per-class.

- **fail-before:** restore the pre-SPR-03 fail-open denylist clause
  (`AND (d.content_class IS NULL OR d.content_class NOT IN (...))`) on the `search.py` gate →
  the polarity suite goes **RED** (3 failures: the guard node + the two parametrized
  live-SQL agreement cases for `None` and the unknown literal; `search()` serves `doc-null`
  and `doc-unknown` again).
- **pass-after:** `git checkout -- substrate/graph/search.py` → **27 GREEN**.

This was executed this session; the output is pasted in the SPR-03 handoff. A
stubbed/in-memory-only guard could not produce this live-SQL bite, which is why the guard
is the live-SQL node rather than the in-memory predicate test.

## Money-path-untouched proof

`git diff 4a7c674..HEAD --stat -- substrate/attribution/compute.py substrate/attribution/payout.py`
is **EMPTY**. Zero payout / Stripe / attribution-compute lines changed (verified; the diff
file set equals PR #29's six files + this branch's owned invariant toml + this decision doc
+ the staged-branch Wave-1 expectation update below).

## Files changed (the diff)

The six core files equal `gh pr diff 29 --name-only` exactly:
`interfaces/research/api/grounding.py`, `substrate/books/servability.py`,
`substrate/graph/search.py`, `tests/test_graph.py`, `tests/test_retrieval_time_gate.py`,
`tests/test_servability_polarity.py` (new).

Plus the SPR-03-owned:
- `substrate/invariants/section-9-0-servability-polarity.toml` — flipped to `@guarded`
  **on this staged branch only** (guard = the live-SQL polarity node; `[non_vacuity]`
  `method=fail_before_pass_after` + a `bite_test` recording the seed-and-catch). On main it
  stays `@unguarded` (owner SPR-03) until the operator merges §9.0.
- `docs/decisions/spr-03-reconcile-servability-and-boundary.md` — this file.

One forced consequence of the M3 flip:
- `tests/test_invariant_registry_meta.py` — `test_wave_1_invariants_are_registered` hardcodes
  the main-branch reality that section-9-0 is `@unguarded`. Because SPR-03's staged branch IS
  the §9.0 PR (on which section-9-0 is guarded), that single Wave-1 expectation is updated to
  move section-9-0 from `must_be_unguarded_with_owner` to `must_be_guarded`, scoped explicitly
  to the staged branch in the test's docstring. This edit is required for
  `pytest tests/test_invariant_registry_meta.py -q` to pass with the guard flipped (M3
  acceptance). It returns to `@unguarded` if the operator rejects the staged §9.0 PR.

## Rebase reconciliation onto current main (2026-06-02) — Full unification

When this PR was opened (2026-05-31) its base was current; by 2026-06-02 `main`
had advanced **77 commits** and the PR went `CONFLICTING`. The stale green checks
predated the drift. Rebased onto `origin/main`; the conflict was confined to the two
§9.0 core files, and resolving it surfaced that #38's design — written knowing only
the grounder — was **incomplete against the main that landed in between**. The
operator chose **Full unification** (over "thread token to owner paths only" or
"keep #38 minimal").

**What main added during the drift (the Personal-Reading Lane, PR #43):** a 4th
rights state `personal_reading` → `PERSONAL_READABLE` (owner-reads-in-full /
never-publicly-servable / never-attributable), plus `PERSONAL_ONLY_CONTENT_CLASSES`
and `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES` in `search.py` (the latter imported by
the money-path `substrate/attribution/compute.py`), and a SECOND copy of the §9.0
gate inside `substrate/graph/retrieval_substrate.py`'s VSS path (a fail-open denylist
whose own comment said "the §9.0 allowlist unification is staged separately in PR
#38, unmerged").

**Conflict resolution (deterministic — both sides converge):**
- `substrate/books/servability.py` — clean union: main's `PERSONAL_READABLE` branch
  (kept out of `_CONTENT_CLASS_TO_STATUS`, so the import-time drift assert
  `servable_full_text_content_classes() == SERVABLE_CONTENT_CLASSES` is untouched) +
  this PR's owned predicate. `is_content_class_servable_full_text('personal_reading')`
  is `False` (it resolves to `PERSONAL_READABLE`, not a servable status).
- `substrate/graph/search.py` — adopted this PR's deny-by-default ALLOWLIST. It
  **subsumes** main's denylist: `personal_reading` and `restricted` are excluded on
  the non-privileged path exactly as the denylist did, and NULL/unknown are
  additionally denied (the bug fix). Retained main's `PERSONAL_ONLY_CONTENT_CLASSES` /
  `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES` as **vocabulary anchors** (compute.py +
  `test_personal_reading_lane.py` import them) — same treatment this PR already gives
  `RESTRICTED_CONTENT_CLASSES`.

**Full unification (the scope the operator chose):**
- `substrate/graph/retrieval_substrate.py` — the VSS path's second §9.0 gate now
  routes through the SAME owned allowlist (`content_class IN
  servable_full_text_content_classes()`), and the SAME `PRIVILEGED_CALLER_TOKEN`
  stage-safety guard is enforced in `_vss_query` so the seam is not a token-less side
  door. `privileged_caller` is threaded through the `RetrievalSubstrate` Protocol +
  both impls (`BruteForceSubstrate.query` forwards to `search()`; `VssSubstrate.query`
  forwards to the fallback `search()` and to `_vss_query`). One polarity now, owned in
  `servability.py`; the "staged separately, unmerged" marker is resolved.
- `substrate/context_pack/knowledge_reuse.py` — `retrieve_prior_units` gained a
  `privileged_caller` passthrough to the seam (its `except Exception → return []` would
  otherwise silently mask the guard for a future privileged caller).

**Correctly OUT of scope (not a duplicate polarity):** `orchestration/monitoring/
monitor.py`'s `putter_feed` gate is a DIFFERENT mechanism — it serves a pre-filtered
`personal_reading`-only feed and gates the **body field** on `owner_path`. Routing it
through the servability allowlist would be *wrong* (it would empty the owner's own
feed, since `personal_reading` is non-servable). Left untouched.

**Tests updated to the now-required token** (intent preserved, not weakened): the
owner-read paths must present `PRIVILEGED_CALLER_TOKEN` —
`test_personal_reading_lane.py::test_search_gate_includes_personal_reading_on_operator_only`,
`test_monitoring_mode.py::test_personal_lane_hidden_from_public_search`,
`test_retrieval_substrate_interface.py::test_gate_includes_restricted_under_private_research`.
Added `test_privileged_tag_without_token_is_refused_on_seam` (parametrized vss +
brute_force) — non-vacuity that the guard bites on the seam, not just on a direct
`search()` call. Full affected suite (servability/graph/retrieval/personal-lane/
monitoring/knowledge-reuse/attribution/payout): **green**.

**Money path still untouched:** `compute.py`/`payout.py` diff remains empty; the
retained vocabulary constants keep their values, so `compute.py`'s import + filter are
unaffected (`test_attribution.py`, `test_payout_pipeline_integration.py` green).

## Out of scope (untouched)

`substrate/attribution/compute.py`, `payout.py`, Stripe connect (the money path);
`owner_boundary_check.py` / `boundary.toml` / `ci.yml` (the parallel boundary-lint builder);
closing the §9.0 legal gate; redesigning servability (PR #29's predicate is composed as-is);
the flywheel.
