# The Switcher's places model (SPR-02)

Spec of record: `specs/antiek-keyboard-panes-agents-20261007/sprint-02-launcher.html`
(claim `ffx-nav-SPR-02`). Owner: Antiek Sweep. Flag: `antiek.flag.switcher.places`
(`lib/featureFlags.ts`; dev ON, test and prod OFF until SPR-05 flips it).

## What it is

Omarchy replaces every bar with a typed launcher (`SUPER+SPACE`); herdr's goto
picker (`prefix+g`) lists every pane on its own row, grouped, with filters.
Antiek already binds `prefix+g` and `⌘K` to ONE surface, the Switcher
(`components/CommandPalette.tsx`, action `palette.toggle`). Places are therefore
SECTIONS of that surface, not a second modal — index.html decision D-06 and the
rejected alternative "a separate Launcher component".

With the flag on, the Switcher's list is:

| Section | Rows come from | Enter runs |
| --- | --- | --- |
| Doors | `WORKFLOW_ORDER` / `WORKFLOWS` (`shell/workflowTaxonomy.ts`) | `navigate(defaultRoute)` — what the rail does |
| Scenes | the palette's `ROUTE_INDEX` (bare routes only) | `navigate(path)` |
| Open | `windowsStore.order/windows/focusedId`, `companionStore.tabs/activeTabId`, `WorkspaceStore.panels/focusedPanelId` | `windowsStore.focus(id)`, `companionStore.activateAgentTab(id)`, `WorkspaceStore.focus(id)` |
| Tabs | `tabTreeStore.trees[mothership]` for the current route's workflow (research→research, read→reading, write→writing) | `tabTreeStore.activateTab(mothership, tabId, "user")` |
| Projects / Agents / Arrangements | ABSENT on main — their inputs are owned by other lanes (v4 data contract; SPR-01 arrangements) | — |

Below the sections the legacy list ("Commands & results": workspace actions,
investigations, documents, notebooks, parked questions) renders as before. With
the flag off the palette is byte-for-byte the pre-SPR-02 palette; every
pre-existing palette test runs flag-off and is therefore a parity check.

## Rules (each has a test in `switcherPlaces.test.ts` / `CommandPalette.places.test.tsx`)

- **Identity by reference.** A row carries the owning store's own id; Enter
  focuses/reveals that host through the host's own command and never calls
  `windowsStore.open` for an already-open identity (pane-flow contract S01, S09,
  S10). `ProductsLauncher`'s window admission is untouched (retained owner).
- **Absent, not empty.** A section whose input the caller did not supply is
  omitted entirely. "No projects" never stands in for "no API".
- **No core row on main.** There is no "focus the core canvas" command on main;
  a row whose Enter did nothing would be a hidden non-consumption (contract:
  "no hidden successful consumption"). The pane-flow packet (SPR-01) adds the
  command and the row.
- **Section order is fixed** (`PLACE_SECTIONS`); ranking happens within a
  section with the same ranker the rest of the palette uses
  (`paletteFacet.rankEntries`). A query never interleaves sections.
- **Filters are query syntax, never bare letters.** `in:open`, `in:tabs`,
  `in:agents is:blocked` lead the query exactly like the existing `state:`
  facet; `Tab` / `Shift+Tab` cycle the section filter; chips click. herdr's
  bare `b/w/i/d` keys were REJECTED for this surface: the Switcher is
  type-to-search first and `r`, `d`, `s`, `o`, `a` begin "read", "documents",
  "speak", "open", "ask" — a bare-letter filter would steal the first
  keystroke of the commonest queries. (This deviates from the sprint page's M2
  wording; recorded in the SPR-02 handoff.)
- **Current host first.** On an empty query the focused window / active
  companion tab / focused panel sorts first inside Open and is marked "● here".
  That is the only recency signal main has; no focus history is invented.

## Contract for the zen-home geared switcher (Undertaker v2, SPR-07)

`buildPlaceRows(ctx)` is pure and takes optional `projects` / `agents` /
`arrangements` inputs. When the project tree exists, the geared switcher calls
`buildPlaceRows({ scenes: [], open: {…empty…}, projects, agents })` and filters
with `filterPlaceRows(rows, { section: "projects" | "agents", agentStatus })`;
`groupBySection` returns the render groups in canonical order. Rows for a
sub-level are the rows whose `parentId` matches the selected node — that
field is on `ProjectInput`, and `projectRows` names the parent in the subtitle.

