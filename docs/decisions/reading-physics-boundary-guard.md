# Reading-physics augmentation-boundary CI guard (SPR-03)

**Decision date:** 2026-05-27
**Status:** ✅ Active — advisory (canon is `draft`); becomes blocking on ratification + `--enforce`
**Owner:** Read-surface instance (SPR-03) + operator (ratification, enforce-flip)
**Guard:** `tools/lint/reading_physics_check.py`
**Wired in:** `.github/workflows/ci.yml` → `tsc` job (TypeScript surface, per canon §7)

## What was decided

The Physics of Reading (`docs/philosophy/physics-of-reading.md`) makes PR-2
("substrate-owned data, no side store") **binding like DuckDB single-writer**.
Rather than leave it to code review — which will miss a smuggled store across
many future agent-authored augmentations (SPR-08) — SPR-03 ships a **static
boundary lint**, modeled on `tools/lint/boundary_check.py` (same path:line
output, same exit-code contract). It scans
`apps/reading/src/reading-physics/augmentations/` + `.../facets/` and fails the
build (under ratified canon + `--enforce`) on the detectable PR-1/2/3/6 patterns
plus the **PR-8 positive import-allowlist** (the canon §7-pattern-6 "single
check that makes PR-8 true").

## Why CI, not code review (the steelman, rigor #2)

**Steelman the rejected alternative — "enforce by code review."** A reviewer can
catch a `localStorage` write and is the *only* thing that can catch the evasions
a static scan can't (dynamic import, a store behind a shared util, a verdict
recompute). Review is also zero CI surface and adapts to intent. So why CI too?

**Why review-only loses.** PR-2 is binding *like single-writer* — the operator
chose to make it mechanical, not advisory. SPR-08's roadmap is an **agent**
authoring augmentations, where **review attention is the scarce resource**: the
guard is exactly what makes agent-authorship safe, because it turns "did the
agent quietly keep a store?" from a thing a tired reviewer must notice on every
PR into a thing the build refuses. The guard does not *replace* review (it
explicitly hands the un-catchable back to it, below) — it removes the
mechanical, high-volume cases from the reviewer's plate so review attention goes
to the judgment calls. **Concession:** the guard adds CI surface and a
maintenance burden (the pattern list); that is the accepted price of a binding
invariant, the same trade `boundary_check.py` already makes.

## Precise scope — what it catches

Each pattern has a literal signature a text/line scan can match:

