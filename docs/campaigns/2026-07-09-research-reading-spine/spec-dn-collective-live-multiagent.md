# Spec (dn) — Collective live multi-agent chat (deferred product)

**Status:** branch_only · **code residual:** deferred (env + product judgment)  
**Campaign:** research-reading-spine · PR #465  
**Depends on:** (dc) continue-as-unit, (di) budget gate on continue, collective merge, twins

## Problem

Operator can multi-select floating deep research spawns and:
1. Merge as prompt unit
2. Merge to draft / parent
3. Create written analysis
4. Continue as cohesive unit (new floating session seeded with prompt)

What is **not** shipped: a **live multi-agent room** where selected spawns share a single chat thread and respond as a council without re-spawning.

## Product decision (recommended)

| Mode | Ship? | Notes |
|---|---|---|
| Merge → continue unit (dc/di) | **shipped** | Offline-safe, budget-gated |
| Live shared chat across spawn IDs | **defer** | Needs real multi-provider session + cost ceiling |
| Fake “council” with single model | **reject** | Violates intellectual honesty |

## Hard requirements if/when implemented

1. **Explicit opt-in** — never auto-join live multi-agent.
2. **Budget ceiling** — recommended + approve (same pattern as Midnight Oil).
3. **HTML deliverable only** — transcript projected via html_projection.
4. **Twin substrate** — each turn seeds/appends twin notes on parent asset.
5. **Citation trust** — evidence pack ungrounded when refs empty (dm).
6. **Env dual-gate** for live injectors (no silent multi-provider).
7. **propose ≠ promote** for any auto-config of models.

## Acceptance (future sprint)

- [ ] Select ≥2 spawn ids → “Open live council” (disabled offline)
- [ ] Price ceiling approve before first turn
- [ ] Each reply HTML-projected + twin recorded
- [ ] Exit deposits draft combined HTML analysis
- [ ] Offline path: continue-as-unit remains default

## Non-goals

- NotDiamond as dispatch authority
- PDF deliverable
- Auto-spend without ceiling

## Next residual after this spec

Implement only after operator unlocks live multi-provider and sets budget env. Until then, product path is **merge + continue unit**.

NEXT: (dn code polish elsewhere) or operator unlock live council.
