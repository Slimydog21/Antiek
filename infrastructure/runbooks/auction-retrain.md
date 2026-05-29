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
cd ~/Desktop/Antiek
# Against the synthetic fixture (no recorded data needed — labeled '[synthetic]'):
./.venv/bin/python tools/auction_ab_eval.py

# Against recorded prod/local feedback (READ-ONLY):
./.venv/bin/python tools/auction_ab_eval.py \
    --db-path ~/.antiek/research_graph.duckdb
```

Read the report. It prints, per ranker, the value-per-impression on the
attention-weighted metric, then:

- **lift (learned - rule)**: the honest number — positive, zero, or negative.
- **LEADER under measurably-better rule**: `LEARNED` only when the lift is
  strictly positive; otherwise `RULE-BASED` stays the leader.
- **data source**: `synthetic`, `recorded:<path> (n=…)`, or
  `synthetic (recorded corpus … empty/insufficient — rule-based leads until
  real feedback accrues)`. If it says the corpus is empty, **stop**: there is
  nothing to learn from yet and rule-based is the honest leader.

If the leader is `RULE-BASED`, you are done — do not promote. The learned ranker
leads ONLY on a positive measured lift.

### 2. Serialize the trained model to an artifact

Only if step 1 shows a positive lift on **recorded** data. Train and write the
small JSON artifact (a handful of floats + a version stamp):

```bash
./.venv/bin/python - <<'PY'
from tools.auction_ab_eval import load_sessions, evaluate
from substrate.ad_inventory.auction_features import AuctionCandidate, extract_features
from substrate.ad_inventory.auction_model import train_model

sessions, source = load_sessions("/home/antiek/.antiek/research_graph.duckdb")
print("data source:", source)
feats, labels, pairs = [], [], []
for s in sessions:
    for ti in s.candidates:
        pairs.append((s.context, ti, s.realized_value.get(ti.item.inventory_id, 0.0)))
maxv = max(v for _, _, v in pairs) or 1.0
for ctx, ti, v in pairs:
    feats.append(extract_features(ctx, AuctionCandidate(item=ti.item, targeting=ti.targeting)))
    labels.append(min(1.0, max(0.0, v / maxv)))
model = train_model(feats, labels)
open("/home/antiek/.antiek/auction_model.json", "w").write(model.to_json())
print("wrote artifact; n_train =", model.n_train)
PY
```

The artifact stamps `feature_schema_version` + `model_schema_version`; loading
refuses a stale feature schema (the coefficients would be positionally wrong),
so a feature change forces a retrain rather than silently mispredicting.

### 3. Promote — flip the flag (the gated config change)

Promotion is a **config flip**, not an auto-deploy. Point the substrate at the
artifact and enable the learned path:

```bash
# In the antiek.service environment (e.g. the systemd unit's Environment= or
# the operator's env file). Do NOT hardcode in source.
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
# Unset (or set to 0) in the service environment:
ANTIEK_LEARNED_AD_RANKER=0
systemctl restart antiek
```

The matcher is immediately back to the exact rule-based behavior it had before
promotion.

---

## Unhappy path — the eval says rule-based leads

This is the **expected** outcome on a fresh integration branch and stays the
honest answer until real feedback accrues. Do nothing: leave the flag off
(rule-based). Re-run the eval periodically as recorded feedback grows; promote
only when a positive lift on **recorded** data appears. A learned ranker that
leads without a proven lift is the failure mode this whole procedure exists to
prevent.

## What this procedure does NOT do

- **It does not train online or stream.** Training is a discrete offline batch
  (deterministic gradient descent, fixed iterations, zero init) → byte-identical
  coefficients on the same data. There is no online/incremental update.
- **It does not auto-promote.** The flag flip is the operator's, gated on the
  measured lift. The agent never flips the prod flag.
- **It does not introduce a runtime/GPU/network surface (§16).** The model is
  pure-Python stdlib arithmetic; inference is a dot product + two sigmoids
  in-process. No second runtime, no model server, no GPU, no network call at
  predict time. Verify: `python -c "import ast,substrate.ad_inventory.auction_model as m;
  print([n for n in ast.walk(ast.parse(open(m.__file__).read())) ])"` shows only
  `math` + `json` imports (the test `test_inference_imports_nothing_heavy`
  enforces this).
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
| eval prints `recorded corpus … empty/insufficient` | fresh branch / no recorded feedback yet | expected — leave the flag off; rule-based leads until feedback accrues |
| `LEADER … RULE-BASED` on recorded data | learned did not beat rule-based | do not promote; the measurably-better gate is working |
| slot fills look unchanged after flipping the flag | `ANTIEK_AD_RANKER_MODEL_PATH` unset / artifact missing / stale schema | the ranker degraded to rule-based (by design); fix the path / retrain to the current feature schema |
| `ValueError: refusing to load stale coefficients` (in logs) | feature schema bumped since the artifact was written | retrain (step 2) against the current schema; the artifact stamps its schema for exactly this guard |
| eval lift looks implausibly high (≈100%) | label leakage or a degenerate fixture | check `feature_provenance()` carries no served-outcome term (the test `test_no_label_field_in_feature_provenance` enforces this) |
