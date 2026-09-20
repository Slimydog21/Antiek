# Lane handoff — Prime invocation profile + kernel environment

Branch `lane/primekernel-20260920`, from `origin/main` at `ebc5996ad`.

> This file is a rolling per-lane artifact — each lane replaces it, and each copy
> names its own branch in this header. The version it replaced is the
> write-lock-on-the-event-loop lane's, recoverable with
> `git show ebc5996ad:HANDOFF.md`.

## 1. Is Prime execution contained today? No.

Four independent checks, all on this checkout of main:

- `PrimeAgentRLMBackend.run` calls `run_prime_agent_process`
  (`orchestration/rlm/prime_agent_backend.py:165`), which reaches
  `subprocess.Popen(argv, executable=artifact, cwd=config.cwd, env=env,
  start_new_session=True)` at **`runtime/prime_agent/process.py:124-133`**. A
  child of the API process, on the host, as the service user.
- `grep -rn "exec_backend\|ExecutionBackend\|Workspace" runtime/prime_agent/
  orchestration/rlm/` returns **nothing**. The RLM backend never touches the
  isolation seam. Read the scope of that grep literally: the sandbox-provider
  abstraction lives in `runtime/remote_exec/`, and Prime *does* have an adapter
  there. See the verifier note below.
- `runtime/research_runner/contained_gather.py` contains only `GATHER_PROGRAM`
  (`:136-176`), a stdlib-only placeholder its own docstring calls "the
  placeholder payload… not a research agent" (`:52-62`). `grep -rin prime
  runtime/research_runner/` returns **nothing**.
- `interfaces/research/api/cascade_routes.py` has **zero** occurrences of
  "prime". The contained path and the Prime path never meet.

So `contained_gather` contains the gather loop's step payload and nothing else.
No Prime invocation runs inside a workspace. Per the brief's decision tree, tools
stay off and this lane adds the profile seam only.

### Verifier correction — there is a fourth Prime argv, and it is tool-enabled

`PrimeExecProvider._spawn` at `runtime/remote_exec/prime_exec.py:447` builds
`prime-agent --mode rpc --session-dir <dir>` plus optional `--provider`/`--model`
and nothing else: no `--no-tools`, no `--offline`, none of the five discovery
flags. `_build_env` (`:431-438`) forwards the real `HOME` through
`_SAFE_ENV_KEYS` as well as `PRIME_AGENT_KERNEL_PYTHON`, so a kernel venv
resolves there normally — the §5 breakage below is specific to the RLM backend's
throwaway `HOME`, not to Prime generally.

That path is not a hole. `_require_enabled` raises `RemoteExecUnavailable`
unless `ANTIEK_PRIME_EXEC_ENABLED` is truthy, the default remote-exec factory
never registers the provider, and the module docstring requires the caller to
supply an external isolation boundary; `tests/test_prime_exec_provider.py`
covers both the gate and the non-registration. But it is the one tool-enabled
Prime invocation in this tree, so the original claim that the flag list is
restated by *three* files was an undercount that the module docstring, the
decision record and a test class name all carried. All three now name the
fourth site and say why it is outside the agreement. It is not asserted against
the profile flags, because pinning its current flagless shape would make that
shape a contract rather than a documented exception.

### Verifier correction — "unreachable by configuration" was unenforced

The profile module said `ACTIVE_PROFILE` is a module constant rather than a
constructor argument "on purpose", and a test comment said "the constructor
takes no profile argument, so RLM cannot be reached by configuration". Nothing
tested it. Adding `profile: PrimeInvocationProfile = ACTIVE_PROFILE` to
`PrimeAgentRLMBackend.__init__` and building argv from `self._profile` passed
the entire lane suite while both comments went on asserting the opposite.
`test_no_construction_path_accepts_a_profile` now reads the signatures of the
constructor and of `prime_agent_backend_from_environment` and fails if a
selector appears; that mutation is caught.

## 2. Brief corrections

**SPR-2 is already done on main.** The spec says no non-test code constructs a
backend and the wrestling bridge passes none. It does now:
`interfaces/research/api/wrestling.py:539` passes
`prime_backend=prime_agent_backend_from_environment()`, with a comment block at
`:520-534` explaining the two-flag gate. This makes the lane *more* load-bearing,
not less — Prime is runtime-reachable behind
`ANTIEK_PRIME_AGENT_RLM_ENABLED` + `ANTIEK_RLM_RATIFIED`.

**The kernel venv measurement in the brief is of the wrong interpreter.** See §4.

**Most of the second task is already built on main.** `substrate/agent_skills/`
(duckdb_store / py_analysis / sketch_svg, with README and registry) already
decides the DuckDB rule by construction and already covers the
Processing-into-HTML-assets half. It went the *opposite* way from the spec's
proposal — stdlib-only, "nothing added to pyproject.toml", rather than adding
polars and a plotting path. I did not build a second copy.

## 3. What I built

`orchestration/rlm/prime_invocation_profile.py` — `PrimeInvocationProfile` with
`EVIDENCE` (today's flags, byte-for-byte) and `RLM` (drops only `--no-tools`,
keeps all five discovery flags), plus `ACTIVE_PROFILE = EVIDENCE`.

`orchestration/rlm/prime_agent_backend.py` — `_argv` now builds its flag block
from `ACTIVE_PROFILE`.

`tests/test_prime_invocation_profile.py` — 9 tests.

**On "a seam with no consumer is an antipattern".** I agree with the principle
and built the seam anyway, because this is not that shape. `EVIDENCE` has a live
consumer from the first commit: it *is* the production argv. It also earns its
place independently of RLM by holding in one reviewable spot a flag list that
three files restate separately — `prime_agent_backend._argv`,
`prime_rpc_evidence._argv` (`:236-247`) and the `_PRINT_FLAGS` set that
`verify_prime_agent_installation` probes the binary against
(`runtime/prime_agent/installation.py:49-61`). Those three must agree and
nothing checked that they did; two tests now do. Only the `RLM` *member* is
unselected, and an enum value pinned by a test is a written decision, not an
unreachable module. `ACTIVE_PROFILE` is the single greppable line that changes
when containment lands.

I did **not** add a per-call `profile=` constructor argument. That would make
`RLM` reachable by configuration, which is the thing that must not be true.

## 4. Kernel interpreter — answered by measurement

`~/.prime/agent/kernel-venv/bin/python` → **Python 3.11.15**.
`platform/.venv/bin/python` → Python 3.12.13. Different processes.

Resolution is `getKernelVenvDir()` at `dist/core/kernel/bootstrap.js:309-314` of
the installed prime-agent 0.9.4 module: `$PRIME_AGENT_KERNEL_VENV`, else
`os.homedir()/.prime/agent/kernel-venv`.

The kernel venv **already has** pandas 3.0.5, numpy 2.4.6, scipy 1.17.1,
**matplotlib 3.11.2**, requests, httpx, yaml, bs4, lxml, pydantic, dill — the
`DEFAULT_RLM_EXTRA_PACKAGES` list at `bootstrap.js:19-32`. It **lacks duckdb**,
which is the operator's first-named ask and is not in that list, so it will never
arrive by auto-bootstrap. It also cannot import Antiek code
(`import substrate.agent_skills` → `ModuleNotFoundError`; no Antiek path on
`sys.path`).

Full decision, including the DuckDB access rule and the one operator command, is
in **`docs/decisions/prime-kernel-provisioning.md`**. I installed nothing.

## 5. New finding — the RLM profile would not even work on that path

`runtime/prime_agent/process.py:205-226` passes through only `PATH`/`LANG`/
`LC_ALL` and overrides `HOME` to a temp dir deleted at call end. It does **not**
forward `PRIME_AGENT_KERNEL_PYTHON`, though `runtime/remote_exec/prime_exec.py:432-435`
deliberately does. Node's `os.homedir()` follows `$HOME` — verified:
`HOME=/tmp/fake-home node -e '...os.homedir()'` → `/tmp/fake-home`. So the kernel
venv would resolve under the throwaway HOME, never exist, and trigger a uv
bootstrap that needs network while argv carries `--offline`.

A second independent reason not to flip `ACTIVE_PROFILE`. Whoever lands
containment must settle the kernel-interpreter question in the same change.

## 6. Recommended tightening, not shipped

Prime 0.9.4 `--help` advertises `-t, --tools <list>` — "Allowlist comma-separated
tool names". `--tools ipython` grants exactly the RLM mechanism instead of
granting everything, which is strictly tighter than dropping `--no-tools`. I did
not add it as a third profile: it is absent from `_PRINT_FLAGS` so the
installation gate would not verify it, and I could not exercise it against a real
provider from here. Shipping an untested third profile would be the antipattern
squared.

## 7. Open items I did not touch

- `_PASSTHROUGH_ENV` at `orchestration/rlm/prime_agent_backend.py:33` is defined
  and referenced nowhere. Dead constant; removing it is a separate concern.
- `orchestration/rlm/session.py:99` has a pre-existing `mypy --strict`
  `[type-arg]` error, reproduced with my changes stashed. Not mine.

## 8. Commands run

```
pytest tests/test_prime_invocation_profile.py tests/test_prime_agent_rlm_backend.py
       tests/test_prime_agent_process.py tests/test_prime_agent_wire_contract.py
       tests/test_rlm_bridge.py tests/test_rlm_prime_call_site_wiring.py
       tests/test_prime_rpc_evidence.py tests/test_agent_skills.py -q
  → 131 passed in 36.88s

ruff check <3 touched files>                     → All checks passed!
ruff format --check <2 new files>                → 2 files already formatted
mypy --strict prime_invocation_profile.py prime_agent_backend.py
  → 1 error, orchestration/rlm/session.py:99, pre-existing (reproduced on stashed tree)
python -m tools.lint.reachability_gate_py --baseline tools/lints/baselines/reachability_py.json
  → exit 0

git diff --stat tests/test_prime_agent_rlm_backend.py  → empty (existing pinning test UNCHANGED)
diff <argv on origin/main> <argv on branch>            → IDENTICAL
```

`ruff format` is not a CI gate here and `prime_agent_backend.py` was already
unformatted on `origin/main`, so I did not reformat it — that would have buried a
14-line change in an unrelated whole-file diff.
