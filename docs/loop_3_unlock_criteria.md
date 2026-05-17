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

**Evidence required:** Output of a query script in `compounding/verification/` reporting both counts. Commit the script.

**Current state (2026-05-17):** 0 production investigations. Zero open-weight policy coverage.

---

### 2. SFT model exists — UNCHECKED

- [ ] An Antiek-specific supervised-fine-tuned model has been produced from the trajectory log on the *same base architecture* targeted for RL.
- [ ] SFT model is registered in `substrate/dispatch/config.yaml` as an addressable model (even if not yet routed for production traffic).
- [ ] SFT loss curves and held-out eval scores are recorded in `docs/training_log.md` (does not exist yet).

**Why this matters:** RL from a zero-shot base model is wildly inefficient and unstable. SFT is the standard precondition. Skipping SFT is the textbook way to burn $X thousand on training a worse model than the one you started with.

**Current state:** Not started.

---

### 3. Reward function is stable and validated — UNCHECKED

- [ ] `middleware/outcomes/RUBRIC_SCORED` events are emitted in production for ≥1,000 LLM calls.
- [ ] Inter-rubric correlation analysis exists: do deterministic and judged scores correlate? If not, which is being optimized?
- [ ] Reward-↔-downstream-outcome correlation: do high-reward LLM calls correlate with `OUTCOME_RECORDED` events grading the resulting synthesis as `DEFENSIBLE`? Evidence in a notebook committed to `compounding/verification/`.
- [ ] Reward noise floor characterized: run the same prompt × model × eval set ≥3 times. Standard deviation of the reward must be smaller than the smallest improvement that would matter.

**Why this matters:** RL maximizes whatever reward you give it. If the reward is noise, you train noise. If the reward is decorrelated from outcome, you train against the outcome. Either is worse than not training.

**Current state:** Schema locked (`middleware/outcomes/events.py`), scorer not implemented, no production emissions, no correlation analysis.

---

### 4. Open-weight deployment is justified — UNCHECKED

- [ ] A one-page written argument exists for why the trained model must be open-weight rather than continuing with closed-weight APIs. Acceptable categories of argument: **cost** (with token-volume math), **latency** (with measurement), **policy/control** (e.g., regulatory), **privacy** (e.g., sensitive data), **capability** (the trained model demonstrably beats the closed alternative on the §D eval).
- [ ] At least one of the above is *measured*, not asserted.

**Why this matters:** Today every Antiek tier uses a closed-weight provider because it is the better choice — cheaper, smarter, or more reliable depending on tier. RL training produces an open-weight model. If there is no concrete reason to *deploy* an open-weight model, the training run produces an artifact for the trophy case. Don't train trophies.

**Current state:** No argument exists. The Researchmaxx vision posits open-weight for the "tab model" product, but Antiek has not yet validated that posture against measurement.

---

### 5. Eval headroom exists — UNCHECKED

- [ ] The eval set from `integration_prime_intellect.md §D` exists and has grown to ≥200 curated examples.
- [ ] The current (pre-RL) policy's eval score has been measured.
- [ ] A *ceiling* has been characterized — either (a) the score of the best available closed-weight model on the same eval, or (b) human inter-annotator agreement on the rubric. The pre-RL score must be consistently below the ceiling by a margin that exceeds the noise from §3.
- [ ] GEPA prompt optimization (`§A`) has already been attempted and has plateaued. RL is not the first knob to turn.

**Why this matters:** RL is the most expensive optimization in the toolbox. If GEPA hasn't been tried, prompt-tuning is cheaper and may close the gap. If there's no measured gap, there's nothing for RL to close.

**Current state:** No eval set, no baseline, no GEPA run, no ceiling.

---

## Process

When any criterion is checked, append a dated line below with the evidence link. Do not delete criteria. Do not weaken them. If a criterion turns out to be wrong, propose an amendment in a separate PR with a written justification — do not edit in place.

### Change log

(empty — no criteria met yet)
