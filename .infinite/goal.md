# .infinite/goal.md — Antiek execution (north star + derivation trail)

> **Control-plane delegation (2026-07-11):** This file preserves the platform checkout's
> historical north star and derivation trail. Before claiming or mutating new work, resolve
> current portfolio ownership, collisions, engine roles, and integration targets through
> `/Users/slimydog/Antiek/.infinite/CEO-DIRECTIVE.md` and `agent-board.json`. New cycle evidence
> remains append-only here when it belongs to this checkout, but this file is not a second
> portfolio authority.

## NORTH STAR (operator's words, verbatim mandate)

Continue executing the Antiek project and the unexecuted sprints to build a
comprehensive reading, research, and writing platform — the perfect knowledge
graph / base and thought-partner / workstation. Execute with technical
precision, exhaustive attention to detail, and craftsmanship that is hard to
vary (James Hawkins / PostHog bar). I am the primary orchestrator; delegate
to sub-terminal CLIs (grok=Composer 2.5, codex=GPT-5.5, mimo, glm-cc=ultracode,
claude=sonnet/haiku). Collaborate with the existing agent-primary (Opus)
orchestrator + Codex agent already on this goal. Quality bar: no faked green,
hard-to-vary, ship real.

## GROUND TRUTH (established 2026-07-02, before any execution)

- Canonical repo: `/Users/slimydog/Antiek/platform` (origin: Slimydog21/Antiek).
- Current branch: `reader/integration` (HEAD `7fa8d6ea`); 6,778 tests collected.
- origin/main FROZEN at `1c4d5df9` since 2026-07-01 — NOTHING merged since the
  team board. **18 open PRs.** 5 verified-clean (0-behind-main) branches stuck
  at operator-PR gate: nygard-resilience/integration, aod/integration,
  hickey/spr-02-values-over-place, integrator/session-hardening,
  integrator/single-writer-repo-wide-audit.
- An agent-primary (Opus) orchestrator + Codex agent + ~5 build lanes are
  ALREADY active, coordinated via `~/specs/ANTIEK-TEAM-COORDINATION.md`.
  Board explicitly: "Team is saturated; collision-avoidance."
- The TRUE bottleneck is OPERATOR action: G2 (lawyer), G3 (publisher opt-in),
  G6 (run ≥20 prompt mutations), run 5-10 real investigations, provider keys.
  Engineering cannot close these.
- Lane-A lesson (binding): diff origin/main BEFORE executing any spec, or you
  build a superseded duplicate. Research-harness spec already verified STALE
  (real_research_loop wired in RDR SPR-04).

## DISCIPLINE (binding on every cycle)

1. Read the team coordination board + append my lane before claiming work.
2. Diff current origin/main before executing ANY spec (duplicate trap).
3. Never collide with a saturated lane; pick genuinely-unclaimed seams.
4. No faked green; no weakened gate; no silent §16 creep.
5. Numbers over adjectives in the ledger.

## DERIVATION TRAIL

- C0 (2026-07-02): Established ground truth. Research-harness spec STALE →
  skip. Next: find the highest-value UNEXECUTED + UNGATED + NON-COLLIDING seam
  by diffing main against unclaimed product specs, OR do integrator/verification
  work the saturated team needs.

## CURRENT SUBGOAL

C45 (2026-07-07): GF-7 DuckDB startup integrity-health slice shipped to
production through PR #234 (`caffen/gf7-duckdb-startup-integrity@8dfd1c88`;
merged as `2acb515e`), after external operator-side activity also merged PR
#231 and PR #233.

Built in C45:

- New read-only `substrate.graph.health.probe_duckdb_health(db_path)` startup
  probe for the graph DuckDB file.
- Probe reports missing DB, read-only open failure/corruption, `nodes` schema
  sentinel presence, `PRAGMA database_size` viability, WAL sidecar presence and
  bytes, and whether `PRAGMA integrity_check` is available.
- `/health` now exposes additive `duckdb_*` fields from an app-construction
  snapshot without initializing or mutating the graph DB.
