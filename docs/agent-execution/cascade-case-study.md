# Case study — Egghead cascade closure + Werner hop theater (`ccb4c66`)

**Status:** ANT-EXEC-H2V SPR-06 (2026-06-02)  
**Protocol:** `docs/agent-execution/HARD_TO_VARY.md`  
**Audience:** Any agent closing a cascade/decompose investigation or claiming platform-wide health.

This document is the **bounded narrative** behind Phase E closure. It ties together:

1. The **Egghead** sub-questions session — correct root cause, easy-to-vary verification.
2. The **cascade contract bug** — pre-network `TypeError`, not “provider down.”
3. **`FakeDecomposer` vs `DispatchDecomposer`** — what each test class actually proves.
4. **`scripts/repro_cascade_decompose_contract.py`** — hermetic contract lock.
5. **Werner `ccb4c66`** — parallel easy-to-vary pattern: hop-delay theater vs measured lag budget (`useMouseFollow` + roam **hop** chain).

---

## 1. Egghead session — correct diagnosis, fragile closure

**Symptom (operator):** Research UI shows “no result” when submitting a problem **without** manual `sub_questions[]`.

**What Egghead got right:** The failure is in the **auto-decompose** branch — `POST /research/plans` → `_decompose()` → `DispatchDecomposer.decompose` — not a generic “engine” outage.

**What Egghead got wrong (easy-to-vary):**

| Theater | Why it fails adversarial read | Forbidden pattern |
|---------|------------------------------|-------------------|
| ~50× `pytest … 2>&1 \| tail -80` from wrong cwd / system Python 3.9 | Truncation hides collection errors; wrong interpreter invalidates pass/fail | **F1**, **F2** |
| “Platform OK — engine fine across platform” with no entry-point rows | Delete the slogan; conclusion unchanged | **F3** |
| “Provider down” / “decomposer model broken” | `TypeError` fires **before** `dispatch` opens a socket | F-equivalent (see §2) |
| Closure after reading `planner.py` once, no named pytest on `DispatchDecomposer` | Memory-without-test | F-equivalent |

**Steelman fast path:** “Keyword fix is obvious; ship.”  
**What it loses:** Hermetic repro exit codes, `test_dispatch_decomposer_maps_stub_response`, light-router HTTP branch, and audit grep — any regression reopens HTTP 500 / “no result” without a failing gate.

Sources: `docs/specs/ant-h2v/index.html`, `docs/specs/ant-h2v/grok-execution-brief.md`, `docs/htmlspec/antiek-hard-to-vary-execution/index.html`.

---

## 2. Cascade — `TypeError` vs “provider down”

### Invariant

> Pre-network `TypeError` on auto-decompose ⇒ **Python contract bug**, not provider outage.  
> **`LLM contacted on failure path: no`**

### Numbered failure chain (pre-fix)

| # | Hop | Location | What happens |
|---|-----|----------|--------------|
| 1 | Trigger | `interfaces/research/api/cascade_routes.py` ~247–257 | `POST /research/plans` without `sub_questions[]` |
| 2 | Branch | `cascade_routes.py` ~108–112 | `_decompose()` → `build_plan(..., decomposer=DispatchDecomposer(), ...)` |
| 3 | Adapter | `roles/cascade_planner/planner.py` ~54–69 | `DispatchDecomposer.decompose` |
| 4a | Contract break | `roles/decomposer/prompt.py` 123–128 | `render_full_prompt(question)` positional — all user args are **keyword-only** after `*` |
| 4b | Contract break | `substrate/dispatch/router.py` 330–334 | `dispatch(prompt, role="decomposer")` omits required kw-only `investigation_id` |
| 5 | HTTP | FastAPI | Uncaught `TypeError` → **500** (or **502** `decompose_failed` after SPR-05 boundary) |
| 6 | UI | Reading client | Empty / error — “no result”; no persisted tree |

### Signatures (source, not memory)

