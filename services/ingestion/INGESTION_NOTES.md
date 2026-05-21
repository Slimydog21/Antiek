# INGESTION_NOTES.md — Sprint SPR-03 numbers and choices

Per rigor value #5 (defensibility), every hardcoded constant in the
universal-library ingestion backend gets a one-sentence justification
here. Future maintainers will tune these; they need to know what
they're changing and why before they change it.

## Throttle window

**Value:** 1 request per 3 seconds per domain (default), tightened to
1 / 3s for ``export.arxiv.org`` and ``arxiv.org``.

**Source:** arXiv's public terms of service ask for ≤ 1 query / 3s
(see ``acquisition/arxiv/client.py`` `_SORT_MAP` comment, which
documents the same rate). The Researchmaxx ingestion got IP-banned on
``export.arxiv.org`` in 2026-05-17 by exceeding this in-process
because the throttle didn't survive worker restarts (cron worker
spawns + dies + spawns within seconds). Redis-backed sliding window
fixes that. Other domains default to 1 req/s, a conservative ceiling
that keeps us out of generic Cloudflare rate-limit territory without
penalizing well-behaved hosts.

## Retry-After default

**Value:** 60 seconds when the server returns 429 without an explicit
``Retry-After`` header.

**Source:** RFC 6585 §4 mentions Retry-After but doesn't mandate it
for 429. Most CDNs (Cloudflare, Fastly) and large publishers return
30-120 seconds; 60s is the median and is the value Cloudflare's
documentation recommends as a sane fallback. Long enough that we
don't immediately re-trigger the limit; short enough that a transient
ban doesn't stall ingestion for a useful URL for too long.

## Metadata cache size

**Value:** 10,000 entries (LRU on disk).

**Source:** Researchmaxx's previous cache was 1,000 entries, which
the 2026-05-17 incident memo flagged as undersized — the cache was
turning over so fast that warm hits on arXiv abstract metadata never
materialized, and every fetch was a fresh HTTP request even when the
same paper had been seen minutes earlier. Spec requires ≥ 10×; we
pick 10× exactly. At ~2 KB per arXiv metadata blob, 10k entries is
~20 MB on disk — trivial.

## EPUB words per page

**Value:** 250 words per synthesized page.

**Source:** EPUB has no fixed pagination; readers synthesize.
Industry conventions: typical English-language printed novel is
250-300 words/page (Penguin trade paperback runs 280-320); academic
non-fiction is 350-400; e-readers like Kindle and Kobo target
200-260 for "what fits on screen at default font size." We pick 250
as a neutral midpoint that produces page boundaries that feel right
to a reader and that chunk reasonably (a chunk caps at 2000 tokens =
about 1600 words ≈ 6.4 pages, which keeps chunks within 1-2 chapters
for most books).

## Paywall detection threshold

**Value:** flag ``paywalled: true`` when the extracted word count is
< 200 AND the page contains at least one of the following markers in
the raw HTML: ``"subscribe"``, ``"sign in to read"``, ``"continue
reading"``, ``"paywall"``, or the meta tag ``meta[name="article:opinion"]``.

**Source:** Best-effort heuristic. 200 words is a single short
paragraph — below that, an article body is almost certainly truncated
by a paywall stub. The marker list is the union of phrases we observed
in WSJ, NYT, Substack, Medium, Bloomberg, and FT paywall stubs. We
intentionally over-flag rather than under-flag — downstream notebooks
will display the ``paywalled`` flag and let the operator decide whether
to manually add the full text. False positives on short legitimate
articles (e.g. a 180-word breaking-news flash) cost nothing; false
negatives mean the operator thinks they have full content when they
don't, which is the worse failure.

## Min word count to graph-write

**Value:** 50 words.

**Source:** Inherited from ``acquisition/urls/adapter.py`` (constant
``MIN_INGEST_WORD_COUNT``). Pages where the extractor returns near-empty
body almost always indicate the extractor missed the article (heavy
JS, paywall, parsing error). Emitting the ``document.loaded`` event
without writing graph rows keeps the trajectory honest while keeping
the graph clean.