- The implementation is honest about the local DuckDB build: `PRAGMA
  integrity_check` is unavailable, so health reports `duckdb_integrity_check:
  "unavailable"` while still validating read-only open, schema sentinel, and
  database-size probing.

Verified in C45:

- `pytest tests/test_duckdb_health.py tests/test_api.py tests/test_health_flywheel.py tests/test_prod_parity.py -q`
  -> 42 passed.
- `ruff check substrate/graph/health.py interfaces/research/api/app.py tests/test_duckdb_health.py`
  -> pass.
- `mypy --strict substrate/graph/health.py interfaces/research/api/app.py`
  -> success.
- `tools/codegen/check_staleness.py` -> OK events/contracts.
- `git diff --check` -> pass.
- Remote PR #234 CI all green: pytest, tsc, vitest, keystone, declared-bar,
  Cloudflare Pages, and Strix Security Review.
- Production deploy via `infrastructure/ansible/playbooks/deploy.yml` completed
  with `failed=0`.
- Independent `curl https://api.antiek.ai/health` reports
  `build_sha=2acb515e5d5dd6658d90e9c8a4072dbda25041cd`,
  `duckdb_ready=true`, `duckdb_status="ok"`, schema present, database-size OK,
  `duckdb_integrity_check="unavailable"`, no WAL sidecar, and no DuckDB error.
- Independent `curl -I https://api.antiek.ai/` returns HTTP 200 HTML.

External state observed after C45:

- PR #231 merged and production `/health` reports
  `build_sha=02495089d30e4aa8639b9eb1367642863e109958`.
- PR #233 merged as `8f509679`; all remote checks were green before merge.
- PR #234 merged as `2acb515e`; `origin/main` and production now match this SHA.

Current subgoal C46: GF-3a Phase-8 gate enable-path slice is built and opened as
PR #235 (`caffen/gf3-phase8-gate-env@3cc011fa`), based on deployed
`main@2acb515e`.

Built in C46:

- `SkillPatchGate` now validates mode, epsilon, and minimum cohort size.
- New env-backed factory `phase8_gate_from_env()` reads
  `ANTIEK_PHASE8_MODE`, `ANTIEK_PHASE8_EPSILON`, and
  `ANTIEK_PHASE8_MINIMUM_COHORT_SIZE`.
- Default remains shadow mode; enforcing is an explicit opt-in.
- Invalid runtime config raises visibly instead of silently degrading to
  shadow.
- `PatchDecision` now uses `enum.StrEnum`, preserving string-like values while
  satisfying the touched-file lint bar.

Verified in C46:

- `pytest tests/test_phase8_gate.py tests/test_gepa_phase8_bridge.py tests/test_gepa_phase8_applier_e2e.py tests/test_prompt_applier.py -q`
  -> 34 passed.
- `ruff check compounding/skill_growth/gate.py compounding/skill_growth/__init__.py tests/test_phase8_gate.py`
  -> pass.
- `mypy --strict compounding/skill_growth/gate.py compounding/skill_growth/__init__.py`
  -> success.
- `tools/codegen/check_staleness.py` -> OK events/contracts.
- `git diff --check` -> pass.

Current status: PR #235 is open, CLEAN/MERGEABLE, and all remote checks are
SUCCESS: pytest, declared-bar, keystone, tsc, vitest, Cloudflare Pages, and
Strix Security Review. This is only the GF-3a config enable-path slice; it does
not claim the full Phase-8 calibration/operator-review loop and does not yet
wire the main auto-patch policy path. Do not merge/deploy without operator
authorization.

C47: GF-3b Phase-8 auto-patch policy wiring is built and opened as stacked PR
#237 (`caffen/gf3-phase8-policy-wiring@edf2b48a`), targeting PR #235's branch.

Built in C47:

- `_run_phase_8` now consults the env-backed Phase-8 gate before either
  auto-patch writer runs.
