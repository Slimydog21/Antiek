# Hard-to-Vary Agent Execution Protocol

**Status:** Active — ANT-H2V SPR-01 (2026-06-02)  
**Spec:** `docs/specs/ant-h2v/` (master: cascade auto-decompose closure)  
**Templates:** `docs/agent-execution/TEMPLATES.md`

Every Antiek agent session that touches code or claims verification **must** follow Phase A→E in order. Skipping a phase or substituting theater for a gate is an automatic fail on adversarial re-read.

---

## Why this exists (egghead grounding)

A prior sub-questions session found the **correct root cause** — `DispatchDecomposer` raised `TypeError` before any provider call — then closed with **easy-to-vary** verification:

1. **Contract bug (real):** `DispatchDecomposer.decompose` called `render_full_prompt(question)` positionally and `dispatch(prompt, role="decomposer")` without `investigation_id`. Both signatures are keyword-only (`roles/decomposer/prompt.py:123`, `substrate/dispatch/router.py:301`). Result: `TypeError` → `_decompose` failure → HTTP 500 → Reading UI “no result.” **LLM contacted: no.**

2. **Theater (repeatable, falsifiable):** ~50× `pytest … 2>&1 | tail -N` from the wrong directory or system `python` (3.9), truncated output treated as pass/fail.

3. **Unbounded closure:** “Engine fine across platform” with no entry-point matrix, no test file per path, no `tested | untested | live-LLM-required` row.

Remove the pytest repetition or the platform slogan — the “we’re done” story **does not change**. That pattern is what this protocol forbids.

**Load-bearing path (cascade auto-decompose):**

```
Reading UI → POST /research/plans (omit sub_questions)
  → _decompose() → DispatchDecomposer.decompose
  → render_full_prompt(*, investigation_id=…, question=…, context=…)
  → dispatch(…, role="decomposer", investigation_id=…)
  → parse_decomposer_response → build_plan → persist_tree
```

Parallel path (out of ANT-H2V scope unless matrix row says otherwise): Loop1 `POST /investigations` → event bus decomposer handler (already keyword-correct).

**Invariant:** Pre-network `TypeError` on auto-decompose ⇒ Python contract bug, not “provider down.” `FakeDecomposer` tests prove tree logic only — not `DispatchDecomposer`.

---

## Phase A — Contract lock

**Goal:** Lock Python contracts from **source**, not memory, before any fix narrative.

| Step | Action | Done when |
|------|--------|-----------|
| A1 | `inspect.signature` on `render_full_prompt`, `dispatch`, `DispatchDecomposer.decompose` | Signatures pasted in Failure Dossier or handoff |
| A2 | Numbered failure chain for the reported bug | Each hop has file:line + exception type |
| A3 | No-network repro (SPR-02: `scripts/repro_cascade_decompose_contract.py`) | Exit 0 recorded verbatim in handoff |
| A4 | State explicitly whether an LLM was contacted on the failure path | `LLM contacted: yes \| no` |

**Pass:** Repro script green **and** dossier cites lines that match current tree.  
**Fail:** “Looks fixed in planner” without signature evidence; repro skipped because “we already know.”

Repro passing **does not** prove live decompose or provider health — only that keyword contracts match the fix.

---

## Phase B — Scope map

**Goal:** Replace platform slogans with a **bounded** entry-point map before writing tests or claiming parity.

| Step | Action | Done when |
|------|--------|-----------|
| B1 | List every decompose entry point (HTTP auto, manual `sub_questions`, event bus, gap/note planners, etc.) | One row per path |
| B2 | Per row: `tested \| untested \| live-LLM-required` | No empty status |
| B3 | Per row: evidence (`test_file:line` or `file:line` + rationale) | No “tested” without file reference |
| B4 | Mark in-scope vs out-of-scope for **this** sprint | Temptations logged, not silently expanded |

Use the Scope Map template (`TEMPLATES.md`). SPR-08 fills `docs/specs/ant-h2v/PLATFORM_MATRIX.md`; until then, the handoff Scope Map section is mandatory.

**Pass:** Another agent can answer “what did we prove?” from the table alone.  
**Fail:** “Platform OK,” “all paths work,” or “engine fine” without rows.

---

## Phase C — Fix + regression

**Goal:** Ship the fix **and** a hermetic regression that fails if the contract regresses.

| Step | Action | Done when |
|------|--------|-----------|
| C1 | Minimal fix at the correct layer (API boundary vs adapter per merge-bar) | Diff scoped; no drive-by refactors |
| C2 | Hermetic test imports **production** `DispatchDecomposer` (not only `FakeDecomposer`) | Test stubs `dispatch` / asserts kwargs |
| C3 | HTTP branch test when the bug is route-visible (omit `sub_questions`) | Branch covered or explicitly deferred with row = `untested` |
| C4 | Merge-bar: non-test production changes have tests | CI-local pytest named in handoff |

