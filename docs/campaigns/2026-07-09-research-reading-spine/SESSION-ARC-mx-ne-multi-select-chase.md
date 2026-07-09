# Session arc · multi-select promote/chase · (mx)–(ne) · PR #465

**Tip:** re-read `git log -1` on `campaign/research-reading-spine-2026-07-09-main`.  
**Prior:** SESSION-ARC-mq-na-twins-promote-chase  
**STOP:** operator only. Infinite continues until STOP.

## Product closed

| Residual | Delta |
|---|---|
| **mx** | Multi-select `note_ids` promote (substrate + API + UI) |
| **my** | Clear selection after promote + note_ids metrics |
| **mz** | Chase selected → floating\|full deep research |
| **na** | Budget soft-gate on chase (force override) |
| **nb** | SESSION-ARC mq–na handoff |
| **nc** | DecisionTreeDriverBadge + chase metrics audit |
| **nd** | Select questions \| Select insights one-click |
| **ne** | Invert multi-select over visible notes |

## Multi-select path (offline complete)

```
load twins
  → list filter (mr)
  → select visible | select questions | select insights | invert | clear
  → promote selected (mx) | promote visible (ms) | promote kinds (mq)
  → clear + metrics (my)
  OR chase selected float|full (mz)
  → budget soft-gate (na) + driver badge (nc)
```

## Proof

TwinNotesPanel vitest **21 passed** at tip ne.  
pytest twin_promote_product **7 passed** at mx.

## Invariants

HTML-first · soft budget · NotDiamond advisory · offline-honest ·  
main merge operator-gated (PR #465).

## Next

1. Operator merge PR #465
2. Pivot: Midnight Oil duration bands / collective chase polish
3. Live L1–L4 dual-gate only

**(nf)** this arc. Infinite continues until STOP.
