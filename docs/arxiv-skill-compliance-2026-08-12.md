# arXiv skill-compliance audit — 2026-08-12

Branch: `fix/arxiv-sync-checkpoint-20260812` (worktree at origin/main `2e4e788d2`)
Scope: `acquisition/arxiv/*.py` + the OAI-PMH sync driver `tools/arxiv_oai_sync.py`
+ the systemd service `infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2`.
Reference standard: the Hermes Agent `arxiv` skill rules — 1 request / 3s spacing
enforced across processes, 429 backoff 60→120→240s with jitter, ban sentinel
(fail fast after a 429), metadata cache, HTML-preferred full text, contact
User-Agent.

Verdict: the platform is *mostly* compliant; the two real gaps are (1) the
OAI-PMH channel's User-Agent carries no contact, and (2) the 429 path jumps
straight to a 30-minute ban sentinel instead of the skill's 60→120→240s
escalating retry ladder (a deliberate, documented deviation — see §2). There is
no raw-response metadata cache; its purpose is served by the DuckDB documents
store + the across-run high-water mark (§4). The "sync never completes / no
resumption-token persistence" failure mode described in the ops report is FIXED
on main (§6); this branch hardens the remaining checkpoint gaps (schema version,
progress counters, page timestamp, `--reset-state`).

## 1. Request spacing ≥ 3s, enforced across processes — COMPLIANT

* `MIN_REQUEST_SPACING_S = 3.5` — `acquisition/arxiv/throttle.py:50`. A 0.5s
  margin above arXiv's 3.0s ceiling (clock skew / redirect hops; the box has
  been IP-banned twice, see the module docstring `throttle.py:1-30`).
* Cross-process: spacing + ban state live in `~/.antiek/arxiv_throttle.json`
  (`throttle.py:61-63` `default_state_path`), atomically written tmp+replace
  (`throttle.py:152-159` `_write_state`).
* Host-global serialization: `ArxivRateGovernor` (`rate_governor.py:358`)
  holds the whole `wait_if_needed -> send -> note_response` critical section
  under an exclusive `fcntl.flock` (`rate_governor.py:395-436`);
  `governed_request` (`rate_governor.py:445`) is the convenience seam. Every
  arXiv egress routes through it (OAI harvest, PDF, HTML, export search, bulk).

## 2. 429 backoff 60→120→240s with jitter — GAP (documented deviation)

* `ArxivThrottle.note_response` (`throttle.py:214-236`): on the FIRST 429 it
  persists `banned_until = now + backoff` where `backoff` is
  `DEFAULT_BAN_BACKOFF_S = 30 * 60` (`throttle.py:56`) or `Retry-After` when
  larger (`throttle.py:226-233`).
* There is NO 60→120→240s escalating retry ladder and NO jitter in the 429
  path: `grep -rn "random" acquisition/arxiv` is empty, and the only "jitter"
  hit is a comment about clock skew (`throttle.py:46`).
* Effect: a transient burst-limit 429 pauses the whole host for 30 minutes
  instead of retrying after 60s. This is conservative-BY-DESIGN (re-hitting a
  banned endpoint is the exact bug that IP-banned the box; see
  `throttle.py:82-94` `ArxivBanned` and the `tools/ingest_arxiv.py:79-93`
  sentinel handling) — but it does not match the skill's graduated ladder.
  Recommendation if the ladder is ever wanted: add it INSIDE
  `ArxivThrottle.request`/`note_response` (escalate 60→120→240 with
  `random.uniform` jitter, then set the 30-min sentinel), so every channel
  inherits it under the same flock. Not changed in this branch (mission scope:
  checkpoint/resume; the sentinel semantics are already safe).

## 3. Ban sentinel (fail fast after a 429) — COMPLIANT

* `wait_if_needed` raises `ArxivBanned` while `banned_until` is in the future
  (`throttle.py:195-204`); `ArxivBanned` (`throttle.py:86-94`) carries
  `banned_until` + `remaining_s` for operator messaging.
* The sentinel is persisted in the shared state file, so a fresh process
  inherits it (the pre-PR#23 bug — every invocation re-hitting a banned
  endpoint — is closed). 30-min floor matches the skill's "fail fast 30 min".
* All consumers honor it: `oai_pmh.py` (propagates, `tools/arxiv_oai_sync.py:441-446`
  prints and exits 1), `html_fetch.py:168-177` (a FRESH 429 is a ban signal,
  NOT "HTML absent"), `pdf_fetch.py:155-160`, `tools/ingest_arxiv.py:79-93`.

## 4. Metadata cache — GAP (purpose served differently)

* No raw-response/record metadata cache exists anywhere in `acquisition/arxiv/*`
  (grep for `cache`/`Cache` hits only `store.py:47-48`, a comment about a
  cached content-class). The skill's cache exists to avoid re-fetching
  unchanged metadata; Antiek achieves the same end with:
  1. the across-run high-water mark `SyncCheckpoint` (`tools/arxiv_oai_sync.py:88-117`):
     incremental runs send `from = last_successful_datestamp`
     (`tools/arxiv_oai_sync.py:225-227`), so arXiv itself only re-serves the
     delta window — unchanged records are never re-transferred;
  2. every harvested record is UPSERTed into the DuckDB documents store under
     one write lock (`acquisition/arxiv/oai_persist.py:176+`), so nothing is
     re-fetched to re-serve a query.
* Within a harvest, each page is fetched exactly once thanks to the persisted
  resumption cursor (`oai_pmh.py:272-324`).
