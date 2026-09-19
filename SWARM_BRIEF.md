# SWARM LANE: make the connected BYO tools actually work

The operator wants users to connect their own X and YouTube API credentials. The
credential chassis is built and wired UI-to-store. Neither vendor actually works.

## Operating contract (read before touching anything)

You are ONE lane of a five-engine swarm on the Antiek platform. You work ONLY in
this worktree. Do not touch files outside the scope named below — a sibling engine
owns them and an out-of-scope edit will be rejected wholesale.

Repo invariants that override any instinct you have (from CLAUDE.md):
- DuckDB is single-writer; uvicorn runs `--workers 1`. Never change that.
- Substrate is the source of truth; every claim cites chunks, every chunk cites
  documents. Do not break the provenance chain.
- Prose and comments: flows, no LLM-slop, no forced bullet lists, no filler.
- Do NOT run the whole pytest suite (thousands of tests, many slow). Run ONLY the
  test files named in the done-bar, plus any you add.
- There is NO `timeout` binary on this Mac. Never invoke it.
- Python is `/Users/slimydog/Antiek/platform/.venv/bin/python` (3.12). Run pytest
  from this worktree root so imports resolve here.

HONESTY CONTRACT — this is the part that matters most:
- If the change turns out to be wrong, blocked, or larger than the brief claims,
  STOP and write what you found in HANDOFF.md. A truthful "blocked, and here is
  why" is worth more than a plausible diff. Do not invent a passing result.
- Never weaken, skip, xfail or delete an existing test to make your change pass.
  If an existing test genuinely encodes stale behavior, say so explicitly in
  HANDOFF.md with the reasoning, and change it deliberately rather than quietly.
- Every claim you make in HANDOFF.md must be backed by a command you actually ran,
  pasted with its real output. Another engine of a different lineage will re-run
  them adversarially, so a fabricated result will be caught and the lane rejected.

When done: commit to this worktree with a clear message, then write HANDOFF.md at
the worktree root containing: what changed and why, the exact commands you ran and
their real output, what you did NOT do and why, and anything you are unsure about.

## Scope: ONLY these files
interfaces/research/api/research_tool_search.py, runtime/connectors/*,
apps/reading/src/modes/Sources/ConnectedToolSearch.tsx, and their tests.

## Task 1 — X search raises AttributeError on every call
`interfaces/research/api/research_tool_search.py:265` calls
`connector.recent_search(body.query, max_results=body.max_results)`, but the
resolved connector (`runtime/connectors/x_twitter.py`) defines no such method. The
method that exists is `search_tweets` at :179, with exactly that signature, and it
returns the raw `data` list the `_x` mapper at research_tool_search.py:220-236
already expects. So every X search from the Sources page 500s.

Change :265 to `connector.search_tweets(...)`.

Then make the test real. `tests/test_research_tool_search.py:23-33` defines a fake
with only `search`, which is why a missing method passed CI. Add a vendor="x" case
whose fake is an ACTUAL `runtime.connectors.x_twitter.XTwitterConnector` over an
`httpx.MockTransport` — the pattern already used in
`tests/test_connectors_x_youtube.py:82`. A future rename must break this test.

## Task 2 — YouTube burns quota and returns nothing
Grounding found the YouTube path runs, spends 100 quota units against the user's
own Google project, and returns zero candidates on every call — an
adapter/connector return-shape mismatch. Find it (compare what the connector
returns against what the mapper in research_tool_search.py destructures), fix it,
and pin it with a MockTransport test using a realistic YouTube search response body.

Spending a user's quota to return nothing is worse than failing, because it is
silent. If you find the shape mismatch is actually somewhere else, say so.

## Task 3 — the 403 branch poisons the idempotency journal
Grounding found the vendor-403 branch is mis-typed and permanently poisons the
`operation_id` — so once a user's quota is exhausted, that operation can never
succeed again even after quota resets. Locate it in the quota/error handling,
classify a vendor 403 as a retriable-later condition rather than a terminal
journal entry, and test that the same operation_id succeeds on a later attempt.

## Done-bar (mechanical, all must pass)
1. `.venv/bin/python -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q` — green.
2. The X test uses a real XTwitterConnector over MockTransport, not a hand-rolled fake.
3. A test proving a realistic YouTube response yields a NON-empty candidate list.
4. A test proving a vendor 403 does not permanently poison the operation_id.
5. No live network calls anywhere in tests.
