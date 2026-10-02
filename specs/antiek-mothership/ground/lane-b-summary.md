## Lane B grounding for the mothership (main 15e78e276)

This synthesis merges the six lane B grounding passes and applies both refuter passes. I re-checked every disputed claim in the read-only worktree myself. All but one dispute were settled by the code. The open one is whether the continuous-research service actually runs in production. That stays NOT MEASURED, because network access was out of bounds. The new RUN evidence from this pass is deliberately small: 28 passing tests covering the per-document block query, marginalia promotion and passage research, plus one probe on artifact hashing. Vitest was not run, so every frontend claim is READ at best. THREAD-CONTRACT.md Part 1 is where this work is handed to lane A (Antiek Nudge). This pass did not message that session.

The storage half of a thread fabric is real and sound. A thread already is an investigation. Each investigation has an append-only event log with Parquet sealing and replay. It also has typed spawn lineage, a synthesis archive, an owner-scoped research artifact, distilled notes, a loader that turns a trajectory back into context, and a WebSocket that pushes events per investigation.

The behaviour half is missing. No path answers a follow-up using the context a thread has already gathered. The Loop One handler drops spawn_context and never reads the parent, so every "Chat · this investigation" and "Follow this" in the UI starts a cold run. Threads cannot be scoped to a project, because nothing groups investigations. Anchors are a page number or a copy of the highlighted text, even though an unused anchor contract on main (SourceLocator plus RegionStore) survives re-rendering. Threads can only be listed globally.

The refuters were right on the most consequential point: the one end-to-end merge-into-document path cannot be reached from the UI. That path is the ReadingCompanion chain of draft, preview, apply, rewrite source and restore. Its chase list is filtered to the book's read-<doc> thread. The only code that records chases is ChaseThread, and since the reader started sending highlights to spin-research, ChaseThread is only ever opened with an /inv/:id parent. The source-body rewrite itself is still live behind the operator API. It still contradicts the binding safe-derived-asset decision, and it still reads a server file path chosen by the client. A fix that confines that path exists only as uncommitted work in the fix/source-merge-path-confinement worktree.

Several other "wired" claims narrowed the same way:

- The drag from the research shelf to the Write outline cannot be done in one window. The real path is the Write door.
- The document Explain page has no in-app link.
- ResearchThis exports the research artifact before Loop One has produced anything, and links it to a route that does not exist.
- The reading companion shows "working" forever. After 30 seconds of reading, an event lands on a reading thread that never finishes.

Three findings go the other way:

- A cross-thread, per-document knowledge query already exists (GET /write/blocks/search?source_document_id=) and passes its tests. The companion rail has a read path to extend.
- Meta-reading promotion emits seam.read_to_research in production, and /readings can file a document into an investigation. Project grouping has some footholds.
- The reserved child of an escalated question is in fact launched, by ChaseThread.

This pass also found problems no grounder reported:

- **Reused thread ids.** POST /investigations uses a client-supplied investigation_id as given and always broadcasts launches that have no operation_id. The reserved-child path reuses ids, so a repeat launch appends a second start event and can start a second run. The ACU meter counts each id once, so that second run is not billed. Whether Loop One suppresses the repeat is NOT MEASURED. Parent ids are never checked either.
- **Compose conflict check.** It can never fire, because the hashed body includes the investigation id.
- **Fork primitive.** Lane A plans to reuse create_document_version. It writes a new documents row that inherits the source's content class, which the derived-asset boundary forbids. The fork store has to be derived_asset_revisions, whose schema exists but has no repository.
- **live_spawn.py.** Lane A's GAPS.md cites orchestration/continuous/live_spawn.py as reusable code. No commit on any ref has ever contained that file.

THREAD-CONTRACT.md now exists. Lane A has written Part 2, Part 1 is still a placeholder, and neither lane has signed. Part 2 makes three claims that are wrong against main, and Part 1 should correct them before anyone builds:

- passage_research anchors by page, not by text quote and position.
- HTML projections have no fork lineage beyond the style parent.
- The branch record is written to the child's log, not the parent's.

The contract should also settle the vocabulary:

- "Thread" means one investigation. The existing seams view and breadcrumb become "trail".
- "Companion document" is the data, shown as a tab (per project) and a rail (per document).
- The data noun is "project"; the UI noun is "workstation".
- "Island" never appears in backend names, because it already names the projection's data island.
- A document fork is a derived-asset revision. Source merge is retired, not extended.

Rights gate everything that is agent-facing or exported. On main, the research artifact exports restricted text verbatim: the branch's rights tests fail 55 times against main. The MCP server returns gated text and other owners' notes. The fixes sit on c2r2-export and w5-mcp-hardening, both unmerged. No companion export or MCP resource should ship until they land.

| Lane | Area | Grade |
|---|---|---|
| B1 | Thread model | 29 |
| B2 | Merge engine | 24 |
| B3 | Companions and evidence base | 31 |
| B4 | Merge into document and fork | 21 |
| B5 | Autonomous diligence | 30 |

The grades are low because the defining behaviours are absent: follow-up with context, project scope, merging into a thread, a fork that leaves the original intact, and autonomous runs whose results come back to the thread. They are not lower because nearly every missing piece extends a module that already exists and is tested; no new store is needed anywhere.

After the list below, the heavier backends follow in this order:

1. Parent-context injection in Loop One.
2. Merge into a thread via SessionEvidencePack.
3. The derived-asset revision repository, with diff and typed accept or reject.
4. The companion builder, once the rights branches merge.
5. Flags with consent, a BudgetLedger daily cap, and a daemon spawn routed through the API.

These are the smallest gaps that unblock lane A's UX first, in order:

1. Write and sign THREAD-CONTRACT Part 1 with the three corrections and the term choices above. This needs no code, and every lane A sprint waiting on the contract depends on it.
2. Make thread ids trustworthy in POST /investigations. Refuse a reused id that already has a start event, except an exact owner replay, and require the parent to exist and be owned. This is a few lines near app.py:2758 and app.py:2842, and it stops the reserved-id double start.
3. Add document_id, kind and title to InvestigationSummary, add matching filters to GET /investigations, enumerate sealed .parquet logs, and give researches_for_passage a route. This unblocks the per-document thread list, the rail and the sidebar counts.
4. Make spin-research set parent read-<documentId>, accept model_choice, and write its escalation to read-<documentId> instead of read-spin. This unblocks island-to-thread lineage and "how I got here".
5. Move status derivation into one server helper keyed by thread kind, so reading threads show idle instead of a permanent "working". Rows then show honest states.
6. Add an optional anchor (a SourceLocator text span, region_id, and quote with prefix and suffix) to the start and spawned_from payloads, fill parent_event_id, and give RegionStore its first writer. This unblocks islands and answers Q-A4.
7. Ship ask-this-thread v0: make /thought-partner load the addressed thread's context and persist each turn as a typed event, following read.book_answered. The thread composer can then ship before Loop One can run follow-up research with parent context.
8. Extend write_folders into the workstation registry: owner-enforced, backed by typed events, with investigation and document members. Carry project_id on every launch.
9. Once the path confinement lands, refuse the legacy source-merge commit and restore through validate_commit_boundary. Lane A's merge-into-document UI can then only target derived-asset revisions.
