# Session arc · twin promote · multi-select · chase · (mq)–(na) · PR #465

**Tip:** re-read `git log -1` on campaign branch (`campaign/research-reading-spine-2026-07-09-main`).  
**Prior:** SESSION-ARC-mp-mu-twins-dualgate · inventory-mq … inventory-na  
**STOP:** operator only. Infinite continues until STOP.

## Product closed

| Residual | Delta |
|---|---|
| **mq** | Selective twin promote by kind (`kinds` filter on promote-context) |
| **mr** | Twin list filter by kind (browse before promote) |
| **ms** | Promote visible one-click (browse→merge) |
| **mt–mu** | Dual-gate checklist on TwinNotes + ResearchContext |
| **mv** | SESSION-ARC mp–mu handoff |
| **mw** | Competitive duration band on ResearchProgressPanel |
| **mx** | Multi-select twin `note_ids` promote (substrate + API + UI) |
| **my** | Clear multi-select after promote + `note_ids` metrics audit |
| **mz** | Chase selected twins as floating\|full deep research |
| **na** | Budget soft-gate on twin chase (force override) |

## Recursive note-taker path (complete offline)

```
load twins → list filter (mr)
  → multi-select checkboxes (mx)
  → promote selected | promote visible | promote by kind (mq/ms/mx)
  → clear selection + metrics (my)
  → research context remount (ec+)
  OR chase selected → floating|full DR (mz)
  → budget soft-gate before fire (na)
```

## Invariants (hard to vary)

- HTML-first human views; PDF ingest only
- `kinds` ∩ `note_ids` when both set
- Soft budget never invents $0; force is explicit
- `launchFloatingDeepResearch` is the only float DR chokepoint
- Live L1–L4 injectors remain operator dual-gate only
- NotDiamond advisory only (L7 forever)
- Main merge / prod never by agents — operator merge PR #465

## Proof surfaces

| Residual | Proof |
|---|---|
| mx | pytest twin_promote_product 7 · vitest TwinNotes 14 |
| my | vitest TwinNotes 15 |
| mz | vitest TwinNotes 18 |
| na | vitest TwinNotes 19 |

## Next

1. **Operator merge PR #465** — highest leverage (gated)
2. Collective multi-select of chase spawns / written analysis polish
3. Competitive citation trust / long-horizon wrestle when live step injects
4. Antiek-bench weekly recursive rewrite dogfood (propose≠promote)

**(nb)+** this arc is residual **nb**. Infinite continues until STOP.
