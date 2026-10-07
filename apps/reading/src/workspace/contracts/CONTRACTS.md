# workspace/contracts — SPR-06 contract freeze

Branch `fix/ffx-kpa-spr-06-20261007` from origin/main `a8b130730`. Note timestamp 2026-10-07T20:20Z. SPR-B (ffx-nav-backend-context / ffx-nav-backend-agent-bridge) is UNOWNED per INBOX 20:21Z; every SPR-B cell below is **unconfirmed, INBOX note pending**. Nothing in this module invents a backend value: an absent field is absent, never defaulted.

Modules: `tree.ts` and `anchor.ts` are ENTRY-SAFE (`import type` only toward the lazy chunk; entryChunk.test.ts). `selection.ts`, `treeStore.ts`, `openers.ts`, `index.ts` and `adapters/preBackend.ts` are LAZY (they import tabTreeStore / companionStore / crossPane values); entry-chunk code imports `type` from `./contracts/tree` or `./contracts/anchor` directly, or dynamic-imports `./contracts` the way `shortcuts.ts:320-322` imports companionStore. `index.ts` never re-exports an adapter name.

## 0. Corrections to the sprint page found while verifying

- `src/workspace/companionStore.test.ts` and `src/workspace/crossPane.test.ts` do not exist. The real regression files are `src/workspace/companionPane.test.tsx` and `src/workspace/crossPane.race.test.ts`. The Units gate line for the sprint page should read: `npx vitest run --maxWorkers=1 --testTimeout=30000 src/workspace/contracts src/workspace/companionPane.test.tsx src/workspace/crossPane.race.test.ts src/workspace/ProjectPicker.test.tsx src/workspace/documentTabs.projectRoundtrip.test.tsx src/modes/Reading/Reading.spawnFlows.test.tsx`.
- `spawnFlows.ts` lives at `src/modes/Reading/island/spawnFlows.ts`; `testAccountOwner.ts` is `src/testAccountOwner.ts`; the feedback wire is `src/api/feedback.ts` (not `lib/api/feedback.ts`) and `FeedbackThread.artifact` carries `{version, content_sha256}`.
- M5 names `CompanionPane.tsx`; the "Open source document" call lives in `CompanionAgents.tsx:84-99` (the surface the pane renders), which is the file edited.
- `ReformatFlow.tsx:69` returns `{ anchor_id } as BookAnchor` with NO payload. `SpawnFlowResult.documentAnchor` is therefore absent for that flow (see §5), not only when `anchorId` is null.

## 1. Mapping table

Status key: **pre-backend** = computed by `adapters/preBackend.ts` from today's wires; **wired** = read from an existing frontend wire; **absent** = representable, never produced today. "Confirmed by" is the INBOX timestamp of the SPR-B note; none exists at 2026-10-07T20:20Z.

