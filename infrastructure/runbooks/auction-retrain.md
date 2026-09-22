# Ad-Auction Retrain — Offline, Gated, Promote-Only-On-Measured-Lift

**Audience**: the operator. This is an **operator-only** promotion procedure.
The agent builds and verifies the pipeline (`substrate/ad_inventory/auction_*`,
`tools/auction_ab_eval.py`) and can run the A/B eval against a local/temp DB or
the bundled synthetic fixture, but it must **never** flip the production
`ANTIEK_LEARNED_AD_RANKER` flag: promoting the learned ranker is a deliberate,
measured, operator decision.

**Time**: ~1 minute to retrain + ~1 minute to read the A/B report + the flag
flip itself. No GPU, no external service — the model is a pure-Python
calibrated logistic over ~9 features and trains/serves in-process on CPU.

**What this does**: pulls the latest recorded ad-selection feedback, retrains
the learned value scorer offline, scores it head-to-head against the current
leader (rule-based by default) via the A/B harness on the **platform's unit of
account** (the SPR-05 per-second attention-weighted value per impression), and
promotes the learned ranker **only if it measurably beats** rule-based. The
whole thing is offline + read-only against recorded data; the only write is a
small JSON model artifact on disk, and the only "deploy" is a config flag flip.

> **Status (2026-09-22): the promote path is BLOCKED, and that is the tooling,
> not your environment.** `tools/auction_ab_eval.py` cannot read recorded
> sessions yet — every branch of `_load_recorded_sessions` returns `[]`, because
> the impression ⋈ frame-attention ⋈ inventory join is deliberately unwritten
> (see the NOTE at `tools/auction_ab_eval.py:393`). `--db-path` therefore always
> falls back to the bundled synthetic fixture, the "positive lift on recorded
> data" gate below cannot be satisfied by any invocation available today, and
> `ANTIEK_LEARNED_AD_RANKER` stays off. Step 1 and the §16 import check are safe
> and useful now; steps 2-4 are the procedure for the day that join lands.

---

## The pieces (one-owner-per-layer)

| Layer | File | Role |
|---|---|---|
| Features | `substrate/ad_inventory/auction_features.py` | pure `(context, candidate) → vector`; no label leakage, denylist honored |
| Model | `substrate/ad_inventory/auction_model.py` | pure-Python calibrated logistic; train / serialize / load / predict |
| Ranker (seam) | `substrate/ad_inventory/auction_ranker.py` | re-ranks behind `select_targeted_ad`; degrades to rule-based on any failure |
| A/B eval | `tools/auction_ab_eval.py` | scores learned vs rule on recorded sessions; honest lift |
| Flag | env `ANTIEK_LEARNED_AD_RANKER` (+ `ANTIEK_AD_RANKER_MODEL_PATH`) | flips learned↔rule with no code change |

---

## Happy path

### 1. Run the A/B eval first (decide BEFORE you train-to-deploy)

Always eval before promoting. The eval trains a model in memory and reports the
lift; it writes nothing.

```bash
# On the prod VM — the checkout is /opt/antiek and the venv is /opt/antiek/.venv
# (deploy.yml git-pulls into antiek_install_dir; antiek.service.j2 runs out of it):
cd /opt/antiek
# Against the synthetic fixture (no recorded data needed — labeled '[synthetic]'):
./.venv/bin/python tools/auction_ab_eval.py

# Same fixture, same numbers, on the operator's Mac control node:
cd ~/Desktop/Antiek && ./.venv/bin/python tools/auction_ab_eval.py
```

The recorded-data run is the one that decides anything, and it is **not usable
yet** (see the status note above). When the join lands, point it at the DB the
service itself opens — `antiek.duckdb`, from
`ANTIEK_DUCKDB_PATH={{ antiek_state_dir }}/antiek.duckdb` in
`infrastructure/ansible/templates/antiek.service.j2:51` — and not at
`research_graph.duckdb`, a filename that appears nowhere in the ansible tree:

```bash
# NOT YET: today this reports 'synthetic' no matter what you point it at.
cd /opt/antiek
./.venv/bin/python tools/auction_ab_eval.py \
    --db-path /home/antiek/.antiek/antiek.duckdb
```

Read the report top-down and start at the **data source** line, not at the
LEADER line. The leader means nothing until the source says `recorded:`.

- **data source**: `synthetic`, `recorded:<path> (n=…)`, or `synthetic (recorded
  corpus at <path> empty/insufficient — rule-based leads until real feedback
  accrues)`. Anything that is not `recorded:` means the numbers under it came
  from the bundled fixture, and you **stop there**. Note what that third label
  does not tell you: a typo'd path, the wrong filename and a genuinely empty
  corpus print the identical line and all exit 0, because the loader catches
  every error and returns `[]`. It is not evidence that feedback has yet to
  accrue — confirm the file you named is the one the service writes before you
  conclude anything from it.
- **lift (learned - rule)**: the honest number — positive, zero, or negative.
- **LEADER under measurably-better rule**: `LEARNED` only when the lift is
  strictly positive; otherwise `RULE-BASED` stays the leader. On the synthetic
  fixture this line reads `LEADER … LEARNED` at `+2.61%` on **every** run — that
  is a property of the fixture, not a measurement of production, and it is not a
  promote signal.

