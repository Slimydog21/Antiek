# caffenagent run — ANT-DRL Perfect Deep Research Loop

- **Spec dir:** `/Users/slimydog/Desktop/Antiek/docs/htmlspec/deep-research-loop`
- **index.html:** `/Users/slimydog/Desktop/Antiek/docs/htmlspec/deep-research-loop/index.html`
- **Target branch:** `main`
- **Run mode:** fully autonomous · resume-on-pre-shipped · Exa Wedge 1 completed later in follow-on execution
- **Started:** 2026-06-12
- **Last updated:** 2026-06-30

## Sprint roster

| Sprint | Title | Wave | Depends on | Status | Rounds | Merge SHA |
|---|---|---|---|---|---|---|
| SPR-DRL-01 | DeepResearchComplete terminal contract | 1 | — | done | 1 | pre-shipped |
| SPR-DRL-02 | PLATFORM_EXEC P-11..P-15 | 2 | 01 | done | 1 | pre-shipped |
| SPR-DRL-03 | Loop 1 engine hardening | 3 | 01 | done | 1 | pre-shipped |
| SPR-DRL-04 | Evict make_demo_loop | 3 | 01 | done | 2 | pre-shipped + sharpen |
| SPR-DRL-05 | SessionEvidencePack | 4 | 02,04 | done | 1 | pre-shipped |
| SPR-DRL-06 | Path A convergence | 4 | 03,05 | done | 1 | pre-shipped |
| SPR-DRL-07 | Flywheel E2E | 5 | 06 | done | 1 | pre-shipped |
| SPR-DRL-08 | Exa gather loop | 6 | 06,07 | done | 1 | see `SPR-DRL-handoff.md` |
| SPR-DRL-09 | Parent terminal + P-17 | 7 | 08 | done | 1 | see `SPR-DRL-handoff.md` |

Status note: the June 12 ledger stopped with SPR-DRL-08 blocked by operator scope.
That is superseded by the June 23 handoff: SPR-DRL-08 and SPR-DRL-09 completed
through P-17. Production deploy and live smoke DRW #1 remain DRW-LEDGER work, not
ANT-DRL code gaps.

## Per-sprint log

### SPR-DRL-01..07 — substrate + engine + harness

- **Harness hint:** fan-out-and-synthesize (Waves 1–5)
- **Capability mapping:** orchestrator-inline verification (pre-shipped working tree)
- **Critic rung used:** 1 (orchestrator gate audit)
- **Gate status:** verified green again on 2026-06-30 via
  `./scripts/canonical_verify.sh deep-research`.

| Round | Builders spun | Gate results | Critic verdict | Blocking defects | Decision |
|---|---|---|---|---|---|
| 1 (verify) | inline audit | deep-research OK; per-sprint pytest OK | MERGE | 0 | done (01–03,05–07) |
| 2 (sharpen) | test fix | cascade OK; test_launch_watch_and_cost OK | MERGE | 0 | done (04) |

- **Sharpen defect fixed:** `test_launch_watch_and_cost` expected demo-loop cost
  (3×0.01×3=0.09); contract stub uses 2 steps → 0.06.

### SPR-DRL-08 — Exa gather loop

- **Status:** done.
- **Handoff:** `docs/htmlspec/deep-research-loop/SPR-DRL-handoff.md`.
- **Proof:** P-16 Exa gather mock E2E in `./scripts/canonical_verify.sh deep-research`.
- **Live gap:** live `EXA_API_KEY` discover→ingest remains operator smoke work.

### SPR-DRL-09 — Parent terminal + P-17

- **Status:** done.
- **Handoff:** `docs/htmlspec/deep-research-loop/SPR-DRL-handoff.md`.
- **Proof:** P-17 parent-terminal observability in
  `./scripts/canonical_verify.sh deep-research`.
- **Live gap:** smoke DRW #1 proving `DeepResearchComplete` on a real production
  session remains DRW-LEDGER work.

## Gate summary

| Gate | Command | Result |
|---|---|---|
| deep-research | `./scripts/canonical_verify.sh deep-research` | `CANONICAL_VERIFY_OK: deep-research` (2026-06-30) |
| handoff | `./scripts/canonical_verify.sh handoff docs/htmlspec/deep-research-loop/SPR-DRL-handoff.md` | `CANONICAL_VERIFY_OK: handoff` (2026-06-30) |
| focused P-16/P-17 | `./.venv/bin/python -m pytest tests/test_exa_gather_loop.py tests/test_drw_parent_terminal.py -q` | 16 passed (2026-06-30) |

## Honesty events

- The old June 12 `SPR-DRL-08 BLOCKED` entry was stale after the June 23 handoff.
  It is now recorded as superseded, not deleted from history by silence.
- `test_loop_one_happy_path_emits_completed` regressed under the stricter
  cite-every-claim parsers: the fixture lacked a bridge-recognized canonical chunk
  block. The fix keeps parser strictness and makes the test fixture cite a real
  `chunk-1` provenance candidate.
- Production deploy, prod Exa key, and smoke DRW #1 remain outside this ANT-DRL
  ledger; see `~/specs/antiek-drw-master-ledger/` and
  `docs/decisions/deep-research-smoke-checklist.md`.

## Hard blocks

- None for ANT-DRL engineering through P-17.
- Operator-live proof remains: prod deploy/key/smoke in the DRW master ledger.