```python
# roles/decomposer/prompt.py — keyword-only after *
def render_full_prompt(*, investigation_id: str, question: str, context: str = "", ...)

# substrate/dispatch/router.py — investigation_id kw-only
def dispatch(prompt: str, role: str, *, investigation_id: str, ...)
```

### Fix in tree (contract-correct)

```63:69:roles/cascade_planner/planner.py
        prompt = render_full_prompt(
            investigation_id=investigation_id,
            question=question,
            context=context,
        )
        result = dispatch(prompt, role="decomposer", investigation_id=investigation_id)
```

### Falsifiers

| Wrong claim | One-command falsifier |
|-------------|----------------------|
| “OpenAI/Anthropic is down” | `.venv/bin/python scripts/repro_cascade_decompose_contract.py` → `REPRO_OK` for **old** positional patterns **without network** |
| “Decomposer returned bad JSON” | Failure at prompt assembly / dispatch kwargs — no `parse_decomposer_response` input |
| “Tree planner is broken” | `FakeDecomposer` path never imports `DispatchDecomposer` (§3) |

Parallel path (different code, already keyword-correct): Loop1 `POST /investigations` → `make_decomposer_handler` in `interfaces/research/api/decomposer.py`. Do not conflate with cascade auto-decompose.

---

## 3. `FakeDecomposer` vs `DispatchDecomposer`

| | **`FakeDecomposer`** | **`DispatchDecomposer`** |
|---|------------------------|---------------------------|
| **File** | `tests/test_cascade_planner.py` (test double) | `roles/cascade_planner/planner.py` |
| **Calls** | In-memory dict → canned sub-questions | `render_full_prompt` + `dispatch` + `parse_decomposer_response` |
| **Proves** | Focus recursion, `MAX_BRANCHES`, gap/note seeds, approval gates | Production adapter kwargs + parse mapping |
| **Does not prove** | Keyword contracts, HTTP 500/502, provider health | Tree focus logic in isolation |

**Merge-bar violation:** Shipping a `DispatchDecomposer` fix with **only** `FakeDecomposer` coverage — the production adapter never ran.

**Required production test:** `tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response` — stubs `render_full_prompt` / `dispatch`, asserts `investigation_id` threading and four `SubQuestion` rows.

**HTTP branch (light router):** `tests/test_cascade_create_plan_light.py` mounts **only** `cascade_router` (avoids `app.py` collection hang). Note: auto-decompose test stubs `_decompose` with `_FixedDecomposer` to prove the **route branch** exists; production wiring is proven by the unit test + repro + audit, not that stub alone.

---

## 4. Hermetic repro — `scripts/repro_cascade_decompose_contract.py`

**Purpose (SPR-02):** Lock contracts with `inspect` + intentional `TypeError` on **old** call patterns. No API keys, no sockets.

**What it does:**

1. Asserts `investigation_id`, `question`, `context`, `extra_user_prefix` on `render_full_prompt` are `KEYWORD_ONLY`.
2. Asserts `investigation_id` on `dispatch` is `KEYWORD_ONLY`.
3. Proves `render_full_prompt("…")` positional raises `TypeError`.
4. Proves `dispatch("prompt", "decomposer")` without `investigation_id` raises `TypeError`.
5. Builds a valid keyword prompt string (no dispatch call to provider).

**Example success output (2026-06-02, `fe04db1`, `.venv` Python 3.12.13):**

```
REPRO_OK: old pattern render_full_prompt(question) positional → TypeError: render_full_prompt() takes 0 positional arguments but 1 was given
REPRO_OK: old pattern dispatch(prompt, role) without investigation_id → TypeError: dispatch() missing 1 required keyword-only argument: 'investigation_id'
REPRO_OK: contracts locked — auto-decompose path can reach dispatch kwargs
```

**What repro does *not* prove:** Live LLM response, provider quota, or operator-visible plan quality.

---

## 5. Werner parallel — commit `ccb4c66` and hop-delay theater

