# Connectors lane — handoff

Worktree: `/private/tmp/claude-501/-Users-slimydog/c35b7db9-c0ac-456c-a6b1-1d23a11ecc3b/scratchpad/opus-connectors`
Branch: `swarm/connectors-opus-20260918`, cut from `goal/v1-operational-2026-09-18` at `e040b19c8`.

## Read this first: which worktree this is

The harness placed me at `/Users/slimydog/.claude/worktrees/wf_3011288e-413-1`, which is a
worktree of the **home-directory** repo — it holds `Antiek/specs`, not the platform source, so
the lane cannot be executed there. The platform worktree the swarm created for this lane,
`scratchpad/swarm/connectors`, was already occupied: `lsof` showed PID 8695 (`claude --effort max
… -p Read SWARM_BRIEF.md`) with its cwd inside it, writing `scratchpad/swarm/connectors.log`, and
it committed `b5b16ea03` at 20:22 while I was reading. Editing there would have raced a live
sibling. I cut my own worktree off the goal branch instead and did the lane independently.

I did not read that sibling's diff before forming my own, and I have not merged or compared
against it. Two independent answers to the same brief now exist; picking one is the
orchestrator's call, not mine.

## What was actually wrong

All three defects reproduce. One of the brief's claims does not.

**Task 1 — X.** `research_tool_search.py:298` called `connector.recent_search(...)`; the resolved
connector (`runtime/connectors/x_twitter.py`) defines `search_tweets` and nothing else, so every X
search raised `AttributeError` — uncaught by the route's handlers, since `AttributeError` is not a
`RuntimeError`.

The brief says `search_tweets` "returns the raw `data` list the `_x` mapper already expects". It
does not. Raw X v2 tweet objects carry `id` and `author_id`; `_x` (research_tool_search.py:253-269)
reads `tweet_id` and `author_handle`. The rename on its own turns a loud 500 into the same silent
empty list as Task 2 — `external_id` comes back falsy and every row is `continue`d. I verified this
by reading both sides rather than by trusting the brief.

Worse, the handle is not on the tweet at all: X returns it only in the `includes.users` expansion,
which the connector was not requesting and then discarded. So the shape had to be closed in the
connector, not in the route.

**Task 2 — YouTube.** `YouTubeDataConnector.search()` returned the raw `items` array, and
`_youtube` (research_tool_search.py:230-250) reads attributes — `getattr(row, "video_id", "")`.
`getattr` on a dict returns the default silently, so `external_id` was always `""` and every row
was dropped. The 100 units of `search.list` were reserved and spent before that. Confirmed: the
pre-fix run of my new test spends the quota and asserts `[] == [{...}]`.

**Task 3 — the 403 branch.** Two separate faults, both poisoning.

The clause `except (QuotaExhausted, YouTubeQuotaExhausted)` imported `YouTubeQuotaExhausted` from
`acquisition.youtube.data_api` (line 25). The connector the route actually resolves is
`runtime.connectors.youtube.YouTubeDataConnector`, which raises
`runtime.connectors.youtube.YouTubeQuotaExhausted` — a different class with the same name. A real
vendor 403 `quotaExceeded` therefore never entered the quota clause. It fell to the generic
`except (YouTubeApiError, XApiError, OSError, RuntimeError)` (it is caught there only because
`ConnectorError` subclasses `RuntimeError`) and was marked `unknown`.

And `unknown` is terminal: `_claim` raises `409 operation outcome is unresolved` for that row
forever (research_tool_search.py:158-159). So did the quota clause itself — it also called
`_unknown`, so even the locally-metered `QuotaExhausted`, raised by `check_and_reserve` **before
any request is built**, permanently burned an operation the vendor had never seen.

`_release` could not be used as it stood: it deleted only `state='claimed'`, and by the time the
connector raises, `_mark_sent` has already moved the row to `sent`.

## What I changed

`runtime/connectors/x_twitter.py` — `search_tweets` now asks for `expansions=author_id` and
`user.fields=username`, and returns flat records (`tweet_id`, `text`, `author_handle`,
`created_at`, `conversation_id`) via a new pure `_flatten_search_page`.

`runtime/connectors/youtube.py` — new frozen `YouTubeSearchHit` and pure `parse_search_items`;
`search()` returns hits instead of raw items. A hit with no id in its id block is dropped; the rest
keep whatever the vendor sent.

