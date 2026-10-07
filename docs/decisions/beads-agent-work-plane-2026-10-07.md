# Decision: beads is Antiek's agent work plane, never its knowledge plane

**Date:** 2026-10-07 (Asia/Riyadh)
**Status:** **accepted** for the compute research-lane scope (the dispatcher
writing beads for `compute run --bead`, under the conditions in "Accepted
scope"); **proposed** for everything else (the engineering-fleet board, any
product projection, Midnight Oil run graphs, `bd prime` wiring), which waits
for the operator decisions at the end and for the owners named there.
**Lane:** `opus-aws-backbone-infra-20261007`
**Relates to:** `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md`
§7 (the dispatcher is the only beads writer; lanes and lane hosts never run
`bd`); PR #3728 `runtime/compute_admission` (open), whose README already says
"Beads claim leases are advisory and are not replicated execution authority".

Evidence labels: **[M]** measured (source at a named tag, live `--help`, or a
sandbox run with an isolated `HOME`), **[I]** inferred from measured facts,
**[A]** assumed. "Forensics" means the beads reports of session `a880aa51`
(`scratchpad/beads/{datamodel,storage,claims,sync,surfaces,ops,philosophy}.md`),
the integration design `ANTIEK-BEADS-DESIGN.md` (cited as *design*), and its two
adversarial reviews `CRITIQUE-correctness.md` and `CRITIQUE-antiek-fit.md`
(cited as *correctness* and *fit*). Where a review corrects the design, the
review wins and this record states the corrected form. Upstream is
gastownhall/beads; facts are pinned to tags v1.3.0 (installed), v1.3.1 and
HEAD `77ab98079`. The numbers this record depends on are restated so it stands
without the scratchpad.

## Context

The operator wants beads in Antiek: a dependency-aware work graph with a
ready frontier (`bd ready`), `discovered-from` side quests, notes that survive
a session, and session-start priming. The demand is real and visible in the
control plane: in one hour on 2026-10-07 one lane wrote eight claim statuses
outside the board's seven-value enum (`claimed-waits-SPR-06` three times,
`ready`, `claimed-wave-2`, `claimed-wave-2-optional`, `claimed-wave-3`,
`executing`), smuggling `blocks` edges and a ready frontier into a free-text
field, and that is part of what turned the validator red [M, fit §0.5].

Today there are **zero live beads workspaces and zero writers** on the Mini;
only `~/.beads/{machine-id,eventsData}` exists [M, fit §0]. compute 1.6.0 (the
draft that adds `compute run --bead`) is not installed: `compute --help`
prints 1.5.1 [M, fit V19].

Beads is a work tracker on embedded Dolt. It has no fencing token, no attempt
bound, an unauthenticated actor (default `git user.name`, with `.`, `_` and
`-` runs collapsed) and a hard-coded 5-minute claim lease
(`internal/storage/issueops/lease.go:26`; `issueops/identity.go:50-84`) [M,
claims.md §0, §9]. Embedded Dolt serializes concurrent writers with an
unbounded backoff (`embeddeddolt/open.go:40-43`, `MaxElapsedTime = 0`) and
does not fence its own compaction against writers: only `bd backup restore`
takes the exclusive workspace gate (`cmd/bd/workspace_gate.go:128-135`) [M,
correctness §2].

## Decision

### 1. Work plane, not knowledge plane

Beads holds what agents are doing, what is blocked, what was discovered
mid-run and what waits on CI, a PR or a person. **DuckDB stays the only store
of anything a user sees.** That is upstream's own boundary
(`docs/related-projects.md:19-21`, `engdocs/PROJECT_CHARTER.md:29-80`) and
Antiek's (`CLAUDE.md` invariants 1 and 3: DuckDB single-writer,
substrate-as-source-of-truth) [M]. No bead is the canonical copy of a finding,
claim, source or memory; nothing in DuckDB may require a bead to still exist,
because `bd gc` and compaction later delete or squash it.

`bd remember` never feeds account memory (`substrate/memory`): memories are
unauthenticated, workspace-scoped, converge "theirs wins" on pull
(`versioncontrolops/mergesettle.go:23,391-394`) and are injected into every
agent session [M, design §8.1].

### 2. Authority, per surface

