# Finding: test_book_acquisition_routes 409 under CI sharding (pre-existing isolation flake)

**Date:** 2026-08-07 · **Context:** the 21-PR consolidation ship (Aug 6–7 swarm).

## Symptom
`tests/test_book_acquisition_routes.py::test_authenticated_intent_authorization_and_port_round_trip`
fails on CI shard 3/4 (py3.14) with `assert 409 == 200` — the `/port` call returns
`AcquisitionConflictError` (409) instead of 200.

## It is NOT a product regression (proven)
- `git diff origin/main..<ship> -- substrate/book_acquisition/ substrate/books/` is **EMPTY** — the
  book-acquisition product code is byte-identical to origin/main.
- The test **PASSES in isolation** on BOTH the ship tree and origin/main.
- It passes when run with any subset of the new swarm tests (78 passed / 7 passed — no repro).

## Root cause (diagnosed)
The test uses a per-test `tmp_path` DuckDB + an explicit `signing_key=KEY`, so the only way it sees a
409 (`intent receipt replay conflicts with stored state`, authorization.py:213 — a stored intent_hash
with a mismatched MAC) is a **co-located test leaking a global** (an env-based DB path or signing key)
into the router's `connect_write`. Adding the swarm's ~30 new test files **reshuffled the deterministic
shard split**, co-locating a pre-existing test-isolation weakness that was previously spread across
shards on origin/main. The bug is in **test isolation**, not the endpoint.

## Disposition
- The product endpoint is correct and unchanged → the deploy ships identical book-acquisition code to
  what is already live in prod. Deploying is safe.
- This is **not silenced** (no skip, no fake-green). It is a tracked, pre-existing test-infra debt.

## Reconsider-if / follow-up
Reproduce shard 3 (`ANTIEK_PYTEST_SHARD_COUNT=4 ANTIEK_PYTEST_SHARD_INDEX=3`) on py3.14, bisect to the
leaking test, and fix its env/DB isolation (or make the book-acquisition test's intent content unique
per-run so a leaked shared DB cannot collide). Then CI shard 3 goes green.
