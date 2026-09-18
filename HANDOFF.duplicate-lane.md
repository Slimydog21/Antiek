# This lane was dispatched twice — record of the second engine (PID 8695)

Written 2026-09-18 20:24 by the second of two engines started on this lane with
the same brief and the same working directory. **I did not write this lane's
fix.** `HANDOFF.md` is the report of the engine that did (PID 3678); read it
first. This file exists so the operator can see the duplicate dispatch, and so
the verification below is attributable to a process rather than to nobody.

## The collision, with evidence

Two `claude -p` processes were started with the identical prompt ("Read
SWARM_BRIEF.md in this directory and execute it completely, end to end…") and
`lsof` puts both of their working directories in this worktree:

```
$ ps -o pid,lstart,etime -p 3678 -p 8695
 3678 Fri Sep 18 20:07:15 2026       14:38
 8695 Fri Sep 18 20:11:53 2026       10:00

$ lsof -a -p 3678 -d cwd | tail -1
2.1.276 3678 slimydog cwd DIR 1,14 1312 571869579 /private/tmp/claude-501/-Users-slimydog/c35b7db9-c0ac-456c-a6b1-1d23a11ecc3b/scratchpad/swarm/connectors
$ lsof -a -p 8695 -d cwd | tail -1
2.1.277 8695 slimydog cwd DIR 1,14 1312 571869579 /private/tmp/claude-501/-Users-slimydog/c35b7db9-c0ac-456c-a6b1-1d23a11ecc3b/scratchpad/swarm/connectors
```

I am 8695 — my shell's parent is 8695. I started 4m38s after 3678.

The worktree's git registration was also renamed underneath us mid-session. My
`.git` named `.../worktrees/connectors1`; at 20:17:59 every git command failed
with `fatal: not a git repository: .../worktrees/connectors1`, the file was
rewritten at 20:19, and git worked again after that against
`.../worktrees/connectors`. The other engine's `HANDOFF.md` says it did that
repoint; I observed only the before and after. Only `connectors` exists now:

```
$ ls -d /Users/slimydog/Antiek/platform/.git/worktrees/connectors*
/Users/slimydog/Antiek/platform/.git/worktrees/connectors
```

Consequence for attribution: the in-scope files were rewritten while I was
reading them — `tests/test_research_tool_search.py` at 20:15:15 (182 lines when
I first read it, 426 at the end), `x_twitter.py` at 20:20:52, `youtube.py` at
20:21:21, `research_tool_search.py` at 20:21:28. I made exactly one edit to a
shared file before I understood what was happening (a module-docstring paragraph
in `runtime/connectors/youtube.py`) and reverted it two minutes later. It is not
in the commit, and the other engine independently flagged it as a paragraph it
could not account for:

```
$ git show HEAD:runtime/connectors/youtube.py | grep -c "ROWS, NOT ENVELOPES"
0
```

## What I did instead: verify the committed revision

The commit is `b5b16ea03` (20:23:05). The committed blobs hash-match the
revision I tested, so the results below are of the committed artifact and not of
a working-tree intermediate:

```
$ shasum -a 256 interfaces/research/api/research_tool_search.py runtime/connectors/x_twitter.py runtime/connectors/youtube.py
fdb8c31340e661a661b2e706d5aa8e98e2eaf24707d2cb193eee5447a9bfac3f  interfaces/research/api/research_tool_search.py
08f7d073654fc9e39d06b66492180f8b57fd81d805c0d40fe8eb4b5815271354  runtime/connectors/x_twitter.py
bcb4e40567decc1253b22031a0afba3868c8f2ed0bca4d7574fc64ec30d58540  runtime/connectors/youtube.py
```

### Done-bar 1

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q -p no:cacheprovider
24 passed, 1 warning in 0.71s
```

### Done-bar 5 — no live network

I did not take this on trust. A pytest plugin blocks `socket.socket.connect`,
`connect_ex`, `create_connection` and `getaddrinfo` for the session, and the
suite still passes; a sanity check confirms the blocker actually fires:

```
$ PYTHONPATH=/tmp/mutants … -m pytest tests/test_research_tool_search.py tests/test_connectors_x_youtube.py -q -p mut_no_network
24 passed, 1 warning in 0.95s

$ PYTHONPATH=/tmp/mutants … -c "from mut_no_network import pytest_configure; … socket.create_connection(('example.com', 443), timeout=1)"
blocked as intended: test attempted a live network connection
```

### Done-bar 2/3/4 — do the tests have teeth?

The done-bar asks for tests that fail when the bug returns. I checked by
mutating the production behavior from a pytest plugin that patches the imported
module at configure time, so no shared file was touched:

```
$ PYTHONPATH=/tmp/mutants … -p mut_rename      # del XTwitterConnector.search_tweets
FAILED tests/test_research_tool_search.py::test_x_search_returns_candidates_from_a_real_connector
FAILED tests/test_research_tool_search.py::test_x_rate_limit_releases_the_operation_id
2 failed, 8 passed

$ PYTHONPATH=/tmp/mutants … -p mut_raw_items   # search() returns the raw items envelope again
FAILED tests/test_research_tool_search.py::test_youtube_search_spends_quota_and_returns_candidates
FAILED tests/test_research_tool_search.py::test_vendor_quota_403_does_not_poison_the_operation_id
2 failed, 8 passed

$ PYTHONPATH=/tmp/mutants … -p mut_no_release  # journal goes back to terminal 'unknown'
FAILED tests/test_research_tool_search.py::test_vendor_quota_403_does_not_poison_the_operation_id
FAILED tests/test_research_tool_search.py::test_x_rate_limit_releases_the_operation_id
2 failed, 8 passed
```

Each mutation fails the tests that name that behavior, and only those.

### Before and after, on instruments written before the fix

The strongest check is a set of probe scripts I wrote against the broken tree at
20:1x, driving the real connectors over `MockTransport` through the real route,
then re-run unchanged after the commit. Pre-fix they recorded:

- YouTube: `HTTP 200` with `"candidates": []` — quota spent, nothing returned.
- X: `AttributeError: 'XTwitterConnector' object has no attribute 'recent_search'`.
- `_x` and `_youtube` over the connectors' actual return values: `[]` and `[]`.
- Vendor 403 then a PT-day reset: `503`, then `409` "operation outcome is
  unresolved"; journal row left in state `unknown`.

The same probes against `b5b16ea03`:

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python /tmp/verify_connectors.py
=== youtube: HTTP 200
{"operation_id": "probe_youtube_0000000001", "vendor": "youtube", "status": "completed",
 "candidates": [
   {"external_id": "dQw4w9WgXcQ", "title_or_text": "Solid-state battery manufacturing, explained",
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "published_at": "2026-08-12T15:04:05Z",
    "author": "Materials Weekly"},
   {"external_id": "UCabc", "title_or_text": "Battery Lab",
    "url": "https://www.youtube.com/channel/UCabc", "published_at": "2026-07-01T00:00:00Z",
    "author": "Battery Lab"}]}
=== x: HTTP 200
{"operation_id": "probe_x_0000000001", "vendor": "x", "status": "completed",
 "candidates": [
   {"external_id": "1800000000000000001", "title_or_text": "New reporting on battery recycling economics.",
    "url": "https://x.com/batterybeat/status/1800000000000000001",
    "published_at": "2026-09-01T12:00:00.000Z", "author": "batterybeat"}]}

$ /Users/slimydog/Antiek/platform/.venv/bin/python /tmp/verify_403.py
attempt 1 (vendor 403 quotaExceeded): 429 {'detail': 'tool quota is exhausted'}
attempt 2 (after quota reset, same operation_id): 200 {'operation_id': 'op_quota_reset_00000001',
  'vendor': 'youtube', 'status': 'completed', 'candidates': [{'external_id': 'v1', …}]}
journal row: [('owner-a', 'op_quota_reset_00000001', 'completed')]
```

The 403 row is the property the brief asks about: a refusal that clears on its
own answers 429, the operation_id survives it, and the same id completes after
the reset.

## What I did not do

- Did not author the fix, any of the four tests, or `HANDOFF.md`.
- Did not run the full suite, per the brief.
- Did not verify against the live vendors. Every result above is `MockTransport`.
- Did not otherwise touch `apps/reading/*` or the untracked
  `runtime/byok/credentials.enc.lock`.

## The commit I made, and the one I unwound

PID 3678 exited around 20:24, so I committed this file and `HANDOFF.md` as
documentation only. My first attempt at that commit (`0f94af54f`) was wrong: the
worktree's index already held three **staged** changes belonging to a parallel
stream, and a plain `git commit` takes the whole index, so it carried another
lane's work alongside my own. I unwound it with `git reset --soft HEAD~1` and
re-committed the two paths only. The stray commit is dangling at `0f94af54f`
(`git reflog`).

No file content changed in any of this — the parallel stream's files are
byte-identical to how I found them, and its staged state is back exactly as it
was:

```
$ git reset --soft HEAD~1 && git status --short
A  HANDOFF.duplicate-lane.md
A  HANDOFF.md
MM apps/reading/.env.example
MM apps/reading/src/lib/api.ts
D  apps/reading/src/lib/apiBase.test.ts
?? SWARM_BRIEF.md
?? apps/reading/src/lib/apiBase.test.ts
```

Whose work that is, I do not know. `apps/reading/*` is outside this lane's scope
and outside mine.

## Uncertainties

- Whether the double dispatch was intended. If it was a retry because the first
  engine looked stalled, note that it was healthy throughout — its edits landed
  steadily from 20:15 to 20:23.
- My verification covers `b5b16ea03` at 20:22–20:23. PID 3678 was still running
  when I wrote this; if it commits again, re-run the commands above against the
  new HEAD.
- `_wait_for_result`'s 409 for a duplicate that arrives while the original is in
  flight is unchanged and unverified by me. The other engine flags the same edge
  in its "What I did not do".
