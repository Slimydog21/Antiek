# Prime kernel provisioning — which interpreter, which imports, and the DuckDB rule

**Decision date:** 2026-09-20
**Status:** ✅ Settled for the substrate half; the one provisioning action is operator-gated
**Owner:** operator + the Prime invocation lane (`orchestration/rlm/prime_invocation_profile.py`)

The operator's ask is that research agents do database building in DuckDB and
SQL, Python data analysis, and Processing-lineage visuals that land in HTML
assets. The engineering question underneath it is narrow: a Prime kernel is a
separate process, so what can that process import, and what is it allowed to
touch. This records the answer, the measurements behind it, and the one thing a
human still has to do.

## 1. The kernel does not use the platform venv

Measured, not assumed:

```
~/.prime/agent/kernel-venv/bin/python --version   →  Python 3.11.15
/Users/slimydog/Antiek/platform/.venv/bin/python --version  →  Python 3.12.13
```

Two different interpreters. Prime resolves the kernel venv in
`getKernelVenvDir()` at `dist/core/kernel/bootstrap.js:309-314` of the installed
`prime-agent` module: `$PRIME_AGENT_KERNEL_VENV` if set, otherwise
`os.homedir()/.prime/agent/kernel-venv`, auto-bootstrapped with uv on first
invocation. `PRIME_AGENT_KERNEL_PYTHON` (`bootstrap.js:735-759`) points it at an
existing environment instead, provided that environment already has a current
`prime-agent-runtime`.

**Consequence: any measurement of `platform/.venv` is irrelevant to what a Prime
kernel can import, and installing into it would provision the wrong process.**
The earlier finding that the platform venv has `duckdb` and no `pandas` is
accurate about the platform venv and says nothing about the kernel.

## 2. What the kernel already has

`DEFAULT_RLM_EXTRA_PACKAGES` at `bootstrap.js:19-32` is the declared default
set, and the venv on this machine matches it. Measured with
`~/.prime/agent/kernel-venv/bin/python -c "import X"`:

| Import | Status |
|---|---|
| `pandas` | 3.0.5 |
| `numpy` | 2.4.6 |
| `scipy` | 1.17.1 |
| `matplotlib` | 3.11.2 |
| `requests` / `httpx` | 2.34.2 / 0.28.1 |
| `yaml` / `tomli` / `dotenv` | present |
| `bs4` / `lxml` | 4.15.0 / 6.1.3 |
| `pydantic` | 2.13.5 |
| `dill` | 0.4.1 |
| **`duckdb`** | **missing** |
| `polars` | missing |
| `turbopuffer` | missing |

So "Python for data analysis" and "a plotting path" need no provisioning at all:
pandas, numpy, scipy and matplotlib are already there, by Prime's own default.
Adding `polars` would duplicate `pandas`; this decision does not.

**The single real gap is `duckdb`, which is the operator's first-named ask and
is not in `DEFAULT_RLM_EXTRA_PACKAGES`.** It will therefore never arrive by
auto-bootstrap, at any Prime version, until somebody puts it there.

## 3. The DuckDB access rule, which was already settled by construction

The invariant is that DuckDB is single-writer and `runtime/db_lock` is the sole
funnel. A Prime kernel is a separate process, so the rule has to make a second
writer impossible rather than merely discouraged.

`substrate/agent_skills/` already does this, and it does it structurally:
`duckdb_store` creates an **in-memory** store and *takes no path argument at
all*, so there is no expression a kernel can evaluate that opens the corpus
database for writing. `py_analysis` reads only. `sketch_svg` emits static bytes
through `services.html_projection.gate.assert_script_free`, which is the same
zero-script gate the ingest daemon applies, and is the answer to the
Processing/p5-into-HTML-assets half of the ask.

**Rule: a Prime kernel gets `substrate.agent_skills` and nothing else that
touches DuckDB. No corpus path, no read-only connection to the live file, no
`db_lock` import.** A read-only connection was considered and rejected: it is a
weaker guarantee than "no path argument exists", it invites a later widening to
read-write, and it would put a corpus file path inside a process whose own
README says it is not a security sandbox.

## 4. Where the declaration goes

`substrate/agent_skills/README.md` records "no heavy deps — nothing added to
`pyproject.toml`", and that stands for the platform. The kernel is a different
process with a different declaration site, and it has two:

- `duckdb` belongs in the kernel venv, installed there once by the operator.
- `PRIME_AGENT_KERNEL_PYTHON`, if the kernel is ever pointed at a purpose-built
  environment instead of the auto-bootstrapped one, is the variable that selects
  it.

Neither is a code change in this repository, which is why this document is the
declaration and no dependency file moves.

## 5. Blocked: the RLM backend cannot select a kernel interpreter today

Two Prime spawn paths exist and they disagree about exactly this variable.

`runtime/remote_exec/prime_exec.py:432-435` forwards
`PRIME_AGENT_KERNEL_PYTHON` into the child environment deliberately.

`runtime/prime_agent/process.py:205-226` — the path
`PrimeAgentRLMBackend` uses — does not. It passes through only `PATH`, `LANG`
and `LC_ALL`, then overrides `HOME` to a freshly created temp directory that is
deleted when the call returns.

That override is the blocker, and it is not theoretical. Node's `os.homedir()`
follows `$HOME`, verified directly:

```
HOME=/tmp/fake-home node -e 'console.log(require("os").homedir())'  →  /tmp/fake-home
```

So under the RLM backend, `getKernelVenvDir()` resolves to
`<throwaway-tmpdir>/home/.prime/agent/kernel-venv`, which never exists. A
tool-enabled run there would attempt a fresh uv bootstrap on every single call;
that bootstrap needs the network, and the argv carries `--offline`. It would
fail before executing anything.

**This is a second, independent reason not to enable tools on that path**, on top
of the containment reason recorded in
`orchestration/rlm/prime_invocation_profile.py`: today the RLM profile would not
merely be unsafe, it would not function. Whoever lands containment has to settle
the kernel-interpreter question in the same change — forwarding
`PRIME_AGENT_KERNEL_PYTHON`, or giving the child a stable `HOME`, are the two
shapes, and the first preserves the fresh-HOME isolation the envelope was built
for.

## 6. The operator action

One command, run by a human, on the deployment host:

```
~/.prime/agent/kernel-venv/bin/python -m pip install duckdb
```

Nothing in this repository installs it, and nothing in this repository should:
the kernel venv is outside the tree, `pip install` into an operator environment
is not a reviewable diff, and the capability it unlocks is gated on containment
that does not exist yet.

**Reconsider if:** Prime adds `duckdb` to `DEFAULT_RLM_EXTRA_PACKAGES` upstream
(then §6 becomes a version bump), or the kernel is moved to a purpose-built
environment under configuration management (then §4 gains a declaration file and
this document points at it).