The design's single chain "compute flock > `agent_work` lease > bead" is
withdrawn: `agent_work` is the product's comment/reply agent queue
(`substrate/agent_work/domain.py:13-29`, leased by bridge credentials in
prod), and no compute lane ever holds one [M, fit V7, F17]. Authority is stated
per surface instead, and **a bead is advisory on every one of them**:

| Surface | Execution authority | What the bead is |
|---|---|---|
| Research lanes under compute | compute's kernel `flock` on the lane lease (`compute run --bead ID` uses the bead id as the lane key; the flock decides) | a visibility record of the lane's state, written only by the dispatcher |
| Product compute admission (PR #3728, when it lands) | its own in-process lane lease and `compute_ledger.v1` | advisory, exactly as #3728's README says |
| Product agent turns (`agent_work`) | the fenced `agent_work` lease (`lease_id` + `attempt_no`) | unrelated; no bead is involved |
| Engineering fleet | the board claim (owner) under the CEO directive | at most a work item beside the claim (pilot, below) |

No code path may treat a bead status, assignee or claim as permission to
spend, merge, deploy or execute. The bead id **names** a lane; it does not
make two lease systems agree (the "can never disagree" claim is refuted:
beads' lease is fixed-TTL, revived by heartbeat, unfenced, and recovery takes
at least 15 minutes against an instant flock release) [M, claims.md §2-3].

### 3. Invariants (as corrected by both reviews)

- **I2 One writer per workspace, one lock file per workspace.** At most one
  `bd` process writes an embedded workspace at any instant. The lock lives in
  the workspace (`<ws>/.beads/antiek-writer.lock`) and **every** writer takes
  that same file: the compute dispatcher, any wrapper, and the
  export/backup/compaction jobs. Two lock paths for one database breaks I2:
  compute 1.6.0 locks `$COMPUTE_HOME/state/beads.lock`, so a maintenance job
  holding any other file could let a compute write commit between
  compaction's branch snapshot and its `DOLT_RESET('--hard')` of `main`
  (`versioncontrolops/compact.go:44-77`) and lose it [M paths, I race;
  correctness F11, fit F8]. Writes wait on the lock with a bound
  (compute's `state_lock` wait is unbounded today, `compute-1.6.0.py:228-232`).
  Maintenance calls are never run under a SIGKILL timeout: `bd compact`'s
  cleanup is a Go `defer` that SIGKILL skips (`compact.go:27-35`); use
  SIGTERM-then-wait and clear a leftover `compact-tmp`/`flatten-tmp` branch
  inside the lock first [M, correctness F12].
- **I3 Knowledge stays in DuckDB** (section 1). Any later projection is
  one-way and idempotent, copies content at read time, and enters the graph
  only through the existing single-writer funnel.
- **I5 Hardened invocation, on every call.** argv only, no shell,
  `stdin=DEVNULL`, an explicit absolute `BEADS_DIR`, and
  `BD_DISABLE_METRICS=1 DO_NOT_TRACK=1 BD_DISABLE_EVENT_FLUSH=1
  BD_NO_REMOTE_ADOPT=1 BD_NON_INTERACTIVE=1 NO_COLOR=1`, a unique actor, and no
  `*_API_KEY`/`*TOKEN` in the environment (which also stops `bd compact --auto`
  and `find-duplicates --method ai` from shipping content to an LLM API). "Every
  call" includes `bd config set` and `bd export`, which the design's own
  recipe left bare [M, fit F15]. **Every read passes `--readonly`**: a
  non-readonly read opens the store writable and runs `schema.MigrateUp`
  (`embeddeddolt/store.go:378-385,427`) [M, correctness F10].
- **I6 One schema family.** Every binary that touches a workspace is in the
  1.3.x schema-66 family. The gate checks `bd version --json` for
  `version` in {1.3.0, 1.3.1} **and** `branch` in {v1.3.0, v1.3.1}, and pins the
  sha256 of the resolved binary, because a build from main also prints
  "1.3.0" (`cmd/bd/version.go` at HEAD) [M, correctness F10]. Exit 14 is
  `ExitMigrationFrozen`, not skew (`cmd/bd/errors.go:162-167`); skew is the
  "forward drift" error, and its own remediation text (rebuild from main,
  or `CGO_ENABLED=0 go install`) is never followed [M, ops.md §5-6].
- **I7 No shared git index.** Workspaces live at
  `~/.local/share/antiek-beads/<project>/`, which the home repo ignores
  (allowlist `.gitignore:1:/*`) [M, design D-4]. They are created only by the
  measured nested-repo recipe: `git init` the workspace directory first, then
  `bd init --skip-agents --skip-hooks --stealth --prefix <p> --quiet` inside it
  with the I5 environment. That confines every git side effect to the inner
  repo and writes `no-git-ops: true` [M, reproduced twice: design D-2,
  correctness §3]. Never a default `bd init` anywhere under `~` or in
  `platform/`; never `bd setup claude --global`; never a Dolt remote pointing
  at the home repo's `origin`, which is the public `Slimydog21/Antiek`
  [M, fit V24]. Production workspaces are not under `/private/tmp`, which
  context-resolving commands refuse as unsafe (`internal/beads/context.go:468-500`).
- **I8 Unique actors, guarded writes.** One actor per writer attempt
  (`compute:<job_id>`), never two that differ only by `.`, `_` or `-`. State
  changes carry **both** guards in one call, `--if-status <seen>
  --if-assignee <actor>`, which bd checks in one in-transaction
  compare-and-set (`cmd/bd/update.go:939-975`;
  `issueops/update_cas.go:34-58`) [M, correctness F4]. Swapping the status
  guard for the assignee guard alone (design B-3) would let compute reopen a
  bead a person closed mid-job, erasing its close reason. `bd close` has no
  compare-and-set at 1.3.x; it is fenced only by `AssigneeMatches`, which
  refuses a non-assignee actor with exit **1**, not 13
  (`cmd/bd/close_direct.go:83-87`; `internal/validation/issue.go:165-175`), so
  callers classify that refusal by name, and `--force` is never the
  workaround (it also waives the pinned, gate and open-children guards)
  [M, correctness F2, fit F10].
- **I9 Literal `closed` is done.** Only `closed`/`pinned` unblock dependents
  and only literal `closed` stamps `closed_at`
  (`issueops/blocked_state.go:270,317,324`) [M]. Antiek terminal states map to
  `closed` with a structured reason; custom statuses are WIP only.
- **I12 Closed is not landed.** A bead for code work closes only with merge
  evidence (`merged_main_sha` an ancestor of `origin/main`, or the PR MERGED),
  the rule `board-reconcile.py` already enforces. `gh:run` gates are not CI
  evidence: they resolve on `conclusion=skipped` (`cmd/bd/gate.go:1098`) [M].

### 4. Measured hazards this record exists to prevent

| Hazard | Measurement |
|---|---|
| **A default `bd init` commits into the enclosing repo.** Even with `--skip-agents --skip-hooks` it runs `git -c core.hooksPath= commit --no-verify` with no pathspec, sweeping whatever is already staged, and git-adds the repo-root `.gitignore`. Every compute project root (`~/Solcoa`, `~/Volantis`, `~/Inferact`, `~/LCH`, `~/Antiek`) resolves to the home repo, so this would commit into `~/.git` and edit `~/.gitignore`. compute 1.6.0's refusal hint recommends exactly this command (`compute-1.6.0.py`, `bead_root`). | live sandbox: a pre-staged `unrelated.txt` landed in bd's init commit; `v1.3.0:cmd/bd/init.go:2190`, HEAD `init.go:3719-3768`; `git rev-parse --show-toplevel` = `/Users/slimydog` for all five [M, ops.md §3, design D-3] |
| **Remote adoption publishes `refs/dolt/data`.** In a non-stealth repo with an origin, `bd init` wires git `origin` as the Dolt remote even with `BD_NO_REMOTE_ADOPT=1`, and records `sync.remote` in the tracked `config.yaml`; after that the consent gate no longer applies and the next `bd sync`/`bd dolt push` publishes the issue history to origin. On a public repo that is a disclosure. | live sandbox "Configured Dolt remote: origin"; `cmd/bd/init.go:1288-1310,3287-3297`; `cmd/bd/dolt.go:453-487` [M, sync.md §0.4, §3] |
| **Telemetry is default-on.** `bd metrics` reports "on" in an empty `HOME`; GA4-format `cli_command` events go to `https://gastownhall-eventsapi.com/mp/collect` via a detached flusher child; the first-run notice is suppressed under `--json`, `bd prime` and hooks; a prune-only flusher still spawns unless `BD_DISABLE_EVENT_FLUSH=1`. Upstream `SECURITY.md:64-65` says there is no telemetry. | `internal/metrics/{metrics.go:21,127-136, flusher.go:64-80, spawn.go:57,166-200}` [M, ops.md §1] |
| **`bd ready` truncates at 100.** The default `--limit` is 100 on 1.3.0; compute 1.6.0's `compute beads ready` passes none. | live `bd ready --help`; `compute-1.6.0.py` `cmd_beads` [M, design D-5] |
| **1.3.0 strands fan-in dependents; 1.3.x priming bans MEMORY.md.** Parallel closes of two blockers left a dependent permanently `is_blocked=1` (#6716, fixed in 1.3.1). 1.3.x `bd prime` injects "Do NOT use MEMORY.md files" and "Prohibited: Do NOT use TodoWrite", which contradicts this operator's memory system. | `v1.3.1:CHANGELOG.md:34,394`, test commit `d79ef4804` in `v1.3.0..v1.3.1`; `v1.3.0:cmd/bd/prime.go:919-921`, override file honoured at `:108-112` [M, ops.md §5, correctness §3, F17] |
| **Builds from main migrate a workspace to schema 69, one-way for every pinned binary.** 1.3.0, 1.3.1 and 1.3.2-rc.1 all stop at migration 0066; HEAD is at 0069 and still prints "1.3.0". Every writable open migrates up; afterwards every pinned binary is refused with skew, and the only way back is the schema-cursor rollback runbook. | migration `ls-tree` per tag; `docs/getting-started/upgrading.md:233-237` [M, ops.md §5-7, correctness F10] |

### 5. Version pin and placement

- **bd 1.3.1 from the upstream release tarball**, verified against
  `checksums.txt` and `gh attestation verify`, installed to a versioned path
  first on `PATH`: `beads_1.3.1_darwin_arm64.tar.gz` on the Mini,
  `beads_1.3.1_linux_arm64.tar.gz` (sha256 `c3b32c71a6c0cd6358a12c28272b17e6818db991da192f87df52339c222e423a`,
  glibc >= 2.34) wherever a Linux host ever needs it [M, ops.md §9]. Not
  Homebrew: its 1.3.0 is a different build (ICU, no `gms_pure_go`) and
  `brew upgrade beads` also moves the dolt CLI to 2.4.2 [M, ops.md §6, §8, §9]. 1.3.1
  is a binary swap from 1.3.0 (same schema 66); upgrade under the workspace
  lock with a `bd export --all` first and `bd recompute-blocked --json` once
  after. Never main, `go install`, or `CGO_ENABLED=0`.
- **Embedded mode only.** The dolt CLI pin (2.2.0, because 2.3.0/2.3.1 break
  `CALL DOLT_RESET('--hard')` on 3 of 60 and 3 of 100 fresh databases,
  `docs/architecture/dolt.md:58-75`) applies **only when server mode arrives**,
  which this record does not adopt [M, ops.md §7].
- **Lanes and lane hosts never run `bd`** (backbone ADR §7): no binary, no
  `.beads`; results return through the dispatcher's stage-out and the
  dispatcher records them.
- **No Dolt remote and no `bd sync`.** Backups are a nightly
  `bd export --all --include-memories` plus `bd backup sync` into a **dated**
  directory with a retention count (a single directory is overwritten nightly,
  so one bad run reaches the only Dolt-native copy within 24 hours [M,
  correctness F8]), under the workspace lock. This is single-disk durability:
  the Mini has no off-host backup job (no Time Machine destination, no
  backup LaunchAgent) [M, fit V24]. Restore is `bd init` with the recipe, then
  `bd backup restore --force <dir>`; a restore can rewind the journal sequence
  and change `_project_id`, so any consumer of the journal re-baselines after
  one (`docs/reference/events-journal.md:446-450`;
  `cmd/bd/backup_restore.go:96-102`) [M, correctness F7].
- **No decay, no semantic compaction, no compaction yet.** `bd gc` without
  `--skip-decay` deletes closed beads older than 90 days; `bd admin compact
  --auto` ships content to third-party LLMs. Weekly history squash
  (`bd compact`) waits until bytes per write are measured, because it erases
  the per-row commit history (one Dolt commit per `bd` call) [M, correctness F6].
  The events journal stays at its default floors (7 days / 100k rows) unless a
  projection reads the workspace [M, correctness F9].

### 6. Accepted scope: compute research lanes

Accepted: compute's dispatcher may write beads for `compute run --bead ID`,
one embedded workspace per project at `~/.local/share/antiek-beads/<project>/`,
the dispatcher the only writer, plain status writes (never `--claim`, so no
lease to heartbeat and `bd reclaim` ignores these beads), with the job id in
the actor and the ledger reference in the close reason. compute 1.6.0 already
has this shape (`compute-1.6.0.py` `bead_admitted`, `bead_finish`: admission
`--if-status <seen>`, terminal writes `--if-status in_progress`, exit 13 logged
as "changed outside compute") [M].

**Conditions before any project is configured with a beads workspace** (owner:
the compute lane, `~/.agents/compute` release after 1.6.0; none is product
code):

1. The refusal hint in `bead_root` stops recommending
   `bd init --skip-agents --skip-hooks` in a project root and prints the I7
   recipe; `bead_root` reads `beads.projects.<p>.dir` (default
   `~/.local/share/antiek-beads/<p>`) and refuses a workspace whose
   `git rev-parse --show-toplevel` is `$HOME` unless its `config.yaml` has
   `no-git-ops: true` (design B-1, the one dangerous defect) [M].
2. I5 environment and `BEADS_DIR` on every call; `--readonly` on every read.
3. `--limit 0` on `bd ready`.
4. The I6 gate (version, branch, binary sha256) on the first call per process.
5. The I2 lock moves into the workspace and every writer takes it, with a
   bounded wait.
6. Guards per I8: blocked/released writes carry `--if-status in_progress
   --if-assignee compute:<job>`; admission sets `-a compute:<job>`; the done
   close classifies the exit-1 assignee refusal as "changed outside compute".

With the first project that opts in, not before: admission only from
`bd ready --json --limit 0 --readonly` (or a takeover of a bead held by a
`compute:<job>` the ledger proves terminal), and refusal of beads with open
`parent-child` children, since `bd close` refuses a parent with open children
(`cmd/bd/close.go:139-164`) (design B-2, B-6).

## Deferred, and why

- **Product and Midnight Oil.** No projection of beads into DuckDB, no
  `beads_bridge` package, no event-schema bump, no run-graph materializer.
  Midnight Oil is frozen: no agent may create another Midnight Oil PR or
  worktree until it proves its seam in PR #709's keep partition
  (`.infinite/CEO-DIRECTIVE.md:152-158`), and #709 is closed unmerged [M, fit
  V13]. A projection would also collide with PR #3728, which reserves
  `owner_user_id`, `tenant_id`, `project_id`, "the single-writer graph funnel"
  and "event migration" for Undertaker p2C
  (`docs/decisions/compute-admission-phase1-2026-10-06.md:11-15,29-31` on the
  PR); the design's projection used `project_id` with a different meaning, in
  the same database and event union [M, fit §2.1]. If a projection is ever
  justified it routes through Undertaker p2C **after #3728 lands**. When a run
  graph is needed, `bd create --graph` is the transactional path on 1.3.x
  (`cmd/bd/graph_apply.go:22-56,931-1096`); `bd batch` cannot express parents,
  metadata or references to ids minted in the same batch
  (`cmd/bd/batch.go:271-273,388-417`) [M, correctness F5].
- **Fleet board mirror or write path.** The control-plane validator is red
  (rc 1, 42 errors on 2026-10-07: dead worktrees and off-schema statuses), and
  the directive blocks new claim mutation on a red preflight
  (`CEO-DIRECTIVE.md:174-175`) [M, fit F2]. A board migration would also have
  no owner for the 661 `active_agents` rows and the merge singletons, which the
  validator fingerprints and `board-close-guarded.py` writes (`:487-505`), and
  the design's mirror would duplicate every closed row on each run because
  `bd list --external-ref` excludes closed beads unless `--all` is passed
  (`internal/workapi/list.go:237-245`) [M, correctness F1-F3]. **Start instead
  with a lane-DAG pilot:** one fleet workspace made with the I7 recipe, one
  small writer wrapper that enforces I2/I5/I6/I8, and one spec
  (`specs/antiek-keyboard-panes-agents-20261007`, the lane already encoding
  dependencies in status strings) as epic, sprints as children, "waits-SPR-06"
  as a `blocks` edge, "ready"/"wave-N" as `bd ready`. The board keeps
  ownership and its seven statuses; no mirror, no migration. Decide after 14
  days on counted adoption: bead writes by distinct actors, off-schema
  statuses from that lane (target 0), and INBOX/run-ledger appends for that
  spec [fit §7].
- **Server mode, multiple writers, `bd serve`, remotes.** Until G7 or a
  measured lock-wait problem (p95 above 30 s).
- **Upstream `beads_mcp`.** No registry row: nothing imports it, and a Tier-0
  row as drafted fails `load_registry` (`vouched_at` and `justification` are
  mandatory) [M, fit F6].

## Operator decisions still live

| ID | Decision | Recommendation |
|---|---|---|
| OD-2 | Install bd 1.3.1 from the verified upstream tarball on the Mini (not `brew upgrade`, which also moves dolt) | yes, before the first workspace |
| OD-3 | Off-host durability for beads data: a private git repo as Dolt remote with one nightly pusher, `aws://` (DynamoDB + S3 in eu-north-1), or copying the dated backup directory with a new off-host job. Never the public `origin` | decide before relying on beads for anything not reconstructible from the compute ledger |
| OD-5 | Ratify the proposed parts of this record, and the reading of master-spec §16 ("substrate stays tool-thin": beads lives off the substrate) | ratify the boundary now; product parts stay deferred |
| OD-P | Approve the lane-DAG pilot on `antiek-keyboard-panes-agents-20261007` once the board owner has the validator green | yes |
| OD-8 | Wire `bd prime` into Claude/prime-agent sessions with a `.beads/PRIME.md` override (keeps MEMORY.md and TodoWrite permitted), and move work-state entries out of MEMORY.md into the fleet workspace | after the pilot shows use |
| OD-1 | Make beads the board's write path (strangler) and amend the directive's claim protocol, co-signed by the control-plane owner | only on pilot evidence, and only with JSON-owned sections for `active_agents` and the merge singletons |

Settled here, no longer open: OD-9 (`agent.profile = conservative`
everywhere) is the rule. Parked with their blockers: OD-4 (Midnight Oil
executor) and OD-7 (run-progress view) with the Midnight Oil freeze; OD-6
(server-mode host and dolt pin) with G7.

## What would change this

- Pilot adoption is absent after 14 days: stop at the compute scope and
  delete the fleet workspace (one directory).
- PR #3728 lands and Undertaker p2C wants agent-work state in DuckDB: a new
  record, owned there, decides any projection.
- Upstream ships a release line past 1.3.x with a schema change: re-run I6 and
  the hazard table against it before any swap.
- The Mini gains an off-host backup (or the dispatcher moves): revisit OD-3.

## Evidence

- Session `a880aa51` scratchpad `beads/`: `ANTIEK-BEADS-DESIGN.md` (§0-§12,
  measurements D-1..D-11), `CRITIQUE-correctness.md` (F1-F21, single-writer
  audit, answered open questions), `CRITIQUE-antiek-fit.md` (V1-V27,
  collisions, beads-lite plan), and the reader reports `ops.md`, `sync.md`,
  `claims.md`, `storage.md`, `datamodel.md`, `surfaces.md`, `philosophy.md`.
  Sandboxes `sandbox-design/`, `sandbox-critic-correctness/`,
  `sandbox-critic-antiek-fit/` (isolated `HOME`; no write outside them).
- compute 1.6.0 draft: `scratchpad/compute-wt` branch
  `feat/compute-1.6.0-node-beads` (`compute-1.6.0.py` beads section,
  `policy.yaml` `beads:` block).
- Control plane: `~/Antiek/.infinite/CEO-DIRECTIVE.md`, `agent-board.json`,
  `validate-control-plane.py`; `~/Antiek/bin/board-reconcile.py`,
  `board-close-guarded.py`.