- **PR-2** — `localStorage`/`sessionStorage`/`indexedDB`; a persistence/store
  client import (`idb`, `dexie`, `zustand`, `*store*`, `persist`, …); a direct
  `fetch`/`axios`/`XHR`. A `// PR-2 escape:` comment exempts the bounded,
  view-only, derivable cache (the canon's bounded escape clause).
- **PR-1** — `innerHTML=`/`outerHTML=`, `appendChild`/`insertBefore`/
  `removeChild`/`replaceChild`, `classList.add/remove/toggle`,
  `document.querySelector`/`getElementById`/`getElementsBy*`, `createPortal`.
- **PR-3** — an import that resolves to a *sibling* augmentation module.
- **PR-4/PR-5** — `getBoundingClientRect`, `offsetTop/Left/Width/Height`,
  `scrollTop`, `window.innerWidth/innerHeight`, `matchMedia`.
- **PR-6 (import half)** — importing a substrate **write** path (`db_lock`,
  `event_log`, `append_event`, a POST-mutation/dispatch-write client).
- **PR-8 (positive import-allowlist)** — beyond the negative patterns above, the
  guard asserts the *positive*: every **static** import specifier in an
  augmentation module (under `.../augmentations/`) must resolve to the allowed
  set, else it fails. The allowed set, per canon §7 pattern 6 and matched to
  what the real shipped augmentations actually import:
  - the **facet API barrel** — any relative specifier that resolves inside
    `apps/reading/src/reading-physics/` (`../types`, `../facet`, `../facets/*`,
    `../registry`). (servability.ts and ip-holder.ts import only `../types`.)
  - the **substrate read API** — a relative specifier resolving to
    `apps/reading/src/lib/api` (canon-named; received via `ctx.substrate`, so no
    shipped augmentation imports it directly today, but the canon permits it).
  - **React** — bare `react` / `react/jsx-runtime` (types only).
  - the **design-token / Lemon primitives** — canon-named but NOT yet imported
    by any shipped augmentation, so deliberately **left out of the active bare
    allowlist** (no speculative pre-allow). Add the exact name/prefix here the
    moment a real augmentation imports one.
  Anything else (e.g. `lodash`, `chart.js`, `date-fns`) fails as a PR-8
  violation — proof that the augmentation was *not* authorable from the facet
  contract alone. This is the check that makes SPR-08's agent-authorship safe.
  (Its one blind spot is a *dynamic* `import(expr)` with a computed specifier —
  no string to resolve; see "what it CANNOT catch" → dynamic import.)

## Precise scope — what it CANNOT catch (intellectual honesty, rigor #1 & #3)

A static scan is not airtight, and the guard's own docstring + this doc refuse
to pretend otherwise. **Review owns these** (canon §9 open questions 1 & 1b):

- **Dynamic import** — `await import(someVar)` has no literal module string.
- **Indirection through a shared util** — a store/singleton one hop away in a
  helper the augmentation imports; the guard scans the file, not the call graph.
- **A module-level mutable singleton** as a store of record — no banned token.
- **A write through React context / a prop callback** — no banned token.
- **PR-6 §7-pattern-5b: substrate-verdict *recompute*** — re-deriving a
  servability verdict / rubric score / attribution share locally is arbitrary
  arithmetic with **no import or call signature**. **Advisory / review-owned.**
  (The *import* half of PR-6 IS caught.)
- **PR-7 anti-purgatory** — partly a product judgment; the guard emits an
  **advisory** grep for `*Prototype*`/`*Playground*` reader imports, never blocks.

## Advisory ↔ blocking (rollout)

Blocking requires **BOTH** the canon front-matter `status: ratified` **AND** the
`--enforce` flag. While the canon is `draft` the guard only warns (exit 0) — it
never blocks a PR against unratified canon. After ratification, the first PR
stays advisory (no flag) so findings surface on the real tree without a surprise
red gate; a follow-up PR adds `--enforce`. This mirrors the standing
informational-then-blocking discipline (`ci-informational-gates.md`).

The CI step (`.github/workflows/ci.yml`) invokes the guard **with no `|| echo`
swallow**, so the step's pass/fail is exactly the guard's self-gated exit code.
The guard already returns 0 (advisory) unless *both* gates are set, so the step
is green today. This deliberately avoids a false-negative trap: flipping the
gate blocking is the **single atomic act** of adding `--enforce` to the command
(under a ratified canon) — there is no second edit to remember (no `|| echo` to
delete), so the gate cannot silently stay green once enforced.

## Proof the guard is real, not theater (rigor #1)

SPR-03 wrote a deliberately-violating fixture augmentation (a `localStorage`
store + a DOM `innerHTML=` mutation + a `getBoundingClientRect` measure + a
sibling-augmentation import), ran the guard, and confirmed:
- **advisory (canon draft):** the guard *listed* all five findings, exit 0;
- **blocking (canon temporarily ratified + `--enforce`):** the guard *blocked*,
  **exit 1**;
- after **deleting** the fixture: the guard is clean (exit 0) on the real
  servability + ip-holder augmentations in both modes.

The SPR-03 sharpen round added the **PR-8 allowlist** and proved it the same
way: a fixture augmentation importing `lodash` + `chart.js` (and `../types`,
which is allowed) was flagged on the two non-allowlisted imports only — advisory
exit 0 while draft, **exit 1** under temporarily-ratified canon + `--enforce` —
then **deleted**. The real servability + ip-holder augmentations (which import
only `../types`) stay clean. Both fixtures were deleted; neither is in the tree.
Recorded in the SPR-03 handoff.

## Reconsider if

- A pattern proves too noisy on the real tree (false positives on a legitimate
  idiom) → narrow the regex, never silence the whole guard.
- The augmentations directory moves → update `_AUG_DIR`/`_FACET_DIR`.
- A sharper signal for the review-owned clauses appears (e.g. an augmentation
  registry that the production surface and only it reads from, making PR-7
  "registered ⇒ shipped" mechanical) → fold it in and shrink the advisory set.
