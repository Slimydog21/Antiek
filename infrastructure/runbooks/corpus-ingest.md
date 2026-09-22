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

### 0. Pin the live DB path before anything touches prod

The live DuckDB path exists **only** in the systemd units: `ANTIEK_DUCKDB_PATH`
is set in `infrastructure/ansible/templates/antiek.service.j2:51` and matched by
the continuous-research and arXiv/OAI-sync units. An interactive shell does not
inherit it, so a bare `python` falls back to `substrate.constants.DUCKDB_PATH`
(`~/.antiek/research_graph.duckdb`) — an **orphan** DB the API never reads. An
ingest against the orphan reports success, lands nothing in the product, and the
step-7 servability audit then certifies the wrong corpus. This is Preflight 1 of
`corpus-mass-ingest.md`; it applies here identically.

Resolve the path from the unit rather than trusting any path written in this
document:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
# the single source of truth for the live path:
systemctl show antiek -p Environment | tr ' ' '\n' | grep ANTIEK_DUCKDB_PATH
# -> ANTIEK_DUCKDB_PATH=/home/antiek/.antiek/antiek.duckdb   (example)
export LIVE_DB=/home/antiek/.antiek/antiek.duckdb   # use the value printed above
test -f "$LIVE_DB" && echo "live DB present: $LIVE_DB" || echo "WRONG PATH — stop"
```

Every prod command below takes `$LIVE_DB` explicitly; never let `--db-path`
default. Two mechanics to keep straight. Where `$LIVE_DB` appears as an
argument, *your* shell expands it before `sudo` ever runs, so it arrives
correctly. Where a child process must read an environment variable, `sudo` will
not carry it — sudoers resets the environment — so it is passed with `env`, the
same reason `prod-ocr-cli.md:20` writes `sudo -u antiek env PATH=...`.

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

`--limit` is not a batch size, and under `--pd-curated` it is not even a cap.
It caps arXiv and open-access discovery, but for the public-domain spine
`run_corpus_ingest.py:702-703` does `limit = max(limit, len(CURATED_GUTENBERG_IDS))`,
so all 23 curated Gutenberg works land whatever you pass; that reassigned limit
is then handed *separately* to each of the five PD book connectors at `:777`
(Standard Ebooks, Wikisource, Internet Archive, HathiTrust, Library of
Congress). `--limit 25` therefore plans up to 23 Gutenberg + 5×25 PD book
candidates + 25 arXiv, not 25. Size the batch by the plan's **would ingest**
count, never by the flag.

If the plan looks wrong, adjust `--source` / selectors / `--limit` and dry-run
again. Nothing has touched any DB.

### 2. Optional: dry-run against a temp copy, or do a real LOCAL ingest

To exercise the actual write path without touching prod, point `--db-path` at a
throwaway DB (the orchestrator refuses a `--db-path` that resolves to the prod
default unless `--allow-prod-write` is given — step 0 explains what that default
actually resolves to in your shell):

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

This runs the same `/usr/local/bin/antiek-backup` that `antiek-backup.timer`
runs nightly (snapshot → R2); the legacy `/etc/cron.d/antiek-backup` was removed
by `deploy.yml`, so the timer is the only schedule left. Confirm `failed=0` and
that the script's stdout reports a fresh archive. Do not proceed without a good
backup — a corpus ingest appends many documents and is not trivially reversible
in place.

Know the snapshot's shape before you need it: `backup.sh.j2:329` runs DuckDB's
`EXPORT DATABASE ... (FORMAT PARQUET)`, so the artifact is a *directory* of
Parquet shards plus `load.sql`, not a copy of the `.duckdb` file. That is why
the rollback below is an `IMPORT DATABASE` into a fresh file and not a file
copy.

### 4. Stop the writer so the single-writer lock is free

The substrate is **single-writer** (`--workers 1` uvicorn; the invariant lives
in `runtime/db_lock.py`). A running `antiek.service` holds the write lock, so an
ingest would otherwise block until timeout. Stop it for the duration of the
ingest:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
systemctl stop antiek
```

The orchestrator pre-flights this for you, but only for the file you name: with
`--allow-prod-write` it calls `_assert_lock_free(args.db_path)`
(`run_corpus_ingest.py:2352`), which takes and releases the write lock on
`--db-path` with a five-second deadline and aborts with a clear "stop the
antiek.service" message if it is held. The guarantee is exactly as good as the
path — a pre-flight against the orphan DB takes `research_graph.duckdb.write.lock`,
which nothing else ever holds, and sails through while uvicorn is still running.
Prod's real lock is `$LIVE_DB.write.lock`, the same file `deploy.yml:494` waits
on. Pin the path as in step 0 and the fail-fast becomes real.

One more link in that chain: the pre-flight only runs when the orchestrator
believes it is writing prod, and it decides that by comparing `--db-path`
against `substrate.graph.default_db_path()` (`_is_prod_db`,
`run_corpus_ingest.py:1331-1337`), which reads `ANTIEK_DUCKDB_PATH` first and
falls back to the orphan default. So the ingest process needs that variable set
as well as `--db-path` passed. Without it the orchestrator treats the live DB as
an ordinary non-prod path, stops demanding `--allow-prod-write`, and skips the
lock check entirely — step 5 passes it with `env` for this reason.

