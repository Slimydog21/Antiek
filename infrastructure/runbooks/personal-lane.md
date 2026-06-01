# Personal-Reading Lane — Cold-Operator Verify + Go-Live Runbook (audit-gated)

**Audience**: the operator, months from now, who has never gone live with the
personal-reading lane. This is the **operator-only** procedure to verify the
lane both directions on the live prod substrate and to **refuse go-live unless
the standing audit exits 0**.

The lane (SPR-01..SPR-09) lets the OWNER fetch third-party copyrighted content
(a Paul Graham essay, a YouTube transcript, a subscribed Substack post, the
owner's own tweets) for their **own private reading** — landing it at
`content_class='personal_reading'` — while NEVER serving that body to the
public, NEVER ad-attributing it, and NEVER putting it in a training/RL export.
This runbook proves those properties hold on the live corpus before you go live.

The agent builds + verifies the lane code and the audit (`substrate/corpus_audit.py`)
and can run all of it against a temp/staging DB. The agent **never** runs a real
prod write and **never** makes the go-live decision — the go-live decision is
yours, and it is gated on the audit exit code below.

> **This is the verify-and-go-live procedure, not a deploy.** Deploy mechanics
> (ansible, Cloudflare Pages) are operator/PRcrouch-owned and §16 box-bounded —
> out of scope here. This runbook assumes the lane code is already deployed; it
> tells you how to confirm the lane is correct on the live corpus and when you
> are (and are not) allowed to go live.

---

## 0. Preflight — pin `$LIVE_DB` from the systemd unit (do this first)

The live DB path lives **only** in the systemd units (`ANTIEK_DUCKDB_PATH`). An
interactive shell does **not** inherit it, so a bare `python` targets the orphan
`~/.antiek/research_graph.duckdb` (the `substrate.constants.DUCKDB_PATH` default)
instead of the real prod file — and you would audit the wrong DB.

* **Symptom if skipped**: the audit "passes" against an empty/orphan DB while the
  live corpus is never checked — a green light that proves nothing about prod.
* **Check** — pin the live path the unit actually uses, and use it for EVERY
  command below. Never let `--db-path` default.

  ```bash
  ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
  # The single source of truth for the live path:
  systemctl show antiek -p Environment | tr ' ' '\n' | grep ANTIEK_DUCKDB_PATH
  # -> ANTIEK_DUCKDB_PATH=/home/antiek/.antiek/antiek.duckdb   (example)
  export LIVE_DB=/home/antiek/.antiek/antiek.duckdb   # use the value printed above
  test -f "$LIVE_DB" && echo "live DB present: $LIVE_DB" || echo "WRONG PATH — stop"
  ```

  Every command below uses `$LIVE_DB`.

> **§16 box-bounded / read-only**: the audit opens the DB **read-only**
> (`runtime.db_lock.connect_read`) and never takes the write lock, so it is safe
> to run while `antiek.service` serves. Do not stop any service for this
> procedure; there is no daemon, queue, or second writer here.

---

## 1. Confirm the lane connectors land `personal_reading` (write-side)

The three third-party connectors must land `content_class='personal_reading'`
(or, with a positive verified basis, a servable/open class) — **never** a
servable default and **never** a NULL that serves. The static BINDING in the
audit (step 4) enforces this at the source level. Confirm the live corpus shows
the lane class present and on the third-party rows:

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -c "
import duckdb
con = duckdb.connect('$LIVE_DB', read_only=True)
for row in con.execute('''
  SELECT document_type, content_class, COUNT(*) AS n
    FROM documents
   WHERE document_type IN ('web_article','video_transcript','social_thread','newsletter_post')
   GROUP BY 1, 2 ORDER BY 1, 2
''').fetchall():
    print(row)
"
```

Every third-party row should read `personal_reading` (or a positive class WITH a
basis). A third-party row on a servable class with no basis is the §9.0 leak —
step 4's `third_party_servable` check will fail go-live on it.

## 2. Verify the lane BOTH directions (the proof this runbook exists for)

Pick one real `personal_reading` `document_id` from step 1 (any row whose
`content_class='personal_reading'`). Export it for the checks below:

```bash
export PR_DOC=$(sudo -u antiek /opt/antiek/.venv/bin/python -c "
import duckdb
con = duckdb.connect('$LIVE_DB', read_only=True)
r = con.execute(\"SELECT document_id FROM documents WHERE content_class='personal_reading' LIMIT 1\").fetchone()
print(r[0] if r else '')
")
test -n "$PR_DOC" && echo "personal_reading doc: $PR_DOC" || echo "no personal_reading row yet — ingest one first (SPR-04..08)"
```

### 2a. OWNER read path renders the FULL body

The owner's personal-space read path serves the full body of a `personal_reading`
document (`serve_full_text(con, doc, owner=True)` → `full_text` populated, the
lane's whole purpose):

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -c "
import duckdb
from substrate.books.serve import serve_full_text
con = duckdb.connect('$LIVE_DB', read_only=True)
r = serve_full_text(con, '$PR_DOC', owner=True)
assert r.full_text is not None and len(r.full_text) > 0, 'owner must read the FULL body'
assert r.servable is False, 'personal_reading is never publicly servable, even to the owner'
print('OWNER full body OK: %d chars, servable=%s, reason=%s' % (len(r.full_text), r.servable, r.reason))
"
```

### 2b. PUBLIC serve path WITHHOLDS the body

The public projection (`owner=False`, the default the public API uses) treats
`personal_reading` exactly like a gated row — body withheld, at most a bounded
snippet (`SERVE_SNIPPET_MAX_CHARS=500`, `substrate/constants.py`), full text
`None`:

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -c "
from substrate.constants import SERVE_SNIPPET_MAX_CHARS
import duckdb
from substrate.books.serve import serve_full_text
con = duckdb.connect('$LIVE_DB', read_only=True)
r = serve_full_text(con, '$PR_DOC')                       # public projection (owner defaults False)
assert r.full_text is None, 'PUBLIC path MUST NOT render personal_reading full text'
assert r.servable is False, 'personal_reading is never publicly servable'
snip = r.snippet or ''
assert len(snip) <= SERVE_SNIPPET_MAX_CHARS, 'snippet must be <= %d chars' % SERVE_SNIPPET_MAX_CHARS
print('PUBLIC withhold OK: full_text=None, servable=False, snippet<=%d (%d)' % (SERVE_SNIPPET_MAX_CHARS, len(snip)))
"
```

### 2c. The same document accrues ZERO ad attribution

`personal_reading` is non-attributable (`is_attribution_eligible` returns False)
and absent from the public graph (`monetization_eligible('personal_reading')` is
False), so it accrues zero ad attribution and zero IP escrow by construction:

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -c "
from substrate.ad_inventory.attribution import monetization_eligible
from substrate.collective_graph.eligibility import (
    CollectiveGraphDocument, is_attribution_eligible)
from substrate.quality_gate import QualityGateResult, QualityGateVerdict
probe = CollectiveGraphDocument(
    document_id='$PR_DOC', note_id='$PR_DOC', owner_user_id='operator-verify',
    content_class='personal_reading',
    quality_gate_result=QualityGateResult(verdict=QualityGateVerdict.PASS_PUBLIC, checks=()),
)
assert is_attribution_eligible(probe) is False, 'personal_reading must NOT be attribution-eligible'
assert monetization_eligible('personal_reading') is False, 'personal_reading must NOT be in the public graph'
print('ZERO attribution OK: attribution_eligible=False, monetization_eligible=False')
"
```

If any of 2a/2b/2c fails, **stop** — the lane is not correct on this row. Do not
go live; file the failure against the owning sprint (serve = SPR-01/SPR-09,
attribution = SPR-01).

## 3. (Optional) Confirm no `personal_reading` reaches a training/RL export

There is **no** training/RL export builder on prod today, so this is a
forward-guard: the `personal_reading_not_in_training` audit check (step 4) scans
whatever export surfaces are declared in `substrate.corpus_audit.TRAINING_EXPORT_TABLES`
(empty today) and asserts zero `personal_reading` rows appear. The X no-training
constraint (`docs/operator_gate_actions.md`) is the human-readable counterpart:
when a real export builder is added, its source table MUST be declared there so
this check guards it. Nothing to run today beyond step 4's check.

## 4. Run the standing audit — go-live REFUSED unless it exits 0

Run the extended audit **against `$LIVE_DB`** (the same DB the units serve). It
opens the DB **read-only** and asserts all corpus-level invariants — including
the three personal-lane checks — plus THE BINDING, and **exits 0 only when ALL
pass**:

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -m substrate.corpus_audit \
    --db-path "$LIVE_DB"
echo "audit exit code: $?"
```

The checks (each links to its owning sprint):

| Check | What it proves | Owning sprint |
|---|---|---|
| `servable_without_basis` | every servable work has a non-empty `license_basis` | SPR-02 |
| `gated_body_leak` | no body renders full text on the public serve projection that shouldn't (b1 gated row + b2 servable-class-over-gated-basis) | SPR-02 |
| `dedup_identity` | no two distinct docs share a stable identity | SPR-04 |
| `extraction_quality` | no HTML-as-body, no empty body | SPR-03 |
| `budget_ceiling` | corpus within the SPR-09 box ceiling | SPR-09 |
| `third_party_servable` | no third-party document_type on a servable class without a basis (must be `personal_reading`) | SPR-02 |
| `personal_reading_nonattributable` | every `personal_reading` row is non-attributable AND absent from the public graph | SPR-10 |
| `personal_reading_not_in_training` | no `personal_reading` document_id appears in any declared training/RL export surface (forward-guard) | SPR-10 |
| `content_class_binding` | ZERO connectors assign `content_class` outside `classify()` / an imported lane constant (static) | SPR-10 |

> **GO-LIVE GATE (binding): if the audit exits non-zero, you are NOT live.**
> A non-zero exit means a §9.0 / lane / dedup / quality / budget / single-source-
> rights invariant is violated on the live corpus. **Do not announce, do not
> serve, do not enable the lane publicly.** The single failure this whole spec
> exists to prevent — the owner's private third-party reading served to the
> public or ad-attributed — is exactly what `third_party_servable`,
> `personal_reading_nonattributable`, and `gated_body_leak` catch. Trust the exit
> code over your memory: **audit exits 0 → you may go live; non-zero → you are
> NOT live.** Restore the pre-change backup (see `corpus-mass-ingest.md`
> Rollback) and file the failing check against its owning sprint.

## 5. Post-go-live — confirm the real corpus state

```bash
sudo -u antiek /opt/antiek/.venv/bin/python -m substrate.corpus_audit \
    --summary --db-path "$LIVE_DB"
```

Prints total docs + DB bytes + chunk count, the servable/gated split, by-source
counts, and the last-audit verdict. The verdict line is sourced from the **same
`AuditResult`** the step-4 audit returned — one source of truth, so the dashboard
never disagrees with the gate. Confirm the verdict reads `PASS` and the
servable/gated split matches what you expect (personal_reading rows count in the
gated/withheld complement, never the servable count).

---

## What this procedure does NOT do

* **It does not modify `payout.py` / `stripe_connect/`.** `personal_reading`
  accrues zero ad attribution + zero IP escrow by construction; this runbook
  touches no money path.
* **It does not deploy.** No ansible, no Cloudflare Pages redeploy — deploy is
  operator/PRcrouch-owned and §16 box-bounded. This is verify-and-go-live only.
* **It does not bypass the single-writer invariant.** The audit is read-only
  (`connect_read`); there is no daemon, queue, or second writer.
* **It does not relax the public-corpus rights gate.** The books-family audit
  (`assert_no_content_class_bypass` over books/textbooks/papers/opt_in) keeps its
  exact semantics; the lane EXTENDS it to the web family, never loosens it.
* **It is not a shadow-library path.** The lane covers content the owner fetched
  through lawful means (subscribed Substack `/feed`, PG public site, X via the
  owner's own API key); the acquisition method itself must be lawful — the lane
  cures serving, not a fetch ToS breach.

## Possible follow-on (out of scope here)

A reviewer may argue the go-live gate should be a checked-in `preflight.sh` that
runs the audit and exits non-zero, harder to skip than a markdown instruction.
That is a legitimate hardening, but deploy mechanics are operator/PRcrouch-owned
and §16 box-bounded (out of scope for this lane sprint). The enforcement is
already real: the audit **command itself** exits non-zero — this runbook just
tells you to trust the exit code. If you later want a wrapper script, it is a
separate deploy-owned follow-on; do not smuggle it in here.
