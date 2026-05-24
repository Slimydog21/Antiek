# Antiek Heresies

This file is the canonical registry of *recurrent invariant violations* —
wrong ideas that take root in agent-written code and keep coming back
across sessions, even after correction. The framing is Steve Yegge's, from
his December 2025 interview: agent prompts and LLM-judges are unreliable
enforcers; mechanical CI guards are not.

Every heresy in this file has either:

- a **mechanical detector** in `tools/heresy_detectors/` that runs at
  pre-commit time and refuses commits that introduce the violation, or
- a **manual-only** tag with a sharp prompt-warning phrasing that gets
  pulled into agent system prompts.

This file is read by agent system prompts (kept short on purpose — under
200 lines — so the signal isn't diluted). Future heresies get appended
with the next free ID; IDs are stable and never reused.

## Activation

The detectors are wired through `.githooks/pre-commit`. Activate per-clone
with:

```
git config core.hooksPath .githooks
```

(or `./scripts/install_hooks.sh` once that lands from
`are/wave-1-substrate-additive`). Without activation the registry is
documentation only.

Operator override: `ANTIEK_HERESY_SKIP=1 git commit ...` bypasses the
pre-commit hook for a single commit. The skip is printed to stderr and is
expected to be audited periodically.

## H-001 — Single-writer to `syntheses` is non-negotiable

The `syntheses` table is the substrate-of-record for completed
investigations. Writes go through one code path; every other writer is a
heresy. Multi-writer violations break archive-side invariants (timestamp
ordering, ID monotonicity, attribution chain) in ways that are extremely
hard to diagnose downstream.

**Sanctioned writer:** `middleware/archive/archive.py` (the
`archive_synthesis` path). Test fixtures and `scripts/exercise_substrate.py`
seed the table for development purposes and are whitelisted by the
detector.

**Detector:** `tools/heresy_detectors/h001_single_writer_syntheses.py`
(regex; INSERT/UPDATE/UPSERT/COPY INTO targeting `syntheses` outside the
whitelist is blocked).

**Recurrence trace:** Researchmaxx pre-substrate (the `orchestrate.py`-only
rule pre-dates the Antiek codebase; see `project_researchmaxx` memory).
Antiek-side traces accumulate in agent-session history; one rule, many
attempted violations.

**Carve-out (require this on a noqa):** if you genuinely need to write to
the table from a new path, the right answer is to add the call site to
`middleware/archive/archive.py` and route through `archive_synthesis`. A
noqa is appropriate only when introducing a one-off migration script that
runs once and is then deleted; the noqa reason must say so.

**Prompt-warning phrasing for system prompts:**
> `syntheses` is single-writer. Only `middleware/archive/archive.py` writes
> to it. If you want to insert/update a row, find the existing helper in
> archive.py — do not write SQL elsewhere.

## H-002 — DuckDB writes go through `connect_write`, never raw `duckdb.connect`

`runtime/db_lock.py` provides `connect_write(db_path, purpose=...)` which
acquires the advisory flock and forwards via `LockedConnection`. Raw
`duckdb.connect(path)` for writes bypasses the lock and re-introduces the
multi-writer corruption that prompted db_lock's existence (writer overlap
between the daily ingest cron, the weekly monitor cron, and on-demand
workers).

Read-only access is fine via `connect_read(db_path)` or
`duckdb.connect(path, read_only=True)`.

**Detector:** `tools/heresy_detectors/h002_missing_db_lock.py` (AST;
flags `duckdb.connect(...)` calls without `read_only=True` and not inside
`runtime/db_lock.py`, `substrate/event_log/migrations/`, or `tests/`).
The `tests/` whitelist was set in the 2026-05-24 calibration sweep — 30
legitimate test-fixture cases vs zero production-code cases. Tests
legitimately open `tmp_path` DBs with no other process touching them; the
cross-process flock buys nothing there.

**Recurrence trace:** db_lock.py module docstring spells out that future
agents will try to "introduce a parallel WriteCoordinator class above this
one" — that's the heresy's typical shape.

**Carve-out (require this on a noqa):** in-memory databases
(`duckdb.connect(":memory:")`) need no lock; test fixtures that create
isolated `tmp_path` DBs may legitimately not use db_lock if no other process
will touch the file. Note the case in the noqa reason.

**Prompt-warning phrasing for system prompts:**
> DuckDB writes use `connect_write` from `runtime/db_lock.py`. Never call
> `duckdb.connect(path)` for writes directly. Reads can use
> `connect_read` or pass `read_only=True`.

## H-003 — Multiple write handles to the same DuckDB file in one module

The fake-Quack-DB pattern: a module opens two write handles to the same
file (different variable names, both forwarded operations). Both go
through `connect_write` so the lock is acquired, but in-process, they are
two distinct connections — DuckDB will serialize them but the calling
code starts treating them as separate stores, which is the substrate
equivalent of Yegge's Gas Town "two databases the agents kept treating as
one." The bug surfaces as silent data divergence months later when one
handle's transactions don't see the other's commits.

**Detector:** `tools/heresy_detectors/h003_fake_quack_db.py` (regex;
flags files with ≥2 `connect_write(<same-path-literal>, ...)` or
`duckdb.connect(<same-path-literal>, ...)` calls).

**Recurrence trace:** Yegge transcript, polecat heresy in Gas Town
(generalized).

**Carve-out (require this on a noqa):** initialization scripts that
open the file, run a schema check, close it, then re-open it once
ready may legitimately have two opens. Note that the noqa reason
must include "sequential, not parallel."

**Prompt-warning phrasing for system prompts:**
> One write handle per DuckDB file per module. If you need a second
> connection, that's a sign you should pass the existing one through.

## H-004 — Unobserved spawn (WARN-ONLY at Wave 1)

Yegge: "sub-agents have the problem of being opaque." Antiek's
substrate-correct path for any long-running spawned worker is to
register it with the worker registry so the operator can see it
mid-flight. At Wave 1 the registry does not yet exist (it lands in a
future `feature/yegge-spr-04-worker-identity` sprint); this detector is
warn-only until then, then flips to blocking.

**Detector:** `tools/heresy_detectors/h004_unobservable_spawn.py`
(regex; flags `subprocess.Popen`, `asyncio.create_task`,
`threading.Thread`, `multiprocessing.Process` not followed by a registry
call). At Wave 1, prints warnings to stderr but exits 0.

**Carve-out (require this on a noqa):** subprocess calls that complete
in well under 100ms (measured) don't benefit from registry overhead.
The noqa reason must include `ephemeral, <100ms (measured)`.

**Prompt-warning phrasing for system prompts:**
> Long-running spawns become first-class workers via the registry.
> Sub-second helpers are exempt. If you can't tell which yours is,
> default to first-class.
