# Corpus Mass-Ingest — Cold-Operator Go-Live Runbook (no-outage, audit-gated)

**Audience**: the operator, six months from now, who has never run an ingest.
This is the **operator-only** procedure for landing a rights-correct,
quality-gated batch of documents into the live prod substrate **without taking
the API down** and **without going live until the standing audit exits 0**.

The agent builds + verifies the orchestrator (`tools/run_corpus_ingest.py`), the
staging→merge tooling (`tools/merge_staging.py`), and the audit
(`substrate/corpus_audit.py`), and can run all of them `--dry-run` / against a
temp DB. The agent **never** runs a real prod write: the backup, the
`--allow-prod-write` / staging merge, and the go-live decision are yours.

> **This SUPERSEDES the stop-both-writers model in `corpus-ingest.md`.** That
> older runbook stopped `antiek.service` for the whole ingest (an outage).
> SPR-01's staging→merge keeps the API UP: the ingest writes to a *separate
> staging DuckDB* off the hot path, and only a brief `db_lock` merge touches the
> live writer. **Do not stop either service for the ingest body.** (See
> Preflight 4.)

---

## 0. Preflight landmines — CHECK ALL FOUR before you write anything

These are the four gotchas the first real ingest hit. Each is a numbered check
with its exact symptom-if-skipped and the one-line check that prevents it. They
are not prose afterthoughts — **run each check and confirm it before step 1.**

### Preflight 1 — `ANTIEK_DUCKDB_PATH` and `--db-path` must point at the SAME live DB

The live DB path lives **only** in the systemd units (`ANTIEK_DUCKDB_PATH`).
An interactive shell does **not** inherit it, so a bare `python` targets the
*orphan* `~/.antiek/research_graph.duckdb` (the `substrate.constants.DUCKDB_PATH`
default) instead of the real prod file.

* **Symptom if skipped**: the ingest "succeeds" but writes to an orphan DB the
  API never reads (a useless ingest); worse, it also bypasses the prod-write
  guard because the path isn't the prod default. The audit then reports the
  *orphan* corpus, not the live one.
* **Check** — confirm the live path the unit actually uses, and pin BOTH the
  ingest `--db-path`/merge `--live-db` AND the audit `--db-path` to it:

  ```bash
  ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
  # The single source of truth for the live path:
  systemctl show antiek -p Environment | tr ' ' '\n' | grep ANTIEK_DUCKDB_PATH
  # -> ANTIEK_DUCKDB_PATH=/home/antiek/.antiek/antiek.duckdb   (example)
  export LIVE_DB=/home/antiek/.antiek/antiek.duckdb   # use the value printed above
  test -f "$LIVE_DB" && echo "live DB present: $LIVE_DB" || echo "WRONG PATH — stop"
  ```

  Every command below uses `$LIVE_DB`. **Never** let `--db-path` /
  `--live-db` / the audit `--db-path` default — always pass `$LIVE_DB`.

### Preflight 2 — Ansible `template:` renders from the CONTROL-NODE checkout

Any templated ansible play (`deploy.yml`, anything with a `template:` task)
renders the template from the **checkout you run `ansible-playbook` from on the
control node**, NOT from the box. A stale clone renders stale config; a clone
missing the real gitignored `inventory.ini` can't even target the host.

* **Symptom if skipped**: you "deployed the fix" but the box got the old
  rendered file (the control-node checkout was behind), or the play fails to
  find the host because `inventory.ini` is the committed `.example`, not the
  real one.
* **Check** — run templated plays only from a checkout that has BOTH the fix AND
  the real `inventory.ini`:

  ```bash
  cd ~/Desktop/Antiek               # the control-node checkout
  git fetch && git log --oneline -1 # confirm it has the fix you intend to ship
  test -f infrastructure/ansible/inventory.ini \
    && echo "real inventory present" \
    || echo "MISSING inventory.ini (you only have the .example) — stop"
  ```

  This runbook's ingest body does NOT run a templated play — the only ansible
  here is the backup (Preflight-clean, no template). But if you touch any
  templated play, this check is binding.

### Preflight 3 — the Caddy `@api_routes` allowlist is a hand-maintained allowlist

The reverse proxy in front of `api.antiek.ai` matches a **hardcoded
`@api_routes` allowlist**. A new public route 404s behind the proxy until it is
added to that list — the allowlist drifts behind the app.

* **Symptom if skipped**: a freshly-added endpoint returns 404 through
  `https://api.antiek.ai/...` even though it works on `localhost` on the box.
