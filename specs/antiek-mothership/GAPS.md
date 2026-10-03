> **PACKET-ALIAS (2026-09-29):** In this file, bare `F1`–`F9` = packet namespace **`GAPS-F1`–`GAPS-F9`**. Bare `G-X*` = packet `G-X*`. Do **not** confuse with `CR-F*` (cockpit-composition-review) or STATIC-AUDIT `F-01`–`F-18`.

# Gap analysis — lane A (the motherships' UX) on main `15e78e276`

- **Author:** Antiek Nudge v2 (236c36bd), 2026-09-24.
- **Evidence:** `ground/lane-a-*.json` (5 areas, 85 capabilities), each adversarially refuted in
  `verify/lane-a-*.json`. All five verdicts were MOSTLY_RELIABLE: 79/86 status checks held, and the
  refuters added 49 missed capabilities.
- **Merged table:** `ground/lane-a-MERGED.json`. In it, `*` means a refuter-corrected status and `+`
  means a refuter-found capability.
- **Pending:** a sixth lane (the Reading mothership, D5/D6) is still being grounded and is folded in as
  §7 when it lands.
- **Binding inputs:** `DECISIONS.md` D1–D6.

## 1. Headline

Antiek organises work by *workflow and route*, not by *project*. There is no workstation, no tab and no
way to hold two things open and hop between them. Those three layers are the core of the mothership, and
they are ABSENT (SW-01..04).

