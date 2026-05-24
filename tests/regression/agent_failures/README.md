# tests/regression/agent_failures/ — the harness backstop

> Anytime you see AI do a bad thing, try to build the tooling that
> catches it next time. — Mitchell Hashimoto, 2026

Every time an Antiek agent path produces a wrong or surprising output
in production, file a YAML fixture here BEFORE shipping the fix. The
parametrized test in `tests/regression/test_agent_failures.py` replays
every fixture; the fixture must fail until the underlying mitigation
lands; once the mitigation is in place, the fixture flips to passing
and acts as a regression sentinel forever after.

## Why fixture-first

If you fix the underlying bug first and only then write a fixture, you
risk writing a fixture that happens to pass against the post-fix code
but doesn't actually exercise the bug. Writing the fixture FIRST proves
both (a) the fixture really reproduces the failure (because it fails
before the fix), and (b) the fix really mitigates the failure (because
the fixture flips to passing once the fix lands).

This mirrors the standard test-driven-development discipline but applied
specifically to agent behavior — where "the bug" is less about a
single function and more about a class of input that the agent path
mishandles.

## Fixture shape

```yaml
id: <kebab-case-slug-matching-filename>
observed_at: 2026-05-NN          # ISO date
source: project_<memory-file>.md # path of the memory entry that documents the incident
agent: claude | codex | operator-manual
phase: <which Antiek phase> # e.g. parameter_extraction, synthesis, verify
failure_type: <one of>           # e.g. subprocess_died, rate_limited, ssl_handshake
context_summary: |
  Two-to-five sentence operator-readable description of what
  happened. Pretend the reader has not seen the original memory
  entry — make this self-contained.
input:                           # synthetic minimum-reproducible input
  prompt: |
    <the prompt the agent saw, anonymised>
  env:
    KEY: VALUE                   # any env knobs that mattered
expected_behavior: |
  What the agent SHOULD have done.
actual_failure: |
  What the agent ACTUALLY did, including the error trace if any.
harness_check_that_now_catches: |
  Which existing Antiek mechanism (phase_runner verify, quality_gate,
  inline rubric, etc.) blocks this failure mode today, OR "GAP" if
  no mechanism exists yet.
fix_commit: <git SHA or "GAP">   # the commit that mitigated, or GAP
notes: |
  Anything else a future maintainer needs (related fixtures,
  caveats, expected obsolescence date if the failure mode goes
  away when a dependency upgrades).
```

## Onboarding a new fixture

1. **Observe the failure in production.** Capture the prompt that
   produced it (the SPR-E6 prompts/ directory makes this routine —
   look at `prompts/<hash>.md` for the offending agent commit).
2. **File the fixture.** Create `tests/regression/agent_failures/<slug>.yaml`
   with the schema above. Run `pytest tests/regression/test_agent_failures.py
   -k <slug>` — it should FAIL (proving the fixture really reproduces
   the bug).
3. **Land the fix.** In a SEPARATE commit, ship the mitigation.
   Re-run the test — it should now PASS. Update the fixture's
   `fix_commit` field with the SHA.
4. **Record the failure.** Call `orchestration.agent_failure_log.record()`
   from any code path that detects the same failure class going
   forward — gives the operator a tally of "how often does this
   re-trigger."

## Counting the library

```
ls tests/regression/agent_failures/*.yaml | wc -l   # fixture count
```

The library starts at 5 fixtures (the well-documented Phase A +
arxiv-ingestion failures from May 2026). Each new prod incident
should add one. A small library is fine; a stale library is not.

## Out of scope

- This directory does NOT replace the Phase 8 SkillPatchGate at
  `compounding/skill_growth/gate.py`. That gate is mode-flippable
  (shadow → enforcing) and decides patch acceptance, not failure
  detection.
- Fixtures should be SYNTHETIC reproducers, not real prod data.
  Operator-personal context (file paths, env values) belongs in the
  prompt persistence layer (`prompts/<hash>.md`), not in test
  fixtures committed to the repo.

## Spec

- Engineering: `~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html`
- Philosophy: `~/specs/antiek-philosophy/rounds/round-01-hashimoto/sprint-03-harness.html`
- Hashimoto source: 2026-Q1 podcast interview, "anytime you see AI
  do a bad thing, try to build tooling that could have called out to
  to have prevented that bad thing or course corrected that bad thing."