If the leader is `RULE-BASED`, you are done — do not promote. If the data source
is not `recorded:`, you are equally done, whatever the leader says. The learned
ranker leads ONLY on a positive measured lift over recorded data.

### 2. Serialize the trained model to an artifact

Only if step 1 shows a positive lift on **recorded** data — which, until the
recorded-session join lands, it cannot. Train and write the small JSON artifact
(a handful of floats + a version stamp):

Use the SHARED training helper `train_from_sessions(sessions)` — the one owner
of the session → (feature, label) → model transform. The A/B harness's
`evaluate()` calls the SAME helper, so the artifact you promote is trained by
exactly the code the eval measured (no hand-rolled, drift-prone copy of the
loop here). It is deterministic: the same sessions yield a byte-identical
artifact.

```bash
cd /opt/antiek
./.venv/bin/python - <<'PY'
import sys
from tools.auction_ab_eval import load_sessions, train_from_sessions

sessions, source = load_sessions("/home/antiek/.antiek/antiek.duckdb")
print("data source:", source)
if not source.startswith("recorded:"):
    sys.exit("REFUSING to promote: not trained on recorded data (%s)" % source)
model = train_from_sessions(sessions)
open("/home/antiek/.antiek/auction_model.json", "w").write(model.to_json())
print("wrote artifact; n_train =", model.n_train)
PY
```

The `source.startswith("recorded:")` guard is load-bearing, not decoration.
Without it this block cannot fail: `load_sessions` falls back to the fixture on
any DB problem, training succeeds, and the script cheerfully prints
`wrote artifact; n_train = 800` after writing a fixture-trained model to the
production artifact path. Run today it exits 1 with `REFUSING to promote` and
writes nothing, which is the correct outcome.

> Note: `train_from_sessions` trains on ALL the sessions you give it — for the
> promoted production artifact that is intentional (use every recorded example).
> The A/B harness's `evaluate()` instead trains on a TRAIN partition and reports
> lift on a HELD-OUT partition, so the headline lift you read in step 1 is an
> honest out-of-sample number, not the in-sample fit.

The artifact stamps `feature_schema_version` + `model_schema_version`; loading
refuses a stale feature schema (the coefficients would be positionally wrong),
so a feature change forces a retrain rather than silently mispredicting.

### 3. Promote — flip the flag (the gated config change)

Promotion is a **config flip**, not an auto-deploy. Point the substrate at the
artifact and enable the learned path:

```bash
# In /etc/antiek/secrets.env — the unit's EnvironmentFile=, and the only env that
# survives a deploy. Do NOT hand-add an Environment= line to
# /etc/systemd/system/antiek.service: deploy.yml re-renders that unit from
# antiek.service.j2 every run and your line silently disappears (and
# EnvironmentFile= wins over Environment= for the same key regardless).
# Do NOT hardcode in source.
ANTIEK_AD_RANKER_MODEL_PATH=/home/antiek/.antiek/auction_model.json
ANTIEK_LEARNED_AD_RANKER=1
```

Restart the service so it picks up the env:

```bash
systemctl restart antiek
systemctl is-active antiek          # expect: active
```

Callers are unchanged — `select_targeted_ad` transparently routes through the
learned ranker when the flag is on, and degrades to rule-based on any model
problem (a missing/stale artifact never blanks a slot).

### 4. Roll back instantly if anything looks off

Rollback is the same flag, flipped off — no redeploy, no model surgery:

```bash
# Unset, or set to 0, in /etc/antiek/secrets.env — the flag reads as ON only for
# 1/true/on/yes (auction_ranker._TRUTHY), so 0 and a deleted line both disable it:
ANTIEK_LEARNED_AD_RANKER=0
systemctl restart antiek
```

The matcher is immediately back to the exact rule-based behavior it had before
promotion.

---

## Unhappy path — the eval says rule-based leads

This is the **expected** outcome on a fresh integration branch and stays the
honest answer until real feedback accrues. Do nothing: leave the flag off
(rule-based). Re-run the eval periodically as recorded feedback grows — noting
that until the recorded-session join lands the eval cannot see that growth at
all, so a re-run is a check on the tooling shipping, not on the corpus filling.
Promote only when a positive lift on **recorded** data appears. A learned ranker
that leads without a proven lift is the failure mode this whole procedure exists
to prevent.

## What this procedure does NOT do

- **It does not train online or stream.** Training is a discrete offline batch
  (deterministic gradient descent, fixed iterations, zero init) → byte-identical
  coefficients on the same data. There is no online/incremental update.
- **It does not auto-promote.** The flag flip is the operator's, gated on the
  measured lift. The agent never flips the prod flag.
