# Quack in Antiek — Architecture & Utility Spec

**Status:** Draft 1 (2026-05-17)
**Owner:** runtime / substrate
**Pairs with:** `architecture_notes.md` §2.3 (single-writer invariant), `runtime/db_lock.py`, Sprint 10 plan
**Target landing:** DuckDB v2.0 GA (autumn 2026). Beta opt-in available immediately on v1.5.2 via `INSTALL quack FROM core_nightly`.

---

## 0. TL;DR / Verdict

Adopt Quack as Antiek's **write coordinator**, swapping `FlockWriteCoordinator` for `QuackWriteCoordinator` behind the existing `WriteCoordinator` Protocol in `runtime/db_lock.py`. This is a one-line factory change in a future `substrate/init_db.py:get_write_coordinator()` plus a long-running `duckdb` process under launchd. Every existing call site (`connect_write(path, purpose=...)`) keeps working because Quack returns a `DuckDBPyConnection`-shaped handle.

**Adopt:**

1. Quack as the single transport for multi-process writes to `research_graph.duckdb`.
2. Quack as the read transport for the in-browser consume-side (Antiek `apps/reading` Vite app and any DuckDB-WASM surface).
3. Token-based auth, with the token kept in `~/.antiek/quack.token` (file mode 0600), distributed to clients via DuckDB Secrets.
4. `localhost:9494` bind only. No external exposure. If we later expose for remote dev, terminate TLS at nginx; never expose the Quack port directly.
5. The default Antiek wiring stays Flock until: (a) the Quack extension is on the `stable` repository, (b) two-thread concurrent-write scenarios are exercised in tests, and (c) the `write_log` migration is committed. Phase gates are detailed in §8.

**Reject (with reasons):**

1. **Reject** running Quack on top of `iceberg` or `delta` to "future-proof" the storage layer. Antiek is a DuckDB-native graph store; the warehouse-format detour adds two interchange layers (Parquet manifest + commit log) for zero current benefit. If we ever need cross-engine reads, that is a separate decision pinned to DuckLake, not a justification to add an abstraction layer above Quack today.
2. **Reject** Arrow Flight SQL and GizmoSQL as alternatives. Both require maintaining a non-DuckDB serialization (Arrow IPC) on the wire, paying a CommandStatementQuery + DoGet round-trip per query, and double the binary surface. Quack is strictly better for our workload, which is dominated by small inserts (event log, edge writes) and occasional bulk reads (backtest archival, synthesis materialization).
3. **Reject** PostgreSQL + `pg_duckdb` as the multi-writer story. Maintains two database engines, doubles backup surface, and re-introduces wire-format translation costs at every write. We already paid the cost of moving to DuckDB; reversing that to satisfy a multi-writer requirement Quack now solves natively is a regression.
4. **Reject** keeping the flock indefinitely. Flock works today (and the WP-2 facade is well-built), but it serializes every writer end-to-end at ~1 write/process — fine for the daily cron, fatal once the wrestling loop, REST surface, and acquisition adapters all want to write concurrently. Sprint 10's REST + first-LLM-run + 3-adapter pile-on is the inflection point where Flock breaks down.
5. **Reject** read-side migration to Quack in Phase 1. Reads through Quack work but burn a network hop and a serialization round-trip the local-fs read does not. Keep `connect_read()` direct against the file for in-process callers; route Quack only at the cross-process boundary.
6. **Reject** "every write goes through Quack always." We will retain a `local_writer` escape hatch (the existing `FlockWriteCoordinator`) for two scenarios: (a) the migration scripts themselves, which need to run before the Quack server exists; (b) test runs that spin a transient DB.

Everything below justifies these positions and specifies the implementation.

---

## 1. Background and Constraints

### 1.1 What Antiek's writers look like today

The single DuckDB file at `~/.antiek/research_graph.duckdb` is written by the following surfaces (audited 2026-05-17):

| Surface | Path | Cadence | Volume per call |
|---|---|---|---|
| `middleware/archive/archive.py` | synthesis archival | per investigation completion | 1 syntheses row + N substrate manifest rows |
| `processing/extraction/extract.py` | claim/edge extraction | per ingested document | ~10–200 edge rows |
| `acquisition/arxiv/adapter.py` | arXiv ingest | daily cron + on-demand | ~50–200 document + chunk rows |
| `acquisition/books/adapter.py` | book ingest | on-demand (Antiek consume) | 1 document + 10s–100s of chunks |
| `acquisition/urls/adapter.py` | URL ingest | on-demand (Antiek consume) | 1 document + ~10–50 chunks |
| `substrate/graph/ops.py` + `schema.py` | graph CRUD + init | first run + every node/edge upsert | varies |
| `interfaces/research/api/wrestling.py` | wrestling loop note_taker | per distillation request from the browser | 1 chunk + 1 claim node + N edges |
| Future: REST surface | Sprint 10 day 1-2 | per request | varies |

The single-writer invariant (only one process holds DuckDB write at a time) is the constraint Quack is being introduced to relax. The flock coordinator is correct but blocking — when the daily arXiv cron is running, the wrestling loop in the browser cannot save a single chunk for up to 300s.

### 1.2 What `db_lock.py` already commits us to

`runtime/db_lock.py` already declares the target shape:

