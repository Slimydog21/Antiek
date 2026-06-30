# PostHog Wedge 3 verdict — command palette accepted

**Date:** 2026-06-30
**Status:** Accepted with scoped live-update interpretation

## Source question

`docs/integration_posthog.md` defines Wedge 3 as a universal Cmd/Ctrl+K palette
that indexes investigations, documents, claims, notes, open questions, skills,
routes, and AI actions, with substrate-event-aware updates through WebSocket
fan-out. `docs/sprint_track_reconciliation.md` identified the remaining gap as
ratification: the shipped palette is substrate-aware enough for Antiek's current
single-operator workstation, but the decision had not been recorded.

## Decision

Accept Wedge 3 as shipped for the current Antiek product stage.

The accepted interpretation is **fresh-on-open substrate awareness**: when the
operator opens Cmd/Ctrl+K, the palette refreshes from substrate-backed API
indexes and merges those rows with stable route and workspace actions. This is
the right scope for a single-operator graph where the palette is primarily a
fast navigation primitive, not a live multi-user activity feed.

The original WebSocket-pushed "updates within seconds" requirement remains a
future upgrade path. It is not required to consider Wedge 3 code-shipped because
no current operator workflow depends on seeing a newly landed substrate row in
an already-open palette without closing and reopening it.

The production-density criterion in the original spec ("at least 50
investigations + 200 documents") is treated as value evidence, not a code
shipping blocker. This verdict does not claim the current production VM has
those counts; it accepts that the code path is ready when the corpus is dense
enough to make the palette indispensable.

## Evidence

| Requirement | Current evidence | Verdict |
| --- | --- | --- |
| Global Cmd/Ctrl+K surface | `apps/reading/src/components/CommandPalette.tsx` mounts a single palette component and registers the global shortcut path through the app shell. | Accepted |
| Investigations indexed | `CommandPalette.loadIndex()` fetches `/investigations` and creates both `/inv/:id` and `/replay/:id` rows. | Accepted |
| Documents indexed | `CommandPalette.loadIndex()` fetches `/documents` and routes entries through the canonical `/read/:id` door. | Accepted |
| Notebooks indexed after Wedge 2 | `CommandPalette.loadIndex()` fetches `/notebooks` and emits `/notebook/:id` rows. | Accepted |
| Open questions indexed | `CommandPalette.loadIndex()` fetches `/watch-for-later` and routes parked questions to `/brainstorm`. | Accepted |
| Workflow-aware ranking | `apps/reading/src/shell/paletteFacet.ts` infers workflow facets for substrate kinds; `apps/reading/src/shell/palette.facet.test.ts` covers workflow-leading queries and text-query regression. | Accepted |
| Workspace/system actions | `CommandPalette.tsx` builds route, workflow jump, panel, reset, and shareable-link actions from the workspace shell. | Accepted |
| Backend substrate endpoints | `interfaces/research/api/app.py` exposes the referenced index endpoints; existing API tests cover the listing surfaces used by the palette. | Accepted |
| WebSocket fan-out within seconds | The shipped palette refreshes on open; it does not subscribe to a live index feed while open. | Deferred |
| Production corpus threshold | Not verified in this repo state. | Activation evidence, not code blocker |

## Rejections and deferrals

- Do not add a WebSocket index feed now. It would add moving parts before the
  current operator workflow needs them.
- Do not put agentic suggestions into Cmd/Ctrl+K. The AI sidecar owns AI
  actions; the palette stays a transparent navigation and command primitive.
- Do not claim production graph density without a direct production probe.
- Do not broaden this verdict to claim every originally listed entity class is
  indexed. Claims, notes, and skills can be added later if their backing index
  contracts become operator-useful.

## Verification commands

These commands cover the current acceptance surface:

```bash
cd apps/reading && npm run test -- palette CommandPalette WorkspaceStore
uv run --extra dev pytest tests/test_sprint11_api.py tests/test_api_documents_listing.py tests/test_api_stats_and_notebook_edit.py -q
```

## Follow-up trigger

Reopen Wedge 3 only when one of these becomes true:

- the palette stays open long enough that stale live rows are a repeated
  operator problem;
- multi-user or background ingestion introduces concurrent graph updates that
  should appear without reopening the palette;
- claims, notes, or skills get stable API index contracts and enough operator
  demand to justify indexing them.
