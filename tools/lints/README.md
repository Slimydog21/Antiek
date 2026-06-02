# `tools/lints/` — baselined lint + type gates

This directory holds the AST-level substrate lints and the **baselined**
`mypy --strict` + `ruff` gate that enforces the contract `pyproject.toml`
already declares. The baselines under `baselines/` are **allow-lists of
violations that already existed when the gate was turned on**. They exist
so a strict gate could be wired into CI without a flag-day block against
the pre-existing backlog.

## Burn-down discipline — the one rule: the allow-list SHRINKS ONLY

> **A baseline entry may be REMOVED (when you fix the violation). A
> baseline entry may NEVER be ADDED. The baseline may NEVER be re-minted
> to silence a NEW red. All new code is held to the full strict contract.**

This is the whole discipline. The baseline is debt made visible and
dated — not a place to park new debt. If the gate reds on your change,
the fix is to **fix the violation**, not to widen the allow-list.

### Why this rule, stated plainly

A strict contract that CI does not enforce is not a contract — it is a
comment. `pyproject.toml` declares `[tool.mypy] strict = true` and
`[tool.ruff.lint] select = E,F,I,B,UP,SIM,RET`, both with **no
`files=` / `exclude=` narrowing**, so by the plain reading the declared
scope is the entire repo (~1191 source files in the ruff scope as of the
2026-06-02 re-baseline). Enforcing that cold would
block every PR on the existing backlog — so instead we snapshot today's
violations into a dated baseline and gate **forward**: only violations in
code with no baseline entry red the build. The backlog then becomes a
visible, shrink-only list instead of silent rot.

(Steelman of the prior "pytest only … Defer" call in `ci.yml`: turning
strict on over 559 files on day one would have been pure flag-day pain
for no regression caught. The baseline keeps that same caution — zero
retroactive block — while still closing the declared-vs-enforced gap.)

## The dated baselines (snapshot: foundation-v2 rebase base `f9c8b50` + 2026-06-02 initial-floor re-baseline)

These two baselines are consumed by `tools/lints/declared_bar.py` and the
`.github/workflows/enforce_declared_bar.yml` job. Each carries its own
`generated_at` timestamp inside the file.

| Baseline file | Tool | Violations at snapshot |
|---|---|---|
| `baselines/declared_ruff.json` | `ruff check` (declared `[tool.ruff.lint]` scope, whole repo) | **685** |
| `baselines/declared_mypy.json` | `mypy --strict` (declared `[tool.mypy]` packages) | **1665** |

That `685 + 1665` is the **honest size of the typing/lint debt** as of
the 2026-06-02 re-baseline. It is recorded here, in each baseline's
`generated_at` field, and in the sprint handoff packet. It is not rounded
down and the declared config was not loosened to make it look smaller —
on the contrary, the ruff floor was *shrunk* by removing the debt (see
the "Initial-floor re-baseline" section below for why the ruff number
dropped from its draft 4541/4792 and the mypy number rose from 1185).

(The substrate-specific baselines `baselines/no_raise.json`,
`baselines/bypass.json`, `baselines/mypy_strict_substrate_core.json` are
the older ARE-11 substrate-floor allow-lists consumed by
`substrate_floor.yml`; the same shrink-only rule applies to them.)

### Initial-floor re-baseline (2026-06-02 · foundation-merge event)

**This is the single, explicit, named exception to the never-grow rule —
the one-time establishment of the floor on the tree the gate actually
goes live on. SHRINK-ONLY applies strictly before and after; this section
documents the one grow and why it is legitimate.**

The gate was drafted against `origin/main @ 5413fdc` (2026-05-29) and its
baselines minted there. By the time it was rebased to go live it sat on a
tree ~167 commits later (the foundation-v2 merge base `f9c8b50`): the
draft baselines were stale, and the **honest** way to re-establish the
floor was *not* to recapture both as-is (mypy would have silently grown,
ruff would have grown too). Instead:

