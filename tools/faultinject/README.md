# `tools/faultinject` — deterministic fault-injection harness

A precision instrument for the nygard-resilience sprints. Each injector targets
**one named seam** and produces **one named fault** deterministically. It is a
test aid, not a chaos monkey — nothing here runs unless a test explicitly arms
it.

## The three guarantees

1. **Inert by default.** `import tools.faultinject` installs no monkeypatch,
   holds no lock, and registers nothing. A fault exists *only* inside an armed
   `with` block. The default `pytest` run (`testpaths = ["tests",
   "compounding/benchmark/tests"]` — this package is outside both) and the live
   `antiek.service` are byte-identical whether or not this package is present.
2. **Fidelity.** Each injector raises the *real* error the production fault
   would raise, at the *real* seam — so a test proves the real handling path,
   not a synthetic stand-in.
3. **Determinism.** No randomness. `fail_on_call=N` fires from the Nth call
   onward (see below). Same arm → same fault, every run.

## Seam-to-injection map

| Injector | Real seam (read, never modified) | Fault raised | Injection point |
|---|---|---|---|
| `readonly_fs(target_path)` | `acquisition/papers/*` + `substrate/graph/retrieval_substrate.py` write sites | `OSError(errno.EROFS)` | scoped monkeypatch of `builtins.open`/`io.open` (write modes), `os.replace`, `os.rename`, `os.open` (write flags) — **for `target_path` only** |
| `locked_db(db_path)` | `runtime/db_lock.py` (`connect_write` flock) | `runtime.db_lock.WriteLockTimeout` | a real `fcntl.flock(LOCK_EX)` on `<db_path>.write.lock` (path via `runtime.db_lock._lock_path_for`) |
| `provider_fault(kind, provider=...)` | `substrate/dispatch/router.py` (`get_provider` → `provider.call`) | `substrate.dispatch.base.ProviderError` (503 / timeout) | replace the registered provider instance's `.call` for the block |

## Usage

```python
from tools import faultinject

# Read-only FS at one path:
with faultinject.readonly_fs(cache_path):
    ...  # a write to cache_path raises OSError(errno.EROFS)

# Real DB-lock contention:
with faultinject.locked_db(db_path):
    connect_write(db_path, timeout_s=0.5)  # raises WriteLockTimeout

# Provider 503 (or "timeout") on an already-registered provider:
with faultinject.provider_fault(kind="503", provider="deepseek"):
    dispatch(...)  # the router walks its fallback chain

# Generic form:
with faultinject.arm("readonly_fs", target_path=cache_path):
    ...
```

## `fail_on_call` (determinism knob)

- `fail_on_call=None` (default) → **every** matching call faults.
- `fail_on_call=N` (N ≥ 1) → calls `1 .. N-1` pass through; call `N` and every
  call after it faults. Monotonic — once tripped, stays tripped. This is what a
  real degraded resource does, and it keeps SPR-07's repeated-fault loop
  well-defined (a fault that self-healed after one fire would make an
  N-iteration leak test ambiguous).

`fail_on_call` applies to `readonly_fs` and `provider_fault` (both gate a
per-call decision). `locked_db` is a **state fault** — the lock is held for the
whole block — so it rejects `fail_on_call` with a `ValueError` rather than
silently ignoring it.

## Teardown

Every injector restores its seam in a `finally`, so an exception inside the
`with` body never leaks a monkeypatch or a held lock past the block. The
`test_*_teardown_on_raise` cases prove this for each injector.

## Concurrency & re-entrancy

- `_CallGate` (the `fail_on_call` counter) is thread-safe: an armed seam hit by
  concurrent worker threads still trips on exactly the Nth eligible call.
- `readonly_fs` patches process-global write primitives, so **only one may be
  armed at a time process-wide** — a nested/concurrent second arm raises
  `RuntimeError` rather than corrupting the shared restore.
- `provider_fault` allows one fault **per provider**; a second arm on the *same*
  provider raises `RuntimeError` (different providers are independent).
- These guards fail loud on purpose: a silent restore-corruption is worse than a
  clear precondition error. Arming across *different* seams
  (`readonly_fs` + `locked_db` + `provider_fault`) concurrently is fully
  supported.

## What this deliberately does NOT do

- No global `chmod` — the RO-FS fault is a scoped monkeypatch, so a crash cannot
  leave the real tree read-only.
- No dispatch routing change and no new provider (§16) — `provider_fault` only
  makes an *already-registered* provider's call raise.
- No wiring into `conftest.py`, the default test run, or any prod path.
