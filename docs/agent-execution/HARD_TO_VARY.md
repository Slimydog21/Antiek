# Hard-to-Vary Agent Execution Protocol

**Status:** Active — ANT-H2V SPR-01 (2026-06-02)  
**Spec:** `docs/htmlspec/antiek-hard-to-vary-execution/` (platform envelope)  
**Templates:** `docs/agent-execution/TEMPLATES.md`

Every Antiek agent session that touches code or claims verification **must** follow Phase A→E in order. Skipping a phase or substituting theater for a gate is an automatic fail on adversarial re-read.

---

## Historical failures (lineage)

Brief anchors. Read the cited paths before claiming closure on the same surface.

| Case | What failed | Load-bearing paths |
|------|-------------|-------------------|
| **Egghead** | Correct cascade root cause, then easy-to-vary closure: truncated pytest from wrong cwd/venv, “platform OK” without rows | `docs/specs/ant-h2v/grok-execution-brief.md`, `docs/htmlspec/antiek-hard-to-vary-execution/index.html` |
| **Cascade** | `DispatchDecomposer` keyword contract: positional `render_full_prompt` / `dispatch` without `investigation_id` → pre-network `TypeError` → HTTP 500 | `roles/cascade_planner/planner.py`, `roles/decomposer/prompt.py`, `substrate/dispatch/router.py`, `interfaces/research/api/cascade_routes.py`, `tests/test_cascade_create_plan_light.py` |
| **AMS-v1** | Sprint pages cited fictional UI (`#scene-root` fiction, `components/ProductsLauncher.tsx`, `scene/index.ts`) — “green” without verified DOM | `docs/ams-v2/verified-interfaces.md` (anti-fiction ledger), `tools/specs/verify_spec_refs.ts`, `docs/ams-v2/mountain-shell-v2-verification.md` |
| **Werner** | Mascot / ice-cursor claims without p95 lag artifact or operator acceptance; hop-delay theater (~4.5s class) | `docs/htmlspec/werner-ice-fishing-cursor/index.html`, `docs/htmlspec/werner-ice-fishing-cursor/operator-acceptance.md`, `apps/reading/src/werner/`, postmortem commit `ccb4c66` |

**Egghead cascade detail (contract bug, real):** `DispatchDecomposer.decompose` called `render_full_prompt(question)` and `dispatch(prompt, role="decomposer")` against keyword-only signatures (`roles/decomposer/prompt.py`, `substrate/dispatch/router.py:301`). **LLM contacted on failure path: no.**

**Load-bearing path (cascade auto-decompose):**

```
Reading UI → POST /research/plans (omit sub_questions)
  → _decompose() → DispatchDecomposer.decompose
  → render_full_prompt(*, investigation_id=…, question=…, context=…)
  → dispatch(…, role="decomposer", investigation_id=…)
  → parse_decomposer_response → build_plan → persist_tree
```

Parallel path (out of ANT-H2V scope unless matrix row says otherwise): Loop1 `POST /investigations` → event bus decomposer handler.

**Invariant:** Pre-network `TypeError` on auto-decompose ⇒ Python contract bug, not “provider down.” `FakeDecomposer` tests prove tree logic only — not `DispatchDecomposer`.

**Collection hazard (cascade tests):** importing `interfaces.research.api.cascade_routes` while `api/__init__.py` eagerly loads `app.py` can hang collection; prefer light router mounts (`tests/test_cascade_create_plan_light.py`).

---

## Phase A — Contract lock

**Goal:** Lock Python contracts from **source**, not memory, before any fix narrative.

| Step | Action | Done when |
|------|--------|-----------|
| A1 | `inspect.signature` on load-bearing callables | Signatures pasted in Failure Dossier |
| A2 | Numbered failure chain for the reported bug | Each hop has `file:line` + exception type |
| A3 | No-network repro when sprint provides one (e.g. `scripts/repro_cascade_decompose_contract.py`) | Exit code recorded verbatim in handoff |
| A4 | State whether an LLM was contacted on the failure path | `LLM contacted: yes \| no` |

**Pass:** Repro (if applicable) green **and** dossier cites lines that match current tree.  
**Fail:** “Looks fixed in planner” without signature evidence; repro skipped because “we already know.”

