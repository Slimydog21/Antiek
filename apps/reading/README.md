# apps/reading/

The TS side of the polyglot seam (architecture_notes §11). Renders a
PDF, captures region selections, posts typed events to the Python
substrate, displays the live event tail from the WebSocket.

## Stack

- Vite + React 18 + TypeScript (strict)
- Tailwind CSS for styling
- pdf.js (`pdfjs-dist`) for PDF rendering and text-layer selection
- Generated types from `tools/codegen/emit_types.py` — **never hand-edit
  `src/generated/types.ts`**, regenerate from the Pydantic schemas.

## Run

Two processes — one Python, one Node.

```bash
# Terminal 1 — Python substrate (FastAPI on :8000)
cd ~/Desktop/Antiek
source .venv/bin/activate
uvicorn interfaces.research.api.app:app --reload --port 8000

# Terminal 2 — Vite dev server (React on :5173)
cd ~/Desktop/Antiek/apps/reading
npm install            # first time only
npm run dev
```

Open <http://localhost:5173>.

Vite proxies `/health`, `/events/*`, `/trajectory/*`, and `/ws/events`
to the Python backend (see `vite.config.ts`), so the browser only ever
talks to localhost:5173 — no CORS preflight in normal dev.

The backend also enables CORS for `http://localhost:5173` as a
fallback, controlled by `ANTIEK_CORS_ORIGINS` env var.

## Layout

```
src/
  main.tsx                    React entry
  App.tsx                     2-column layout (PDF | events)
  index.css                   Tailwind directives + pdf.js text-layer CSS
  hooks/
    useEventStream.ts         WebSocket subscriber with reconnect backoff
  lib/
    api.ts                    Typed POST helpers using generated types
    hash.ts                   SHA-256 of an ArrayBuffer (matches Python hashlib)
  components/
    PdfViewer.tsx             pdf.js render + region selection → POST
    NotesPanel.tsx            Live event list with type-narrowed rendering
  generated/
    types.ts                  AUTO-GENERATED — do not edit. Regen with:
                              python tools/codegen/emit_types.py
```

## Scope vs deferred

Sprint 2 Days 1–5 (shipped):

- Load a PDF, render page 1, emit `document.loaded`.
- Select text in the rendered text layer, emit `document.region_selected`
  with bbox + text excerpt.
- Chat input at the bottom of the right column: post
  `distillation.requested` scoped to the most recently selected region
  (or whole-document when none).
- Chat feed renders `distillation.delivered` as claim cards with
  confidence badges (high/moderate/low/unknown color-coded), source
  region attribution chips, and a "challenge this claim" button on
  each card that posts `claim.challenge_raised`.
- System events (dispatch.call, context_pack.assembled,
  document.region_selected, etc.) render as muted one-line entries in
  the feed so the trajectory is fully visible.
- WebSocket auto-reconnect with exponential backoff (1→2→4→8s).

Sprint 3 (next):

- Multi-page PDF render (currently page 1 only).
- Proper text-layer DOM walk for char_start/char_end (current path
  uses `pageText.indexOf(text)`, approximate when the selection text
  appears multiple times on a page).
- Modal challenge-prompt UX (currently uses a default question text).

Known scaffolding shortcuts (each has a TODO in the relevant file):

- `PdfViewer` renders only page 1. Multi-page render arrives with the
  chat-panel iteration in Days 4–5.
- `char_start` / `char_end` are computed via `pageText.indexOf(text)` —
  approximate when the selected text appears multiple times on a page.
  Sprint 3 swaps for a proper text-layer DOM walk.
- `App.tsx` does not yet emit a follow-up `document.loaded` once
  pdf.js reports the actual page count; current event posts
  `page_count: null`. Wire-up is a one-line fix when the chat panel
  needs the count.

## Discipline

This package follows the rule from architecture_notes §11.2:

> If a TS function cannot be described as "translates DOM events into
> typed substrate events" or "renders substrate events into DOM
> updates," it does not belong here.

If you find yourself reaching for business logic on the TS side,
it belongs in a Python role / middleware module. Roles emit events;
the surface translates DOM to events and events to DOM.