- **RUFF — shrunk, not grown (compliant).** ~87% of the raw ruff findings
  were `ruff check --fix`-able safely (behavior-preserving: import-sort
  `I001`, PEP585 `UP006`, `X | None` `UP045`, `datetime.UTC` alias
  `UP017`, quoted-annotation `UP037`, redundant `open` mode `UP015`, …).
  Those were auto-fixed in a separate reviewable commit
  (*"modernize(lint): ruff safe autofixes …"*) across 784 source files,
  so the ruff baseline minted **smaller** — **4541/4792 (draft) → 685** —
  a genuine debt removal, exactly the shrink direction the rule wants. The
  autofix deliberately **did not touch the money path** (the
  `payout`/`stripe_connect`/`compute.py` files were reverted out of the
  autofix commit; their pre-existing ruff findings remain baselined rather
  than rewritten).
- **MYPY — grown ONCE (the legitimate exception).** `mypy --strict` debt
  (`type-arg`, `no-untyped-def`, `no-any-return`, …) is **not** safely
  auto-fixable in one PR, and this gate has **never been live on main** —
  so there was no prior enforced floor to ratchet down from. The mypy
  floor therefore grows once, **1185 → 1665 (+480)**, to cover the
  foundation-merge type debt that accumulated over those ~167 commits.
  This is the *initial floor*, not a silenced regression. From here it is
  shrink-only like everything else.

Both baselines were minted on the **pinned toolchain** the CI job installs
(`ruff==0.15.15`, `mypy==2.1.0`, CPython 3.14) with the venv tools first on
`PATH` (a stray PATH `mypy` would mint the wrong set). `pyproject.toml`'s
`[tool.ruff] target-version` and `[tool.mypy] python_version` were aligned
`py311 → py314` to match the CI runner + dev interpreter — at `py311` ruff
emitted a phantom `invalid-syntax` on a valid 3.12+ backslash-in-f-string
(`roles/note_taker/distill.py`). That is a tooling-target alignment, **not**
a scope narrowing: no `files=`/`exclude=` was added and the ruff `select` /
mypy `strict` are unchanged (G5).

### Reproduction provenance — what was actually run (2026-05-29)

The "reproduces byte-for-byte" claim below is not an assertion; it was
**verified locally in a CI-equivalent environment** before this sprint
shipped — pinned `ruff==0.15.15` + `mypy==2.1.0` (the workflow pins),
CPython 3.14 (the runner interpreter), and the **full extras superset the
workflow installs** under the pinned lock:

```bash
python3.14 -m venv .venv && . .venv/bin/activate
pip install -c tools/lints/constraints.txt \
    -e '.[dev,arxiv,pdf,urls,embedding,youtube,rss]'
pip install -c tools/lints/constraints.txt ruff==0.15.15 mypy==2.1.0
```