Repro passing **does not** prove live decompose or provider health — only that keyword contracts match the fix.

---

## Phase B — Scope map

**Goal:** Replace platform slogans with a **bounded** entry-point map before writing tests or claiming parity.

| Step | Action | Done when |
|------|--------|-----------|
| B1 | List every entry point for the claimed surface | One row per path |
| B2 | Per row: `tested \| untested \| live-LLM-required` | No empty status |
| B3 | Per row: evidence (`test_file:line` or `file:line` + rationale) | No “tested” without file reference |
| B4 | Mark in-scope vs out-of-scope for **this** sprint | Temptations logged, not silently expanded |

Use the Scope Map template (`TEMPLATES.md`). SPR-10 fills `docs/agent-execution/PLATFORM_EXEC_MATRIX.md`; until then, the handoff Scope Map section is mandatory.

**Pass:** Another agent can answer “what did we prove?” from the table alone.  
**Fail:** “Platform OK,” “all paths work,” or “engine fine” without rows.

---

## Phase C — Fix + regression

**Goal:** Ship the fix **and** a hermetic regression that fails if the contract regresses.

| Step | Action | Done when |
|------|--------|-----------|
| C1 | Minimal fix at the correct layer (API boundary vs adapter per merge-bar) | Diff scoped; no drive-by refactors |
| C2 | Hermetic test imports **production** adapter (not only fakes) | Test stubs seams / asserts kwargs |
| C3 | Route-visible branch test when bug is HTTP-visible | Branch covered or deferred with row = `untested` |
| C4 | Merge-bar: non-test production changes have tests | Named pytest in handoff Gate results |

**Pass:** Removing the new test (or reverting kwargs) reproduces failure mode in principle.  
**Fail:** Only fake/stub coverage for a production-adapter bug; fix “verified” by reading source once.

**xfail rule:** Any `xfail` must pair with a regression fixture that fails if the guard is removed (see `docs/decisions/spr-09-boundary-lint-vs-import-linter.md` — `_with_xfail_bite_test`). Bare xfail is F6.

---

## Phase D — Canonical verify

**Goal:** One **canonical** command block per session — correct repo root, `.venv` interpreter, full exit codes — recorded in the Env Card and handoff.

```bash
cd /path/to/Antiek   # repo root — must match Env Card pwd
pwd
.venv/bin/python -V

.venv/bin/python scripts/repro_cascade_decompose_contract.py   # when sprint names it
.venv/bin/python -m pytest tests/test_cascade_planner.py -k dispatch_decomposer tests/test_cascade_create_plan_light.py -q --tb=short
bash scripts/audit_decomposer_call_sites.sh   # when sprint names it
```

Adjust paths/tests when the sprint spec names different gates; **never** replace this block with ad-hoc one-liners only.

| Step | Action | Done when |
|------|--------|-----------|
| D1 | Env Card filled (pwd, python path, version, commit SHA) | Paste in every handoff |
| D2 | Each gate: command + exit + log path | Gate results table complete |
| D3 | Full pytest output retained for disputes; `tail` not sole artifact | See F1 |

Live provider checks (`docs/agent-execution/OPERATOR_VERIFY_CASCADE_DECOMPOSE.md`, Werner operator-acceptance) are **separate** from D — contract-green ≠ provider-green.

---

## Phase E — Bounded closure

**Goal:** Close with claims that **collapse** if any row, test, or gate is removed.

**Case study (required read for cascade / Egghead lineage):** [`cascade-case-study.md`](cascade-case-study.md) — Egghead session, `TypeError` vs provider-down, `FakeDecomposer` vs `DispatchDecomposer`, `repro_cascade_decompose_contract.py`, gate table with real commands, Werner `ccb4c66` / `useMouseFollow` hop parallel.

| Step | Action | Done when |
|------|--------|-----------|
| E1 | Platform matrix (or handoff Scope Map) has every row filled | No empty `tested` without evidence |
| E2 | Handoff `### Not proved` lists what closure does **not** cover | Before `### Status` |
| E3 | Handoff packet complete (all headings; `N/A — reason` if needed) | Matches `TEMPLATES.md` |
| E4 | Steelman fastest path (“looks right, ship”) and what it loses | Regression, scope map, operator trust; cite case study §1 / §9 where Egghead/Werner theater applies |

