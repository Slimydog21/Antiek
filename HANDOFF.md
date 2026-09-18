# Swarm lane: connected BYO tools — HANDOFF

Branch `swarm/connectors-20260918`, worktree
`/private/tmp/claude-501/.../scratchpad/swarm/connectors`.

All three tasks are fixed and pinned by tests. Four new regression tests, all of
which fail on the pre-fix tree in the exact way the brief describes (output
pasted below). One finding contradicts the brief and is called out in
"Disagreements with the brief".

## What changed, and why

### The three bugs share one root cause

`interfaces/research/api/research_tool_search.py` was written against the
**acquisition-lane** connectors — its `_youtube` mapper reads attributes
(`video_id`, `channel_title`) that belong to
`acquisition.youtube.data_api.YouTubeSearchResult`, and its `except` tuples named
`acquisition` exception classes. But `registry.resolve_tool_connection` resolves
the **runtime BYO** connectors for the only two vendors the route accepts
(`youtube`, `x`). Every one of the three reported failures is a symptom of that
seam:

- **Task 1** — the route called `connector.recent_search(...)`; the resolved
  `XTwitterConnector` has no such method (`AttributeError` on every X search).
- **Task 2** — `_youtube` destructured `YouTubeSearchResult` attributes, while
  `runtime.connectors.youtube.YouTubeDataConnector.search` returned the vendor's
  raw `items` dicts. Attribute access on a dict yields the `getattr` default, so
  every row was skipped: 100 quota units spent, `[]` returned, no error.
- **Task 3** — the quota clause was **mis-typed in the literal sense**: it caught
  `YouTubeQuotaExhausted` imported from `acquisition.youtube.data_api`, but the
  class actually raised is `runtime.connectors.youtube.YouTubeQuotaExhausted`
  (`runtime/connectors/youtube.py:187`) — a different class object. No real 403
  ever entered that clause; it fell through to the generic branch, which calls
  `_unknown()` and writes the terminal `unknown` state, so `_claim` answers 409
  "operation outcome is unresolved" for that `operation_id` forever, quota reset
  or not. `grep` confirms the acquisition class is raised nowhere in `runtime/`
  or `interfaces/`.

The fix therefore reconciles the seam rather than patching three symptoms: each
runtime connector now returns the record its acquisition-lane sibling returns for
the same endpoint, so the route's mappers (already correct for those records) and
its exception handling speak the same language as the connectors the registry
resolves.

### `runtime/connectors/x_twitter.py` — `search_tweets()` returns tweet records

Returns the flattened record `parse_search_response` produces (`tweet_id`,
`text`, `author_handle`, `created_at`) instead of the raw `data` objects, and
requests `expansions=author_id` + `user.fields=username` so the handle exists
(this mirrors `acquisition/twitter/api_client._paged` for the same endpoint). The
parser is imported inside the method, not at module scope, so importing this
connector does not drag in the acquisition adapter's chunking/embedding/substrate
import graph.

### `runtime/connectors/youtube.py` — `search()` returns parsed hits

Delegates to `acquisition.youtube.data_api.parse_search_response` and returns
`list[YouTubeSearchResult]`, matching `YouTubeConnector.search` on the
acquisition side. The vendor-envelope knowledge stays in the one parser that owns
it; the route's `_youtube` mapper is unchanged because it was already correct for
this record.

### `interfaces/research/api/research_tool_search.py`

- `:265` (`recent_search` → `search_tweets`) — Task 1.
- The `except` tuples now name the classes the resolved connectors actually
  raise (`runtime.connectors.x_twitter.XTwitterError`,
  `runtime.connectors.youtube.YouTubeError`/`YouTubeQuotaExhausted`) plus
  `runtime.connectors.rate_governor.VendorBanned`. The acquisition-lane imports
  are gone; their classes are `RuntimeError` subclasses and stay caught by the
  fallback, so no error path lost coverage.
