# Doc-truth ratification proposals — 2026-07-02

**Status: PROPOSED. Applying any diff below is the operator's call** — each
touches a surface that `docs/roadmap/GOVERNANCE.md` (or the decision-doc
supersession convention) reserves for operator ratification. Every diff is
copy-paste appliable and carries its evidence. Declining any of them is a
single visible decision; this doc records it either way.

Produced by AGH SPR-07 (antiek-gap-hardening spec, sprint-07-doc-truth), from
the 2026-07-02 verified gap map. The agent-editable fixes shipped separately
in the same PR; these three did not, because authority boundaries outrank
convenience.

---

## Proposal 1 — supersession banner on the read-frontend blocker doc

**File:** `docs/decisions/read-backend-sprints-and-drw-frontend-blocker.md`
**Evidence:** its lines 6-7 claim SPR-02/03/04/07 are "blocked on the unbuilt
DRW shared reading surface"; the same-day sibling doc
`docs/decisions/read-frontend-sprints-on-existing-surface.md` records all four
complete, and the code is on main (`apps/reading/src/modes/Library/`,
`apps/reading/src/modes/Reading/` incl. `MetaReading/`). `CLAUDE.md` tells
every agent that `docs/decisions/` "tells you what's been settled" — an
unbannered stale decision doc is live misdirection.
**Diff (prepend as line 1):**

```markdown
> **SUPERSEDED** same-day by `read-frontend-sprints-on-existing-surface.md` —
> the DRW blocker was wrong; SPR-02/03/04/07 shipped on the existing surface.
```

## Proposal 2 — master-product-spec companion box: drop the stale ranges

**File:** `docs/master-product-spec.md` lines 52 + 57
**Evidence:** the companion box exists precisely to route readers to live
sources, but embedded ranges that drifted: "(G1–G8)" vs the gate table's
G1–G12; "(D1–D11)" vs ~20 deferrals (with a D17 duplicate now resolved to
D20). The box should be pure pointers.
**Diff:**

```diff
- - **`docs/operator_gate_actions.md`** — the eight binding gates (G1–G8)
+ - **`docs/operator_gate_actions.md`** — the binding gates (live register
+   in its quick-status table)
...
- - **`docs/engineering_deferrals.md`** — the eleven deferrals (D1–D11)
+ - **`docs/engineering_deferrals.md`** — the engineering deferrals (stable
+   don't-re-implement IDs; count-free on purpose)
```

## Proposal 3 — exercise the FLUID register (first time since 2026-05-27)

**File:** `docs/roadmap/ROADMAP.html`
**Evidence:** line ~240 pins status to "origin/main 76c2002" (2026-05-27) —
roughly forty merges behind today's tip; the two "PROPOSED — sign-off pending"
items (auto-notebook definition, meta-reading boundary) have shipped, reversible
code on main (`modes/Notebook/AutoNotebook.tsx`, `modes/Reading/MetaReading/`)
and have waited since May. The propose→ratify mechanism (GOVERNANCE.md) exists
exactly for this and has never been exercised.
**Proposed register diff:** re-pin the status line to the main tip at
ratification time, and for each of the two PROPOSED items either **sign off**
(the fleet then drops the "proposed — sign-off pending" banner in a one-line
follow-up PR) or **redirect** (each decision doc documents its reversible
rollback). The operator may also delegate drafting the exact HTML diff back to
the fleet after choosing per-item verdicts — the choice, not the diff, is the
gated part.
