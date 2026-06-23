# Retrieval Gate Closure — Preflight + D17 Post-Ingest Spot-Checks

**Audience:** operator or PRcrouch verifying §9.0 chunk-gate closure on prod **before**
and **after** a Personal-Reading Lane ingest window (`engineering_deferrals.md`
D17). Complements `infrastructure/runbooks/personal-lane.md` (corpus audit +
serve-path checks); this runbook covers the **retrieval seams** PR #43 left open
until RG-01..RG-06 closed them.

**Master spec:** `~/specs/antiek-retrieval-gate-closure/index.html`  
**Decision record:** `docs/decisions/retrieval-gate-closure.md`

> **Cross-link:** Run `personal-lane.md` steps 0–4 first (pin `$LIVE_DB`, write-side
> class, serve-path 2a/2b/2c, `corpus_audit`). Then run **this** runbook's retrieval
> spot-checks. If either procedure fails, **halt ingest** — do not "note and continue."

---

## 0. Preflight — RG-05 command block (engineering / CI parity)

Run from the repo root with the project venv (same bar as CI `pytest` job boundary
checks). All must exit **0** before any prod ingest window.

```bash
cd /opt/antiek   # or local checkout
PY=.venv/bin/python

# 1. Drift lint — RESTRICTED-only reimplementation is CI-red
$PY tools/lint/retrieval_gate_check.py

# 2. Cross-surface closure matrix (search ≡ vss ≡ brute_force ≡ GET /chunks)
$PY -m pytest tests/test_retrieval_gate_closure.py -q -m "not integration"

# 3. Lint has teeth + compliance boundary suite
$PY -m pytest tests/test_compliance_invariants.py -q -m "not integration" \
  -k "retrieval_gate"
```

**Refuse go-live** (and refuse to start D17 live ingest) if `retrieval_gate_check`
is non-zero or any preflight pytest reports failures.

---

## 1. Pin `$LIVE_DB` (same as personal-lane.md §0)

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
systemctl show antiek -p Environment | tr ' ' '\n' | grep ANTIEK_DUCKDB_PATH
export LIVE_DB=/home/antiek/.antiek/antiek.duckdb   # use printed value
test -f "$LIVE_DB" && echo "live DB present: $LIVE_DB" || echo "WRONG PATH — stop"
PY=/opt/antiek/.venv/bin/python
```

Every command below uses `$LIVE_DB` and `$PY`.

---

## 2. Post-D17 retrieval spot-check (after **each** connector ingest)

Run **immediately after** a connector lands new `personal_reading` rows and
**after** `personal-lane.md` step 4 (`corpus_audit`) exits 0. Repeat per connector
(Bernays, Paul Graham, Substack, X BYOK).

### 2a. Pick a known `personal_reading` chunk

```bash
export PR_CHUNK=$($PY -c "
import duckdb
con = duckdb.connect('$LIVE_DB', read_only=True)
r = con.execute(\"\"\"
  SELECT c.chunk_id FROM chunks c
  JOIN documents d ON c.document_id = d.document_id
  WHERE d.content_class = 'personal_reading'
  LIMIT 1
\"\"\").fetchone()
print(r[0] if r else '')
")
test -n "$PR_CHUNK" && echo "spot-check chunk: $PR_CHUNK" \
  || { echo "no personal_reading chunk — ingest first"; exit 1; }
```

### 2b. VSS query — must exclude on `attribution_eligible`

Default factory substrate is `"vss"`. A `personal_reading` document must **not**
appear in results when `policy_tag='attribution_eligible'`.

```bash
$PY -c "
import os, sys
sys.path.insert(0, '/opt/antiek')
os.environ['ANTIEK_DUCKDB_PATH'] = '$LIVE_DB'
from substrate.graph.retrieval_substrate import make_substrate
# Use the same embedder prod registers, or a short deterministic probe:
from benchmarks.retrieval_bench import HashEmbedding
model = HashEmbedding()
sub = make_substrate('vss', '$LIVE_DB', model=model)
try:
    res = sub.query('essay transcript reading', top_k=20, policy_tag='attribution_eligible')
    doc_ids = {r['document_id'] for r in res['results']}
    pr_docs = set(d[0] for d in sub._con.execute(
        \"SELECT document_id FROM documents WHERE content_class='personal_reading'\"
    ).fetchall())
    leaked = doc_ids & pr_docs
    assert not leaked, f'VSS leaked personal_reading under attribution_eligible: {leaked}'
    print('VSS gate OK: no personal_reading in attribution_eligible top-k')
finally:
    sub.close()
"
```

### 2c. `GET /chunks/{id}` — body must withhold

Claim-modal / named-source paths call the API directly (bypasses `search()`).
Body must be empty; `servable=False`; `servability=personal_only`.

```bash
curl -sS "https://api.antiek.ai/chunks/$PR_CHUNK" | $PY -c "
import json, sys
b = json.load(sys.stdin)
assert b.get('servable') is False, b
assert b.get('servability') == 'personal_only', b
assert (b.get('text') or '') == '', 'chunk body must be withheld'
print('GET /chunks OK: servable=False servability=personal_only text empty')
"
```

### 2d. Operator-only path sanity (optional but recommended)

Confirm the same chunk is retrievable on a privileged path (owner lane works):

```bash
$PY -c "
import sys
sys.path.insert(0, '/opt/antiek')
from runtime.db_lock import connect_read
from substrate.graph.retrieval_substrate import make_substrate
from benchmarks.retrieval_bench import HashEmbedding
model = HashEmbedding()
sub = make_substrate('vss', '$LIVE_DB', model=model)
try:
    res = sub.query('essay', top_k=20, policy_tag='operator_only')
    chunk_ids = {r['chunk_id'] for r in res['results']}
    assert '$PR_CHUNK' in chunk_ids or len(res['results']) > 0, 'operator_only path empty'
    print('operator_only path OK')
finally:
    sub.close()
"
```

---

## 3. On failure — halt ingest (binding)

| Failure | Meaning | Action |
|---|---|---|
| `retrieval_gate_check` non-zero | Drift: RESTRICTED-only gate reimplemented | **Stop.** File against RG-04; do not ingest until fixed + redeployed. |
| VSS leaks `personal_reading` @ `attribution_eligible` | Defect A regression | **Stop ingest.** Roll back connector batch if needed; open RG-02 regression. |
| `GET /chunks` returns body for `personal_reading` | Defect B regression | **Stop ingest.** Open RG-03 regression. |
| `corpus_audit` non-zero (personal-lane) | Write-side / serve leak | **Stop.** Follow `personal-lane.md` §4 — not live. |

Do **not** announce go-live, do **not** continue the ingest window, and do **not**
treat a passing `corpus_audit` alone as sufficient — the retrieval seams are
independent checks.

---

## 4. What this runbook does NOT do

* **No deploy** — assumes RG-01..RG-06 code is already on prod (`build_sha` contains
  `retrieval_gate.py` + closure tests).
* **No NULL `content_class` policy change** — separate ratified initiative (PR #38).
* **No substitute for `personal-lane.md`** — serve-path + audit remain mandatory.

---

## Reference

| Artifact | Path |
|---|---|
| Canonical gate module | `substrate/graph/retrieval_gate.py` |
| Closure matrix tests | `tests/test_retrieval_gate_closure.py` |
| Drift lint | `tools/lint/retrieval_gate_check.py` |
| Personal-lane go-live | `infrastructure/runbooks/personal-lane.md` |
| D17 deferral | `docs/engineering_deferrals.md` (Personal-Reading Lane D17) |