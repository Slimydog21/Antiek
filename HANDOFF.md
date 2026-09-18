# SWARM LANE: arXiv governor coverage + HTML-first ingestion — HANDOFF

Branch `swarm/arxiv-20260918`, commit `5246f09a8`. All three brief tasks done, plus
two things the brief did not anticipate that had to be fixed for the third one to
be safe. Every command below was actually run in this worktree and its output is
pasted verbatim.

Python used throughout: `/Users/slimydog/Antiek/platform/.venv/bin/python` (3.12),
run from this worktree root.

---

## Done-bar

### 1. `pytest tests/ -k "arxiv" -q` — GREEN

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/ -k "arxiv" -q
...
SKIPPED [1] tests/regression/test_agent_failures.py:200: arxiv-missing-ssl-env is an open GAP; not enforced here
SKIPPED [1] tests/resilience/test_chaos_suite.py:145: replay: stub — needs an env-scrub scenario over the live SSL fetch path (SSL_CERT_FILE absence); no deterministic injector for a TLS/env fault yet
467 passed, 4 skipped, 9555 deselected, 9 warnings in 68.57s (0:01:08)
```

**This selection was NOT green before this lane.** At HEAD (`f0638da3a`), with none
of my changes applied, the same command gives 8 failures:

```
$ git checkout -- acquisition/arxiv/adapter.py tests/test_arxiv_ingest.py tests/test_arxiv_html_ingest.py
$ /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/ -k "arxiv" -q -p no:randomly
FAILED tests/test_arxiv_html_ingest.py::test_html_absent_falls_back_to_pdf - ...
FAILED tests/test_arxiv_html_ingest.py::test_html_absent_uses_injected_fetch_pdf
FAILED tests/test_arxiv_html_ingest.py::test_prefer_html_false_never_calls_fetch_html
FAILED tests/test_arxiv_ingest.py::test_cc_by_paper_ingests_servable - Attrib...
FAILED tests/test_arxiv_ingest.py::test_default_terms_paper_ingests_gated - A...
FAILED tests/test_arxiv_ingest.py::test_missing_license_paper_ingests_gated
FAILED tests/test_arxiv_ingest.py::test_ingest_persists_basis_in_substrate - ...
FAILED tests/test_arxiv_ingest.py::test_injected_fetch_callable_is_used - Att...
8 failed, 446 passed, 4 skipped, 9548 deselected, 9 warnings in 90.91s (0:01:30)
```

All eight died on the same pre-existing defect: `_StubEmbedder` in those two test
files has no `.dimension`, which `substrate/graph/embedding_meta.py::_identity`
has read since commit `8f5096795` ("pin chunk embedding provider metadata"). The
stubs were never updated, so every PDF-leg assertion in both files had been dead
on `AttributeError`. Every other stub embedder in `tests/` already carries
`dimension = 16` (`tests/test_arxiv_index.py:31`, `tests/test_arxiv_audit.py:338`,
`tests/test_merge_staging.py:90`, `tests/test_max_context_pack.py:31`,
`tests/test_pdf_storage_tiering.py:57`). I added the same two lines to the two
stale stubs. That is a fixture repair, not a test weakening: it turns eight dead
tests back into eight asserting tests. Baseline 446 passed → 467 passed = +8
repaired, +13 new.

### 2. `python3 tools/lint/rate_governor_check.py` — exit 0 with `tools/` in scope

```
$ /Users/slimydog/Antiek/platform/.venv/bin/python tools/lint/rate_governor_check.py
OK: no ungoverned raw external HTTP egress in the acquisition tree, substrate/graph/, or the arXiv-reaching tools/ scripts, outside the host-based rate-governor seam.
EXIT=0
```

Green here is worth nothing unless the scanner really reads those files, so there
is a non-vacuity test (`test_the_real_arxiv_reaching_tools_files_are_actually_in_scope`)
and this is the actual in-scope set it now reads:

```
IN SCOPE (16):
   tools/arxiv_census.py
   tools/arxiv_oai_sync.py
   tools/arxiv_takedown.py
   tools/arxiv_verify.py
   tools/backfill_book_reader_html.py
   tools/backfill_cc0_remap.py
   tools/gepa/__init__.py
   tools/ingest_arxiv.py
   tools/ingest_open_access.py
   tools/ingest_public_domain.py
   tools/lint/rate_governor_check.py
   tools/lint/register_check.py
   tools/lint/serve_invariants_check.py
   tools/lint/source_gate.py
   tools/run_corpus_ingest.py
   tools/source_census.py
