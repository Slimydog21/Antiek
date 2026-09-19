# SWARM LANE: arXiv governor coverage + HTML-first ingestion

The operator asked to "verify arxiv is clean and follows the arxiv skill". Three
concrete defects were found by grounding against origin/main. Fix all three.

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
tools/run_corpus_ingest.py, tools/arxiv_verify.py, acquisition/arxiv/adapter.py,
tools/lint/rate_governor_check.py, and their tests.

## Task 1 (highest severity) — an ungoverned arXiv egress on a live path
`tools/run_corpus_ingest.py:913-936` `_fetch_paper_pdf` builds a bare
`httpx.Client(follow_redirects=True)` at :925 and calls `c.get(rec.pdf_url, ...)`
at :929 with no `govern_if_arxiv`. That is the exact regression class the rate
governor exists to prevent, and it sits in `tools/`, which the CI scanner does
not look at. arXiv bans by IP, so one ungoverned loop bans the whole host.

Change `_fetch_paper_pdf` to build its client via
`acquisition.arxiv.rate_governor.arxiv_governed_client(follow_redirects=True, timeout=30.0)`
so the per-hop request/response hooks govern any arXiv initial-or-redirect hop.

Then extend `tools/lint/rate_governor_check.py:119` to
`_EGRESS_SCAN_DIRS = ("acquisition/", "substrate/graph/", "tools/")` and delete the
now-false "tools/ carries no arXiv egress" justification at :44-46.

Running `python3 tools/lint/rate_governor_check.py` should then RED on
tools/arxiv_verify.py:134 (Task 2 fixes it) and may red on tools/krea_smoke.py:221
and tools/auth_probe.py:90 — investigate those two: if they cannot reach an arXiv
host, the scanner needs a narrower predicate rather than a blanket suppression.
Say which you chose and why.

## Task 2 — the verifier is itself the only ungoverned arXiv egress
`tools/arxiv_verify.py:129-134` issues a bare `urllib.request.urlopen` against
`{base_url}?verb=Identify` where base_url defaults to `https://oaipmh.arxiv.org/oai`
— the same host production harvests. It never consults the ban sentinel.

Move lines 129-135 into a `def _send(): return urllib.request.urlopen(req, timeout=timeout)`
closure and call it through `govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())`
from `acquisition.arxiv.rate_governor`. Catch `ArxivBanned` and report
`passed=False, detail="ban sentinel armed, endpoint not probed"` rather than
egressing. Also change the User-Agent at :131 to
`acquisition.arxiv.client.default_user_agent()` so the contact address is carried.

## Task 3 — HTML-first is dead code, and it is the skill's biggest measured win
The operator's arxiv skill measured the same paper at 6,635 words via arXiv's HTML
rendering against 2,802 via PDF — a 2.4x loss of body text, plus loss of math,
tables and two-column reading order. `acquisition/arxiv/adapter.py:675` defaults
`prefer_html: bool = False` and no non-test caller flips it.

Change :675 to `prefer_html: bool = True`. Lines :715-733 already fall through to
PDF when `fetch_html` returns None, so papers without an HTML rendering still work.
CAREFUL: `tools/run_corpus_ingest.py:409` pre-fetches `pdf_bytes = fetch_bulk_pdf(...)`
and passes it in, which short-circuits the fetch. HTML-first there needs that
pre-fetch moved to AFTER the HTML attempt, or it silently stays PDF-only. Verify
that specific call site actually takes the HTML path after your change, and show it.

Absolute rule: the HTML leg must NEVER fall back to PDF on a 429. A 429 means the
ban sentinel arms and the call fails; it does not mean "try the heavier endpoint".

## Done-bar (mechanical, all must pass)
1. `.venv/bin/python -m pytest tests/ -k "arxiv" -q` — all green.
2. `python3 tools/lint/rate_governor_check.py` — exits 0 with tools/ in scope.
3. A NEW test proving `_fetch_paper_pdf` uses a governed client (assert the
   client's event hooks, or monkeypatch the governor and assert it was consulted).
4. A NEW test proving `prefer_html=True` is the default AND that a 429 on the HTML
   leg raises rather than falling back to PDF.
5. No network calls in tests. arXiv is rate-limited and previously IP-banned this host.