* **Check** — a corpus mass-ingest adds **no new public route** (it adds
  documents, not endpoints), so this check is a **no-op for this procedure** —
  confirm you are not also shipping a new route. If you are, add it to the Caddy
  `@api_routes` block and reload Caddy before relying on it. Recorded here so the
  next operator who *does* add a route does not relearn it the hard way.

### Preflight 4 — do NOT stop either service for the ingest body

The substrate is single-writer (`--workers 1` uvicorn; the flock lives in
`runtime/db_lock.py`). Two services hold relevance: `antiek.service` (the API)
and `antiek-continuous-research.service` (the §7 daemon). The **old** model
stopped both for the whole ingest — an outage. SPR-01's staging→merge makes that
unnecessary: the ingest writes a **separate staging DuckDB**; only the brief
`merge_staging.py` step takes the live `connect_write` flock, for seconds.

* **Symptom if skipped**: you stop `antiek.service` for the full ingest and the
  API is **down for the entire batch** (minutes-to-hours of network fetches) —
  the exact outage SPR-01 was built to remove. Or you stop
  `antiek-continuous-research` unnecessarily and lose §7 gap-detection for no
  reason.
* **Check** — confirm BOTH services stay active across the ingest; only the
  merge window touches the writer (and `merge_staging.py` acquires + releases the
  flock itself in seconds — you do not stop anything):

  ```bash
  systemctl is-active antiek antiek-continuous-research   # expect: active / active
  ```

  If a previous attempt left `antiek` stopped, **start it** — this procedure
  runs with the API UP.

---

## 1. Dry-run locally and read the plan (writes nothing)

Always dry-run first. The dry-run runs the FULL pipeline — discovery, body fetch
for assessment, dedup, the quality gate — and writes nothing.

```bash
cd ~/Desktop/Antiek
./.venv/bin/python -m tools.run_corpus_ingest \
    --source arxiv --arxiv-category cs.LG \
    --source public_domain --pd-curated \
    --limit 25 --dry-run
```

Read the printed plan: **dedup** (kept vs collapsed + the key that collapsed
each drop), **quality gate** (assessed / passed / reject RATE with a per-item
reason), and **would ingest** (the final set; OA bodies fetched at ingest time
are flagged `[body not assessed pre-ingest]` — expected, not a defect). If the
plan looks wrong, adjust `--source` / selectors / `--limit` and dry-run again.
Nothing has touched any DB.

## 2. Back up prod BEFORE any prod write

```bash
cd ~/Desktop/Antiek/infrastructure/ansible
ansible-playbook -i inventory.ini playbooks/backup.yml
```

This runs the same `/usr/local/bin/antiek-backup` the nightly cron runs
(snapshot → R2). Confirm `failed=0` and a fresh archive in the output. **Do not
proceed without a good backup** — a corpus ingest appends many documents and is
not trivially reversible in place. (Preflight 2's control-node check applies if
you customised the play.)

## 3. Stage the ingest off the hot path — API STAYS UP (no service stop)

On the VM, write the batch to a **separate staging DuckDB**. The live DB keeps
serving; nothing is stopped (Preflight 4).

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
# $LIVE_DB was pinned in Preflight 1.
STAGING_DB=/home/antiek/.antiek/staging-$(date +%Y%m%d-%H%M%S).duckdb

sudo -u antiek /opt/antiek/.venv/bin/python -m tools.run_corpus_ingest \
    --source arxiv --arxiv-category cs.LG \
    --source public_domain --pd-curated \
    --limit 25 \
    --staging-db "$STAGING_DB"
```

The orchestrator reports `ingested N / M planned; K failed`. Per-item failures
are isolated — one bad fetch never aborts the batch. Re-running is safe: dedup
collapses within a run and the connectors key on content-stable identity, so an
already-present work is not duplicated.

> For a standing, box-bounded fill use `--continuous --staging-db "$STAGING_DB"`
> (one process, one in-process loop, paced/halted against the box ceiling — NOT
> a daemon or fan-out). It still merges on a cadence via the same brief-window
> mechanism; the no-stop / staging discipline is identical.

## 4. Merge the staging DB into live — the ONLY writer-touching step (brief)

This is a SINGLE bounded `connect_write` transaction: the staging file is
ATTACHed read-only and every table is copied with a column-explicit anti-join.
The live-writer flock is held for **seconds** (the copy), not the ingest. **No
restart is needed** — the API never went down, and the merge does not require
one. `merge_staging.py` takes and releases the flock itself.

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -m tools.merge_staging \
    --live-db "$LIVE_DB" \
    --staging-db "$STAGING_DB"
```

The merge is idempotent on the content-stable id (a re-merge inserts zero rows)
and atomic (an interruption mid-merge leaves live exactly at its pre-merge
state, resumable by re-running). `antiek.service` keeps serving throughout —
read-only serving connections coexist with the brief write window.

