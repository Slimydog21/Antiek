# Loop 3 Unlock Criteria (Hosted RL Gate)

**Purpose:** This document is the hard gate that must be fully passed before any RL training (`prime rl run`, or any equivalent) is launched against an Antiek-derived model. It exists because building infrastructure is easy and training prematurely is expensive — in money, in calendar time, and in producing artifacts that look like progress while encoding noise.

**Owner:** Faisal. No-one else may flip these checkboxes.
**Source spec:** [integration_prime_intellect.md](integration_prime_intellect.md) §4 (E).

**Rule:** All five criteria below must be checked, with linked evidence, before any RL training command is issued. Partial completion does not justify partial training.

---

## Criteria

### 1. Trajectory volume — UNCHECKED

- [ ] **≥10,000 sealed investigations** in `~/.antiek/research_events/*.parquet`.
- [ ] **≥80% of LLM events** have a `policy_id` resolvable to an open-weight model (i.e., a model checkpoint we could actually fine-tune). Closed-weight-only trajectories cannot train an open-weight policy.

**Evidence required:** Output of the committed query script reporting both counts:

```bash
./.venv/bin/python -m compounding.verification.trajectory_volume \
  --events-dir ~/.antiek/research_events \
  --open-weight-policy-file reports/loop3/open-weight-policy-ids.json
```

Do not pass `--include-live-jsonl`, `--min-sealed-investigations`, or
`--min-open-weight-policy-fraction` for unlock evidence. The committed output
must show the default thresholds (`min_sealed_investigations: 10000` and
`min_open_weight_policy_fraction: 0.800`). The policy registry must be
explicit. The script deliberately does not infer that a `policy_id` is
open-weight from model-name appearance alone.

**Current state (2026-05-17):** 0 production investigations. Zero open-weight policy coverage.

---

### 2. SFT model exists — UNCHECKED

- [ ] An Antiek-specific supervised-fine-tuned model has been produced from the trajectory log on the *same base architecture* targeted for RL.
- [ ] SFT model is registered in `substrate/dispatch/config.yaml` as an addressable model (even if not yet routed for production traffic).
- [ ] SFT loss curves and held-out eval scores are recorded in `docs/training_log.md` (does not exist yet).

**Evidence command:**

```bash
./.venv/bin/python -m compounding.verification.sft_readiness \
  --metadata reports/loop3/sft-model.json \
  --dispatch-config substrate/dispatch/config.yaml \
  --training-log docs/training_log.md
```

`reports/loop3/sft-model.json` is intentionally a placeholder until a real SFT
run exists. Passing evidence requires a real slash-delimited `policy_id`, base
architecture, matching RL target base architecture, model artifact reference,
model hash, training/eval dataset refs, numeric train-loss and held-out eval
metrics, matching dispatch config registration, and a `docs/training_log.md`
entry that references the model, base architecture, RL target architecture, and
metrics. The command verifies the SFT evidence chain only; it does not train,
upload, or independently reproduce the SFT run.

**Why this matters:** RL from a zero-shot base model is wildly inefficient and unstable. SFT is the standard precondition. Skipping SFT is the textbook way to burn $X thousand on training a worse model than the one you started with.

**Current state:** Not started.

---

### 3. Reward function is stable and validated — UNCHECKED

- [ ] `middleware/outcomes/RUBRIC_SCORED` events are emitted in production for ≥1,000 LLM calls.
- [ ] Inter-rubric correlation analysis exists: do deterministic and judged scores correlate? If not, which is being optimized?
- [ ] Reward-↔-downstream-outcome correlation: do high-reward LLM calls correlate with `OUTCOME_RECORDED` events grading the resulting synthesis as `DEFENSIBLE`? Evidence in a notebook committed to `compounding/verification/`.
- [ ] Reward noise floor characterized: run the same prompt × model × eval set ≥3 times. Standard deviation of the reward must be smaller than the smallest improvement that would matter.

**Volume evidence command:**

```bash
./.venv/bin/python -m compounding.verification.reward_signal \
  --events-dir ~/.antiek/research_events
```