- **It does not introduce a runtime/GPU/network surface (§16).** The model is
  pure-Python stdlib arithmetic; inference is a dot product + two sigmoids
  in-process. No second runtime, no model server, no GPU, no network call at
  predict time. Verify by listing what the module actually imports — walking the
  AST and printing node objects, as an earlier version of this line did, prints
  54KB of `<ast.Module object at 0x…>` and names no module at all:

  ```bash
  cd /opt/antiek          # or the Mac checkout — `./.venv/...` is relative
  ./.venv/bin/python -c "
  import ast, substrate.ad_inventory.auction_model as m
  mods = set()
  for n in ast.walk(ast.parse(open(m.__file__).read())):
      if isinstance(n, ast.Import): mods.update(a.name for a in n.names)
      elif isinstance(n, ast.ImportFrom): mods.add(n.module or '')
  print(sorted(mods))"
  # ['__future__', 'auction_features', 'dataclasses', 'json', 'math']
  ```

  Stdlib plus the sibling feature module, nothing else (the test
  `test_inference_imports_nothing_heavy` enforces this).
- **It does not touch payouts or attribution.** The ranker picks which ad to
  SHOW; it never writes escrow, never touches `payout.py` / Stripe Connect, and
  never changes the SPR-04 attribution algorithms or the SPR-09 conservation
  invariant. It only CONSUMES the per-second value as a training label.
- **It does not change advertiser onboarding or targeting surfaces.** It uses
  the existing `PageContext` / `InventoryTargeting` signals and honors the
  targeting denylist (no gated book text or reader notes as features).
- **It does not add a new collection surface.** Features are derived only from
  signals the substrate already records.

## Re-running is safe (idempotent on identity)

Re-training on the same recorded data yields a byte-identical artifact (no
randomness). Re-running the A/B eval is read-only and side-effect-free. Promoting
twice with the same artifact is a no-op.

## Common failure modes

| Symptom | Most likely cause | Fix |
|---|---|---|
| eval prints `recorded corpus … empty/insufficient` | today this is unconditional — the recorded loader returns `[]` on every branch, and returns the same `[]` for a missing file, a missing `reader_impressions` table and a typo'd path | expected; leave the flag off. Before reading it as "no feedback yet", confirm you passed `/home/antiek/.antiek/antiek.duckdb`: the message cannot distinguish a wrong path from an empty corpus |
| `LEADER … LEARNED` with a `synthetic` data source | the bundled fixture, which leads LEARNED at `+2.61%` on every run | do not promote — the leader line is evidence only when the source reads `recorded:` |
| `LEADER … RULE-BASED` on recorded data | learned did not beat rule-based | do not promote; the measurably-better gate is working |
| slot fills look unchanged after flipping the flag | `ANTIEK_AD_RANKER_MODEL_PATH` unset / artifact missing / stale schema | the ranker degraded to rule-based (by design, and silently). Nothing is logged — see "Diagnosing a silent degrade" below; then fix the path or retrain to the current feature schema |
| eval lift looks implausibly high (≈100%) | label leakage or a degenerate fixture | check `feature_provenance()` carries no served-outcome term: `./.venv/bin/python -m pytest -q tests/test_auction_features.py::test_no_label_term_in_feature_provenance_naming_discipline` enforces it (the name an older copy of this table gave, `test_no_label_field_in_feature_provenance`, was renamed out of the suite — pytest answers it with exit 4 as a node id, exit 5 and "9 deselected" as a `-k` filter, never a failure you would notice) |

### Diagnosing a silent degrade

The ranker never tells you why it fell back. `_load_model_from_env` wraps the
load in a bare `except Exception: return None`, and `auction_ranker.py` contains
no logger, print or warning of any kind, so there is no journal line to grep for
— including the `refusing to load stale coefficients` `ValueError`, which is
raised in `auction_model.py` and swallowed before it can reach anything. Do not
go looking for it. Ask the artifact directly instead:

```bash
cd /opt/antiek
./.venv/bin/python -c "from substrate.ad_inventory.auction_model import AuctionModel; AuctionModel.from_json(open('/home/antiek/.antiek/auction_model.json').read()); print('artifact loads OK')"
```

`artifact loads OK` on exit 0 clears the artifact, which points you at the flag
or at `ANTIEK_AD_RANKER_MODEL_PATH` instead. A stale artifact exits 1 and prints
the `ValueError` the ranker hid — `model artifact feature schema '<old>' !=
current 'auction-feat-v1'; refusing to load stale coefficients` — and the fix is
a retrain (step 2) against the current schema. A missing file raises
`FileNotFoundError` on the same line, naming the path it tried.

## Known tooling gaps (close these before the procedure goes live)

- `tools/auction_ab_eval.py:_load_recorded_sessions` returns `[]` on every
  branch, so the recorded-data gate this runbook turns on cannot be reached.
- The same function catches every error, so a bad path, a schema-less DB and an
  empty corpus are indistinguishable to the operator. It should raise, or print
  a distinct "db not found / table missing" line, rather than fall back quietly.
- `substrate/ad_inventory/auction_ranker.py` has no logging, so a degrade to
  rule-based is invisible. One `logger.warning` before the `return None` in
  `_load_model_from_env` would make the check above unnecessary.
- The module docstring at `substrate/ad_inventory/auction_features.py:24` still
  names the pre-rename test `test_no_label_field_in_feature_provenance`.
