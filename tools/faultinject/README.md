# Fault Injectors

`tools.faultinject` is opt-in. Importing it installs no monkeypatches, opens no
locks, changes no environment, and performs no network I/O. A fault is active
only inside `with arm(injector):`; teardown runs in `finally`.

## Seam Map

- Read-only FS: path-scoped writes through `open(..., "w"/"a"/"x"/"+")` and
  `os.replace(...)` raise `OSError(errno.EROFS)`. The 2026-05-17 class was a
  filesystem write failure surfacing as evidence absence. `acquisition/papers/core.py`
  was read for this sprint; it uses `httpx` and has no filesystem write
  primitive. The closest current retriever/index write seam is
  `substrate/graph/retrieval_substrate.py`, where the VSS path copies the graph
  DB into a temp index and writes a derived HNSW index.
- Locked DB: `runtime/db_lock.py:connect_write` acquires an exclusive `flock`
  on `<db>.write.lock` before opening DuckDB. The injector holds that real
  sidecar lock on a disposable DB path so `connect_write(..., timeout_s=...)`
  observes authentic contention.
- Provider fault: `substrate/dispatch/router.py:dispatch` calls a registered
  provider's `.call(...)` inside the tier fallback loop. The injector wraps only
  that provider instance's `.call`, forcing either a retryable 503 or timeout.
  Routing and provider registration are unchanged.

## Usage

```python
from tools.faultinject import arm, readonly_fs

with arm(readonly_fs(tmp_path / "cache")):
    write_cache_file()
```

```python
from runtime.db_lock import connect_write
from tools.faultinject import arm, locked_db

with arm(locked_db(tmp_path / "graph.duckdb")):
    connect_write(str(tmp_path / "graph.duckdb"), timeout_s=0.01, purpose="test")
```

```python
from tools.faultinject import arm, provider_fault

with arm(provider_fault(provider="primary", kind="503")):
    dispatch("prompt", "role", investigation_id="i", config=config)
```

All injectors accept deterministic controls where relevant. `fail_on_call=N`
means calls before `N` pass through and call `N` raises the named fault.
