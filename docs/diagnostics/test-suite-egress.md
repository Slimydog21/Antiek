# Test-suite network egress — census and the credential fix

**Date:** 2026-09-20 · **Branch:** `fix/provider-env-isolation-20260920` · **Base:** `b00ad8913`

## How this surfaced

Four tests in `tests/test_evidence_retriever_bridge.py` failed on an operator
machine and passed in CI. The failure text was a DNS error, not an assertion:

```
ProviderError: xiaomi: network error — [Errno 8] nodename nor servname provided
```

`XIAOMI_API_KEY` was exported in that machine's shell. `substrate/dispatch/
providers/bootstrap.py:_maybe_xiaomi()` registers a live provider whenever it
finds a key, so the test dispatched to `api.mimo.xiaomi.com` for real. With
`env -u XIAOMI_API_KEY`, all 16 tests in the file pass.

The tests were never broken. The suite's result depended on which credentials
the machine happened to export.

## The defect: a hand-maintained defense that drifted

CI already defends against this — `ci.yml` sets provider keys to `""`. The list
was written by hand and fell out of sync with the code it defends:

| | |
|---|---|
| Read by `substrate/dispatch` | `ANTHROPIC`, `DEEPSEEK`, `HERMES`, `OPENAI`, `OPENROUTER`, **`XIAOMI`**, **`Z_AI`** |
| Blanked by CI | `ANTHROPIC`, `DEEPSEEK`, `HERMES`, `OPENAI`, `OPENROUTER`, `XAI` |

`XIAOMI_API_KEY` and `Z_AI_API_KEY` were read but never blanked. `XAI_API_KEY`
was blanked but is not read under `substrate/dispatch` — a stale entry, left in
place, since removing a defense is the wrong direction.

Four CI steps were affected, not one:

| Step | Missing |
| --- | --- |
| `Run pytest shard` (the required merge gate) | `XIAOMI`, `Z_AI` |
| `HTML-projection layer gates (HPRJ SPR-07 M4)` | `HERMES`, `XIAOMI`, `Z_AI` |
| `Invariant-registry meta-check` | all 7 — it had no `env:` block at all |
| `Compounding benchmark (SPR-09 keystone)` | `XIAOMI`, `Z_AI` |

The `Invariant-registry meta-check` case is worth noting on its own: its inline
comment describes it as a "Hermetic in-process runner" while nothing enforced
that. The claim was true of its runner and false of its environment.

## The fix

1. **`tools/lint/provider_env_isolation.py`** — derives the expected key set from
   the source on every run (AST over `substrate/dispatch`), reads `ci.yml`, and
   fails on any gap. Adding a provider that reads a new key now reds here
   instead of silently reopening the hole. Two rules: a step running tests from
   `tests/` must blank every key, and a step that blanks *some* keys must blank
   *all* of them — partial isolation is how this drifted.
2. **`tests/test_provider_env_isolation.py`** — wires it into the suite, so it
   runs inside the `pytest shard` checks the `main-gate-integrity` ruleset
   requires.
3. **`tests/conftest.py`** — a third autouse fixture, `_isolate_provider_
   credentials`, deletes every `*_API_KEY` from the environment per test, so a
   local run matches CI instead of diverging from it. Pattern-based rather than
   list-based, so it cannot drift. Tests that want a provider still set one
   explicitly — `monkeypatch.setenv` runs after the fixture.
4. **`.github/workflows/ci.yml`** — the four steps above now blank all seven.

### Mutation evidence

A gate is only real if breaking the thing it guards turns it red.

| Mutation | Result |
| --- | --- |
| New `NEWVENDOR_API_KEY` added to `bootstrap.py` | RED in all 4 steps — derivation is live |
| `XIAOMI_API_KEY` line deleted from the shard step | RED — `does not blank: XIAOMI_API_KEY` |
| `XIAOMI_API_KEY: ${{ secrets.XIAOMI }}` | RED — `declares a non-empty provider key` |
| (restored) | GREEN |

### Verification

With `XIAOMI_API_KEY` and `DEEPSEEK_API_KEY` still exported in the shell,
`tests/test_evidence_retriever_bridge.py` is **16 passed, zero network attempts**.
Before the fix, on the same machine, it was 4 failed and 6 tests reaching the
internet.

## The wider finding — NOT fixed here

An egress detector (records every non-loopback `connect`, denies it, attributes
it to the test that attempted it) was run across the full suite. Provider
credentials are one of three classes, and the smallest:

| Destination | Attempts | What it is |
| --- | --- | --- |
| `huggingface.co` | 384 | model/tokenizer downloads at test time |
| `api.mimo.xiaomi.com` | 46 | the provider-credential class — **fixed by this PR** |
| Google IP ranges (`142.251.*`, `2001:4860:*`) | ~131 | outbound URL fetching, mostly `test_link_monster_*` |

**561 attempts from 39 distinct tests across 19 hosts. 72 of those attempts
happened during collection**, before any test body ran.

Denying egress reds 17 tests. Attributing each by whether it actually attempted
a connection:

* **11 are denial-caused** — `test_evidence_retriever_bridge` (4),
  `test_semantic_retrieval_divergence` (2), `test_loop_one_orchestrator`,
  `test_loop_one_concurrent`, `test_investigation_endpoints`,
  `test_investigation_deposits_synthesis`, `test_exa_gather_returns_real_chunks`.
* **6 failed without ever opening a socket** — `test_coordination_no_fork` (3),
  `test_grounding`, `test_prime_agent_process`, `test_prime_agent_wire_contract`
  — a different cause, not attributable to this census.

These 11 pass in CI today only because the runner has working internet. They mean
a HuggingFace outage or a slow mirror can red `pytest shard N of 4`, which the
`main-gate-integrity` ruleset requires to merge.

Fixing them is a larger change than this PR (a local model cache or stubbed
embeddings for the HuggingFace class; a fetch seam for the link class) and it
should be the operator's call, not a side effect of a credential fix.

The recommended next step matches the pattern already established in
`docs/decisions/test-integrity-ci-floor.md`: land the detector as an
**informational-first** gate with a recorded baseline of the known-networked
tests, let the baseline settle, then flip it to blocking under a written
reconsider-if condition. It is deliberately not committed here, because
committing a gate without an agreed baseline is how informational gates become
permanent noise.

### What the census does NOT establish

The number above is a **lower bound, not a total.** The detector wraps
`socket.socket.connect` and `socket.create_connection`. It does not wrap
`socket.socket.connect_ex`, it does not wrap `getaddrinfo`, and anything that
shells out — a subprocess running `curl` — bypasses it entirely.

A non-zero result proves the instrument fired. It does not prove the instrument
is complete, and no control was planted to bound the miss rate. The three
classes below are real; the absence of a fourth is not established.

A peer session censusing the vitest suite independently reported two successive
"zero outbound attempts" results that were both **false** — one from a config
path that meant nothing ran, one from logging through a channel vitest buffers
and never surfaces. They only trusted the third after asserting a deliberate
call to a known-bad host appeared in the log. That control is the right bar for
any future run of this census, including a non-zero one: a partially-wired
instrument yields a plausible non-zero just as easily as a broken one yields a
zero. (Their result, with the control in place: 283 attempts, all to
`localhost`, zero external — the pytest problem has no vitest twin. Playwright
e2e remains uncensused.)

## Unrelated observations from the same run

* `tests/substrate/dispatch/test_notdiamond_shadow.py::test_outer_deadline_bounds_a_hung_selector`
  asserts a 40 ms wall-clock budget and flakes under CPU load — measured at 3/5
  and 2/5 failures across ten runs, at the same rate with and without this PR's
  conftest change. It is a candidate for `tests/quarantine.toml`.
* A test run writes `tests/benchmarks/results/baseline_m3_*.jsonl` into the
  working tree. The conftest firewall redirects the DuckDB store but not this
  path.

## Scope

This PR fixes the credential class completely and leaves the other two
documented and measured. It does not change product behavior; it changes which
credentials a test process can see.
