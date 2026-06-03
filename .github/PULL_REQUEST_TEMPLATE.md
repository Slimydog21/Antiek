<!-- ARE-10 of the Antiek Rust-Execution Spec
     (~/specs/antiek-rust-execution/). Source ADR:
     docs/decisions/are-wave-2-tooling-additive.md. Each section
     below asks a SPECIFIC question that resists generic
     "yes, considered" answers. If a section reads like
     boilerplate, the rubric is failing — tighten the question. -->

## What changed

<!-- One paragraph. Specific verbs (added, replaced, removed, refactored).
     If the diff is non-trivial, name the file:function focal points. -->

…

## Why

<!-- The motivation behind the change. Cite the bug / user request / failing
     invariant / missing capability. Avoid "better X" or "cleaner Y" — those
     are conclusions, not motivations. -->

…

---

## Rigor block — five values

Each section asks a specific question. Answer concretely. If you cannot
answer a section, that itself is a finding — say so and propose a fix.

### 1 · Intellectual honesty — what did you NOT do, or do partially?

<!-- Examples of GOOD answers:
     - "Refactored writer at substrate/foo/bar.py:42 only; the other 3
       writers in that package are flagged with `# TODO(are-02)` and
       deferred."
     - "Test coverage on the Err branch is at 100% for the new paths;
       the existing exception-raising paths still have no Err-branch
       coverage but they're out of this PR's scope."
     Examples of BAD answers:
     - "Yes, considered."
     - "Everything is honest."
     - "No notable assumptions." -->

…

### 2 · Fairness — what alternative did you reject, and why did this one win?

<!-- Steelman the rejected alternative in 2-3 sentences. Then say what
     tipped the choice. If you find yourself unable to steelman the
     alternative, that's a finding — the choice may not be well-defended. -->

…

### 3 · Rigor — what verification did you run, and what did it catch?

<!-- Cite specific test files / test names / mypy output / lint output.
     "Tests pass" is necessary but not sufficient. Did the verification
     catch anything that prose review would have missed? If yes, name
     it. If no, explain why the rigor was still worth it. -->

…

### 4 · Diligence — what existing code did you read before writing this?

<!-- Cite specific files + line numbers. The Antiek codebase has 2700+
     tests; chances are something adjacent already exists. Did you grep
     for the pattern before adding a new one? Did you read the file you
     edited in full, not just the lines you changed? -->

…

### 5 · Defensibility — six months from now, can someone reconstruct why this looks like this?

<!-- The answer should be one of:
     - "Yes — the rationale is in the inline comment at <file>:<line>."
     - "Yes — the rationale is in <docs/decisions/whatever.md>."
     - "No — adding the rationale to <X> as part of this PR."
     If the rationale is in chat history or your head, it doesn't count. -->

…

---

## Test plan

<!-- Bulleted checklist of what to run / observe to verify this PR
     works. Each item should be mechanically runnable, not subjective. -->

- [ ] `./.venv/bin/python -m pytest tests/<relevant-tests>.py -v`
- [ ] `./.venv/bin/python -m tools.antiek_cli check types --scope <changed-path> --strict`
- [ ] `./.venv/bin/python -m tools.antiek_cli check lint --scope <changed-path>`
- [ ] If touching substrate: `./.venv/bin/python -m substrate.invariants`
- [ ] Manual check: …

## Substrate invariant impact

<!-- The 6 invariants enforced by substrate/invariants.py are
     non-negotiable. Check each one:
     - [ ] Single-writer DuckDB (I-001)
     - [ ] Substrate runs host-only (I-002)
     - [ ] Substrate-permissive-deps (I-003)
     - [ ] Substrate leaf-of-dep-graph (I-004)
     - [ ] Pass-threshold coherence (I-005)
     - [ ] Voice-style weight floor (I-006)
     If any are at risk, document the mitigation. -->

- [ ] Re-ran `./.venv/bin/python -m substrate.invariants` — 6/6 pass, 0 violations.
- [ ] No pyproject.toml `dependencies` array changes (or: dep change is documented + invariant I-003 re-verified).

## Reachability declaration (ACV SPR-07)

<!-- The reachable-from-prod meta-rule (docs/decisions/reachable-from-prod-declaration.md):
     a PR/sprint touching a USER-FACING feature MUST either register a reachability
     probe under tools/reachability/probes/ OR carry written internal-only
     justification here. This is the in-repo carrier of the declaration; the
     skill-level amendments (htmlspec sprint template + caffenagent 5th done-bar)
     are operator-apply (see that decision doc). Pick ONE: -->

- [ ] This PR touches a user-facing feature and registers/updates a reachability probe under `tools/reachability/probes/` (named here: …), green under `python -m tools.reachability.probe_runner`.
- [ ] This PR is INTERNAL-ONLY (lint / migration / refactor / process-as-code — no new user-facing route or surface). Justification: …
- [ ] If this PR adds or converges a substrate concern that must be unique, the registry row exists in `tools/lint/uniqueness_registry.py` and `python tools/lint/uniqueness_registry.py` is green.