Same **easy-to-vary** shape, different surface: mascot “feels slow” → agent tightens timers → claims “fixed” without naming **which lag budget** moved.

### `ccb4c661` — what actually changed

Postmortem commit `ccb4c66` (*feat(werner): tighten cursor-follow lag from 5s to 0.5s*):

| Constant / behavior | Before | After (`ccb4c66`) |
|---------------------|--------|-------------------|
| `LAG_MS` (`useMouseFollow.ts`) | 5000 | 500 |
| `FOLLOW_EASE` | 0.5 | 0.75 |
| `POINTER_IDLE_MS` | 4000 | 2000 |
| Roam `STROLL_MS` / `REST_*` (`PenguinMascot.tsx` legacy path) | 2600 / 1800–4200 | 800 / 300–800 |
| **Hop cycle (legacy roam)** | ~4.4–6.8 s per hop | ~1.1–1.6 s per hop |

**F5 risk:** Saying “p95 lag fixed” or “feels snappy” without citing `LAG_MS`, `ROAM_STROLL_MS`, or a test row — remove the adjective, story unchanged.

### `useMouseFollow` — sample-delay, not provider latency

`apps/reading/src/werner/useMouseFollow.ts` is a **read seam**: ring buffer of pointer samples; `read().target` ≈ pointer position from **`LAG_MS` ago** (500 ms after `ccb4c66`). It does **not** move the mascot — `PenguinMascot` polls `read()` at each roam **hop**.

WERNER-ICE mode: reel pursuit in `PenguinMascot` (`REEL_TAU_MS`) closes gap on top of sample-delay; idle roam uses `ROAM_STROLL_MS` / `ROAM_REST_*` from `iceFishingConstants.ts` when flag on.

### Roam **hop** chain (where “hop delay” lives)

In `PenguinMascot.tsx` autonomous roam (`stepOnce`):

1. **`nextHopTarget`** — biased follow (ease toward lagged cursor) or bounded random wander.
2. **`strollTo(x, y, STROLL_MS)`** — CSS transition leg (800 ms legacy / 1400 ms ice-fishing).
3. **Rest timer** — `REST_MIN_MS + random * (REST_MAX_MS - REST_MIN_MS)` then next hop.

**Theater pattern:** Tweaking only commit message / operator vibe while leaving `LAG_MS` at 5000 — hop period dominated by 5 s sample-delay, not stroll ms. Honest closure names **both** hook lag and hop timers (or ice-fishing constants) and points at `useMouseFollow.test.ts` / `PenguinMascot*.test.tsx`.

---

## 6. Phase A→E mapping (cascade investigation)

| Phase | Cascade action | Done when |
|-------|----------------|-----------|
| **A** Contract lock | `inspect.signature`; run repro; dossier with `LLM contacted: no` | Repro exit **0**; lines match tree |
| **B** Scope map | Row per entry point (`tested` / `untested` / `live-LLM-required`) | No “platform OK” |
| **C** Fix + regression | Fix `DispatchDecomposer`; add/keep production adapter test + light HTTP test | Revert kwargs → failure in principle |
| **D** Canonical verify | Env Card + gate table below | Full commands + exits recorded |
| **E** Bounded closure | `### Not proved`; steelman; link this case study | Claims falsifiable per row |

---

## 7. Gate table — commands run on `caffen/ant-exec-spr06` @ `fe04db1`

**Env Card (canonical verify run):**

