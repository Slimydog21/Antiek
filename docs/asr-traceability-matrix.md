# ASR §9.0 traceability matrix

**Baseline:** `origin/main` @ `2b59fed` (2026-06-02)  
**Spec:** `~/specs/antiek-substrate-reconciliation/index.html`  
**Ledger:** `~/specs/antiek-substrate-reconciliation/.caffenagent/asr-run.json`

Byte-verify discipline: confirm `file:line` on handoff before editing substrate.

| obligation | owner_module | file:line | test | lint | sprint | status |
|------------|--------------|-----------|------|------|--------|--------|
| Public chunk-search excludes `personal_reading` on default `policy_tag` | `substrate.graph.search` | `substrate/graph/search.py:291-297` | `tests/test_personal_reading_lane.py::test_search_gate_excludes_personal_reading_on_default_policy` | — | PR #43 | **CLOSED** |
| Owner path includes `personal_reading` under privileged `policy_tag` | `substrate.graph.search` | `substrate/graph/search.py:209-219,291-297` | `tests/test_personal_reading_lane.py::test_search_gate_includes_personal_reading_on_operator_only` | — | PR #43 | **CLOSED** |
| VSS / `retrieval_substrate` gate matches search (excludes owner-only + restricted) | `substrate.graph.retrieval_substrate` | `substrate/graph/retrieval_substrate.py:443-445` | `tests/test_retrieval_substrate_interface.py::test_gate_excludes_restricted_under_attribution_eligible` (restricted only; no `personal_reading` fixture yet) | — | **SR-02** | **OPEN** |
| `GET /chunks/{chunk_id}` withholds `personal_reading` body | `interfaces.research.api.app` | `interfaces/research/api/app.py:2207-2213` | — (no `personal_reading` chunk fixture) | — | **SR-02** | **OPEN** |
| NULL `content_class` grandfather passes public retrieval (legacy carve-out) | `substrate.graph.search` | `substrate/graph/search.py:285-296` | `tests/test_retrieval_time_gate.py::test_default_policy_excludes_restricted` | — | **SR-06** / **SR-07** | **OPEN** |
| NULL fail-closed after backfill (remove `IS NULL OR`) | `substrate.graph.search` | `substrate/graph/search.py:295` | TBD post-backfill | — | **SR-07** | **OPEN** (blocked on **SR-06**) |
| Third-party `insert_document` deny-default → `personal_reading` | `substrate.graph.ops` | `substrate/graph/ops.py:199-231` | `tests/test_personal_reading_lane.py::test_insert_document_deny_default_third_party_lands_personal_reading` | — | PR #43 | **CLOSED** |
| `serve_full_text_guarded` is sole serving-boundary caller | `substrate.books.serve_guard` | `substrate/books/serve_guard.py:149` | `tests/test_serve_guard.py` | `tools/lint/serve_guard_check.py` | PR #43 | **CLOSED** |
| `personal_reading` non-servable on public serve path; full body owner-only | `substrate.books.serve` + `serve_guard` | `substrate/books/serve_guard.py` (wraps `serve.py`) | `tests/test_personal_reading_lane.py::test_serve_gate_public_path_does_not_serve_personal_reading`, `::test_serve_gate_owner_path_serves_full_personal_reading_body` | `tools/lint/serve_guard_check.py` | PR #43 | **CLOSED** |
| Attribution / monetization compute drops `personal_reading` | `substrate.ad_inventory.attribution` | `substrate/ad_inventory/attribution.py:79-159` (`PUBLIC_GRAPH_CONTENT_CLASSES`; deny-by-default for unknown) | `tests/test_personal_reading_lane.py::test_attribution_compute_drops_personal_reading_doc`, `::test_personal_reading_accrues_zero_attribution_share` | `tools/lint/owner_boundary_check.py` | PR #43 | **CLOSED** |
| `source_gate` wired; census on real corpus deferred | `tools.lint.source_gate` | `tools/lint/source_gate.py:1-21` | `tests/test_source_gate.py` | `tools/lint/source_gate.py` (CI) | P3 merged (**SR-10** for live census) | **PARTIAL** |
| Single SQL emitter for retrieval NOT IN (no drift) | `substrate.graph.retrieval_gate` (planned) | TBD — `substrate/graph/retrieval_gate.py` | TBD | `tools/lint/retrieval_gate_check.py` (planned) | **SR-01** | **OPEN** |
| `retrieval_gate_check` blocks second handwritten NOT IN | `tools.lint` | TBD | TBD | `tools/lint/retrieval_gate_check.py` (planned) | **SR-03** | **OPEN** |
| `register_source_document` chokepoint + txn serve-guard | `substrate.rights.register` (held branch) | `substrate/rights/register.py` — **not on main**; reviewable diff on `caffen/reframe-p1` | `tests/test_register_source.py` (held) | `tools/lint/register_check.py` (held) | **SR-04** | **OPEN** |
| `personal_reading` ∈ `VALID_CONTENT_CLASSES` before P1 merge | `substrate.rights.register` | held `register.py` | held tests | `register_check.py` | **SR-04** | **OPEN** |
| Adapters migrate to register; allowlist → empty | `acquisition.*.adapter` | per-adapter insert paths | adapter tests TBD | `tools/lint/register_check.py` | **SR-05** | **OPEN** |
| NULL backfill on prod DB (box) | operator tooling | TBD migration | TBD | — | **SR-06** | **OPEN** |
| PR #38 §9.0 servability staged until G2/G3 | legal / serve | staged branch | TBD | serve lint cluster | **SR-08** | **OPEN** |
| P4 continuous sync + P5 chunk provenance | `acquisition` / codegen | TBD | TBD | schema staleness | **SR-09** | **OPEN** |
| P3b live `source_census.json` + D17 capstone | `tools.source_census` | `tools/source_census.py` | `tests/test_source_gate.py` (fixtures) | `source_gate.py` enforces when census present | **SR-10** | **OPEN** |