`interfaces/research/api/research_tool_search.py` — `recent_search` → `search_tweets`; the runtime
quota class and `VendorBanned` added to the imports (the acquisition one aliased, not removed,
since the same route still catches `XApiError`/`YouTubeApiError`); the quota clause now calls
`_release`; `_release` widened to `state IN ('claimed','sent')` with the reasoning in its
docstring; a new `_clears_on_its_own` sends a 429 or a governor ban down the release path too,
while transport errors and unparseable bodies keep the terminal `unknown` mark they deserve.

The judgement behind the release: a search is a **read**. A refusal leaves nothing at the vendor to
reconcile, so the outcome is not ambiguous and does not warrant a terminal mark. Ambiguity is still
respected where it is real — an `XApiError` with no status, an `OSError` mid-flight — because there
the request may have reached the vendor.

### Why the parse landed in the connectors rather than the route

The route's two mappers already speak the acquisition lane's parsed shapes; the BYO connectors
spoke raw vendor envelopes. Closing the seam at the connectors means the six pre-existing route
tests keep passing **untouched**, and their fakes — which return parsed rows — become an accurate
model of the connector contract instead of the misleading one that let a missing method through CI.
Closing it at the route would have required rewriting those six tests' fakes.

I did not import `acquisition.*.parse_search_response` from `runtime/connectors`, though it is the
DRY move. `acquisition.twitter.api_client` and `acquisition.youtube.data_api` both import
`runtime.connectors.base`; reaching back up inverts that, and the twitter one additionally pulls
`acquisition.twitter.adapter` into a connector whose docstring promises to stay box-bounded. The
cost is two ~20-line parsers duplicated from the acquisition lane, and the drift risk that comes
with it. **This is the one design call in the lane I would most want a second opinion on.** If the
reviewer prefers DRY over layering, the change is local: delete both helpers and call the
acquisition functions (lazily imported inside the method, which is what dodges the twitter cycle).

I did **not** touch `apps/reading/src/modes/Sources/ConnectedToolSearch.tsx` or
`apps/reading/src/api/researchToolSearch.ts`, both in scope. The wire contract they consume is
unchanged, they already branch on 429 and 409, and the real vendor timestamps
(`2026-08-12T09:30:00.000Z`, `2026-07-01T12:00:00Z`) both satisfy the client's strict
`validTimestamp` check — before this fix no candidate ever reached that validator. One cosmetic
imprecision remains and I left it: the client shows "This provider's search allowance is
exhausted." for every 429, which now also covers the rate-window case whose detail string is
"tool search is rate limited". Fixing it means a vitest file at ~55 s and a collision with the
apps/reading lane that committed `89729c44c`; it is not worth that here.

## Commands, with real output

Baseline before I touched anything (27 → 20 is the 7 tests I added):

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q -p no:randomly
....................                                                     [100%]
20 passed, 1 warning in 1.33s
```

New tests against the **unfixed** code — each defect, reproduced:

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py -q -p no:randomly
E               AttributeError: 'XTwitterConnector' object has no attribute 'recent_search'
interfaces/research/api/research_tool_search.py:298: AttributeError

>       assert response.json()["candidates"] == [{
E       AssertionError: assert [] == [{'external_i...00:00Z', ...}]
E         Right contains one more item: {'external_id': 'dQw4w9WgXcQ', ...}

        refused = client.post("/research/tools/search", json=body)
>       assert refused.status_code == 429, refused.text
E       AssertionError: {"detail":"tool search is unavailable"}
E       assert 503 == 429

        after_reset = client.post("/research/tools/search", json=body)
>       assert after_reset.status_code == 200, after_reset.text
E       AssertionError: {"detail":"operation outcome is unresolved"}
E       assert 409 == 200

FAILED tests/test_research_tool_search.py::test_x_search_yields_candidates_through_the_real_connector
FAILED tests/test_research_tool_search.py::test_youtube_search_yields_candidates_for_the_quota_it_spends
FAILED tests/test_research_tool_search.py::test_vendor_quota_403_leaves_the_operation_retriable
FAILED tests/test_research_tool_search.py::test_local_quota_refusal_leaves_the_operation_retriable
4 failed, 6 passed, 1 warning in 1.14s
```