| Field | Value |
|-------|-------|
| Repo root | `/Users/slimydog/Desktop/Antiek` |
| Branch | `caffen/ant-exec-spr06` (based on `caffen/ant-exec-spr04`) |
| Commit | `fe04db1e257de849dddc7d1415b2366b486aa625` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` → **3.12.13** |
| LLM contacted | **no** (hermetic gates only) |

| Gate | Command | Exit | Notes |
|------|---------|------|-------|
| Contract repro | `.venv/bin/python scripts/repro_cascade_decompose_contract.py` | **0** | Three `REPRO_OK` lines (§4) |
| Production adapter | `.venv/bin/python -m pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response -q --tb=short` | **0** | 1 passed |
| HTTP light router | `.venv/bin/python -m pytest tests/test_cascade_create_plan_light.py -q --tb=short` | **0** | 2 passed |
| Canonical bundle | `.venv/bin/python -m pytest tests/test_cascade_planner.py::test_dispatch_decomposer_maps_stub_response tests/test_cascade_create_plan_light.py -q --tb=short` | **0** | 3 passed |
| Decomposer audit | `bash scripts/audit_decomposer_call_sites.sh` | **0** | `AUDIT_OK: decomposer call sites in audited files` |
| Handoff schema | `npx tsx tools/agent/verify_handoff.ts tests/fixtures/agent_execution/handoff_pass.md` | **0** | `HANDOFF_OK` |
| Session theater grep | `bash scripts/audit_agent_session.sh tests/fixtures/agent_execution/handoff_pass.md` | **0** | `AUDIT_OK` |
| F3 negative control | `bash scripts/audit_agent_session.sh tests/fixtures/agent_execution/handoff_fail_platform_ok.md` | **1** | Catches platform OK without Scope Map |

**Forbidden (do not use as sole sign-off):**

```bash
# F1 — hides failures
pytest … 2>&1 | tail -80

# F2 — wrong env
python -m pytest …   # system python
cd tests && pytest … # wrong cwd

# Collection hang — full app factory
pytest tests/test_cascade_api.py -k auto_decompose
```

Use `tests/test_cascade_create_plan_light.py` instead.

---

## 8. Scope map snapshot (cascade auto-decompose)

| ID | Entry | Hook | Status | Evidence |
|----|-------|------|--------|----------|
| E1 | `POST /research/plans` omit `sub_questions` | `DispatchDecomposer` | **tested** (adapter) | `test_dispatch_decomposer_maps_stub_response`; repro script |
| E1b | Same HTTP branch | route + 502 boundary | **tested** (stubbed decompose) | `test_cascade_create_plan_light.py` |
| E2 | `POST /research/plans` with `sub_questions` | fixed decomposer | **tested** | `test_create_plan_auto_decompose_without_sub_questions` (stub path) |
| E3 | Loop1 investigations bus | `make_decomposer_handler` | **untested** (this sprint) | `interfaces/research/api/decomposer.py` — keyword-correct, separate matrix row |
| E4 | Live operator decompose | configured provider | **live-LLM-required** | `docs/agent-execution/OPERATOR_VERIFY_CASCADE_DECOMPOSE.md` — not implied by rows above |

---

## 9. `### Not proved` (honest closure)

- Live LLM decompose on operator machine (SPR-07 operator card).
- Event-bus decomposer parity with HTTP cascade.
- Werner operator acceptance / measured p95 (separate htmlspec; `ccb4c66` is code+unit tests only).
- Full `test_cascade_api.py` journey under canonical verify (intentionally deferred — light router is the gate).

---

## 10. Related artifacts

| Artifact | Role |
|----------|------|
| `docs/agent-execution/HARD_TO_VARY.md` | Phase A–E + F1–F8 |
| `docs/agent-execution/TEMPLATES.md` | Env Card, handoff, scope map paste |
| `docs/specs/ant-h2v/FAILURE_DOSSIER.md` | Numbered chain (SPR-02) |
| `docs/specs/ant-h2v/grok-execution-brief.md` | Wave order + canonical verify block |
| `scripts/repro_cascade_decompose_contract.py` | Hermetic contract repro |
| `scripts/audit_decomposer_call_sites.sh` | Call-site drift grep |
| `scripts/audit_agent_session.sh` | Handoff F1/F3 theater |
| `apps/reading/src/werner/useMouseFollow.ts` | Sample-delay lag seam |
| `apps/reading/src/shell/PenguinMascot.tsx` | Roam hop / `stepOnce` chain |

**Read this file before Phase E sign-off on any cascade or “platform OK” investigation.**