## PR #43 closed obligations (on main @ `2b59fed`)

| obligation | owner_module | file:line | test | lint | sprint | status |
|------------|--------------|-----------|------|------|--------|--------|
| `PERSONAL_ONLY_CONTENT_CLASSES` / union gate vocabulary | `substrate.graph.search` | `substrate/graph/search.py:156-165` | `tests/test_personal_reading_lane.py::test_search_gate_personal_only_set_is_separate_from_restricted` | — | PR #43 | **CLOSED** |
| Constants: `personal_reading` not servable / not trainable | `substrate.constants` | `substrate/constants.py` (vocabulary) | `tests/test_personal_reading_lane.py::test_constants_personal_reading_not_servable`, `::test_non_trainable_denylist_members` | — | PR #43 | **CLOSED** |
| Training / RL export excludes `personal_reading` | `substrate.constants` + export paths | `substrate/constants.py` | `tests/test_x_byok_training_exclusion.py` | — | PR #43 | **CLOSED** |

## SR-01..SR-10 ownership (OPEN rows)

| sprint | owner | closes |
|--------|-------|--------|
| **SR-01** | `substrate/graph/retrieval_gate.py` (new) + `search.py` delegate | Single NOT IN SQL emitter |
| **SR-02** | `retrieval_substrate.py`, `app.py` `get_chunk` | VSS + REST parity with search gate |
| **SR-03** | `tools/lint/retrieval_gate_check.py` | CI anti-drift for retrieval predicates |
| **SR-04** | `substrate/rights/register.py` (reconcile `caffen/reframe-p1`) | P1 chokepoint + `personal_reading` vocab |
| **SR-05** | `acquisition/*/adapter.py` | `register_check` allowlist → ∅ |
| **SR-06** | operator / box migration | NULL backfill before flip |
| **SR-07** | `substrate/graph/search.py` | NULL fail-closed (`GATE-BACKFILL-DONE`) |
| **SR-08** | PR #38 servability (counsel G2/G3) | Legal §9.0 servability merge |
| **SR-09** | P4 daemon + P5 codegen | Corpus sync + chunk provenance |
| **SR-10** | `tools/source_census.py` + `reports/source_census.json` | P3b live census; `source_gate` **CLOSED** |

## Sequencing (binding)

1. **SR-01 → SR-02 → SR-03** (`GATE-RETRIEVAL-LINT`) before **SR-04** (P1 reconcile).  
2. **SR-04 → SR-05** (write spine).  
3. **SR-06 → [GATE-BACKFILL-DONE] → SR-07** (NULL).  
4. **SR-08** only after **GATE-G2-G3**.  
5. **SR-09 → SR-10** (corpus compound).

See `docs/decisions/asr-baseline-2026-06-02.md`.