## robots.txt cache TTL

**Value:** 24 hours per domain.

**Source:** RFC 9309 ("Robots Exclusion Protocol") recommends caching
robots.txt for "a reasonable period," and notes most crawlers use 24
hours. The Internet Archive and Common Crawl both default to 24h.
Long enough that we don't hammer the robots endpoint; short enough
that policy changes propagate within a day.

## Chaos test backoff

**Value:** retry 3 times with exponential backoff (1s, 2s, 4s) on
5xx responses; surface failure to ``ingestion_jobs`` after the third
attempt.

**Source:** Three retries is the standard `tenacity` default
(``stop_after_attempt(3)``) and matches the existing
``acquisition/urls`` retry behavior. 1-2-4 second backoff is short
enough that a transient hiccup (server warm-up, brief network blip)
resolves; long enough that we don't compound load on a struggling
upstream. Beyond 3 retries is "the server is down" territory and the
job should fail clearly rather than keep grinding.

## Library choices

- **HTML reader-mode extraction**: we inherit
  ``acquisition/urls/extract.py`` which uses ``beautifulsoup4`` for
  main-content isolation + ``html2text`` for markdown rendering. We
  considered ``readability-lxml`` (the Python port of Mozilla
  Readability), but the existing extractor has worked-out edge
  cases (NYT byl meta, schema.org/Person markup, og:title fallback)
  that we'd lose by switching. The existing extractor is a
  lightweight Readability-equivalent — not a full port — and
  documented as such.
- **EPUB extraction**: stdlib ``zipfile`` + ``xml.etree.ElementTree``.
  We considered ``ebooklib``, but it's not installed in the project's
  venv and adding a dep for what's structurally a zipfile parse felt
  unwarranted. EPUB is just a ZIP with an OPF manifest pointing at
  XHTML content files; the stdlib handles both. If we hit
  malformed-EPUB edge cases that warrant ebooklib's edge handling we
  can adopt it later — the extractor's interface ``extract_epub(path)
  -> ExtractedDocument`` doesn't change.
- **PDF extraction**: ``pypdf>=4.3`` (already in
  ``[project.optional-dependencies] pdf``). Used by
  ``processing/extraction`` already; we inherit.
- **Redis client**: ``redis>=5.0`` for the cross-process throttle.
  ``fakeredis`` is used in tests so we don't need a live Redis server
  in CI.

## Inherited arXiv fixes — what landed

From memory ``project_researchmaxx_arxiv`` (2026-05-17):

1. **IP 429-ban on export.arxiv.org** — fix: persistent ``banned_until``
   sentinel in DuckDB ``ingestion_bans`` table. Fetcher short-circuits
   to a cached error when the ban window is still active.
2. **In-process throttle** — fix: Redis-backed sliding window
   (`throttle.py`). Survives worker restart. Verified manually by
   stopping/restarting the worker between fetches.
3. **Missing SSL env exports** — fix: `fetcher.py` loads ``SSL_CERT_FILE``
   and ``REQUESTS_CA_BUNDLE`` from the project config at module
   import, falling back to ``certifi`` if the env vars are unset.
4. **Undersized metadata cache** — fix: 10,000 entries (10× the
   previous 1,000). See the cache-size justification above.
5. **No banned-until sentinel** — fix: ``ingestion_bans`` table with
   ``(domain, banned_until)`` schema. See ``migrations/0001_ingestion_bans.sql``.

Preserved (worked already, not touched):
- arXiv PDF endpoint (``arxiv.org/pdf/...``) used as the primary
  full-text source.
- Semantic Scholar (S2) fallback for arXiv papers when the primary
  fetch fails after retries.

## Storage model

The ``ingestion_bans`` and ``ingestion_jobs`` tables live in the same
DuckDB file as the rest of the graph substrate
(``~/.antiek/research_graph.duckdb``). They go through the same
``runtime/db_lock.connect_write`` discipline as every other writer.
