# Sprint 11 — Web App MVP Spec

**Status**: ready for implementation
**Surface**: `app.antiek.ai` (Cloudflare Pages, DNS already wired by Sprint 10 IaC)
**Predecessor**: `apps/reading/` (the existing TS app — extended in place, not replaced)
**Substrate prereqs**: all 1166 tests passing; production substrate live at `api.antiek.ai`; OpenRouter dispatch working end-to-end (validated 2026-05-17)

---

## Context and scope

Antiek's substrate is in production. Loop 1 runs end-to-end against real LLMs.
`MASTER.md` artifacts get generated correctly. Cost per investigation is ~$0.08-$0.16.
Operator can post cold questions via `tools/demo/run_cold_question.py` and read the
output as a static markdown file in `~/research/<topic-slug>/`.

This sprint replaces the static markdown reading experience with an interactive
research workstation. The thesis: reading-for-understanding is a different shape
than reading-for-pleasure; LLMs let you compress hundreds of sources at speed;
the right UX surface is closer to Cursor than to Kindle.

The MVP is **deliberately narrow**. Three follow-up sprints (continuous mode,
document-first integration, golden-insight tagging) are deferred to follow-on
sprints once the operator has actually used the v0 surface for a week.

---

## Voice and style discipline (load-bearing quality bar)

This sprint MUST land the substrate-side prompt engineering for voice and
style at the same time as the UI. The MVP only works if the output
doesn't feel like LLM slop. Operator's words: "to eliminate the robotic
nature of the output and that every output has the same flow of like
bullet point, bullet point, bullet point."

The discipline is documented in detail at
[`docs/strategy/voice-and-style-discipline.md`](../strategy/voice-and-style-discipline.md).
Summary of what changes in this sprint:

**Substrate-side (Day 1, alongside the new endpoints):**
- Synthesizer prompt (`roles/synthesizer/prompt.py`) gets a "voice and
  style" section that: forbids em-dashes and other slop markers; requires
  absorbing the source corpus's vocabulary; allows bullet structure ONLY
  at the top-level insights-vs-questions distinction; mandates prose
  flow within each section.
- Evidence_retriever prompt (`roles/evidence_retriever/prompt.py`) gets
  a parallel discipline so the upstream claims fed into the synthesizer
  are also non-slop.
- New role: `style_extractor` (optional, behind a feature flag for
  Sprint 11; on by default for thematic/qualitative investigations,
  off for purely quantitative ones). Reads the top-K corpus chunks
  before synthesis, produces a short "house style guide" for the
  sector, injects it into the synthesizer's context. ~150 LOC.

**UI-side:**
- The MasterMdViewer renders thesis summary as flowing prose (no
  forced bullets at the top). Falsification conditions and execution
  risks default to COLLAPSED — the primary reading experience is the
  thesis itself, not the structural metadata around it.
- Claim spans are inline (`<span>` not `<li>`) — wrapped in prose, not
  broken out as a list.
- Reading typography: serif body (Charter / Georgia / system serif),
  not the system sans the trajectory view uses. Reading flow matters.

## Primary source connection

Operator: "Let's say you provided an insight or a question and you
mentioned a data point and I say, where did you get this from? It
would be great if you could pull the user towards the actual document
... pull the user to the actual page."

The substrate already has the metadata: every chunk row carries
`section_path` which for ingested PDFs is "Page N" (set by
`acquisition/books/reader.py` via `_join_pages_to_markdown`). The MVP
ships these affordances:

1. **In the chunk hover modal** (already in scope): add a button
   "**Open in document viewer**" that navigates to
   `/wrestle/<document_id>?page=<N>` where N is parsed from the chunk's
   `section_path`.
2. **Cross-mode linking**: the existing `apps/reading/src/components/PdfViewer.tsx`
   gets a new `initialPage` prop. WrestleApp reads `?page=` from
   the route query string and jumps the PDF to that page on load.
3. **Legal posture flag**: a one-line footer in the chunk modal:
   "Source: <document_title>. Used for research purposes." Documented
   in `docs/strategy/post-mvp-roadmap.md` under "IP posture for source
   ingestion" — for Sprint 11, the posture is "ingest everything we
   can find online; address IP holders' concerns at scale in the
   attribution-architecture sprint."

This adds ~1 day to the sprint (Day 6.5). MasterMdViewer fetches +
parsing stays as planned; chunk modal gets the "Open in document"
button + WrestleApp gets the `?page=` query handling.

## Three architectural decisions (with rationale)

### Decision 1 — Extend `apps/reading/`, do not create a separate codebase

The existing `apps/reading/` app is Vite + React 18 + TypeScript strict + Tailwind
+ pdf.js. It already consumes the substrate's `/ws/events` stream, renders typed
event payloads (`NotesPanel.tsx`), shows claim cards with confidence badges,
handles cross-doc resolution sidebars, etc.

The new research workstation needs the same primitives: WebSocket consumer for
the same typed event vocabulary, claim card rendering for synthesizer output,
attribution chips backed by chunk IDs. Building a separate app means
maintaining two TS codebases that drift apart and duplicate ~70% of their
primitives. Sharing means one codebase, two routes, one set of generated types
from `tools/codegen/`.

**What this means in practice:**
- Keep the directory name `apps/reading/` (renaming is churn).
- Introduce React Router at the top level.
- Two routes:
  - `/` (default) → new research workstation (Mode A)
  - `/wrestle` → existing PDF wrestling surface (Mode B), moved into a route component without behavior change
