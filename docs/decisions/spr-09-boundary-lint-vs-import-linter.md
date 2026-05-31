# boundary-lint — composed from antiek-harness-hardening sprint-04, narrowed to one-owner

**Date:** 2026-05-31
**Branch:** `caffen/aff-spr-03-boundary` (Antiek Flywheel Foundation SPR-03)
**Source spec:** Antiek Flywheel Foundation SPR-03 (M2/M5) · composes the
stranded commit `48c3856` (itself composing
`~/specs/antiek-harness-hardening/sprint-04-boundary-lint.html`)
**Filename note:** the `spr-09-` stem is kept deliberately — the composed lint
(`owner_boundary_check.py`) and `boundary.toml` reference this doc by that exact
path, and they are landed BYTE-IDENTICAL to `48c3856` (where they were authored
under the earlier "SPR-09" label). The work itself lands under Antiek Flywheel
Foundation **SPR-03**; only the artifact's provenance filename is preserved so
the byte-identical references resolve.
**Status:** COMPOSED (the harness sprint stays authoritative for its *intent*;
this records the one mechanical NARROWING + the enforcing-not-informational
choice this Foundation made).

## Why this is on its own immediate-merge PR (defensibility)

This boundary-lint carries **zero servability-decision lines** — it asserts
*who may OWN* the servability predicate, never *what may be served*. It has no
§9.0 legal surface, so it merges on its own green PR, independently of the
staged §9.0 servability reconciliation (which lands on a separate branch behind
the operator's legal sign-off). The two are deliberately decoupled:
`test_lint_passes_on_the_post_9_0_dual_consumer_topology` pins that the
immediate-merge lint is GREEN on the post-§9.0 topology (owner DEFINES;
`search.py` / `serve.py` / `grounding.py` IMPORT), so the lint can neither block
nor be blocked by that staged reconciliation.

## Enforcing, not informational (the whole point — defensibility)

The prior foundation wired the equivalent guard **informational** (it ran but
never failed the job), so it never caught the §9.0 drift it was meant to catch.
This lint is wired **ENFORCING**: the CI step `One-owner-per-layer boundary
check` runs `python tools/lint/owner_boundary_check.py` with **no**
`continue-on-error` and **no** `|| true` / `|| echo` swallow — the step's
pass/fail is EXACTLY the lint's exit code, modelled on the existing
`tools/lint/boundary_check.py` step. A swallowed exit code would re-create the
exact silent-pass hole that let the polarity mismatch survive.

## Provenance verdict (rigor #5 / defensibility)

The boundary-lint is **composed, not re-specced and not superseded**. The
harness sprint-04's intent — "one-owner-per-layer, CI-enforced; an accidental
boundary break fails CI instead of quietly rotting the architecture" — is
adopted verbatim. The harness spec is still authoritative for the *idea*. What
this Foundation sprint changed is the **mechanism of the first assertion**, and
that single divergence is recorded here so a future maintainer is not confused
about why the shipped lint is an AST one-owner check rather than the
`import-linter` layered contract the harness page describes.

## The narrowing (what diverged, and why this version wins)

**Harness sprint-04 proposed** Python's `import-linter` with a `layers` contract
encoding `substrate → dispatch → loop → orchestration → product`, so a lower
layer can never import a higher one (Cline's strict dependency direction).

**This Foundation shipped** `tools/lint/owner_boundary_check.py`: an AST check
that a declared *concern* (the §9.0 servability predicate) is DEFINED in exactly
ONE module, and that no other module reimplements it. The first real assertion
targets `substrate/books/servability.py` — the §9.0 servability owner (the Read
workflow's legal-gate vocabulary; see that module's `servability_of` /
`is_servable_full_text`).

**Why the narrowing wins for the Foundation's purpose:** the Foundation spec is
explicit that boundary-lint exists to "prevent exactly the §9.0 polarity
mismatch and the one-entity DTO erosion the capstone found." That mismatch was
**two same-layer modules** (`substrate/graph/search.py`'s chunk denylist and
`substrate/books/servability.py`'s allowlist) each owning a servability decision
with **opposite polarity** over the same `documents.content_class` column.

`import-linter` checks dependency *direction*. It would have passed that bug
cleanly: two sibling modules at the same layer, with no upward import between
them, each defining a predicate, is exactly what import-linter cannot see. The
concern that actually broke was *single-ownership of a decision*, not layer
direction — so the Foundation's first assertion has to be a one-owner check, or
it would be decorative against the failure it cites. An AST walk for a top-level
`def` whose name matches the concern's predicate pattern decides one-ownership
mechanically; that is what shipped.

## Honest scope (rigor #1)

The lint flags a second **DEFINED predicate** (a top-level `def` whose name
matches the concern's pattern), not inline SQL. On live main the chunk-search
§9.0 gate in `substrate/graph/search.py` is expressed as an inline
`content_class NOT IN (...)` SQL denylist, NOT a defined `is_chunk_servable`
function — so this lint correctly does NOT flag it as a second owner, and could
not catch a denylist re-expressed as raw SQL. Closing the SQL-polarity drift is
the job of the §9.0 servability unification (the parallel §9.0 builder) plus the
registry's §9.0 servability-polarity invariant — NOT this lint. This lint's
narrower, mechanically-decidable job is: *no second module re-introduces the
owned predicate as a Python definition* (the pre-SPR-08 chunk fork shape). The
lint's `predicate` regex therefore still INCLUDES `is_chunk_servable` so that a
future module re-introducing it as a defined predicate is caught — even though
the owner does not currently define it (the owner defines `servability_of` +
`is_servable_full_text`, which satisfies the "owner must define at least one
matching predicate" non-vacuity check).

## Steelman of "just use import-linter as the harness spec says" (rigor #2 / fairness)

The case for following the harness page literally: import-linter is a mature,
declarative tool; layer-direction is a real and valuable rule; a custom AST lint
is more code to own. All true. It loses on **fit to the cited failure**: the
Foundation names the §9.0 polarity mismatch as the thing to prevent, and
import-linter is structurally blind to it (no upward import is involved). Layer
direction is a complementary, additive rule — **not rejected**, just deferred:
it can be added later as a second concern/contract without changing this lint's
shape. Shipping the one-owner check first is choosing the rule that bites the
documented bug over the rule the title suggested. This is the narrowing the
harness-hardening "import-linter layer-direction" idea undergoes (rigor #2): it
is NOT widened into a general import linter.

## Search-root coverage: all five servability-consuming roots

The lint scans the five substrate roots that consume servability —
`substrate/graph` (chunk/search), `substrate/attribution` (money),
`substrate/books` (serve + owner), `substrate/write` (`trace.py` resolves a
gated book to `servable_snippet` vs full text) and `substrate/speak`
(`publish.py` maps `PLATFORM_AUTHORED` to served full text). `write/` and
`speak/` are serve-/money-adjacent, so leaving them unscanned would shrink the
invariant's reach below the surface that actually decides servability. Because
both import the owner today (no competing top-level predicate), the lint stays
**green** while the guarded surface covers every consuming root. Three tests
make the coverage non-vacuous rather than decorative:
`test_real_servability_consumers_are_scanned_and_clean`,
`test_widened_lint_catches_a_second_owner_in_speak`, and
`test_servability_search_roots_cover_every_real_consumer` (discovers the real
consumers from the tree and asserts the serve-/money-deciding ones are scanned,
so the coverage claim cannot silently shrink). Adding a sixth root later is a
one-line `search_roots` change plus a consumer assertion.

## Coexistence with the existing vendor-SDK boundary check

`tools/lint/boundary_check.py` (DDIA-execution SPR-03) already exists and checks
a *different* boundary — no vendor SDK imported in `substrate/` outside
`substrate/dispatch/providers/` (vendor-agnosticism / §16). The new
`owner_boundary_check.py` is its sibling, not its replacement: vendor-check =
"don't import the wrong thing"; owner-check = "don't reimplement the owned
thing." Both run as distinct CI steps with the same `path:line` + exit-code
contract.

## Registered invariant + the script-kind loader hardening

`substrate/invariants/boundary.toml` (`id = "boundary"`, `status = "guarded"`,
`guard_kind = "script"`). Guard: `tools/lint/owner_boundary_check.py`.
Non-vacuity: `tests/test_owner_boundary_lint.py` injects a divergent second
owner and proves the lint flags it (fail), then proves it goes green once the
bypass imports the owner (pass).

Registering this as a SCRIPT-KIND guard required bringing the loader delta from
`48c3856` onto the SPR-02 registry: SPR-02 reconciled the registry loader from a
*pre-script-kind-bite* version, so `substrate/invariants/__init__.py` parsed a
`script` guard but **never RAN** its non-vacuity — a `script` "guarded" meant
only "a `[non_vacuity]` block is declared", the §14.4 fake-green disease one
`guard_kind` over. SPR-03 adds (a) the loader's `bite_test` field +
require-bite-for-script-kind validation, and (b) the meta-check's
`test_script_kind_guard_bite_test_is_live`, which **RUNS** the declared bite_test
with the same rigor a pytest-kind guard's own node gets (collected, not
xfail/xpass, passes). Three broken-fixture proofs
(`test_meta_check_rejects_script_guard_without_bite_test` / `_with_dead_bite_test`
/ `_with_xfail_bite_test`) prove the new contract has teeth. The SPR-02
reconciliation of `test_wave_1_invariants_are_registered` (owners/statuses for
the Wave-1 rows) is left untouched — only the script-kind machinery was added.

## Reconsider-if

- A real upward-import bug appears (a `substrate/` module importing
  `orchestration/`) → add the import-linter layer-direction contract as a second,
  additive mechanism. It does not replace the one-owner check; the two answer
  different questions.
- A second single-owner concern is established (a shared DTO, an enum) → add one
  `Concern` row to `CONCERNS` in `owner_boundary_check.py`. No new code.
- The §9.0 servability reconciliation lands `is_chunk_servable` on the owner →
  no change needed (the predicate regex already includes it; the owner gaining a
  matching predicate keeps the lint green). If instead it removes
  `is_servable_full_text` from the owner, the lint's missing-predicate branch
  reddens — by design (a vacuous owner is a silent gap).
