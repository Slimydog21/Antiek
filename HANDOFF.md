# HANDOFF — write-lock-on-the-event-loop lint

Branch `lane/writelint-20260919`, commit `3d8caf1ef`.

## Where the brief was wrong

**The lint belongs in `tools/lints/` (plural), not `tools/lint/` (singular).**
The brief named `tools/lint/` and pointed at `tools/lint/rate_governor_check.py`
as the AST precedent, but it also required a baseline, and the baseline
machinery is a different directory with a different contract. `tools/lint/` holds
standalone scanners with no baseline support; `tools/lints/` holds the baselined
lints — `baseline.py`, `cli_with_baseline.py` with its `LINT_REGISTRY`, and
`baselines/*.json`. Putting a baselined lint in `tools/lint/` would have meant
reimplementing the baseline, so the lint went where the baseline lives and picked
up the sibling convention (frozen `Violation` + `scan_file` / `scan_paths` /
`main` with the 0/1/2 exit contract). `rate_governor_check.py` was still read as
the AST precedent, and `no_seam_call_under_write_lock.py` — same write-lock
subject, already registered — was the closer structural model.

**The count is 48, not ~30, and it spans ten files, not one.** The brief's
numbers for `app.py` are literally correct and I reproduced them:

```
$ grep -c 'connect_write(' interfaces/research/api/app.py
32
$ grep -c 'to_thread' interfaces/research/api/app.py
2
```

But the reading was wrong in two directions. The two `to_thread` mentions in
`app.py` have nothing to do with `connect_write` — one is a comment on line 1980,
the other is `await asyncio.to_thread(_probe_flywheel)` on line 1991, a startup
flywheel probe. So `app.py` is not "32 against 2"; it is 32 against 0. All 32
`connect_write` call sites sit directly in async route bodies, none is hopped.
And the problem is wider than `app.py`: the AST scan finds 48 sites across ten
files, including three in `substrate/multimedia/knowledge_registration.py` and
five in `interfaces/research/api/federation.py`.

The brief's claim that a `connect_write` inside a nested sync `def` within an
`async def` is not blocking is **conditionally** true, not unconditionally — it
only holds if that closure is actually dispatched to a thread. I measured the
tree rather than assuming: exactly three nested sync defs hold a `connect_write`,
and all three reach a hop (`ad_routes.py::_accrue_sync` and
`books.py::convert_and_publish` are passed straight to a hop;
`ad_routes.py::_decide` reaches `run_in_executor` through the `_sync` wrapper).
So treating the nested-def case as clean costs nothing today, but it is a real
gap, and it is pinned by a test rather than left implicit.

## What the baseline says — the remaining work

**48 entries.** This is the enumeration the brief asked for.

| Path | Entries |
|---|---|
| `interfaces/research/api/app.py` | 32 |
| `interfaces/research/api/federation.py` | 5 |
| `substrate/multimedia/knowledge_registration.py` | 3 |
| `interfaces/research/api/wrestling.py` | 2 |
| `interfaces/research/api/account_memory_routes.py` | 1 |
| `interfaces/research/api/feedback_routes.py` | 1 |
| `interfaces/research/api/settings_compute_capacity.py` | 1 |
| `interfaces/research/api/settings_tiers.py` | 1 |
| `interfaces/research/api/upload_routes.py` | 1 |
| `substrate/research_bridge/ingest_file.py` | 1 |

Two of these are worth a second look before the bulk migration, because they are
not just slow, they are wrong in kind.

`interfaces/research/api/feedback_routes.py:193` takes the **write** lock at the
default 300s timeout inside `async def get_feedback`, a GET handler, purely to
read a thread:

```python
async def get_feedback(...)-> Response:
    _require_enabled()
    with connect_write(_db_path(), purpose="feedback/read") as con:
        thread = FeedbackStore().get_thread(...)
```

A read path holding the single-writer lock serializes itself against every
writer on the box for no reason. That one probably wants `connect_read`, not a
thread hop.

`substrate/multimedia/knowledge_registration.py:251` is worse: it takes the lock
bare at the default timeout and then **awaits** inside the held lock
(`await run_document_pass(...)` at line 255). That yields the event loop while
holding the flock, so a second request can enter the same handler and deadlock
against the writer gate. Moving it to `to_thread` is necessary but not
sufficient; the await has to come out of the locked section too, which is the
invariant `no_seam_call_under_write_lock` already enforces elsewhere.

## What changed