```python
@runtime_checkable
class WriteCoordinator(Protocol):
    def acquire_write_context(self, purpose: str): ...

@runtime_checkable
class WriteContext(Protocol):
    def execute(self, sql, params=None): ...
    def executemany(self, sql, params_list): ...
    def query(self, sql, params=None): ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

`FlockWriteCoordinator` satisfies these today. The spec below specifies `QuackWriteCoordinator` so it satisfies the same Protocols. Call sites do not change. The `LockedConnection.__getattr__` forwarding pattern means even non-Protocol DuckDB methods (`register`, `from_df`, etc.) keep working when we replace the underlying handle.

### 1.3 What Antiek-specific constraints matter

* **`ANTIEK_PARAM_VERSION` stamping.** Every event-log emit and every archived synthesis carries this stamp. Quack must not change the value or the stamping point — the version is `0.1.0` per `substrate/constants.py:349`, owned by the application layer.
* **Event log on disk is JSONL → Parquet.** The event log is not in DuckDB and is not subject to the write lock. Quack does not touch this surface and should not.
* **The browser consume-side runs DuckDB-WASM.** This is the killer use case for Quack: the in-browser PDF reader at `apps/reading/` can talk Quack natively to the central graph without bouncing through the REST surface for read queries.
* **Antiek's writer counts will scale to ~6–10 parallel processes** (one per acquisition adapter family + 1 REST + 1 wrestling-loop dispatcher + 1 cron + 1 interactive CLI). This sits comfortably inside Quack's measured 8-thread concurrent-insert ceiling. Beyond that DuckDB's own concurrency is the bottleneck — not Quack — and is on the upstream roadmap.

---

## 2. Architecture

### 2.1 Component diagram

```
                          ┌──────────────────────────────────────┐
                          │ Quack Server Process                 │
                          │ (long-running `duckdb` CLI under     │
                          │ launchd: ~/Library/LaunchAgents/     │
                          │   com.antiek.quack.plist)            │
                          │                                      │
                          │  - LOAD quack                        │
                          │  - CALL quack_serve(                 │
                          │      'quack:localhost',              │
                          │      token = <from quack.token>,     │
                          │      bind_port = 9494,               │
                          │      auth_callback = …,              │
                          │      authz_callback = …)             │
                          │                                      │
                          │  Opens research_graph.duckdb in      │
                          │  read-write mode. THIS is the only   │
                          │  process holding the file write      │
                          │  handle.                             │
                          └─────────────────┬────────────────────┘
                                            │
                            HTTP / application/duckdb
                                            │
        ┌───────────────────────────────────┼──────────────────────────────────┐
        │                                   │                                  │
        ▼                                   ▼                                  ▼
 ┌──────────────┐                  ┌────────────────┐                ┌────────────────┐
 │ Cron writers │                  │ REST API       │                │ DuckDB-WASM    │
 │ - arxiv      │                  │ (uvicorn,      │                │ in browser     │
 │ - urls       │                  │  Sprint 10)    │                │ (apps/reading) │
 │ - books      │                  │                │                │                │
 │ - extraction │                  │ wrestling-loop │                │ Read-only      │
 │ - archive    │                  │ dispatch       │                │ ATTACH for     │
 │              │                  │                │                │ live graph     │
 │ ATTACH       │                  │ ATTACH         │                │ queries        │
 │ 'quack:…' AS │                  │ 'quack:…' AS   │                │                │
 │ graph        │                  │ graph          │                │ ATTACH         │
 └──────────────┘                  └────────────────┘                │ 'quack:…' AS   │
                                                                     │ graph          │
                                                                     └────────────────┘
                                            │
                                            ▼
                          ┌──────────────────────────────────────┐
                          │ Read-only fast path (bypass Quack)   │
                          │                                      │
                          │ For in-process Python readers that   │
                          │ already have FS access:              │
                          │   duckdb.connect(path, read_only=    │
                          │   True)                              │
                          │ via runtime.db_lock.connect_read.    │
                          │ Coexists with the writer process     │
                          │ because DuckDB allows multi-reader   │
                          │ + single-writer.                     │
                          └──────────────────────────────────────┘
```

### 2.2 Process placement

* **Quack server.** Single long-running process owned by launchd (`~/Library/LaunchAgents/com.antiek.quack.plist`). Launches at login, restarts on crash, logs to `~/.antiek/logs/quack.{out,err}.log`. Quack server's working directory is `~/.antiek/`. It does not run the REST API; that is a separate uvicorn process.
* **REST API process.** Sprint 10 day 1-2 deliverable. uvicorn workers; each worker `ATTACH 'quack:localhost' AS graph` at startup. Workers are read-write through Quack.
* **Cron writers.** Each cron job opens a Quack connection at startup, runs its batch, exits. Quack handles the connection lifecycle and reuses the underlying DuckDB transaction primitives.
* **Interactive Python (notebooks, scripts).** Two paths:
  * Read-only: use `connect_read()` directly against the file (fast, zero hops, no Quack).
  * Read-write: `ATTACH 'quack:localhost' AS graph`. Document this in a runbook so people stop reaching for `duckdb.connect(path)` and hitting a "file is locked" error against the server.

### 2.3 The coordinator swap

`runtime/db_lock.py` already declares the protocol shape. The Phase-2 implementation adds a new class:

```python
# runtime/db_lock.py — Phase 2 addition (does NOT exist today)