**Pass:** Removing the new test (or reverting kwargs) reproduces failure mode in principle.  
**Fail:** Only `FakeDecomposer` tests; fix “verified” by reading `planner.py` once.

---

## Phase D — Canonical verify

**Goal:** One **canonical** command block per session — correct repo root, `.venv` interpreter, full exit codes — recorded in the Env Card and handoff.

```bash
cd /path/to/Antiek   # repo root — must match Env Card pwd
pwd
.venv/bin/python -V

.venv/bin/python scripts/repro_cascade_decompose_contract.py
.venv/bin/python -m pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response tests/test_cascade_create_plan_light.py -q --tb=short
bash scripts/audit_decomposer_call_sites.sh
```

Adjust paths/tests when the sprint spec names different gates; **never** replace this block with ad-hoc one-liners only.

| Step | Action | Done when |
|------|--------|-----------|
| D1 | Env Card filled (pwd, python path, version, commit SHA) | Paste in every handoff |
| D2 | Each gate: command + exit code + one-line outcome | No gate ommitted as “same as before” |
| D3 | Full pytest output retained for disputes; `tail` not used as sole artifact | See forbidden list |

Live provider checks (SPR-07 operator card) are **separate** from D — contract-green ≠ provider-green.

---

## Phase E — Bounded closure

**Goal:** Close with claims that **collapse** if any row, test, or gate is removed.

| Step | Action | Done when |
|------|--------|-----------|
| E1 | `PLATFORM_MATRIX.md` (or equivalent) has every row filled | SPR-08 gate |
| E2 | Closure sentence names what is **not** proved | e.g. bus parity, live LLM on all paths |
| E3 | Handoff packet complete (all headings; `N/A — reason` if needed) | Matches `TEMPLATES.md` Handoff Packet |
| E4 | Steelman fastest path (“looks right, ship”) and what it loses | Regression, scope map, operator trust |

**Pass:** Adversarial reader can falsify each claim via matrix row or cited test.  
**Fail:** Superlatives (“fully fixed,” “production ready,” “all platforms”) without matrix backing.

---

## Forbidden patterns (binary audit)

An auditor marks **FAIL** if any row is true for the session under review.

| # | Pattern | Why it’s easy-to-vary |
|---|---------|------------------------|
| F1 | `pytest … 2>&1 \| tail -N` (or repeated truncated runs) as **sole** sign-off | Hides collection errors, wrong cwd, wrong interpreter |
| F2 | System `python` / wrong venv (e.g. 3.9) while repo expects `.venv/bin/python` | Tests pass or fail for the wrong environment |
| F3 | Wrong `cd` — pytest from subdirectory without repo-root `PYTHONPATH`/config | False green or false red |
| F4 | Importing `interfaces.research.api.cascade_routes` while `api/__init__.py` eagerly loads `app.py` | Collection hangs minutes; kill stale `pytest` first |
| F4 | **Memory-without-test** — signature or behavior from training weights, not `inspect` + test | Regresses silently on next edit |
| F5 | **Unbounded platform OK** — “engine fine across platform” without Scope Map / PLATFORM_MATRIX | Claim survives deleting all evidence |
| F6 | Deleting template headings in handoff instead of `N/A — reason` | Hides skipped diligence |
| F7 | “Provider down” as first diagnosis when repro shows pre-network `TypeError` | Misroutes operator time |
| F8 | Declaring sprint done with only `FakeDecomposer` coverage for a `DispatchDecomposer` bug | Production adapter untested |

---

## Session checklist (quick)

```
[ ] A  Contract lock — signatures, dossier, repro exit 0, LLM contacted stated
[ ] B  Scope map — all entry points rowed; no platform slogans
[ ] C  Fix + regression — production adapter + HTTP branch as spec requires
[ ] D  Canonical verify — Env Card + full gate commands + exit codes
[ ] E  Bounded closure — matrix/handoff; steelman; explicit not-proved
[ ] —  Zero forbidden patterns (F1–F8)
```

---

## Related artifacts (ANT-H2V)

| Sprint | Artifact |
|--------|----------|
| SPR-01 | This file + `TEMPLATES.md` |
| SPR-02 | `scripts/repro_cascade_decompose_contract.py`, failure dossier |
| SPR-03–04 | Hermetic pytest for adapter + HTTP branch |
| SPR-05–06 | API error boundary + audit script |
| SPR-07 | `OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` (live LLM once) |
| SPR-08 | `PLATFORM_MATRIX.md`, `CLOSURE_DOSSIER.md` |

Executors cite this file **before** touching cascade code or closing a sub-questions / decompose investigation.