This is the EXACT extras set the workflow installs (no longer a subset —
the earlier capture had dropped the torch-bearing `embedding`/`youtube`
extras "to verify locally"; this round installed and verified the full
superset, so the residual is no longer "unverified on the workflow's
actual extras"). It was run twice: once in the venv the lock was frozen
from, and once in a **fresh clean-room venv installed via the `-c` lock
above** — both green.

| Gate run against the unmodified committed tree (full superset + lock) | Result |
|---|---|
| `enforce ruff` | 4541 current == 4541 baseline · **0 NEW · 0 STALE · rc 0** |
| `enforce mypy` | deduped current set == 1185 baseline set · **0 NEW · 0 STALE · rc 0** |

This is the **G2 "green on HEAD"** contract, observed — not simulated.
The 137 `import-*` baseline keys (116 `import-not-found` + 21
`import-untyped`) and the 230 `unused-ignore` keys are the most
environment-sensitive; with the full install above they reproduced
exactly, neither resolving away (which would make them STALE — harmless,
the CI gate omits `--check-stale`) nor surfacing a shadowed NEW error at
the same site. In particular the torch-bearing extras did **not** shadow a
different error at any baselined mypy site. The **G4 non-vacuity** pair was
likewise observed against a confirmed-clean non-baselined file
(`substrate/contracts/note_taker.py`, `grep -c` = 0 in both baselines):
with an injected `F401` + a `return-value` type error both gates RED and
named the violation (`rc 1`); reverted, both GREEN (`rc 0`).

#### Why the lock — the install-set sensitivity, demonstrated

The mypy gate's findings depend on the **exact installed dependency set**,
because `mypy --strict` resolves the real import graph. This is not
hypothetical — it was reproduced as a **negative control**: installing
only `.[dev]` (the extras `arxiv`/`pdf`/`urls`/`rss` missing) made the
mypy gate report **11 spurious NEW violations** and red (`rc 1`) on the
unmodified clean tree:

```
acquisition/urls/extract.py:113,116,119,131,136,139  NEW mypy:no-any-return
acquisition/books/reader.py:186                       NEW mypy:unused-ignore
substrate/graph/rlm_tools.py:209                      NEW mypy:arg-type
substrate/research_bridge/extractors.py:99,105,115    NEW mypy:import-not-found
```

None of these is a real regression — each is an artifact of a missing
import. They cleared to **0 NEW** only once the extras were installed. So:

- A **missing extra** can flip a baselined key NEW → the workflow installs
  the **full extras superset** `.[dev,arxiv,pdf,urls,embedding,youtube,rss]`.
- **Transitive-pin drift** (a later resolve of a different `numpy`/`torch`/
  `pydantic`/…) could shadow a different error at a baselined site → the
  workflow installs that superset **under `tools/lints/constraints.txt`**,
  a `pip freeze` of the exact resolved set the baselines were captured
  against. This is the lock that makes the gate's import graph reproducible
  rather than "whatever the resolver picks today."

**The one residual, stated honestly.** A *local* CI-equivalent run is not
the *GitHub Actions* run itself, and the lock was frozen on macOS arm64
while the runner is ubuntu-latest. The lock pins **versions**, which exist
on PyPI for both platforms; `-c` only constrains a package if it is
installed, so platform-only wheels that don't resolve on ubuntu are simply
left unconstrained (not an install failure). The lock makes a baselined key
flipping NEW on the runner *unlikely* — it can no longer be caused by
transitive float — but not *impossible* (e.g. a platform-specific typing
stub difference). If it ever happens, that is the intended bite: the fix is
to fix the violation or, only if it is a genuine environment artifact,
re-capture the baseline **and** re-freeze the lock in the same PR
(shrink-only for the baseline). **The final confirmation point for G2/G4 is
the `enforce-declared-bar` job going green on the integrating PR's own
ubuntu-latest/py3.14 runner — that run is the binding G2 evidence.**

## Known limitation — mypy and ruff do NOT cover the same scope

These two gates do not enforce over an identical file set, and the
`(~1191 source files)` whole-repo framing above is the *ruff* scope, not
the mypy scope (mypy covers the 10 declared wheel packages). This is a
deliberate, documented asymmetry — not an accident — but it is a real
enforcement hole, so it is stated plainly here:

| Gate | What it covers | Top-level dirs |
|---|---|---|
| **ruff** | the whole repo via ruff's own pyproject file discovery (no path arg, no `exclude`) | `substrate`, `skills`, `acquisition`, `processing`, `roles`, `middleware`, `orchestration`, `interfaces`, `compounding`, `runtime`, **plus** `tools`, `tests`, `scripts`, `benchmarks`, `antiek_extensions`, `apps` |
| **mypy** | exactly the 10 declared wheel packages in `DECLARED_MYPY_TARGETS` | `substrate`, `skills`, `acquisition`, `processing`, `roles`, `middleware`, `orchestration`, `interfaces`, `compounding`, `runtime` |

**Why mypy is package-scoped and not whole-tree.** `[tool.mypy]` declares
`strict = true` with **no `files=`**, so mypy needs an explicit target to
run at all. We pass the `[tool.hatch.build.targets.wheel] packages` list —
the authoritative statement of what code the project *ships*. That is
strictly broader than the rejected `substrate_floor` 3-file pattern and is
kept honest by a CI-enforced cross-check
(`tests/test_declared_bar.py::test_mypy_targets_match_wheel_packages`),
which fails if `DECLARED_MYPY_TARGETS` ever drifts from the wheel list.

**The hole this leaves.** New *untyped* code added under `tools/`,
`tests/`, `scripts/`, `benchmarks/`, `antiek_extensions/`, or `apps/`
escapes the strict **type** gate (ruff still lints it; mypy does not
type-check it). Likewise, **a brand-new top-level directory** that is not
also a wheel package gets ruff coverage but **no mypy coverage** until it
is added.

**The rule that follows.** When you add a new top-level package that the
project ships, add it to the wheel-package list in `pyproject.toml` —
which forces you (via the cross-check test) to also add it to
`DECLARED_MYPY_TARGETS` in `tools/lints/declared_bar.py`, and to
re-capture `baselines/declared_mypy.json` so the new package's existing
violations are baselined. A new *non-package* top-level dir that you want
type-checked must be added to `DECLARED_MYPY_TARGETS` deliberately (the
cross-check would then need updating, since it would no longer be a pure
wheel-package mirror). Until that happens, treat type-coverage of
non-package dirs as a known gap, not an enforced bar.

## How to REMOVE an entry (the only legal mutation)

1. Fix the underlying violation in the source file.
2. Re-run the gate locally:

   ```bash
   # ruff (no path arg — declared whole-repo scope):
   python -m tools.lints.declared_bar enforce ruff \
       --baseline-file tools/lints/baselines/declared_ruff.json --check-stale
   # mypy --strict (declared packages):
   python -m tools.lints.declared_bar enforce mypy \
       --baseline-file tools/lints/baselines/declared_mypy.json --check-stale
   ```

   With `--check-stale`, a fixed violation shows up as a **stale baseline
   entry** — proof the floor can ratchet down.
3. Re-capture to drop the now-stale entries (this is the **only** time
   `capture` is legitimate — and it must result in a baseline that is a
   strict subset of the previous one):

   ```bash
   python -m tools.lints.declared_bar capture ruff \
       --baseline-file tools/lints/baselines/declared_ruff.json
   python -m tools.lints.declared_bar capture mypy \
       --baseline-file tools/lints/baselines/declared_mypy.json
   ```
4. Commit the shrunken baseline **in the same PR** as the fix. A reviewer
   confirms the baseline got smaller, never larger.

## Re-capturing to silence a NEW red is FORBIDDEN

`capture` regenerates the baseline from the current tree, so running it
after introducing a new violation would "fix" the red by grandfathering
the new violation. **That is exactly the abuse this rule prohibits.**
`capture` is legal only as step 3 above — to drop entries you have
genuinely fixed — and the result must be a strict subset of what was
there before. If a PR's diff makes a baseline file *grow*, that PR is
wrong: revert the baseline and fix the code.

Tool versions are pinned in the workflow (`RUFF_VERSION` / `MYPY_VERSION`)
**and the full transitive set is pinned in `tools/lints/constraints.txt`**
so the committed baseline reproduces in CI rather than against "whatever the
resolver picks today" (mypy resolves the real import graph, so the resolved
dependency set — not just the tool versions — determines its findings).
Bumping a tool pin, adding an extra, or otherwise changing what gets
installed is a deliberate change that must re-capture the matching baseline
**and** re-freeze `constraints.txt` in the same PR — and, like every
capture, only ever to shrink the baseline floor. See the header of
`constraints.txt` for the freeze command and the `-c` semantics that keep
the macOS-frozen lock safe to apply on the ubuntu runner.
