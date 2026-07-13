# Marketplace production durability

Date: 2026-07-13

Status: accepted for implementation; deployment remains operator-gated

## Decision

The uvicorn module entry point composes `SQLiteHostStore` only when
`ANTIEK_MARKETPLACE_HOST_DB_PATH` is explicitly configured. Production's
systemd unit sets it to `${ANTIEK_STATE_DIR}/marketplace-host.sqlite3`.
Malformed explicit configuration or an invalid database aborts startup. An
absent or empty variable preserves the in-memory local-development default.

Nightly backup uses `sqlite3.Connection.backup` against a read-only source
connection. The snapshot is checked through the same read-only schema validator
used by `SQLiteHostStore`, checked with `PRAGMA quick_check`, and retained only
if both checks pass. Disaster recovery stages and validates the snapshot while
the service is stopped, preserves the previous main file and sidecars through a
hard-linked rollback directory, then atomically renames the replacement and
restores mode `0600` before restart. Historical archives without marketplace
state explicitly produce a fresh empty generation instead of retaining a hybrid.

## Why

The durable store introduced by ANT-MDL-SPR-01 was injectable but the production
launcher still called the in-memory default. Restart survival was therefore a
tested library capability, not an operational guarantee. The nightly archive
also omitted that new state. Activation, backup, and restore must share one
path contract or the platform can claim durability while losing hosted books,
account memberships, and receipt evidence.

## Rejected alternatives

- Make every `create_app()` call durable by default. Rejected because tests and
  offline development would write ambient operator state. Reconsider only if
  application construction receives a required, isolated state directory.
- Fall back to memory when an explicit SQLite path fails. Rejected because a
  production misconfiguration would look healthy while silently discarding
  writes. No reconsideration without an independently visible read-only mode.
- Copy the live `.sqlite3` file with `cp` or `rsync`. Rejected because the copy
  is not a SQLite consistency boundary. Reconsider only for stopped-service
  backups with an operationally enforced stop assertion.
- Stop the API for every nightly backup. Rejected because SQLite's online
  backup API provides a transactionally consistent snapshot without planned
  downtime. Reconsider if measured backup contention harms foreground writes.

## Reversal conditions

Move this state to the platform's primary database when marketplace data needs
cross-store transactions, multiple API workers, or tenant-scale query patterns.
Until then, a single local SQLite file matches the one-process production
topology and keeps recovery inspectable.