OUT OF SCOPE: 130 files
```

### 3. New test proving `_fetch_paper_pdf` uses a governed client

`tests/tools/test_run_corpus_ingest_governed_pdf.py`, four tests: the factory is
consulted AND the client it returns carries both per-hop hooks; an arXiv-host
pdf_url writes the shared throttle state; a non-arXiv pdf_url does NOT (no false
governance); a 429 from the arXiv hop arms the ban sentinel.

Teeth check — the same four tests against the OLD bare-`httpx.Client` code:

```
FAILED tests/tools/test_run_corpus_ingest_governed_pdf.py::test_fetch_paper_pdf_uses_a_governed_client
FAILED tests/tools/test_run_corpus_ingest_governed_pdf.py::test_fetch_paper_pdf_governs_an_arxiv_url_through_the_shared_state
FAILED tests/tools/test_run_corpus_ingest_governed_pdf.py::test_fetch_paper_pdf_does_not_falsely_govern_a_non_arxiv_url
FAILED tests/tools/test_run_corpus_ingest_governed_pdf.py::test_fetch_paper_pdf_records_a_429_from_an_arxiv_hop_in_the_ban_sentinel
4 failed in 31.88s
```

### 4. New tests proving `prefer_html=True` is the default AND a 429 does not fall back

In `tests/test_arxiv_html_ingest.py`:

- `test_prefer_html_defaults_to_true` — asserts the signature default via
  `inspect.signature`, and behaviorally that the stored `raw_text` is the
  sanitized HTML, not the PDF text.
- `test_html_leg_429_raises_and_never_falls_back_to_pdf` — drives the REAL
  `html_fetch.fetch_html` over an `httpx.MockTransport` returning 429; asserts
  `ArxivBanned` propagates, the HTML hop went out, the PDF fetcher was never
  called, and the ban sentinel is armed.
- `test_html_leg_429_does_not_fall_back_even_with_pdf_bytes_in_hand` — the same
  rule when ingesting the PDF would have cost nothing.
- `test_pdf_bytes_in_hand_never_triggers_a_default_html_fetch` — the guard rail
  described below.

### 5. No network calls in tests

Proven, not asserted. I ran the whole selection under a pytest plugin that raises
on any DNS lookup or TCP connect to a non-loopback host
(`scratchpad/netguard/netblock.py`, patches `socket.getaddrinfo` /
`socket.create_connection`):

```
$ PYTHONPATH=.../scratchpad/netguard /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/ -k "arxiv" -q -p netblock
467 passed, 4 skipped, 9553 deselected, 8 warnings in 61.49s (0:01:01)
```

---

## What changed, and why

### Task 1 — `tools/run_corpus_ingest.py::_fetch_paper_pdf`

Builds its client via `arxiv_governed_client(follow_redirects=True, timeout=30.0)`
instead of a bare `httpx.Client`. `rec.pdf_url` comes from CORE / Semantic
Scholar / bioRxiv / PLOS metadata and every one of those mirrors arXiv, so the
URL can be `https://arxiv.org/pdf/<id>` on the initial hop or after a redirect.
The aggregator's own `SourceThrottle` still runs; the two are independent layers.

### Task 2 — `tools/arxiv_verify.py::_check_endpoint_health`

Routed through `govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())`,
catching `ArxivBanned` and reporting `passed=False,
detail="ban sentinel armed, endpoint not probed"`. User-Agent is now
`acquisition.arxiv.client.default_user_agent()`.

**I did not follow the brief's literal instruction here, and the difference
matters.** The brief said to move the lines into
`def _send(): return urllib.request.urlopen(req, timeout=timeout)`. That does not
work: `ArxivThrottle.request` reads `resp.status_code` and `resp.headers`
(`acquisition/arxiv/throttle.py:255-257`), and a `http.client.HTTPResponse`
exposes `.status`/`.headers`, not `.status_code`. Worse, `urlopen` **raises**
`HTTPError` on a 429 rather than returning it, so a 429 would propagate out of
`throttle.request` before `note_response` ever ran and the ban sentinel would
stay disarmed — the exact failure the change exists to fix. `_send` therefore
converts both outcomes into a small frozen `_UrlopenResult` carrying
`status_code`/`headers`/`body`/`error`, and the `HTTPError` is re-raised after
the governor has seen the status. `test_endpoint_health_429_arms_the_ban_sentinel`
is the regression guard for that.