Done-bar 1, after the fix, exactly as the brief words it:

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q
...........................                                              [100%]
27 passed, 1 warning in 0.72s
```

Done-bar 5 — no live network. A pytest plugin at `../nonet.py` replaces `socket.socket.connect`,
`connect_ex` and `socket.create_connection` with raisers for INET families. First, proof the
blocker is not a no-op:

```
$ ... -m pytest ../test_nonet_selfcheck.py -p no:randomly -p nonet     # httpx.get("https://api.twitter.com/...")
>       raise AssertionError(f"LIVE NETWORK create_connection ATTEMPTED to {address!r}")
E       AssertionError: LIVE NETWORK create_connection ATTEMPTED to ('api.twitter.com', 443)
1 failed in 0.19s
```

Then the suite under it:

```
$ PYTHONPATH=…/scratchpad ... -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q -p no:randomly -p nonet
...........................                                              [100%]
27 passed, 1 warning in 0.74s
```

Mutation check — do the retriable tests pin the journal, or only the status code? I kept the
corrected exception typing and reverted `_release` to `state='claimed'` alone:

```
$ ... -m pytest tests/test_research_tool_search.py -q -p no:randomly -k "retriable"
E       AssertionError: {"detail":"operation outcome is unresolved"}
E       assert 409 == 200
FAILED tests/test_research_tool_search.py::test_vendor_quota_403_leaves_the_operation_retriable
FAILED tests/test_research_tool_search.py::test_local_quota_refusal_leaves_the_operation_retriable
2 failed, 8 deselected, 1 warning in 60.52s (0:01:00)
```

Both fail, and the 60 s is itself the evidence: the row is left at `sent`, so each retry sits out
the full 30 s `_wait_for_result` poll before answering 409. The tests pin the release, not the
status line. Restored afterwards.

Blast radius. The only production caller of either connector's search surface is this route:

```
$ grep -rn "search_tweets" --include="*.py" .
runtime/connectors/x_twitter.py:179:    def search_tweets(
tests/test_connectors_x_youtube.py:124:def test_x_search_tweets(artifact: str) -> None:
tests/test_connectors_x_youtube.py:141:    tweets = conn.search_tweets("AI agents", max_results=10)
```

The adjacent registry suite still passes:

```
$ ... -m pytest tests/test_tool_connector_registry.py -q
...................                                                      [100%]
19 passed in 0.55s
```

Lint:

```
$ ... -m ruff check runtime/connectors/x_twitter.py runtime/connectors/youtube.py tests/test_research_tool_search.py tests/test_connectors_x_youtube.py
All checks passed!
```

`ruff check interfaces/research/api/research_tool_search.py` reports one `I001` (organize
imports). It pre-exists at `HEAD` — I reproduced it on `git show HEAD:…` — and comes from the
`interfaces.research.api.account_memory_identity` import that `e040b19c8` placed between `fastapi`
and `fastapi.responses`. `--fix` would reorder lines that commit owns, so I left it.

## Not done, and why

- No existing test was weakened, skipped, xfailed or deleted. All 20 baseline tests still pass
  with their assertions as written. The 7 new tests are additive.
- No live round-trip against X or YouTube. `expansions=author_id` and `user.fields=username` are
  documented X v2 parameters and the acquisition sibling sets the same pair
  (`acquisition/twitter/api_client.py:209-210`), but this connector's docstring bar is
  "fixture-validated, live-unverified" and that is still where it stands. If X rejects those
  params, dropping them costs the handle and nothing else — the URL falls back to
  `https://x.com/i/status/<id>`, which is a valid permalink.
- No mypy run (memory records the mypy/ruff gate as parked on line-keyed reds).
- No whole-suite pytest run, per the brief.

## Unsure about

1. The duplicated parsers, discussed above. Layering versus DRY; I chose layering and said why.
2. `_release` deleting a `sent` row races a concurrent duplicate sitting in `_wait_for_result`:
   that waiter sees `row is None`, breaks, and answers 409. That is the pre-existing behaviour for
   a deleted claim and I did not change it, but a 403 now reaches it on a path it could not reach
   before. The retry after the 409 succeeds, so it degrades rather than strands.
3. `_clears_on_its_own` keys on `status_code == 429`. `XTwitterError` and `YouTubeError` both carry
   `status_code`; a future connector that does not will fall through to `unknown`, which is the
   safe direction but silently so.
