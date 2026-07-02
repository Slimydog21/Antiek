## Sprint ANT-DRL — Handoff (SPR-DRL-01..09 complete, P-17)

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-23 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `main` |
| Commit SHA | `a5e3094733c2e6d8b4cafc3d47be5927176bfe97` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic | Operator-live gap |
|-----|----------|-------------------|
| P-11 Loop 1 E2E | stub providers | live LLM on all 5 roles |
| P-12 negative | fixture trajectory | prod DRW with live Exa |
| P-13 reconstruct | JSONL hermetic | SSE transport reconnect E2E |
| P-14 funnel | 20 concurrent promotions | remote-exec fan-out under load |
| P-15 reuse | two-run `knowledge.reused` event | dispatch cost delta > 0 on reuse-consuming loop |
| P-16 Exa gather | MockTransport E2E | live `EXA_API_KEY` discover + ingest |
| P-17 parent terminal | `test_drw_parent_terminal.py` | smoke DRW #1 `deep_research_complete` on real session |

MOCK / contract-stub economics do **not** compound — documented in `compounding/benchmark/README.md`.

### Status

`done` — Path A convergence + Exa Wedge 1 gather + parent-terminal observability; P-11..P-17 green via `canonical_verify deep-research`. **Prod deploy and smoke DRW #1 are ledger work (DRW-LEDGER), not ANT-DRL code gaps.**

### Architecture (ratified)

- **Path A:** DRW gather → `SessionEvidencePack` → Loop 1 phases 6–9 on `session_id`
- **Terminal:** `DeepResearchComplete` on session parent (not per leaf)
- **Gather:** `ANTIEK_DRW_GATHER=exa|stub` (stub default CI); Exa-first on prod per operator + `deep-research-exa-gather.md`

### Files touched

| Sprint | Key paths |
|--------|-----------|
| SPR-DRL-08 | `make_exa_gather_loop`, `cascade_routes.py`, `tests/test_exa_gather_loop.py`, P-16 matrix |
| SPR-DRL-09 | `cascade_routes.py` session_status + synthesis_tail_error, `tests/test_drw_parent_terminal.py`, P-17, `docs/decisions/deep-research-smoke-checklist.md` |

### Milestones (checkboxes)

- [x] SPR-DRL-01..07 (prior handoff)
- [x] SPR-DRL-08: Exa gather loop + P-16
- [x] SPR-DRL-09: Parent terminal + P-17 + smoke checklist doc

### Gate results

| gate | command | exit |
|------|---------|------|
| deep-research | `./scripts/canonical_verify.sh deep-research` | 0 |
| handoff | `./scripts/canonical_verify.sh handoff docs/htmlspec/deep-research-loop/SPR-DRL-handoff.md` | 0 (when run) |

### Steelman rejected alternative

**Re-grind SPR-DRL-08/09 or switch to Parallel-first gather (PR #79)** — rejected; P-11..P-17 already green on Exa-first main; parallel-first conflicts with operator Exa embedding for DRW.

### Open questions

- Live smoke DRW #1 — operator, `~/specs/antiek-drw-master-ledger` SPR-LEDGER-05
- Turbopuffer wedge — SPIKE in SPR-LEDGER-07 (retrieval, not gather)

### Scope Map

**Investigation ID:** ANT-DRL

**Next program:** `~/specs/antiek-drw-master-ledger/` (ship, keys, smoke, `drw-honest-failure` delegate)