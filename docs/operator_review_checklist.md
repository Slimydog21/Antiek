# Operator review checklist

ARE-10 of the Antiek Rust-Execution Spec
(`~/specs/antiek-rust-execution/`). Companion to
`.github/PULL_REQUEST_TEMPLATE.md`. The checklist runs in **the operator's
head**, not as automation — it's a discipline aid, not a CI check.

Read this before approving any non-trivial PR (operator-authored or
Claude-authored). Each section asks 2–3 questions calibrated to catch
the value's anti-patterns. If 3 or more of the 5 values come back with
"nothing of note," the checklist is mis-calibrated and the operator
should tighten the questions for the next review pass.

## 1. Intellectual honesty

The most common failure mode of agent-authored PRs: silent assumption,
silent partial-implementation, silent "looks like" claims.

- [ ] Does the PR description name what was NOT done in addition to what was done?
- [ ] Does any test in the diff use `pytest.skip`, `xfail`, or a relaxed assertion that wasn't there before? If yes, is the reason in the diff?
- [ ] Does the PR claim a property ("Result-clean across substrate") that the diff doesn't fully establish? If yes, demote the claim or expand the diff.

## 2. Fairness

The most common failure mode: momentum-anchoring on the first plausible
design, no honest steelman of alternatives.

- [ ] Does the rigor section §2 name a SPECIFIC alternative and SPECIFIC reason for rejecting it? "Considered other options" doesn't count.
- [ ] If the rejected alternative is a third-party library (e.g., `returns`, Click, `pytest-benchmark`), is the reason for rejecting it about CONCRETE cost (new dep, fewer features) rather than vague "we have our own way"?
- [ ] If the PR adds an opinionated convention (a lint, a CI gate, an ADR), is there at least one named user-type or use-case that would NOT benefit from the convention?

## 3. Rigor

The most common failure mode: "tested manually" without record; verification by self-assessment.

- [ ] Is every claim in the PR description backed by a runnable command in the test plan?
- [ ] If the diff touches an existing file: does the change have a test that would have caught the bug it fixes? (If it's a refactor with no bug fix, mark N/A.)
- [ ] For any new module: does it pass `./.venv/bin/mypy --strict <module>`? If not, why not?

## 4. Diligence

The most common failure mode: agent invents a new abstraction when an
existing one is adjacent.

- [ ] Does the rigor section §4 cite specific file paths the author read before writing? Generic "I read the codebase" doesn't count.
- [ ] For any new pattern: did the author grep for prior occurrences of similar shapes? Result type → grep for `class Ok`, `from returns`, `Either`, etc.
- [ ] If the diff adds a new package directory, does the package layout match neighboring packages' conventions (init.py, main.py, README.md)?

## 5. Defensibility

The most common failure mode: rationale lives in chat history; six months later nobody can reconstruct it.

- [ ] For every non-obvious choice in the diff (a magic number, a chosen library, a chosen pattern), is the rationale in the file or in `docs/decisions/`? Not in commit messages alone — those rot.
- [ ] Does the PR title and commit messages let an outsider understand the change without reading chat?
- [ ] If the PR adds a deferred-work pointer ("ARE-12 hot-path harness is in this commit; verifier env throughput is deferred"), is the deferred work named in an ADR or follow-on issue?

---

## Worked example — apply retroactively to a recent PR

The ARE Wave 1 commits (`eeed22c`, `cbe1ed3`, `f8062df`) on branch
`are/wave-1-substrate-additive` are the worked example for this
checklist. Running the rubric against those commits produces real
findings (not "nothing of note"):

| Value | Finding |
|---|---|
| Intellectual honesty | The Wave 1 ADR explicitly named 9 deferred ARE items (ARE-01, ARE-02 M3–M5, ARE-03, ARE-04…ARE-12) with per-item reasons. Did not claim "Result-clean across substrate" — claimed "Result encoding exists, 3 caller refactors deferred." ✅ |
| Fairness | The Wave 1 ADR steelmanned the `returns` library in 2-3 sentences and gave a SPECIFIC reason for rejecting (Pydantic serialization is already the wire format; parallel encoder would multiply round-trip surface). ✅ |
| Rigor | 52 unit tests on Wave 1 modules; mypy --strict clean; 6/6 substrate invariants pass after the commit. mypy --strict surfaced 35 real errors in adjacent `runtime/db_lock.py` + `substrate/event_log/events.py` — discovered AS A CONSEQUENCE of running mypy (which the codebase hadn't been running). Finding: that pre-existing gap was filed as deferred ARE-01 rather than silently worked around. ✅ |
| Diligence | Read `runtime/db_lock.py` (570 lines) in full before designing the Result encoding; discovered the existing `WriteCoordinator` Protocol shape and mirrored it. Read `substrate/event_log/__init__.py` and discovered the existing `ActionType`-discriminated event union — chose the same discriminator shape (`tag` literal) for consistency. ✅ |
| Defensibility | All decisions live in the ADR + module docstrings, not in chat. Each commit message stands alone. Six months from now, an agent asking "why Pydantic and not `returns`?" finds the answer in the ADR's Rationale section. ✅ |

If the worked example had any "nothing of note" entries, the rubric questions would need to be tightened to make them harder to answer with generic responses.

---

## When to skip the checklist

- For pure-typo / docs-only PRs (<10 lines, only `.md` / `.txt`): skip §3 (rigor) — there's nothing to verify.
- For dependency-bump PRs from automation: focus on §3 (does the new version's test suite pass?) and §5 (is the changelog linked?). §1, §2, §4 are usually N/A.
- Never skip §5 (defensibility) on substrate-touching PRs — the rationale must be capturable.

## Failure mode of the checklist itself

If the checklist becomes a rubber-stamp ("✅" boxes ticked without thought), it's worse than no checklist — it provides false confidence. Watch for:

- PRs where every box is ticked but no SPECIFIC finding is named.
- PRs where the rigor section §1–§5 of `PULL_REQUEST_TEMPLATE.md` is filled with "Yes" / "Considered" answers.
- The operator's own time per PR review shrinking month-over-month without commensurate confidence growth.

If any of those smell, pause new PR merges and triage the checklist itself.
