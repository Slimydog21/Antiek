# Decision: Outline → Write auto-import (from-investigation)

**Date**: 2026-09-19  
**Status**: accepted  
**Cite**: `POST /write/deliverables/from-investigation` (WV-SPR-01); AutoNotebook daily-loop (#3168); ConnectResearch; anti-ek composite rollup residual 4.

## Context

Notebook → Write handoff already opened `/write?investigation=` and pre-selected ConnectResearch (#3168). The outline stayed empty: operators still tapped blocks by hand. Backend promotion of a depositable synthesis into a seeded deliverable already existed; the UI never called it.

## Decision

1. `createDeliverableFromInvestigation` in `writeApi.ts` wraps `POST /write/deliverables/from-investigation`.
2. WriteHome `createWithConnection` tries that promote first whenever a research folder is connected.
3. Honest fallback: HTTP 404 `no_synthesis` → existing empty `createDeliverable` + `investigation_root_id` link (ConnectResearch path unchanged).
4. Preferred-notebook copy states the import behavior.

## Non-goals

- Fabricating outline sections without a depositable synthesis.
- Merging TipTap notebooks with AutoNotebook.
- TalkToBook ↔ thought_partner unify (separate residual).

## Consequences

Daily loop research → notebook → Write lands on a seeded outline when synthesis exists. Notebook grade climbs; residual 4 closed for the connect path.
