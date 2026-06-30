# PostHog Wedge 4 verdict — AI sidecar undo accepted

**Date:** 2026-06-30
**Status:** Accepted for current structured AI sidecar actions

## Source question

`docs/integration_posthog.md` defines Wedge 4 as a ubiquitous AI assistant that
can mutate UI state, provided every mutating action leaves an event-log audit
trail and can be undone through that log. `docs/sprint_track_reconciliation.md`
still recorded this as open because the original sidecar chrome shipped before
the undo-via-event-log path was wired end to end.

## Decision

Accept Wedge 4 for the current structured AI sidecar action set.

The accepted scope is the action grammar implemented in
`apps/reading/src/components/ai/aiActions.ts`: panel open/focus/close, panel
mode changes, notebook append, and chase-question panel opening. These actions
mutate client or substrate-adjacent state, emit `ai.action.applied` when the
sidecar supplies context, and expose an undo handle that routes through
`POST /ai/undo` before applying the local inverse.

Transient actions such as toast notifications are intentionally outside the
event-log undo contract because they do not create durable UI or substrate
state.

## Evidence

| Requirement | Current evidence | Verdict |
| --- | --- | --- |
| Sidecar dispatches structured actions | `AISidecar.tsx` parses `@@actions` blocks and passes `AiActionContext` into `dispatchAiAction()`. | Accepted |
| Apply event emitted | `recordAiActionApplied()` posts typed `ai.action.applied` payloads through `postTypedEvent()`. | Accepted |
| Undo routes through API | `dispatchAiAction()` wraps undo handles and calls `undoAiAction({ event_id, investigation_id })` before local rollback. | Accepted |
| Backend undo endpoint exists | `interfaces/research/api/app.py` exposes `POST /ai/undo`, looks up the applied event, calls `substrate.ai_actions.undo_ai_action()`, and returns `ai.action.undone`. | Accepted |
| Backend undo accepts current sidecar targets | `substrate/ai_actions/handlers.py` registers `notebook`, `notebook_block`, `ui_layout`, and `investigation_chase`, so `POST /ai/undo` can emit linked undo events for the current sidecar target kinds. | Accepted |
| Notebook append is undoable | `add_to_notebook` stores the previous local notebook HTML/etag and restores both after the audit undo succeeds; the backend `notebook` handler is intentionally metadata-only. | Accepted |
| Event schemas include apply/undo | `substrate/schemas/events.py` defines `AIActionAppliedPayload` and `AIActionUndonePayload`; generated TS types include both. | Accepted |
| Regression tests cover the path | Frontend dispatch tests cover applied event ids, `/ai/undo` invocation, fallback undo, and notebook-append restore; backend tests cover apply/undo round trips and bad-event errors. | Accepted |

## Limits

- This verdict does not claim that free-form natural-language assistant replies
  are reversible. Only parsed structured actions are in scope.
- This verdict does not claim undo for future target kinds. Any new
  `target_kind` that can be emitted by the sidecar must register a substrate
  undo handler or deliberately reuse an existing client-owned no-op handler.
- Client-owned layout, chase, and current local notebook-append state restore in
  the client after the audit event is written. The substrate handler for
  client-owned target kinds is intentionally a no-op so the event log can record
  a linked `ai.action.undone` event without pretending that client localStorage
  lives in DuckDB.

## Verification commands

```bash
cd apps/reading && npm run test -- aiActions AISidecar CommandPalette WorkspaceStore
uv run --extra dev pytest tests/test_ai_actions.py tests/test_api_ai_undo.py -q
```