- Cloudflare Pages serves the whole bundle at `app.antiek.ai`.

### Decision 2 — Hybrid rendering for the MASTER.md viewer

Three options were considered: pure markdown, hybrid (markdown + structured claim
overlays), structured canvas (Roam-style).

**Pure markdown** is fastest but flattens the synthesizer's structured output —
losing the per-claim `chunk_ids`, `confidence`, `source_tier_min` metadata that
the substrate works hard to produce. You can't hover a claim and see its citations.

**Canvas** is the most powerful but is ~3x the UI work. Every insight becomes a
draggable node, links between claims become explicit edges, you get a graph
view. Real value, but it's a separate sprint of work after the MVP proves the
chat-first flow.

**Hybrid** is the right answer: render the synthesis as readable markdown for
reading flow, but parse the structured `SynthesisArchivedPayload` + role outputs
behind it so each claim is a `<span data-claim-id="...">` that exposes its
citations on hover. The reading experience is markdown; the interactivity is
structured. Same approach Notion / Roam use for their hybrid blocks.

**What this means in practice:**
- The viewer fetches both `/investigations/{id}` (the structured terminal payload)
  AND walks `/trajectory/{id}` to reconstruct per-role outputs (decomposer's
  sub-questions, evidence_retriever's per-sub-q claims, etc).
- A custom remark plugin parses MASTER.md and wraps each claim paragraph with
  span metadata.
- Claim spans show source chunk IDs + tier on hover; click expands to show
  chunk text (fetched from substrate; needs a new `GET /chunks/{id}` endpoint
  added in this sprint).

### Decision 3 — MVP scope: chat + trajectory + viewer + chase

The v0 ships exactly these four affordances. Defer everything else.

| In scope | Deferred |
|---|---|
| Chat input → POST /investigations | Continuous mode (substrate change, separate sprint) |
| Live trajectory view of all 8 phases | Document-first integration (extend the existing wrestle mode) |
| MASTER.md viewer with claim-level hover citations | Golden-insight tagging (needs a new typed event + substrate change) |
| Highlight-to-spawn child investigation | Per-user accounts / authentication (operator's own flag: very far down the line) |

Rationale: the operator has been at "scope expanding" mode for a while. The
shortest path to learning what the surface should be is *using it on the
operator's actual research workflow*, not pre-building the imagined feature set.
Anything not in the four-bullet MVP gets deferred until after a week of real use.

---

## Target architecture

```
                  ┌──────────────────────────────────────────────┐
                  │           app.antiek.ai (Pages)              │
                  │                                              │
                  │  ┌──────────┐    ┌──────────┐    ┌────────┐  │
                  │  │ Mode A:  │    │ Mode B:  │    │ /chase │  │
                  │  │ Research │    │ Wrestle  │    │ /:id   │  │
                  │  │ (NEW)    │    │ (EXIST.) │    │ (NEW)  │  │
                  │  └────┬─────┘    └────┬─────┘    └────┬───┘  │
                  │       │               │               │      │
                  │       └───────┬───────┴───────┬───────┘      │
                  │               │               │              │
                  │   ┌───────────▼──────┐   ┌────▼────────────┐ │
                  │   │ useEventStream() │   │ useInvestigation │ │
                  │   │ (existing hook,  │   │ (NEW hook)       │ │
                  │   │  extended)       │   │                  │ │
                  │   └────────┬─────────┘   └────────┬─────────┘ │
                  └────────────┼───────────────────────┼──────────┘
                               │ WSS /ws/events        │ REST
                               │ + REST /trajectory    │
                               │   /investigations     │
                               ▼                       ▼
                  ┌──────────────────────────────────────────────┐
                  │         api.antiek.ai (substrate)            │
                  │  POST   /investigations                      │
                  │  GET    /investigations/{id}                 │
                  │  GET    /trajectory/{id}                     │
                  │  WS     /ws/events                           │
                  │  GET    /chunks/{id}    ← NEW THIS SPRINT    │
                  └──────────────────────────────────────────────┘
```

### State management

No Redux, no Zustand, no Jotai. The substrate is the source of truth — the UI
re-derives everything from `/trajectory/{id}` + the live `/ws/events` stream.
React `useState` + `useReducer` handle local-only state (which investigation is
focused, highlight selection ranges, sidebar collapse state).

Investigation tree (parent → child chase relationships) is stored in
`localStorage` for the MVP — a flat map of `{ child_inv_id: parent_inv_id }`.
This is migratable to a substrate event later without changing the UI contract.

### Routing

React Router 6, just enough to enable deep-linking and the two modes:

| Path | Component | Purpose |
|---|---|---|
| `/` | `<ResearchWorkstation>` | Mode A (primary) — chat-first research |
| `/inv/:investigationId` | `<ResearchWorkstation>` (with id) | Deep link to a specific investigation |
| `/wrestle` | `<WrestleApp>` | Mode B — existing PDF wrestler (current `App.tsx` becomes this) |
| `/wrestle/:documentId` | `<WrestleApp>` (with doc id) | Deep link to a loaded document |

---

## Substrate-side changes needed

Three small, surgical changes. None of them are refactors.

### 1. New endpoint: `GET /chunks/{chunk_id}`

The MASTER.md viewer's hover-citation feature needs to fetch chunk text by id.
Currently the trajectory exposes events but not the chunk table. Add:

```python
# interfaces/research/api/app.py
@app.get("/chunks/{chunk_id}", response_model=ChunkResponse)
async def get_chunk(chunk_id: str) -> ChunkResponse:
    """Read-only chunk fetch for the web app's claim-citation hover."""
    # Open read-only DuckDB connection, SELECT text, section_path,
    # source_tier, document_title FROM chunks JOIN documents
    # WHERE chunk_id = ?. 404 if not found.
```

~30 LOC. Schema: `ChunkResponse(chunk_id, text, section_path, source_tier, document_title, document_id)`. Codegen picks it up for TS types.

### 2. Optional `parent_investigation_id` field on `InvestigationStartRequest`

The "chase this" flow needs to record that one investigation spawned another.
For MVP, this is metadata-only (the substrate doesn't act on it); the UI uses
it to build the tree view.

```python
class InvestigationStartRequest(BaseModel):
    question: str = Field(..., min_length=3)
    context: str = ""
    topic_slug: Optional[str] = None
    max_sub_questions: int = Field(default=8, ge=1, le=20)
    investigation_id: Optional[str] = None
    parent_investigation_id: Optional[str] = None  # NEW
    spawn_context: Optional[str] = None  # NEW — highlighted text from parent
```

When set, the orchestrator emits a `INVESTIGATION_SPAWNED_FROM` event (new
ActionType, payload carries parent_investigation_id + spawn_context). ~20 LOC
substrate change + schema codegen.

### 3. `GET /investigations` (list endpoint)

Currently you can only fetch a single investigation by id. The web app needs
to list past investigations for the left sidebar. Add:

```python
@app.get("/investigations", response_model=InvestigationListResponse)
async def list_investigations(
    limit: int = Query(default=50, ge=1, le=500),
    status: Optional[Literal["completed", "failed", "in_progress"]] = None,
) -> InvestigationListResponse:
    """List recent investigations. Walks the events dir to find all
    unique investigation_ids; for each, returns the start event +
    terminal verdict."""
```

~50 LOC. Schema: `InvestigationListResponse(count, investigations: list[InvestigationSummary])` where summary has `investigation_id, question, status, created_at, completed_at, cost_usd_total`.

**Total substrate change**: ~100 LOC of net-new code, no schema migrations, no
existing-behavior changes. Tests added for each new endpoint.

---

## UI flow walkthroughs

### Flow 1 — Cold question, happy path

1. User opens `app.antiek.ai/`. Sees an empty workstation with a chat input
   at the bottom of the center panel: *"What do you want to research?"*
2. Left sidebar shows "Past investigations" (empty or with prior runs from
   `GET /investigations`).
3. User types: *"What's the load-bearing constraint on scaling diffraction-
   limited photonic interconnects to 1 TB/s?"* Hits Cmd+Enter.
4. Client POSTs `/investigations` with `{question, topic_slug: <derived>}`.
   Receives `{investigation_id, status: "started", start_event_id}`.
5. Client navigates to `/inv/<id>`. Subscribes to `/ws/events?investigation_id=<id>`.
6. Center panel transitions from "empty chat" to "live trajectory view":
   - `phase.enter` (phase 1) → shows "Phase 1: Orientation" with a spinner
   - `decompose.requested` → "Decomposing your question..."
   - `decompose.delivered` → renders the 8 sub-questions as a numbered list,
     each with category badge + evidence_type chip
   - `evidence.retrieve.requested` (×8) → "Searching corpus for sub-q 3..."
     (sub-q text from the decomposed list, in-line spinner)
   - `evidence.retrieve.delivered` (×8) → per-sub-q card with TWO columns:
     **Insights** (supporting_claims) + **Open Questions** (evidentiary_gaps)
   - `parameter_extract.delivered` → "Constraints: 4 hard, 2 soft" (collapsible)
   - `connector.delivered` → "Cross-domain mappings: 3 paths found" (collapsible)
   - `synthesize.requested` → spinner: "Synthesizing thesis..."
   - `synthesize.delivered` → thesis preview (first 200 chars + "expand")
   - `skill.auto_patch_applied` → small footer note: "Patched 1 domain skill"
   - `investigation.completed` → transition to MASTER.md viewer

7. MASTER.md viewer (the post-completion state):
   - Thesis summary at top (large type, readable)
   - Numbered thesis components, each with a confidence badge + chunk citation
     count ("cited 3 chunks")
   - Falsification conditions section
   - Execution risks section
   - Implicit recommendation banner (color-coded: green=proceed, amber=conditional,
     red=insufficient_evidence)
   - Cost footer: "Investigation cost: $0.082"

8. User hovers a claim → tooltip shows the chunk IDs supporting it, with tier
   badges. Click a chunk ID → modal opens showing chunk text + source document
   title (fetched via new `GET /chunks/{id}`).

### Flow 2 — Highlight to chase

1. User reads the MASTER.md. In the thesis text, sees: *"Adaptive filtering
   algorithms LSL and block lattice filters reduce sidelobe level by >40 dB..."*
2. Wants to chase: "How does this 40 dB compare to ECA's reported performance
   across different illuminator types?"
3. User selects text in the viewer with mouse drag. A floating action button
   appears anchored to the selection: **"Chase this"** (and, faded, **"Mark
   golden"** — disabled for v0 with tooltip "coming soon").
4. Click "Chase this" → slide-over panel from the right:
   - Pre-fills a textarea with the highlighted text as starting context
   - User types the actual question they want chased: *"How does the 40 dB LSL
     result compare to ECA across illuminator types?"*
   - Click "Spawn investigation"
5. Client POSTs `/investigations` with `{question, context: <highlighted text>,
   parent_investigation_id: <current_inv_id>, spawn_context: <highlighted text>}`.
6. Slide-over transitions to a mini live-trajectory view for the child
   investigation. Parent MASTER.md stays visible behind it.
7. Left sidebar updates: child investigation appears under the parent in a
   tree view.
8. User can dismiss the slide-over and come back later; the child investigation
   keeps running on the substrate.

### Flow 3 — Returning to a past investigation

1. User opens `app.antiek.ai/`.
2. Left sidebar lists past investigations sorted by `created_at desc`. Each
   row shows the question (truncated) + status badge + timestamp.
3. Click a row → navigates to `/inv/<id>`.
4. Center panel renders the investigation's state:
   - If `status: in_progress` → live trajectory view, resubscribes to WS
   - If `status: completed` → MASTER.md viewer immediately
   - If `status: failed` → terminal payload error message + replay of trajectory

---

## File layout

```
apps/reading/
├── package.json                              (add: react-router-dom, react-markdown,
│                                              remark-gfm, unified)
├── src/
│   ├── main.tsx                              (UPDATED — wraps App in BrowserRouter)
│   ├── App.tsx                               (UPDATED — becomes the route registry only)
│   ├── components/                           (existing)
│   │   ├── NotesPanel.tsx                    (existing — used by Mode A's trajectory view too)
│   │   ├── ClaimCard.tsx                     (existing — reused by MASTER.md viewer)
│   │   ├── ChatInput.tsx                     (existing — reused for "chase this" textarea)
│   │   ├── PdfViewer.tsx                     (existing — used by Mode B only)
│   │   ├── NotesFeed.tsx                     (existing — Mode B)
│   │   └── CrossDocSidebar.tsx               (existing — Mode B)
│   ├── modes/                                (NEW DIRECTORY)
│   │   ├── ResearchWorkstation/              (NEW — Mode A, the primary)
│   │   │   ├── index.tsx                     (default export, top-level layout)
│   │   │   ├── ChatInputArea.tsx             (the bottom input for question entry)
│   │   │   ├── TrajectoryView.tsx            (live phase progression renderer)
│   │   │   ├── MasterMdViewer.tsx            (post-completion synthesis viewer)
│   │   │   ├── PhaseRow.tsx                  (single-row renderer for one trajectory event)
│   │   │   ├── ChaseSlideOver.tsx            (the right-side slide-over for spawning)
│   │   │   ├── InvestigationSidebar.tsx      (left sidebar with tree of investigations)
│   │   │   └── HighlightToolbar.tsx          (floating action buttons on text selection)
│   │   └── WrestleApp/                       (NEW — wrapper around existing App.tsx body)
│   │       └── index.tsx                     (currently the contents of App.tsx, moved here)
│   ├── hooks/                                (existing dir)
│   │   ├── useEventStream.ts                 (existing — reused)
│   │   ├── useInvestigation.ts               (NEW — fetches + manages one investigation's state)
│   │   ├── useInvestigationList.ts           (NEW — fetches /investigations for sidebar)
│   │   └── useInvestigationTree.ts           (NEW — derives parent-child tree from localStorage + events)
│   ├── lib/                                  (existing dir)
│   │   ├── api.ts                            (existing — extend with startInvestigation, getChunk, listInvestigations)
│   │   ├── synthesisParser.ts                (NEW — parses MASTER.md + structured payload into claim-spans)
│   │   └── markdownClaimRenderer.tsx         (NEW — react-markdown + custom remark for claim wrapping)
│   ├── types/
│   │   └── tree.ts                           (NEW — InvestigationNode type for the tree view)
│   └── generated/types.ts                    (REGENERATED by tools/codegen — includes new substrate types)
└── README.md                                 (UPDATED — documents the two modes)
```

**Net-new file count**: 12 components + 3 hooks + 2 lib files + 1 types file = **18 net-new TS files**, ~2000-2500 LOC.

**Net-new dependencies**:
- `react-router-dom@^6.20` (routing)
- `react-markdown@^9.0` (MD rendering)
- `remark-gfm@^4.0` (tables, strikethrough, etc)
- `unified@^11.0` (transitive — needed for custom remark plugin)

---

## Detailed requirements per file

### `apps/reading/src/main.tsx` (updated)

Wrap the app in `BrowserRouter`. Otherwise unchanged.

### `apps/reading/src/App.tsx` (updated)

Becomes the route registry only. ~30 LOC:

```tsx
import { Routes, Route, Navigate } from "react-router-dom";
import ResearchWorkstation from "./modes/ResearchWorkstation";
import WrestleApp from "./modes/WrestleApp";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<ResearchWorkstation />} />
      <Route path="/inv/:investigationId" element={<ResearchWorkstation />} />
      <Route path="/wrestle" element={<WrestleApp />} />
      <Route path="/wrestle/:documentId" element={<WrestleApp />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
```

The current `App.tsx` body (the 3-column PDF wrestler layout) moves to
`modes/WrestleApp/index.tsx` unchanged. Header bar becomes a shared
component that includes a mode toggle (the existing "Antiek" header gets
a "Mode: Research | Wrestle" segmented control).

### `apps/reading/src/modes/ResearchWorkstation/index.tsx`

Top-level layout for Mode A. ~150 LOC. Three columns:

```
+----------------+----------------------------+----------------+
| Sidebar (250px)| Center (flex)              | Trace (300px,  |
|                |                            |  collapsible)  |
| Past invs      | EITHER:                    | Raw trajectory |
| (tree view)    |  - Empty chat + input      | events (JSON)  |
| - inv A        |  - Live trajectory view    | for debugging  |
|   - A.1        |  - MasterMdViewer          |                |
|   - A.2        |                            |                |
| - inv B        | Chat input fixed at bottom |                |
+----------------+----------------------------+----------------+
```

Reads route param `investigationId`. If present, calls `useInvestigation(id)`.
If absent (`/` path), shows the empty chat. Chat submit → POST + navigate.

Right column is collapsed by default; toggle button in the header.

### `apps/reading/src/modes/ResearchWorkstation/TrajectoryView.tsx`

Renders the live phase progression. Subscribes to `useEventStream(investigationId)`.
Maps each event to a `<PhaseRow>` variant based on `action_type`. Auto-scrolls
to bottom on each new event.

Renders one row per event for events with display value. Suppresses noise
events (`audit.finding_emitted`, intermediate `phase.enter`/`phase.exit` —
collapse into "Phase N: <name>" rollups).

Transitions to `<MasterMdViewer>` when `investigation.completed` arrives.

### `apps/reading/src/modes/ResearchWorkstation/PhaseRow.tsx`

Single-row renderer with action_type-keyed variants. Each variant is small:

| action_type | Rendering |
|---|---|
| `decompose.delivered` | Numbered list of sub-questions with category badges |
| `evidence.retrieve.delivered` | Two-column card: Insights / Open Questions, with chunk citation chips |
| `parameter_extract.delivered` | Collapsible "X constraints extracted" |
| `connector.delivered` | Collapsible "Cross-domain mappings: N paths" |
| `synthesize.delivered` | Thesis preview + "View full thesis" button (transitions to viewer) |
| `dispatch.call` | One-line muted row: "deepseek/v4-flash · in=1138 out=652 · $0.000268 · 4.5s" (collapsed by default into a "Show LLM calls" toggle) |
| `skill.auto_patch_applied` | Small footer note: "Patched X domain skills" |
| default | Suppressed (audit findings, phase enter/exit pairs roll up) |

Cap rendered events at 200 with a "Load older" affordance — investigations can
emit 100+ events total.

### `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx`

The post-completion view. Fetches via `useInvestigation(id)`. Uses
`lib/synthesisParser.ts` to parse the structured `terminal_payload`. Renders
through `lib/markdownClaimRenderer.tsx` which wraps each claim text in a
`<ClaimSpan>` that exposes chunk IDs on hover.

Layout:
```
┌─────────────────────────────────────────────────────────────┐
│ ← Back to trajectory                          Cost: $0.082  │
├─────────────────────────────────────────────────────────────┤
│  # <Question>                                               │
│                                                             │
│  > Synthesis ID: syn-inv-... | Generated: 2026-05-17 ...   │
│                                                             │
│  [Recommendation badge: insufficient_evidence | proceed]    │
│                                                             │
│  ## Thesis Summary                                          │
│  <paragraphs with hoverable claim spans>                    │
│                                                             │
│  ## Thesis Components                                       │
│  ### Component 1                                            │
│  - Claim: <hover for chunk ids> [conf: high]                │
│  - Supporting chunks: [chunk-abc123] [chunk-def456]         │
│                                                             │
│  ## Falsification Conditions                                │
│  ## Execution Risks                                         │
└─────────────────────────────────────────────────────────────┘
```

Highlight selection triggers the `<HighlightToolbar>` (floating).

### `apps/reading/src/modes/ResearchWorkstation/HighlightToolbar.tsx`

Listens for text selection in its parent's container via `selectionchange`
events. When a non-empty selection exists, renders a floating button group
anchored to the selection bounding box:

- **Chase this** (active) → opens `<ChaseSlideOver>` with the selection text
- **Mark golden** (disabled, tooltip: "Coming soon")

Hides when selection is cleared or focus moves elsewhere.

### `apps/reading/src/modes/ResearchWorkstation/ChaseSlideOver.tsx`

Right-side slide-over (full height, 480px wide). Triggered by "Chase this".
Pre-fills a textarea with the highlighted text. Operator edits to formulate
the actual question. Submit POSTs `/investigations` with parent metadata.

After submit, the slide-over transitions to a mini live-trajectory view for
the child investigation (reusing `<TrajectoryView>` in compact mode). Operator
can dismiss; the child keeps running.

### `apps/reading/src/modes/ResearchWorkstation/InvestigationSidebar.tsx`

Left sidebar. Calls `useInvestigationList()` + `useInvestigationTree()` to
render the tree. Each node shows:
- Question text (truncated to 60 chars)
- Status badge (in_progress = amber spinner, completed = green check, failed = red)
- Timestamp (relative: "2m ago", "yesterday")
- Cost (small, muted: "$0.08")

Click → `navigate(/inv/<id>)`. Children indented under parents based on the
localStorage tree map. Collapsed by default with chevron expander.

### `apps/reading/src/hooks/useInvestigation.ts`

```ts
type InvestigationState = {
  id: string;
  status: "loading" | "in_progress" | "completed" | "failed" | "not_found";
  question: string | null;
  events: Event[];                  // from /trajectory/{id} initial fetch
  terminalPayload: object | null;   // populated when completed
  costTotal: number;                // sum of dispatch.call cost_usd
};

export function useInvestigation(investigationId: string | undefined): InvestigationState;
```

Fetches `/trajectory/{id}` on mount + on id change. Subscribes to `useEventStream`
for the same id to append live events. Recomputes `costTotal` reactively as
new `dispatch.call` events arrive.

### `apps/reading/src/hooks/useInvestigationList.ts`

```ts
type InvestigationSummary = { /* matches GET /investigations response */ };

export function useInvestigationList(opts?: { limit?: number; refresh?: boolean }):
  { investigations: InvestigationSummary[]; loading: boolean; refetch: () => void };
```

Fetches `/investigations`. Refetches on a 30s interval when the tab is visible
(uses `document.visibilityState` to pause polling when backgrounded).

### `apps/reading/src/hooks/useInvestigationTree.ts`

```ts
type TreeNode = { investigationId: string; children: TreeNode[]; };

export function useInvestigationTree(investigations: InvestigationSummary[]): TreeNode[];
```

Reads parent-child relationships from localStorage (key:
`antiek:investigation_tree`, value: `{[childId]: parentId}`). Computes the
tree structure. Persists new relationships when `spawnInvestigation()` is
called.

Migration path noted in code comment: when the substrate adds an
`INVESTIGATION_SPAWNED_FROM` event consumer, this hook switches to reading
from the trajectory instead of localStorage. Public API unchanged.

### `apps/reading/src/lib/api.ts` (extended)

Add three functions:

```ts
export async function startInvestigation(req: {
  question: string;
  context?: string;
  topic_slug?: string;
  parent_investigation_id?: string;
  spawn_context?: string;
}): Promise<{ investigation_id: string; status: string; start_event_id: string }>;

export async function listInvestigations(limit = 50):
  Promise<{ count: number; investigations: InvestigationSummary[] }>;

export async function getChunk(chunkId: string):
  Promise<{ chunk_id: string; text: string; section_path: string | null;
            source_tier: number; document_title: string | null; document_id: string }>;
```

All use the existing fetch wrapper. No new deps.

### `apps/reading/src/lib/synthesisParser.ts`

Takes the `terminal_payload` from `/investigations/{id}` (the
`SynthesisArchivedPayload`-shaped object) + walks `/trajectory/{id}` to
extract the per-role outputs. Produces a `ParsedSynthesis` shape suitable
for the renderer:

```ts
type ParsedClaim = {
  text: string;
  confidence: "high" | "moderate" | "low" | "unknown";
  chunkIds: string[];
  sourceTierMin: number | null;
};

type ParsedSynthesis = {
  question: string;
  thesisSummary: string;
  components: { claim: ParsedClaim; rationale: string }[];
  falsificationConditions: { text: string; observable: string }[];
  executionRisks: string[];
  recommendation: "proceed" | "pass" | "conditional" | "undetermined" | "insufficient_evidence";
  totalCost: number;
};
```

~150 LOC. Pure function; testable without DOM.

### `apps/reading/src/lib/markdownClaimRenderer.tsx`

Renders a `ParsedSynthesis` as JSX. Uses `react-markdown` for the markdown
blocks (thesis summary, rationales) with a custom remark plugin that wraps
every `<p>` containing a claim with a `<ClaimSpan>` (which carries the
metadata and exposes hover citations).

The remark plugin is small: walks AST, finds paragraphs, matches against the
parsed claim list by text, wraps with metadata.

---

## Sprint days

Estimated **8-10 working days** of focused TS work. Day-by-day:

### Day 1 — Substrate-side API additions

- `GET /chunks/{chunk_id}` endpoint + Pydantic schema + test
- `GET /investigations` (list) endpoint + Pydantic schema + test
- `POST /investigations` extended with optional `parent_investigation_id` +
  `spawn_context` fields + new ActionType `INVESTIGATION_SPAWNED_FROM` +
  payload schema + emit logic in orchestrator + test
- Regenerate TS types via `tools/codegen/emit_types.py`
- Run full test suite

End state: substrate has the three new endpoints, all tests passing, TS types regenerated.

### Day 2 — Routing + WrestleApp extraction

- Add `react-router-dom@^6.20` to package.json
- Wrap App in `BrowserRouter` in `main.tsx`
- Move existing `App.tsx` body into `modes/WrestleApp/index.tsx`
- New `App.tsx` becomes the route registry
- Header bar gets a mode toggle (segmented control: Research / Wrestle)
- Add `/wrestle` route, verify Mode B (PDF wrestler) still works at `/wrestle`
  exactly as before
- `npm run build` + `npm run dev` smoke test

End state: existing Mode B works at `/wrestle`, root `/` shows a placeholder
"Research workstation coming soon."

### Day 3 — ResearchWorkstation layout + ChatInputArea

- `modes/ResearchWorkstation/index.tsx` — 3-column layout
- `ChatInputArea.tsx` — bottom input, Cmd+Enter to submit
- Wire submit → `lib/api.startInvestigation()` → navigate to `/inv/<id>`
- Empty state UI when no investigation is loaded
- Left sidebar placeholder (just "Past investigations" title for now)

End state: can type a question, hit Cmd+Enter, navigate to a new
investigation URL. Center panel shows the empty "investigation starting..."
state.

### Day 4 — Live trajectory view

- `useInvestigation.ts` hook — fetches trajectory + subscribes to WS
- `TrajectoryView.tsx` — maps events to phase rows
- `PhaseRow.tsx` — variant rendering per `action_type` (start with
  decompose.delivered + evidence.retrieve.delivered + synthesize.delivered)
- Manual test: trigger a real investigation, watch phases stream in

End state: full live trajectory rendering for a real investigation, with
auto-scroll, dispatch.call cost ticker, phase rollups.

### Day 5 — MasterMdViewer (read-only)

- `lib/synthesisParser.ts` — parses terminal_payload + trajectory into
  ParsedSynthesis
- `lib/markdownClaimRenderer.tsx` — renders ParsedSynthesis as JSX with
  react-markdown
- `MasterMdViewer.tsx` — uses the renderer, shows thesis + components +
  falsifications + risks + recommendation badge + cost footer
- Transition logic: when `investigation.completed` event arrives, TrajectoryView
  fades out and MasterMdViewer fades in

End state: post-completion MASTER.md viewer works for any completed
investigation, claim hovering shows chunk IDs.

### Day 6 — Chunk hover modal + InvestigationSidebar

- `<ClaimSpan>` component with hover popover showing chunk IDs + tier badges
- Click chunk ID → modal opens, fetches via `lib/api.getChunk(id)`, shows
  chunk text + source document title
- `useInvestigationList.ts` hook
- `InvestigationSidebar.tsx` renders list (flat for now, tree on day 7)
- Click sidebar item → navigates to `/inv/<id>`, viewer updates

End state: sidebar shows past investigations, clicking switches context.
Claim hover citations work end-to-end.

### Day 7 — Highlight-to-chase

- `HighlightToolbar.tsx` — listens to selection, shows floating buttons
- `ChaseSlideOver.tsx` — right-side panel, pre-fills highlighted text,
  textarea for question refinement, submit → spawns child investigation
- localStorage write on spawn (`useInvestigationTree.ts`)
- Slide-over transitions to mini `<TrajectoryView>` after submit

End state: highlight any claim, click "Chase this", spawn a child
investigation visible as a mini trajectory in the slide-over.

### Day 8 — Tree sidebar + polish

- `useInvestigationTree.ts` — reads localStorage, produces nested tree
- `InvestigationSidebar.tsx` renders tree with chevron expanders
- Status badges (in_progress spinner, completed check, failed X)
- Cost display per row
- Mode toggle in header is functional + persists via localStorage
- Dark mode? (defer)
- Mobile responsive? (defer — operator uses Mac desktop)

End state: sidebar shows full tree. Investigations spawn correctly visible in
their parent's subtree. Everything polished enough to ship.

### Day 9 (buffer) — Deploy to Cloudflare Pages

- `npm run build` — confirm production bundle builds clean
- Configure Cloudflare Pages project (operator creates via dashboard):
  - Build command: `cd apps/reading && npm install && npm run build`
  - Output directory: `apps/reading/dist`
  - Environment variables: `VITE_API_BASE_URL=https://api.antiek.ai`
- DNS already wired (CNAME `app.antiek.ai` → Pages project from Sprint 10)
- First deploy + smoke test through `app.antiek.ai`

End state: `app.antiek.ai` serves the workstation. Operator can run a real
investigation through the web UI end-to-end.

### Day 10 (buffer) — Critique + first user feedback

- Operator uses the workstation for one real research session
- Document friction points
- Decide what goes in Sprint 12 (likely: continuous mode OR document-first
  integration, based on what felt missing)

---

## Style and quality requirements

**TypeScript strict mode**, no `any` except where the substrate's types
genuinely permit `unknown`. Use the codegen'd types from
`src/generated/types.ts` for every event payload.

**No new global state libraries.** React `useState` + `useReducer` only.
The substrate is the source of truth; don't duplicate state.

**No new CSS systems.** Tailwind utility classes only. Match the visual
language of the existing Mode B (stone/amber palette, font-mono for IDs,
text-sm for body).

**Accessibility minimums**: all clickable affordances are `<button>`,
keyboard navigation works for the sidebar (arrow keys), focus states
visible.

**Component size cap**: ~200 LOC per component. If something is bigger,
split.

**No tests required for the TS app** in this sprint. The substrate has
1166 tests; the UI is a thin renderer over the substrate's API. Manual
QA is enough for the MVP. Test infrastructure (Vitest + React Testing
Library) can be added in a follow-up sprint if/when the UI complexity
warrants it.

**Comments**: every non-trivial component has a 3-5 line header
docblock explaining what it renders, what events it listens to, and
what state it owns. Same convention as the substrate code.

---

## What this sprint deliberately does NOT do

These are real items the operator described in their vision dump.
They're deferred to follow-on sprints, not forgotten. Document them as
known gaps so the next agent reading this knows where to look.

- **Continuous mode / 24-hour autonomous chase loop.** Substrate change
  required (orchestrator gets a `keep_chasing_until` parameter or a
  separate "question chaser daemon" daemon process). Not UI work. Sprint 12+.
- **Golden insight tagging.** Needs a new typed event
  (`CLAIM_MARKED_GOLDEN` or similar), substrate write path, plus UI.
  Sprint 12+ once the operator has used the chase flow for a week.
- **Document-first deep-read integration.** The existing Mode B
  (`apps/reading/` PDF wrestler) handles this for single-document
  wrestling. The integration the operator described — "load a document
  AND chase its open questions through the research workstation" — is a
  cross-mode handoff that needs both modes to share investigation state.
  Sprint 13+.
- **Multi-document workspace.** Loading multiple PDFs and wrestling them
  together. Sprint 14+.
- **Per-user accounts / private vs public graphs.** Operator's own flag:
  very far down the line. Single-user assumption for MVP.
- **Network-effect mechanisms (cross-user knowledge graph contribution).**
  Connected to DeepBlu interview surface. Sprint 16+.
- **Test infrastructure for the TS app.** No Vitest, no Playwright, no
  Storybook. Add when the UI is complex enough that manual QA misses
  things — which it isn't yet.
- **Authentication.** No login. `app.antiek.ai` is publicly reachable
  but the substrate has no auth — anyone with the URL can post an
  investigation. Acceptable for MVP because the only consequence is
  burning the operator's OpenRouter credits; add rate limiting +
  per-IP throttling in Sprint 12 if abuse appears.
- **Mobile / tablet responsive layout.** Operator's primary device is
  the Mac desktop. Mobile is a separate UX problem.
- **Dark mode.** Defer.
- **Animations / transitions polish.** Functional UI first. Polish
  after operator has used it for a week.

---

## Open questions to flag

Decisions deferred to operator judgment with a recommended default. Each
is non-blocking — work continues with the default unless operator pushes
back.

1. **Hosting build**: Cloudflare Pages (the wired path) or alternative
   (Vercel, Netlify)? **Default: Cloudflare Pages** (DNS already wired).
2. **`react-markdown` vs `markdown-it`**: both work. **Default:
   react-markdown** (better React integration, used by Stripe docs,
   Linear, etc).
3. **WebSocket reconnection backoff**: existing `useEventStream` uses a
   1s constant. **Default: switch to exponential backoff 1s → 30s
   max** during this sprint, since production latency matters more
   than local dev.
4. **Investigation tree storage migration timing**: localStorage now,
   substrate event later. **Default: localStorage for MVP**, plan the
   substrate migration for Sprint 12 along with golden-insight tagging
   (they share an event-schema branch).
5. **Chase slide-over UX**: slide-over right-side panel vs new tab vs
   modal? **Default: slide-over** (keeps parent context visible,
   feels lighter than a new tab, doesn't block the parent UI like a
   modal would).
6. **Empty-state copy**: what the workstation shows when no
   investigation is loaded. **Default: a one-line prompt** ("What do
   you want to research?") plus a faint "or load a document at
   `/wrestle`" footer link.
7. **Rate of `/investigations` poll**: 30s. **Default: 30s when tab
   visible, paused when backgrounded** (via `document.visibilityState`).

---

## Verification criteria

The sprint is **done** when an operator (the actual operator, sitting at
their Mac) can do all of the following without referring to documentation:

1. Open `https://app.antiek.ai/` in a browser.
2. See the empty workstation with a chat input.
3. Type a real research question, hit Cmd+Enter.
4. Watch the 8 phases stream in live in the trajectory view, with each
   phase's output rendered legibly (sub-questions as a list, evidence
   as insights/open-questions columns, etc).
5. See the MASTER.md viewer when the investigation completes.
6. Hover any claim in the thesis to see the chunk IDs supporting it.
7. Click a chunk ID to see the chunk text in a modal.
8. Highlight any paragraph in the thesis.
9. Click "Chase this" in the floating toolbar.
10. Refine the highlighted text into a child question in the slide-over.
11. See the child investigation start streaming in the slide-over while
    the parent MASTER.md stays visible.
12. Dismiss the slide-over, see the child appear in the left sidebar as
    a sub-node of the parent investigation.
13. Click the parent investigation in the sidebar to switch context.
14. Refresh the page on `/inv/<id>` and see the same state restored
    (deep-link works).
15. Switch to `/wrestle` via the header mode toggle and verify the
    existing PDF wrestler still works exactly as before.

**Plus** the substrate-side success criterion: `python -m pytest -q` still
shows all 1166+N tests passing where N is the count added in Day 1.

**Plus** the deployment criterion: `app.antiek.ai` serves the bundle,
Caddy-side of `api.antiek.ai` handles the WebSocket upgrade correctly
(900s timeouts already configured), CORS is configured to allow
`https://app.antiek.ai` origin (substrate change in
`interfaces/research/api/app.py`'s CORS middleware — Sprint 10 already
allows `localhost:5173`; add the production origin).

---

## What's outside this spec

This spec covers ONLY Sprint 11 (the web app MVP). The following are
known follow-on work but out of scope here:

- **Sprint 12+ continuous mode**: substrate orchestrator change to support
  long-running "keep chasing" investigations. Likely 3-4 days of substrate
  work + 1-2 days of UI work.
- **Sprint 13+ golden-insight tagging**: new typed event + substrate write
  path + UI surface in the MasterMdViewer.
- **Sprint 14+ corpus ingestion UX**: a UI to upload PDFs / add URLs /
  ingest arXiv papers to populate the production VM's graph. Currently
  the operator has to SSH in and run Python scripts; the UI should
  surface acquisition adapters directly.
- **Sprint 15+ document-first integration**: cross-mode handoff between
  the wrestle surface and the research workstation.
- **Sprint 16+ DeepBlu interview surface**: the AI interviewer leveraging
  the research substrate's graph between turns. The operator's stated
  long-term goal; depends on substrate being battle-tested through Sprints
  11-15 first.

---

## Sequence for the implementing agent

When a coding agent picks this up:

1. Read this spec end-to-end.
2. Read `architecture_notes.md` for the substrate's design commitments.
3. Read `apps/reading/src/App.tsx` + `NotesPanel.tsx` + `ClaimCard.tsx` to
   understand the existing TS patterns + visual language.
4. Read `interfaces/research/api/app.py` to understand the API surface.
5. Read `substrate/schemas/events.py` for the typed event vocabulary.
6. Execute days 1-9 sequentially. Substrate work (day 1) must complete
   and tests must pass before TS work starts on day 2.
7. At the end of each day, commit + push so the operator can review
   incremental progress.
8. Day 10 is the operator-driven retro + Sprint 12 planning hook.
