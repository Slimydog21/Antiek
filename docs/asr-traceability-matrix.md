# ASR §9.0 traceability matrix

**Baseline:** `origin/main` @ `2b59fed` (2026-06-02)  
**Spec:** `~/specs/antiek-substrate-reconciliation/index.html`  
**Ledger:** `~/specs/antiek-substrate-reconciliation/.caffenagent/asr-run.json`

Byte-verify discipline: confirm `file:line` on handoff before editing substrate.

| obligation | owner_module | file:line | test | lint | sprint | status |
|------------|--------------|-----------|------|------|--------|--------|
| Public chunk-search excludes `personal_reading` on default `policy_tag` | `substrate.graph.search` | `substrate/graph/search.py:291-297` | `tests/test_personal_reading_lane.py::test_search_gate_excludes_personal_reading_on_default_policy` | — | PR #43 | **CLOSED** |
| Owner path includes `personal_reading` under privileged `policy_tag` | `substrate.graph.search` | `substrate/graph/search.py:209-219,291-297` | `tests/test_personal_reading_lane.py::test_search_gate_includes_personal_reading_on_operator_only` | — | PR #43 | **CLOSED** |
| VSS / `retrieval_substrate` gate matches search (excludes owner-only + restricted) | `substrate.graph.retrieval_substrate` | `substrate/graph/retrieval_substrate.py` (via `retrieval_gate`) | `tests/test_retrieval_substrate_personal_reading.py` | `tools/lint/retrieval_gate_check.py` | **SR-02** | **CLOSED** |
| `GET /chunks/{chunk_id}` withholds `personal_reading` body | `interfaces.research.api.app` | `interfaces/research/api/app.py:2207-2213` | `tests/test_get_chunk_personal_reading.py` | — | **SR-02** | **CLOSED** |
| NULL `content_class` grandfather passes public retrieval (legacy carve-out RETAINED) | `substrate.graph.retrieval_gate` | `substrate/graph/retrieval_gate.py` (`IS NULL OR` carve-out kept) | `tests/test_null_content_class_gate.py::test_search_default_policy_grandfathers_null_content_class` | — | SR-01 | **CLOSED** |
| NULL fail-closed after backfill (remove `IS NULL OR`) | `substrate.graph.retrieval_gate` | _not landed_ — deferred behind SR-06 backfill | `tests/test_null_content_class_gate.py` | `tools/lint/retrieval_gate_check.py` | **SR-07** | **DEFERRED** (gated on SR-06 `GATE-BACKFILL-DONE`; dropped from #65 — flipping NULL fail-closed ahead of the prod backfill hides legacy content from search/grounding) |
| Third-party `insert_document` deny-default → `personal_reading` | `substrate.graph.ops` | `substrate/graph/ops.py:199-231` | `tests/test_personal_reading_lane.py::test_insert_document_deny_default_third_party_lands_personal_reading` | — | PR #43 | **CLOSED** |
| `serve_full_text_guarded` is sole serving-boundary caller | `substrate.books.serve_guard` | `substrate/books/serve_guard.py:149` | `tests/test_serve_guard.py` | `tools/lint/serve_guard_check.py` | PR #43 | **CLOSED** |
| `personal_reading` non-servable on public serve path; full body owner-only | `substrate.books.serve` + `serve_guard` | `substrate/books/serve_guard.py` (wraps `serve.py`) | `tests/test_personal_reading_lane.py::test_serve_gate_public_path_does_not_serve_personal_reading`, `::test_serve_gate_owner_path_serves_full_personal_reading_body` | `tools/lint/serve_guard_check.py` | PR #43 | **CLOSED** |
| Attribution / monetization compute drops `personal_reading` | `substrate.ad_inventory.attribution` | `substrate/ad_inventory/attribution.py:79-159` (`PUBLIC_GRAPH_CONTENT_CLASSES`; deny-by-default for unknown) | `tests/test_personal_reading_lane.py::test_attribution_compute_drops_personal_reading_doc`, `::test_personal_reading_accrues_zero_attribution_share` | `tools/lint/owner_boundary_check.py` | PR #43 | **CLOSED** |
| `source_gate` wired; census producer available; live corpus census deferred | `tools.lint.source_gate` + `tools.source_census` | `tools/lint/source_gate.py:1-21`, `tools/source_census.py`, `infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2` (`ExecStartPost`) | `tests/test_source_gate.py`, `tests/test_arxiv_oai_sync_systemd.py` | `tools/lint/source_gate.py` (CI) | P3 merged (**SR-10** live emission remains operator-corpus work) | **PARTIAL** |
| Single SQL emitter for retrieval NOT IN (no drift) | `substrate.graph.retrieval_gate` | `substrate/graph/retrieval_gate.py` | `tests/test_retrieval_gate_canon.py` | `tools/lint/retrieval_gate_check.py` | **SR-01** | **CLOSED** |
| `retrieval_gate_check` blocks second handwritten NOT IN | `tools.lint` | `tools/lint/retrieval_gate_check.py` | `tests/test_retrieval_gate_matrix.py` | CI step | **SR-03** | **CLOSED** |
| `register_source_document` chokepoint + txn serve-guard | `substrate.rights.register` | `substrate/rights/register.py` | `tests/test_register_source.py` | `tools/lint/register_check.py` | **SR-04** | **CLOSED** (PR #58) |
| `personal_reading` ∈ `VALID_CONTENT_CLASSES` before P1 merge | `substrate.rights.register` | `register.py:VALID_CONTENT_CLASSES` | `tests/test_register_source.py::test_personal_reading_content_class_accepted` | `register_check.py` | **SR-04** | **CLOSED** |
| Adapters migrate to register; allowlist → empty | `acquisition.*.adapter` | per-adapter insert paths; `tools/lint/register_check.py` `_MIGRATION_PENDING = frozenset()` | `tests/test_register_source.py`, acquisition adapter clusters | `tools/lint/register_check.py` | **SR-05** | **CLOSED** |
| NULL backfill on prod DB (box) | operator tooling | TBD migration | TBD | — | **SR-06** | **OPEN** |
| PR #38 §9.0 servability staged until G2/G3 | legal / serve | staged branch | TBD | serve lint cluster | **SR-08** | **OPEN** |
| P5 chunk provenance (`personal_reading` non-citable) | `tools.codegen` | `tools/codegen/chunk_provenance.py` | `tests/test_conformance_gate.py` | `tools/codegen/check_conformance.py` | **SR-09** | **CLOSED** (P5) |
| P4 continuous OAI sync under shared flock | `tools.arxiv_oai_sync` + systemd timer | `tools/arxiv_oai_sync.py`, `infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2`, `infrastructure/ansible/templates/antiek-arxiv-oai-sync.timer.j2` | `tests/test_arxiv_oai_sync.py`, `tests/test_rate_governor.py::test_oai_harvest_send_is_inside_the_host_global_governor_flock`, `tests/test_arxiv_oai_sync_systemd.py` | `tools/lint/rate_governor_check.py`; deploy renders/enables `antiek-arxiv-oai-sync.timer` | **SR-09** | **PARTIAL** (local sync driver + deployable timer landed; live timer enablement / first production run remains operator proof) |
| P3b live `source_census.json` + D17 capstone | `tools.source_census` | `tools/source_census.py` (`compute_source_census`, `python -m tools.source_census --source ... --out reports/source_census.json`), `antiek-arxiv-oai-sync.service` emits `{{ antiek_state_dir }}/reports/source_census.json` after successful OAI sync | `tests/test_source_gate.py` (fixtures + DB-backed producer), `tests/test_arxiv_oai_sync_systemd.py` | `source_gate.py` enforces when census present | **SR-10** | **PARTIAL** (producer + prod timer emission landed; first live report capture / threshold calibration still requires operator/prod corpus) |

## PR #43 closed obligations (on main @ `2b59fed`)

| obligation | owner_module | file:line | test | lint | sprint | status |
|------------|--------------|-----------|------|------|--------|--------|
| `PERSONAL_ONLY_CONTENT_CLASSES` / union gate vocabulary | `substrate.graph.search` | `substrate/graph/search.py:156-165` | `tests/test_personal_reading_lane.py::test_search_gate_personal_only_set_is_separate_from_restricted` | — | PR #43 | **CLOSED** |
| Constants: `personal_reading` not servable / not trainable | `substrate.constants` | `substrate/constants.py:543-617` | `tests/test_personal_reading_lane.py::test_constants_personal_reading_not_servable`, `::test_non_trainable_denylist_members` | — | PR #43 | **CLOSED** |
| Training / RL export excludes `personal_reading` | `substrate.constants` + export paths | `substrate/constants.py` | `tests/test_x_byok_training_exclusion.py` | — | PR #43 | **CLOSED** |

## SR-01..SR-10 ownership (OPEN rows)

| sprint | owner | closes |
|--------|-------|--------|
| **SR-01** | `substrate/graph/retrieval_gate.py` (new) + `search.py` delegate | Single NOT IN SQL emitter |
| **SR-02** | `retrieval_substrate.py`, `app.py` `get_chunk` | VSS + REST parity with search gate |
| **SR-03** | `tools/lint/retrieval_gate_check.py` | CI anti-drift for retrieval predicates |
| **SR-04** | `substrate/rights/register.py` (reconcile `caffen/reframe-p1`) | P1 chokepoint + `personal_reading` vocab |
| **SR-05** | `acquisition/*/adapter.py` | `register_check` allowlist → ∅ (**CLOSED**) |
| **SR-06** | operator / box migration | NULL backfill before flip |
| **SR-07** | `substrate/graph/search.py` | NULL fail-closed (`GATE-BACKFILL-DONE`) |
| **SR-08** | PR #38 servability (counsel G2/G3) | Legal §9.0 servability merge |
| **SR-09** | P4 timer + P5 codegen | Corpus sync + chunk provenance (P4 live proof pending) |
| **SR-10** | `tools/source_census.py` + `reports/source_census.json` | P3b census producer + timer emission landed; first live `source_census.json` capture still operator-corpus proof |

## Sequencing (binding)

1. **SR-01 → SR-02 → SR-03** (`GATE-RETRIEVAL-LINT`) before **SR-04** (P1 reconcile).  
2. **SR-04 → SR-05** (write spine).  
3. **SR-06 → [GATE-BACKFILL-DONE] → SR-07** (NULL).  
4. **SR-08** only after **GATE-G2-G3**.  
5. **SR-09 → SR-10** (corpus compound). P4's local driver/timer is present; live timer enablement + first production run remain operator proof before calling SR-09 fully closed.

See `docs/decisions/asr-baseline-2026-06-02.md`.