**Pass:** Adversarial reader can falsify each claim via matrix row or cited test.  
**Fail:** Superlatives (“fully fixed,” “production ready,” “CI green” for serve/rights) without named blocking jobs and matrix backing.

---

## Forbidden patterns (binary audit)

An auditor marks **FAIL** if any row is true for the session under review.

| # | Pattern | Why it’s easy-to-vary | Lineage |
|---|---------|----------------------|---------|
| F1 | `pytest … 2>&1 \| tail -N` (or repeated truncated runs) as **sole** sign-off | Hides collection errors, wrong cwd, wrong interpreter | Egghead cascade session |
| F2 | Wrong venv or cwd — system `python` (e.g. 3.9), pytest from subdirectory without repo-root config | Tests pass or fail for the wrong environment | Egghead; `scripts/canonical_verify.sh` (SPR-08) |
| F3 | **Unbounded platform OK** — “engine fine across platform” without Scope Map / PLATFORM_EXEC_MATRIX | Claim survives deleting all evidence | Egghead; AMS-v2 “green & invisible” (`docs/htmlspec/antiek-hard-to-vary-execution/index.html`) |
| F4 | Deleting template headings in handoff instead of `N/A — reason` | Hides skipped diligence | `tools/agent/verify_handoff.ts` (SPR-03) |
| F5 | **Invented metrics** — p95, fps, cost, “CI green” for serve/rights without measured artifact or named blocking job | Remove the number; story unchanged | Werner SPR-07; AMS-v2 `mountain-shell-v2-verification.md` |
| F6 | `xfail` / skip without regression fixture that bites if guard removed | Guard rots; looks covered | `docs/decisions/spr-09-boundary-lint-vs-import-linter.md` |
| F7 | **Informational CI as legal proof** — latency, Lost-Pixel, axe warn-only treated as blocking serve/rights/craft closure | `::warning::` survives; product claim does not | `docs/decisions/ci-informational-gates.md` |
| F8 | **Ambiguous deferral IDs** — bare `D17` without `engineering_deferrals.md:L###` @ commit SHA | Reader cannot find the deferral cluster | `docs/engineering_deferrals.md` (D17 ≈ L475+, Personal-Reading live-ingest) |

**Additional fails (cite in case study; audit as F-equivalent, not optional):** “Provider down” when repro shows pre-network `TypeError`; sprint done with only `FakeDecomposer` for a `DispatchDecomposer` bug (`roles/cascade_planner/planner.py`); **memory-without-test** — closure from training-data recall or “I read the file” without `inspect` signatures, repro exit codes, or a named pytest row in the Scope Map.

---

## Session checklist (quick)

```
[ ] A  Contract lock — signatures, dossier, repro exit 0, LLM contacted stated
[ ] B  Scope map — all entry points rowed; no platform slogans
[ ] C  Fix + regression — production adapter + route branch as spec requires
[ ] D  Canonical verify — Env Card + Gate results (command, exit, log path)
[ ] E  Bounded closure — Not proved; matrix/handoff; steelman
[ ] —  Zero forbidden patterns (F1–F8)
```

---

## Related artifacts (ANT-H2V)

| Sprint | Artifact |
|--------|----------|
| SPR-01 | This file + `TEMPLATES.md` |
| SPR-02 | Theater taxonomy + repro scripts |
| SPR-03–04 | `verify_handoff.ts`, `audit_agent_session.sh` |
| SPR-05 | `AMS_BRIDGE.md`, `scripts/agent_ams_ref_lint.sh`, `tools/ams-v2/ref-lint.sh` |
| SPR-06 | [`cascade-case-study.md`](cascade-case-study.md) |
| SPR-07 | Werner operator-acceptance + H2V handoff gates |
| SPR-08–10 | `canonical_verify.sh`, CI wiring, `PLATFORM_EXEC_MATRIX.md` |

Executors cite this file **before** touching cascade code, AMS surfaces, Werner mascot paths, or closing any investigation that claims verification.