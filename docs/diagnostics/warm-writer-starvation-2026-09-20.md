# Warm writer starvation, 2026-09-20

Nightly backups on September 19 and 20 exported and uploaded nothing. The
API retained a parked DuckDB writer beyond its nominal idle lease. Scheduled
arXiv ingestion timed out on the same coordinator. The repair preserves warm
reuse while independently expiring parked handles and yielding to contenders.

### Env Card

Base: `ee283d9c8f7500ec504db00b4424b52bab8b4c35`.
Worktree: `/Users/slimydog/Antiek/.worktrees/warm-writer-handoff-20260920`.
Python: canonical platform `.venv/bin/python`, 3.12.13; additional verification
uses `.venv314/bin/python`, 3.14.5. Logs are under `.audit/warm-writer/` in the
worktree. LLM contacted on reproduced failure paths: no. Tests use temporary
DuckDB files and subprocesses; backup upload is stubbed and archive restore is real.

### Failure dossier

1. `LockedConnection.close()` parked a successful writer and kept its flock.
2. `_take_warm_slot()` checked expiry only on the next local acquisition.
   An idle owner therefore retained the lock indefinitely. Repeated local writes
   also renewed the lease without respecting published external waiters.
3. Backup and graph export duplicated a raw-flock loop, so they never requested
   handoff. Export's 15-second timeout was shorter than the default 20-second lease.
4. An independent audit then reproduced a residual-reader defect. A same-config
   read handle retained DuckDB's own lock after warm expiry released the sidecar.
   An external writer failed in roughly 4 ms despite a two-second budget.

Two core subprocess tests failed before the runtime change. Two actual caller
regressions failed against raw snapshot callers. The residual-reader suite
produced four failures and two passes before the contention retry fix. These
failures establish behavior, not just a static missing-code assertion.

### Scope map

| Entry point | Evidence | Scope |
|---|---|---|
| Warm close/reuse/expiry | `tests/test_db_lock_warm_writer.py` | Idle expiry, published handoff, stale callbacks, flush race, thread/probe failures |
| External writer with surviving reader | `tests/test_db_lock_reader_handoff.py` | Native lock retry, deadline and cleanup |
| Read-only snapshot | `tests/test_db_lock_snapshot.py` and reader-handoff tests | Physical RO, no logging, contention, source bytes, failures |
| Rendered backup script | `tests/test_backup_deployed_script.py` | Warm external owner, timeout0, archive restore, blocked upload |
| HTTP graph export | `tests/test_export_routes.py` | Warm same-process owner, source unchanged, value-free errors |
| Live Linux/R2 deployment | Not run | Requires integration and production verification |

### Files touched

`runtime/db_lock.py`, the backup template, graph export route, five focused test
modules, and the incident fixture. No schema, Parquet contract, provider, model,
or spending policy changes. Existing authority-handoff write-log behavior remains.

### Decisions mid-flight

- Each parked slot owns a cancellable expiry worker. Slot identity under the
  registry lock is the authority to destroy it. Cancellation alone is insufficient.
- Expiry never acquires the process write gate, which a local contender may hold
  while waiting on the parked flock. A stale callback cannot close a reused handle.
- Cold acquisition yields to already-published waiter tokens before competing
  for the flock. Simply releasing and immediately reacquiring can starve pollers.
- Backup/export use `snapshot_read`, which opens physically read-only and never
  appends `write_log`. Connection close precedes sidecar unlock; inode is preserved.
- Retry only the recognized same-process configuration conflict or DuckDB native
  file-lock conflict, within the acquisition deadline. Permission failures and
  unsupported lock operations fail immediately.

### Gate results

Final counts, independent review and CI links are recorded in the PR. Local logs:
`repro.log`, `core-final.log`, `snapshot-callers-red.log`,
`snapshot-callers-green.log`, `reader-handoff-red.log`,
`reader-handoff-green.log`, `combined.log`, `python314-core-backup.log`.

The all-surface Python 3.14 invocation initially stopped at collection because
the shared local 3.14 environment lacks `webauthn`; it did not prove export on
that interpreter. Core/backup run separately there; CI installs declared extras.
Direct mypy reports ten pre-existing diagnostics, identical on the base file.
No baseline was expanded. The repository's declared-bar CI remains authoritative.

### Security and limitations

Hardenx strict reported one unchanged synthetic test-key finding and three
OSV-confirmed vulnerable dependency pins in `uv.lock`: cryptography 49.0.0,
pypdf 6.14.2, yt-dlp 2026.6.9. The scanner's source is `uv.lock`, not an inspected
production environment. Dependency files are unchanged in this repair. These
findings remain open for a dependency/security lane; this is not a repository-wide
security clearance. No secret value is included here.

### Steelman rejected alternative

Disabling warm reuse would stop retention but restore expensive repeated opens.
Increasing backup timeouts would not release an indefinitely parked connection.
Restarting services or bypassing the flock would either hide the defect or violate
single-writer safety. Independent lease expiry and cooperative handoff address
both idle and busy starvation without changing database authority.

### Status and grade

Implementation and local verification are complete pending independent review
and CI. Grade remains below 100 until Linux verification and a real restored
production backup prove the operational outcome. See the PR for the current
check-based score; a unit-test count is not a product-completion score.

### Not proved

No production deployment, backup upload, restore, arXiv run, or notification
webhook repair was performed. Tests do not prove failure-free operation under
all OS schedules. The backup-freshness webhook's HTTP 404 is a separate defect.

### Next sprint can start when

After review and CI, integrate under the existing merge authority, deploy the
coordinator and backup template together, verify a fresh restorable backup and
successful arXiv handoff, then verify backup-freshness alert delivery. Never
remove the stable sidecar file while processes may still use it.

### Local verification checkpoint

At code commit `21e7b8248`, the final combined Python 3.12 run passed **70 tests**.
The Python 3.14 core/backup run passed **63 tests** before the final two
non-contention-error cases were added. The incident fixture passes six checks.
Ruff and diff checks pass. The ten direct mypy diagnostics match the base exactly.
The schema auditor found no single-writer or export-contract regression; its
retry-classification refinement was implemented and covered by red/green tests.

Local repair score: **80/100**, using five equal checks: reproduced failure,
root-cause implementation, actual caller regressions, invariant/error-path audit,
and cross-lineage acceptance plus CI. The first four are satisfied; the fifth is
pending. Production recovery is a separate unverified outcome, not included in
that local score. Full Antiek perfection remains unproven.

### Independent review checkpoint

MiMo V2.5 Pro returned ACCEPT after source review. Its attempted test invocations
used a nonexistent worktree-local venv and are not counted as executed validation.
Its narrative described an earlier snapshot exception catch; the later native-lock
retry was separately audited and proved by the eight reader-handoff cases. The
reviewer's row scores sum to94 although its displayed total says84; neither is
used as a product grade.

Two identified coverage gaps are now tested: exhausting the prior-waiter yield
budget without leaking the local gate or erasing another owner's token, and two
process snapshots serializing on the same inode. The warm/snapshot suite passes
18 tests including these additions. At the prior PR head, declared-bar, write-lock,
tsc, vitest and Pages checks passed; pytest shards/keystone were still running.
Final CI must be checked on the eventual head. Local readiness remains below100;
production restoration is still unverified.
