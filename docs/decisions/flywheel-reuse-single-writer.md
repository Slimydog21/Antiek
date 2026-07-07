# Flywheel knowledge-reuse via the single-writer connection

**Status:** PROPOSED — design record + executable sprint. Author: Opus 4.8
executor (/infinite), 2026-07-03. Grounded in the #178 review + an empirical
spike (below).

## The verified gap

The compounding knowledge-reuse **flywheel is OFF** in the cascade launch path.
Research investigations do not currently reuse prior knowledge units — the
"perfect knowledge graph / thought partner" compounding loop is unshipped, for a
sound but temporary reason.

- **#140** wired reuse via `make_substrate("brute_force", _db(), …)`. Each
  substrate `.open(db_path)` calls `connect_read(db_path)` =
  `duckdb.connect(path, read_only=True)`. But the research funnel already holds a
  `connect_write` (`read_only=False`) on the **same file** in the **same
  process**, so DuckDB raises
  `ConnectionException: Can't open a connection to same database file with a
  different configuration`. This broke **every** cascade launch (6
  `test_cascade_api` failures).
- **#178 / #190** correctly reverted the wire — it violated the DuckDB
  single-writer invariant (`runtime/db_lock.py`, CLAUDE.md invariant #1), and the
  deleted test was a false-confidence test (it monkeypatched `_db` to an isolated
  tmp graph, so it never exercised the write connection). See the #178 review.
- **The reuse machinery survives** on the runner side: `host_local.py` accepts a
  `retrieval_substrate` and fires exactly one `knowledge.reused` event when one is
  injected ("reuse is purely additive"). Critically, the substrate classes
  **already separate connection from construction** —
  `BruteForceSubstrate.__init__(self, con, *, model)` and
  `DuckDbVssSubstrate.__init__(self, con, *, model, vss_active)` take a **`con`**;
  only their `.open(db_path)` factory opens the conflicting fresh `connect_read`.
- Both wire attempts (#140 and `fix/flywheel-reuse-substrate-wire`) ended in a
  revert. **The real single-writer read path is unstaged** — nobody has it.

## Root cause (precise)

Not "reuse is impossible under single-writer." The defect is narrower: the
injection path opened a **second connection with a different `read_only`
configuration** to a file already held by the writer. DuckDB forbids two
connections with different configs to one file in one process — but it fully
supports **multiple logical read handles on one connection** via `.cursor()`.

## The fix — construct the reuse substrate from the funnel's own connection

Build the reuse `RetrievalSubstrate` from the funnel's existing **write
connection via `.cursor()`**, not from `.open(db_path)`:

```python
# at the cascade launch site, where the funnel's write `con` is in scope:
substrate = DuckDbVssSubstrate(con.cursor(), model=model, vss_active=…)   # NOT .open(db_path)
# inject `substrate` as host_local's retrieval_substrate — reuse turns ON.
```

`con.cursor()` shares the writer's DuckDB instance and configuration, so there is
**no second connection** — the single-writer invariant is preserved (one
instance; the reuse read is a logical handle on it). The read is **live**, not a
stale snapshot.

### Empirical spike (M1 — done in this record, reproducible)

```
writer holds connect_write on the file
A  connect_read(read_only=True) while writer open  -> RAISES ConnectionException  (the bug)
B  w.cursor() read                                 -> [('reuse-me',)]  shares instance, no 2nd connection
C  cursor sees a write made AFTER cursor creation  -> count = 2        live, not a snapshot
```

So the mechanism is verified. The remaining work is wiring + gating + regression
proof in the real cascade path — one focused sprint.

## Milestones (one sprint; fleet-executable)

- **M1 — connection-sharing proven.** ✅ Done here (A/B/C above). Lock it as a
  unit test: `w.cursor()` reads a graph the writer holds; a fresh
  `connect_read` on the same open file raises.
- **M2 — construction-from-connection path.** Add a small, typed way to build a
  substrate from an injected connection (e.g. `RetrievalSubstrate.from_con(con,
  kind, *, model)` or a `make_substrate(..., con=…)` overload) that constructs
  `Substrate(con.cursor(), …)` and **never** calls `connect_read`. The `__init__`
  contracts already accept `con`, so this is additive, not an adapter rewrite.
- **M3 — wire it at the cascade launch site.** Replace the reverted
  `make_substrate("…", _db(), …)` injection with the M2 path fed by the funnel's
  in-scope write connection; inject the result as `host_local`'s
  `retrieval_substrate`. Nothing on the runner side changes.
- **M4 — red-proof regression (the done-bar).** A test that a real cascade launch
  with reuse ON (a) does **not** raise `ConnectionException`, (b) fires exactly
  **one** `knowledge.reused` event, (c) keeps all `test_cascade_api` green (the 6
  that #140 broke), and (d) asserts the process opens **one** DuckDB write
  connection (no 2nd connection). This test must fail on the #140 approach and
  pass on the cursor approach — that is what makes the fix hard to vary.
- **M5 — §9.0 reuse gate.** Reuse retrieval must honor the
  servable/`personal_reading`/attribution gates (do **not** surface non-servable
  or personal-reading knowledge across investigations). Route reuse reads through
  the existing retrieval gate; assert via `test_flywheel_reuse_gate`.
- **M6 — VSS caveat.** `DuckDbVssSubstrate.open` has a copy-to-read fallback for
  the VSS extension (retrieval_substrate.py ~L357). Confirm the VSS extension
  loads on a cursor of the write connection; if not, fall back to `brute_force`
  on the shared cursor cleanly (never to a 2nd connection). Measure reuse-read
  latency against the funnel write to confirm no contention regression.

## Alternatives considered (rejected)

- **Snapshot/copy read** (reuse from a copied DB file — the existing
  `copy_path` VSS pattern). Safe but **stale** (misses in-flight knowledge) and
  pays a full-DB copy per launch. Rejected for a *live compounding* loop; the
  point of the flywheel is reusing knowledge as it accrues.
- **A second read-only connection/process.** Violates single-writer and is
  **proven to raise** (spike A). Rejected.
- **Keep reuse OFF (status quo).** Forgoes the core compounding capability that
  distinguishes "a research tool" from "a thought partner that gets smarter."
  Acceptable only as the honest interim; this record exists to end it.

## Reconsider-if

- The `db_lock.py` note flags an autumn-2026 swap of `connect_write`'s body to "a
  Quack client." If connection/instance semantics change, re-verify the
  cursor-sharing assumption (M1's unit test is the guard).
- If M6 measures real reuse-read contention against write latency, revisit a
  bounded read-replica instead of a live cursor.

## Invariant proof (why this is safe)

Single-writer preserved: exactly **one** `connect_write` connection/instance
exists; the reuse read is a `.cursor()` on it — a logical handle, not a second
connection. The empirical B/C rows demonstrate correctness and liveness under a
held write connection. `--workers 1` and the `db_lock` flock are untouched.

## Sizing / execution

~1 focused sprint. Fleet-executable: a workhorse (grok/codex) builds M2–M6
against this record; heterogeneous verifier-critic adversarially checks M4's
red-proof (does the test actually fail on the #140 approach?) and M5's gate.
Registry lane: `inf-flywheel-reuse-single-writer`.
