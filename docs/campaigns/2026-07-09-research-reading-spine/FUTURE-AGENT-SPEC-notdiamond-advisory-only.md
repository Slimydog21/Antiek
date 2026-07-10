# Future-agent executable brief — NotDiamond advisory only (never router)

**Campaign tip at write:** residual **ahw** · branch `campaign/research-reading-spine-2026-07-09-main` · PR **#465**  
**Bar:** five values · intellectual honesty · never silent authority creep

## Operator question (verbatim mandate)

> Investigate whether implementing NotDiamond as a router will be useful and if so create specs to implement it.

## Verdict (binding · hard to vary)

**NotDiamond must remain advisory only. It must never be dispatch authority.**

| Criterion | Finding |
|---|---|
| Useful as **advisor** | Yes — weekly pick vs Antiek-bench leaderboard delta helps operators choose models |
| Useful as **router** | **No** under Antiek §16 / campaign L7 — operator model choice is the product |
| Implementation status | Settings NotDiamond panel · refuse if `notdiamond_is_dispatch_authority` true · dual-gate L7 never-router |

## Why not router

1. **Operator sovereignty** — decision-tree tab is the product control surface for model choice.
2. **Budget honesty** — soft budget + projection before fire must stay operator-visible; auto-route hides cost foresight.
3. **Antiek-bench recursive rewrite** — weekly learnings propose suite changes; they do not auto-promote models to authority.
4. **Failure mode** — silent routing when ND fails is worse than offline-honest manual selection.
5. **L7 dual-gate** — campaign deferred map permanently rejects ND as router.

## What is useful (keep shipping)

1. Weekly advisory pick beside Antiek-bench best-by-task (already shipped).
2. Delta chrome: ND pick vs bench recommended (already shipped).
3. Refuse surface if ND claims dispatch authority (already shipped).
4. Optional: deeper task_class sub-benchmarks as platform expands — still advisory.

## What future agents must not do

- Wire NotDiamond into `dispatch` / model_control as automatic router.
- Drop decision-tree manual selection in favor of ND.
- Auto-promote ND weekly pick into default driver without operator action.
- Hide budget projection when ND advises a model.

## If product later wants assisted routing (operator opt-in)

1. Spec a **new** dual-gate flag `ANTIEK_ND_ASSIST_ROUTE=0` default off.
2. UI: explicit "Use ND suggestion for this prompt" button — never silent.
3. Still show budget projection for the chosen model.
4. Never remove manual override.
5. Log usage events for Antiek-bench rewrite (propose≠promote).

Until that dual-gate exists and is operator-enabled: **advisory only**.

## Proof bar for any ND change

- Settings tests: `notdiamond_is_dispatch_authority` false or refuse.
- No dispatch path imports ND as required authority.
- Decision-tree manual model selection still works offline.
