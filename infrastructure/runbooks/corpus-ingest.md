# Corpus Ingest — Land a Rights-Correct, Quality-Gated Corpus in Prod

**Audience**: the operator. This is an **operator-only** procedure. The agent
builds and verifies the orchestrator (`tools/run_corpus_ingest.py`) and can run
it in `--dry-run` against a local/temp DB, but it must **never** run a real
prod ingest: the prod-write steps below mutate the live substrate and require a
backup + a deliberate `--allow-prod-write`, both of which are your call.

**Time**: ~5 minutes of dry-run review + ~1 minute backup + however long the
batch's network fetches take.

**What the orchestrator does**: discovers candidates from the three
rights-correct connectors (public-domain / arXiv / open-access), collapses
cross-source duplicates, runs each survivor through the corpus-quality gate,
and ingests only the kept ∩ passing set through each connector's own
`runtime.db_lock.connect_write` single-writer path. The whole plan is computed
before anything is written; `--dry-run` prints that exact plan and writes
nothing.

---

## Happy path

### 1. Dry-run locally and read the plan

Always dry-run first. The dry-run runs the FULL pipeline — discovery, body
fetch for assessment, dedup, and the quality gate — and writes nothing.

```bash
cd ~/Desktop/Antiek
# arXiv by category + the curated public-domain spine, dry-run:
./.venv/bin/python -m tools.run_corpus_ingest \
    --source arxiv --arxiv-category cs.LG \
    --source public_domain --pd-curated \
    --limit 25 --dry-run
```

Read the printed plan. It reports, in order:

- **dedup**: how many candidates were kept vs dropped, and which key collapsed
  each drop (`doi` / `arxiv_id` / `source_id` / `title_author`).
- **quality gate**: how many were assessed, how many passed, and the
  **rejection RATE** with a reason per rejected candidate. A high reject rate
  is shown, never hidden — if it looks wrong, fix the selectors before you
  write anything.
- **would ingest**: the final set. Items whose body could not be assessed
  before ingest (open-access, whose body is a publisher PDF fetched at ingest
  time) are flagged `[body not assessed pre-ingest]` — that is expected and
  honest, not a defect.

If the plan looks wrong, adjust `--source` / selectors / `--limit` and dry-run
again. Nothing has touched any DB.

### 2. Optional: dry-run against a temp copy, or do a real LOCAL ingest

To exercise the actual write path without touching prod, point `--db-path` at a
throwaway DB (the orchestrator refuses the prod default unless
`--allow-prod-write` is given):

```bash
./.venv/bin/python -m tools.run_corpus_ingest \
    --source arxiv --arxiv-ids 2402.03300 \
    --db-path /tmp/antiek-corpus-smoke.duckdb
```

### 3. Back up prod BEFORE any prod write

```bash
cd ~/Desktop/Antiek/infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/backup.yml
```

This runs the same `/usr/local/bin/antiek-backup` the nightly cron runs
(snapshot → R2). Confirm `failed=0` and that the script's stdout reports a
fresh archive. Do not proceed without a good backup — a corpus ingest appends
many documents and is not trivially reversible in place.

### 4. Stop the writer so the single-writer lock is free

The substrate is **single-writer** (`--workers 1` uvicorn; the invariant lives
in `runtime/db_lock.py`). A running `antiek.service` holds the write lock, so an
ingest would otherwise block until timeout. Stop it for the duration of the
ingest:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
systemctl stop antiek
```

The orchestrator pre-flights this for you: with `--allow-prod-write` it tries to
acquire the write lock with a short deadline and aborts with a clear "stop the
antiek.service" message if the lock is held — so a forgotten `systemctl stop`
fails fast instead of stalling for five minutes.

### 5. Run the real prod ingest

On the VM (where the prod DB lives), with the writer stopped:

```bash
cd /opt/antiek
sudo -u antiek ./.venv/bin/python -m tools.run_corpus_ingest \
    --source arxiv --arxiv-category cs.LG \
    --source public_domain --pd-curated \
    --limit 25 \
    --db-path ~antiek/.antiek/research_graph.duckdb \
    --allow-prod-write
