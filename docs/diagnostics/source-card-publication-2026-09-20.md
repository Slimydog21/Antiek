# Source-card publication synchronization — 2026-09-20

Concurrent creators could reject the same valid PNG while its publisher was removing its temporary hard link. Publication now takes an exclusive flock on an independently opened output-directory descriptor through temporary-file cleanup. Verification takes a shared lock on that directory before opening the PNG relative to the descriptor. The reader's single-link, owner, mode, size, PNG-shape and digest checks remain in force.

## Failure Dossier

### Signatures

`_publish(root: Path, name: str, payload: bytes) -> None` and `_private_png(path: Path) -> str` retain their contracts. Internal `_locked_directory(root: Path, operation: int) -> Iterator[int]` owns and closes its descriptor; `_publish_locked` and `_private_png_locked` work under that lock.

### Numbered failure chain

1. CI35509492690 shard0 failed `test_concurrent_create_elects_one_identical_card` on CLI commit `3a09e4357`; source-card files were unchanged from main `f24981db2`.
2. `_publish` links the complete, fsynced temporary inode to its final PNG name, then fsyncs the directory before unlinking the temporary name.
3. A concurrent creator sees the final name and verifies it before cleanup. During this window, `st_nlink` is two.
4. The old reader tried twenty 5ms sleeps, then rejected the inode as not private and bounded. This timed retry came from `ef4903540`; it did not synchronize publication.
5. A controlled writer pause after actual `os.link` reproduces the exception with valid owner, mode, size and PNG bytes. After cleanup the same inode passes. CI did not log the failing stat field, so its exact interleaving is inferred from the matching stack and deterministic reproduction.

No LLM, external provider, production database or network call participated in the failure or tests.

## Scope Map

| Surface | Verification |
|---|---|
| Thread reader during publication | Actual `_publish`, paused after real hard link; actual reader must remain pending for three seconds, then verify after release |
| Separate-process reader during publication | Independent interpreter using actual `_private_png`; same barrier and result assertions |
| Persistent hard link | Must still raise the original privacy/bounds error |
| Two concurrent registry creators | Existing database-backed test, plus ten independent pytest invocations |
| Registry replay, graph/font/file tamper, attestation | Full source-card module |
| Replay verification while another writer needs the database | Real write-context SELECT and independent FlockWriteCoordinator acquisition while `_reopen` is paused |
| Workstation/runtime/coordinator/video bridge | Five-module direct-consumer suite |

## Handoff

### Env Card

- Worktree: `/Users/slimydog/Antiek/.worktrees/source-card-publication-20260920`.
- Branch: `fix/source-card-publication-20260920`.
- Base: `f24981db2bde8ce2fb88158fc54460cfd168c294`.
- Interpreter: `/Users/slimydog/Antiek/platform/.venv/bin/python`, Python3.12.13, macOS.
- `PYTHONPATH=$PWD`, scratch `ANTIEK_HOME=$PWD/.audit/runtime`, scratch `ANTIEK_DUCKDB_PATH=$PWD/.audit/runtime/graph.duckdb`; pytest additionally isolates stores per test.
- Network/provider calls: none. Logs retained in `.audit/`.

### Not proved

Linux CI has not run this commit. Local verification covers macOS directory-flock behavior, including independent descriptors and a separate process. Windows support is not added; the existing runtime already uses POSIX fcntl. No full multimedia suite, production rendering or deployment claim. A process killed after linking may leave an orphan second link; it remains rejected rather than silently repaired. Locks are advisory and coordinate cooperating code, not arbitrary same-owner filesystem mutation.

### Status

Local scoped and consumer verification pass. GLM accepted the initial synchronization change at 92/100. The subsequent database-lock ordering change requires a follow-up review; Linux CI remains required.

### Files touched

`substrate/multimedia/local_source_card.py`, `tests/test_multimedia_local_source_card.py`, this dossier. No schema, writer, db_lock, Parquet, dependency or CLI changes.

### Milestones (checkboxes)

- [x] Reproduce delayed-publication failure before production edits.
- [x] Replace time-based retry with directory locks and relative descriptor open.
- [x] Preserve strict persistent-hardlink rejection.
- [x] Verify thread/process behavior, existing concurrent creation and direct consumers.
- [ ] Independent review and Linux CI.

### Gate results

All commands used the interpreter and scratch environment above from this worktree. Logs retain full output and exit codes are reported below.

| Gate | Exit | Evidence |
|---|---|---|
| New regression selection before fix | 1 | 2 failed, 1 passed; `.audit/publication-red.log` |
| Final delayed-publication/hardlink regressions after test cleanup refinement | 0 | 3 passed; `.audit/publication-final-regression.log` |
| Full source-card module | 0 | 12 passed; `.audit/publication-green.log` |
| Direct consumers | 0 | 53 passed, no skips; `.audit/publication-consumers.log` |
| Existing concurrent creator, ten independent invocations | 0 each | `.audit/publication-concurrency-repeat.log` |
| Ruff on source and test | 0 | `.audit/publication-ruff.log` |
| Strict mypy on source and test | 1 | Seven existing test annotations missing; production and added tests clean; `.audit/publication-mypy.log` |
| Base strict mypy with shadow files from f24981db2 | 1 | Same seven errors; `.audit/publication-mypy-base.log` |