Do not pass `--include-live-jsonl`, `--min-llm-events`, or
`--min-rubric-scored-events` for unlock evidence. This command only proves the
`rubric.scored` volume bullet. It does **not** prove reward/outcome correlation
or the reward noise floor.

**Why this matters:** RL maximizes whatever reward you give it. If the reward is noise, you train noise. If the reward is decorrelated from outcome, you train against the outcome. Either is worse than not training.

**Current state:** Schema locked (`middleware/outcomes/events.py`), scorer not implemented, no production emissions, no correlation analysis.

---

### 4. Open-weight deployment is justified — UNCHECKED

- [ ] A one-page written argument exists for why the trained model must be open-weight rather than continuing with closed-weight APIs. Acceptable categories of argument: **cost** (with token-volume math), **latency** (with measurement), **policy/control** (e.g., regulatory), **privacy** (e.g., sensitive data), **capability** (the trained model demonstrably beats the closed alternative on the §D eval).
- [ ] At least one of the above is *measured*, not asserted.

**Evidence command:**

```bash
./.venv/bin/python -m compounding.verification.open_weight_justification \
  --justification docs/decisions/loop3-open-weight-justification.md \
  --measurements reports/loop3/open-weight-justification.json
```

`reports/loop3/open-weight-justification.json` is intentionally empty until
measured evidence exists. Do not pass `--min-justification-words` for unlock
evidence. Passing evidence requires a written affirmative `Decision: deploy
open-weight...` argument of at least 350 words and at least one measured
category from `cost`, `latency`, `policy_control`, `privacy`, or `capability`.
A measurement must name a metric, date, source artifact, and the category-
specific numeric values enforced by the verifier; assertion-only prose and
arbitrary numeric fields do not pass. This command verifies evidence shape
only and does not unlock Loop 3 by itself.

**Why this matters:** Today every Antiek tier uses a closed-weight provider because it is the better choice — cheaper, smarter, or more reliable depending on tier. RL training produces an open-weight model. If there is no concrete reason to *deploy* an open-weight model, the training run produces an artifact for the trophy case. Don't train trophies.

**Current state:** No argument exists. The Researchmaxx vision posits open-weight for the "tab model" product, but Antiek has not yet validated that posture against measurement.

---

### 5. Eval headroom exists — UNCHECKED

- [ ] The eval set from `integration_prime_intellect.md §D` exists and has grown to ≥200 curated examples.
- [ ] The current (pre-RL) policy's eval score has been measured.
- [ ] A *ceiling* has been characterized — either (a) the score of the best available closed-weight model on the same eval, or (b) human inter-annotator agreement on the rubric. The pre-RL score must be consistently below the ceiling by a margin that exceeds the noise from §3.
- [ ] GEPA prompt optimization (`§A`) has already been attempted and has plateaued. RL is not the first knob to turn.

**Evidence command:**

```bash
./.venv/bin/python -m compounding.verification.eval_headroom \
  --evidence reports/loop3/eval-headroom.json
```

Do not pass `--min-eval-examples` for unlock evidence. The committed placeholder
points at the current 50-example `parameter_extractor_v0.jsonl` fixture and
must fail until the curated eval set is expanded to ≥200 rows. Passing evidence
requires current-policy score, ceiling kind (`closed_weight` or
`human_agreement`), ceiling score, non-negative reward noise floor, a headroom
margin greater than that noise floor, source artifacts for the score/ceiling/
noise measurements, schema-valid eval rows (`chunk_text` +
`expected_parameters`), and explicit GEPA plateau evidence with a report
artifact. This command checks evidence shape only and does not run GEPA or
evals.

**Why this matters:** RL is the most expensive optimization in the toolbox. If GEPA hasn't been tried, prompt-tuning is cheaper and may close the gap. If there's no measured gap, there's nothing for RL to close.

**Current state:** No eval set, no baseline, no GEPA run, no ceiling.

---

## Process

When any criterion is checked, append a dated line below with the evidence link. Do not delete criteria. Do not weaken them. If a criterion turns out to be wrong, propose an amendment in a separate PR with a written justification — do not edit in place.

### Change log

(empty — no criteria met yet)