I also added a `_CANONICAL_THROTTLE` reset to the autouse fixture in
`tests/tools/test_arxiv_verify.py`. `ArxivThrottle` binds its state path once at
construction (`throttle.py:156`) and `canonical_arxiv_throttle()` caches the
instance, so without the reset the first test to build it would pin every later
test to one `tmp_path` and leak the 3-second spacing across tests.

### Task 3 — `prefer_html: bool = True`

Plus two changes the brief did not call for, both load-bearing.

**(a) The brief's stated mechanism for the bulk call site was wrong, but its
warning was right.** The brief says the pre-fetched `pdf_bytes` at
`run_corpus_ingest.py:409` "short-circuits the fetch", so HTML-first "silently
stays PDF-only". It does not: the `if prefer_html:` block sits *before* the
`if pdf_bytes is None:` check, so the HTML leg ran either way. The real damage
was different and still real — the eager pre-fetch spent a full arXiv request
(≥3s of the host-global budget) on a body the HTML leg then discarded, and
`_assert_pdf_body_quality` could reject the paper on PDF extraction quality
*before* the higher-fidelity HTML rendering was ever attempted. The thunk now
passes a lazy `fetch_pdf=_fetch_pdf_checked` callable, so the PDF is fetched only
when the HTML leg returns `None`, and the quality gate still guards every PDF
body that reaches ingest. Proven, with teeth, in
`tests/tools/test_run_corpus_ingest_html_first.py` — reverting just the call site
(adapter default still True) reds it:

```
E       AssertionError: fetch_bulk_pdf was called although an HTML rendering was available — the PDF pre-fetch is still eager and the HTML leg is bypassed
FAILED tests/tools/test_run_corpus_ingest_html_first.py::test_bulk_ingest_thunk_takes_the_html_leg_and_never_fetches_the_pdf
1 failed, 1 passed in 0.41s
```

**(b) A bare default flip turns offline-shaped calls into live arXiv egress.**
This is the thing I most want the next reader to check. With
`prefer_html=True` and nothing else, any caller that supplies `pdf_bytes` or only
`fetch_pdf` reaches `_default_fetch_html`, which is a real network fetcher
(`adapter.py:398-412`). I proved the reach offline, with a tripwire that raises
before any socket opens:

```
$ .venv/bin/python  # ingest_paper_with_rights(paper, fetch_pdf=..., db_path=...)
RESULT: TRIPWIRE: default arxiv.org/html fetcher reached
default html fetcher consulted for: ['2402.00006']
```

Before I noticed this, a `-k arxiv` run with the naked default flip produced
`KeyError: 'id'` in `test_injected_fetch_callable_is_used` (the injected
`fetch_pdf` was never called) and `DID NOT RAISE` in `test_empty_pdf_raises` —
both only explicable by the default HTML fetcher returning real content for those
arXiv ids. **Live requests to arxiv.org went out from a unit-test run because of
my change.** No ban resulted: `~/.antiek/arxiv_throttle.json` showed
`banned_until` unchanged at `1780506878.593083` (in the past) throughout, and the
governor did space the requests, which is why that run took 114s. I am flagging
it rather than quietly moving on, because this box has been IP-banned before and
the next person to flip a fetch default should know this failure mode exists.

The fix is in the adapter: the DEFAULT HTML fetcher is withheld when the caller
handed in `pdf_bytes` and wired no `fetch_html`. An in-hand body is the caller
saying "this is the body"; going to arxiv.org to replace it is a surprise egress
that buys nothing. Passing `fetch_html` alongside `pdf_bytes` opts back in, and a
caller that passes no body at all — both production call sites — gets HTML-first,
which is the point.

### The lint scope decision (the brief asked me to choose and say why)

The brief predicted `tools/arxiv_verify.py:134` plus maybe `krea_smoke.py:221`
and `auth_probe.py:90`. The real blanket-`tools/` result was larger — 16 sites
across 9 files:

```
tools/arxiv_verify.py:134
tools/auth_probe.py:90
tools/demo/run_cold_question.py:79
tools/demo/run_cold_question.py:92
tools/demo/run_cold_question.py:105
tools/krea_smoke.py:221
tools/posthog/sync_dashboards.py:64
tools/posthog/verify_capture.py:82
tools/posthog/verify_capture.py:117
tools/prod_parity/check.py:98
tools/reachability/probes/usability_keystone.py:596
tools/reachability/probes/usability_keystone.py:625
tools/reachability/probes/usability_keystone.py:659
tools/reachability/probes/usability_keystone.py:671
tools/reachability/probes/usability_keystone.py:796
tools/run_corpus_ingest.py:929
```

I read every one. Fourteen of the sixteen, across seven files, reach hosts fixed
by configuration — PostHog, Krea, `api.antiek.ai/health`, and a localhost client
to the Antiek API — and cannot resolve to arXiv. Six of those seven files are
outside this lane's scope, so wrapping them was not available to me anyway; but I
would not have wrapped them regardless, because a `govern_if_arxiv` call that is
a no-op for its host teaches the next reader that the governor is paperwork.

So: **narrower predicate, not blanket suppression**, as the brief's own preference
ordering suggests. A `tools/` file is scanned when it either names arXiv anywhere
in its source or imports the `acquisition` package. The second clause is the
important one — it is what catches `_fetch_paper_pdf`, whose ungoverned fetch
names no arXiv host anywhere near the egress, and it generalizes: a script that
reaches paper records through `acquisition.papers` / `acquisition.openaccess`
fetches URLs it did not choose, from aggregators that all mirror arXiv.

Measured separation on the real tree: the two arXiv-reaching files score
`arxiv_hits=26/83, acq_import=1/28`; all seven others score `arxiv_hits=0,
acq_import=0`. There is no borderline case to argue about.

**The predicate's gap, stated plainly:** it is lexical. A `tools/` script that
hand-rolls its own OpenAlex or CORE query with plain `httpx`, never imports
`acquisition` and never writes the word arXiv would fetch an arXiv-mirrored PDF
unflagged. Closing that needs the check at the fetch boundary, which is what
`govern_if_arxiv` and the per-hop hooks already are; the scanner is the backstop
that makes forgetting the boundary loud, not the guarantee itself. An unreadable
file fails closed (scanned), and the predicate only ever adds files — nothing in
`acquisition/` or `substrate/graph/` can escape through it.

---

## Existing tests I changed, and exactly how

I deleted, skipped and xfailed nothing. Four existing tests changed; all
assertions in all four are unchanged.

1. **`tests/test_arxiv_html_ingest.py::test_prefer_html_false_never_calls_fetch_html`**
   — relied on the default being False and passed no `prefer_html`. Now passes
   `prefer_html=False` explicitly. The opt-out path it guards still exists and is
   still covered; the new default gets a stronger, explicit assertion in
   `test_prefer_html_defaults_to_true`.

2. **`tests/test_arxiv_ingest.py::test_injected_fetch_callable_is_used`** — now
   also injects `fetch_html=lambda _id: None`. Its own docstring already promised
   "CI never hits the network"; under HTML-first that promise was false. The
   injection restores the property the test claims.

