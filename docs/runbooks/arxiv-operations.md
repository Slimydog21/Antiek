# arXiv Acquisition Operations

This runbook covers the arXiv OAI-PMH sync pipeline: rate limits, endpoints,
sync troubleshooting, how to run the verifier, and what to check nightly.

## Overview

Antiek's arXiv acquisition path harvests metadata and license information via
arXiv's OAI-PMH protocol. The pipeline runs nightly via systemd timer
(`antiek-arxiv-oai-sync.timer`), incremental from the last successful
datestamp.

**Key files:**

| File | Purpose |
|------|---------|
| `acquisition/arxiv/oai_pmh.py` | OAI-PMH ListRecords harvester |
| `acquisition/arxiv/throttle.py` | Cross-process rate throttle + ban sentinel |
| `acquisition/arxiv/rate_governor.py` | Host-global fcntl.flock-serialized governor |
| `acquisition/arxiv/oai_records.py` | XML parsing + census fold |
| `acquisition/arxiv/oai_persist.py` | Persist records to DuckDB documents store |
| `tools/arxiv_oai_sync.py` | Nightly sync CLI |
| `tools/arxiv_verify.py` | Health verification CLI |
| `infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2` | systemd service |

---

## Rate Limits — THE ONE RULE

**arXiv rate limits ban the whole IP.** The policy is 1 request per 3 seconds.
Exceeding it returns HTTP 429 and blocks your entire source IP for 30 minutes
to several hours — every tool on the machine, not just the offending script.

Antiek enforces this through a layered defense:

1. **`ArxivThrottle`** (`acquisition/arxiv/throttle.py`): 3.5s spacing
   (deliberate 0.5s margin above the 3s minimum), persisted to a JSON state
   file (`~/.antiek/arxiv_throttle.json`). Cross-process: survives restarts.
   Ban sentinel: on 429, persists a `banned_until` timestamp (default 30 min).
   While banned, calls raise `ArxivBanned` instead of hitting the endpoint.

2. **`ArxivRateGovernor`** (`acquisition/arxiv/rate_governor.py`): Wraps the
   throttle's critical section in an exclusive `fcntl.flock` so the
   wait-if-needed → send → note-response sequence is atomic across ALL arXiv
   jobs on the host. This prevents two concurrent processes from both firing
   inside the same 3s window.

3. **Redirect-safe governance** (`rate_governor.py:install_arxiv_request_hook`):
   Per-hop event hooks on httpx clients so a redirect from a non-arXiv URL to
   `arxiv.org/pdf/<id>` is governed at the redirect target, not just the
   initial host.

### Checking governor health

```bash
# Check throttle state + ban sentinel
python -m acquisition.arxiv.throttle

# Check the full governor (import and inspect)
python -c "from acquisition.arxiv.rate_governor import canonical_arxiv_throttle; t = canonical_arxiv_throttle(); print(f'banned={t.is_banned()}')"
```

### If the IP gets banned

1. **STOP all arXiv requests immediately.** The ban extends on each 429.
2. Wait for `banned_until` to pass (check `~/.antiek/arxiv_throttle.json`).
3. Use the verifier: `python -m tools.arxiv_verify` — it reports the ban state.
4. Once clear, resume operations. The incremental sync will catch up.

---

## Endpoint

**Canonical OAI-PMH endpoint:** `https://oaipmh.arxiv.org/oai`

arXiv moved the OAI-PMH service from `export.arxiv.org/oai2` (now a 301
redirect) to `oaipmh.arxiv.org/oai` in 2026-08. The harvester targets the new
endpoint directly and follows redirects defensively for future moves.

**Metadata prefix:** `arXiv` — the only prefix carrying the per-paper
`<license>` element (the rights source of truth for the census).

---

## Sync Architecture

Two checkpoints, two distinct jobs:

| Checkpoint | File | Purpose |
|------------|------|---------|
| Mid-harvest cursor | `arxiv_oai_harvest.json` | Resumes an interrupted harvest from the last completed page |
| Sync high-water mark | `arxiv_oai_sync.json` | The `from` date for the next incremental run |

**The incremental sync** passes `from=last_successful_datestamp` so only
records stamped after the last good run are fetched.

**State persistence (SPR-09 fix):** The sync checkpoint is now written
incrementally after each OAI-PMH page completes, not just at the end of the
harvest. This prevents the "full re-crawl each night" bug where a killed-long-
running-harvest (systemd `TimeoutStartSec=21600`) never wrote the checkpoint.

### systemd service

```
# Trigger: daily at 04:20 UTC
OnCalendar=*-*-* 04:20:00 UTC
Persistent=true     # missed runs fire after boot

# Service: oneshot, 6h timeout
Type=oneshot
TimeoutStartSec=21600

# All state pinned under {{ antiek_state_dir }}
ANTIEK_ARXIV_THROTTLE_PATH={{ antiek_state_dir }}/arxiv_throttle.json
ANTIEK_ARXIV_OAI_STATE_PATH={{ antiek_state_dir }}/arxiv_oai_harvest.json
ANTIEK_ARXIV_OAI_SYNC_PATH={{ antiek_state_dir }}/arxiv_oai_sync.json
```

