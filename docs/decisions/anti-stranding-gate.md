# Anti-stranding gate — merge-age budget N + reachability burn-down

**Decision date:** 2026-05-31
**Status:** ✅ Active (blocking on `pull_request:[main]`; each rule carries a reconsider-if below)
**Owner:** operator + SPR-01 (Antiek Flywheel Foundation)

SPR-01 designs out the two failure modes that killed the prior foundation. That
work forked at `69bcfef`, was lapped by ~+38 commits onto a long-lived
integration branch, halted at SPR-10 with "base is stale," and **never merged to
main**. Two new CI checks make those failures mechanically loud on every PR to
`main`:

- **Merge-age gate** (`tools/lint/merge_age_gate.py`) — reds when the PR's base
  is more than `N` commits behind `origin/main` (the anti-*stranding* gate).
- **Reachability gate** (`tools/lint/reachability_gate.py`) — reds when a PR
  introduces a NEW zero-importer module or a route with no inbound link (the
  anti-*purgatory* gate).

Both are wired into the `pytest` job (which checks out `fetch-depth: 0`,
satisfying merge-age's full-history need) **after** the `arXiv contact-guard
check` step. Neither step uses `|| echo` / `|| true`: the step's pass/fail is
**exactly** the gate's exit code — a swallowed exit code would re-create the
silent-pass hole these gates exist to close.

This follows the standing **informational-then-blocking** discipline recorded in
`docs/decisions/ci-informational-gates.md`: a gate is allowed to land
informational while its baseline/contract settles, then flips to blocking by a
single reviewed edit. Both gates here land **blocking from day one** because
their non-vacuity is proven by seed-and-catch tests
(`tests/test_anti_stranding_gate.py`) rather than left to a future flip.

## Threshold N (= 25)

`N = 25` is the maximum number of commits the PR's base may be behind
`origin/main` before the merge-age gate reds. It lives in **one named constant**,
`MAX_BEHIND` in `tools/lint/merge_age_gate.py`. The decision doc and the code
cite the same number so the two cannot drift; `tests/test_anti_stranding_gate.py`
imports that constant and asserts the doc-stated value matches it.

**The arithmetic that ties N to the prior +38 stranding.** The prior foundation
ended ~+38 commits behind the line it forked from. With `N = 25`, that base would
have first tripped the gate the moment `origin/main` advanced to **+26** — i.e.
*inside a single sprint's normal lifetime*, long before +38 made the branch
unmergeable. The budget is deliberately generous enough for normal multi-day
parallel work (a sprint that absorbs ~20 sibling commits stays green) yet strictly
below the distance at which the prior stranding became terminal:

```
prior stranding distance : ~+38 commits behind
chosen budget N          :  25
first red at              :  +26  ( = N + 1 )
margin before terminal    :  38 − 26 = 12 commits of warning
```

The 12-commit margin is the warning window: from +26 onward every PR is red until
the author rebases, so a branch physically cannot reach +38 unnoticed.

**Reconsider-if.**
- **Raise N** only if a *measured majority* of legitimate PRs trip the gate
  (i.e. +26 is being hit routinely by healthy parallel work, not by stranding).
  The fix for that is faster integration cadence first; raising N is the last
  resort, and only with the measured PR-trip rate recorded here.
- **Lower N** if a stranding still slips through under the current budget — i.e.
  a branch reaches an unmergeable distance without the gate having red-flagged it
  in time to act. That would mean +26 warned too late; lower N and re-derive the
  margin arithmetic above.

## Reachability gate — what is enforcing vs advisory

The reachability gate promotes to **enforcing** only the half of "anti-purgatory"
that has a concrete static signature, leaving the product-judgment half advisory.

**Promoted to enforcing (mechanically detectable):**
- a NEW **zero-importer module** — a source module that nothing imports; and
- a NEW **no-inbound-link route** — a route with no inbound navigation reference
  *that the scan can match*.

The zero-importer check is statically decidable (resolve every importer; a NEW
module with zero is a violation). The route check is **ENFORCING for the nav
forms the scan matches** — JSX `to=` / `href=` / `navigate("…")` and
config-object `to:` / `path:` / `route:` **string-literal** keys. Both block the
PR with a `path:line: message`.

The route scan is sound only over those literal nav forms. It does **not** see
genuinely computed or variable navigation — `navigate(pathVar)`, `to={expr}`,
paths assembled from constants — nor template-expression paths nor barrel
indirection (per the gate's CANNOT-catch list). Routes reached only by such
navigation are **not statically matchable**, so they are grandfathered with a
one-line justification and are **review-owned** — the same boundary the
CANNOT-catch list draws everywhere else.

**Left advisory (product judgment, not statically decidable):**
- "did this ship into the *production* surface rather than a prototype/playground
  reader?" — the judgment half of anti-purgatory.

### Relationship to `reading_physics_check.py` PR-7

`tools/lint/reading_physics_check.py` already named the **PR-7 anti-purgatory**
concern but implemented it as an **advisory grep only** — it scans augmentations
for an `import … from "…Prototype…"` / `…Playground…` specifier and warns, never
blocking, because "did this ship into the production surface?" was deemed "partly
a product judgment" (canon §7, §9 OQ 1). That file's own docstring is explicit:
"it never blocks on PR-7."

SPR-01's reachability gate is the **promotion of the statically-detectable core**
of that same PR-7 concern to enforcing: a module nothing imports, or a route
nothing links to, *is* dead-on-arrival regardless of product taste, and that has a
signature a scan can match. The unstructured "prototype vs production surface"
judgment — the part reading_physics_check.py left advisory — **stays advisory**;
SPR-01 does not promote it. So the two checks are complementary, not duplicative:
reading_physics_check.py keeps its advisory prototype-import grep; reachability
adds the blocking zero-importer / no-inbound-link check.

## Baseline burn-down rule — `reachability.json` is shrink-only

`tools/lints/baselines/reachability.json` grandfathers the modules/routes that
already had zero importers / no inbound link when the gate landed, so the gate
flags only **NEW** violations (the standard ARE-11 baseline-adoption pattern;
shared helper `tools/lints/baseline.py`).

**The baseline only ever shrinks.** An entry is removed when its underlying
violation is fixed (the module gains an importer, the route gains an inbound
link) — surfaced as a *stale* entry via `find_stale_baseline_entries` in
`tools/lints/baseline.py`. An entry is **never added** except by a deliberate,
reviewed `--write-baseline` re-mint. A baseline that *grew* (an extra entry whose
violation no longer exists, or that was never a real violation) is rejected as
stale: a grown baseline would silently re-grandfather a fresh dead module, which
is exactly the purgatory this gate exists to forbid.

This shrink-only rule is **enforced by a test**:
`tests/test_anti_stranding_gate.py` (the M5 deliverable of SPR-01) asserts that a
**grown** baseline (an extra entry whose violation no longer exists) is
rejected / flagged stale, and that a **shrunk** baseline (a fixed entry removed)
is accepted — reusing the `find_stale_baseline_entries` semantics from
`tools/lints/baseline.py`.

**The "keep it advisory" steelman, and the rebuttal.** *Steelman:* dead modules
and unlinked routes are cheap to leave lying around; a blocking gate adds friction
to every PR and risks false positives on intentionally-staged scaffolding, so it
should warn, not block — the same call `ci-informational-gates.md` made for the
latency/axe/lostpixel checks. *Rebuttal (dated 2026-05-31):* those three gates
were made informational because each red was *not a product-code defect* (runner
noise, Storybook infra, missing baselines) — the gate could not be trusted to red
only on real problems. The reachability gate is different in kind: a NEW
zero-importer module / no-inbound-link route *is* a real defect (it is the
purgatory that stranded the prior foundation), and the **shrink-only baseline
grandfathers every legitimate pre-existing case**, so a red means a route with no
nav reference the scan can match — usually a freshly-introduced dead route,
occasionally a live route reached only by computed navigation, which is
grandfathered with a one-line note. With the false-positive surface closed by the
baseline, the friction argument no longer outweighs the cost of the failure mode
it prevents — so this gate blocks, and any intentionally-staged scaffolding is
admitted by a reviewed `--write-baseline` re-mint, on the record, rather than by
silently swallowing the gate.

## Defensibility — surviving turnover

`N`, the +38 arithmetic, the enforcing-vs-advisory split, and the shrink-only
rule are recorded here (not only in code comments) so a future maintainer can
re-derive every threshold from first principles. The single source of truth for
`N` is the `MAX_BEHIND` constant in `tools/lint/merge_age_gate.py`; this doc
restates it and a test pins the two together.