`tools/lints/no_blocking_write_in_async.py` is the lint. It flags a call to
`connect_write`, `connect_write_retrying` or `acquire_write_context` whose
nearest enclosing function scope is an `async def`. "Nearest enclosing scope" is
the whole design: `app.py` is one `create_app()` factory wrapping every route, so
the enclosing chain is sync then async, and a rule keyed on "any enclosing async"
or "any enclosing sync" gets every one of the 32 backwards. Aliases are resolved
from the module's own AST, so `from runtime.db_lock import connect_write as _cw`
and `_GRAPH_WRITER = connect_write` — both shapes the tree already writes — bind
names the rule still recognizes.

`tools/lints/baselines/no_blocking_write_in_async.json` grandfathers the 48.
`tools/lints/cli_with_baseline.py` gains the registry entry
`blocking_write_in_async`. `tools/lints/README.md` gains the baseline's section
and the table above. `tests/test_no_blocking_write_in_async.py` is 21 tests, all
against fixture source in `tmp_path`, never the real tree.
`.github/workflows/write_lock_async_floor.yml` runs enforce with `--check-stale`.

I did not fix any call site.

### False positives, and how each was handled

A nested sync `def` or `lambda` inside the `async def` is **not** flagged. It
interposes a scope, and it is the sanctioned fix shape, so flagging it would red
every correct migration. The cost is a false negative on a closure that is called
rather than dispatched; measured cost today is zero, and
`test_known_false_negative_sync_closure_that_never_reaches_a_hop` pins it.

Being inside a thread hop's arguments is **not** an exemption. Python evaluates
a call's arguments on the calling thread, so
`await asyncio.to_thread(apply, connect_write(db))` takes the flock on the event
loop and only then hands the open connection to a worker. The only shape that
really defers the acquisition is a callable, and the nearest-scope rule already
lets a nested `def` or `lambda` through, so an argument-position exemption could
only ever bless the eager form. An earlier draft carried one; no test could tell
whether it was there, which is how it surfaced.

A `@contextmanager` helper wrapping `connect_write` and called from async code
**is** a violation and this lint cannot see it — the `connect_write` lives in a
module-level sync generator, and only a call graph connects it to the async
caller. Stated in the module docstring as limitation 3 and pinned by
`test_known_false_negative_contextmanager_helper`. Closing it needs whole-program
analysis, which is a different tool.

Test files are skipped, matching `SKIPPED_PARTS` in the sibling lints.

The rule everywhere: where the AST cannot decide, prefer the false negative. A
lint that reds honest code gets switched off, and then it protects nothing.

### Why a new workflow rather than a step in `resilience_floor.yml`

The seam-under-write-lock lint is its natural sibling and lives there, but this
gate has to fire on PRs touching `interfaces/**` and `substrate/**` — that is
where the async handlers are — and widening `resilience_floor.yml`'s path filter
would change which PRs every other gate in that file runs on. The new workflow is
install-free (the lint is stdlib: `ast`, `dataclasses`, `pathlib`), and it does
not re-run the bite tests because `ci.yml` already runs the whole `tests/` tree
in its four shards.

## Commands, with real output

Done-bar 1 — clean with the baseline:

```
$ python -m tools.lints.cli_with_baseline enforce blocking_write_in_async \
    --paths acquisition compounding interfaces middleware orchestration \
            processing roles runtime services substrate tools \
    --baseline-file tools/lints/baselines/no_blocking_write_in_async.json \
    --check-stale
EXIT=0
```

Standalone mode, no baseline, showing the raw debt:

```
$ python -m tools.lints.no_blocking_write_in_async acquisition compounding \
    interfaces middleware orchestration processing roles runtime services \
    substrate tools
...
48 violation(s)
EXIT=1
```

Done-bar 2 — removing a baseline entry reds. I dropped the
`feedback_routes.py` entry, ran enforce, then restored the file:

```
dropped 1 entry: [{'col': 9, 'kind': 'blocking-write-in-async:connect_write',
                   'line': 193, 'path': 'interfaces/research/api/feedback_routes.py'}]
--- enforce after dropping one entry ---

1 NEW violation(s) since baseline (no_blocking_write_in_async.json)
interfaces/research/api/feedback_routes.py:193:9: NEW blocking-write-in-async:connect_write
EXIT=1
--- restored; enforce again ---
EXIT=0
```

Done-bar 3 — a new violating call site reds. I appended a blocking `async def`
to `settings_compute_capacity.py`, ran enforce, then reverted:

