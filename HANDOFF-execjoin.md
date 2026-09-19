# Lane: execjoin — making the ExecutionBackend seam execute something

Status: **DONE**, with two places where I did the opposite of what the brief said.
Both are called out below rather than buried.

## What was wrong before

`interfaces/research/api/cascade_routes.py` built an `ExecutionBackend` behind
`ANTIEK_EXEC_BACKEND`, logged its name with the phrase `(runner remains %s)`, and
dropped it. `CascadeSession` got the `HostLocalRunner` either way. Confirmed by
grep: outside its own package and tests, the only reference to `exec_backend`
anywhere in the tree was that one dead call site.

## The join, and what I rejected

**Chosen: join at the BrowseLoop, not at the ResearchRunner.**
`_research_loop_factory()` now returns a *contained gather loop* when the flag is
set. It provisions one workspace per investigation, writes the request in with
`put_file`, runs one `exec` per pass, exports `out/gather.jsonl` with `get_file`,
and destroys the workspace in a `finally`. The runner is untouched.

**Rejected 1 — the adapter `interface.py` defers** ("a `RemoteExecProvider`
implemented over an `ExecutionBackend`"). It is not merely unbuilt, it is
unbuildable over this interface:

- `RemoteExecProvider.run` must *stream* `RemoteStepEvent`s and `steer` must reach
  into a running loop. `ExecutionBackend` is deliberately "`exec` + files, no
  streaming, no steering, no event channel". An adapter would have to fake both,
  and a silently no-op `steer` is a capability regression wearing a "same shape"
  label.
- It needs an in-sandbox leaf program. `runtime/remote_exec/daytona.py:111` names
  one (`python -m antiek.remote.research_leaf`); `find . -name 'research_leaf*'`
  returns nothing, and `DaytonaProvider.run` is still a `NotImplementedError`
  whose body says "Wire the SDK exec/stream call here". The ratified remote seam
  never built that program either, so this lane would have been building it from
  scratch — with the corpus inside the box, which is the thing we must not do.
- Swapping the runner drops `retrieval_substrate`, `seal_on_complete=False` and
  the `_receipted_hard_ceiling_loop` wiring at the launch site.

**Rejected 2 — reassigning `runner` inside the flag guard.** This is where I
contradict the brief. The brief said the old test "pins the current non-behaviour
as the contract" because it asserts `runner` is never reassigned inside the
guard, and implied the join should reassign it. It should not. `HostLocalRunner`
*is* the single-writer discipline: it owns `on_emit=funnel.submit`, the budget,
the event log and the seal. Swapping it is exactly how a second writer would get
in. The right change is to keep the runner fixed and change the loop it drives —
which is also already the house idiom at that site, where
`_receipted_hard_ceiling_loop(inner: BrowseLoop) -> BrowseLoop` decorates the loop
two lines above.

So the old assertion's *conclusion* survives; its *reasoning* did not. The
rewritten test now pins it for the real reason and says so inline.

## Single-writer preservation (done-bar 4)

Structural, not disciplinary:

- The workspace receives bytes (`put_file` of a request JSON) and returns bytes
  (`ExecResult.stdout` + `get_file` of its `out/` artifact). No graph handle, no
  db path, no ingest lock, no credential crosses the boundary.
  `_LocalWorkspace._build_env` gives the child an allowlisted `PATH`/`LANG`/`HOME`
  and nothing else; `_DockerWorkspace` passes only `profile.env`, which this loop
  leaves empty.
- Those bytes become ordinary `StepEvent`s. `HostLocalRunner._push` forwards
  `note`/`question` to `on_emit`, which the cascade binds to `funnel.submit`.
  Results return through the **existing** funnel, still serialized behind
  `db_lock`.
- Writer count is unchanged: one, on the host.

Held two ways in `TestSingleWriterPreserved`: a grep-proof that the join module's
source contains none of `connect_write` / `ingest_lock` / `log_event` / `duckdb`
(the discipline `runtime/remote_exec/funnel.py` uses), and a run through the real
`HostLocalRunner` asserting every promotable result arrives at `on_emit` and
nowhere else.

## Second thing the brief did not ask for: `local` cannot serve this loop

The loop declares `net_policy=DENY_ALL` — the gather program needs no network.
`LocalProcessBackend` has no egress filter, so it raises `NetPolicyUnsupported` at
`create()` (invariant I4) rather than pretending. That is stronger than done-bar 5
asked for: done-bar 5 only wanted a missing *docker daemon* to raise, but an
operator can also set `ANTIEK_EXEC_BACKEND=local` deliberately and believe agent
code is contained. Now it cannot run at all. There is also a WARNING logged at
selection time saying `local` is a seam exerciser, not a sandbox.

Consequence to be honest about: with today's backends, the flag-set path is only
*runnable* under docker. On this machine it raises, which is the correct outcome
and the one I could actually exercise.

## Files

- `runtime/research_runner/contained_gather.py` (new) — `make_contained_gather_loop`
  plus `GATHER_PROGRAM`, the stdlib-only script that runs in the workspace.
- `interfaces/research/api/cascade_routes.py` — flag branch moved into
  `_research_loop_factory`; the dead log block deleted from `launch`.
- `tests/test_cascade_exec_backend_wiring.py` — rewritten.

## The test that encoded a bug as the specification

The old file parsed `launch`'s AST and asserted three things about the *shape* of
a branch whose entire body was a `build_execution_backend` call and a
`logger.info`. All three passed because the seam did nothing, and would have
stayed green forever while no agent code ever ran outside the API process. An AST
assertion over a branch with no effects cannot distinguish "wired" from "logged".
That reasoning is now the module docstring of the rewritten file, at the top,
where the next reader hits it first. This is the second time on this project a
test has pinned a bug as the contract; it is worth treating the pattern — a test
that asserts structure where it should assert effects — as the smell rather than
either instance.

Two tests were dropped from that file, both duplicates of existing coverage, not
weakenings: `test_flag_set_factory_returns_local_backend` is
`tests/test_exec_backend_factory.py::test_env_var_local`, and
`test_forwarded_runner_kwargs_do_not_raise` is that file's
`test_seal_on_complete_accepted` / `test_both_forwarded`. The call site no longer
forwards those kwargs (it no longer builds a runner-shaped thing), but the factory
still accepts them and the factory's own tests still cover it.

## Commands, with real output

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest \
    tests/test_cascade_exec_backend_wiring.py tests/test_exec_backend_factory.py \
    tests/test_exec_backend_interface.py tests/test_exec_backend_conformance.py -q
....................................................................     [100%]
68 passed in 1.21s
```
(baseline before this lane, same selection: `58 passed in 1.84s`)

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest \
    tests/test_exec_backend_local.py tests/test_exec_backend_docker.py \
    tests/test_research_loop_factory_selector.py tests/test_cascade_api.py \
    tests/test_cascade_session.py tests/test_cascade_reuse_single_writer.py \
    tests/test_exa_gather_loop.py -q
SKIPPED [1] tests/test_exec_backend_docker.py:469: docker CLI or daemon unavailable
107 passed, 1 skipped, 1 warning in 24.56s
```

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m ruff check \
    runtime/research_runner/contained_gather.py \
    tests/test_cascade_exec_backend_wiring.py \
    interfaces/research/api/cascade_routes.py
All checks passed!
```

```
$ python -m mypy runtime/research_runner/contained_gather.py --ignore-missing-imports \
    | grep '^runtime/research_runner/contained_gather.py'
(no output — the repo-wide run is 223 pre-existing errors in 53 other files)
```

Docker state, so the done-bar-5 path is not taken on trust:

```
$ docker version --format '{{.Server.Version}}'
docker_exit=1
failed to connect to the docker API at unix:///Users/slimydog/.colima/default/docker.sock;
check if the path is correct and if the daemon is running: dial unix
/Users/slimydog/.colima/default/docker.sock: connect: no such file or directory
```

The CLI is installed at `/opt/homebrew/bin/docker`; colima is not running. So
`DockerBackend.probe()` raises `BackendUnavailable`, and
`test_docker_absent_raises_out_of_the_loop_factory` drives that through the real
loop factory. I did not start docker.

## What I did NOT do, and why

- **No in-sandbox agent.** `GATHER_PROGRAM` reads the host's request, appends a
  record to `out/gather.jsonl`, and prints a summary. It performs no retrieval.
  That is the same honesty class as `make_contract_gather_stub`, whose own
  docstring calls it "an honest production gather placeholder — not real
  research". This lane ships the join; the payload it carries is still a
  placeholder and both the module docstring and this file say so. The one
  non-placeholder fact it reports is the effective `uid` it ran as — 65534 under
  docker, the service user under local — which is the thing an operator actually
  needs to see to know whether containment happened.
- **Did not containerise the Exa loop.** It retrieves over the network and
  promotes through `ingest_url` in-process; moving it into a workspace would make
  the workspace a second writer. `ANTIEK_EXEC_BACKEND` and `ANTIEK_DRW_GATHER=exa`
  together now raise instead of one silently winning.
- **Did not add `contextlib.aclosing` to `HostLocalRunner`.** See the risk below.
- Did not run the whole suite, the arXiv selection, `npm install`, or vitest.

## What I am unsure of

1. **Workspace cleanup on the abandonment paths.** The loop's `finally` runs
   inline on the normal and raising paths. But `HostLocalRunner._run` raises
   `BudgetExceeded` *out of its own `async for` body* without `aclosing()` the
   generator, so on a budget halt (and on cancel) cleanup runs only when asyncio
   finalizes the abandoned async generator. `destroy()` is idempotent and the
   asyncgen finalizer hook does fire, so this is best-effort-but-real rather than
   broken — but it is not deterministic, and under `DockerBackend` a missed
   `destroy()` leaks a container, not just a temp dir. The fix is two lines in
   `runtime/research_runner/host_local.py:340`:

   ```python
   async with contextlib.aclosing(self._loop_fn(ctx)) as gen:
       async for ev in gen:
   ```

   I left it alone because it changes shared runner behaviour for every loop and
   sits outside this lane's blast radius. It should be someone's next small PR,
   and it wants its own negative test (halt a leaf mid-loop, assert `destroy`
   was recorded before the leaf went terminal).

2. **`python:3.12-alpine` is unverified here.** `DockerBackend`'s default image
   is `alpine:latest`, which ships no interpreter, so `python3 gather.py` there
   would return exit 127 forever. The loop therefore declares
   `DEFAULT_GATHER_IMAGE = "python:3.12-alpine"`. With no daemon I could not pull
   it, so the first real docker run will be the first test of that image name, of
   the `--read-only` + tmpfs `/workspace` write path for `out/gather.jsonl`, and
   of whether the provision timeout covers a cold image pull.

3. **One workspace per investigation, one backend per launch.** `build_execution_backend()`
   runs once per launch (so `probe()` runs once, not per leaf) and the resulting
   loop closure is shared by every leaf, each of which provisions its own
   workspace. That matches the remote runner's "one box per investigation" and it
   is what I'd want, but at 20 concurrent leaves it is 20 containers, and nothing
   in this lane caps that independently of the runner's existing semaphore.
