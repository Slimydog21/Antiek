<!-- ARE-08 of the Antiek Rust-Execution Spec
     (~/specs/antiek-rust-execution/). Copy this file when proposing a
     non-trivial substrate change. The 9 sections mirror the Rust RFC
     template; the single-operator ratification block at the bottom
     substitutes for Rust's multi-team final-comment-period. -->

# RFC NNNN — <one-line title>

- **Date proposed:** YYYY-MM-DD
- **Branch / PR:** `…`
- **Author:** `<who-or-what-agent>`
- **Status:** Draft | Ratified | Withdrawn | Superseded by RFC NNNN

## When is an RFC required?

A change requires an RFC if any of the following hold:

1. It touches a substrate invariant (anything enforced by
   `substrate/invariants.py` or by `runtime/db_lock.py`'s single-writer
   contract).
2. It adds a new package under `substrate/`.
3. It changes a public internal API (function or class re-exported from
   a package's `__init__.py`).
4. It introduces a new external integration (LLM provider, search
   provider, ad-tech provider, etc.).
5. It adds a runtime dependency (a `dependencies` entry in
   `pyproject.toml`).

Below the threshold, an inline commit message is sufficient.

## 1. Summary

One paragraph. What is being proposed?

## 2. Motivation

Why is this change needed? What problem does it solve that the current
code does not? Cite the bug, the user request, the failing invariant,
or the missing capability that prompted this RFC. Avoid hand-waves like
"better X" or "cleaner Y".

## 3. Guide-level explanation

Write this section *as if the feature already existed*. Show how a
developer would use it. Include 1–2 minimal code examples and the names
of the public functions / classes / config keys involved. A developer
reading this section in six months should know how to use the feature
without reading the rest of the RFC.

## 4. Reference-level explanation

The internals. Mechanism, data flow, edge cases, error handling. Cite
the specific files and functions that will change. Include:

- New types / functions and their signatures.
- Data shape changes (schema_version bumps; new event types).
- Concurrency story (what happens with N concurrent callers).
- Failure modes (what happens when the upstream is down, the disk is
  full, the lock is held, the user cancels).

## 5. Drawbacks

What are the costs of this change? Be honest. Enumerate:

- Maintenance burden (code complexity, new dependency, new failure
  mode to debug).
- Operational burden (new monitoring, new runbook entry).
- Migration burden (existing callers need to change; deprecation
  shim required; flag-day risk).
- Reversibility (can we undo this in one commit, or does it touch
  data shapes that would need a migration?).

## 6. Rationale and alternatives

For each non-trivial design choice in §3 + §4, name the alternative
that was considered and why this design won. Format:

| Alternative | Why rejected | Reconsider if … |
|---|---|---|
| … | … | … |

A reader six months later asking "why didn't you do X instead?" should
find the answer here, not in chat history.

## 7. Prior art

Link to:

- Existing ADRs in `docs/decisions/` that this RFC builds on or
  supersedes.
- External design references (Rust RFCs, papers, blog posts).
- Adjacent code patterns in this codebase that this RFC matches or
  intentionally diverges from.

## 8. Unresolved questions

Things you don't know yet. List each as a question + the assumption
you're operating under + who can resolve it.

| Question | Current assumption | Who can resolve |
|---|---|---|
| … | … | … |

## 9. Future possibilities

What does this RFC make possible that we are *not* doing now? Listing
these prevents scope-creep in the current PR while preserving the
forward path.

---

## Ratification

The Antiek single-operator substitute for Rust's final-comment-period.
The operator (or a subsequent Claude session) runs the 5-value rigor
rubric against this RFC and either ✅ approves or ❌ sends back for
rewrite. Failing ratification means rewrite, not approve-anyway. A
half-ratified RFC is worse than no RFC.

- [ ] **Intellectual honesty.** The RFC names assumptions that were
  tempting to hide. Risks and trade-offs are recorded, not papered
  over. The Status field is honest about Draft vs Ratified.
- [ ] **Fairness.** Each rejected alternative is steelmanned in §6.
  The current design's win is defended against the strongest opposing
  case, not the weakest.
- [ ] **Rigor.** Acceptance criteria in §4 are mechanically checkable
  (a test, a query, a screenshot, a CI step). "It works" is not a
  criterion.
- [ ] **Diligence.** Prior art in §7 cites file paths and line numbers
  where applicable. The author read the surrounding code, not just
  the change site.
- [ ] **Defensibility.** The RFC contains enough context that a future
  reader can answer "why is this code like this?" without asking the
  author or grepping chat history.

**Ratified by:** `<operator-or-agent-id>` on `YYYY-MM-DD`
