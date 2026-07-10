# SESSION-ARC · rl–rm · NotDiamond L7 operator path

**Tip residual:** rm · **tip SHA:** fcda5bf6 · **PR #465**

## Closed

| Residual | What |
|---|---|
| **rl** | Settings NotDiamond panel: installed driver vs weekly advisory delta (`match`/`differs`/`no_installed`/`no_suggestion`); pure `notDiamondDriverDelta` helper; `data-advisory-only` forever |
| **rm** | Every `DecisionTreeDriverBadge` deep-links **ND advisory** → `/settings#notdiamond-advisory` with `data-notdiamond-authority=advisory_only` |

## Invariants (hard to vary)
1. **NotDiamond is never dispatch authority** — decision-tree install is the only operator path
2. Weekly advisory is **suggestion only** — differs never auto-applies
3. HTML-first Settings + badge chrome; offline-honest kill-switch defaults

## Operator path
```
any research host → DecisionTreeDriverBadge "ND advisory"
  → Settings#notdiamond-advisory
  → see installed vs suggested
  → optional explicit "Install advisory pick as decision-tree driver"
  → Hermes / decision-tree remains dispatch owner
```

## Highest leverage remaining
- Operator merge **PR #465**
- Live L1–L4 dual-gate injectors (operator-only)
- Competitive wrestle dogfood / Midnight Oil polish

Infinite continues until STOP.
