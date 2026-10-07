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

## Not done in this PR (SPR-02 M4–M5)

The rail strip (`NavRail` icon variant behind the same flag) and the keymap rows
for `switcher.open.<section>` are the next PR; both depend on nothing here but
were split to keep this diff reviewable.
