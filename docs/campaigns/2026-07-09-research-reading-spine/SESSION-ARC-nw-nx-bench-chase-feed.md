# Session arc · Antiek-bench chase feed · (nw)–(nx) · PR #465

**Tip:** re-read `git log -1` on campaign branch.  
**Prior:** SESSION-ARC-nt-nu · inventory-nw · inventory-nx  
**STOP:** operator only. Infinite continues until STOP.

## Product closed

| Residual | Delta |
|---|---|
| **nw** | sessions/open → Antiek-bench usage (twin_chase \| floating_deep_research) |
| **nx** | Settings known_sources + by_source legend; API by_source passthrough fix |

## Recursive suite rewrite feed path

```
highlight / twin multi-select chase
  → launchFloatingDeepResearch → POST /engagement/sessions/open
  → usage_event { source, task_class from research_tier }
  → weekly_usage_summary.by_source + known_sources
  → Settings usage panel + suite proposal rewrite (propose≠promote)
```

## Proof

- pytest session_open 2 · test_usage_session_open_feed_nx 1
- vitest launch+TwinNotes 29 · Settings known feed filter green

## Next

1. **Operator merge PR #465**
2. Dogfood more workstation polish
3. Live L1–L4 dual-gate only

**(ny)** this arc. Infinite continues until STOP.