Canonical consumer command: `python -m pytest tests/test_multimedia_local_source_card.py tests/test_multimedia_local_workstation.py tests/test_multimedia_local_runtime.py tests/test_multimedia_local_production_coordinator.py tests/test_multimedia_local_video_bridge.py -q`.

Typing command: `python -m mypy --strict --follow-imports=silent --explicit-package-bases substrate/multimedia/local_source_card.py tests/test_multimedia_local_source_card.py`. Baseline uses `--shadow-file` for those two paths, preserving module context and configuration. Unchanged-line diagnostic comparison is retained in `.audit/publication-mypy-delta.json`.

### Decisions mid-flight

Lock the stable output directory instead of introducing a lockfile lifecycle. Every acquisition opens its own descriptor, so independent threads and processes contend correctly. Readers share locks; publication serializes across that output directory. Rendering happens before locking. Retain no-overwrite hard-link publication and fail-closed file validation.

### Assumptions surfaced

Output directories remain private, as required by the existing registry constructor. A registry create releases all filesystem locks before acquiring the database writer. Both newly inserted and concurrently elected rows are reopened only after the database write context exits. Slow shared-filesystem-lock acquisition during verification therefore does not retain that write context. No filesystem-locked code acquires a database lock. Closing the directory descriptor releases its flock on both success and exception paths.

The first exploratory half-second barrier run did not expose the old race under local scheduling load. The retained red run uses a three-second hold and fails both thread and process cases; the tests keep that hold. Sleeps do not coordinate production behavior.

### Steelman rejected alternative

A longer retry could make this CI instance pass while retaining scheduler-dependent correctness. Allowing two links would weaken the artifact's privacy invariant. Synchronization makes cleanup completion, rather than elapsed time, the condition for verification.

### Open questions

The initial source received GLM ACCEPT92; a follow-up critic and Linux CI must assess the changed replay control flow. Crash-orphan recovery is intentionally outside this repair.

### Next sprint can start when

The orchestrator accepts this scoped commit after independent review and relevant CI. Ownership was handed off explicitly from both blocked source-card and coordinator lanes.

### Out-of-scope temptations

Retry-count inflation, broad filesystem cleanup, database/schema changes, unrelated multimedia changes, CI reruns and deployment.

### Source security scan

Hardenx scanned copies of the changed Python source and test with the repository's
.gitignore preserved. Strict scan exited 0, LOW, zero REAL and seven advisory
findings. This is source-only evidence, not dependency or production clearance.
The first reduced fixture omitted .gitignore and was classified as a Git tree
without ignore protection. It exited 1 for that fixture condition; both reports
remain under .audit/publication-hardenx*.json. No finding was waived.


### Review follow-up: release the database writer before verification

GLM returned ACCEPT92/100 for `3f1da4353` (`.audit/publication-independent-review.log`). It identified that the concurrently inserted existing-row branch still called `_reopen` inside the database write context. Since reopening can now wait on a shared filesystem flock, a stalled publisher could extend the database writer hold. Both outcomes now select their row under the same write context and perform `_reopen` after leaving it. The winning row, insert-if-absent semantics, MAC checks and file validation are unchanged; no schema or coordinator changes were made.

The added regression creates a real card, forces only the initial lookup to miss (the concurrent-creator interleaving), and leaves the write-context SELECT real. It pauses `_reopen`, then requires a second thread to acquire an actual FlockWriteCoordinator and read the row before verification resumes. The old flow times out; `.audit/publication-writer-red.log` records one failed test, exit1. This tests database-lock ordering without replacing the coordinator or database connection. Filesystem blocking is covered separately by the existing thread/process regressions.

The original ACCEPT and source-only Hardenx scan preceded this control-flow change; neither is represented as review or security clearance for the follow-up. The Scope Map formatting defect was also repaired. Board validation passed and origin was fetched before edits; root-owned state and other worktrees were not modified.

Follow-up gates: the same five-module consumer command passes **54 tests, no skips**, exit0 (`.audit/publication-review-consumers.log`). The new replay test supplies a later creation timestamp and still requires the previously elected artifact, pinning winner semantics as well as writer release. Ruff passes, exit0 (`.audit/publication-review-ruff.log`). Strict mypy reports the same seven baseline test annotation errors, no production errors and no introduced errors, exit1 (`.audit/publication-review-mypy.log` and source-mapped `publication-review-mypy-delta.json`). `git diff --check` passes. The earlier original53-consumer and initial source-review evidence remain historical rather than being relabeled as the new result.

### Follow-up review and final source scan

GLM follow-up review of a143aadc488ed7e3e1c949b3a589f844c6e7a8b3
returned ACCEPT, 94/100. It confirmed the shared reopen call occurs after the
database write context exits and preserves both elected and inserted rows.
The new regression proves a second writer can acquire during paused verification
and that a losing creator returns the original winner. Evidence:
`.audit/publication-followup-review.log`.

A fresh strict source-only Hardenx scan of the updated source and test exited 0,
LOW, zero REAL and seven advisory findings, recorded in
`.audit/publication-final-hardenx.json`. This does not clear dependencies or
production. Linux CI is pending. The paused-verification test targets the
previously defective replay branch; the new-insert branch shares the same call
site but has no separate pause assertion. Crash-orphan recovery remains outside
this repair, and timeout-based test deadlines retain a load-related flake risk.
