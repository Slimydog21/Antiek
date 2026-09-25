# Closed backup restore verification

**Decision, 2026-09-25.** A backup may claim DuckDB graph fidelity only after a closed archive restores to the same catalog and row multiset as an independently authenticated observation of the source snapshot. The verifier returns a bounded report for a later protected guard decision; it does not grant that decision itself.

## Failure the decision addresses

The existing backup script verifies an EXPORT directory before creating its tar archive. That directory and its manifest are writable by the application identity. Counts and a partial catalog cannot detect a same-count row change, and the CI-locked DuckDB 1.5.3 EXPORT/IMPORT drops all four self-referential foreign keys in the current Antiek schema. Comma normalization makes the exported SQL importable but does not restore those constraints. A manifest packed into the same archive cannot independently testify to the source snapshot.

## Contract

`observe_snapshot` inventories supported persistent DuckDB objects and hashes each table using `antiek-row-multiset-sha256-v1`. Source and restored observations use the same function. Canonical source bytes must come from a protected worker that proves source inode, writer exclusion, DuckDB transaction, and EXPORT generation. Parsing a source report validates its shape, not its origin.

`verify_closed_archive` must run **after** the archive is closed, inside a dedicated non-root Linux sandbox. It admits gzip/tar bytes with bounded extraction, requires the expected single-export layout, imports into a disposable DuckDB, observes that restore, and compares exact catalog, table set, counts, row digests, and canonical observation hash. Unknown DuckDB versions, types or catalog features refuse; absent objects cannot be ignored to make a fixture pass. Cleanup failure overrides apparent success. The archive-internal manifest is never source authority. The caller freezes one archive inode and binds its length and SHA-256 to upload and R2 read-back before issuing a guard receipt.

The report covers the DuckDB graph. Packaged `research_events/` and `knowledge_skills/` are hash-bound as archive bytes but lack protected source inventories; their live-source fidelity needs a separate proof or an explicitly narrower receipt. No report from this module is itself a production receipt.

## Rejected shortcuts

- Trusting the application-written manifest or pre-tar EXPORT check would let the same mutable tree make and verify its own claim.
- Running tar admission or `IMPORT DATABASE` as root would parse attacker-influenced bytes and execute SQL with root privileges. DuckDB [treats untrusted SQL as code](https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview); its settings are defense in depth, not a replacement for an OS sandbox.
- `COPY FROM DATABASE` is [documented](https://duckdb.org/docs/current/sql/statements/copy) to copy a database, but a local DuckDB 1.5.4 parent/child self-FK fixture raised a constraint error. `ALTER TABLE ... ADD CONSTRAINT` is [unsupported](https://duckdb.org/docs/current/sql/statements/alter_table). Neither is a demonstrated repair for the four missing FKs.
- A native DuckDB-file backup may preserve the schema after checkpoint and full quiescence, but copying only the main file while committed data remains in the WAL can lose data. In a local 53-table fixture on DuckDB 1.5.4, a checkpointed, closed, offline copy matched the 1,164-object source observation; an uncheckpointed main-file copy had zero catalog objects. A native-file format would need a separately versioned archive contract, a reader-and-writer quiescence proof, checkpoint/WAL proof, and its own restore verifier. The current Parquet verifier must not silently accept it.

## Release gates

The current real-schema negative test deliberately refuses the four lost FKs. Keep that refusal until a corrected pinned DuckDB export or separately reviewed backup format preserves them and the full-schema restore test turns positive. Before production, also prove protected source identity and authenticated observation from the same transaction as EXPORT; target-Linux sandbox denial of host-file and network access plus CPU, memory, disk and time limits; immutable archive inode through verification, upload and R2 read-back; token/job/generation-bound protected guard evidence; and receipt projection compatibility. Backup-script integration belongs to #3244; worker installation belongs to #3247. The disaster-recovery runbook must use the verified route before claiming full recovery.

The local component passes 92 relevant tests on the CI-locked DuckDB 1.5.3, including a normal GNU-tar success fixture, adversarial archive/report/content cases, and the real-schema refusal. The exact-head CI run must pass before that evidence can be called complete. This is **55/100 integration readiness**: component behavior and review evidence exist, while source authority, sandbox, guard binding, R2 proof, and the real-schema positive restore remain open. Production release evidence is **0/100**.
