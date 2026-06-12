## Sprint ANT-DRL — Handoff (SPR-DRL-01..07 complete)

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-12 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `main` |
| Commit SHA | `6fdde98` (local; uncommitted DRL work may extend) |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` |
| Python version | `3.12.13` |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic | Operator-live gap |
|-----|----------|-------------------|
| P-11 Loop 1 E2E | stub providers | live LLM on all 5 roles |
| P-12 negative | fixture trajectory | prod DRW with Exa adapter |
| P-13 reconstruct | JSONL hermetic | SSE transport reconnect E2E |
| P-14 funnel | 20 concurrent promotions | remote-exec fan-out under load |
| P-15 reuse | two-run `knowledge.reused` event | dispatch cost delta > 0 on reuse-consuming loop |

MOCK / contract-stub economics do **not** compound — documented in `compounding/benchmark/README.md`.

### Status

`done` — Path A convergence shipped; P-11..P-15 green via `canonical_verify deep-research`.

### Architecture (ratified)

- **Path A:** DRW gather → `SessionEvidencePack` → Loop 1 phases 6–9 on `session_id`
- **Terminal:** `DeepResearchComplete` on session parent (not per leaf)
- **Exa:** out of scope — `make_contract_gather_stub` in prod factory seam

### Files touched

| Sprint | Key paths |
|--------|-----------|
| SPR-DRL-01 | `orchestration/invariants/deep_research_complete.py` |
| SPR-DRL-02 | `scripts/canonical_verify.sh deep-research`, `PLATFORM_EXEC_MATRIX.md` |
| SPR-DRL-03 | `orchestration/loop_one/orchestrator.py` (bounded Phase 2) |
| SPR-DRL-04 | `make_contract_gather_stub` in `cascade_routes` |
| SPR-DRL-05 | `orchestration/session_evidence_pack.py` |
| SPR-DRL-06 | `run_synthesis_tail_from_pack`, cascade synthesis hook |
| SPR-DRL-07 | `tests/test_flywheel_reuse.py`, P-15 matrix update |

### Milestones (checkboxes)

- [x] SPR-DRL-01: DeepResearchComplete contract
- [x] SPR-DRL-02: P-11..P-15 harness
- [x] SPR-DRL-03: Loop 1 engine hardening
- [x] SPR-DRL-04: Evict `make_demo_loop` from prod
- [x] SPR-DRL-05: SessionEvidencePack
- [x] SPR-DRL-06: Path A convergence
- [x] SPR-DRL-07: Flywheel E2E gates

### Gate results

| gate | command | exit |
|------|---------|------|
| deep-research | `./scripts/canonical_verify.sh deep-research` | 0 |
| agent-gates | `./scripts/canonical_verify.sh agent-gates` | 0 |
| handoff | `./scripts/canonical_verify.sh handoff docs/htmlspec/deep-research-loop/SPR-DRL-handoff.md` | 0 |

### Steelman rejected alternative

**Skip P-15 two-run gate** — rejected; flywheel observability is the moat even when MOCK economics stay null.

### Open questions

- Exa adapter drops into `_research_loop_factory` with zero route changes when operator provisions it.

### Scope Map

**Investigation ID:** ANT-DRL

| Entry | Production hook | Test |
|-------|-----------------|------|
| Cascade launch | `POST /research/plans/{id}/launch` | `test_cascade_convergence.py` |
| Synthesis tail | `CascadeSession.run_synthesis_tail` | `test_cascade_convergence.py` |
| Terminal check | `check_deep_research_complete` | `test_deep_research_complete.py` |
| Reuse flywheel | `HostLocalRunner.start` + substrate | `test_flywheel_reuse.py` |