class QuackWriteCoordinator:
    """Quack-backed implementation of WriteCoordinator.

    Drop-in replacement for FlockWriteCoordinator. Selected by
    init_db.get_write_coordinator() based on the ANTIEK_WRITE_BACKEND
    env var (default 'flock' until Phase 4 cutover).
    """

    def __init__(
        self,
        quack_uri: str = "quack:localhost",
        token_path: str = "~/.antiek/quack.token",
        attach_alias: str = "graph",
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ):
        self.quack_uri = quack_uri
        self.token_path = os.path.expanduser(token_path)
        self.attach_alias = attach_alias
        self.timeout_s = timeout_s
        self._token: Optional[str] = None

    def _load_token(self) -> str:
        if self._token is None:
            with open(self.token_path, "r") as f:
                self._token = f.read().strip()
        return self._token

    @contextlib.contextmanager
    def acquire_write_context(self, purpose: str):
        if not purpose:
            raise ValueError(
                "QuackWriteCoordinator.acquire_write_context: "
                "purpose is mandatory."
            )
        con = duckdb.connect(":memory:")
        con.execute(f"LOAD quack")
        con.execute(
            "CREATE OR REPLACE SECRET antiek_quack "
            "(TYPE quack, TOKEN ?)",
            [self._load_token()],
        )
        con.execute(
            f"ATTACH '{self.quack_uri}' AS {self.attach_alias}"
        )
        # purpose is application-level metadata. We record it in
        # write_log via the same path the flock coordinator uses.
        acquired_at = time.monotonic()
        error: Optional[str] = None
        try:
            yield QuackWriteContext(
                con, attach_alias=self.attach_alias, purpose=purpose
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            duration = max(0.0, time.monotonic() - acquired_at)
            try:
                con.execute(f"DETACH {self.attach_alias}")
            except Exception:
                pass
            con.close()
            _log_write_event(
                # Note: write_log itself is in the remote DB now, so
                # the log path goes through Quack too. See §9 for the
                # observability section.
                _quack_db_handle(),
                purpose,
                duration,
                success=(error is None),
                error=error,
            )
```

The factory:

```python
# substrate/init_db.py — DOES NOT EXIST TODAY. Created during the swap.

def get_write_coordinator() -> WriteCoordinator:
    backend = os.environ.get("ANTIEK_WRITE_BACKEND", "flock")
    if backend == "quack":
        return QuackWriteCoordinator()
    if backend == "flock":
        return FlockWriteCoordinator(
            db_path=os.path.expanduser(DUCKDB_PATH)
        )
    raise ValueError(f"Unknown ANTIEK_WRITE_BACKEND: {backend!r}")
```

Call sites stop importing `connect_write` directly and import the factory:

```python
# in middleware/archive/archive.py, processing/extraction/extract.py, etc.
from substrate.init_db import get_write_coordinator

coord = get_write_coordinator()
with coord.acquire_write_context("archive_synthesis") as ctx:
    ctx.execute("INSERT INTO syntheses ...", [...])
```

`connect_write` continues to exist for migration scripts and for the Quack server's own startup (which cannot bootstrap through itself).

### 2.4 What does NOT need to change

* The `LockedConnection.__getattr__` forwarding pattern.
* The `WriteCoordinator` / `WriteContext` Protocols already in place.
* `ANTIEK_PARAM_VERSION` stamping (it is at the event-log emit layer, not the DB layer).
* The schema definitions in `substrate/graph/schema.py`.
* Every CHECK constraint, every NOT NULL, every PRIMARY KEY.
* The Pydantic payload contracts.

This is by design: the Quack swap is supposed to be invisible to application code. The fact that the swap is invisible is the strongest argument that the `db_lock.py` WP-2 work was correctly factored.

---

## 3. Connection Protocol & Secrets

### 3.1 Token generation

At server startup the Quack server generates a 32-byte random token. We override this with a stable token written by an install-time script so client processes can be configured deterministically:

```python
# scripts/install/provision_quack_token.py — DOES NOT EXIST TODAY
import secrets, os
TOKEN_PATH = os.path.expanduser("~/.antiek/quack.token")
if not os.path.exists(TOKEN_PATH):
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(secrets.token_urlsafe(32))
    os.chmod(TOKEN_PATH, 0o600)
```

The server reads `~/.antiek/quack.token` at boot. Clients read the same file when constructing the `QuackWriteCoordinator`. There is exactly one token. Token rotation = stop server, regenerate, restart server.

### 3.2 SQL secret idempotency

Quack accepts the token via DuckDB Secrets:

```sql
CREATE OR REPLACE SECRET antiek_quack (TYPE quack, TOKEN '<value>');
```

`CREATE OR REPLACE` is required because every cron invocation creates a fresh in-memory DuckDB connection and would otherwise hit "secret exists" on a subsequent attach.

### 3.3 Localhost binding

```sql
CALL quack_serve(
    'quack:localhost',
    token = '<token>',
    -- IMPORTANT: 'localhost' bind means the server is unreachable
    -- from anywhere off the loopback interface. This is the default
    -- and we do not override it.
);
```

If we ever want a remote dev case (extremely unlikely; rejected in §0), the path is:
1. nginx terminates TLS, listens on 443, proxies to `localhost:9494`.
2. Quack server still binds `localhost` only.
3. Token stays the same; client config gains a `quack:remote.host:443` URI.

Never bind Quack to `0.0.0.0`.

---

## 4. Surfaces

### 4.1 Write surface

Every write to `research_graph.duckdb` after Phase 4 cutover flows through one of:

| Caller | Backend | Reason |
|---|---|---|
| middleware/archive | Quack | concurrent with other writers |
| processing/extraction | Quack | parallel adapters extract simultaneously |
| acquisition/{arxiv,urls,books} | Quack | adapter family parallelism |
| interfaces/research/api/wrestling.py | Quack | REST request handlers are concurrent |
| substrate/graph/ops.py | Quack | called by all of the above |
| `substrate/graph/schema.py:init_database` | **Flock** | Bootstraps before Quack server can exist. Must serialize against any other writer regardless. |
| `scripts/migrate_v*.py` | **Flock** | Schema migrations need exclusive access; Quack server is stopped during migrations. |
| Test suite | **Flock or in-memory** | Tests run on disposable DBs; no Quack server. |

### 4.2 Read surface

Three classes of reader; each picks its own path:

1. **In-process Python readers** (most of `roles/`, `middleware/`, scripts): use `runtime.db_lock.connect_read(path)`. Direct file access in read-only mode. DuckDB allows this concurrently with the Quack server's write handle. Zero network overhead.
2. **REST API read endpoints**: use `connect_read(path)` in the worker. Same reason. Quack would add a serialization round-trip we do not pay otherwise.
3. **Cross-process readers without filesystem access** (browser DuckDB-WASM, the `apps/reading` Vite app, future remote dev): `ATTACH 'quack:localhost' AS graph` and read from `graph.*`. This is the surface Quack uniquely enables.

This is the explicit rejection of "all reads through Quack." The benchmark numbers in the announcement are excellent (60M rows in 5s), but those benchmarks measure cross-host TCP. Local in-process reads against the file are still strictly faster because they skip the HTTP framing entirely.

### 4.3 Browser surface

The `apps/reading` Vite app (PDF reader for the wrestling loop) currently posts every claim through the REST API. With Quack-WASM available:

```typescript
// apps/reading/src/lib/graph.ts — new
import * as duckdb from "@duckdb/duckdb-wasm";

const db = await duckdb.AsyncDuckDB.create();
const con = await db.connect();
await con.query(`INSTALL quack FROM core_nightly`);
await con.query(`LOAD quack`);
await con.query(
  `CREATE OR REPLACE SECRET antiek_quack
   (TYPE quack, TOKEN '${quackTokenFromConfig}')`
);
await con.query(`ATTACH 'quack:localhost:9494' AS graph`);

// Subsequent live queries against the graph:
const result = await con.query(
  `SELECT * FROM graph.query(
     'SELECT claim_text, confidence
      FROM nodes
      WHERE node_type = ''claim''
        AND investigation_id = ?
      ORDER BY created_at DESC
      LIMIT 50',
     $1
   )`,
  [investigationId]
);
```

The token shipped to the browser is the same `~/.antiek/quack.token` value; this is acceptable because the consume-side runs only on `localhost` and we do not expose Quack publicly. **If the consume-side ever runs on a non-localhost browser, this changes** — we would issue a per-session ephemeral token via the REST API instead and rotate it. That work is out of scope until the deployment story requires it.

The browser surface unlocks the live wrestling loop pattern from the talk: select PDF text → claim materializes from the graph in real time → no REST hop. This is the highest-leverage Quack use case for Antiek's consume-first product positioning.

---

## 5. Auth & Authz

### 5.1 Authentication

Default token compare, no override. The token check Quack does internally is constant-time, which is what we want. We do not need LDAP, OAuth, or anything fancier for a single-user workstation deployment.

If Antiek ever has multi-user identities, the path is to override the auth callback with a SQL macro that looks the token up in an `antiek_users` table. We will not build this until a second user exists.

### 5.2 Authorization

The default Quack authz callback says yes to everything. We override it with one rule:

```sql
-- in the Quack server's startup config
CREATE MACRO antiek_authz(query) AS
  CASE
    -- Block DROP / TRUNCATE from non-migration paths.
    -- Migrations run with the flock coordinator while the Quack
    -- server is stopped, so any DROP arriving over Quack is by
    -- definition not a sanctioned migration.
    WHEN regexp_matches(upper(query), '^\s*(DROP|TRUNCATE)\s')
      THEN false
    -- Block VACUUM (DuckDB-specific reclaim) from clients; only the
    -- server's internal maintenance loop should run this.
    WHEN regexp_matches(upper(query), '^\s*VACUUM\b')
      THEN false
    -- Allow everything else.
    ELSE true
  END;
```

The point is not to build a security model. It is to make accidental destructive operations from a misconfigured client return an explicit "denied" error rather than silently nuking a table. The actual security posture is **"localhost binding plus a 32-byte token"**; the authz callback is a guardrail against operator error, not an attack-mitigation layer.

### 5.3 What we explicitly do not implement

* Row-level security. Antiek is single-user; row-level filters are gold-plating.
* Per-user query logging beyond the existing `write_log` table.
* Token-per-purpose. The flock coordinator's `purpose` parameter is application-level metadata stamped into `write_log`. We do not split it into Quack-side auth tokens.

---

## 6. Lifecycle

### 6.1 Server start/stop

launchd plist at `~/Library/LaunchAgents/com.antiek.quack.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.antiek.quack</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/slimydog/.local/bin/duckdb</string>
    <string>-c</string>
    <string>INSTALL quack FROM core_nightly;
            LOAD quack;
            -- The .read directive sources the server config from
            -- a separate SQL file so token rotation does not require
            -- editing the plist.
            .read /Users/slimydog/.antiek/quack_serve.sql</string>
    <string>/Users/slimydog/.antiek/research_graph.duckdb</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>
    <key>Crashed</key><true/>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/slimydog/.antiek/logs/quack.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/slimydog/.antiek/logs/quack.err.log</string>
  <key>WorkingDirectory</key>
  <string>/Users/slimydog/.antiek</string>
</dict>
</plist>
```

`quack_serve.sql`:

```sql
-- ~/.antiek/quack_serve.sql
-- Reads the token from the sidecar file at server boot.

CREATE TEMP TABLE _config AS
  SELECT read_text('/Users/slimydog/.antiek/quack.token') AS token;

CREATE MACRO antiek_authz(query) AS (
  CASE
    WHEN regexp_matches(upper(query), '^\s*(DROP|TRUNCATE)\s') THEN false
    WHEN regexp_matches(upper(query), '^\s*VACUUM\b') THEN false
    ELSE true
  END
);

CALL quack_serve(
  'quack:localhost',
  token => (SELECT trim(token) FROM _config),
  authz_callback => 'antiek_authz'
);
```

Operations:

* Start: `launchctl load ~/Library/LaunchAgents/com.antiek.quack.plist`
* Stop: `launchctl unload ~/Library/LaunchAgents/com.antiek.quack.plist`
* Status: `launchctl list | grep com.antiek.quack`
* Logs: `tail -f ~/.antiek/logs/quack.*.log`

### 6.2 Migrations

Migrations run with the Quack server stopped. The flow:

1. `launchctl unload com.antiek.quack`
2. Run `scripts/migrate_v*.py` using `FlockWriteCoordinator` directly. Migration acquires the flock; nothing else can write because nothing else holds an open connection.
3. `launchctl load com.antiek.quack`

This is the explicit reason `FlockWriteCoordinator` does not get deleted after the Quack swap. It remains the migration path forever, and it remains the test path forever.

### 6.3 Crash recovery

* Quack server crash: launchd restarts it. The DuckDB file's last-committed state is what survives — same as today, because DuckDB's MVCC + WAL handle this irrespective of Quack.
* Client crash mid-transaction: Quack rolls back the open transaction server-side when the client connection drops. This is a strict improvement over Flock, where a crashed writer would hold the flock until the OS reaped the process (typically near-instant on macOS, but theoretically arbitrary on contended NFS — not relevant here, just noting).
* Token file lost: regenerate, restart server, restart every client.

---

## 7. Concurrent-Write Semantics & Limits

### 7.1 What gets faster

* **Cron + REST overlap.** Today: cron holds flock for 30s during arXiv ingest; every REST write blocks. After Quack: both run concurrently against the server, which dispatches them to DuckDB's MVCC-aware writer. The flock barrier disappears.
* **Wrestling loop responsiveness.** Today: a chunk insert during a running cron waits up to 300s. After Quack: typical latency drops to the few-millisecond range observed in the small-write benchmark.
* **Adapter-family parallelism.** Today: the three acquisition adapters (`arxiv`, `urls`, `books`) serialize when run in the same cron window. After Quack: they run truly in parallel.

### 7.2 What stays the same

* DuckDB's internal write-concurrency model. Quack does not increase the number of writers DuckDB itself can handle internally — the benchmark plateau at 8 threads is a DuckDB engine limit, not a Quack protocol limit. Antiek's concurrent-writer ceiling is ~6–10 processes; we sit under that comfortably.
* The single-file invariant. There is still one `.duckdb` file. There is still one process holding the write handle. Quack does not horizontally shard.
* Schema invariants. CHECK constraints fire on the server side, exactly as they did locally.

### 7.3 What gets worse (and why we accept it)

* **Single-process write latency.** A direct flock-write inside one process is ~50µs to begin a transaction. A Quack-write is ~280µs (the announcement's localhost ping figure) plus a request/response cycle on the order of 1–2ms. For Antiek's workload where each writer batches ~10–200 rows per call, the per-row amortized cost is negligible. For a one-row write the overhead is ~20x — acceptable because we never do hot per-row writes in tight loops.
* **Process count.** One additional always-on process. Costs ~50MB resident, no measurable CPU at idle.
* **A new failure mode.** "Quack server is down" is a new error. Mitigated by launchd's KeepAlive (auto-restart) and by `connect_read()` continuing to work from the file when the server is down. Pure-write callers will fail loudly, which is correct behavior — we do not want silent data loss.

### 7.4 Explicit non-goals

* **Horizontal sharding of `research_graph.duckdb`.** Not needed at our data scale (current largest investigation graph is ~50k edges).
* **Read replicas.** The announcement mentions WAL-replication is on the Quack roadmap. We do not need it. If the graph grows past single-host read capacity (which would be ~100M+ rows) we revisit.
* **Geographic distribution.** Antiek is a single-workstation product. There is no second machine to coordinate with.

---

## 8. Migration Plan

The migration is **substrate-first** and **gated**. Each phase has a hard exit criterion that must be met before the next phase begins. This is the same discipline used for the RL readiness plan; same reason — premature cutover to Quack while the substrate has gaps causes silent corruption that costs more than the speedup is worth.

### Phase 0 — Substrate readiness (today → next 2 days)

Hard prerequisites for any Phase 1 work:

* [ ] **Land the missing `migrate_v7_write_log.py` script.** `runtime/db_lock.py:107` calls `_log_write_event()` which inserts into a `write_log` table. The migration script that creates this table is referenced in the docstring but does not exist. Today every Flock write silently dumps a "write_log insert failed" line to stderr. Fix this independently of Quack.
* [ ] **Create `substrate/init_db.py:get_write_coordinator()`** with the factory shape from §2.3, returning `FlockWriteCoordinator` for now. This is a no-op refactor: all call sites move from `from runtime.db_lock import connect_write` to `from substrate.init_db import get_write_coordinator`, but the behavior is unchanged.
* [ ] **Add `ANTIEK_WRITE_BACKEND` env var honoring** to the factory, with `flock` as the only currently supported value. This pre-wires the switch for Phase 4.
* [ ] **Tests pass** with the factory in place (all `test_*.py` under `tests/` still green).

Exit criterion: the codebase has exactly one path to a writer, and that path is the factory. No `connect_write` import outside the factory + migration scripts.

### Phase 1 — Install Quack server (1 day)

* [ ] `INSTALL quack FROM core_nightly` validated on the workstation.
* [ ] Provision `~/.antiek/quack.token` via the install script.
* [ ] Write `~/.antiek/quack_serve.sql`.
* [ ] Write `~/Library/LaunchAgents/com.antiek.quack.plist`.
* [ ] Server boots and serves a smoke-test query: `duckdb -c "INSTALL quack; LOAD quack; CREATE SECRET (TYPE quack, TOKEN '<token>'); ATTACH 'quack:localhost' AS g; SELECT count(*) FROM g.nodes;"`
* [ ] Server's `research_graph.duckdb` file is the same file the Flock writers are pointed at, **but** Flock writers must be confirmed not to run concurrently with the server during Phase 1 (the single-writer-per-file rule still applies until Phase 4).

Exit criterion: Quack server stays up across two consecutive reboots; smoke-test query passes; no contention with Flock writers because none are running yet.

### Phase 2 — `QuackWriteCoordinator` class lands (1 day)

* [ ] Implement `QuackWriteCoordinator` per §2.3.
* [ ] Add unit tests that mock the Quack server.
* [ ] Add an integration test that runs against a real Quack server on a transient port.
* [ ] Factory accepts `ANTIEK_WRITE_BACKEND=quack` but does **not** make it the default.

Exit criterion: `ANTIEK_WRITE_BACKEND=quack pytest tests/` passes end-to-end with the Quack server running.

### Phase 3 — Dual-run validation (3–5 days)

Operate in dual mode: production keeps Flock; a parallel pipeline run with `ANTIEK_WRITE_BACKEND=quack` exercises the Quack path against a copy of the production DB.

* [ ] Run a full daily-ingest cycle (arxiv + extraction + archive) under Quack.
* [ ] Run the wrestling loop interactively for a full session under Quack.
* [ ] Compare `write_log` from both paths: same row counts, same purposes, same durations within 2x.
* [ ] Compare the resulting DB hashes (excluding `write_log` itself, which records different timing). Must be byte-identical at the data layer.
* [ ] Run all benchmarks under Quack and confirm latency is within the expected envelope (§7.3).

Exit criterion: two consecutive dual-run days show byte-identical data tables and no Quack-side errors.

### Phase 4 — Cutover (1 day)

* [ ] Set `ANTIEK_WRITE_BACKEND=quack` in the launch environment for all writer processes.
* [ ] Stop Flock writers from being able to run concurrently with the Quack server (they would corrupt). Document the migration-only exception in the runbook.
* [ ] Run for one week with monitoring.

Exit criterion: zero `write_log` rows show Quack-side errors over the first week.

### Phase 5 — Browser surface (after Phase 4 stabilizes)

* [ ] Add the `@duckdb/duckdb-wasm` + Quack-WASM dependency to `apps/reading/`.
* [ ] Implement the live-graph-query pattern from §4.3.
* [ ] Deprecate the REST endpoints that exist purely as a graph-read proxy.

Exit criterion: the wrestling loop's claim-list refreshes from `graph.*` directly, with no REST round-trip.

### Phase 6 — Cleanup (after Phase 5 stabilizes)

* [ ] Remove the `connect_write` direct imports from any callers we missed.
* [ ] Remove dead code paths from `db_lock.py` if any are unreachable in the Quack world. The `FlockWriteCoordinator` itself stays — it remains the migration + test path.
* [ ] Bump `ANTIEK_PARAM_VERSION` because the persistence path changed. (Arguable; the data on disk is identical, but the substrate stamp is the audit trail we have for "what code wrote this row.")

---

## 9. Observability

### 9.1 `write_log` table

Today's `write_log` table records: `purpose, duration_s, success, error, ts`. With Quack:

* The table itself lives in `research_graph.duckdb`. Every writer continues to write to it.
* `_log_write_event` no longer re-locks a sidecar flock — it goes through Quack like every other write.
* This introduces a recursion risk: the log write itself produces a log write. We block this with the existing `_WRITE_LOG_PURPOSE` sentinel. The Quack version keeps the sentinel and asserts the recursion is bounded at 1.

### 9.2 Server-side telemetry

Add two columns to `write_log` (or a sibling `quack_log` table) capturing Quack-specific data:

* `client_attach_alias` — the ATTACH alias the caller used (`"graph"` by default, but tests can vary it).
* `transport` — `"flock"` or `"quack"` so we can read the audit trail across the cutover.

The `transport` column is the single most important diagnostic for Phase 3 dual-run validation.

### 9.3 Quack server logs

`~/.antiek/logs/quack.{out,err}.log` is the operator's first-stop. Surface in the runbook:

* `Connection from 127.0.0.1:NNNN authenticated` (normal traffic)
* `Authentication failed` (token drift between server and a client — usually a stale env var)
* `Authorization denied: <query>` (a client tried to DROP or TRUNCATE — investigate which one)
* Server panics. Should never happen; if they do, file an upstream bug with the query that triggered it.

### 9.4 The dashboard tile

Add to the existing `runtime/monitoring/` surface: a tile that reads from `write_log` and shows:

* writes/min over the last hour, split by purpose
* p50 / p95 / p99 duration per purpose
* error rate (rows where `success=false`)

This tile becomes the primary signal during Phase 3 dual-run validation. It is also the most likely place to first notice Quack regressions.

---

## 10. Failure Modes & Mitigations

| Failure mode | Symptom | Mitigation |
|---|---|---|
| Quack server not running | Every write raises connection refused | launchd KeepAlive auto-restarts. Pre-flight check in `get_write_coordinator()` could probe the port; rejected because it adds latency to every coordinator construction. The right place for the probe is a dedicated `runtime/health/quack.py` checker in the dashboard. |
| Token mismatch | Auth failure on every client | Single-file token + `CREATE OR REPLACE SECRET` makes drift unlikely. If it happens: regenerate token, restart server, restart all clients. |
| DuckDB file corruption | Server fails to open the file | The Quack server is the single writer (post-Phase 4), so concurrent-writer corruption is impossible. Other corruption modes (disk failure, OOM during commit) are unchanged from today. Recovery is from the same backups we use today. |
| Network glitch on localhost | Spurious disconnects mid-transaction | Practically never happens on macOS loopback. Quack's reconnect is automatic; the transaction rolls back server-side. The caller sees an exception and the retry logic in `connect_write_retrying` semantics applies if the caller uses it. We will need a `QuackCoordinatorTimeout` (separate from `WriteCoordinatorTimeout`) for clean error classification. |
| Quack extension regression in core_nightly | A nightly bump breaks something | We pin to a known-good build in the launchd plist (`INSTALL quack FROM core_nightly VERSION '<sha>'`) once the Quack project supports pinning. Until then, we lock to v1.5.2 + the current Quack build and revisit on every DuckDB upgrade. Treat any Quack extension upgrade as a Phase-3-style dual-run validation. |
| Test suite tries to talk to Quack | Tests fail in CI / offline | Tests run with `ANTIEK_WRITE_BACKEND=flock` (default) against in-memory or temp DBs. Quack is a runtime-only dependency, not a test-time dependency. The `QuackWriteCoordinator` integration tests are explicitly opt-in (marked `@pytest.mark.requires_quack`). |
| Browser token leak via DevTools | Anyone with file access sees the token | We accept this. Antiek is single-user; the token lives in a 0600 file already. If multi-user comes, see §5.1. |

---

## 11. Testing Strategy

### 11.1 Unit tests

`test_db_lock.py` already covers `FlockWriteCoordinator`. Add a parallel `test_quack_coordinator.py` that:

* Stubs `duckdb.connect` to return a fake handle.
* Verifies `LOAD quack` and `CREATE OR REPLACE SECRET` and `ATTACH` are called in order with the expected args.
* Verifies the `purpose` round-trips into `_log_write_event`.
* Verifies the `DETACH` happens in `finally`.
* Verifies the error path captures the exception type and stamps it into `write_log`.

### 11.2 Integration tests

`test_quack_integration.py` (gated by `@pytest.mark.requires_quack`):

* Spins up a Quack server on an ephemeral port.
* Provisions a temporary token.
* Writes 100 rows in parallel from 4 worker threads.
* Reads them back through both Quack and direct file access. Both must agree.
* Confirms `write_log` accumulates 4 rows with `transport='quack'`.

CI runs the unit tests by default. Integration tests run nightly on the workstation only.

### 11.3 Dual-run shadow tests

During Phase 3:

* `scripts/shadow/compare_write_paths.py` runs an ingest cycle twice on cloned DBs (once each backend) and diffs the result.
* Checked into `scripts/shadow/` because it is a permanent diagnostic, not a one-shot.

### 11.4 What we explicitly do not test

* Quack's own correctness. That is upstream's job.
* Network partitions on loopback. Not a real failure mode.
* Auth callback overrides beyond the one authz macro we ship.

---

## 12. Antiek-Specific Utility Surfaces

This is the "why bother" section. Quack is not adopted for its own sake; it unblocks specific Antiek capabilities that the flock cannot.

### 12.1 The wrestling loop's live latency

The talk's demo is exactly Antiek's wrestling loop: user selects PDF text, agent emits structured claims, claims stream into the notes panel. Today this is a REST round-trip plus a `connect_read` plus a `connect_write` (flock-blocked) plus an event-log emit. The flock can sit on a wrestling-loop call for 300 seconds during a parallel cron run. After Quack: the chunk insert lands in 2–5 ms regardless of what else is writing. **This is the single largest UX improvement Quack delivers for Antiek.**

### 12.2 Acquisition-adapter parallelism

Sprint 10 ships three adapters (`arxiv`, `urls`, `books`) that today serialize against each other on the flock. Acquisition is inherently I/O-bound (HTTP fetches, PDF parsing); the writes are small. After Quack the adapters write in parallel and the Sprint-10 throughput target becomes achievable instead of aspirational. **This is the single largest throughput improvement.**

### 12.3 Backtest DB closure (Sprint 10 day 4-5)

The backtest closure lands `syntheses`, `synthesis_substrate_manifest`, `outcomes`, and `chunk_tier_overrides` tables. These are written by the archive middleware *during* normal investigation completion, which today contends with whatever ingest is running. Post-Quack, archival and ingest do not block each other, and the backtest pipeline can run as a continuous accumulator instead of a nightly batch. **This is what makes the backtest a closed loop instead of a daily snapshot.**

### 12.4 Cross-tool concurrent inspection

The talk explicitly calls out the "DBeaver + CLI + UI" pattern. For Antiek this is "Jupyter notebook + the wrestling loop + a cron." After Quack all three coexist. Today, opening a Jupyter notebook with a write-mode connection silently blocks every other writer. Post-Quack, the notebook uses `ATTACH 'quack:localhost'` and everyone gets their own session.

### 12.5 The consume-side knows the graph

Antiek's consume-first design — the PDF reader is the front door — has a long-standing seam: the reader and the graph live on different sides of the REST API. Quack-WASM dissolves the seam. The reader queries the graph directly, the wrestling loop's claims appear live, and the REST API can shrink to "things that genuinely require a server-side LLM call." **This is the architectural simplification that justifies the entire spec.**

---

## 13. Open Questions & Deferred Decisions

These are not blockers for Phase 0–4 but should be revisited at Phase 5.

* **Do we use Quack for the event log?** The event log is JSONL → Parquet, not DuckDB-backed. Quack does not naturally fit. Likely no. Revisit if event-log queries become a hot path that wants SQL.
* **Pinning the Quack extension version.** Pin once upstream supports `VERSION '<sha>'` syntax. Until then, treat every DuckDB upgrade as a Phase-3 dual-run.
* **Replacing `connect_write_retrying` semantics.** The 60s-retry-3x pattern was designed for flock timeouts. Under Quack, transient failures look different (TCP-level rather than lock-level). We may need a `QuackReconnect` helper, or we may find Quack's built-in reconnect is enough. Decide during Phase 3.
* **Token rotation cadence.** None today. Add a quarterly rotation if the deployment story expands beyond single-user workstation.
* **DuckLake interaction.** Antiek is not on DuckLake. If it ever migrates (extremely unlikely; the graph is a poor fit for warehouse-format storage), Quack-as-catalog becomes interesting. Out of scope for this spec.

---

## 14. Appendix A — Substrate Gaps Surfaced by This Audit

Independent of the Quack swap, this audit surfaced one gap to close in Phase 0:

* `runtime/db_lock.py:107` calls into a `write_log` table that no migration creates. The migration script was named in the comment (`migrate_v7_write_log.py`) but never landed. Every Flock write today fails its log insert silently. Fix: write the migration. This is a one-page job. **Do this before Phase 1.**

The `_log_write_event` function's "best-effort, stderr-and-continue" design correctly prevents this gap from breaking the main pipeline, which is why nothing has caught fire. It does mean the `write_log` observability layer is effectively non-functional today.

## 15. Appendix B — Why Not Defer Quack to DuckDB v2.0 GA?

The Quack extension on core_nightly is labeled beta. The temptation is to wait until v2.0 GA (autumn 2026) and skip the dual-run discipline.

We reject the wait because:

1. Sprint 10's REST + 3-adapter pile-on is happening **now**. Every week without Quack is a week the wrestling loop's live-latency UX is degraded and the acquisition adapters serialize against each other.
2. The `WriteCoordinator` Protocol is already in place. The cost of swapping the implementation is bounded.
3. Beta-stability risk is exactly what Phase 3 dual-run validates against. If the beta is unstable, we find out in dual-run rather than in production.
4. v2.0 GA is autumn 2026; that is six months of Antiek runtime improvements we would forfeit.

The right cadence is: install Quack in Phase 1 today, cutover in Phase 4 once dual-run is clean, pin to whatever Quack version we end up on, and re-validate at v2.0 GA. This matches the way the substrate migration was sequenced and is consistent with the gated phasing the rest of the Antiek roadmap uses.