Almost everything the motherships need *inside* those layers already exists, but disconnected:
- an in-place multi-turn Dialogue on a highlight (FloatMenu)
- a floating chase island in Research
- a semantic-anchoring kit with marginalia (BUILT_UNREACHABLE)
- reader windows
- a context picker
- per-passage research records
- the herdr attention P0 (#3078)
- spend preview and owner-bound approval
- a fork-lineage primitive (`create_document_version`, no production caller)
- the continuous-research daemon and `chase_mode` (both BUILT_UNREACHABLE)

The work is mostly *connecting* them under one new chassis, and fixing the shell defects that would
poison any build on top of it.

## 2. Defects to fix before anything is built on the shell (RUN or READ proven)

| # | Defect | Evidence |
|---|---|---|
| F1 | ⌘K does not open the palette unless focus is in a text field: two handlers toggle it and cancel each other out. | shell-workstations SW-09 (RUN, jsdom) |
| F2 | On fresh storage, AppShell's hydration effect wipes the route's PanelHost starters: the investigation sidebar and chat do not dock on `/inv/:id`. | SW-07 (RUN) |
| F3 | AppShell calls `useParams` outside the inner `<Routes>`, so the per-investigation layout key is never read or written. "Reset layout (this investigation)" clears a key that never exists. | SW-07 (RUN) |
| F4 | A nested PanelLayout renders every docked or floating panel twice (two left docks in the DOM). | MISS4 (RUN) |
| F5 | ResearchWorkstation never remounts across `/inv/:id` changes, so starters open only once. | MISS5 (RUN) |
| F6 | Reader highlight → Deep research navigates away and fails silently (only `console.error`). | threads MISS12 / craft MISS10 (READ) |
| F7 | Write sub-agent proposal: accepting spawns a child investigation, then drops its id; the outcome never returns. | threads MISS10 (READ) |
| F8 | The reader opens only documents with a `book_assets` row. Web and URL ingests, `/ingest/asset` conversions and DRW web evidence 404 in the reader window. | RE-01, reading MISS11 (READ/RUN) |
| F9 | No single keymap owner: at least 3 window-level handlers claim ⌘ combos (⌘K doubled, ⌘J conflicting). | SW-15 |
| R1 | ~~**Security risk:** unconfined server-path reads in the merge and notes routes (`source_merge.py:189-193` reads `Path(draft_merge_path)` with no root confinement). READ, not RUN.~~ **CLOSED on main 2026-09-26.** `substrate/research_artifact/paths.py` now routes every merge/notes path through `_read_confined_text(...)` with an explicit `refusal` and `direct_child` allowlist; `draft_merge_path_for()` replaces the bare `Path(draft_merge_path)` read, and anything outside the root raises `ValueError("source_merge_draft_merge_path_invalid")`. Regression guard: `tests/test_source_merge_draft_confinement.py`. Verified against `origin/main` @ `3d800a665` — see the row's original claim for the pre-fix shape. | threads MISS11. Routed to lane B and Sweep's audit. **Resolved by lane B.** |

## 3. Gap matrix by lane-A cluster

Each row gives the status on main, what to reuse, and what is missing. Ownership: **A** = lane A (UI),
**B** = lane B (data or endpoint), **C** = a contract field.

### A1 Mothership shell: motherships, workstations, tabs, keys, attention

| Capability | Status | Reuse | Missing |
|---|---|---|---|
| Workstation = project entity | ABSENT | `write_folders` edges-not-copies precedent; `parent_investigation_id` families; `deliverables.investigation_root_id` | **B:** workstation registry + members (edges). **A:** `/w/:workstationId/*` routing + store. |
| Three motherships over shared projects (D1/D5) | ABSENT (one shell, four "doors" that reset your place) | NavRail doors, SceneChrome | **A:** mothership switch that keeps the workstation; per-mothership forest. |
| Several open workstations | ABSENT | windowsStore (8, memory-only) | **A:** `openWorkstations[]` + active; per-workstation last route and layout. |
| Tabs (branch tree, D6) | ABSENT | panel layer (docks, float, popout); WorkspaceWindow keyboard verbs | **A:** tab tree UI (path header, sibling strip, tree panel, numbers). **B/C:** server-side tab tree per account. |
| Keys: herdr prefix + direct chords (D2) | ABSENT for workstations and tabs; panel cycling ⌘[ ] exists | `bindings.ts` + `shortcuts.ts`; 22 free ⌘⇧ letters | **A:** ONE keymap dispatcher and ONE table (key sheet + `aria-keyshortcuts`). D2 supersedes SPR-08's no-leader rule. |
| Switcher (goto) | PARTIAL (palette exists, ⌘K broken) | CommandPalette, `state:` chips | **A:** workstation, tab, thread and document kinds; hierarchical-number jump. |
| Sidebar with live thread state | PARTIAL (Research-only panel) | `/my-research` monitor (families, attention, unseen) | **A:** shell-level sidebar. **B:** list endpoint for sessions/threads by owner and state (none today). |
| Session restore across devices | PARTIAL (localStorage only) | `workspace/persistence.ts` scopes | **B/C:** server session. **A:** hydrate and cache. |
| Attention inbox | PARTIAL (#3078 P0 registry, toasts, unseen) | P1 #3088 (sound, title) + P2 #3092 (favicon, layout presets) are OPEN since 2026-08-14 | **A:** inbox surface + title/favicon. **B:** inbox items (thread done, needs-you, consent, cap). |
| Cross-workflow breadcrumb | BUILT_UNREACHABLE (ThreadBreadcrumb / GET `/thread/{node_id}`) | as is | **A:** wire it, and **rename** it ("thread" collides with subagent threads; see Q-A3). |

### A2 Reading everywhere (and the Reading mothership: see §7)

| Capability | Status | Reuse | Missing |
|---|---|---|---|
| One door to any document | SPEC_ONLY (`antiek-reader` `openDocument()` never landed) | reader window (#3384), BookReader, the HTML projection reader | **A:** `openDocument(id, {where: tab\|pane\|window, at: locator})` used by every door. **B:** serve non-book documents (F8). |
| Reader pane in Research | PARTIAL (DRW evidence opens a window; `/inv/:id` has none) | `WINDOW_PAGES.reader` | **A:** Reader PanelKind + "open beside". |
| Reader pane in Writing | ABSENT | same | **A:** citation chip → reader beside the draft at the chunk. |
| Evidence opens in place | PARTIAL (only ChunkModal, TalkToBook page jump) | ChunkModal | **A:** one `openEvidence()` for every citation, claim and source card. |
| Position persistence | PARTIAL (per tab, dies with the tab) | `usePosition` | **B:** durable position per account. **A:** resume. |
| Side by side | PARTIAL (DRW floating windows only) | windows | **A:** the docked pane (two panes max). |

### A3 Islands and asking

| Capability | Status | Reuse | Missing |
|---|---|---|---|
| Selection affordance | PARTIAL: FloatMenu (Note, Dialogue, Search, Deep-research) | FloatMenu; floatMenuActions | **A:** decouple island lifetime from the DOM selection (IslandStore snapshots the anchor). |
| In-place multi-turn | BUILT_AND_WIRED for Dialogue (thought-partner); ABSENT for deep research | FloatMenu Dialogue; ChaseThread floating island (Research) | **A:** one Island primitive for Reader, Research and Write; follow-up composer. **B:** thread continuation. |
| Anchoring + marginalia | BUILT_UNREACHABLE (reading-physics anchored widgets, RegionStore, marginalia) | as is | **A:** mount it. **B/C:** text-quote locator (Q-A4). |
| Persistence + reopen | PARTIAL | `read-<docId>` thread id; `researches_for_passage` | **B:** per-document thread index. **A:** margin marks + rail rehydrate. |
| Ask without a highlight | PARTIAL (thought partner, not a research subagent) | ContextPicker (@doc/@insight); TalkToBook; "Research this page" | **A:** AskComposer with attachable docs, notes and threads. **B:** thread kind in `/compose-context`. |
| Model choice on the island | ABSENT | ModelUsagePicker (#3400) | **A:** header picker. **B:** `model_choice` on spin-research (and #3278 for Dialogue). |
| Streaming + honest failure | PARTIAL | IslandStatus states | **B:** stream endpoints. **A:** states (F6). |
| Cost before spend | PARTIAL (cascade spend-preview + owner-bound approval exist) | `cascade_routes` spend-preview / spend-approval | **A:** estimate in the island. **B:** estimate for single-thread spawns. |

### A4 Threads, merge, fork, companion

| Capability | Status | Reuse | Missing |
|---|---|---|---|
| Thread list per document | BUILT_UNREACHABLE (data exists) | `researches_for_passage`, `read-<doc>` chases, `read.book_answered` | **B:** GET `/documents/{id}/threads`. **A:** rail list + margin marks. |
| Thread list per workstation | PARTIAL | `/my-research` | **B:** per-workstation thread list. **A:** Threads tab + sidebar. |
| Ask this thread (held context) | ABSENT | DRW steer (Deepen/Redirect), but its deepen follow-up is never consumed | **B:** continuation primitive (lane B B1). **A:** composer on any thread row. |
| Manual merge | PARTIAL (ArtifactOutlineShelf draft merge; its output can't be continued) | ArtifactOutlineShelf | **B:** merged-thread entity with lineage + conflicts. **A:** select → preview → conflicts → accept. |
| Automatic merge | ABSENT | reuse flywheel (records only) | **B:** policy merger. **A:** suggestion in the inbox. |
| Process + outcome views | BUILT_AND_WIRED per research thread; not for Dialogue or TalkToBook | trajectory views, AutoNotebook | **A:** process tab on every thread kind. |
| Companion per project (D3 tab) | PARTIAL (AutoNotebook is per investigation) | AutoNotebook derive | **B:** project-scoped derived companion. **A:** Companion tab. |
| Companion per document (D3 rail) | PARTIAL (ReadingCompanion) | ReadingCompanion | **B:** per-document aggregate. **A:** rail. |
| Merge into document | PARTIAL | companion chase merge / source-merge (unreachable) | **B:** merge-proposal endpoint. **A:** "merge into…" flow. |
| Fork with lineage | BUILT_UNREACHABLE (`create_document_version` has no production caller; SDAM repository unbuilt) | `versioning.py` | **B:** fork repository (B4). **A:** fork chip + lineage. |
| Diff / accept UI | ABSENT | — | **A:** DiffReview (per-hunk accept or discard; AI vs operator source). |

### A5 Autonomy (D4) and craft

| Capability | Status | Reuse | Missing |
|---|---|---|---|
| Flag concept / question / insight | ABSENT / PARTIAL / weak | QuestionIdentified payload; marginalia → user insight node | **B:** one flag entity (read \| diligence, actor). **A:** flag actions in FloatMenu, rail and thread rows. |
| Consent + daily cap | PARTIAL (cascade approval exists; no autonomy settings) | spend-preview / approval | **B:** reserve-before-spend cap ledger. **A:** consent sheet + Autonomy settings. |
| Autonomous run | BUILT_UNREACHABLE (daemon SpawnFn is a stub; `chase_mode` is not on the start request) | `orchestrator` chase_mode; `continuous/live_spawn.py` | **B** (B5). **A:** "Keep digging" control, queue states. |
| Result lands in thread/companion + inbox | PARTIAL | — | **B + A**, via the contract. |
| Craft | Rubric baseline 24/48 (50%) | W1 (tokens), W5 (motion), W3 (shell, states, prose) are pushed and green; W7 (vetoes, crashes) is queued | **A:** island keyboard/ARIA (CR-03), physics (CR-04), 390 px bottom sheets (CR-05), designed states (CR-06), narrow companion (CR-07), state-matrix stories (CR-08). |

## 4. What this means for sequencing (to be formalised in `index.html`)

1. **Stabilise the shell first:** F1–F5 and F9 (one keymap owner). They sit under every later sprint,
   and they are frontend-only, so lane A can start now.
2. **Workstations + tabs (branch tree) + keys:** depends on lane B's workstation registry and the
   server-side tab tree. It can start local-first behind the contract's shapes and switch to the
   server once B lands.
3. **One document door + reader pane + Reading mothership home** (§7): needs B to serve non-book
   documents (F8) and durable position.
4. **Islands + ask:** after the contract is signed, since they need the thread continuation and
   text-quote locator.
5. **Threads, merge, fork, companion, flags/inbox:** after B1–B5 endpoints exist.
6. **Craft** runs alongside every step. Every sprint ships its state matrix and its stories, and stays
   inside the bundle budget.

## 5. Decisions this analysis surfaces

- **SPR-08's ratified no-leader-key rule is superseded by D2** (the operator chose a herdr prefix on
  2026-09-24). Record it in `docs/decisions/` when the keymap sprint lands.
- **"Thread" already names ThreadBreadcrumb's cross-workflow entity hop.** Rename that component
  ("lineage" or "trail") so "thread" means a subagent investigation, one meaning per name.
- **The operator's standing choice for the Write canvas is "net-new, not merged"**
  (`spr-09-write-canvas-xray-rewrite.md:82-87`). That is consistent with D1/D5 (separate motherships)
  and must not be undone by a shared tab model: shared projects, separate shells.

## 6. Items routed to lane B (Antiek Sweep v2)

C03 (continuation primitive) · C01 (GET `/documents/{id}/threads`) · SW-01 (workstation registry: the
grounding proposes a table shape) · SW-06 (session/thread list endpoint; none exists) · RE-16 (durable
position) · F8 (serve non-book documents) · C13 / MISS6 (fork repository and `create_document_version`)
· AD-04 / AD-05 (daemon SpawnFn, `chase_mode` on the start request) · AD-09 (cap ledger) · F7 (Write
sub-agent drop) · ~~R1 (unconfined path reads)~~ **R1 CLOSED 2026-09-26** (see the R1 row in the gap table).

## 7. The Reading mothership (D5/D6)

- **Evidence:** `ground/lane-a-reading-mothership.json` (24 capabilities) and
  `verify/lane-a-reading-mothership.json` (MOSTLY_RELIABLE, 22/25 hold, 6 missed capabilities added).
- **Refuter corrections:** F2 is ABSENT (no handler for in-body link clicks exists anywhere). T3 is
  ABSENT (`SeamResearchToReadPayload` is never emitted, and it carries an insight node, not a document).
  H2 is PARTIAL.

| Capability | Status | Reuse | Missing |
|---|---|---|---|
| Kindle-grade typography + measure | PARTIAL | W3's `.prose-antiek` (Charter, 30em, heading n→h(n+1)), unmerged; the Unified Reader `Reader.tsx` rich-block renderer exists only on `origin/snapshot/2026-09-21/detached/antiek-rebase-preflight` | **A:** land W3; salvage `Reader.tsx` for lists, tables, math and figures (never rewrite from scratch). |
| Page keys (←/→, space, PgUp/PgDn, Home/End) | ABSENT | `setPageIndex` | **A:** a reader key scope in the MS-01 keymap. Key-scope rule: never fire in inputs or FloatMenu, and not while a WorkspaceWindow owns ←/→ (MISS5, a real collision). |
| Progress | PARTIAL ("Page N of M" text only) | TocPanel current page | **A:** progress bar, %, chapter remaining, time-left estimate, progress on Continue cards. |
| Position: durable, cross-device, not clobbered | PARTIAL (sessionStorage per tab; a citation open overwrites it; several instances share one key: MISS6) | `usePosition`; `BlockPositionPayload` event precedent (latest wins, single writer) | **B:** `reading.position` typed event plus a read endpoint. **A:** resume, and open-at-citation *without* moving the saved position. |
| Distraction-free | ABSENT | — | **A:** `prefix+f` hides everything but the path header (chrome takes 35–42% of 844 px on Read routes today). |
| Themes | PARTIAL (OS-only; W1 adds in-app Light/Dark/System) | W1 `useTheme` | **A:** reader night/paper toggle; fix the 3.25:1 reader error text. |
| Text size / font | ABSENT | pagination is size-independent (`usePosition` docblock) | **A:** Aa control (size, line height, margins). |
| Layout stability | PARTIAL | W3 skeleton | **A:** a skeleton shaped like the final TOC and column; scroll reset on page turn (NOT MEASURED). |
| Footnotes / endnotes | ABSENT (deleted at ingest or left as dead text; a `#fn` link on another page's DOM can't resolve because of `paginate()`) | — | **B:** keep footnotes at ingest as structured notes. **A:** a footnote opens as a popover in place, and "open as tab" makes a child tab. |
| Links inside the reader body | ABSENT (a click navigates the whole app away) | — | **A:** intercept every body link → child tab (D6) or an external-link confirm. |
| Citation → source | PARTIAL (navigates away or opens a flat window; no parentage) | `openDocument` (snapshot branch) | **A:** MS-05 `openDocument(id,{where: child_tab, at})`. |
| Resolve a reference (DOI / arXiv id) | PARTIAL | arXiv register; graph lookup | **B:** resolve-reference call: graph hit, else rights-aware ingest offer. **A:** "Open reference" state machine. |
| Rabbit-hole lineage | PARTIAL (flat windows, cap 8, memory-only) | the investigation tree (`parent_investigation_id` → InvestigationSidebar) is the one unbounded tree on main: **the D6 model** | **A:** MS-04 tab tree. **B:** branch record. |
| Tree keys | ABSENT | — | **A:** MS-01/MS-04 keymap. |
| Path back to the passage | PARTIAL | `read-<documentId>` thread (MISS1); passage notes (MISS2) | **A:** path header + `prefix+u` returns to the exact locator. |
| Saved reads (`/readings`) | BUILT_AND_WIRED ("what I have read", from `source.read` dwell) | as is | Feeds the Continue door once position exists. |
| Read flags (user) / agent to-read | ABSENT / ABSENT | — | **B:** flag entity (`intent: read`, actor). **A:** flag actions + To-read door. |
| Curate prompt | BUILT_AND_WIRED (session-only) | as is | Save as a queue tied to a project (**B**). |
| Reading home (three doors) | PARTIAL (only "New" exists) | Library, search, import | **A:** Continue / To read / New. **B:** Q-A5 reading workstation kind. |

**Collisions and risks.**
- `readingFocus` is a module-level single bus (MISS3): with two readers open, the last one mounted wins.
  Islands and the ask composer must bind to a *per-pane* focus, not the global one.
- ←/→ are owned by WorkspaceWindow when a window is focused (MISS5). The reader key scope must defer to
  window focus.

## 8. Found while executing (dated, owner named)

**From MS-01 (2026-09-24, branch `design/mothership-01-shell-keymap` @ `de162ae26`).**
- **G-X1, starters don't reopen on a route change.** WrestleApp (`/wrestle` → `/wrestle/:id`) and CreationStudio (`/create` → `/create/:id`) reuse the route component, so their starter panels never reopen. MS-01's F5 fixed only ResearchWorkstation, by keying PanelHost by investigation id. The generic fix belongs in PanelHost: a starter key from the route's params. Owner: lane A, scheduled with MS-03 (it owns the chassis).
- **G-X2, "Reset workspace layout" doesn't reset.** The palette clears the saved layout key, then about 250 ms later the emptied layout is written back into the same key. The file is CommandPalette, W2's lane. Owner: lane A, after W2 lands; fix with a red-first test.
- **G-X3, the Trail still says "thread".** "Thread integrity error", its aria-label and the `thread-*` test ids survived the rename, because M6 required no behaviour change. "Thread" now means one investigation (§1.0), so this copy is wrong. Owner: lane A, in MS-08, the threads UX. The backend `/thread/{node_id}` route keeps its name; lane B is told.
- **G-X4, the prefix has an API and a storage key but no Settings control.** Operator question: is one wanted? The default `ctrl+b` works without it.
- **Settled here, not open:** the `ctrl+alt+u` and `ctrl+alt+a` desktop collisions (DESIGN-MODEL §2, "Desktop-grab collisions").
