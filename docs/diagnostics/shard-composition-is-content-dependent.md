# Adding one test file reshuffles every shard

**Date:** 2026-09-20 · **Base:** `origin/main`

## The property

`tools/pytest_file_shard.partition_nodeids` is a greedy load balancer, not a
stable hash. It sorts every collected file by descending test count and assigns
each to whichever shard is currently lightest:

```python
files = sorted(by_file.items(), key=lambda item: (-len(item[1]), item[0]))
for _, file_nodeids in files:
    shard_index = min(range(count), key=lambda index: (loads[index], index))
```

That balances well, and it means **shard membership is a function of the whole
collected set**. Add one small test file and files unrelated to it move between
shards.

Measured, not argued. Collecting `tests/ -m "not integration"` gives 10263 node
ids. `tests/test_provider_env_isolation.py` contributes **9** of them:

| collected set | `test_investigation_deposits_synthesis.py` lands in |
| --- | --- |
| with those 9 node ids | **shard 2** |
| without them | **shard 1** |

Nine node ids out of ten thousand relocated an unrelated file across a shard
boundary.

## Why it matters

The four `pytest shard N of 4` checks are required by the `main-gate-integrity`
ruleset. Because composition depends on content, **which tests share a process
is a function of the PR under test**. A latent order-dependent defect therefore
surfaces on whichever PR happens to co-locate its trigger and its victim — which
may be a PR that touches nothing related.

That is not hypothetical either. Two PRs hit the same failure on the same day in
different shards:

```
_duckdb.ConnectionException: Can't open a connection to same database file
with a different configuration than existing connections
  tests/test_investigation_deposits_synthesis.py::test_investigation_deposits_synthesis_with_manifest
```

* **#3284** — shard 0. Touches 5 `.css`, 2 `.md`, 8 `.ts`, 9 `.tsx` and **zero
  `.py`**, so its collected set, and therefore its shard composition, is
  byte-identical to `main`'s. It still failed. That is what proves the defect is
  latent on `main` rather than introduced by either PR.
* **#3281** — shard 1. Adds `.py` test files, so its composition differs.

The test isolates its own database correctly (`db_path = tmp_path /
"graph.duckdb"`), so a same-file collision can only mean a process-global DuckDB
connection leaked from an earlier test in the same shard. It is load-sensitive,
which is why it appeared on a day with 36 CI runs queued and not on a quiet
board.

`tests/quarantine.toml` already has an `order-dependent` category in its
taxonomy. This test is not listed in it.

## What NOT to conclude

A red shard on a PR that touches nothing related is not evidence that the PR
broke something, and a green board is not evidence that an order-dependent
defect is absent — it may simply have landed in a shard where its trigger did
not run. Attribute by mechanism, not by which PR was unlucky:

1. Does the PR change the collected `.py` set at all? If not, its composition
   equals `main`'s and the defect is on `main`.
2. Does the failing test isolate its own state? If yes, a collision means
   something process-global leaked from a sibling.
3. Does it reproduce in isolation? If it passes there, it is order-dependent by
   definition and the shard is the variable.

## Options, none taken here

Recording the property, not changing it. The obvious moves each have a real cost
and belong to whoever owns the test-integrity floor:

* Quarantine the test under the existing `order-dependent` category. Cheapest,
  but it hides a genuine connection leak rather than fixing it.
* Find and close the leak — a process-global DuckDB handle opened with a
  different configuration than a sibling opens later. Correct, and the only
  option that makes the board mean what it reads.
* Make partitioning content-independent (stable hash per path, which the module
  already implements as `shard_for_nodeid` and does not use). That trades
  balance for determinism and would make an order-dependent failure reproducible
  on the same shard every time.

Quarantining another lane's backend test to unblock an unrelated PR is the one
option that should not be taken quietly.