- Shadow mode remains the default and preserves current behavior.
- Enforcing mode rejects the current uncalibrated auto-patch path before file
  writes, emits the existing typed `skill.auto_patch_applied` event with
  `status="rejected_by_phase8_gate"`, and lets the existing Phase-8
  postcondition fail honestly.
- The implementation does not fabricate a candidate backtest score; it uses
  `cohort_size=0` to make the missing calibration explicit.

Verified in C47:

- `pytest tests/test_phase8_orchestrator_gate.py tests/test_phase8_gate.py tests/test_phase_runner_postconditions.py tests/test_skills_domain_auto_patch.py -q`
  -> 72 passed.
- `pytest tests/test_loop_one_orchestrator.py tests/test_cascade_convergence.py::test_pack_synthesis_tail_mechanical_phase8_when_skill_templates_missing -q`
  -> 4 passed, 2 existing warnings.
- `ruff check orchestration/loop_one/orchestrator.py tests/test_phase8_orchestrator_gate.py compounding/skill_growth/gate.py compounding/skill_growth/__init__.py tests/test_phase8_gate.py`
  -> pass.
- `mypy --strict orchestration/loop_one/orchestrator.py compounding/skill_growth/gate.py compounding/skill_growth/__init__.py`
  -> success.
- `tools/codegen/check_staleness.py` -> OK events/contracts.
- `git diff --check` -> pass.

Current status: PR #237 is open, CLEAN, and stacked on #235. Because its base is
the feature branch, GitHub attached only Cloudflare Pages and Strix checks; both
are SUCCESS. PR #235 remains the main-base prerequisite and is CLEAN with full
main-target CI green.

C48: GF-3c Phase-8 gate decision/audit evidence is built and opened as stacked
PR #238 (`caffen/gf3-phase8-gate-decision-audit@5ebe4a2e`), targeting PR #237's
branch.

External state changed before/during C48:

- PR #235 merged externally as `287194aa`.
- PR #237 was retargeted to `main` and now points at
  `caffen/gf3-phase8-policy-wiring@9b1757f1`; it is MERGEABLE with all attached
  checks success except remote pytest still IN_PROGRESS at record time.

Built in C48:

- Added typed `skill.patch_gate_decided` events and bumped event schema to v30.
- `_run_phase_8` now emits the gate decision before pre-write enforcing
  rejection or shadow-mode continuation.
- Added `orchestration.audit.phase8_calibration_status`, reporting shadow
  decisions collected, operator-reviewed count, and current epsilon agreement.
- Updated generated TS types and the Research narration coverage map for the
  new action type.
- Fixed the visualtest lostpixel browser install to use Lost Pixel's nested
  Playwright version, after the branch exposed a real CI infra mismatch.

Verified in C48:

- `pytest tests/test_phase8_orchestrator_gate.py tests/test_phase8_gate.py tests/test_phase8_calibration_status.py tests/test_phase_runner_postconditions.py tests/test_skills_domain_auto_patch.py -q`
  -> 75 passed.
- `pytest tests/test_events_schema.py tests/test_loop_one_orchestrator.py tests/test_cascade_convergence.py::test_pack_synthesis_tail_mechanical_phase8_when_skill_templates_missing -q`
  -> 60 passed, 2 existing warnings.
- Ruff on touched backend/schema/test/codegen files -> pass.
- `mypy --strict orchestration/loop_one/orchestrator.py orchestration/audit/phase8_calibration_status.py compounding/skill_growth/gate.py compounding/skill_growth/__init__.py`
  -> success.
- `tools/codegen/check_staleness.py` -> OK events/contracts.
- `git diff --check` -> pass.
- `npm run build` in `apps/reading` -> success with existing Vite chunk
  warnings.
- PR #238 remote checks: lostpixel, axe-core, and Cloudflare Pages SUCCESS.

Current status: PR #238 is open, MERGEABLE, and fully green for its attached
stacked checks. PR #237 remains the prerequisite: open, MERGEABLE, retargeted
to `main`, and waiting on remote pytest at record time. Operator-review capture
and real candidate backtest scoring remain unbuilt; the new status helper
honestly reports zero reviewed decisions until that workflow exists.