## 5. Verify the writer recovered and the API is healthy (no restart performed)

```bash
systemctl is-active antiek antiek-continuous-research   # expect: active / active
curl -s https://api.antiek.ai/health | jq .registered_providers
```

Both services were never stopped, so this is a confirmation, not a restart.

## 6. Run the standing audit — go-live REFUSED unless it exits 0

Run the audit **against `$LIVE_DB`** (Preflight 1 — the same DB the units serve).
It opens the DB **read-only** (`runtime.db_lock.connect_read`) and never takes
the write lock, so it is safe to run while the API serves.

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -m substrate.corpus_audit \
    --db-path "$LIVE_DB"
echo "audit exit code: $?"
```

It asserts FIVE corpus-level invariants + THE BINDING and **exits 0 only when
ALL pass**, non-zero with the failing check(s) + offending ids otherwise:

| Check | What it proves | Owning sprint |
|---|---|---|
| `servable_without_basis` | every servable work has a non-empty `license_basis` | SPR-02 |
| `gated_body_leak` | no body renders full text on the public serve projection that shouldn't — both (b1) a gated `restricted_pending_opt_in` row AND (b2) a SERVABLE-classed row whose `license_basis` says `GATED:` (a mislabel the serve path would render); asserted against `substrate.books.serve`, not the raw column | SPR-02 |
| `dedup_identity` | no two distinct docs share a stable identity (DOI/ISBN/arXiv/source-id/content-hash) | SPR-04 |
| `extraction_quality` | no HTML-as-body (`<!DO…`), no empty body | SPR-03 |
| `budget_ceiling` | corpus within the SPR-09 box ceiling (DB-size dimension) | SPR-09 |
| `content_class_binding` | ZERO connectors assign `content_class` outside `classify()` (static) | SPR-10 |

> **GO-LIVE GATE (binding): if the audit exits non-zero, you are NOT live.**
> A non-zero exit means a §9.0 / dedup / quality / budget / single-source-rights
> invariant is violated on the live corpus. **Do not announce, do not serve the
> new batch publicly.** Restore the step-2 backup (see Rollback) and file the
> failing check against its owning sprint. The single failure this whole spec
> exists to prevent — one in-copyright work served as full text — is exactly
> what `gated_body_leak` catches. Trust the exit code over your memory.

## 7. Operator dashboard — confirm the real corpus state

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -m substrate.corpus_audit \
    --summary --db-path "$LIVE_DB"
```

Prints total docs + DB bytes + chunk count, the servable/gated split, by-source
counts, and the last-audit verdict. The verdict line is sourced from the **same
`AuditResult`** the step-6 audit returned — one source of truth, so the
dashboard never disagrees with the gate. On the first batch this reads
**31 docs (22 servable / 9 gated), 5,017 chunks**. If the numbers don't match
what the plan said it would ingest, stop and investigate before going live.

---

## Rollback (unhappy path)

A corpus ingest only **appends** documents (+ their chunks/embeddings); it never
modifies existing rows. To undo a bad batch, restore the pre-ingest snapshot —
do NOT hand-delete rows (the document → chunks → claims provenance chain makes
partial deletion error-prone).

```bash
# See disaster-recovery.md for the full restore-from-R2 procedure.
# Restore the step-2 backup over $LIVE_DB. The API stays up except for the
# brief restore swap; no need to stop antiek-continuous-research.
```

Re-running the ingest after a partial failure is safe (idempotent on identity):
the already-merged items are recognised and only the failures retry.

## What this procedure does NOT do

* **It does not modify `payout.py` / `stripe_connect/`.** Escrow accrues via
  `ip_holders.accrue_escrow`; disbursement stays operator-gated on G2 (lawyer
  review) + G3 (publisher opt-in). This runbook touches no money path.
* **It does not run the frontend ansible play.** No `deploy.yml --tags frontend`,
  no Cloudflare Pages redeploy. Adding documents is a substrate write only.
* **It does not stop either service for the ingest body** (Preflight 4). The old
  stop-both-writers model is retired; only the brief merge touches the writer.
* **It does not bypass the single-writer invariant.** Every write goes through
  `runtime.db_lock.connect_write`; the merge is the one bounded window.
* **It is not an Anna's-Archive / shadow-library path.** The orchestrator only
  ingests through the rights-correct connectors; no scraper, no copyrighted
  full-text serving. Out of scope by §9.0 + the SPR-08 spec.
* **It does not change the gates.** SPR-02 owns rights, SPR-03 extraction, SPR-04
  dedup, SPR-09 budget. The audit asserts they hold; a failure is a finding
  routed back to the owning sprint, never a gate tuned here.