| Contract field | Today's source (file:line) | SPR-B field | Confirmed by | Status |
|---|---|---|---|---|
| `ProjectNode.id` | `Project.project_id` (lib/api/projects.ts:18) · `"default"` (tabTreeStore.ts:66) · `InvestigationSummary.investigation_id` (lib/api.ts:387) | project id / sub-project id | unconfirmed, INBOX note pending (ffx-nav-backend-context) | wired / pre-backend |
| `ProjectNode.kind` | `"project"` for registry+default; `"subproject"` for an investigation (adapter rule 3) | nested project vs sub-project | unconfirmed, INBOX note pending (ffx-nav-backend-context) | pre-backend |
| `ProjectNode.title` | `Project.title` · `"Default project"` (ProjectPickerContent.tsx:44-48) · `summary.question ?? investigation_id` | title | unconfirmed, INBOX note pending | wired / pre-backend |
| `ProjectNode.parentId` | `"default"` or the member project for a forest root; `parent_investigation_id` / local spawn map for nested (hooks/useInvestigationTree.ts:45 rule, re-implemented) | parent project id | unconfirmed, INBOX note pending | pre-backend |
| `ProjectNode.children` | investigation forest, newest-first by `started_at` (useInvestigationTree.ts:66-74) | children | unconfirmed, INBOX note pending | pre-backend |
| `ProjectNode.agents` | companion tabs filed by `membersByProject` (no production caller feeds it) | agents by project | unconfirmed, INBOX note pending (ffx-nav-backend-agent-bridge) | pre-backend |
| `ProjectNode.members?` | `ProjectDetail.members` (lib/api/projects.ts:36-38) only when `membersByProject.has(id)` | members | unconfirmed, INBOX note pending | absent (not fetched) |
| `ProjectNode.memberCount?` | `Project.member_count` | member_count | unconfirmed, INBOX note pending | wired |
| `ProjectNode.archived` | `Project.archived_at !== null`; false for default and every investigation (never from status) | archived | unconfirmed, INBOX note pending | wired / pre-backend |
| `ProjectNode.provenance` | constant `"pre-backend"` (adapter) | `"backend"` from adapters/backend.ts | n/a | pre-backend |
| `ProjectNode.source` | `registry {project}` · `default` · `investigation {summary, parentMissing, run}` | n/a (frontend discriminant) | n/a | pre-backend |
| `RunDescriptor.agentViewId` | `agentViewId("research-thread", id)` = companionStore.agentTabId (companionStore.ts:89-94) | never persisted (view) | n/a | pre-backend |
| `RunDescriptor.state?` | `InvestigationSummary.status` (lib/api.ts:389) | run state (SPR-B's "five states") | unconfirmed, INBOX note pending (ffx-nav-backend-agent-bridge) | wired |
| `RunDescriptor.since?` | `completed_at ?? started_at` | since | unconfirmed, INBOX note pending | wired |
| `AgentNode.id` | `tab.investigationId` for research-thread; `tab.id` for dialogue (= viewId by construction) | agent / run identity | unconfirmed, INBOX note pending (agent-bridge) | pre-backend |
| `AgentNode.viewId` | `AgentTabDescriptor.id` verbatim | never persisted | n/a | wired |
| `AgentNode.viewOpen` | true for every companion tab (the only source today) | n/a | n/a | pre-backend |
| `AgentNode.runId?` | none | bridge run/attempt id | unconfirmed, INBOX note pending (agent-bridge) | absent (never fabricated) |
| `AgentNode.kind` | `AgentTabDescriptor.kind` (companionStore.ts:25) | view kind | n/a | wired |
| `AgentNode.runKind` | `AGENT_RUN_KIND_OF_TAB[kind]` (= crossPane `opened_by.agent_kind` vocabulary, crossPane.ts:28-30) | agent_kind | unconfirmed, INBOX note pending | pre-backend |
| `AgentNode.scope` | `"project"` iff `membersByProject` links the investigation to exactly one registry project; else `"cross-project"` | scope | unconfirmed, INBOX note pending | pre-backend |
| `AgentNode.scopeProvenance` | `"registry-member"` / `"session-global"` (companion store has no project field, STAGED T9/P1-5) | `"backend"` | n/a | pre-backend |
| `AgentNode.projectId` | owning ProjectNode.id iff scope project; null otherwise | project id | unconfirmed, INBOX note pending | pre-backend |
| `AgentNode.investigationId?` | `AgentTabDescriptor.investigationId` | thread id | n/a | wired |
| `AgentNode.documentId?` | `AgentTabDescriptor.documentId` (the sourceDocumentOf rule, companionStore.ts:76-87); never guessed | document_id | n/a | wired |
| `AgentNode.title` | `AgentTabDescriptor.title` | n/a | n/a | wired |
| `AgentNode.status?.state` | `summary.status` when the investigation is in the list window | bridge state | unconfirmed, INBOX note pending (agent-bridge) | wired |
| `AgentNode.status?.since` | `completed_at ?? started_at ?? null` | since | unconfirmed, INBOX note pending | wired |
| `AgentNode.status?.lastSeen` | null (useSeenVersion is a sidebar concern) | lastSeen | unconfirmed, INBOX note pending | absent |
| `AgentNode.status?.freshness` | `"live"` (always; the 30 s poll window is not tracked yet) | n/a | n/a | pre-backend |
| `ContextTree.status` / `error` | feeder lifecycle (`unfed` / `loading` / `ready` / `error`) | n/a | n/a | frontend |
| `Selection.projectId` | mirror of `tabTreeStore.projectId`, persisted at `antiek.workspace.tab-project` (persistence.ts:441-504) | selected project id | unconfirmed, INBOX note pending | wired |
| `Selection.subProjectId?` | session-only, raw investigation_id pre-backend | selected sub-project | unconfirmed, INBOX note pending | session-only |
| `Selection.agentId?` | session-only, `AgentNode.id` | selected agent | unconfirmed, INBOX note pending | session-only |
| `DocumentAnchor.version` | `node_text_sha256` (BookAnchorPayload / AnchorMapChunk.node_text_sha256, lib/api.ts:1253-1293) · `artifact_version` (src/api/feedback.ts:120-124) · `prose_text_sha256` (crypto.subtle at capture) · `unversioned {reason}` | n/a (frontend) | n/a | wired / typed absence |
| `DocumentAnchor.kind` / `range` | text: pin payload (scalar, chunk) or locateSelection (Reading/index.tsx:566-582, utf16, chunk) · page: `page_index_hint` · block: BackendLocator (Write/Editor/locator.ts:48-54) | BranchAnchor (tabTree.ts:77-85) | n/a | wired |
| `DocumentAnchor.quoteHint` | `anchor.quote/prefix/suffix` iff quote non-empty; null when withheld (§9.0) or metadata-only | quote/prefix/suffix | n/a | wired |
| `BookDocumentAnchor.pageIndex?` | `BookAnchor.page_index_hint` / the reader's current page (added so a text anchor can carry the page the wire wants; see §5) | page_index | n/a | wired |
| `BookDocumentAnchor.anchorId?` / `investigationId?` / `status?` | `BookAnchor.anchor_id` / `investigation_id` (first-link-wins) / `status` | same | n/a | wired |
| `DeliverableDocumentAnchor.deliverableId` | `BackendLocator.deliverable_id` | deliverable id | n/a | wired |

## 2. Pre-backend provenance rule

A node or agent may carry `source.kind: "investigation"` or `scopeProvenance: "session-global"` only with `provenance: "pre-backend"`, and only `adapters/preBackend.ts` constructs either (writerCensus.test.ts asserts the object-literal constructor `kind: "investigation",` appears in no other non-test file under `contracts/`; `tree.ts` declares the union member with a `;`). `displayKind()` is the only label function and returns `"Investigation"` for every pre-backend subproject; any consumer rendering "Sub-project" copy from a pre-backend node fails the SPR-04/07 provenance-leak lens (tree.test.ts T4 walks the whole adapter fixture). `ContextTree.provenance` is `"pre-backend"` whenever any node is (checkTree). Backend status fields are never defaulted: an absent `status` / `run.state` is absent.

The `displayKind` lens: `source.kind "default"` → "Default project"; `kind "project"` → "Project"; `kind "subproject"` + `provenance "backend"` → "Sub-project"; everything else → "Investigation".

## 3. Deletion path (the adapter is deletable by one edit)

1. Implement `adapters/backend.ts`: map the SPR-B context route to a `ContextTree` with `provenance: "backend"` on every node, `source.kind` `registry` or (if SPR-B picks nested projects) a new source member, `scopeProvenance: "backend"`, and publish through `publishTree` (the ONLY write path; it reuses identities and reconciles the selection).
2. Replace the one `<PreBackendTreeFeed />` mount line at the SPR-04 consumer root with the backend feeder. (No mount exists on this branch: SPR-04 owns it.)
3. Delete `adapters/preBackend.ts` and `adapters/preBackend.test.ts`; the `fixtures.test.helpers.ts` rows that build `PreBackendInputs` go with them.
4. No consumer edit: consumers read `useContextTree` / `useSelectedProjectNode` / `useSelection` only and never name the adapter (`index.ts` re-exports nothing from `adapters/`; writerCensus.test.ts).

## 4. Selection

- **The one writer** of the selected project is `useSelection.getState().selectProject` (selection.ts). It trims, refuses blanks, refuses a same-id call (a `tabTreeStore.selectProject` discards pendingOps and held closes, so "just to be sure" is not free) and otherwise calls `useTabTrees.getState().selectProject(id)`. `ProjectPickerContent.choose` is its only UI caller. writerCensus.test.ts proves no other non-test file calls `.selectProject(`.
- **The one persistence writer** stays `tabTreeStore.selectProject` → `persistence.writeTabProject` / `clearTabProject` (tabTreeStore.ts:514-527). The census proves only `persistence.ts` and `tabTreeStore.ts` call them.
- **The documented non-choice path**: the owner subscription in tabTreeStore.ts:745-756 re-seeds `projectId: readTabProject() ?? TAB_PROJECT_ID` on an account switch. The mirror's single `useTabTrees.subscribe` sees it (projectId or contextEpoch changed) and resets the selection to `{projectId}`, clearing sub/agent; contracts.account-isolation.test.ts I19 proves "p-a" never leaks into account-b and comes back for account-a. No `auth.tsx` entry and no `setWorkspaceOwner` call anywhere under `contracts/`.
- Sub/agent selection is **session-only**: no new storage key before SPR-B names one.
- `isSelectionPathOf` is strict: a persisted project id absent from the tree is not a prefix of any path, so `selectSubProject`/`selectAgent` refuse under a stale project (even a cross-project agent) and `useSelectedProjectNode()` returns null (R5). `reconcile` keeps `projectId` regardless.
- No registry validation of the stored id (async; a stored id may name an archived project). The ProjectPickerContent.tsx:16-18 comment ("an archived project stays listed only when it IS the selection") versus its code (the registry's default list simply excludes archived rows; nothing re-adds the selected one) is recorded, not resolved.

## 5. Anchor

- `source_locator` is omitted by every producer today. §1.4c rules 7/8/12: `TextLocator.text_sha256 = sha256(utf8(projection[start:end]))` over document-global scalar offsets. The reader's `locateSelection` (Reading/index.tsx:566-582) yields chunk-relative UTF-16 indices; the pinned payload yields chunk-relative scalars; the only digest in either is the chunk's `node_text_sha256`, which is the whole-chunk digest, not the selection digest (anchor.test.ts A4 asserts `text_sha256 !== version.sha256`). To emit it a producer must set `range.basis "document"`, `unit "scalar"` and `selectionSha256` from the html-text/v1 projection; `toBranchAnchor` then emits it with no other change (A4).
- `region_id` is never emitted (a per-projection RegionStore id).
- `BookDocumentAnchor.pageIndex?` was added beyond the binding design: a text anchor has no page in its `range`, yet the wire wants `page_index` for a text pin (`page_index_hint`) and the design's A2/A3 cases require it. It is a pagination hint, never identity, absent when unknown.
- `SpawnFlowResult.documentAnchor` is absent when `anchorId` is null AND when the pin returned a forged row with no payload (ReformatFlow.tsx:69). The `reformat_forged_anchor` reason stays in `DocumentVersion` for a producer that wants to name it; spawnFlows never fabricates a range for it.
- Dedup is anchor-blind: crossPane's reopen path activates the existing tab and leaves its `branch_origin.anchor` untouched (openers.test.tsx O4 records this). Landing at the passage on a dedup reuse is still open (R8/P1-4 half-closed: anchor on the request and on the node DONE).
- `anchorKey` carries unit+basis so a UTF-16 and a scalar anchor over the same astral text never collide; its fields 3..5 are spawnFlows' `(chunkId, start, end)` tuple.

## 6. Open questions recorded, not decided

- Archived selected project: picker comment vs code at ProjectPickerContent.tsx:16-18 — the picker's owner.
- Whether `"default"` survives as a server project (TODO ffx-nav-backend-context).
- SPR-B's run-state names ("five states"): `AgentRunState` aliases `InvestigationSummary.status` until an INBOX note lands; SPR-10's attention order cannot be designed against them yet.
- Dialogue run identity: `AgentNode.id === viewId` by construction (no run exists); SPR-B's agent bridge decides whether a dialogue ever gets a run id.
- Membership for a NESTED investigation (a member whose parent is not a member): the adapter re-files only forest roots; the nested node stays under its parent and its tab is filed on that node with `scope "project"`. Whether SPR-B's membership is inherited is unknown.
- `summary: null` investigation nodes are representable but never built by the adapter (a parent outside the window promotes the child instead of inventing the parent).

## 7. Steelman of "no module" (rigor #2) and the collapse rule

Letting each consumer (SPR-04 switcher, SPR-07 pane, SPR-10 status) read `listProjects`, `useInvestigationTree` and `useCompanion` directly costs no new module, no fingerprinting store and no selection mirror; each consumer already imports the hooks it needs, and a backend swap would be three small edits instead of one adapter. It loses because the degenerate cases are where the three would disagree: a cycle (the sidebar hook silently drops both members), a parent outside the 50-row window (orphan vs placeholder), an unlinked research tab (which project?), and the view/run identity split (a dialogue has no run). Each consumer would re-derive those and render different trees for the same account. The invariants here (checkTree, isSelectionPathOf, the one writer) are tests, which three ad-hoc derivations would not share.

Collapse rule: if only ONE consumer lands against this branch head by the time SPR-04/07/10 close, this module is overbuilt and should collapse into that consumer: keep `tree.ts` + `anchor.ts` as that consumer's local types, inline `composePreBackendTree` next to it, and delete `treeStore.ts`/`selection.ts`'s identity-reuse machinery (the mirror subscription stays wherever the project picker's writer lives).

## 8. Deviations from the binding design, recorded

1. `BookDocumentAnchor.pageIndex?` added (§5).
2. `companionStore.openAgentTab` now omits absent `investigationId`/`documentId` keys (decision 9 "absent means absent"; JSON- and `toEqual`-identical to the earlier `undefined`-valued keys; no `toStrictEqual`/snapshot test reads descriptors). The O2 design case "with a deliverable anchor the descriptor has NO `documentId` key" is unsatisfiable without it.
3. `spawnFlows.documentAnchor` absent for ReformatFlow's forged anchor (§0, §5).
4. The census regex matches the constructor literal (`kind: "investigation"` followed by `,` or `}`), since `tree.ts` must declare the union member.
5. `isSelectionPathOf` under a stale project id is strict (§4).

## 9. Verification (local head, no push, no PR)

- `npx vitest run --maxWorkers=1 --testTimeout=30000 src/workspace/contracts` — 9 files, 68 tests, all green (red-first: every suite failed on module resolution at commit `2fceac4da`).
- Regression: `src/workspace/companionPane.test.tsx src/workspace/crossPane.race.test.ts src/workspace/ProjectPicker.test.tsx src/workspace/documentTabs.projectRoundtrip.test.tsx src/modes/Reading/Reading.spawnFlows.test.tsx` — 5 files, 50 tests, all green.
- `npm run typecheck`, `npm run lint:tokens`, `npm run lint:type` — exit 0. `npm run build:check` — see the run-ledger entry for the measured index chunk.