C49: GF-3d Phase-8 operator-review events are built and opened as stacked PR
#239 (`caffen/gf3-phase8-gate-review-events@d0b04d0e`), targeting PR #238's
branch.

Built in C49:

- Added typed `skill.patch_gate_reviewed` events and bumped event schema to v31.
- Added `SkillPatchGateReviewedPayload`, schema/codegen exports, generated
  reading types, and Research narration coverage.
- Added `record_phase8_gate_review(...)`.
- Updated `phase8_calibration_status` to join review events to decision events
  by `decision_event_id` with a patch-id fallback, while preserving legacy
  inline review fields.

Verified in C49:

- `pytest tests/test_phase8_calibration_status.py tests/test_events_schema.py tests/test_phase8_orchestrator_gate.py tests/test_phase8_gate.py tests/test_phase_runner_postconditions.py tests/test_skills_domain_auto_patch.py -q`
  -> 133 passed.
- Ruff on touched Python files -> pass.
- Strict mypy on audit + skill_growth source -> success.
- `tools/codegen/check_staleness.py` -> OK events/contracts.
- `git diff --check` -> pass.
- `npm run build` in `apps/reading` -> success with existing Vite chunk
  warnings.
- PR #239 remote checks at record time: axe-core, Cloudflare Pages, and Strix
  Security Review SUCCESS; lostpixel still IN_PROGRESS.

Current status: PR #239 is open and MERGEABLE but not fully green until
lostpixel completes. PR #238 remains open/MERGEABLE and fully green for its
attached checks. PR #237 remains open/MERGEABLE against `main`; all visible
checks are green except remote pytest still IN_PROGRESS. Candidate backtest
scoring and a full operator-review UI/CLI workflow remain unbuilt.

C50: GF-3e Phase-8 calibration readiness guard is built and opened as stacked
PR #240 (`caffen/gf3-phase8-calibration-readiness-guard@00c83bdc`), targeting
PR #239's branch.

Built in C50:

- Added `calibration_ready` and `calibration_notes` to `SkillPatchGate`.
- Enforcing mode now rejects an otherwise-acceptable candidate when loaded
  calibration evidence is not ready.
- `phase8_gate_from_env(...)` can receive computed readiness/summary without
  importing the audit layer into the gate module.

Verified in C50:

- `pytest tests/test_phase8_gate.py tests/test_gepa_phase8_bridge.py tests/test_phase8_orchestrator_gate.py -q`
  -> 21 passed.
- Ruff on `compounding/skill_growth/gate.py tests/test_phase8_gate.py` -> pass.
- `mypy --strict compounding/skill_growth/gate.py compounding/skill_growth/__init__.py`
  -> success.
- `git diff --check` -> pass.
- PR #240 remote checks: Cloudflare Pages and Strix Security Review SUCCESS.

Current status: PR #240 is open, MERGEABLE, and green for its attached stacked
checks. PR #239 is now fully green: lostpixel, axe-core, Cloudflare Pages, and
Strix Security Review all SUCCESS. PR #237 remains open/MERGEABLE against
`main`; all visible checks are green except remote pytest still IN_PROGRESS.
Candidate backtest scoring and production runtime loading of
`Phase8CalibrationStatus` remain unbuilt.

C51: GF-3f Phase-8 runtime calibration readiness is built and opened as
stacked PR #241 (`caffen/gf3-phase8-runtime-calibration-readiness@f47fa6c8`),
targeting PR #240's branch.

Built in C51:

- Added `ANTIEK_PHASE8_CALIBRATION_INVESTIGATION_IDS`.
- In enforcing mode, the Phase-8 runtime gate fails closed if that env var is
  absent or empty.
- When configured, `_run_phase_8` loads `phase8_calibration_status(...)` for
  those investigation IDs and threads `ready_for_enforcing` plus the summary
  into `phase8_gate_from_env(...)` before any auto-patch writer runs.
