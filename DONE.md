# DONE — BYO-tools: YouTube Data API + FMP connectors

Sub-goal from `SWARM_BRIEF.md`, executed in this worktree only. Commit:
`5c23a545b` on `swarm3/byo-tools-youtube-fmp` (not pushed). Built on the
round-1 chassis (`runtime/connectors/base.py` `PasteKeyConnector` +
`rate_governor.py`) — reused, not forked; the chassis files themselves are
untouched except `runtime/connectors/__init__.py` (export additions).

## Files

| File | What |
|---|---|
| `runtime/connectors/quota_meter.py` | NEW — `QuotaMeter` (spec §5.5): `check_and_reserve` / `record_actual` (signed diff, exa-budget shape) / `mark_exhausted` / `remaining`; `YOUTUBE_UNIT_COSTS` (search.list=100); date-stamped JSON sidecar; reset at midnight America/Los_Angeles via zoneinfo on an injectable clock; fail-closed reads. |
| `acquisition/youtube/data_api.py` | NEW — `YouTubeConnector` (spec §5.7 row 2): `search(query, ...)` over `GET https://www.googleapis.com/youtube/v3/search?part=snippet&q=...&key=...`; reserves 100 units BEFORE the request is built (exhausted meter refuses with PT reset time); failed send releases its hold; 403 `quotaExceeded` hard-sets the meter and raises `YouTubeQuotaExhausted`; key via chassis, revealed only into the param line; errors carry status + path only; `quota_remaining()` exposes the daily meter. Scrape `client.py` untouched (separate module on purpose). |
| `acquisition/fmp/client.py` | NEW — `FmpConnector` (spec §5.7 row 3a): `profile(symbol)` (`/api/v3/profile/{symbol}`) + `transcripts(symbol, year, quarter)` (`/api/v3/earning_call_transcript/{symbol}`) with `apikey` in the query at send time; `redact_query()` drops the query string; every error carries status + PATH only (byte-asserted in tests); vendor-429 via `VendorRateGovernor` at a documented no-window rate (`FMP_RATE_NO_WINDOW`, spec §5.4). |
| `acquisition/fmp/__init__.py` | NEW — package exports. |
| `acquisition/youtube/__init__.py` | + data_api exports (no collision with the scrape path). |
| `runtime/connectors/__init__.py` | + quota-meter exports. |
| `tests/test_youtube_data_api_quota.py` | NEW — 20 tests, offline. |
| `tests/test_fmp_client.py` | NEW — 12 tests, offline. |
| `SWARM_BRIEF.md` | committed per the brief's `git add -A` (as round 1 did). |

## Exact test command + result

```bash
~/Antiek/platform/.venv/bin/python -m pytest tests/test_youtube_data_api_quota.py \
  tests/test_fmp_client.py -q
# 32 passed in 0.70s
```

Regression (must stay green): 80 passed — `test_connectors_chassis.py`,
`test_acquisition_edgar.py`, `test_connector_rate_governor.py`,
`test_acquisition_youtube.py`. Spec §7 regression set: 114 passed —
`test_personal_lane_read_side.py`, `test_settings_models_admin.py`,
`test_midnight_oil_budget_ledger.py`, `test_corpus_audit.py`.

All offline: `httpx.MockTransport` only, zero live calls; quota/rate state
always pinned under `tmp_path` (never `~/.antiek`).

## Gates

- `ruff check` on all new/changed files: **clean**.
- `mypy --strict` on all new code: **clean** (0 findings in
  `quota_meter.py`, `data_api.py`, `fmp/*`, `__init__.py` updates, both test
  files; the repo-wide errors mypy reports while following the import graph
  are the pre-existing CI-baselined noise — 239 of them reproduce when
  checking the already-merged `acquisition/edgar/client.py` alone).
- `scripts/check_integration_tiers.py`: green (httpx-only, zero new package
  rows — no `integrations.toml` change needed).
- `tools/lint/rate_governor_check.py`: green (both clients route through
  `govern_if_arxiv`, the scanner-visible seam).

## Honest gaps

1. **Endpoint shapes fixture-validated, live-unverified** — same honesty bar
   as the EDGAR client: request params and response envelopes follow public
   vendor docs, not a fresh live probe. Live round-trips are the operator's
   smoke test (no keys exist on this box to probe with, and the brief bans
   live calls anyway).
2. **FMP no-window rate** — `FMP_RATE_NO_WINDOW = RateSpec(max_calls=1_000_000,
   window_s=60.0)` is a stand-in for "no client-side pacing window" (spec
   §5.4 assigns FMP only vendor-429 governance); documented in-code. The
   descriptor's `rate` stays `None`.
3. **Quota meter is a client-side advisory counter** — spec §10 risk 3
   acknowledged: the 403 `quotaExceeded` hard-set is the vendor-ledger
   backstop, and cross-process races on the sidecar are accepted (single
   operator, one process; Sprint 22+ moves this into DuckDB/`db_lock`).
4. **Not built (out of this sub-goal's scope):** Polygon, the settings API
   vertical (`settings_connectors.py`), adapters/`insert_document` wiring,
   and the frontend tiles — all later sprints of the spec (§5.7 rows 3b,
   5.2, adapters, 5.8).
5. **YouTube KeyShape prefix** — `prefix="AIza"` enforced at paste time
   (GCP API-key prefix class). If Google ever issues non-`AIza` keys, the
   shape is a one-line relax; documented in the descriptor.
