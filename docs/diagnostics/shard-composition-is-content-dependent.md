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

  That inference has a premise, and the premise is easy to miss: "no `.py`
  changed" only implies "same collection" if **no Python test's collection count
  depends on the repo tree**. A test that parametrized over a glob of `.tsx`
  files would make a frontend-only diff reshuffle backend shards — the exact
  mechanism above, triggered by a PR touching no Python at all.

  Checked, rather than assumed. `tests/test_cost_consent_no_disbursement.py`
  does parametrize over frontend paths (`_FRONTEND_SURFACE_FILES`, four
  parametrize sites), which is precisely that shape — but it is a hardcoded
  two-element tuple of literal `.tsx` paths, so its count cannot move with the
  file tree. Repo-wide, no module-level glob of the tree feeds any
  `parametrize`: every `glob`/`rglob`/`iterdir` in `tests/` runs inside a test
  body against `Path.home()`, `tempfile.gettempdir()`, `tmp_path` or an output
  directory, never the checkout. And #3284 is 24 modified with 0 added and 0
  deleted, so even a glob-based parametrization would have yielded the same
  count.

  **This is the premise to re-check before anyone reuses this argument**, and it
  is one refactor away from being false: converting `_FRONTEND_SURFACE_FILES`
  to a glob is an obvious-looking improvement that would silently invalidate it,
  with no signal to the next person reasoning this way. Credit to the
  slimydog-6f session for finding the hole in its own argument.
* **#3281** — shard 1. Adds `.py` test files, so its composition differs.

The test isolates its own database correctly (`db_path = tmp_path /
"graph.duckdb"`), so a same-file collision can only mean a process-global DuckDB
connection leaked from an earlier test in the same shard. It is load-sensitive,
which is why it appeared on a day with 36 CI runs queued and not on a quiet
board.

**It is also non-deterministic at fixed composition, which is stronger than
anything above.** Both failures cleared without the defect being touched:

* #3281 failed, then passed. The only commits in between added a markdown file.
  A `.md` is not collected, so the node set — and therefore the shard
  composition — was byte-identical across the two runs.
* #3282 failed, then passed on a **plain re-run of the same commit**. No diff at
  all.

So composition explains *which shard* a failure appears in; it does not explain
*whether* it appears. The trigger is a race or an ordering effect within the
shard process, amplified by load. Any attribution that stops at "this PR changed
the shard" is incomplete, and any green run is weak evidence — the same commit
produced both outcomes.

`tests/quarantine.toml` already has an `order-dependent` category in its
taxonomy. This test is not listed in it.

## CORRECTION — there are TWO causes behind this one error message

A later commit on `main`, `d87dd5208` "fix(loop-one): deposit the synthesis
BEFORE announcing INVESTIGATION_COMPLETED", found a **real production race**
producing this identical DuckDB error, and its author explicitly retracted their
own "pre-existing order-dependence exposed by shard packing" call.

They are right about their branch and it does not transfer to the instances
above. Checked rather than assumed:

* The race was introduced by `28ce4af9e` "hop the last three non-route
  write-lock calls off the loop", which changed
  `_deposit_synthesis_to_substrate(ctx)` to
  `await asyncio.to_thread(_deposit_synthesis_to_substrate, ctx)`. Correct in
  intent — the DuckDB write does not belong on the event loop — but both call
  sites emitted `InvestigationCompletedPayload` FIRST. While the deposit was
  synchronous there was no yield between the two; `await asyncio.to_thread(...)`
  introduces exactly that yield, so a subscriber can observe
  INVESTIGATION_COMPLETED before the syntheses row exists. The frontend and the
  artifact exporter are exposed to it, not only the test that caught it.
* `grep -c "asyncio.to_thread(_deposit_synthesis_to_substrate"` returns **0** at
  `b00ad8913`, **0** at `57c2337fb`, and **0** on both
  `fix/provider-env-isolation-20260920` and
  `fix/attribution-share-invariant-20260920`. `28ce4af9e` merged to `main` after
  `57c2337fb`, so neither branch above ever carried it.

So the same error message has two roots, and they need different responses:

| | cause | response |
| --- | --- | --- |
| tree contains `to_thread` on the deposit path | real production race, ordering guarantee broken | fixed by `d87dd5208` — deposit first, announce after |
| tree does not | something else, non-deterministic at fixed composition | still open |

**Check which tree you are in before attributing.** `git grep -c
"asyncio.to_thread(_deposit_synthesis_to_substrate" -- orchestration/loop_one/`
settles it in one command. The evidence above — two failures clearing with
byte-identical composition, one on a plain re-run of the same commit — stands
for the second row only, and this document previously implied it covered both.

### And the misdiagnosis had a cause this repo can fix

`d87dd5208`'s own message explains why three CI runs were spent on the wrong
answer: *"every local reproduction had provider keys exported, so
`_dispatch_once` found a registered `xiaomi`, forced `provider_override="xiaomi"`
and died on DNS long before the deposit. That masked the real behaviour."*

That is precisely the defect PR #3281 closes. Ambient provider credentials made
a local reproduction diverge from CI and hid a real production race behind a DNS
error. It is the strongest argument for that change that anyone has made, and it
was made by someone who did not know the change existed.

## What NOT to conclude

A red shard on a PR that touches nothing related is not evidence that the PR
broke something, and a green board is not evidence that an order-dependent
defect is absent — it may simply have landed in a shard where its trigger did
not run. Attribute by mechanism, not by which PR was unlucky:

1. Does the PR change the collected node set at all? Note that this is not the
   same question as "does it touch `.py`" — re-check the premise above first,
   because a Python test parametrized over a tree glob would let a non-Python
   diff change the count. If the node set is unchanged, composition equals
   `main`'s and the defect is on `main`.
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
  already implements as `shard_for_nodeid`, exports in `__all__`, and never
  calls — `pytest_collection_modifyitems` calls `partition_nodeids` instead).
  That trades balance for determinism and would make an order-dependent failure
  reproducible on the same shard every time.

  **This option is stronger than the other two on second-order grounds.**
  Quarantine hides a real connection leak. Finding the leaked handle is correct
  but unbounded. Only the stable hash buys the property that *a PR's content
  cannot change which tests share a process*, which is what makes a green board
  mean something — and it closes the latent trap above permanently, rather than
  leaving a correct-today premise that one plausible refactor turns false. The
  module's own docstring already concedes the tradeoff it was avoiding: "a
  stable hash can produce as the suite grows while retaining reproducible
  shards."

Quarantining another lane's backend test to unblock an unrelated PR is the one
option that should not be taken quietly.
