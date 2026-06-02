# Retrieval Gate Closure — RG-01..RG-06 decision record

**Date:** 2026-06-02  
**Status:** Closed (code + docs + CI)  
**Master spec:** `~/specs/antiek-retrieval-gate-closure/index.html`  
**Predecessor:** PR #43 Personal-Reading Lane (`9aeb2c9`) — `personal_reading` on
`search()` only; VSS + `GET /chunks` still RESTRICTED-only.

## Problem

After PR #43, `content_class='personal_reading'` was excluded in
`substrate/graph/search.py` but **not** on the default vector path or the direct
chunk HTTP API. Empty prod corpus (D17 ingest deferred) kept the gap latent.
Live ingest would surface chunk text via VSS ranking or claim-modal
`GET /chunks/{id}` — a §9.0 leak past what `corpus_audit` and `search()` tests
proved.

## Verified defects (pre-fix line numbers on `origin/main` @ `9aeb2c9`)

### Defect A — default VSS substrate (RESTRICTED-only SQL)

| | |
|---|---|
| **Symptom** | `make_substrate("vss")` (factory default) ranked `personal_reading` chunks on `policy_tag='attribution_eligible'`. |
| **Root cause** | `DuckDbVssSubstrate._vss_query` filtered only `RESTRICTED_CONTENT_CLASSES`, not `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES`. |
| **Evidence (pre)** | `substrate/graph/retrieval_substrate.py:441-445` — `NOT IN` restricted only; module doc claimed `search()` parity — **false**. |
| **Contrast (correct)** | `substrate/graph/search.py:291-295` (pre-RG-01) already excluded restricted ∪ personal_reading. |

### Defect B — chunk HTTP `GET /chunks/{chunk_id}` (RESTRICTED-only withhold)

| | |
|---|---|
| **Symptom** | `personal_reading` → `servable=True`, full `chunks.text` returned to any caller (claim hover / named-source). |
| **Root cause** | Handler branched on `RESTRICTED_CONTENT_CLASSES` only. |
| **Evidence (pre)** | `interfaces/research/api/app.py:2200-2203` — docstring cited `search.py` parity — **false**. |

## Fixes (file:line at INTEGRATION tip `5753b09`)

### RG-01 — canonical gate module

| Change | Location |
|---|---|
| `non_privileged_chunk_sql_clause()` + `is_chunk_body_withheld()`; docstring: RESTRICTED-only is never sufficient | `substrate/graph/retrieval_gate.py:73-121` |
| `search()` delegates to helper | `substrate/graph/search.py:237-241` |
| Polarity / fail-before tests | `tests/test_retrieval_gate_polarity.py`, `tests/test_retrieval_time_gate.py` |
| **Commit** | `d4ad3d7` RG-01; sharpen `a43ea6a` |

### RG-02 — VSS + brute_force alignment

| Change | Location |
|---|---|
| `_vss_query` calls `non_privileged_chunk_sql_clause(table_alias="d", policy_tag=...)` | `substrate/graph/retrieval_substrate.py:438-444` |
| Substrate gate tests (personal_reading @ attribution_eligible / operator_only) | `tests/test_retrieval_substrate_interface.py` |
| **Commit** | `85ee529` RG-02 |

### RG-03 — HTTP chunk endpoint

| Change | Location |
|---|---|
| `is_chunk_body_withheld(content_class, taken_down=...)` drives `text` / `servable` / `servability` | `interfaces/research/api/app.py:2149-2224` (`withheld` at `:2208-2210`, empty `text` at `:2217`) |
| **Commit** | `0e60b97` RG-03 |

### RG-04 — drift lint (CI-red)

| Change | Location |
|---|---|
| AST scanner forbids RESTRICTED-only reimplementation on watched surfaces | `tools/lint/retrieval_gate_check.py` |
| CI wire | `.github/workflows/ci.yml:193` |
| Planted-violation tests | `tests/test_compliance_invariants.py` (retrieval_gate scanner section) |
| **Commit** | `dbe1581` RG-04 |

### RG-05 — cross-surface closure matrix

| Change | Location |
|---|---|
| One fixture; `search` / `vss` / `brute_force` / `TestClient GET /chunks` | `tests/test_retrieval_gate_closure.py` |
| Attribution regression pin | `test_compute_attribution_drops_personal_reading` in same file |
| **Commit** | `809efeb` RG-05 |

### RG-06 — capstone docs + D17 spot-checks

| Change | Location |
|---|---|
| Operator runbook (preflight + post-ingest spot-check) | `infrastructure/runbooks/retrieval-gate-closure.md` |
| D17 deferral append + operator breadcrumb | `docs/engineering_deferrals.md`, `docs/operator_gate_actions.md` |
| This decision record | `docs/decisions/retrieval-gate-closure.md` |

## Fail-before evidence

| Sprint | Proof |
|---|---|
| RG-01 | Restoring RESTRICTED-only SQL in `search()` only → `test_search_gate_excludes_personal_reading_on_default_policy` fails. |
| RG-02 | Restoring RESTRICTED-only VSS SQL → personal_reading included @ `attribution_eligible` fails. |
| RG-03 | RESTRICTED-only withhold in `get_chunk` → `personal_reading` body leak fails. |
| RG-04 | Planted RESTRICTED-only SQL in temp tree → `retrieval_gate_check` exit 1. |
| RG-05 | Single matrix file; HTTP + both substrates parametrized. |

## Verification (RG-06 capstone, 2026-06-02)

```text
python tools/lint/retrieval_gate_check.py          → exit 0
pytest tests/test_retrieval_gate_closure.py \
     tests/test_compliance_invariants.py -k retrieval_gate → 25 passed
```

Full CI subset: `pytest tests/ -q -m "not integration"` per `.github/workflows/ci.yml`.

## Out of scope (unchanged)

* NULL `content_class` allowlist unification (PR #38).
* Book full-text serve allowlist (`substrate/books/serve.py`) — different polarity.
* Deploy to prod (operator / PRcrouch).

## Operator follow-on

D17 ingest window unchanged in deferral; **added** mandatory retrieval spot-checks
after each connector ingest — see `infrastructure/runbooks/retrieval-gate-closure.md`
§2 and `docs/operator_gate_actions.md` Personal-Reading Lane breadcrumb.