---

## Sync Troubleshooting

### "Full re-crawl each night" — sync never completes

**Symptom:** The nightly sync runs but the high-water mark never advances.
Each run re-harvests the full corpus.

**Root cause (fixed):** The sync checkpoint was only written AFTER the entire
harvest completed. If systemd killed the process (6h timeout), the checkpoint
was never written.

**Fix:** The checkpoint is now written incrementally after each page via
`on_page_complete` callback. Verify with:

```bash
# Check if high-water mark is advancing
cat ~/.antiek/arxiv_oai_sync.json

# Check systemd journal for the last run
journalctl -u antiek-arxiv-oai-sync.service --since yesterday
```

### Sync raises ArxivBanned

**Symptom:** Sync exits with "arXiv endpoint banned for another N seconds".

**Action:**
1. Check throttle state: `python -m acquisition.arxiv.throttle`
2. Wait for ban to expire.
3. The mid-harvest cursor is intact — next run resumes from the cursor.

### Sync is very slow (taking > 6h)

**Symptom:** systemd kills the sync before completion.

**Possible causes:**
- The `from` datestamp is stale (checkpoint not advancing — see above).
- arXiv is throttling responses (check for 429 in logs).
- Very large incremental window (first run after a long gap).

**Action:**
- Check journal for 429 errors.
- Run a manual backfill: `python -m tools.arxiv_oai_sync backfill --until <date>`
- Monitor the high-water mark: `watch -n 60 cat ~/.antiek/arxiv_oai_sync.json`

### Census JSON missing

**Symptom:** `reports/arxiv_oai_census.json` not written.

**Action:** Check `--census-json` arg in the systemd service template. The
ExecStart should include `--census-json {{ antiek_state_dir }}/reports/arxiv_oai_census.json`.

---

## Running the Verifier

```bash
# Full verification (human-readable report)
python -m tools.arxiv_verify

# Machine-readable JSON verdict
python -m tools.arxiv_verify --json

# Custom paths
python -m tools.arxiv_verify --db-path /path/to/antiek.duckdb
```

**Exit codes:**
- `0` — all checks passed
- `1` — one or more checks failed

**Checks performed:**

| Check | What it verifies |
|-------|-----------------|
| `endpoint_health` | OAI-PMH `Identify` verb responds with valid XML |
| `rate_governor` | `MIN_REQUEST_SPACING_S >= 3.0`, ban sentinel state |
| `sync_state` | Checkpoint files readable, datestamp present, no null high-water |
| `census_json` | Census JSON has required keys (`total`, `t1`, `t2`, `t3`, `harvested_at`) |
| `coverage` | DuckDB has arXiv documents (count reported) |

### Nightly verification

Add to the systemd service (after ExecStart):

```
ExecStartPost=/path/to/.venv/bin/python -m tools.arxiv_verify --json >> /var/log/arxiv-verify.jsonl
```

Or add a separate timer for verification:

```ini
[Timer]
OnCalendar=*-*-* 05:00:00 UTC
Persistent=true
```

---

## What to Check Nightly

1. **Sync completed:** `cat ~/.antiek/arxiv_oai_sync.json` — check
   `last_harvested_at` is recent.
2. **High-water mark advancing:** Compare `last_successful_datestamp` across
   days — it should monotonically increase.
3. **No ban active:** `python -m tools.arxiv_verify` — check
   `rate_governor` doesn't report BANNED.
4. **Census reasonable:** `cat reports/arxiv_oai_census.json` — total should
   be non-decreasing.
5. **DuckDB coverage:** The verifier's `coverage` check reports arXiv doc count.

---

## Key Design Decisions

- **3.5s spacing, not 3.0s:** Deliberate 0.5s margin above arXiv's 3s minimum
  to absorb clock skew, request jitter, and redirect hops. The ban is IP-scoped
  with hours-long recovery — the extra half-second is negligible insurance.
- **Cross-process lock (fcntl.flock):** The rate governor serializes ALL arXiv
  jobs under one exclusive lock, so concurrent processes cannot burst past the
  limit.
- **Ban sentinel (30 min):** After a 429, calls fail fast for 30 minutes
  instead of deepening the ban. The sentinel clears automatically on success.
- **Incremental checkpoint:** The sync high-water mark is written after each
  page, not just at harvest completion. This ensures progress survives process
  kills.
- **Deny-by-default licensing:** OAI records land at the gated floor
  (`restricted_pending_opt_in`) until their license is verified as
  redistributable (T1). T3 (default/unknown) records are never stored/served.