* Note: this is a substitution, not a literal cache; if the skill's exact
  semantics are ever required (e.g. offline replay), a TTL disk cache of OAI
  responses would slot in at `_fetch_page` (`oai_pmh.py:244-268`).

## 5. HTML-preferred full text — COMPLIANT

* `acquisition/arxiv/html_fetch.py:111` `fetch_html`: fetches the native LaTeXML
  HTML (`arxiv.org/html/<id>`), slices the `<article>` body (`html_fetch.py:83-97`),
  detects stubs (`html_fetch.py:99-104`, `MIN_HTML_CHARS`), and returns `None`
  when no rendering exists so the caller falls back to PDF.
* The ingest path prefers HTML when configured: `adapter.py:674-716`
  (`prefer_html` → `fetch_html` first, PDF fallback) with the governed default
  fetcher `adapter.py:398-410`; behavior matrix covered in
  `tests/test_arxiv_html_ingest.py:7-10`. PDF remains the guaranteed path
  (`pdf_fetch.py:142`).
* Both legs route every send through the host-global governor
  (`html_fetch.py:175`, `pdf_fetch.py:211-223`).

## 6. Contact User-Agent — PARTIAL GAP (OAI channel)

* Compliant channels: `client.py:55` `_DEFAULT_CONTACT = "+https://antiek.ai/contact"`
  and `client.py:58-64` `default_user_agent()` build
  `Antiek/0.1 (<ANTIEK_ARXIV_CONTACT | contact URL>; acquisition.arxiv)`. Used by
  `client.py:296`, `html_fetch.py:154`, `adapter.py:385`, `pdf_fetch.py:211`,
  `bulk.py:286`.
* GAP: the OAI-PMH harvester — the busiest and most ban-prone channel — sends a
  static `Antiek/0.1 (acquisition.arxiv.oai_pmh)` with NO contact
  (`oai_pmh.py:60`, applied at `oai_pmh.py:247`).
* FIXED in this branch: `oai_pmh.py` now derives its UA from
  `client.default_user_agent()` (env-configurable contact), matching the other
  channels.

## 7. Governor coverage of EVERY GET — COMPLIANT (historical hole closed)

* `_fetch_page` wraps BOTH send paths (injected test client and the
  redirect-safe governed client) in the outer
  `governed_request(send, throttle=self._throttle)` (`oai_pmh.py:263`) — the
  wait→send→note critical section runs under the host-global flock for every
  page, including redirect hops (`arxiv_governed_client` hook,
  `rate_governor.py:520+`, 612-676).
* The historical hole — a BARE `self._throttle.request(send)` that bypassed the
  flock — is gone from main: the only hit for `self._throttle.request` in
  `oai_pmh.py` is the docstring warning at `oai_pmh.py:236`. `test_rate_governor.py:721`
  (`test_oai_harvest_send_is_inside_the_host_global_governor_flock`) pins this.
* `html_fetch.py:175`, `pdf_fetch.py:216-223`, `adapter.py:355-403`,
  `client.py:277-296` show the same discipline.

## 8. OAI-PMH ListRecords resumption-token usage — COMPLIANT

* First page carries `metadataPrefix` + optional `from`/`until`; every
  subsequent page carries ONLY `resumptionToken` (the protocol forbids mixing)
  — `oai_pmh.py:198-219` `_page_url`, verified by
  `tests/test_arxiv_oai_pmh.py:149-158`.
* An empty `<resumptionToken/>` reads as the terminal page (`oai_pmh.py:354-372`
  `_extract_resumption_token`), so the loop never issues a pointless empty-token
  request.

## 9. Sync completion / checkpoint-resume — COMPLIANT on main, HARDENED here

* Main already persists the mid-harvest cursor after EVERY page
  (`oai_pmh.py:170-174` `_write_state`, atomic tmp+replace) and clears it on
  clean completion (`oai_pmh.py:176-178`, `oai_pmh.py:316-322`); `harvest`
  resumes from the stored token (`oai_pmh.py:272-324`). The across-run
  high-water mark lives in `tools/arxiv_oai_sync.py` (`SyncCheckpoint:88`,
  `read_checkpoint:119`, `write_checkpoint:133`, `run_sync:212-311`) and
  advances only on clean completion (`run_sync:298-306`).
* Systemd wiring is correct: the service pins
  `ANTIEK_ARXIV_OAI_STATE_PATH`/`ANTIEK_ARXIV_OAI_SYNC_PATH` under
  `{{ antiek_state_dir }}` (service.j2), `ReadWritePaths` covers it, and
  `TimeoutStartSec=21600` bounds a single pass — a killed pass resumes next
  night from the persisted token instead of restarting at `skip=0`.
* Remaining gaps this branch closes (the "never-completing" hardening):
  * **No schema version** on `HarvestState` (`oai_pmh.py:81-126`): a future
    schema change would mis-parse silently. Now `schema_version: 2` with
    versioned load (v1 files migrate; unknown future versions read as fresh +
    warning, matching the repo's degrade-not-crash state discipline).
  * **No progress bookkeeping**: only the OAI datestamp was persisted, so an
    operator could not tell how far a multi-night backfill had gotten. Now
    `skip_count` (records consumed) + `last_page_at` (wall-clock of the last
    completed page) are persisted with each page.
  * **No operator reset**: `--no-resume` (`tools/arxiv_oai_sync.py:403-404`)
    ignores the mid-harvest cursor but keeps the high-water mark. New
    `--reset-state` flag clears BOTH the mid-harvest cursor and the sync
    high-water mark for full operator recovery; the throttle/ban state is
    deliberately NOT reset (clearing a live ban sentinel re-opens the
    re-hit-a-banned-endpoint bug).
