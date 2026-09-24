# Operator-gated actions, 2026-09-24

The operator requested execution of the six decisions in `operator-instructions.txt`.
The user subsequently clarified: "Preserve and verify the existing gates" for
items 3–6. The production change in this run is the explicit v10 account-memory schema
migration. It does not enable multi-user accounts, change owner namespaces, or
activate any paid or publication path.

## Requirement and evidence map

| Attachment item | Decision and result | Evidence |
|---|---|---|
| 1. `migrate_v10_account_memory` | Applied to `/home/antiek/.antiek/antiek.duckdb` at 09:00:05–09:00:25 UTC. Before: all three memory flags false. After: all true. Second run no-op. | `production-result.json`, `post-migration-services-and-public-health.txt` |
| 1. Fresh verified backup | Ran the deployed backup service; restored and verified its export before upload, downloaded the uploaded object, checked SHA-256, restored it again, then rehearsed v10. | `backup-marker.json`, `rehearsal-result.json`, `restore-rehearsal-v2.log` |
| 1. Preserve production data | Took an exact checkpointed live-file snapshot while holding the writer lock. Rehearsed that exact copy before live execution. Compared every original row and column of all 78 tables using two-way `EXCEPT ALL` before releasing the maintenance lock. | `apply_v10.py`, `production-result.json` |
| 2. DuckLake Stage 1 to Stage 2 | No production moves. Deployed state is the single operator database, without a personal-graph directory or catalog. Recorded a no-move decision with Stage 1, trigger, recovery and approval prerequisites. | `ducklake-plan.json`, `live-gates.json` |
| 3. Backfills/remaps/sweeps | No target set or approved row mapping was supplied. Preserved production refusal in IP-holder backfill, CC0 remap and personal-reading reclassification. No production backfill ran. | Source-pinned CLI guard inspection; `gate-tests.txt`, `additional-gate-tests.txt` |
| 4. Disbursement | G2/G3 remain required. Stripe provider is unset, so it retains the mock default. No payout ran. | `live-gates.json`; `substrate/speak/gate_status.py` on the pinned build; cost-consent tests |
| 5. Public publishing/export | No artifact or destination was specified or acknowledged. Nothing was publicly published or exported. Speak public publishing remains unset and denied by default. Private disaster-recovery backup is the existing configured backup operation. | `live-gates.json`; `tests/test_speak_publish.py`; `public-export-gate-tests.txt` for explicit multimedia distribution acknowledgement |
| 6. Paid/external execution | No new credential, budget or execution authorization was granted. Remote execution remains disabled; multimedia authorization remains required. No paid model, TTS or multimedia request ran. | `live-gates.json`; execution, narration, visual authorization and remote fallback tests |

Items 3–6 preserve the explicit gates in the attachment. Their presence in a list
is not a supplied payee, publisher grant, artifact, provider credential or spend
limit. Additional concrete actions require those missing inputs.

The multimedia public-export review rejects approval without explicit distribution
acknowledgement, and the publish handler refuses an unacknowledged request. Those
controls were also exercised by `tests/test_multimedia_live_worker.py`.

## Environment and commands

Product checkout: `/Users/slimydog/Antiek/worktrees/gated-actions-20260924`.
Local branch: `ops/gated-actions-20260924`.
Deployed and rehearsed source: `874345539e9e2f75d9f85f7f2da54a2bf08e9877`.
Production Python: `/opt/antiek/.venv/bin/python`.
Production service: one uvicorn worker on `127.0.0.1:8001`.
The operator graph path was read from the running service configuration.
No product source was changed, merged or deployed. Exact callable signatures and
local versions are recorded in `contracts-and-environment.txt`; production versions
and the completed maintenance unit are in `maintenance-journal.txt`.

Local verification commands, all exit 0:

```
.venv/bin/python -m pytest tests/test_graph_account_memory_migration.py tests/test_ducklake.py -q
# 20 passed; preflight-tests.txt
.venv/bin/python -m pytest -q tests/test_backfill_cc0_remap.py tests/test_reclassify_personal_reading.py tests/test_cost_consent_no_disbursement.py tests/test_speak_publish.py tests/test_multimedia_execution_authorization.py tests/test_remote_exec_fallback.py
# 92 passed; gate-tests.txt
.venv/bin/python -m pytest -q tests/test_ip_holder_resolver_ingest.py tests/test_multimedia_narration_authorization.py tests/test_multimedia_visual_authorization.py
# 35 passed; additional-gate-tests.txt
```

Production maintenance ran under the transient systemd unit
`antiek-v10-maintenance-20260924.service`. `apply_v10.py` pins the deployed SHA,
requires a successful restored-backup rehearsal, verifies all known graph-writing
services are stopped, acquires `runtime.db_lock.connect_write`, checkpoints the
database, takes the exact rollback snapshot, proves migration on its clone, then
applies the deployed migration. The same locked session compares production data
and verifies idempotency. Its wrapper always restarts the API. An exception after
live mutation restores the exact snapshot; that recovery branch was not needed.

The first restored-copy comparison correctly detected two new `write_log` rows.
The revised comparison proves that every old audit row remains and admits exactly
two successful `migrate_v10_account_memory` audit entries. It does not exclude the
whole audit table. Production comparison occurs inside the locked session before
its close adds the operator-maintenance audit entry.

## Maintenance and recovery

The existing backup runner first waited 45 seconds for the writer lock, then stopped
the API for its retry. The lock actually belonged to arXiv sync PID 1207967, started
at 04:19:59 UTC. A normal systemd stop released it. The sync source uses idempotent
upserts and advances its high-water mark only after a complete harvest. The API
restarted after the snapshot. ArXiv sync was resumed after migration verification;
the previously inactive continuous-research service was left inactive.

This exposed a limitation in the deployed backup's maintenance coordination: its
fallback stops the API but not a separate ingest writer. Future manual maintenance
must identify and coordinate every writer before taking the API down. This run
made no persistent service or timer configuration change.

The remote private directory `/var/lib/antiek-ops-v10-20260924` retains the downloaded
verified backup, restored and rehearsed copies, and `production-before.duckdb`.
The exact pre-migration snapshot is checkpointed and should be used for a targeted
rollback only under a stopped-writer maintenance window. Restoring it later would
also remove writes made since 09:00 UTC; do not replace the active database casually.
Production data and backup archives were not downloaded to the laptop.

## Not proved

Schema readiness is not proof of owner isolation or complete account-memory UI
behavior. The independent owner-namespace work remains separate. This does not
close counsel/publisher gates or qualify paid providers. Stage 2 has no actual
catalog move manifest because Stage 1 is not deployed; its implementation also
needs the preservation and interruption controls named in `ducklake-plan.json`.
The row comparison proves the completed migration, not hypothetical recovery from
every possible hardware failure. The physical rollback branch was not invoked.