## Exported API (`shell/switcherPlaces.ts`)

| Export | Purpose |
| --- | --- |
| `PLACE_SECTIONS`, `SECTION_LABELS`, `SECTION_WORDS` | section order, header labels, `in:` words |
| `AGENT_STATUSES` | herdr's blocked/working/idle/done/unknown |
| `buildPlaceRows(ctx)` | rows in section order; absent inputs → absent sections |
| `tabInputFromTree(mothership, tree)` | pre-order walk of a tab tree (pruned skipped) into `TabInput` |
| `presentSections(rows)` | sections present, canonical order |
| `filterPlaceRows(rows, filter)` / `NO_FILTER` | section + agent-status narrowing |
| `parseFilterQuery(q)` / `formatFilterQuery(filter, text)` | `in:` / `is:` syntax ⇄ filter |
| `cycleSection(current, present, ±1)` | Tab cycling |
| `rankPlaceRows(rows, text)` | within-section ranking; current-first on empty text |
| `groupBySection(rows)` | render groups |

## The rail strip and the key (SPR-02 M4–M5)

With the flag on, the bottom dock (`shell/NavRail.tsx`) folds into its existing
compact five-key layout at every width: the four doors + More, captions kept
(SPR-07's "no caption-less bar control" rule stands), keycap chips and the
Home/Search keys dropped (`⌘O` and `prefix+g` still reach them), height 48 px
(`data-rail-strip="true"`). More — by click and by the `door.more` hotkey —
opens the Switcher narrowed to Scenes (`in:scenes`) instead of the products
drawer; `ProductsLauncher` stays mounted and untouched. The sprint page's
"40 px icons-only" wording was NOT followed: icon-only bar controls were the
v1 complaint SPR-07 fixed, and 48 px keeps the caption legible.

One keymap row: `switcher.open` = `prefix+shift+o` / `ctrl+alt+shift+o` opens
the Switcher at `in:open` (herdr's goto, narrowed to what is open). `shift+o`
because `prefix+o` is `tab.visitChild`. The toggle event carries
`detail.query`; the palette honours it only with places on, so the key degrades
to the plain Switcher when the flag is off. No `in:agents` key: that section is
absent on main, and a key to an absent section would be a hidden
non-consumption.

## Input types and the frozen contract (index.html D5)

`ProjectInput` / `AgentInput` are this module's exported, structural inputs.
When Undertaker v4 freezes `workspace/contracts/{tree,selection}.ts`, these
become aliases of (or are replaced by) its `ProjectNode` / `AgentNode`, so the
places rows and the zen home's geared switcher read ONE source. `is:<status>`
accepts exactly herdr's five words (`AGENT_STATUSES`) and gets a live source
only from the monitoring lane's store (SPR-10); no status is invented before
that.

## Independent critique of #3748 (MiMo V2.6 Pro, 2026-10-07) — dispositions

Report: `specs/antiek-keyboard-panes-agents-20261007/ground/critic-mimo-spr02-3748-b286539d8.md`.

| # | Finding | Disposition |
| --- | --- | --- |
| F1 | The sprint page claimed Esc "returns focus to the opener (existing behaviour)"; the palette never did. | Page corrected; focus return IMPLEMENTED here (opener captured on open, focused on close; KeySheet pattern); tested in both flag states. |
| F2 | j/k when the box is empty not implemented. | Implemented (empty box only; with text they are search text). |
| F3 | Esc closed immediately instead of clear-then-close (Omarchy menu rule R14). | Implemented: Esc clears a non-empty query, a second Esc closes. |
| F4 | PageUp/PageDown ×6 absent. | Implemented (six rows, R14). |
| F5 | Right/Left/Backspace descend/ascend absent. | N/A: the Switcher's list is flat; the nested descend/ascend belongs to the zen home's geared switcher (SPR-04). Recorded, not built. |
| F6 | `is:all` is a sixth accepted token. | Kept, documented: `is:all` and `in:all` are the clear tokens the chips write; they are never a status. |
| F7 | Flag-off still subscribes to windows/companion/tab-tree stores. | Accepted as render-frequency-only (DOM parity proven); zustand hooks cannot be conditional. Revisit if a profile shows the palette re-rendering on window moves with the flag off. |