```
--- enforce with a NEW violating call site ---

1 NEW violation(s) since baseline (no_blocking_write_in_async.json)
interfaces/research/api/settings_compute_capacity.py:161:9: NEW blocking-write-in-async:connect_write
EXIT=1
--- standalone mode on the same file ---

2 violation(s)
interfaces/research/api/settings_compute_capacity.py:123:13: connect_write() on the event loop in async def put_compute_capacity — ...
interfaces/research/api/settings_compute_capacity.py:161:9: connect_write() on the event loop in async def _temporary_probe_for_lint_proof — ...
EXIT=1
--- reverted; enforce again ---
EXIT=0
(empty diff above = cleanly reverted)
```

The inverse proof, which matters as much: the **sanctioned fix shape** added to
the same real file stays green. A sync `def _sync()` holding the
`connect_write(..., timeout_s=2.0)` block, awaited through `asyncio.to_thread`:

```
--- enforce with the SANCTIONED FIX shape added (must be green) ---
EXIT=0
(empty = reverted)
```

Done-bar 4 — the bite tests, fixture-only:

```
$ python -m pytest tests/test_no_blocking_write_in_async.py -q
...............                                                          [100%]
15 passed in 0.51s
```

No regression in the lint family (the `cli_with_baseline` registry changed):

```
$ python -m pytest tests/test_no_blocking_write_in_async.py \
    tests/test_lints_cli_with_baseline.py tests/test_lints_baseline.py \
    tests/test_lints_no_raise.py tests/test_lints_unannotated_bypass.py \
    tests/test_no_seam_call_under_write_lock.py -q
91 passed in 0.82s
```

The gates `substrate_floor.yml` already applies to `tools/lints/`:

```
$ ruff check tools/lints/ tests/test_no_blocking_write_in_async.py
All checks passed!

$ mypy --strict --explicit-package-bases --namespace-packages \
    tools/lints/no_blocking_write_in_async.py tools/lints/cli_with_baseline.py \
    tools/lints/baseline.py
Success: no issues found in 3 source files
```

Workflow YAML parses:

```
name: write-lock-async-floor
jobs: ['write-lock-async-gate']
scope: acquisition compounding interfaces middleware orchestration processing roles runtime services substrate tools
steps: ['actions/checkout@v7', 'Set up Python 3.12', 'Enforce — no blocking DuckDB write on the event loop']
```

Python throughout is `/Users/slimydog/Antiek/platform/.venv/bin/python` (3.12),
run from the worktree root. No `timeout`, no arXiv selection, no full suite, no
npm, no Docker.

## What I did not do, and why

**I did not fix any of the 48 call sites.** The brief ruled it out and it is the
right call: each one needs the locked section reshaped into a closure, a timeout
chosen, and a 503 path added, and `knowledge_registration.py` additionally needs
an `await` lifted out of a held lock. That is a behaviour change per route with
its own test surface.

**I did not run CI.** The workflow is unexecuted. It is mechanically the same
shape as the `enforce` steps already in `resilience_floor.yml`, and the command
inside it is the exact one proved above, but `actions/checkout@v7` /
`actions/setup-python@v7` were copied from the sibling workflows rather than
verified against the runner.

**I did not add snippet keying to the baseline.** The substrate lints do not use
it and `cli_with_baseline` does not stamp it, so entries are keyed on
`(path, line, col, kind)`. Consequence: an insertion above a baselined site
shifts its line and the entry reports as one NEW violation plus one stale entry
until the baseline is recaptured. `declared_bar.py` has the `enrich` path that
solves this; wiring it here is a separate change.

**I did not touch `tools/lint/` (singular).** Nothing there needed changing once
the lint went to `tools/lints/`.

## What I am unsure about

The `SCOPE_DIRS` list is a judgment call. I picked the directories that contain
`async def` today plus the obvious neighbours. Capture and enforce must use the
identical list or enforce judges a different file set than the one grandfathered;
the workflow's `SCOPE_DIRS` is the single copy, and the README says so, but
nothing mechanically enforces that the committed baseline was captured with it.
A drift check would be a worthwhile follow-up.

`acquire_write_context` and `connect_write_retrying` are in the watch set for
future-proofing. Neither appears in an async body today, so that half of the rule
is covered only by the fixture test, not by the real tree.

I have not confirmed whether `interfaces/research/api/feedback_routes.py:193`
uses `connect_write` for a read deliberately — there may be an
ensure-table-on-first-read reason I did not find. It reads as a mistake, but I
did not change it and I did not chase the history.