- Shadow mode remains unchanged.

Verified in C51:

- `pytest tests/test_phase8_orchestrator_gate.py tests/test_phase8_gate.py tests/test_phase8_calibration_status.py -q`
  -> 21 passed.
- Ruff on orchestrator/gate touched files -> pass.
- `mypy --strict orchestration/loop_one/orchestrator.py compounding/skill_growth/gate.py compounding/skill_growth/__init__.py`
  -> success.
- `git diff --check` -> pass.
- PR #241 remote checks: Cloudflare Pages and Strix Security Review SUCCESS.

Current status: PR #241 is open, MERGEABLE, and green for its attached stacked
checks. PR #237 remains open/MERGEABLE against `main`; all visible checks are
green except remote pytest still IN_PROGRESS. Candidate backtest scoring is
still unbuilt; current orchestrator auto-patch candidates still use
`candidate_backtest_score=0.0` and `cohort_size=0`.

C52: GF-3g Phase-8 backtest score adapter is built and opened as stacked PR
#242 (`caffen/gf3-backtest-score-adapter@beda675c`), targeting PR #241's
branch.

Built in C52:

- Added `middleware.backtest.score`.
- Added `score_backtest_report(...)` for deterministic bounded scores from
  `BacktestReport` outcome rows plus bounded structural penalties for
  invalidated cited edges and demoted cited chunks.
- Added `score_backtest_cohort(...)` with Wedge-2's >=50 graded-outcome
  readiness threshold.
- Exported the scoring API from `middleware.backtest` and corrected the package
  doc to reflect that the DB path and scoring layer are wired.

Verified in C52:

- `pytest tests/test_backtest_score.py tests/test_middleware_backtest.py tests/test_backtest_db.py tests/test_phase8_gate.py -q`
  -> 37 passed.
- Ruff on touched backtest files -> pass.
- `mypy --strict middleware/backtest/score.py middleware/backtest/__init__.py`
  -> success.
- `git diff --check` -> pass.
- PR #242 remote checks: Cloudflare Pages and Strix Security Review SUCCESS.

Current status: PR #242 is open, MERGEABLE, and green for its attached stacked
checks. For PR #237, I canceled the stale attempt whose pytest job had been
stuck since `2026-07-07T09:51:32Z` and reran the same workflow. The fresh
attempt has tsc, vitest, and keystone SUCCESS; pytest is still IN_PROGRESS
from `2026-07-07T10:19:35Z`. Candidate patch replay against a temporary skill
overlay remains unbuilt.

C53: GF-3h Phase-8 backtest cohort comparison is built and opened as stacked
PR #243 (`caffen/gf3-backtest-cohort-comparison@f043bd80`), targeting PR
#242's branch.

Built in C53:

- Added `BacktestComparison`.
- Added `compare_backtest_cohorts(...)` for baseline-vs-candidate cohort
  scores, delta, min graded-outcome cohort size, readiness, and notes.
- Readiness is false unless both baseline and candidate cohorts meet Wedge-2's
  graded-outcome floor.
- Exported the API from `middleware.backtest`.

Verified in C53:

- `pytest tests/test_backtest_score.py tests/test_middleware_backtest.py tests/test_backtest_db.py tests/test_phase8_gate.py -q`
  -> 39 passed.
- Ruff on touched backtest files -> pass.
- `mypy --strict middleware/backtest/score.py middleware/backtest/__init__.py`
  -> success.
- `git diff --check` -> pass.
- PR #243 remote checks: Cloudflare Pages and Strix Security Review SUCCESS.

Current status: PR #243 is open, MERGEABLE, and green for its attached stacked
checks. PR #237 fresh rerun still has pytest IN_PROGRESS from
`2026-07-07T10:19:35Z`; all other visible checks are green. Candidate replay
to materialize candidate `BacktestReport` cohorts remains unbuilt.


