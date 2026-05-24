# ADRB — Operator dogfood log

Operator-owned log for the SPR-06 dogfood loop.
Spec: `~/specs/antiek-deep-research-bridge/sprint-06-operator-dogfood.html`

## The 5 projects (named up front; pre-commit)

Before running ANY project, write the 5 topics here. Avoids
"I ran whatever came up this week" sampling bias.

- 1. _________
- 2. _________
- 3. _________
- 4. _________
- 5. _________

**Provider-mix discipline.** ≥2 AlphaSense-leaning, ≥2
Anthropic-leaning, ≥1 mixed.

**Don't switch tools mid-project.** Abandoning the bridge mid-project
is a logged failure, not a silent restart.

## Mid-sprint discipline

If a bug or missing feature shows up: log it in
`wave4_candidates.md` and DO NOT touch the code. Mid-sprint
engineering changes invalidate the verdict.

## The 5 entries

(Copy from `_template.md`. One per project.)

<!-- Project 1 -->
<!-- Project 2 -->
<!-- Project 3 -->
<!-- Project 4 -->
<!-- Project 5 -->

## Post-loop next steps

```
./.venv/bin/python -m tools.research_bridge_cli dogfood-report \
    --out runs/adrb/dogfood_metrics.md
```

Then write `docs/decisions/adrb_post_dogfood_verdict.md`
(see the `_template` sibling).