- `_release()` now also clears `sent` rows, and the quota / rate-window branches
  call it instead of `_unknown()`. `_refusal_clears()` states the rule: a refusal
  the vendor documents as temporary (daily quota that resets, rate window that
  reopens, the governor's ban sentinel, any connector error carrying HTTP 429)
  releases the claim so the same `operation_id` can succeed later; anything
  ambiguous (transport error, unparseable body, a credential the vendor rejected)
  keeps the terminal `unknown` mark. Deleting the row is safe because the vendor
  refused the request outright — nothing was produced and nothing changed, so a
  later send is not a duplicate.

### Not changed

`apps/reading/src/modes/Sources/ConnectedToolSearch.tsx` and its API client
needed no edit: the UI consumes `candidates[{external_id, title_or_text, url,
published_at, author}]`, which is exactly what the route returns once the
connectors are fixed. Its retry identity (`pending.operationId` reused for a
same-query retry) is what made Task 3 user-visible: without the fix, hitting
Search again after a quota 403 returned 409 forever.

## Commands run, with real output

The done-bar writes the interpreter as `.venv/bin/python`; **this worktree has no
`.venv`** (`ls -d .venv` → `No such file or directory`), so every command below
was run from the worktree root with the absolute platform interpreter the brief
names. Verified that this resolves imports to *this* worktree, not the main
checkout: `/Users/slimydog/Antiek/platform/.venv/bin/python -c "import
interfaces.research.api.research_tool_search as m; print(m.__file__)"` →
`/private/tmp/claude-501/.../swarm/connectors/interfaces/research/api/research_tool_search.py`.

### Pre-fix: the new tests fail for the stated reasons

`tests/test_research_tool_search.py` was extended first, then run against the
untouched product code:

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py -q --tb=line
E   AttributeError: 'XTwitterConnector' object has no attribute 'recent_search'
.../interfaces/research/api/research_tool_search.py:265: AttributeError
E   AssertionError: assert [] == [{'external_i...30:00Z', ...}]
.../tests/test_research_tool_search.py:337: AssertionError
E   AssertionError: {"detail":"tool search is unavailable"}
.../tests/test_research_tool_search.py:376: AssertionError
E   AttributeError: 'XTwitterConnector' object has no attribute 'recent_search'
.../interfaces/research/api/research_tool_search.py:265: AttributeError
4 failed, 6 passed, 1 warning in 13.06s
```

Line 337 is the YouTube candidate assertion — `[]`, the silent-zero bug, after
the real connector had spent its 100 units. Line 376 is the first request of the
403 test: 503, not 429, which is the mis-typed clause routing the vendor 403 into
the generic `_unknown()` branch.

### Done-bar 1 — targeted suite green

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q
24 passed, 1 warning in 0.77s
```

(20 pre-existing tests, 4 added. `tests/test_connectors_x_youtube.py` was not
edited.)

### Done-bar 2 — the X test drives a real `XTwitterConnector` over MockTransport

`test_x_search_returns_candidates_from_a_real_connector` resolves through the
real registry (`connect_tool` → `resolve_tool_connection`, wrapped only to inject
`httpx.Client(transport=httpx.MockTransport(handler))` and a temp state dir), so
the registry's vendor→connector map and the connector's method surface are both
under test:

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py -q -k "real_connector or spends_quota or poison or releases_the_operation" -v
4 passed, 6 deselected, 1 warning in 0.45s
```

The X test asserts the full candidate list including the author handle and the
`https://x.com/<handle>/status/<id>` URL, the requested path, the query param,
that the bearer rides only the `Authorization` header, and that it is absent from
the URL.

### Done-bar 3 — a realistic YouTube response yields non-empty candidates

`test_youtube_search_spends_quota_and_returns_candidates` drives the real
`YouTubeDataConnector` with a recorded-shape Data API v3 `searchListResponse`
(a video hit and a channel hit), asserts both candidates with their `/watch?v=`
and `/channel/` URLs, and asserts
`state["connectors"][0].quota_remaining().remaining == 10_000 - 100` — the spend
and the rows are checked together, which is the property that was broken.

### Done-bar 4 — a vendor 403 does not poison the `operation_id`

`test_vendor_quota_403_does_not_poison_the_operation_id` sends a 403
`quotaExceeded` body, then retries the same `operation_id` twice: 429 (vendor
refusal, claim released), 429 again (local meter refusal, no second vendor send),
then 200 `completed` with one candidate once the meter is fresh (the reset). The
vendor handler has been called exactly twice at the end, so the second 429 really
did not spend a call.

Mutation check that this pins the release, not just the exception typing — with
the clause retyped correctly but `_release` reverted to `_unknown`:

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py -q --tb=line
E   AssertionError: {"detail":"operation outcome is unresolved"}
E   AssertionError: {"detail":"operation outcome is unresolved"}
2 failed, 8 passed, 1 warning in 0.79s
```

`test_x_rate_limit_releases_the_operation_id` covers the same rule for the other
vendor: X answers 429, the retry inside the governor's ban window raises
`VendorBanned` (refused before the send, claim released), and the same
`operation_id` succeeds once the window reopens.

### Done-bar 5 — no live network calls

The suite was re-run with every `AF_INET`/`AF_INET6` `socket.connect` replaced by
a raiser (unix sockets left alone) via `PYTHONPATH=/tmp` + `nonet_plugin.py`:

```
$ PYTHONPATH=/tmp /Users/slimydog/Antiek/platform/.venv/bin/python -c "import nonet_plugin, pytest, sys; sys.exit(pytest.main(['tests/test_research_tool_search.py','tests/test_connectors_x_youtube.py','-q']))"
24 passed, 1 warning in 0.88s
```

Every connector in both files is injected with `httpx.MockTransport`.

### Adjacent check

`tests/test_tool_connector_registry.py` (the other consumer of
`resolve_tool_connection`; it never calls `search*`) — `19 passed in 0.68s`.
`ruff check` on all four touched files — `All checks passed!`, and each file was
already lint-clean at HEAD, so no new lint was introduced.

## Disagreements with the brief

1. **Task 1 is not a one-line rename.** The brief states that `search_tweets`
   "returns the raw `data` list the `_x` mapper at research_tool_search.py:220-236
   already expects". It does not: raw X API v2 tweet objects carry `id` and
   `author_id`, while `_x` destructures `tweet_id` and `author_handle`. Renaming
   the method alone would have swapped a loud 500 for the same silent-zero bug
   Task 2 describes — X searches returning `[]` with the candidate list empty and
   no error. Fixing the connector's return shape (to the flattened record
   `acquisition.twitter.api_client` already returns for this endpoint) is what
   makes the mapper's expectation true rather than papering over it.

2. **Task 2's mismatch is on the connector side, not the mapper side.** I fixed
   the connector rather than teaching `_youtube` to read raw `items`, because the
   mapper's attribute access is already correct for the record both lanes' parsers
   produce, and because the route's exception handling had the same
   acquisition-vs-runtime confusion. Decoding the envelope in the route instead
   would have duplicated vendor-shape knowledge and permanently lost the X author
   handle (raw `data` has no username; only `includes.users` does).

3. **The 403 branch's "mis-typing" is literal.** See Task 3 above — the except
   clause named a class from the acquisition module that the resolved connector
   never raises. Worth knowing if a sibling lane greps for the same pattern
   elsewhere: any code that catches acquisition exception classes while holding a
   registry-resolved connector is catching nothing but the `RuntimeError`
   fallback.

## What I did not do

- **No live verification against either vendor.** The endpoint shapes remain
  fixture-validated and live-unverified, exactly as the modules' own banners
  claim. I added `expansions=author_id` and `user.fields=username` to the
  recent-search request, following `acquisition/twitter/api_client.py`'s use of
  the same pair on the same endpoint; if X rejects them on a real key, drop those
  two params — the rows survive and only the handle (and the URL's author
  segment, which falls back to `/i/status/<id>`) is lost.
- **No change to the connector contracts' other consumers** — there are none:
  `grep` shows `resolve_tool_connection`'s only production caller is this route,
  and `tests/test_tool_connector_registry.py` never calls `search*`. Flagging it
  anyway because the return shapes of `XTwitterConnector.search_tweets` and
  `YouTubeDataConnector.search` did change; a sibling lane that calls either
  expecting raw payloads would need to adapt.
- **Did not change the terminal classification for credential failures.** A 401,
  or a 403 that is not a rate/quota refusal, still burns the `operation_id`
  (`_unknown`). That is the pre-existing behavior for conditions the user must
  resolve, and the brief scoped the fix to refusals that clear on their own. If
  the operator wants a rejected credential to stay retriable too, it is a
  one-line addition to `_refusal_clears`.
- **Did not touch `_wait_for_result`'s 409** for a row released mid-wait (a
  concurrent duplicate of a request that then got rate-limited gets 409 rather
  than 429). Same outcome as before this change, so not a regression, but it is
  the one rough edge left in the journal's state machine.
- **Did not run the full suite** — per the brief, only the named files plus the
  adjacent registry test.

## Environment notes the operator should know

- **The worktree's git metadata was renamed under me mid-session.** `.git`
  pointed at `/Users/slimydog/Antiek/platform/.git/worktrees/connectors1`, which
  no longer exists; the live directory is `.../worktrees/connectors` (its
  `gitdir` file names this worktree, and its HEAD is `refs/heads/swarm/connectors-20260918`,
  so it is ours). Every git command was failing with "not a git repository"
  until I repointed the one-line `.git` file. The original content is backed up
  at `/tmp/gitfile-backup-connectors.txt`. If the orchestrator renames it again,
  this will need repeating.
- **A parallel stream landed `89729c44c`** ("fix(reading): resolve relative API
  paths against API_BASE in apiFetch") into this branch during the session, and
  left `apps/reading/.env.example`, `apps/reading/src/lib/api.ts` and
  `apps/reading/src/lib/apiBase.test.ts` dirty in the worktree, plus an untracked
  `runtime/byok/credentials.enc.lock`. None of that is mine; I verified the lock
  file is not produced by either done-bar test file (removed it, ran both, it did
  not reappear). My commit stages only the four files below.
- **A doc paragraph I did not write appeared in `runtime/connectors/youtube.py`**
  during the session ("ROWS, NOT ENVELOPES: ..."). It describes this change
  accurately, so I kept it rather than reverting it, but I cannot account for its
  author — flagging it so a reviewer does not attribute it to me.

---

## Addendum, appended by the second engine on this lane (not the author)

I wrote that paragraph, and I am not the author of anything else here. This lane
was dispatched twice: two engines with the identical prompt and this worktree as
their working directory (`lsof` on PIDs 3678 and 8695; I am 8695, started 4m38s
after 3678). The fix, the four tests, the commit `b5b16ea03` and the report
above are the other engine's work. I reverted my paragraph at 20:22 — it is not
in `HEAD` — and then did what a second engine can usefully do: independently
verified the committed revision without writing to any shared file.

That verification is in **`HANDOFF.duplicate-lane.md`** and it corroborates the
report above: the committed blobs hash-match the tested revision, the done-bar
is green (24 passed), the suite passes with every socket call blocked, three
out-of-worktree mutations show each new test fails when its fix is reverted, and
probes written against the broken tree now return populated candidates and a
retriable 429 where they previously returned `[]`, a 500, and a poisoned
`operation_id`.

Operator action: this lane was dispatched twice. Once the authoring engine had
exited I committed these two handoff documents and nothing else — the account of
that commit, and of one over-broad attempt I unwound, is in
`HANDOFF.duplicate-lane.md`.