3. **`tests/test_arxiv_ingest.py::test_cli_real_run_splits_servable_and_gated`**
   and **`::test_live_429_pdf_fetch_sets_sentinel_and_halts_batch`** — both
   monkeypatched `_default_fetch_pdf` but not `_default_fetch_html`, so the
   "real (offline) run" issued a live `arxiv.org/html` request per paper. Both
   now stub `_default_fetch_html` to `None` ("arXiv has no rendering for this
   paper"), routing them down the PDF leg every assertion is written against. The
   netguard run above is the proof this is now airtight.

4. **`tests/test_rate_governor.py::test_scanner_scope_is_the_acquisition_tree_not_tools`**
   — name and assertion byte-identical; only the docstring changed, because its
   stated reason ("`tools/` carries no arXiv egress") was the false claim this
   lane disproves. Its fixture names no arXiv host and imports no `acquisition`
   module, so it remains correctly out of scope under the new predicate.

5. Two `_StubEmbedder` fixtures gained `dimension = 16` — see done-bar 1.

---

## Lint and types: no new findings

```
$ .venv/bin/python -m ruff check <the 10 touched files>
Found 2 errors.
```
Both pre-existing: `SIM115` at `tests/test_arxiv_ingest.py:421` and `SIM102` at
`tools/lint/rate_governor_check.py:192`. Baseline on the same set at HEAD is also
`Found 2 errors.` (I introduced one `I001` and fixed it.)

```
$ .venv/bin/python -m mypy tools/arxiv_verify.py acquisition/arxiv/adapter.py tools/lint/rate_governor_check.py
# errors in MY files, after:
tools/lint/rate_governor_check.py:356: error: "AST" has no attribute "lineno"  [attr-defined]
tools/arxiv_verify.py:105: error: Missing type arguments for generic type "dict"  [type-arg]
# errors in MY files, at HEAD:
tools/lint/rate_governor_check.py:321: error: "AST" has no attribute "lineno"  [attr-defined]
tools/arxiv_verify.py:105: error: Missing type arguments for generic type "dict"  [type-arg]
```
Same two, line-shifted. No new mypy errors. (Repo-wide mypy reports 250 errors in
53 files; that is the pre-existing parked state, not this lane.)

---

## What I did NOT do

- **Did not touch the other six `tools/` files with raw egress** (`auth_probe`,
  `krea_smoke`, `posthog/*`, `prod_parity/check`, `demo/run_cold_question`,
  `reachability/probes/usability_keystone`). Out of this lane's scope, and the
  narrower predicate means they do not need changing. If a later lane decides
  every external fetcher everywhere should route through `govern_if_arxiv` for
  uniformity, that is a coherent position — it is what `public_domain.py` does —
  but it is a different decision from this one.
- **Did not extend `assess_extraction_quality` to HTML bodies.** The HTML leg is
  not ungated (`html_fetch` rejects an absent/stub rendering under
  `MIN_HTML_CHARS`, and the body is allowlist-sanitized), but the OCR-garbage
  floor that guards PDF extraction does not run on it. I wrote that gap into the
  `_arxiv_bulk_candidates` docstring rather than leaving it implied.
- **Did not fix the `SIM115` / `SIM102` ruff findings or the two mypy errors.**
  Pre-existing, unrelated, and touching them would blur the diff.
- **Did not run the full pytest suite.** Per the brief.

---

## Things I am not certain about

1. **The `pdf_bytes`-withholds-the-default-HTML-fetcher rule is a judgment call.**
   It is the minimum that makes the HTML-first default safe without editing
   call sites I do not own, and I think "an injected body is not a request to go
   find a different one" is the right line. But it is a conditional default, and
   a reader skimming the signature will see `prefer_html: bool = True` and not
   the caveat. If a reviewer prefers the unconditional default, the alternative
   is to inject `fetch_html` stubs at roughly four more existing test call sites
   and accept that `ingest_paper_with_rights(paper, pdf_bytes=...)` performs
   network I/O. I did not take that path because it makes every future
   fixture-bytes caller a live-egress caller by accident.

2. **The lint scanner never *recognizes* `arxiv_governed_client` as governed — it
   fails to see it at all.** `_ctor_is_http_client` only matches
   `httpx.Client(...)`-shaped constructors, so a name bound to
   `arxiv_governed_client(...)` is not a client receiver and its `.get` is never
   examined. That is how every existing caller in `acquisition/papers/*` passes
   today, and it is why my `_fetch_paper_pdf` change passes. It works, but it is
   luck rather than design, and the same blind spot would hide a genuinely
   ungoverned fetcher behind any helper that wraps `httpx.Client`. Worth a
   follow-up; out of scope here.

3. **I could not verify the 2.4x HTML-vs-PDF figure myself.** I took it from the
   brief (6,635 words against 2,802) and cited it as the skill's reference
   measurement in the adapter docstring rather than as something I measured. The
   direction of the effect is not in doubt; the exact multiple is the brief's.

4. **`tools/gepa/__init__.py` is now in the lint's scope** because it mentions
   arXiv. It has no egress today, so it is silent. Harmless, but it is the kind
   of incidental match a stricter predicate would exclude.