```

It prints the same plan as the dry-run, then ingests the kept ∩ passing set and
reports `ingested N / M planned; K failed`. Per-item failures are isolated — one
bad fetch does not abort the batch.

### 6. Restart the writer

```bash
systemctl start antiek
systemctl is-active antiek          # expect: active
curl -s https://api.antiek.ai/health | jq .registered_providers
```

### 7. Servability audit (the §9.0 deny-by-default check)

Confirm the new documents carry the right `content_class` and that **nothing
gated is servable as full text**. The substrate's retrieval gating
(`substrate/graph/search.py`, landed SPR-04) treats `NULL`/gated
`content_class` as not-servable — this audit verifies the ingest respected it.

```bash
# On the VM, against the now-restarted (or briefly re-stopped) DB:
sudo -u antiek ./.venv/bin/python - <<'PY'
import duckdb
con = duckdb.connect("/home/antiek/.antiek/research_graph.duckdb", read_only=True)
print(con.execute(
    "SELECT content_class, COUNT(*) FROM documents GROUP BY content_class ORDER BY 2 DESC"
).fetchall())
PY
```

Confirm: the counts match what the plan said it would ingest, servable classes
are only the ones whose licenses Antiek holds (CC-BY / CC-BY-SA / CC0 / public
domain), and there is **no full-text serving of GATED or NULL-class
documents**. If anything gated shows as servable, stop and restore from the
step-3 backup — that is a §9.0 violation, not a cosmetic bug.

---

## Unhappy path — rollback

A corpus ingest only **appends** documents (and their chunks/embeddings); it
does not modify existing rows. To undo a bad batch, restore the pre-ingest
snapshot:

```bash
# See disaster-recovery.md for the full restore-from-R2 procedure.
systemctl stop antiek
# restore the step-3 backup archive over ~antiek/.antiek/research_graph.duckdb
systemctl start antiek
```

Do **not** attempt to hand-delete the ingested documents row-by-row — the
provenance chain (document → chunks → claims) makes partial deletion
error-prone. Restore the snapshot instead.

## What this procedure does NOT do

- **It does not run autonomously.** The agent never runs steps 3–7. The
  `--allow-prod-write` flag and the backup are the operator's, by design.
- **It is not an Anna's Archive / shadow-library path.** The orchestrator only
  ever ingests through the three rights-correct connectors; it has no scraper
  and serves no copyrighted full text. Both are explicitly out of scope (SPR-08
  spec + §9.0).
- **It does not bypass the single-writer invariant.** Every write goes through
  `runtime.db_lock.connect_write`. The writer must be stopped first; the
  orchestrator's lock pre-flight enforces this.
- **It does not re-rank or change retrieval gating.** Servability is decided by
  the connectors' license resolution + the SPR-04 retrieval gate. This script
  only adds documents; the gate that was already in prod governs what is
  served.
- **It does not quality-assess every body before ingest.** The OCR/real-word
  checks run on the text that is available *at discovery*: public-domain
  text-format bodies and arXiv abstracts. Open-access bodies (and Gutenberg
  works served only as PDF) are publisher/extracted PDFs fetched at ingest
  time, so they enter on metadata + rights alone and are flagged
  ``[body not assessed pre-ingest]`` in the plan. These are born-digital
  sources where assessing a title would false-reject good papers; rights and
  servability still gate them. If body-quality assessment of OA PDFs becomes a
  requirement, it belongs in the connector's ingest path, not this
  orchestrator.

## Re-running is safe (idempotent on identity)

Re-running the same selectors is safe: cross-source dedup collapses duplicates
within a single run, and the connectors' ingest path keys on source identity,
so a document already present is not duplicated. If a previous run failed
partway (`K failed`), simply re-run — the already-ingested items are recognized
and the failures are retried.

## Common failure modes

| Symptom | Most likely cause | Fix |
|---|---|---|
| `the single-writer lock is held — stop the antiek.service` | `antiek.service` (uvicorn) is still running | `systemctl stop antiek`, then re-run; restart after (step 6) |
| `--db-path resolves to the prod substrate default` and it refuses | real run against prod without `--allow-prod-write` | this is the guard working; supply the flag only after a backup |
| arXiv discovery aborts with a ban / 429 | the arXiv IP throttle tripped (`ArxivThrottle` ban sentinel) | wait out the ban window; the throttle persists it cross-process — do not hammer |
| high rejection rate in the plan | selectors pulling scanned/low-quality or off-topic works | tighten `--arxiv-category` / `--pd-curated` / drop the bad `--source`; re-dry-run |
| `K failed` on open-access items | publisher PDF fetch blocked or no fetchable PDF | expected for some OA records (DOAJ has no PDF); the others still land |
| servability audit shows a gated doc as servable | a license-resolution regression upstream | restore the step-3 backup; do not serve; file against the connector, not this script |
