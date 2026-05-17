# compounding/verification/

Compounding-growth measurement.

## What it does

- Runs file diffs against snapshots and surfaces alerts when Phase 8
  was logged as executed but the skill files didn't grow.
- Tracks **skill-quality** metrics, not just skill-size metrics: for
  investigations that used a given skill version, what was the
  average constraint-pass rate, the average archive rate, the average
  outcome correlation?

## The size-vs-quality distinction

Skill-size growth is necessary but not sufficient. A diff that adds
500 words of restated content isn't substantive growth. The
size-metric protects against the most egregious failure (claiming
compounding without any growth at all); the quality-metric is what
tells us whether the compounding is substantive.

See architecture_notes §3.2 and §6.

## Out of scope

Evaluating the **content** of what was added (is this insight true? is
it well-cited?) requires evaluation cohorts and held-out outcome data
and is a separate problem.