## Operator addendum (verbatim, 2026-07-09 — Grok /infinite primary orchestrator)

> I want to execute my Antiek project and the unexecuted sprints to build my comprehensive reading, research, and writing platform to be the perfect knowledge graph/base and thought partner/workstation (also when product and technology gaps arise, write specs and plan to set future agents up for perfect execution with precision, exhaustive attention to detail, and craftsmanship that is hard to vary). … I give you permission to merge code into main and deploy to backend/frontend. If the PR is stale and is not intellectually honest, fair, rigorous, and defensible to merge into main, then extract the core technical insights from those PRs and write new PRs that is of the high quality bar …

## CURRENT SUBGOAL (Grok infinite, cycle 285, 2026-07-09T07:08Z)

**Strategy change (mandatory after two-line honesty check):**

The multimedia "copy/evidence/no-spend boundary" stack (~87 open PRs, zero base=main) is **non-defensible idle burn**. All 12 documented multimedia sprints already shipped (#295–#342). Continuing micro-label PRs is consecutive low-delta work — forbidden by /infinite §2.

**This cycle's executable subgoal:**

1. Land a **defensible** knowledge-base ingest path: hardened Hermes research-event ingest (rebuild of #351 after codex BLOCKING) → PR #436.
2. Board hygiene: close/supersede non-defensible #351; do **not** merge the multimedia micro-stack; leave a coordination note for peer agents to stop the boundary spam.
3. Re-derive residual gaps against `origin/main` (verified): thought-partner dispatch, notebook hydration, flywheel substrate wiring = **CLOSED/STALE**; cold flywheel (`knowledge_reuse_count=0`) is content-cold not wire-dead; data-durability SPR-02 (IMPORT DATABASE self-ref FK) and CF `/multimedia/*` SPA-HTML edge allowlist remain REAL.

**Merge/deploy authority:** operator granted for this goal instance. Ship bar still requires mechanical green + heterogeneous verify + hardenx + five values.

## CURRENT SUBGOAL (Grok infinite, cycle 288, 2026-07-09T07:56Z)

**Shipped this cycle:** PR #437 Caddy `/multimedia*` allowlist → `origin/main@03108115` + production deploy. Live: `/multimedia/assets` returns API JSON 401 (auth), not SPA HTML. `build_sha` parity confirmed.

**In flight:**
1. **#436** Hermes hardened ingest (codex security rounds closed TOCTOU/DoS/redaction/walk-cap) — land when CI green.
2. **#439** NotDiamond Wave 1 advisory adapter (schema 31→32) — heterogeneous review then land.
3. **Settings model/budget SPR-01** — brief at `.infinite/sprint-briefs/C288-settings-model-budget.md`; Settings UI still stub.

**Still residual vs operator north star:**
- Midnight oil: continuous daemon exists; `spawn_fn` still `no_op_spawn`; no time/goals/price-ceiling UI.
- Floating research windows / merge instances / twin-note productization — not built as interactive surfaces.
- Antiek-bench — missing.
- Book marketplace partial; Substack deferred in master-spec.
- Cold flywheel (`knowledge_reuse_count=0`) needs operator dogfood through D2.

**Merge/deploy authority:** operator granted; ship bar still mechanical + heterogeneous + hardenx + five values.

**Strategy:** stop multimedia micro-PR burn; compound knowledge/research workstation path.


## CURRENT SUBGOAL (post cycle 288, 2026-07-09T08:36Z)

**Shipped this session:** #437 Caddy `/multimedia*` (live 401 JSON) + #436 hardened Hermes ingest (prod build_sha 50a0d5ef, HERMES_INGEST_VERSION=2).

**Next highest-value unblocked:**
1. Run a **limited Hermes ingest** against the real graph (library is live; 97 inv / 2171 events ready) so the corpus compounds — then distill.
2. Do **not** continue multimedia copy-boundary micro-PRs; prefer closing the floating stack.
3. Coordinate with peer lanes (notdiamond, settings model-budget, research-workstation) via board before claiming.