For a large batch, prefer `corpus-mass-ingest.md` instead of this section: it
ingests into a staging DuckDB with the API up and merges in one brief write
transaction, so there is no stop window at all. What follows is the
stop-the-writer path, appropriate for a small supervised batch.

### 5. Run the real prod ingest

On the VM (where the prod DB lives), with the writer stopped:

```bash
cd /opt/antiek
# $LIVE_DB was pinned in step 0. ANTIEK_DUCKDB_PATH is passed through `env`
# because sudo resets the environment; it is what arms the prod-write guard and
# the lock pre-flight on the file uvicorn actually holds (step 4).
sudo -u antiek env ANTIEK_DUCKDB_PATH="$LIVE_DB" \
    ./.venv/bin/python -m tools.run_corpus_ingest \
    --source arxiv --arxiv-category cs.LG \
    --source public_domain --pd-curated \
    --limit 25 \
    --db-path "$LIVE_DB" \
    --allow-prod-write
```

It prints the same plan as the dry-run, then ingests the kept ∩ passing set and
reports `ingested N / M planned; K failed`. Per-item failures are isolated — one
bad fetch does not abort the batch. Two things to read rather than assume: the
`would ingest` count is the real batch size (`--limit` is not, see step 1), and
a run that never mentions arXiv did not fail — arXiv discovery self-skips on a
ban and the run still exits 0 (see the failure-mode table).

### 6. Restart the writer

```bash
systemctl start antiek
systemctl is-active antiek          # expect: active
curl -s https://api.antiek.ai/health | jq .registered_providers
```

### 7. Servability audit (the §9.0 deny-by-default check)

Confirm the new documents carry the right `content_class` and that **nothing
gated is servable as full text**. The deny-by-default gate lives in
`substrate/books/servability.py` (serve path in `substrate/books/serve.py`):
full-text serving is an **allowlist**, `SERVABLE_CONTENT_CLASSES`, and `NULL` /
unknown / `restricted_pending_opt_in` resolves to `gated_metadata_only`. Do not
audit against `substrate/graph/search.py` — that is the chunk-search gate, a
*denylist* where a `NULL` content_class passes as legacy, deliberately looser
than the full-text gate. Auditing the ingest against the looser module would
pass content the serve path is supposed to refuse.

Run this in the writer-stopped window — before step 6, or by stopping the
service again for the few seconds it takes. A read-only DuckDB connect fails
outright while any process holds a read-write handle, and `runtime/db_lock.py`'s
warm-writer keepalive (`ANTIEK_WRITE_KEEPALIVE_S`, default 20s) parks that
handle for twenty seconds after every API write, so against a live service this
audit loses the race more often than it wins it:
`IOException: Could not set lock on file ... Conflicting lock is held`.

```bash
# On the VM, with antiek stopped. $LIVE_DB was pinned in step 0; cd first so the
# substrate package is importable, and pass LIVE_DB through `env` past sudo.
cd /opt/antiek
sudo -u antiek env LIVE_DB="$LIVE_DB" ./.venv/bin/python - <<'PY'
import os

import duckdb

from substrate.constants import SERVABLE_CONTENT_CLASSES

con = duckdb.connect(os.environ["LIVE_DB"], read_only=True)
rows = con.execute(
    "SELECT content_class, COUNT(*) FROM documents "
    "GROUP BY content_class ORDER BY 2 DESC"
).fetchall()
for content_class, n in rows:
    verdict = ("SERVABLE" if content_class in SERVABLE_CONTENT_CLASSES
               else "gated / metadata-only")
    print(f"{str(content_class):32} {n:8d}  {verdict}")
print("allowlist:", sorted(SERVABLE_CONTENT_CLASSES))
print("taken down but still servable-classed:", con.execute(
    "SELECT b.document_id, d.content_class FROM book_assets b "
    "JOIN documents d USING (document_id) WHERE b.taken_down"
).fetchall())
PY
```

Read the verdict column, not the class names. The allowlist it prints is
`opt_in_licensed`, `public_domain`, `source_declared_open`, `user_owned`,
`user_public_contribution` — these are content classes, not license names, so
there is nothing in that output to compare against CC-BY or CC0; the license
that justified each class is recorded per book in `book_assets.license_basis`.
Confirm three things: the counts moved by what the plan said it would ingest,
every row printed `SERVABLE` belongs to a class the connector's license
resolution actually established, and the taken-down list is empty (takedown
moves a document to `restricted_pending_opt_in`, so a taken-down row still
carrying a servable class means the override did not stick). A gated or
`NULL`-class document showing as servable is a §9.0 violation, not a cosmetic
bug — stop, do not serve, and restore from the step-3 backup.

---

## Unhappy path — rollback

A corpus ingest only **appends** documents (and their chunks/embeddings); it
does not modify existing rows. To undo a bad batch, restore the pre-ingest
snapshot:

The step-3 snapshot is an `EXPORT DATABASE` Parquet directory, not a file
image, so there is nothing to copy "over" the live DB — the inverse is
`IMPORT DATABASE` into a fresh file. `disaster-recovery.md` steps 4-6 fetch the
archive from R2 and extract it; what follows is its step 7 applied to a live box
whose only problem is a bad batch.

```bash
systemctl stop antiek

# Fetch and extract the snapshot first (disaster-recovery.md steps 4-5).
# backup.sh removes its own staging directory on exit, so nothing is left on
# the box — you always restore from the R2 archive, never from a local leftover.
rclone --config /etc/rclone/rclone.conf ls r2:antiek-backups/nightly/
rclone --config /etc/rclone/rclone.conf copyto \
    r2:antiek-backups/nightly/antiek-<UTC-timestamp>.tar.gz /tmp/antiek-restore.tar.gz
cd /tmp && tar -xzf antiek-restore.tar.gz

# $LIVE_DB was pinned in step 0. The extracted directory is
# antiek-backup.<suffix> — a DOT, not a hyphen; globbing the hyphen matches
# nothing and once destroyed prod (see the guard in disaster-recovery.md step 7).
RESTORE_DIR=$(ls -d /tmp/antiek-backup.*/ | head -n 1)
if [ -z "${RESTORE_DIR:-}" ] || [ ! -d "${RESTORE_DIR}duckdb" ]; then
  echo "ABORT: no extracted backup found. RESTORE_DIR='${RESTORE_DIR:-}'" >&2
  exit 1
fi

# Keep the bad batch for forensics; IMPORT requires a fresh file.
mv "$LIVE_DB" "$LIVE_DB.pre-restore"
mv "$LIVE_DB.wal" "$LIVE_DB.wal.pre-restore" 2>/dev/null || true

sudo -u antiek /opt/antiek/.venv/bin/python -c "
import duckdb
con = duckdb.connect('$LIVE_DB')
con.execute(\"IMPORT DATABASE '${RESTORE_DIR}duckdb';\")
con.close()
print('IMPORT complete')
"
chown -R antiek:antiek /home/antiek/.antiek/
systemctl start antiek
```

Expect `IMPORT complete`. Restoring onto `research_graph.duckdb` instead would
restore a file the API never opens while the live DB keeps the bad batch, which
is why step 0 exists.

One caveat if you ever improvise a snapshot instead of using an `antiek-backup`
archive: a raw DuckDB `EXPORT DATABASE` leaves a stray comma in `schema.sql`
where it drops a self-referential FK, and the inverse `IMPORT DATABASE` then
dies with `Parser Error: syntax error at or near ","`. Run
`tools/backup_normalize_schema.py` over that `schema.sql` first. Archives from
R2 need no such fix-up — `backup.sh` normalizes and then test-imports every
export before it uploads it.

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
  the connectors' license resolution plus the gates already in prod — the
  full-text allowlist in `substrate/books/servability.py` and the looser
  chunk-search denylist in `substrate/graph/search.py`. This script only adds
  documents; those gates govern what is served.
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
| arXiv contributes nothing and the run still exits 0 | the arXiv ban / 429 sentinel tripped; discovery is **skipped, not fatal** — `run_corpus_ingest.py:537-544` logs `arxiv banned, skipping arxiv discovery`, returns no candidates, and the batch continues over the other sources | grep the run log for that line before you trust the plan; wait out the ban window — the throttle persists it cross-process, do not hammer |
| the real run starts without demanding `--allow-prod-write` | `ANTIEK_DUCKDB_PATH` never reached the child (sudo resets the environment), so `_is_prod_db` is False and the lock pre-flight was skipped too | re-run the step-5 form, `sudo -u antiek env ANTIEK_DUCKDB_PATH="$LIVE_DB" …` |
| the plan is far bigger than `--limit` | `--limit` is a per-source floor under `--pd-curated`, not a batch cap (step 1) | size by the plan's `would ingest` count; drop `--pd-curated` or a `--source` to shrink |
| `IMPORT DATABASE` dies with `Parser Error: syntax error at or near ","` | a hand-made `EXPORT DATABASE` whose `schema.sql` still carries the self-ref-FK stray comma | normalize it with `tools/backup_normalize_schema.py`, then re-import; archives from R2 are already normalized |
| the audit dies with `Could not set lock on file ... Conflicting lock is held` | `antiek.service`, or its warm-writer keepalive window (default 20s), still holds a read-write handle | `systemctl stop antiek`, run the audit, then restart (step 7) |
| high rejection rate in the plan | selectors pulling scanned/low-quality or off-topic works | tighten `--arxiv-category` / `--pd-curated` / drop the bad `--source`; re-dry-run |
| `K failed` on open-access items | publisher PDF fetch blocked or no fetchable PDF | expected for some OA records (DOAJ has no PDF); the others still land |
| servability audit shows a gated doc as servable | a license-resolution regression upstream | restore the step-3 backup; do not serve; file against the connector, not this script |
