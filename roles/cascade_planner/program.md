# Cascade planner — operator-editable program (DRW SPR-05)

The cascade planner turns one problem into an **editable, approvable tree of
focused sub-researches**. It is the glass-box plan: nothing launches until
the operator approves the tree.

## What it does
1. Decompose a problem (or a structural gap, or a note challenge) into
   sub-questions, reusing the `decomposer` role.
2. Run each sub-question through `focus.focus_check`; recurse into over-broad
   ones so an over-broad problem yields a *deeper* tree, not vague breadth.
3. Persist the tree as SPR-01 `question` nodes + `decomposes_into` edges.
4. Hold an explicit **approval gate** — `approval.is_plan_launchable` is the
   check SPR-06 must pass before fanning out.

## Conventions (edit these, not the code)
- **Max branches per node:** `focus.MAX_BRANCHES` (8). Mirrors
  `constants.SUB_QUESTIONS_MAX`. Exceeding it is surfaced (capped + flagged),
  never silently truncated.
- **Max depth:** `planner.DEFAULT_MAX_DEPTH` (3). A leaf still over-broad at
  max depth is reported in `PlanReport.over_broad_leaves` — honest, not hidden.
- **Focus thresholds:** `focus.py` (`_MAX_CONJUNCTIONS_FOCUSED` etc.). The
  check is syntactic; it is weak on short, conjunction-free but *semantically*
  broad questions — a documented blind spot.

## What it does NOT do
- It does not launch. That is SPR-06, gated on `assert_launchable`.
- It does not auto-approve. Editing an approved plan re-opens the gate.
