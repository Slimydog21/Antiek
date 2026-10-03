# Lane B grounding for the operator's addendum, R18 to R40

**Revision 2 (2026-09-27).** This revision applies lane B's cross-check of the two groundings (`cockpit/CROSSCHECK-R18-R40-LANE-A-VS-B-2026-09-27.md`, all fifteen §6 edits), the operator's second set of rulings, the delegated decisions D-P, D-A and D-M, and lane A's naming reconciliation. The prior text is kept at `cockpit/GROUNDING-LANE-B-R18-R40-2026-09-26.v1.md`. What changed, and why:
- **A crosswalk (§0).** Lane A had numbered its own proposals LB-12 to LB-25 and S9 to S21, colliding with lane B's ids. Lane B's numbers are canonical, and §0 maps lane A's onto them (edit 1).
- **Data names follow ruling 1.** Every code value stays `reading`: the mode key, `home_product`, `products[]` and the book-shaped `kind`. Only `interest` is new. This revision first recorded D-P's `books`/`book` values as a conflict with ruling 1. Lane A then withdrew them (DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27"), so O-7 is closed and no `books` alias exists anywhere (edit 2).
- **The delegated decisions are applied.** D-P goes into LB-17 and LB-18; D-A into LB-26, with LB-21 and LB-27; D-M into LB-24 and LB-25. The agent's context assembler loses v1's ambient "calling project's context" step, and the merge draft is no longer a §1.11a derivation (edit 13).
- **Seven packages are new or reassigned** (edits 3, 4 and 6, and lane B's agreements with lane A of 2026-09-27):
  - LB-1(c): sign rev 8, then co-sign rev 9, which gates LB-17 onward;
  - LB-24a: the RightsGatedPack and the §1.10 base;
  - LB-32: unified flags;
  - LB-33: retiring source merge;
  - LB-33b: a source-merge receipt read, built only if prod holds committed merges;
  - LB-34: the public-opportunities takedown leak, built and in review;
  - LB-35: serving non-book documents in the reader (F8).
- **Two scopes grow by agreement with lane A:**
  - LB-26 now owns the `evidence_index` primary-key re-key (R29-d);
  - LB-30's §1.11a `source` union gains the Books notebook's `companion_document` form.
- **These rulings are applied** (edits 5, 7 and 8):
  - 4 and 16 take Speak out of the registry and out of Converse;
  - 11 makes R33 a link;
  - 12 widens interest shelves;
  - 15 makes audio the monologue default and forbids cutting;
  - 17 keeps only the confirmed transcript;
  - 20 makes a group answer in one voice.
- **Four register facts are corrected** (edit 10):
  - R18's `parent_event_id` is set, but to the child's own start event;
  - R24 is lane B's (LB-2), and #3517 closes per ruling 21;
  - R39-public had a takedown leak (LB-34);
  - R20's source merge is live on main.
- **Seams** (edit 11):
  - `seam.speak_to_write` and `seam.research_to_read` are emitted beside `project.transferred`;
  - the `hardened` projection is declined for the MVP;
  - `model_choice` and owner BYOT join ask;
  - the nullable `thread_counts` and `spend_today` gain acceptance tests;
  - S24 to S26 are new.
- **The Speak read model** gains ruling 6's request text and honest counts (edit 9).
- **One DONE bar** (§3 rule 8) now applies to every package, and each package names its prod probes (edit 14).
- **Governance** (edit 12):
  - §6 marks each answered O-question with its ruling and gives each open one a fallback;
  - §7 closes K-12, replaces T11 citations with rulings 4 and 10, and adds the T8, source-merge, §1.11a-cap and voice rows.
- **Rev 9 items** (edit 15). §5 gains ruling 18's "talking is built", the settled names, and lane A's eight Part 2 §C requests, each mapped to a package. Contract citations are pinned as `THREAD-CONTRACT.md §x.y ("quoted anchor")`.

**Status.** Draft input to THREAD-CONTRACT rev 9, Part 1. It is not signed. Nothing from LB-17 onward, and no lane-A sprint marked R9, builds against it until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT (LB-1(c)).

**Author.** Antiek Sweep v2 (lane B, a59f7aa2). Revision 1 was synthesized from four cluster groundings: agent-output branching, projects and transfers, Books, and voice/Converse/Speak. Revision 2 applies the inputs above.

**Ground truth.** It was read read-only through `git show` and `git grep`:
- `origin/main` = `d61e5256d` (2026-09-26 23:33 +0300), unchanged at this revision, abbreviated `@d61e525`;
- the B0 and wave-5 export branch, `origin/fix/audit-wave5-c2-export` = `2be3e0d1b`;
- the companion stack, `origin/feat/companion-spr03` = `0af7a2b7b`;
- LB-2 in flight, `origin/feat/lb2-projects-tabs-20260926` = `f1ca945e2`;
- LB-34, branch `fix/public-opportunities-takedown-20260927` = `e64d24b46`, PR #3531 (GLM ACCEPT, with the Nudge train).
- LB-2, PR #3530 (GLM round 2 ACCEPT at `c26773191`; `4ec2c4a9d` admits left `research` tabs per R3).

The contract is cited at home commit `e7c13d360`, which carries rev 8.8's §1.11 correction. Every quoted contract anchor in this revision was checked to occur exactly once there.

**Evidence labels.** A citation is VERIFIED unless it is marked INFERRED. Revision 1's load-bearing citations were re-read by `~/.claude/jobs/a59f7aa2/tmp/scratch/synth/v1.sh` to `v5.sh`. Every citation new in revision 2 was read on the heads above from the `lb2-projects-tabs` worktree.

**Binding inputs.**
- The operator requirements: `forensics/REQUIREMENTS-2026-09-26.md`, R18 to R40, including the addendum quoted verbatim.
- The lane split: `cockpit/GOAL-cockpit-2026-09-26-v2.txt`.
- The operator decisions in `DECISIONS.md`:
  - D1 to D6, C1 to C5, T6, T7 and T9;
  - the prod-verification ruling of 2026-09-26;
  - the second set of rulings 1 to 21;
  - the delegated decisions D-P, D-A and D-M of 2026-09-27;
  - the naming and gates reconciliation of 2026-09-27.
- The evidence for the delegated decisions: `forensics/FABLE-PANEL-DELEGATED-DECISIONS-2026-09-27.md`.
- The contract: THREAD-CONTRACT rev 7 (signed) and rev 8.x (under audit).
- Lane A's inputs:
  - its sprint plan, `forensics/SPRINTS-LANE-A-A10-A24-2026-09-27.md`;
  - its Part 2 draft, `THREAD-CONTRACT-REV9-PART2-DRAFT.md`;
  - its defaults 1 to 8 in DECISIONS.

---

## 0. Namespace crosswalk with lane A

Both lanes numbered proposals from LB-12 and from S9 with different meanings. Lane B owns the LB namespace (Part 1), so lane B's ids are canonical. Lane A's sprint plan now cites lane B's LB-12 to LB-34, including LB-24a, 32, 33 and 34 (its header, "Lane-B dependencies use Sweep v2's numbering"). LB-35, LB-33b and LB-1(c) were agreed with lane A on 2026-09-27, after that plan was written. Lane A's A18 depends on LB-35. The table keeps lane A's original proposals so older references still resolve.

| Lane A's original proposal | Lane B's package | Note |
|---|---|---|
| "LB-12" containment: source merge and the opportunities takedown leak | LB-33 (source merge), LB-33b (conditional receipt read), LB-34 (takedown) | All new in revision 2 |
| "LB-13" registry rev 9 | LB-17 on LB-2; owner repairs in LB-15 | |
| "LB-14" B0 on main, `thread_ref`, harden | LB-19 and LB-20 | B0 itself is not an LB package; it lands with the c2-export merge |
| "LB-15" merge draft | LB-24a (base), LB-25 (draft), LB-24 (targets) | |
| "LB-16" reading home, F8, agent origin | LB-14 (continue), LB-35 (F8), LB-2 (the agent origin, already validated on the LB-2 branch) | |
| "LB-17" RightsGatedPack and the §1.10 base | LB-24a | Lane A's "LB-17 is unused" was false: LB-17 is lane B's registry |
| "LB-18" book notebook | LB-29 | |
| "LB-19" voice metering | LB-12 and LB-23 | |
| "LB-20" Speak backend | LB-13, LB-15 and LB-16 | |
| "LB-21" transfers | LB-18 (with LB-15) | |
| "LB-22" Converse | LB-21 (with LB-22 and LB-27) | |
| "LB-23" monologues | LB-30 and LB-31 | |
| "LB-24" growing agents | LB-26 (with LB-24's target) | |
| "LB-25" autonomous | LB-28, with LB-32 for flags and `diligence_queue.project_id` | |
| none | LB-1(c) | Signing rev 8, co-signing rev 9 |
| none | LB-13 (Speak intake integrity), LB-22 (book-ask scope) | Lane A had no package for these |

**Seams.** Lane A's Part 2 draft now uses lane B's S9 to S23. The earlier lane-A seam ids map as follows:

| Lane A's seam | Lane B's seam |
|---|---|
| A-S9 | S14, S15 |
| A-S10 | LB-2 (signed §1.6) |
| A-S11 | S9, S10 |
| A-S12 | S11 |
| A-S13 | S12 |
| A-S14 | S13 |
| A-S15 | S20 |
| A-S16 | S21 |
| A-S17 | S19, S17, S24 |
| A-S18 | S22 |
| A-S19 | S16 |
| A-S20 | S23, S24 |
| A-S21, the `hardened` projection | none: declined for the MVP, and lane A agrees (Part 2 draft §A3) |
| none | S18 (book ask) |
| none | S24 (flags), S25 (reader), S26 (source-merge retirement), all new in revision 2 |

---

## 1. Verdict

Lane B can meet R18 to R40 without a new store. The delegated decisions keep that true:
- an agent is a promoted thread, with no agents table (D-A);
- a merge draft persists as events on a log (D-M);
- a project is one registry row across modes (D-P).

**Which requirements lane B carries.** Two requirements (R22 and R23) belong to lane A and need only read seams from lane B. R24's project layer is lane B's LB-2; revision 1 wrongly filed it under lane A. The other twenty-one compose over one of two things:
- stores main already has: investigations and their event logs, `write_folders`, `derived_asset_revisions`, `reading_state`, account memory, the Speak tables and the Midnight Oil ledger;
- structures the signed contract already commits lane B to build: the §1.5 registry, §1.8 turns, §1.10 merge, §1.11a reformat, §1.12 companion document and §1.13 ledger.

**What main is missing.** Main lacks behaviour, plus one missing axis per cluster:
- an addressable anchor into an agent's output;
- a reviewed draft before a merge is accepted;
- a presence dimension on projects;
- a scope and participants on dialogue;
- a spend class for conversational and voice dispatches.

**What gates most of the work.**
- B0 and the wave-5 rights resolvers still sit on unmerged `fix/audit-wave5-c2-export`.
- The `RightsGatedPack` exists nowhere, with 0 hits on main and on `2be3e0d1b` (LB-24a).
- The §1.11a stores are absent from main. Only the monologue packages still need them.
- LB-2 is in flight at `f1ca945e2` and not on main.
- The rev-9 co-sign gate (LB-1(c)) holds back every package from LB-17 on.

**Forward fixes that ship first.** Seven defects on main need none of those dependencies:
1. `/voice/transcribe` and `/speech/tts` block the event loop of the single uvicorn worker (LB-12).
2. Invitee voice answers skip the correction step, and they are authored as `__operator__` (LB-13).
3. The Speak-to-Write path copies claim text, and a takedown never reaches the copy (LB-15, gated in LB-18).
4. `promote_investigation_to_deliverable` checks no owner and mints a new deliverable on every call (LB-15).
5. `GET /speak/projects` takes the write lock for a read and filters no owner (LB-15).
6. Source merge is live against T6: `/research/artifacts/source-merge/{preview,apply,commit,restore}` can rewrite a source body (LB-33).
7. The unauthenticated `/speak/opportunities` listed projects whose subject had demanded a takedown and counted voices under takedown (LB-34, built and in review).

**Two contract misstatements**, both independent of those dependencies:
- §1.14 says `GET /reading/continue` reads the table, but the route does not exist on main (LB-14).
- §1.11 said source-merge commit and restore are refused through `validate_commit_boundary`. That function has no production caller. Rev 8.8 corrects the claim: THREAD-CONTRACT.md §1.11 ("Source merge (corrected in rev 8.8)").

**One contract change is time-critical.** On the unmerged B0 payload, `BranchOrigin` can point only into a document. The output anchor that R18 needs must land before c2-export merges, or it will cost a second schema bump. That puts LB-1(c) on the export merge's critical path; see LB-19's risks.

---

## 2. Requirement register

Status key:
- EXISTS: main meets the lane-B part.
- EXTEND: a named module gains a delta.
- NEW: defined here.
- lane A only: lane B supplies at most a read seam.

| R | Lane-B status | Key evidence (`@d61e525` unless noted) | WP |
|---|---|---|---|
| R18 highlight agent output, re-prompt a sub-agent | EXTEND | <ul><li>`HighlightToolbar.tsx:45-52`: the highlight becomes the question itself, and the withheld guard runs only in the client.</li><li>`interfaces/research/api/app.py:2856-2867`: `investigation.spawned_from` is written inside `contextlib.suppress(Exception)` (:2857), so a failed write is swallowed. Its `parent_event_id` **is** set, but to the child's own start event (:2866), never to an event of the parent. Revision 1 said it was never set.</li><li>`orchestration/loop_one/orchestrator.py:2085-2098`: the child's context omits both `spawn_context` and the parent's pack.</li><li>`app.py:2754`: an owner-model launch refuses any parent.</li><li>B0 is not on main. `BranchOrigin` is document-only (`events.py:2546-2568@2be3e0d1b`).</li><li>Lane A accepts lane B's `origin.output_anchor`, which reuses the rules of `validate_node_text_anchor` (`substrate/feedback/domain.py:42`). Ruling 3: research-thread output first.</li></ul> | LB-19, LB-20 |
| R19 harden an insight or chase a question; several lanes at once | EXTEND | <ul><li>`distill_routes.py:103-163`: insights and questions carry stable ids, and `challenge` refines a note in place.</li><li>`app.py:5077-5170`: question escalation to a reserved child.</li><li>No `parent_thread_id` filter exists.</li><li>Ruling 2: Harden (an immediate, paid child) and Flag (consented, capped) are two verbs.</li><li>The unified `/flags` route has 0 hits on main. `diligence_queue` has no `project_id` (`substrate/diligence/schema.py:52-67`).</li><li>No per-claim `hardened` projection (§4 S10).</li></ul> | LB-20, LB-32 |
| R20 merge manually after seeing a draft | NEW (draft), plus a T6 CONFLICT live on main | <ul><li>`/research/artifacts/compose` is ungated (`artifact_routes.py:103-105,374-398`), and its draft GET writes files (`:341-355`).</li><li>Source merge is live at `artifact_routes.py:399,448,490,543` (preview, apply, commit, restore). `validate_commit_boundary` (`substrate/write/derived_asset_boundary.py:61`) is called only by tests.</li><li>`build_session_evidence_pack` (`orchestration/session_evidence_pack.py:195`) is reusable.</li><li>`RightsGatedPack` has 0 hits on main and on `2be3e0d1b`.</li><li>D-M: the draft is a model-written, answer-shaped synthesis adopted verbatim.</li></ul> | LB-24a, LB-24, LB-25, LB-33 |
| R21 merges group ideas for agents; a growing agent callable across projects | NEW (identity, merge into agent), EXTEND (membership) | <ul><li>`write_folder_members` is many-to-many but node-only, and emits no events (`substrate/write/folders.py:44-75`).</li><li>Account memory never promotes a prompt (`account_memory_context.py:1-10`).</li><li>`evidence_index` is absent from main.</li><li>D-A: an agent is a promoted thread with narrow, explicit reach.</li></ul> | LB-24, LB-26 |
| R22 redesigned homes | lane A only | <ul><li>No registry `/projects` route on main (LB-2 adds it).</li><li>`/reading/continue` has 0 hits.</li><li>The Speak index is `speak_routes.py:405-431`.</li><li>Homes list by presence, `?product=` (D-P).</li><li>Rulings 4 and 10: Speak and Autonomous are doors outside the mode cycle.</li></ul> | seams via LB-14, LB-16, LB-17, LB-28 |
| R23 keys to jump between products | lane A only | <ul><li>The product registry is client-side (`apps/reading/src/shell/workflowTaxonomy.ts:36`).</li><li>Rulings 7 and 8 concern lane A only.</li></ul> | none |
| R24 project keys and cockpit keys | lane B: LB-2 (with LB-17's `last_mode`); the keys are lane A's | <ul><li>On main, `/projects` exists only on the Speak router (`speak_routes.py:359`), there is no `project_tabs`, and `write_folders` is node-only.</li><li>LB-2 is in flight at `origin/feat/lb2-projects-tabs-20260926@f1ca945e2`, with `MOTHERSHIPS = ("research", "writing", "reading")` (`substrate/projects/schema.py:36`).</li><li>Ruling 21 closes #3517, which is open at head `7e0c68e58` (per the cross-check). It keeps #3485's owner scoping, revision CAS and validator.</li><li>Where a project key lands is lane A's rule (DECISIONS reconciliation).</li></ul> | LB-2, LB-17 |
| R25 an agent-first pane: one agent or a group | EXTEND (one agent), NEW (group) | <ul><li>`/thought-partner` is stateless (`app.py:6654-6732`). The client holds the history, and `investigation_id` defaults to `__sidecar__` (`:6719`).</li><li>No `thread.turn` event exists, and `ContextItem.kind` is `doc \| insight` (`app.py:1318`).</li><li>D-A: one session per (agent, project).</li><li>Ruling 20: a group answers in one voice, with per-sentence attribution.</li><li>K-12 is closed: C3 stands, and prefix+f is R25's "command F" (lane-A default 7).</li></ul> | LB-21, LB-26, LB-27 |
| R26 an add-project key opens a create page | NEW | Five ad-hoc create calls, none idempotent: <ul><li>`POST /deliverables` (`app.py:3548-3578`), which takes no owner;</li><li>`POST /speak/projects` (`speak_routes.py:359-370`);</li><li>`POST /write/deliverables/from-investigation`;</li><li>`/books/import/*`;</li><li>the Midnight Oil preflight.</li></ul>Lane A accepts the atomic seeded create. There is no `speak` seed (ruling 4). | LB-15, LB-17 |
| R27 a new project means something different per product | EXTEND | <ul><li>§1.5's `kind` is `project \| reading`. The LB-2 branch has `PROJECT_KINDS = ("project", "reading")` (`substrate/projects/schema.py:40`).</li><li>D-P, with the naming reconciliation: `home_product` and `products[]` are over `research \| writing \| reading`, and the kind adds only `interest`.</li><li>Autonomous research is a preflight only (`midnight_oil_routes.py:21-23`), and spawning is env-gated off (`orchestration/continuous/daemon.py:86`). Ruling 10 keeps it off.</li><li>The folder owner defaults to `__operator__` (`folders.py:57`).</li></ul> | LB-17 |
| R28 whole or partial transfers | EXTEND (Research→Writing, Speak→Writing), NEW (Research→Autonomous, Research→Books, Books→Research) | <ul><li>`promote_context.py:196-242` does no owner check and creates a deliverable on every call.</li><li>`speak/write_composer.py:74-91` copies claim text into `outline_blocks`.</li><li>`speak/biography.py:98-122` composes every claim and ignores `interview_projects.deliverable_id`.</li><li>`seam.speak_to_write` and `seam.research_to_read` are typed (`substrate/schemas/events.py:3739,3787`) and have no emitter, although the trail reader consumes them (`substrate/seams/thread.py:57-65`).</li><li>Speak → Writing is Speak-side (ruling 4).</li><li>Research → Autonomous needs O-11 (unruled); the fallback is per-flag consent.</li></ul> | LB-15, LB-18, LB-28, LB-32 |
| R29 agents that grow beyond projects | NEW (identity), EXTEND (membership, budgeted context) | <ul><li>Memory is owner-scoped with reference provenance (`substrate/memory/models.py:10-25`).</li><li>`note_retrieval` scans every node with no owner filter (`substrate/context_pack/note_retrieval.py:75-82`).</li><li>D-A: an agent is a promoted thread, and `evidence_index` is keyed `(owner_user_id, evidence_id)`.</li></ul> | LB-26 |
| R30 casual-interest reading projects | NEW (the interest project), EXTEND (the reading surface) | <ul><li>`folders.py:57-75`: membership is node-only, with no role or order.</li><li>`GET /books/curate` (`books.py:1282`).</li><li>Ruling 12: any long-form type, books first, non-books marked.</li><li>A non-book document cannot open in the reader: `GET /books/{id}` answers `404 book_not_found` without a `book_assets` row (`books.py:2014-2026`, detail at `:2025`). THREAD-CONTRACT.md §1.18 ("non-book documents served to the reader (lane A F8)") assigns F8 to lane B.</li></ul> | LB-17, LB-35 |
| R31 Reading becomes Books; the rabbit hole | EXTEND, label only (ruling 1); EXTEND rabbit hole | <ul><li>`workflowTaxonomy.ts:36,115` has the id `read` and the label "Read".</li><li>Ruling 1 renames the label only: code ids, routes and ⌘E stay, and every data name stays `reading`.</li><li>Talk-to-book answers from "ONE book … only this book" (`substrate/books/book_qa.py:1-9`), on the route at `books.py:2262`.</li><li>`/read/:documentId` is stored in artifacts, so it is kept.</li><li>The rabbit hole's agent origin is already in §1.6 and validated on the LB-2 branch.</li></ul> | LB-17, LB-22, LB-14, LB-35 |
| R32 an autonomous notebook in Books | EXTEND | <ul><li>The ratified per-investigation auto notebook (`docs/decisions/spr-06-auto-notebook-proposed.md`) is derived from `GET /research/{id}/distill`.</li><li>Bug: companion entry ids hash the claim text (`substrate/companions/projector.py:210-212@0af7a2b7b`), while living notes rewrite that text in place (`roles/note_taker/living_note.py:136`).</li><li>Ruling 13: v1 is spend-free, and prose is an opt-in write-up under the cap.</li><li>The lens value is `lens=reading`. The thread set follows lane-A default 2.</li></ul> | LB-29 (+ LB-9 amendment), LB-30 (the write-up) |
| R33 Books may select a Research project | EXTEND (a link, ruling 11) | <ul><li>Filing puts a document in one investigation only (`events.py:465`).</li><li>The start request carries no `project_id` (`app.py:438`).</li><li>Ruling 11: the book keeps its id and becomes a context member of the research project, with a link back. Books agents read that project and never write to it.</li><li>Promote-in-place survives only as "turn this book into a new project".</li></ul> | LB-17, LB-18, LB-21, LB-29 |
| R34 voice input everywhere | EXISTS (capture and ASR), EXTEND (bounds, off-loop, metering, input provenance, retention) | <ul><li>`read_voice.py:91-108` reads an unbounded body and calls the synchronous client. The client uses synchronous `httpx` with a 120 s timeout (`acquisition/voice/client.py:105-113`).</li><li>`/speech/tts` calls its provider synchronously (`speech.py:28-38`).</li><li>The invitee voice bound is 64 MB (`speak_routes.py:1180`).</li><li>`substrate/dispatch/config.yaml:150-158` claims a cost helper that does not exist.</li><li>`voice.captured` is typed (`substrate/schemas/events.py:383`). The client posts it through `/events/typed` right after transcription, before the operator confirms the text (`apps/reading/src/hooks/useVoiceCapture.ts:17,184`). Ruling 17 keeps the confirmed transcript only.</li></ul> | LB-12, LB-13, LB-23 |
| R35 Converse: talk to any project | NEW | <ul><li>The stateless thought partner (`app.py:6654-6732`).</li><li>Book ask is page-cited over one book (`books.py:2262-2480`).</li><li>The pattern of search restricted to given document ids exists (`substrate/books/meta_reading.py:204-225`).</li><li>Ruling 16: no Speak in the MVP. Ruling 14: turn-by-turn voice.</li></ul> | LB-21 |
| R36 time-bound monologues | EXTEND | <ul><li>Meta-reading length box: 150 wpm, 1–120 minutes (`meta_reading.py:59,75-76,99-126`).</li><li>`_bound_to_budget` truncates the script (`meta_reading.py:128`).</li><li>TTS is 8,000 characters, blocks the loop and has no server-side §9.0 check (`speech.py:19-38`).</li><li>The duration planner (`substrate/multimedia/planner.py:156-176`).</li><li>Ruling 15: audio at MVP, estimate first, never pad or cut.</li></ul> | LB-30, LB-31 |
| R37 prompt by text and voice notes during a conversation | EXTEND (turns), NEW (interrupting a monologue) | <ul><li>The confirmed-transcript guard (`substrate/books/voice_note.py:168-172`).</li><li>No turn persistence exists on main.</li><li>`at` is `{derived_asset_id, revision_id, span_id, offset_seconds}` (DECISIONS reconciliation).</li><li>Ruling 14: turn-by-turn.</li></ul> | LB-21, LB-30 |
| R38 Speak gathers insight by frictionless voice notes | EXISTS (private voice path), EXTEND (integrity, spend, request text) | <ul><li>The invitee voice route (`speak_routes.py:1379-1504`) passes raw ASR to `submit_answer` (`:1480-1497`).</li><li>Authorship defaults to `__operator__` at tier 2, as `USER_CONTENT` (`acquisition/voice/adapter.py:61,124,201,214-218`).</li><li>The follow-up stub (`substrate/speak/async_interview.py:430-446`).</li><li>Ruling 6: `topic_description` is accepted on create (`speak_routes.py:227`) but absent from `ProjectResponse` (`:230-236`) and from the list (`:405-431`).</li><li>Open contribution is default-deny (`invitations.py:61-67`).</li></ul> | LB-13, LB-15, LB-16, LB-23 |
| R39 Speak manages my projects, inbound invites and public requests | EXTEND (my projects); gated until G7 (inbound, ruling 5); EXTEND, with a leak fixed (public) | <ul><li>`GET /speak/projects` takes a write lock for a read, filters no owner, and counts every interview as a voice (`count(*)`, `speak_routes.py:414`).</li><li>Public: the unauthenticated `/speak/opportunities` (open path, `app.py:1725`) returned `subject_ref` from `list_public_opportunities`, whose query had no `speak_takedowns` predicate (`substrate/speak/pushes.py:213-227`); `/speak/feed` has one. `/speak/pushes` reads the same list (`speak_routes.py:1069`).</li><li>Revision 1 graded public "EXISTS read-only", which was wrong. LB-34 fixes it at `e64d24b46`.</li></ul> | LB-15, LB-16, LB-34 |
| R40 Speak's three sections left, detail right | EXTEND (read models only) | <ul><li>The project page composes several calls (`apps/reading/src/modes/Speak/index.tsx:8-22`).</li><li>Ruling 4: a two-pane door, with no forest.</li><li>Both lanes drop the write lock on reads.</li></ul> | LB-16 |

---

## 3. Lane-B work packages

### Rules every package inherits

1. **No parallel store.** Each concept has one home:

   | Concept | Store |
   |---|---|
   | Threads, agents, sessions, merge drafts | Investigations and their logs |
   | Projects | `write_folders` and `write_folder_members` (§1.5) |
   | Derived text, agent charters | `derived_asset_revisions` |
   | Positions | `reading_state` |
   | Durable memory | Account memory (no agent writes it; D-A) |
   | Money | `BudgetLedger` |

   The only new rows are those the contract names.
2. **Owner scope, reads and idempotency.**
   - Every new route is owner-scoped from day one, per THREAD-CONTRACT.md §1.15 ("Every route this contract adds is owner-scoped from day one").
   - Every GET uses `connect_read` and writes nothing.
   - Every mutation takes an `idempotency_key` bound to a request identity: a repeat replays, and a mismatch answers `409 idempotency_conflict`.
3. **Rights.** Every rights-bearing text is a `GatedText`, and a model sees only served text. Speak material is also filtered, at the moment of use, by live consent and by takedown.
4. **Single writer.**
   - Writes go through the API process's `connect_write`.
   - Events go through `write_event_outbox` inside the same transaction, or through strict `emit_typed`.
   - No database lock spans a model call.
   - No daemon writes directly.
5. **Spend classes.** Every new dispatch belongs to exactly one class. Every hold and settlement records `thread_id`, `project_id` and `mothership` (D-P tightening 3). The table is new in rev 9 (§1.13) and still waits on O-16 (§6).

   | Class | Members | Admission | Can stop at the cap |
   |---|---|---|---|
   | Research start | Harden and Chase from output, agent-call research, "Research further" | ACU gate before start, then the run's research budget (as for islands) | No: stops with `user`, `cancel` or `budget` |
   | Cap-admitted generation | Merge drafts (D-M), monologue text, monologue audio, the narrated notebook digest (ruling 13, opt-in), autonomy continuations, diligence, reformat | `DiligenceBudget` admission plus a `reserve_dispatch` hold per dispatch | Yes: `cap_reached`, `cap_overshoot` |
   | Conversational turn | Ask turns, Converse turns, group turns (one dispatch per turn, ruling 20), book ask, Speak interviewer follow-ups | None. Each request is bounded by `max_tokens`, and a record-only settlement is written | No |
   | Operator ASR and TTS | `/voice/transcribe`, `/speech/tts` | None. Bounded body or text, record-only settlement | No |
   | Third-party triggered | Whisper behind Speak token doors | A per-owner daily intake budget; `429 rate_limited` when it is spent | Not applicable |

6. **Edge.** A PR that adds a new top-level prefix adds it to the one-line Caddy `@api_routes` allowlist in the same change (`infrastructure/ansible/templates/Caddyfile.j2:71`). The full-glob guard (`tests/test_caddy_allowlist_coverage.py:176-230`) fails otherwise.
   - LB-2 already changed `/projects/*` to `/projects*` (`f39427b83`, "bare /projects reaches uvicorn").
   - On that branch the line still lacks `/threads*` (LB-24a), `/flags*` (LB-32), `/reformats*` (LB-30), `/derived-assets*` (LB-31), `/inbox*` (W3's inbox) and `/autonomy*` (LB-28).
   - The line is a merge hotspot that both lanes touch.
7. **Schema.** Event additions ride one sequenced bump per wave, with codegen in the same commit (§1.16). Speak event strings stay Speak-local and need no bump (`substrate/speak/events.py:10-23`).
8. **The standard DONE bar (DB-B).** Every package below closes only when all of these hold, and each states only its own acceptance items and prod probes:
   - **Red-first.** Each acceptance item has a test recorded red on the base before the fix.
   - **Mutants.** Every guard the package adds kills at least one mutant (the test-integrity floor, `tools/fake_gate_detector.py`).
   - **The full sweep.** `./.venv/bin/python -m pytest tests/ -q` is green, and so are the declared ruff and mypy gates.
   - **A critic.** A different-lineage critic ACCEPTs the exact head, with every finding closed or recorded as an override in DECISIONS. The critic is codex gpt-6-sol when it is available, and GLM or MiMo until then, as in lane A's DB-3.
   - **Landing.** The package lands through Antiek Nudge's train (the merge authority in `~/Antiek/.infinite/COORDINATION-2026-09-25-glm-twin.md`). It is never self-merged, admin-merged or auto-merged.
   - **Prod, read-only.**
     - `build_sha` equals the merge SHA.
     - The package's GET probe list passes. A probe asserts that the route reaches the API and answers the API's own JSON for an unauthenticated caller, never a 404 or the SPA's HTML. An open route is probed for its body. A POST-only route is probed through `GET /openapi.json`.
     - Agents never POST, PUT or DELETE on prod, and agent sign-in is disabled there.
     - Write flows are the operator's, run from lane A's per-sprint walkthrough checklist (DECISIONS "Prod verification (2026-09-26)").

### Order of the packages

| Tier | Packages | Gate |
|---|---|---|
| 0 | LB-12 to LB-16, LB-33, LB-33b (conditional), LB-34 | Forward fixes on main, independent of B0, LB-2, §1.11a and the rev-9 gate, because none of them consumes a rev-9 seam. LB-34 is built and in review. LB-33b is built only if Q-B1 finds committed merges on prod. |
| gate | LB-1(c) | Rev 8 signed; rev 9 Part 1 drafted from §5, audited by a different lineage, findings closed, and co-signed by both lanes. |
| 1 | LB-17, LB-18, LB-32, LB-35 | LB-2 merged, and LB-1(c) |
| 2 | LB-24a first, then LB-19 to LB-23 | The c2-export merge (B0 with the rev-9 origin, plus the wave-5 resolvers), LB-3, the §1.13 ledger extension, and LB-1(c) |
| 3 | LB-24 to LB-31 | W3 merge, LB-24a and LB-9. LB-30 and LB-31 also need §1.11a (LB-4b, LB-5); LB-25 no longer does (D-M). |

**The rev-9 co-sign gate.** No build of LB-17 or any later-numbered package, and no lane-A build from A11 on (the sprints lane A marks R9), starts until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT. Pure-UI parts may be prototyped against fixtures on branches that do not merge. The tier-0 packages LB-33, LB-33b and LB-34 are outside the gate: they are forward fixes that change no rev-9 seam. Two packages under the gate build seams that are already signed:
- LB-32's `/flags` routes are signed at rev 3, in THREAD-CONTRACT.md §1.13 ("Flag identity and lifecycle (rev 3)");
- LB-35's reader serving is signed at rev 7, in THREAD-CONTRACT.md §1.18 ("non-book documents served to the reader (lane A F8)").

Each is gated only for its rev-9 delta: `diligence_queue.project_id`, and ruling 12's shelf admission. The co-sign may split those deltas out if lane A needs the signed halves earlier.

### LB-1(c) · Sign rev 8; draft, audit and co-sign rev 9 Part 1 (the gate)

**Scope**
- Sign rev 8 once its audit rounds close, including rev 8.8's §1.11 source-merge correction.
- Draft rev 9 Part 1 from §5 of this grounding, and fold in lane A's Part 2 draft (`THREAD-CONTRACT-REV9-PART2-DRAFT.md`).
- Pin every rev-9 citation as `path@<commit>` plus a quoted anchor phrase. Line numbers alone are not used.
- Commission a different-lineage audit of rev 9 (Part 1 and Part 2), and close every finding or record it as an override in DECISIONS.
- Collect both lanes' signatures on rev 9.
- Record a DECISIONS row for every override of a signed decision. For lane B, that is only the D4 exception, and only if the operator grants O-11.

**Acceptance**
- The signature block of `THREAD-CONTRACT.md` names rev 8 and rev 9, signed by both lanes, with the audit's ACCEPT cited.
- A grep of rev 9 finds no bare `path:line` contract citation without an anchor phrase.

**Depends on:** the rev-8 audit rounds and lane A's Part 2 draft.

**Done:** the signatures and the audit ACCEPT are the evidence. There is no code and no prod probe.

**Risk:** if c2-export is ready to merge before rev 9 is co-signed, LB-19's origin delta either lands early under a DECISIONS override or costs a second schema bump.

### LB-12 · Voice and TTS service hardening (R34)

**Scope**
- Move the provider calls in `/voice/transcribe` and `/speech/tts` off the event loop, using the `_off_loop` pattern already used at `speak_routes.py:1480-1497`.
- Bound the transcribe body at 25 MB on the server and refuse larger bodies with `413 too_large`.
- Take optional `thread_id`, `project_id` and `language`, each checked for existence and owner.
- Return `{transcript, language, duration_seconds, asr: {provider, model}, cost_cents | null}`. Cost is duration × $0.006 per minute, and `null` when the duration is unknown.
- **The transcribe route persists nothing** (ruling 17: keep the confirmed transcript only). This retires the client's `voice.captured` post through `/events/typed` right after transcription (`useVoiceCapture.ts:184`).
- **Input provenance.** Launch (`POST /investigations`), ask and reformat accept `input: {modality: text | voice, asr_model?, language?, duration_s?, edited}`, and the prompt stays `origin: operator`.
  - For a voice input, the consuming route writes `voice.captured {transcript: the submitted text, transcript_status, language, duration_seconds, audio_ref: null}` on the target thread, in the same transaction as the launch or turn.
  - That route returns `voice_capture_event_id`, and the start or turn payload carries it. The client never supplies the id.
- **The §9.0 gate on TTS.**
  - `/speech/tts` gains an optional `source: {document_id, page_index} | {turn_event_id}`. With a source, the server narrates only the text it serves for that ref: a withheld ref answers `422 not_servable`, and a `cite_only` passage becomes the fixed spoken marker.
  - A bare `{text}` call cannot be gated, because the server cannot know where the text came from. It stays for operator-typed text only, is recorded in §1.19 as ungated, and is listed with the pre-G7 holes (§1.15).
  - Lane A moves every rights-bearing read-aloud to the `source` form (A17 retires `useSpeech` from the ReadAloud paths).
- Keep no audio.
- Correct the comment at `config.yaml:150-158`, which names a `processing.transcription` helper that does not exist.

**Acceptance (red-first)**
- `/health` answers within 200 ms while a stubbed transcription sleeps 2 s. This is red today: `read_voice.py:101` calls the synchronous client on the loop.
- A 25 MB + 1 byte body gets 413 before the provider is called.
- An unknown `thread_id` gets 404.
- `cost_cents` is `null`, never `0`, when the duration is missing.
- A transcription writes no event to any log.
- A voice launch records `input.modality: voice`. Its `voice.captured` holds the submitted (edited) text, not the raw ASR, with `audio_ref: null`, and the response returns its id.
- A `/speech/tts` call whose `source` is withheld never reaches the provider (asserted at the provider seam).
- No audio file exists under the storage root after a transcription.

**Depends on:** none. Settlements arrive with LB-23. Lane A's A17 removes the client's `/events/typed` post.

**Done:** DB-B. Probes: `GET /health` and `GET /openapi.json` listing the `input` and `source` fields.

**Risks**
- The operator's audio goes to OpenAI. Retention stays "never" (ruling 17).
- Spend is unmetered until LB-23.

### LB-13 · Speak intake integrity (R38)

**Scope.** Close the six gaps in R38:
1. Wire the interviewer dispatch, keeping `max_followups=3` and a bounded `max_tokens`. HTTP callers omit it today.
2. Store invitee voice answers with `transcript_status: unconfirmed`. They stay out of claim extraction until the operator confirms them (O-19; lane A's A19(6) renders it).
3. Author informant voice notes by their contributor handle through `speak_contributors`, with a contributor source kind, never operator tier 2 or `USER_CONTENT`. This waits on a rights review.
4. Rate limits and bounds:
   - per-token and global voice rate limits;
   - a per-owner daily Whisper intake budget that answers `429 rate_limited`;
   - the invitee voice body bound drops from 64 MB (`speak_routes.py:1180`) to 25 MB, matching LB-12, and a larger body is refused with 413 before the provider call.
5. Add the Speak-local strings `speak.answer.received` and `speak.claims.proposed` on the project log.
6. When `record` is revoked, exclude that interview's `voice_note` documents from every Speak-scoped retrieval.

**Acceptance (red-first).** Each gap reproduces red before its fix:
- An HTTP follow-up equals the stub string (`async_interview.py:440-446`).
- An unconfirmed invitee answer reaches claim extraction (`speak_routes.py:1487-1497`).
- The stored document's author is `__operator__` (`adapter.py:124,201`).
- A token past its hourly limit is still served.
- A 25 MB + 1 byte invitee body reaches the provider.
- A revoked interview's chunks are still retrievable. This one is INFERRED, since `consent.py:126-150` only flips flags.

**Depends on:** a rights review for item 3; LB-23 for settlements.

**Done:** DB-B. Probes: `GET /speak/feed` (open) and `GET /openapi.json`.

**Risks**
- Informant audio goes to OpenAI, and the operator's consent label reads only "Sharing a memory" (`apps/reading/src/modes/Speak/Invites.tsx:44-48`). The invitee copy is UNVERIFIED.
- Speak writes its events outside the database transaction (`substrate/speak/events.py`), so new strings go through the outbox.

### LB-14 · Continue reading (R22 Books home, R31)

**Scope**
- Add `ReadingStateStore.list_for_owner(owner, limit)`. The store has only `get` and `put` today (`substrate/books/reading_state.py:122,137`).
- Add `GET /reading/continue`, returning `{items[{document_id, title, author, document_type, gate, progress: {page_index, page_count, pct} | null, updated_at}]}`. `page_count` comes from `book_assets`, so a non-book document served by LB-35 reads `progress: null`.
- Keep the prefs allowlist empty unless the operator rules otherwise.

**Acceptance (red-first)**
- A document with no known page count returns `progress: null`, never 0%.
- While another process holds the writer, the GET answers a bounded 503 rather than hanging, and it takes no write lock.
- Another owner's rows never appear.

**Depends on:** none. The `/reading/*` glob already exists at the edge.

**Done:** DB-B. Probe: `GET /reading/continue`.

**Risks:** none beyond owner scoping.

### LB-15 · Owner, idempotency and takedown repairs on existing create and promote paths (R26, R28, R38, R39)

**Scope**
- `promote_investigation_to_deliverable` checks the investigation's owner and takes an idempotency key. Today it looks up the synthesis by id only (`promote_context.py:196-201`) and inserts a deliverable on every call (`:232-242`).
- The Speak draft reuses `interview_projects.deliverable_id` once it is set, so a redraft is a new revision of the same deliverable. That is lane-A default 4, and it is listed for the operator in §6. The draft composes only claims that are not under an active takedown and that hold `record` consent. Today `speak/biography.py:119-122` mints a new deliverable, and `:101-111` composes every claim.
- `POST /deliverables` and `POST /speak/projects` bind the request owner. `POST /speak/projects` also accepts `interview_guide` (ruling 6). The column exists on `interview_projects`, and the `/interview-projects` routes already read it (`app.py:4640`).
- `GET /speak/projects` filters by owner and reads through `connect_read`. This is coordinated with board claim `codex-speak-project-index-read-20260924`.

**Acceptance (red-first)**
- Promoting another owner's investigation is refused.
- Two calls with one key create one deliverable.
- A claim under takedown never lands in `outline_blocks` (repro against `write_composer.py:74-91`).
- Two Speak drafts produce one deliverable.
- Rows created through these routes carry the request owner, never `__operator__`.
- `interview_guide` given on create is returned by LB-16's detail.

**Depends on:** W1 owner-on-start for the full investigation owner check. Until then, the check reads the start payload's `owner_user_id` where it is present and refuses a mismatch.

**Done:** DB-B. Probe: `GET /speak/projects`.

**Risks**
- Collision with the codex claim and with PR #3011's owner binding.
- The serve-time gate for claim text already copied is LB-18's.

### LB-16 · Speak section read models (R38, R39, R40)

**Scope.** Read-only routes, one call per pane:

| Route | Returns / behaviour |
|---|---|
| `GET /speak/sections` | `{my_projects: {count, attention}, invites: {count, state}, public: {count, contribution: live \| gated_G7}}` |
| `GET /speak/projects/{id}/detail` | Composed from the existing functions (`get_project`, the invite lifecycle, `async_interview.resume`, repings, `economics_mode`); fields listed below |
| `GET /speak/public/{project_id}` | An exact open path beside `/speak/feed` and `/speak/opportunities` (`app.py:1724-1725,1814`), filtered by takedown |
| Invites section | Answers `state: gated_G7` (ruling 5). A bookmark list of invite links opened while signed in is an optional later route. |

The detail route returns:
- `project`, with `topic_description` and `interview_guide` (ruling 6)
- `economics_gate`
- `invites[]`
- `interviews[{interview_id, who, status, consent, pending_questions, last_answer_at, unconfirmed_answers}]`
- `arrivals_unseen`
- `claims_summary`
- `repings[]`

**Ruling 6 on the existing reads.** `ProjectResponse`, the `GET /speak/projects` list, the feed and the opportunities list return `topic_description`. List rows carry three counts, replacing today's `count(*)` over every interview (`speak_routes.py:414`):
- `contributed_voice_count`: interviews with at least one received answer and no active takedown;
- `invited_count`;
- `pending_reping_count`.

This definition of a contributed voice is lane B's proposal for the co-sign.

**Acceptance (red-first)**
- No GET in the module takes `connect_write` (a test over the route module), and a held writer yields a bounded 503.
- Counts are `null`, never `0`, when unreadable.
- An invited interview with no answer is counted in `invited_count` and not as a voice. This is red today.
- A taken-down subject is absent from the public detail, and the detail never returns its `subject_ref`.
- Another owner's project is absent from the sections and answers 404 on detail.

**Depends on:** LB-15 (or the codex claim) for the owner filter; LB-13 for arrivals; LB-34 for the shared public-listing predicate. The seen state waits on the W3 inbox.

**Done:** DB-B. Probes: `GET /speak/public/{project_id}` (open) plus `GET /speak/sections` and `GET /speak/projects/{id}/detail`.

**Risks:** inbound invites stay honestly gated until G7 (invariant 5).

### LB-33 · Retire source merge (R20; T6)

**Scope**
- `POST /research/artifacts/source-merge/{preview,apply,commit}` answer `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}`. The answer comes before any lock is taken or receipt written. The alternatives name the T6 flows, which is lane A's request C3.
- **`restore` depends on Q-B1** (§6: "Does prod hold any `source_merge.committed` without a later `.restored`?").
  - If prod holds none, `restore` retires in this package with the same 410.
  - If prod holds some, `restore` stays live as their undo, and LB-33b adds the receipt read that lets lane A offer it. `restore` then retires once every such merge is restored or the operator releases it.
- **Lane A's client removal lands first.** Branch `design/retire-source-merge-ui-20260927` (A10(4)) removes every client caller, including the restore client, before LB-33 lands. Until LB-33b exists, a live `restore` is reachable only through the API.
- The contract's false claim is already corrected in rev 8.8: THREAD-CONTRACT.md §1.11 ("Source merge (corrected in rev 8.8)").

**Acceptance (red-first)**
- Preview, apply and commit each answer 410 with that body. No `connect_write` opens, which is asserted, and no receipt row is written.
- Preview opens no writer. This is red today: its docstring says "no-write", but it opens `connect_write` (the cross-check, §3 #19).
- On Q-B1's answer:
  - if prod holds no committed merges, `restore` answers the same 410;
  - otherwise it still restores a committed merge (regression).
- A grep shows 0 client callers of preview, apply, commit and restore once lane A's branch is in.

**Depends on:** Q-B1 for `restore` only. It lands after lane A's `design/retire-source-merge-ui-20260927`.

**Done:** DB-B. Probe: `GET /openapi.json` showing the retired routes.

**Risks:** retiring `restore` while a committed merge exists on prod would strand it. Hence Q-B1.

### LB-33b · Source-merge receipt read (R20; conditional on Q-B1)

**Built only if** the operator confirms that prod holds committed source merges with no later restore (Q-B1). Otherwise it is not built, and `restore` retires in LB-33.

**Scope**
- `GET /research/artifacts/source-merge/receipts?document_id=` returns the committed and unrestored merges, through `connect_read`: `[{source_revision_id, twin_revision_id, before_source_hash, after_source_hash, committed_at}]`.
- **Where the receipts live.** They come from `source_merge_body_commits`, less the rows that `source_merge_body_restores` names by `commit_id` (`substrate/research_artifact/source_merge.py:119-158`). `committed_at` is the commit row's `created_at`.
- Lane A shows "Restore the original" only where a receipt exists.
- **Owner scope.** The route is owner-scoped per rule 2. Neither receipt table has an owner column, and `parent_reading_thread_id` is a per-document `read-<doc>` id. So the scope reduces to the operator identity today, which is single-operator. It is listed with the pre-G7 holes (§1.15), and the route retires with `restore`.

**Acceptance (red-first)**
- The GET writes nothing and takes no write lock.
- A committed merge is listed, and a restored one is not.
- A document with no merges returns `[]`, never an error.
- A request without the operator identity is refused.

**Depends on:** LB-33 and Q-B1.

**Done:** DB-B. Probe: `GET /research/artifacts/source-merge/receipts`.

### LB-34 · Public opportunities honour takedowns (R38, R39)

**Status: built and in review.** The fix is one commit on main `d61e5256d`: branch `fix/public-opportunities-takedown-20260927` at `e64d24b46`. No PR was open for the branch when this revision was written (checked with `gh`, 2026-09-27).

**Scope.** `list_public_opportunities` (`substrate/speak/pushes.py:196-277@e64d24b46`) is the single source for the unauthenticated `/speak/opportunities` (`speak_routes.py:991-1005`) and the operator's `/speak/pushes` (`:1069`). The change does four things:
- it excludes a project whose subject has an active takedown;
- it stops counting an interview under an active takedown in `voice_count`;
- a reversed takedown restores both;
- a claim takedown leaves the project listed, since claims are never part of this list.

**Acceptance (red-first).** These results come from the commit's own record; they were not re-run for this revision.
- `tests/test_speak_opportunities_takedown.py`: the subject and interview cases are red on main (the project stays listed; `voice_count` 2 == 1), and the claim case guards against over-filtering.
- Four mutants are killed: no subject predicate, no interview predicate, reversed takedowns still hiding, and any takedown hiding.
- All 177 Speak tests pass, and the declared ruff and mypy are clean.

**Remaining for DONE:** the different-lineage critic's ACCEPT, the train, and the prod probe.

**Done:** DB-B. Probes: `GET /speak/opportunities` (open), and `GET /speak/pushes`.

### LB-17 · Registry presence, shapes, create seeds and the shelf (R22, R24, R26, R27, R30, R31, R33), per D-P

**Scope.** Built on LB-2's registry, one registry and one identity across modes (D-P), with every data name at `reading` (ruling 1; DECISIONS reconciliation).

*Folder fields*
- `home_product: research | writing | reading`. It is the birth product and immutable. It picks the create page and the default mode, and it never filters a home.
- `products[]` is a non-empty subset of `{research, writing, reading}`. Homes, `mode.cycle` and transfer offers read it. Its values equal the mode keys (`project_tabs.mothership`), so presence and trees join without a mapping.
- `kind: project | reading | interest`. Only `interest` is new.
  - `reading` is the rev-7 book-shaped project. Its `primary_document_id` is required and must be servable in the reader: a `book_assets` row until LB-35 lands, then any long-form type LB-35 serves.
  - `interest` has a null primary.
- `derived_from_project_id?` is set by a partial transfer (LB-18).
- There is no `speak` or `autonomous` value anywhere. Speak joins only by link (ruling 4), and Autonomous is `member_role: managed` on threads (ruling 10; D-P tightening 1).
- **Legacy rows.** Existing `write_folders` rows migrate as `kind: project, home_product: writing, products: [writing]`, so they appear in Research or Books only once transferred.

*Member fields*
- `member_kind` gains three values:
  - `speak_project`, a link only (ruling 4);
  - `derived_asset`;
  - `project`, a context link. Aggregates never recurse through it.
- `member_role: primary | shelf | context | managed | agent | null`.
- `reach` is set exactly on `agent` and `managed` rows and is CHECK-constrained to `attached_only` (D-A). A second value needs a ruling. It lands here so the member table is rebuilt once.
- `ordinal`, the name both lanes settled on.
- **Shelf admission** (ruling 12): any long-form `document_type`, from a closed list shared with LB-35. Books come first, and non-books are marked by `document_type`. Agents only propose; an agent actor adding a shelf member gets 403.

*`POST /projects {home_product, kind, title?, seed, idempotency_key}`*
- The seed union:
  - `question`, stored and not launched;
  - `blank_deliverable`, which never launches research (lane-A default 1);
  - `from_investigation`;
  - `book {document_id}`, which makes kind `reading`;
  - `interest {title, seed_prompt?}`.
- Removed seeds:
  - There is no `speak` seed. Speak creates stay on `POST /speak/projects` (ruling 4).
  - There is no `autonomous` seed until LB-10 lands (D-P).
  - `template: biography` moves back to the Speak side, where `create_biography` already lives (ruling 6).
- The registry row, the seed rows, the members and `project.created` are all written in one `connect_write` transaction through `write_event_outbox`.
- The response is `{project, next: {kind: open_mode | launch_first_question | import_book, ref?}}`.

*Reads and writes*
- `GET /projects?product=&archived=` lists by presence and has no `home_product` filter. Each row carries:
  - §1.5's aggregates `thread_counts | null` and `spend_today | null`, each null with a reason when unreadable, never `0`;
  - `last_mode`, derived from the newest `project_tabs.updated_at` per mode. It is a field lane A may use (ruling 8); where a key lands is lane A's rule in DECISIONS;
  - `shelf_count | null`;
  - `linked_project_ids[]`, derived from `project` context members.
- `GET /projects/{id}/shelf`, and `PUT /projects/{id}/shelf {document_ids[], expected_version}` with compare-and-set.
- **The ruling-11 link.** `POST /projects/{id}/members {member_kind: project, member_role: context, ref, link_back: true}` writes both rows (research → book, and book → research) in one transaction. The book keeps its id.
- **Leaving a product.** `DELETE /projects/{id}/products/{product}` writes `project.product_left`, which is "Leave Writing", never "Archive". Leaving the last product answers `409 last_product`.

*Mode key and events*
- The mode key stays `reading`, with no alias (ruling 1). This matches LB-2's `MOTHERSHIPS`.
- Typed events: `project.created`, `project.members_changed`, `project.shelf_changed` and `project.product_left`. `project.transferred` is LB-18's.

**Acceptance (red-first)**
- A double press with one key yields one project, and the same key with a different body answers 409.
- A crash injected after the seed insert leaves no registry row.
- Seed rows carry the request owner.
- `kind: reading` with a non-servable document answers `422 seed_invalid`.
- `home_product: speak`, `home_product: autonomous` and `home_product: books` each answer `422 seed_invalid {reason: product_invalid}`.
- A PATCH that changes `home_product` answers 422.
- A stale shelf PUT answers 409, and an agent actor adding a shelf member answers 403.
- A second `reading` create for the same owner and document returns the same project.
- A legacy folder lists under `?product=writing` only.
- A project born in Writing and transferred whole to Research lists under `?product=research`.
- `thread_counts` and `spend_today` are present on every row, and each is `null` with a reason when the ledger is fault-injected unreachable, never `0`. The in-flight LB-2 routes do not compute them yet.
- A `reach` value other than `attached_only` is refused by the table.
- The ruling-11 link writes both rows or neither.
- `/tabs/books` answers 422 from LB-2's validator, so no alias exists.

**Depends on:** LB-2, LB-15 and LB-1(c).

**Done:** DB-B. Probes: `GET /projects` and `GET /projects/{id}/shelf`.

**If D-P is overturned** (its reconsider-if list in DECISIONS): `mothership` is already on tab rows and, with LB-23, on spend rows, so splitting into per-product identities is a mechanical partition, not a migration of meaning.

**Risks**
- Owner defaults leak today in three places (`folders.py:57`, `POST /deliverables`, `create_project`).
- Legacy threads with no `project_id` are adopted by document only (LB-18).

### LB-18 · Transfers and the Books lens (R28, R33), per D-P

**Scope**
- `GET /projects/{id}/transfer-candidates?to_product=` returns threads, claims or long-form documents, each with its gate.
- `POST` and `GET /projects/{id}/transfers {to_product, scope: whole | partial, to_project_id?, selection, idempotency_key}`.
  - The outbox event is `project.transferred {transfer_id, from_project_id, to_project_id, to_product, scope, selection_digest}`.
  - The registry change, the members and the event are one `connect_write` transaction.
- Semantics:
  - **Whole:** the same project id gains `to_product` in `products[]`, and its tree in that mode is its own (T9).
  - **Partial:** a new or named target project receives member references, never copies, with `derived_from_project_id` set.
- The pairs:

  | Pair | Behaviour |
  |---|---|
  | Research → Writing | Several investigations, whole or partial, with optional `node_ids[]`. One section per investigation, `graph_node` references, and the deliverable registered as a member. |
  | Research → Books (`to_product: reading`) | Whole: the project gains `reading`, and its shelf is picked from the long-form candidates. Lane A lands it on a "Which book(s)?" step. Partial: a new `reading` or `interest` project with a shelf and `derived_from_project_id`. |
  | Books → Research | "Turn this book into a new project", the one remaining promote-in-place (ruling 11): `kind` goes from `reading` to `project`, `products[]` gains `research`, and the id, members and threads are unchanged. |
  | Research → Autonomous | LB-28: managed threads in place. |
  | Speak → Writing | **Speak side, not this route**, because a Speak request is not a registry project (ruling 4). `POST /speak/projects/{id}/draft` (`speak_routes.py:844`) is extended: it creates or reuses a Writing project (`home_product: writing`) that holds a `speak_project` link, and it reuses `interview_projects.deliverable_id` (LB-15). Selected `claim_ids[]` or `interview_ids[]` are filtered as in LB-15. |

  Every other pair answers `422 transfer_not_supported`.
- **R33 from the Books side is not a transfer.** It is LB-17's ruling-11 link.
- **Speak claims in Write.** A serve-time gate on `source_block_kind='speak_claim'` blocks checks for a live takedown and for scope, where `attribute` is needed to name the informant. Share or export answers `422 speak_publish_required` (the O-12 fallback).
- **Seam events** (lane A's request C8), written in the same transaction as the transfer:
  - Speak → Writing emits one `seam.speak_to_write {entity_id: claim_id, provenance_ref: <draft or transfer id>, contributor_interview_ids}` per claim.
  - A Research → Books partial transfer emits one `seam.research_to_read {entity_id: <insight node id>, provenance_ref: transfer_id}` per selected insight node. The payload's `entity_kind` is fixed to `insight_node` (`substrate/schemas/events.py:3739-3745`), so document-only selections emit none.
  - The trail reader (`substrate/seams/thread.py:57-65`) shows them.
- `GET /investigations` gains `document_ids[]`, and legacy threads with no `project_id` are adopted by shelf document. In the Books lens, a thread off the shelf is hidden; in Research it stays visible.

**Acceptance (red-first)**
- A partial Research → Writing transfer places only the selected nodes and sets `derived_from_project_id`. A whole transfer keeps the same project id.
- A whole Research → Books transfer keeps the id and adds `reading`. Books → Research keeps the id and changes the kind.
- A retry yields one transfer, one deliverable and no second seam event.
- Two Speak → Writing sends reuse one project and one deliverable.
- A Speak claim taken down after transfer has its block text withheld on the next serve. This is red today: the copy survives.
- A Write export containing testimony answers 422.
- A book that cannot be served is listed `cite_only` with its reason, never dropped.
- A thread outside the shelf is hidden in the Books lens and visible in Research.
- An unsupported pair answers 422.

**Depends on:** LB-17, LB-15, W1 owner-on-start, the W3 member table for the Speak gate, and LB-1(c).

**Done:** DB-B. Probes: `GET /projects/{id}/transfer-candidates` and `GET /projects/{id}/transfers`.

**Risks**
- Rights over testimony leaving Speak.
- Bypassing Speak's publish scope and its escrow path (`speak_routes.py:864-887`).
- The GET scan cost over every `.jsonl` log (`app.py:3079`).
- The existing Speak → Write copy (`write_composer.py:74-91`) is a defect to gate, never a precedent (D-P).

### LB-32 · Unified flags (R19, R28, R31)

**Scope**
- `POST /flags {intent: read | diligence, target, reason, project_id?, idempotency_key}` creates a flag with a server-derived `actor`, per THREAD-CONTRACT.md §1.13 ("Flag identity and lifecycle (rev 3)").
  - `intent: diligence` lands in `diligence_queue`, the diligence-flag store of THREAD-CONTRACT.md §1.13 ("Store for diligence flags (rev 8").
  - `intent: read` lands in the `question.identified` family.
- `GET /flags?intent=read|diligence&project_id=&cursor=` lists the owner's flags through `connect_read`, newest first and cursor-paged.
  - A read flag whose document cannot be resolved stays listed with `document: null` and `reason: unresolved_document`.
  - This is the extension the contract names in THREAD-CONTRACT.md §1.13 ("extended into `GET /flags?intent=&project_id=`"). `GET /watch-for-later` stays as an alias until lane A moves its callers.
- `diligence_queue` gains a nullable `project_id`; it has none on main (`substrate/diligence/schema.py:52-67`). Legacy rows read `project_id: null`.
- Consent, decline and launch stay on the shipped routes, per THREAD-CONTRACT.md §1.13 ("The shipped `/diligence/flags*` routes stand"). LB-32 adds no launch path, so D4 is untouched.
- The edge line gains `/flags*`.

**Acceptance (red-first)**
- Another owner's flags never appear.
- The GET takes no write lock and writes nothing.
- A diligence flag created with a `project_id` lists under that project and is stored in `diligence_queue`.
- An unresolved read flag is listed with its reason, never dropped.
- A cursor page never repeats or skips a flag under concurrent inserts.
- An `actor` in the request body is ignored.
- A replayed key returns the first flag, and a mismatched body answers 409.

**Depends on:** LB-2 (project ids) and LB-1(c).

**Done:** DB-B. Probe: `GET /flags?intent=read`.

### LB-35 · Non-book documents in the reader (R30, R31; F8)

**Scope**
- THREAD-CONTRACT.md §1.18 ("non-book documents served to the reader (lane A F8)") already assigns F8 to lane B in W1. Ruling 12 makes it load-bearing, because interest shelves admit any long-form `document_type`.
- `GET /books/{id}`, the reader's route behind `/read/:documentId`, answers `404 book_not_found` for a document with no `book_assets` row (`books.py:2014-2026`, detail at `:2025`).
- With LB-35, `GET /books/{id}` and the reader serve any long-form `document_type` through the same servability gate as books.
  - A long-form document without that row is served as one flowing document: `{document_id, title, author?, document_type, gate, page_count: null, text: GatedText}`.
  - A `cite_only` or `withheld` document returns its gate and reason, and no text.
- The long-form set is a closed list of `document_type` values that LB-17's shelf admission also reads. The package enumerates it from main's values; it is not enumerated here.
- It serves ruling 12's interest shelves, and lane A's A18 depends on it.

**Acceptance (red-first)**
- A long-form non-book document opens with its gate. This is red on main, which answers 404.
- A withheld non-book document returns no text.
- A book's response is unchanged (regression).
- A document outside the closed list still answers 404, with a reason.
- The GET writes nothing.

**Depends on:** tier 1, after LB-2. It shares LB-17's admission list, and LB-1(c) applies to ruling 12's delta only.

**Done:** DB-B. Probe: `GET /books/{id}`.

### LB-24a · The RightsGatedPack and the §1.10 base, with no model call (R20, R21)

**Scope**
- **The adapter.** NEW `RightsGatedPack`, per THREAD-CONTRACT.md §1.10 ("Rights-gated pack (rev 3)").
  - Items are built from source events: each retrieval's `supporting_claims[]` with its `chunk_ids` and `edge_ids`, and each archived synthesis with its manifest pins.
  - Each item passes `resolve_pin_sources` and `resolve_synthesis_sources` (`services/html_projection/resolvers/substrate_refs.py:360,377@2be3e0d1b`) and `build_body._excerpt_cleared` (`build_body.py:71@2be3e0d1b`).
  - Every item carries `content: GatedText`.
  - It exists nowhere yet: 0 hits on main and on `2be3e0d1b`.
- **The preview.** `POST /threads/merge/preview {thread_ids[]}` returns `{preview_digest, items[{item_id, content, origin_thread_id}], conflicts[]}`, as signed. It writes nothing.
- **The commit skeleton.** Signed §1.10's steps 1–5 sit behind `POST /threads/merge`: `thread.merge_started` first, the members' pending `merged_into`, the merged start event, `merge_pending`, and a 503 that resumes on replay.
  - Until LB-25 lands, the route answers `422 draft_required` to every request, because D-M allows no commit without a draft.
  - The skeleton is exercised by tests through its internal function with a fixture draft.
- No model is called anywhere in this package.
- The edge line gains `/threads*`.

**Acceptance (red-first)**
- A withheld chunk's text never appears in the preview. The withheld-chunk fixture is red against a pack built naively from `build_session_evidence_pack`.
- A `cite_only` item carries pointers only.
- A rights change re-keys `preview_digest`.
- A replay resumes from `merge_started`, and a partial merge never reports success.
- The preview opens no writer.
- `POST /threads/merge` answers `422 draft_required` before LB-25.
- A cross-owner member answers 403.

**Depends on:** the c2-export merge (B0 and the wave-5 resolvers) and LB-1(c). LB-20, 21, 24, 25, 26, 29, 30 and 31 depend on it.

**Done:** DB-B. Probe: `GET /openapi.json` listing the preview route.

**Risks:** if the base slips past W3, D-M says to ship preview-only with Accept disabled, never the compose page.

### LB-19 · Output segments and anchors (R18)

**Scope**
- The `OutputAnchor` type (rev 9 §1.4b). Validation reuses the rules of `validate_node_text_anchor` (unicode-nfc-v1, 32-scalar context; `substrate/feedback/domain.py:42`) rather than a second validator.
- `GET /investigations/{id}/outputs`, owner-scoped, returns segments with `content: GatedText` in display order.
  - **Phase 1** (ruling 3: research-thread output first) draws on `synthesize.delivered`, `graph.node.inserted` and `note.refined`.
  - **Phase 2**, after LB-3, adds `read.book_answered` and `thread.turn`.
- A reformat thread answers `422 use_probe` and points at §1.11a spans.
- A quote is kept only for a segment that was served when it was pinned.
- **The shared offset fixture** lives at one path that both lanes import byte-for-byte (lane A's request C6). The path is `apps/reading/src/lib/api/__fixtures__/output_anchor_nfc_v1.json`, beside #3530's `projectTabs.snapshot.json` (agreed with lane A 2026-09-27). Vite's fs guard refuses imports from repo-root `tests/`, so pytest reads the file by path, the same pattern as #3530. Neither lane keeps a copy.

**Acceptance (red-first)**
- An anchor into a withheld segment answers `422 output_not_servable`.
- A tampered `segment_sha256` answers `409 output_anchor_stale`.
- A refined note yields a new segment, and the old anchor still validates against its own event.
- A reformat thread answers 422.
- The shared fixture proves that the server's NFC offsets equal lane A's rendering of `content.text`.

**Depends on:** B0 merged, with `BranchOrigin.output_anchor` added **before** the merge; the wave-5 excerpt gate `_excerpt_cleared`; LB-3 for phase 2; LB-1(c).

**Done:** DB-B. Probe: `GET /investigations/{id}/outputs`.

**Risks**
- Missing the c2-export merge window forces a separate schema bump (see LB-1(c)).
- A synthesis cleared on the export branch may still withhold on main until wave 5 lands.

### LB-20 · Branch from output, with purpose and lanes (R18, R19)

**Scope**
- `POST /investigations` gains:
  - `origin: {kind: selection, output_anchor}`;
  - `purpose?: harden | chase | ask`, where `ask` makes a dialogue child (tier 0);
  - `target?: {insight_id} | {question_id}`;
  - `kind?: research | dialogue`;
  - `continue_from_parent`;
  - `context_items[]`.
- Validation runs before `record_branch`, in this order:
  1. The parent is owned.
  2. The anchor's thread equals the parent.
  3. The anchor's event is in the parent's trajectory.
  4. The anchor's path is in the closed set.
  5. The recomputed hash matches.
  6. The offsets are in range.
  7. The segment is served.
- The server-side served check replaces the client-only guard.
- Loop One loads the parent's gated pack (LB-24a) and the focus span into `InvestigationContext`.
- `chase_mode` is forced `off` for output branches.
- `?parent_thread_id=` lists children in branch-event order, with `ThreadSummary.origin`.
- Sealed `.parquet` logs are enumerated.
- **The four verbs** (ruling 2; lane A's A14): Ask, Harden and Chase start here, and Flag for diligence is LB-32's `POST /flags`. O-4 is closed.
- **No `hardened` projection in the MVP.** A harden child's outcome is its own thread, and the lane view shows its state and its thesis excerpt as GatedText. A per-claim verdict would be a model judgement with no typed home, so it waits for a later revision that adds a typed verdict to the child's outcome. Lane A agrees (Part 2 draft §A3).
- **Owner-model parents** wait on O-3. Until it is ruled, an owner-model launch keeps refusing a parent (`app.py:2754`), and output branches run on the platform lineup with an estimate.

**Acceptance (red-first)**
- The parent's log holds `investigation.branched` with `output_anchor`.
- The child's `context_pack.assembled` lists the served parent items and the focus. This is red at `orchestrator.py:2085-2098`.
- A withheld-segment anchor never puts text into the child's start payload. This is red today: the server copies whatever text arrives.
- Three children with distinct purposes list with their origins.
- A branch whose child has no log reads `no_record`.

**Depends on:** LB-19; LB-24a; the §1.9 estimate (absent on main); O-3 for owner-model parents; LB-1(c).

**Done:** DB-B. Probe: `GET /investigations?parent_thread_id=`.

**Risks**
- Every Harden or Chase is a paid start.
- A parent whose log is written off-host as a remote-exec cascade leaf needs `409 parent_log_remote` until that log is funneled (INFERRED).

### LB-21 · Dialogue scope, agent sessions and Converse turns (R25 one agent, R35, R37)

**Scope**
- **Create.** `POST /investigations {kind: dialogue, scope, participants?[], title?}`. `scope` is the union `{project_id} | {document_id}`, which stays a union because TalkToBook needs a book scope (DECISIONS reconciliation). There is no Speak scope (ruling 16).
- **Sessions** (D-A). A session is the one dialogue per (agent, project), with `participants: [agent_thread_id]` and `scope: {project_id}`.
  - It is created or found idempotently on (owner, agent, project).
  - Turns never go to the agent's own log.
  - A session's `thread.turn` carries `session_of: {agent_thread_id, project_id}`.
- **Ask.** `POST /investigations/{id}/ask {question, input?, at?, context_items[], model_choice?, idempotency_key}` persists `thread.turn {question, input, at?, answer: GatedText, context[], project_id, model}` together with `answer.provenance`.
  - When the session has an agent, the ask also writes LB-26's context receipt, and the ask response returns it (lane A's request C5).
  - `model_choice` is resolved once at admission and bound into the request identity.
  - Owner BYOT (PR #3278's owner model) is usable in any session whose scope the caller owns. A project never holds a key of its own. This is coordinated with #3278, as for O-3.
  - `at` is `{derived_asset_id, revision_id, span_id, offset_seconds}` (lane A's four fields): the turn sees monologue spans only up to `span_id`.
  - `input` is LB-12's. For voice, the server writes `voice.captured` and returns `voice_capture_event_id`.
- **Context resolvers:**

  | Session | Context |
  |---|---|
  | An agent session | LB-26's assembler for the scope's project. The project's other members are not read unless attached. |
  | A project session with no agent (Converse) | Member threads' gated packs, plus chunk search restricted to member documents; member deliverables at their current revision under the owner serve-time gate, plus `derived_asset_block_informs` |
  | A book session (`{document_id}`) | Delegates to `book_qa`; the dialogue branches from `read-<doc>` with `via: api`. When the book's project carries a ruling-11 link, the session may read the linked research project's served material, read-only. |

- **The route** is new. `/thought-partner` is not edited while #3278 and codex-r15 own it.
- **Answer refs.** Answers carry `source_refs {document_id, anchor}`.

**Acceptance (red-first)**
- A turn survives a reload and lists under `?kind=dialogue&project_id=`.
- A second ask to an agent from the same project lands on the same session, and from another project on a different session.
- A book-scoped turn never contains a withheld page.
- `cited_refs ⊆ retrieved_refs`.
- A key replay returns the first turn, and a replay with another `model_choice` answers `409 idempotency_conflict`.
- A concurrent writer is not blocked during the model call.
- A turn with `at` sees monologue spans only up to `at.span_id`.
- A Speak scope answers 422.
- No path from a book session writes to a linked research project (asserted over its log and membership).

**Depends on:** LB-3, LB-24a, LB-17, LB-26 for agent sessions (plain dialogues do not wait), LB-1(c), and coordination with #3278 and codex-r15 on the board. Revision 1's dependency on LB-13 item 6 went with the Speak scope.

**Done:** DB-B. Probe: `GET /investigations?kind=dialogue`.

**Risks**
- Owner-read gating must never leak into shared views.
- Turns are unmetered until LB-23.

### LB-22 · Book ask scope and openable refs (R31)

**Scope**
- `/books/{id}/ask` gains `scope: book | shelf | library`: owned-corpus retrieval under the same gate, with `shelf` requiring `project_id`.
- `read.book_answered` citations carry `source_refs {document_id, anchor}`.
- An agent opens a document only as a proposal and never acquires one.
  - An agent-initiated open of an absent document files a read flag through LB-32's `POST /flags {intent: read}`.
  - `/books/marketplace/purchase-request` (`books.py:1310`) is unreachable from any agent path.
- A ref to a non-book document opens in the reader once LB-35 lands. Until then it comes back with its gate and `document_type`.

**Acceptance (red-first)**
- A reply naming another owned book returns a ref that resolves.
- A document that cannot be served comes back `cite_only`.
- `scope: book` behaves exactly as today (regression).
- An agent-initiated open of an absent document files a `read` flag and calls no acquisition route.

**Depends on:** LB-3; LB-17 for the shelf scope; LB-32; LB-35 for non-book refs; LB-1(c).

**Done:** DB-B. Probe: `GET /openapi.json` listing `scope` on `/books/{id}/ask`.

**Risks:** `read-<doc>` is keyed per document, not per owner, which remains pre-multi-user work.

### LB-23 · Record-only spend for unadmitted dispatches (R25, R34 to R38)

**Scope**
- NEW `BudgetLedger.record_dispatch(run_id, dispatch_id, actual_cents | None, thread_id, project_id, mothership, kind)`, idempotent by `dispatch_id`.
  - An unknown cost is recorded as `cost_unknown`, never as `0`.
  - `mothership` follows D-P tightening 3.
- It is wired into `/voice/transcribe`, `/speech/tts`, ask turns (one settlement per group turn), book ask and Speak follow-ups.
- `spend_today` includes these settlements.
- The Speak token-door intake budget refuses with 429.

**Acceptance (red-first)**
- A transcription carrying a thread and project writes one settlement with both, plus its `mothership`.
- A replayed `dispatch_id` writes nothing.
- `spend_today` rises by the recorded amount. It reads `null` with a reason when any settlement that day is `cost_unknown`.
- A record-only dispatch is never refused by the cap, and a later diligence admission sees the reduced `remaining_cents`.

**Depends on:** the §1.13 ledger extension (W3's `reserve_dispatch` and `settle_dispatch`). O-16 is still open, and record-only is its fallback (§6).

**Done:** DB-B. Probe: `GET /projects` showing `spend_today`.

**Risks:** conversational spend can starve diligence admissions. That is truthful, and O-16 decides whether it is wanted.

### LB-24 · Merge targets and retirements (R20, R21), per D-M

**Scope**
- **The target** on the commit is `target: "new_thread"` (the default) or `{into_thread_id}`.
  - `{into_thread_id}` answers `422 target_unavailable` until LB-26 lands. That answer is distinct from 403 (lane A's request C4).
  - After LB-26, a merge into an agent writes exactly one event on the target: `thread.merged_in {merge_id, merged_from[], accepted_draft {draft_id, draft_digest}, preview_digest}`.
    - No thread is minted, and the target's state is unchanged.
    - Members record `investigation.merged_into {thread_id: target}` under the pending pattern.
    - An owner mismatch answers 403.
    - The assembler reads the event as an attachment (D-M's naming choice).
  - O-2's auto-fold is struck. The server never picks a target. Lane A only preselects the common parent when every member descends from it.
- `merged_from` members count as export dependencies, and summaries expose `merge_ids[]`.
- Retire `/research/artifacts/compose*` once lane A's MergeFlow preview is on main. The compose draft GET writes files today (`artifact_routes.py:341-355`).
- The restated rule: members are never rewritten, and a target receives one append.

**Acceptance (red-first)**
- `into_thread_id` answers `422 target_unavailable` before LB-26, never 403 for that reason.
- A merge into a target leaves the target's state unchanged and writes exactly one `thread.merged_in`.
- A partial merge never reports success, and a replay resumes from `merge_started`.
- An unresolved member withholds the merged excerpt.
- GET routes write nothing. This is red today: the compose draft GET renders files.
- No request makes the server fold into a thread it was not given.

**Depends on:** LB-24a, LB-25, LB-26 for `into_thread_id`, and LB-1(c). O-1 and O-2 are answered by D-M.

**Done:** DB-B. Probes: `GET /investigations/{id}` showing `merge_ids[]`, and `GET /openapi.json`.

**Risks:** a merge spans several logs, so the pending pattern is mandatory.

### LB-25 · Merge drafts (R20), per D-M

**Scope**
- **What a draft is.** One model-written, answer-shaped synthesis over the free §1.10 preview, generated under an estimate and the daily cap.
  - It passes the Synthesis gate (`build_body._excerpt_cleared`) and carries T7's `answer.provenance {retrieved_refs[], cited_refs[], presentation_mode}`.
  - It has `claims[{claim_id, text, item_ids[], source_refs[]}]`. A claim whose `item_ids` do not all resolve to served or `cite_only` pack items refuses the draft with `422 unresolved_claim_ref`.
  - It is **not** a §1.11a reformat thread. LB-25 therefore drops its LB-4b and LB-5 dependency, and §1.11a's limit of five investigations, THREAD-CONTRACT.md §1.11a ("`research_context` (rev 8.7)"), does not bound merge members.
- **Routes** (the path is singular, per D-M):
  - `POST /threads/merge/draft/estimate {thread_ids[], preview_digest, question, model_choice?}` returns `{estimate_cents | null, max_cents, assumptions {input_tokens, max_tokens, model}}`. An unpriced estimate needs explicit confirmation.
  - `POST /threads/merge/draft {thread_ids[], preview_digest, question, model_choice?, idempotency_key}` returns `{draft_id, draft_digest, synthesis: GatedText, claims[], answer_provenance, grouping[{origin_thread_id, item_ids[]}], conflicts[], not_shown[{item_id, gate, reason}], cost_cents, model {provider, model, dispatch_event_id}}`.
    - The request identity is sha256(owner, sorted member ids, `preview_digest`, question, resolved model).
    - `draft_digest` is sha256(`preview_digest`, question, model, synthesis text hash, canonical claims, `parent_draft_id?`).
  - `POST /threads/merge/draft/{draft_id}/revise {synthesis_text, idempotency_key}` returns a child draft.
    - Edited sentences carry `origin: operator`.
    - Claims are recomputed from the ref markers that survive the edit.
    - No model is called.
- **Spend.** A draft is cap-admitted: admission against `remaining_cents`, then `reserve_dispatch(dispatch_id=<draft_id>:0)` and `settle_dispatch`. A spent cap answers `402 refused_capped` before any dispatch.
- **What the model sees.** Only served text reaches the model. `cite_only` items are cited by pointer, never quoted.
- **The commit**, on LB-24a's skeleton: `POST /threads/merge {thread_ids[], preview_digest, draft: {draft_id, draft_digest}, question, target, idempotency_key}`.
  - A commit without a draft answers `422 draft_required`.
  - A draft generated against another preview, or one whose members, sources or rights changed since, answers `409 draft_stale {reason}`. The server never regenerates it silently.
  - A `preview_digest` mismatch answers `409 preview_stale`.
  - The commit adopts the draft byte-for-byte as the merged thread's first outcome and makes zero dispatches.
  - The merged thread's start event carries `merged_from[]` and `accepted_draft {draft_id, draft_digest}`.
  - Signed §1.10's `request_identity` gains `draft_digest` and `target`.
- **Counts.** For a merged thread with no retrieval of its own, `claim_count` is the length of the accepted draft's `claims[]`, and `source_count` is the number of distinct documents its `cited_refs` resolve to. Neither is null for a committed merge.
- **Where drafts persist.** `thread.merge_drafted {draft_id, draft_digest, preview_digest, cost_cents, model}` and `thread.merge_draft_revised` are written to a merge-session log, never to a member's log (D-M). **The log is a merge-session log keyed by `merge_id`** (agreed with lane A 2026-09-27; it replaces lane B's earlier reserved-thread-id candidate).
  - **Why not a reserved thread id.** An into-agent merge never mints a thread, so its drafts would sit on an id that never becomes one. A discarded draft would also leave a reservation that listings must learn to hide.
  - **The id.** `merge_id` (`merge-<uuid4 hex>`, validated like other log ids) is minted at the first draft. Its request identity is bound to (owner, sorted member ids, `preview_digest`), so a repeat replays and a mismatch is `409 idempotency_conflict`.
  - **What it holds.** `thread.merge_drafted` and `thread.merge_draft_revised` go there. At commit, `thread.merge_started` goes there first, then:
    - for a new thread, the merged thread's start event carries `{merge_id, accepted_draft}`;
    - into an agent, the agent's single `thread.merged_in` carries the same.
  - **Never a thread.** The log has no `investigation.started`, so the §1.2 listings (which list only started threads) never show it. `GET /investigations/{merge_id}` answers `404 not_found`. It is read only through an owner-scoped `GET /threads/merge/{merge_id}/draft`.
  - **Kept.** A discard leaves the session log as an append-only audit, with no ghost thread. It is the existing log mechanism, not a new store.
- **T7 and G4.** T7's `answer.provenance` covers merge drafts. `page.attribution.computed {subject: "merge-draft:<draft_id>"}` is telemetry only.

**Acceptance (red-first)**
- A commit without a draft answers `422 draft_required`.
- The dispatch count at commit is 0 (asserted by counting).
- A withheld item's text never appears in the dispatch request body (asserted at the dispatch seam with the withheld-chunk fixture).
- A claim with an unresolved item id answers `422 unresolved_claim_ref`.
- A revised draft is the one accepted, byte-for-byte, and the original stays in lineage.
- A member event after the draft makes the commit answer `409 draft_stale` with its reason, and nothing regenerates.
- An exhausted cap answers `402 refused_capped` before any dispatch.
- A draft over six members is admitted, since the §1.11a limit does not apply.
- The merged thread's counts equal the accepted draft's.
- The draft writes nothing to member logs.

**Depends on:** LB-24a, the §1.13 cap ledger, and LB-1(c). It no longer depends on LB-4b or LB-5.

**Done:** DB-B. Probe: `GET /openapi.json` listing the three draft routes.

**If D-M is overturned** (its reconsider-if list): if the operator says the grouping alone is the draft, the commit accepts `draft: null` and the merged thread runs per signed §1.10. That is a one-line change, with no migration.

**Risks**
- The model is paid per draft, so the estimate comes first.
- Drafts may arrive mostly unreferenced (D-M's trigger is under 50% of sentences carrying refs).

### LB-26 · Agents across projects (R21, R29), per D-A

**Scope**

*Identity*
- An agent is a promoted thread, and its id is its `thread_id`. There is no agents table and no `agent_id`.
- `POST /investigations/{id}/agent {charter, model_choice?, idempotency_key}` writes `agent.promoted {charter_asset_id, model_choice?}` on the thread's own log. It creates the charter as the derived asset `agent:<thread_id>` (`asset_kind: analysis`, owner from the request).
- `PATCH /investigations/{id}/agent {charter, expected_revision_id}` is a compare-and-set `revise` of that asset (§1.11), writing `agent.charter_revised {revision_id}`. A moved revision answers `409 revision_moved`.
- `ThreadSummary.agent {charter_asset_id, charter_revision_id, home_project_id, project_ids[], managed, envelope?} | null` is all derived; `project_ids[]` comes from membership.
- `GET /investigations?agent=true&project_id=` lists agents.

*Membership*
- `POST /projects/{id}/members {member_kind: investigation, member_role: agent | managed}` writes a row with `reach: attached_only` (LB-17's CHECK).
- Owner equality is required, and a mismatch answers 403. Any membership or attach write answers `422 project_shared` when any member project has more than one owner, so O-6's "no once shared" holds at write time.
- T8 holds as membership: the agent tab in project P holds P's session (LB-21).

*Attach*
- `POST /investigations/{id}/attach {project_id, items[{kind: thread | doc | note | insight, id}], idempotency_key}` writes `thread.context_attached {items[], via: manual, attached_by, project_id}` on the agent's log.
  - A withheld item is refused with its reason.
  - A `cite_only` item attaches refs-only.
- A merge into the agent is not an attach. It is LB-24's single `thread.merged_in`, which `thread.context_attached` never duplicates.

*Context*
- `GET /investigations/{id}/context?project_id=` is the one assembler, shared by §1.8 asks, tier-1 continuations, agent calls and LB-27 groups. It assembles, in this order:
  1. the charter;
  2. the agent's own gated pack (LB-24a);
  3. its accepted drafts;
  4. its `merged_from` members, recursively to depth 8;
  5. its own B0 children that are members of the calling project;
  6. the session's turns, for the (agent, calling project) session only;
  7. the items explicitly attached in the calling project.
- There is no ambient step. Revision 1's fifth step, "the calling project's context", is removed, and the calling project's other members are never read unless attached.
- It is budgeted by `reuse_token_budget`. Every item carries `included` and `reason: budget | withheld | refs_only`.
- `personal_reading` and Speak-derived items are refs-only outside their home project (O-6).
- **Receipts.** Every turn that uses the assembler writes `thread.context_receipt {turn_event_id, items[{id, included, reason}]}` beside the turn, and the ask response returns it.

*Calls and memory*
- Agent-call research is a B0 branch with `via: agent_call`. Its `thread_id` is the child, and its `project_id` is the calling project.
- `note_retrieval` is restricted through `restrict_node_ids`, built from owned membership.
- **The `evidence_index` re-key** (R29-d, D-A) is in this package's scope.
  - The primary key becomes `(owner_user_id, evidence_id)`, and it lands before any cross-project read.
  - Scopes gain `thread`, and an agent's evidence base is scope `thread` with its thread id as `scope_id`.
  - LB-29's node-keyed id material rides on the same key.
- No agent path writes account memory until R15's proposal-and-confirmation contract lands. O-6 is amended by D-A to "never *implicitly* from turns", and lane-A default 6 applies.

**Acceptance (red-first)**
- An agent in two projects returns the same items 1–4 in both, and each project sees only its own session turns and attachments.
- A document member of the calling project that was never attached is absent from the context. This is the no-ambient test.
- Budget truncation is reported per item with its reason, and each turn's receipt lists every assembled item.
- A cross-owner membership answers 403, and a membership into a project with two owners answers `422 project_shared`.
- A `reach` value other than `attached_only` is refused by the table.
- A stale `expected_revision_id` answers `409 revision_moved`.
- No path writes to the memory store (asserted over the store).
- Agent-call spend attributes to the calling project.
- A `personal_reading` item appears refs-only in another project.
- Attaching a withheld item is refused with its reason, and a `cite_only` item attaches refs-only.
- **Cross-owner collision.** Two owners writing the same `evidence_id` get two rows, and neither overwrites or reads the other's. This is red against a key of `evidence_id` alone.

**Depends on:** LB-17 (members and `reach`), LB-21 (sessions), LB-24a, LB-24 and LB-25 (merges into an agent), LB-9 (the `evidence_index` store that the re-key changes), and LB-1(c).

**Done:** DB-B. Probes: `GET /investigations?agent=true` and `GET /investigations/{id}/context`.

**If D-A is overturned.** Ambient reach is a `reach` value change under a ruling, not a new model. A first-class agent entity would be a new store against rule 1, recorded as an override.

**Risks**
- Paraphrase can leak across projects even when quotes are gated.
- Per-project sessions may read as amnesia (a D-A reconsider-if).
- `/thought-partner` ownership, as in LB-21.

### LB-27 · Group dialogue in one voice (R25), per ruling 20 and D-A

**Scope**
- A group is a session dialogue with 2 to 4 `participants[]` (agent thread ids) and `scope: {project_id}`. It is the same object as a solo session, found or created on (owner, sorted participants, project).
- **One ask is one dispatch.** The server assembles each participant's context through LB-26's assembler for the group's project, fits them within one budget, and writes one `thread.turn` on the group's own log.
- **One voice.** The answer is one synthesising voice (ruling 20).
  - Its spans carry `origin_thread_id`, derived by the server from each span's cited refs, never from the model's own claim.
  - A span whose refs come from more than one participant, or from none, carries `null` with `reason: mixed | unsupported`.
- A participant that contributed nothing is named on the turn with its reason: `withheld`, `budget` or `empty`.
- The context receipt tags every item with its participant.
- A per-turn bound (the `max_tokens` bound, priced where a price is known) is shown before sending. An unpriced turn needs explicit confirmation.
- **Removed from revision 1:**
  - per-participant turns;
  - `dialogue.round`, `round_id` and `speaker_thread_id`;
  - `addressees`;
  - sequential answers.

**Acceptance (red-first)**
- A group turn makes exactly one dispatch (asserted by counting).
- A span citing only participant A's refs is attributed to A. Every span's `origin_thread_id` is a participant, or null with a reason.
- A withheld participant is named, never dropped silently.
- A fifth participant answers 422.
- No participant's own log is written.
- A key replay returns the first turn.

**Depends on:** LB-21, LB-26, LB-23 and LB-1(c). Ruling 20 answers O-5.

**Done:** DB-B. Probe: `GET /investigations?kind=dialogue`.

**Risks:** input grows with the number of participants. `reuse_token_budget` caps it, and output stays one bounded answer.

### LB-28 · Autonomy and Research → Autonomous (R28)

**Scope**
- **Research → Autonomous** promotes selected threads in place as agents (LB-26), with `member_role: managed` and `reach: attached_only`, inside their existing project. Each thread keeps its research membership. Autonomous is not a product value and has no create seed (D-P tightening 1).
- **Consent is per flag under D4 by default.** Until the operator rules on O-11:
  - each continuation of a managed thread is a flag through LB-32, with its own consent and launch (§1.13's lifecycle), held and settled through the ledger;
  - nothing standing is written.
- **The envelope, only if O-11 is granted:**
  - `POST /investigations/{id}/autonomy {max_cents, expires_at, model_choice}` writes `agent.autonomy_consented {max_cents, expires_at, model_choice, consent_id}`, validated through the Midnight Oil preflight (`substrate/midnight_oil/contracts.py:93-130`);
  - `max_cents` is at most today's cap, and `expires_at` is at most 24 h away;
  - `DELETE` writes `agent.autonomy_revoked {consent_id}`;
  - the route ships behind the ruling and is absent until then.
- **The roster read** (lane A's request C2): `GET /autonomy/roster` returns `{spawning_enabled: bool, spawning_reason: consent_route_absent | env_refused | cap_exhausted | enabled, agents[{thread_id, title, home_project_id, project_ids[], state, consent_mode: per_flag | envelope, envelope: {max_cents, expires_at, spent_cents | null, state: live | expired | revoked} | null, spend_cents | null}]}` through `connect_read`.
  - `spawning_reason` is the first failing condition, in this order:
    1. LB-10's consent and claim-then-spawn route is absent from the build: `consent_route_absent`.
    2. `ANTIEK_DAEMON_SPAWN_ENABLED` is off: `env_refused`.
    3. No cap remains today: `cap_exhausted`.
    4. Otherwise: `enabled`.
  - The API reads the flag from the environment file both units load. That the two systemd units share one file is INFERRED, and the package pins it with a template test.
  - The edge line gains `/autonomy*`.
- **The daemon** reads `member_role: managed` rows through `connect_read`, then only those threads' consent events.
  - Continuations are tier-1 `continue_from_parent` runs with `chase_mode`.
  - They are held through `reserve_dispatch` and branched with `via: chase`.
- **Operator enable** (ruling 10). Spawning stays off until LB-10 lands and the operator enables it.

**Acceptance (red-first)**
- Nothing spawns without a consumed per-flag consent, or, if O-11 is granted, a live envelope.
- The daemon refuses to spawn while `ANTIEK_DAEMON_SPAWN_ENABLED` is off, even after LB-10.
- `spawning_enabled` is false with `consent_route_absent` before LB-10, and with `env_refused` when the flag is off.
- An unknown spend reads `null`.
- The roster GET writes nothing.
- An unmanaged thread is never chased.
- If O-11 is granted:
  - the envelope ceiling and the daily cap are both enforced;
  - a revocation stops the next admission;
  - an expired envelope refuses.

**Depends on:** LB-10, LB-26, LB-32, the §1.13 ledger and LB-1(c). The envelope half depends on O-11.

**Done:** DB-B. Probe: `GET /autonomy/roster`.

**Risks**
- The envelope is an exception to D4, which only the operator can grant.
- The daemon's gap scan reads every investigation today (`orchestration/continuous/daemon.py:1-30`).

### LB-29 · Books notebook lens (R32, R33) and the LB-9 amendment

**Scope**

*Amend LB-9*
- The entry id is the sha of `(owner_user_id, scope, scope_id, node_id)`, never of the claim text.
- The table's primary key, `(owner_user_id, evidence_id)`, is LB-26's re-key (D-A).

*New fields and parameters*
- `anchors[]` and `chapter?`, with the chapter taken from `book_assets.toc_json`.
- `GET /projects/{id}/companion-document?lens=reading&document_id=&group=chapter`. The lens value is `reading` (lane A's request C7). Under D-P every book is a `kind: reading` project, so the per-project lens reaches every book.

*Thread set* (lane-A default 2; the operator may overturn it)
- Project threads.
- Legacy threads adopted by shelf or context document.
- The owner's `read-<d>` answers.
- A ruling-11 linked research project's threads are not in the set unless they grounded in or opened a shelf document.

*Spend* (ruling 13). A rebuild makes no model call. The prose write-up is opt-in and cap-admitted. It is LB-30's §1.11a derivation from `{companion_document: {project_id, lens: "reading"}}`, and lane A's A20(3) stays disabled until that lands.

*Audiences and rebuilds*
- Two audiences: owner-read and public.
- The rebuild triggers are a terminal event, a `thread.turn`, a `read.book_answered`, a resolved island, a landed diligence run, or a shelf change. A `reading.position` event is **not** a trigger.
- A rebuild writes a typed `companion_document.refreshed`, never the untyped `companion.rebuilt` (`substrate/companions/watcher.py:319@0af7a2b7b`).

**Acceptance (red-first)**
- A living-note refinement keeps the entry id. This is red on the companion stack at `projector.py:210-212`.
- Two owners rebuilding one document get distinct rows.
- A `personal_reading` quote is served to its owner and is `cite_only` on export.
- A `reading.position` event alone never triggers a rebuild.
- The GET and every rebuild make zero dispatches.
- A linked research project's unrelated thread is absent from the notebook.

**Depends on:** LB-9, LB-17, LB-24a, the rights branches (wave 5, `fix/w5-mcp-hardening-20260923`) and LB-1(c).

**Done:** DB-B. Probe: `GET /projects/{id}/companion-document`.

**Risks:** the bounded scan (see LB-18).

### LB-30 · Monologue derivation and the notebook write-up (R32, R36, R37)

**Scope**
- §1.11a gains three things:
  - `source: {scope: {project_id} | {document_id}, query}`, whose core set is the documents behind the retrieved chunks;
  - `params: {mode: explain, listening_minutes: 1..120, delivery: audio | text, voice?}`, where `delivery` defaults to `audio` (ruling 15) and the text always renders alongside;
  - `parent_thread_id`, where the parent is the Converse dialogue.
- **The notebook write-up** (agreed with lane A, 2026-09-27). The §1.11a `source` union also gains `{companion_document: {project_id, lens: "reading"}}`, for the Books notebook's opt-in prose (ruling 13).
  - The input is spend-free: LB-29's structured entries, as served GatedText.
  - The server records the companion document's `content_hash` at admission as part of the request identity, so a rebuilt notebook makes a stale request visible rather than silently different.
  - The core set is the documents the entries' refs resolve to.
  - Generation runs under the cap like any reformat.
  - Lane A's A20(3) stays disabled until this lands.
- Chapters follow the planner's intro/body/recap ratios of 10/82/8 (`substrate/multimedia/planner.py:401-403`), with one `revise` per chapter.
- `listening_estimate {minutes, method, shortfall?}`.
- **Never pad or cut** (ruling 15).
  - A thin scope reports a shortfall.
  - `_bound_to_budget` (`substrate/books/meta_reading.py:128`) is not on the monologue path.
  - A chapter that comes back over its share is re-planned as a `revise`, or delivered whole with its measured length. It is never truncated.
- `/reformats/estimate` gains `assumptions.tts_chars` and `voice`.
- A re-plan is a `revise` with `listening_minutes = requested − elapsed` and the question as a `focus_item`.

**Acceptance (red-first)**
- A 30-minute request on a thin scope reports a shortfall rather than padding.
- A script over its word budget is never truncated. This is red on the meta-reading path, where `_bound_to_budget` truncates.
- Every chapter revision has zero unclassified spans.
- A short cap answers 402 before any spend.
- Chapter 1's spans answer 200 while chapter 2 is still generating.
- A re-plan leaves the earlier revision untouched.
- A `companion_document` source builds its input with zero dispatches. Only its generation is held under the cap, and an exhausted cap answers 402 before that dispatch.
- A withheld notebook entry's text never reaches the write-up's dispatch body.

**Depends on:** LB-4b, LB-5, LB-21, LB-24a, the cap ledger and LB-1(c). The write-up also needs LB-29. Ruling 15 answers O-18, and ruling 13 answers the write-up's opt-in.

**Done:** DB-B. Probe: `GET /openapi.json` listing the monologue and `companion_document` fields.

**Risks:** scope creep into web research. Research is offered only as an explicit branch.

### LB-31 · Monologue audio (R36)

**Scope**
- `POST /derived-assets/{id}/revisions/{rev}/audio {voice}` renders only served spans. A withheld or `cite_only` span becomes a fixed spoken marker and is never narrated.
- **Segments** are built from whole served spans, gated span by span, and never split a span.
  - A segment holds at most 3,500 characters, and a single span above that is its own segment.
  - Each segment is one TTS dispatch, run off the loop and held under `reserve_dispatch` id `<gen>:tts:<n>`.
- A content-addressed cache holds segments per owner. It is keyed by the gate fingerprint and can be rebuilt.
- `GET …/audio/{n}` streams a segment.
- A measured duration replaces the estimate.
- The listening position uses `reading_state` on `drv-<generation_id>`.
- The edge line gains `/derived-assets*`.

**Acceptance (red-first)**
- Withheld text never appears in a TTS request body (asserted at the provider seam).
- No segment boundary falls inside a span.
- A retried segment is held and charged once.
- The measured duration replaces "words@150wpm".
- After a core source is taken down, the next serve answers `withheld`.

**Depends on:** LB-30, LB-12, LB-23 and the ledger, LB-24a and LB-1(c). Ruling 15 answers O-18.

**Done:** DB-B. Probe: `GET /derived-assets/{id}/revisions/{rev}/audio/{n}`.

**Risks**
- The provider's per-request limit is UNVERIFIED; the 3,500-character segment is the hedge.
- A 30-minute script is about 27k characters, or about $0.41 of TTS (INFERRED arithmetic from `config.yaml:175`).

---

## 4. Seams with lane A (to be signed in writing)

S1 to S8 are signed at rev 7 and rev 8. The new seams are S9 to S26. Each row states what lane B serves, what lane A must send or render, and which lane-A sprint waits on it. Lane A's Part 2 draft has already accepted lane B's shapes for S9, S10, S13, S14 and S16, and for the Speak-side Speak → Writing (DECISIONS reconciliation).

| Seam | Lane B serves | Lane A sends or renders | Lane-A sprint |
|---|---|---|---|
| **S9** Output anchors (R18) | `GET /investigations/{id}/outputs` returns `segments[{segment_id: "<event_id>#<path>", event_id, path, role: thesis\|component\|insight\|open_question, node_id?, current, text_sha256, content: GatedText}]`. The roles `answer` and `turn` follow LB-3 (ruling 3). `POST /investigations {origin: {kind: selection, output_anchor}, purpose?, target?, kind?, question}` returns `{thread_id, branch_event_id}`. WS `investigation.branched` is broadcast on the parent. One shared NFC fixture (LB-19). | Renders exactly `content.text` so the offsets hold, and imports the shared fixture. The tab node carries `branch_origin.output_anchor`, and `parent_tab_id` is the parent agent tab. `prefix+u` scrolls to `segment_id` plus the offsets. Drops the `localStorage` lineage (`useInvestigationTree.ts:89-96`). | A14 |
| **S10** Lanes (R19) | `GET /investigations?parent_thread_id=`. `ThreadSummary.origin {kind, purpose?, output_anchor \| anchor \| target, quote_state: served \| withheld}`, in branch order. No `hardened` projection in the MVP. | Lane labels ("hardening: …", "passage withheld"). | A14 |
| **S11** Merge (R20, R21) | `POST /threads/merge/preview` (LB-24a), then `POST /threads/merge/draft/estimate`, then `POST /threads/merge/draft`, then optionally `POST /threads/merge/draft/{draft_id}/revise`, then `POST /threads/merge {…, draft: {draft_id, draft_digest}, target: "new_thread" \| {into_thread_id}}`. Errors: `409 preview_stale`, `409 draft_stale {reason}`, `422 draft_required`, `422 unresolved_claim_ref`, `422 target_unavailable` (distinct from 403), `402 refused_capped`. WS `thread.merge_drafted`, `thread.merge_started`, `investigation.merged_into`, `thread.merged_in`. | Part 2 §2.5 takes D-M's states (Part 2 draft §A5). Accept is enabled only on a served draft. | A15 |
| **S12** Agents (R21, R29) | `POST /investigations/{id}/agent`; `PATCH …/agent {charter, expected_revision_id}` (`409 revision_moved`); `POST /investigations/{id}/attach`; `GET /investigations?agent=true&project_id=`. `ThreadSummary.agent {charter_asset_id, charter_revision_id, home_project_id, project_ids[], managed, envelope?}`. `GET /investigations/{id}/context?project_id=` returns items `{content: GatedText, included, reason: budget\|withheld\|refs_only}`. `POST /projects/{id}/members {member_kind: investigation, member_role: agent}`, with `reach: attached_only`, 403, and `422 project_shared`. | The Agents group, header chips ("Attached only", "Knows: …"), attach, and the charter CAS form. An agent tab holds only a `thread_id`. | A23 |
| **S13** Dialogue (R25, R35, R37) | `POST /investigations {kind: dialogue, scope: {project_id} \| {document_id}, participants?[], title?}`, with sessions idempotent on (owner, agent, project). `POST /investigations/{id}/ask {question, input?, at?, context_items[], model_choice?, idempotency_key}` returns the turn and its context receipt. WS `thread.turn`. `ThreadSummary.scope` and `participants[]`. Answers carry `source_refs {document_id, anchor}`, and group answers carry span-level `origin_thread_id`. `at` is `{derived_asset_id, revision_id, span_id, offset_seconds}`. | A scope picker over `GET /projects` only (ruling 16). Opens left tabs through S1. Attribution chips for a group. | A16, A22, A23 |
| **S14** Projects (R22, R24, R26, R27, R30) | `POST /projects {home_product, kind, title?, seed, idempotency_key}` returns `{project, next: {kind: open_mode \| launch_first_question \| import_book, ref?}}`; errors are `409 idempotency_conflict`, `422 seed_invalid {reason}`, `404 source_not_found` and `403 not_owner`. `GET /projects?product=&archived=` returns `thread_counts \| null`, `spend_today \| null`, `last_mode`, `shelf_count \| null` and `linked_project_ids[]`. `DELETE /projects/{id}/products/{product}` writes `project.product_left` (`409 last_product`). WS `project.created`, `project.product_left`. | A create page at `/new?product=research\|writing\|reading`. Homes by presence. Lane A's landing rule uses `last_mode` (ruling 8, DECISIONS reconciliation). | A11, A12, A13 |
| **S15** Shelf (R30, R31, R33) | `GET /projects/{id}/shelf` returns items `{document_id, title, author, document_type, gate, progress \| null, adopted_version?}`, books first and non-books marked (ruling 12). `PUT …/shelf {document_ids[], expected_version}` (`ordinal`). "Keep" is `POST /projects/{id}/members {member_role: context}`. The ruling-11 link is `POST /projects/{id}/members {member_kind: project, member_role: context, ref, link_back: true}`. WS `project.shelf_changed`. | Tab node `transient: true` for agent-opened left tabs, a Keep action, and a "Which book(s)?" step. | A18 |
| **S16** Transfers (R28, R33) | `GET /projects/{id}/transfer-candidates?to_product=`. `POST` and `GET /projects/{id}/transfers`. Speak → Writing on `POST /speak/projects/{id}/draft`. WS `project.transferred`, with typed `seam.speak_to_write` and `seam.research_to_read` in the same transaction. Errors: `422 transfer_not_supported`, `422 speak_publish_required`. | The transfer dialog with partial selection, and the lineage chip from `derived_from_project_id`. | A19, A21 |
| **S17** Notebook (R32) | `GET /projects/{id}/companion-document?lens=reading&document_id=&group=chapter`. Entries gain `anchors[]` and `chapter?`. The opt-in prose write-up is `POST /reformats` with `source: {companion_document: {project_id, lens: "reading"}}` (LB-30), estimated first and run under the cap. | The Findings tab titled "Notebook" in Books, with the existing §2.7 states. "Write it up as prose" (A20(3)) stays disabled until LB-30 lands. | A20 |
| **S18** Book ask (R31) | `/books/{id}/ask {scope: book \| shelf \| library}`. Answers carry `source_refs {document_id, anchor}`. | `openDocumentInLeftPane` from answer refs. | A18 |
| **S19** Continue (R22, R31) | `GET /reading/continue` (LB-14). | The Books home. | A12, A18 |
| **S20** Voice (R34, R37) | `POST /voice/transcribe?thread_id=&project_id=&language=` returns `{transcript, language, duration_seconds, asr, cost_cents \| null}` and persists nothing. Errors: `400 empty_audio`, `413 too_large`, `429 rate_limited`, `503 transcription_unavailable`. Launch, ask and reformat take `input {modality, asr_model?, language?, duration_s?, edited}`, and for voice return `voice_capture_event_id` (the server writes `voice.captured` with the submitted text and `audio_ref: null`). `/speech/tts` gains `source?`. | One `useVoiceInput()` hook: record, transcribe, show an editable field, submit with `input`. It stops posting `voice.captured` through `/events/typed`. Rights-bearing read-aloud uses `source`. | A17 |
| **S21** Monologue (R36, R37) | `POST /reformats/estimate`, then `POST /reformats {source: {scope, query}, params: {mode: explain, listening_minutes, delivery, voice?}, parent_thread_id}`, where `delivery` defaults to audio. WS `reformat.generated` per chapter. `POST …/audio`, then `GET …/audio/{n}` with a segment list `{segments[{n, span_ids, duration_ms \| null, url}]}` built from whole served spans. The position is a `reading_state` PUT on `drv-<gen>`. | The player supplies `at` to ask. Shortfall copy. No client trim. | A22 |
| **S22** Speak (R38, R39, R40) | `GET /speak/sections`, `GET /speak/projects/{id}/detail` (with `topic_description` and `interview_guide`), `GET /speak/public/{project_id}` (open, takedown-filtered). List rows carry `topic_description`, `contributed_voice_count`, `invited_count` and `pending_reping_count`. `/speak/opportunities` and `/speak/pushes` honour takedowns (LB-34). Inbox kinds `speak_answer_received` and `speak_claims_proposed`, with `POST /inbox/{id}/seen` and a WS nudge. | Three left sections and a right detail layer. | A19 |
| **S23** Autonomy (R28) | `GET /autonomy/roster` with `spawning_enabled` and `spawning_reason`. Per-flag consent through S24 by default. `POST` and `DELETE /investigations/{id}/autonomy` only if O-11 is granted. `ThreadSummary.agent.envelope {max_cents, expires_at, spent_cents \| null, state}`. | Banner reasons, and the envelope consent copy, which must say "starts if free; pauses at the cap". | A24 |
| **S24** Flags (R19, R28, R31) | `POST /flags {intent, target, reason, project_id?, idempotency_key}` and `GET /flags?intent=read\|diligence&project_id=&cursor=` (LB-32). | The Flag verb, To read, and per-flag consent for Autonomous. | A14, A18, A24 |
| **S25** Reader (R30, R31) | `GET /books/{id}` serves non-book long-form documents (LB-35). | Non-book shelf items open in the reader. | A18 |
| **S26** Source-merge retirement (R20) | Preview, apply and commit answer `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}` (LB-33). `restore` follows Q-B1: it retires with the same 410, or it stays live and LB-33b serves `GET /research/artifacts/source-merge/receipts?document_id=`. | Every caller, restore included, is removed on `design/retire-source-merge-ui-20260927` before LB-33 lands (A10(4)). "Restore the original" returns only if LB-33b is built, and only where a receipt exists. | A10 |

**Lane-A inputs lane B needs signed with these seams:**
- Part 2 §2.1 accepts `home_product`, `products[]`, `kind: project | reading | interest` and `derived_from_project_id`. Part 2 draft §A1 already does.
- §2.2 accepts `output_anchor` and `transient`, and the mode key stays `reading` (Part 2 draft §A2). Lane A's sprint plan still says `books` in A18(1) and in its §5 line for §2.2, and needs the same edit.
- §2.3 accepts `output_anchor` wherever `anchor` is required (Part 2 draft §A3).
- §2.5 takes D-M's states (Part 2 draft §A5).
- The client renders exactly `content.text` and imports the shared fixture (S9).
- `useVoiceInput` reads `voice_capture_event_id` from the launch, ask or reformat response, and stops posting `voice.captured`. Part 2 draft §B9 still expects the id on the transcribe response and in the client-sent `input` (§7).
- The Speak door shows the inbox kinds (Part 2 draft §B4).
- The source-merge client callers, restore included, are removed on `design/retire-source-merge-ui-20260927` before LB-33 lands (A10(4)).

---

## 5. THREAD-CONTRACT rev 9 items (Part 1)

Rev 9 is layered after rev 8.x is signed (LB-1(c)). Every item below is "(rev 9)". Each citation in the signed text will be `path@<commit>` plus a quoted anchor.

1. **§1.0 vocabulary.**
   - **Books** is the user-facing label only (ruling 1). Code ids, routes, `⌘E`, the mode key, `home_product`, `products[]` and the book-shaped `kind` all stay `reading`. `/books` is only a brand-alias SPA route.
   - The cockpit row's citation "(T11)" becomes "(rulings 4, 10)". T11 was a recommendation; DECISIONS records only T6, T7 and T9.
   - **New words:**

     | Word | Means | Never used for |
     |---|---|---|
     | shelf | a Books project's ordered document members | |
     | context member | a document kept from a rabbit hole, or a project linked by ruling 11 | |
     | transient tab | an agent-opened left tab | |
     | Notebook | the Books view of the companion document | |
     | agent | a promoted thread, identified by its `thread_id`; its charter is the derived asset `agent:<thread_id>` | a store of its own, or an `agent_id` distinct from a thread id |
     | session | the one dialogue thread per (agent, project) that holds that project's turns with the agent | the agent itself |
     | lane | a branch subtree | an entity |
     | merge draft | a model-written, answer-shaped synthesis over a preview (D-M) | a §1.11a derivation |
     | transfer | a presence append or member references, plus a lineage event | a copy |
     | Converse | a door whose data is a dialogue scoped to a registry project | a Speak surface (ruling 16) |
     | monologue | a §1.11a derivation with a listening budget | |
     | voice input | `input.modality`, with the confirmed transcript kept | raw audio |
     | speak project | `interview_projects` under `/speak`, joined to the registry only by `member_kind: speak_project` (ruling 4) | a §1.5 registry project |
     | autonomous | `member_role: managed` on threads | a product value or a create seed |

   - **Persisted names that are never renamed:**
     - `/read/:documentId`
     - `read.*` events
     - `read-<doc>` ids
     - `personal_reading`
     - `reading_state`
     - `book_assets`
     - `anchored_highlights`
     - `reading_research_spun`
   - **Citation fix:** `interview_projects` is at `substrate/graph/schema.py:330-338`.
2. **§1.2 threads.**
   - `ThreadSummary` gains:
     - `origin`;
     - `project_ids[]`, derived from membership;
     - `scope`;
     - `participants[]`;
     - `agent {charter_asset_id, charter_revision_id, home_project_id, project_ids[], managed, envelope?} | null`;
     - `merge_ids[]`.
   - Filters gain `document_ids[]`, `participant`, `agent`, and `project_id`. Membership is the authority for "threads of project X" (D-P), and the start payload's `project_id` is the home project only.
   - A promoted thread reads `idle` when nothing runs.
   - **Counts.** THREAD-CONTRACT.md §1.2 ("Counts (answers the audit's claim-count gap)") gains one clause: for a merged thread with no retrieval of its own, the counts come from the accepted draft (LB-25).
   - Legacy threads with no `project_id` are adopted by document for `reading` and `interest` projects only.
   - NEW routes: `GET /investigations/{id}/outputs` (§1.4b) and `GET /investigations/{id}/context?project_id=` (§1.12a).
3. **§1.3 branch.**
   - `BranchOrigin` gains:
     - `output_anchor?`. For `kind: selection`, exactly one of `anchor` and `output_anchor` is set.
     - `purpose?: harden | chase | ask`
     - `target?: {insight_id} | {question_id}`
   - `via` gains `agent_call`.
   - The errors are:
     - `422 output_not_servable`
     - `409 output_anchor_stale`
     - `409 parent_log_remote` (INFERRED need)
   - These change the B0 payload (`events.py:2561-2587@2be3e0d1b`), so they land before c2-export merges. The same change aligns the payload's docstring, which says a branch means "the child ran", with the contract's rule that a branch is a dependency, not proof.
4. **§1.4b `OutputAnchor` (NEW).**
   ```
   OutputAnchor {
     thread_id, event_id,
     path,              // closed set, phase 1: /thesis_summary, /thesis_components/<i>/<field>,
                        // /canonical_label, /new_text; after LB-3: /answer, /answer/text
     segment_sha256,    // NFC segment text at pin
     start, end,        // Unicode scalar offsets, unicode-nfc-v1 (validate_node_text_anchor's rules)
     selection_sha256,
     quote?, prefix?, suffix?,   // only when the segment was served at pin (32-scalar context)
     node_id?
   }
   ```
   Events are append-only, so the anchor never drifts and needs no remap. "Refined since you branched" is derived from a newer `note.refined` for the same `node_id`. One shared fixture proves both lanes' offsets.
5. **§1.5 registry** (D-P).
   - **Folder fields:**
     - `home_product: research | writing | reading`, immutable;
     - `products[]`, a non-empty subset of the same three;
     - `kind: project | reading | interest`;
     - `primary_document_id`, required and reader-servable for `reading`, and null for `interest`;
     - `derived_from_project_id?`.
   - **Member fields:**
     - `member_kind` adds `speak_project` (a link), `derived_asset` and `project` (a context link, with no aggregate recursion);
     - `member_role` is `primary | shelf | context | managed | agent | null`;
     - `reach` is CHECK-constrained to `attached_only` on `agent` and `managed` rows;
     - `ordinal`.
   - `POST /projects` with the seed union, idempotency and atomicity (LB-17). It has no `speak` seed and no `autonomous` seed.
   - The shelf routes; ruling 12's shelf admission; the ruling-11 link; and `DELETE /projects/{id}/products/{product}`.
   - The aggregates `thread_counts` and `spend_today` stay nullable. `last_mode`, `shelf_count` and `linked_project_ids[]` are derived.
   - Legacy `write_folders` rows migrate as `writing` projects.
   - Typed events on the outbox: `project.created`, `project.members_changed`, `project.shelf_changed`, `project.product_left`, `project.transferred`.
   - THREAD-CONTRACT.md §1.5 ("Standalone book (Q-A5)") narrows promote-in-place to "turn this book into a new project" (ruling 11). Part 2's two matching sentences narrow the same way.
6. **§1.5a Transfers (NEW).**
   - The four registry pairs, with whole and partial semantics, the candidates, the lineage event and `422 transfer_not_supported` (LB-18).
   - The Speak-side Speak → Writing on `/speak/projects/{id}/draft` (ruling 4).
   - The two typed seam events.
   - R33 from the Books side is the ruling-11 link, not a transfer.
7. **§1.6 tabs.**
   - `mothership: research | writing | reading` is unchanged, with no alias (ruling 1). It matches LB-2's `MOTHERSHIPS`.
   - Nodes gain `transient` and `branch_origin.output_anchor`.
8. **§1.8 ask and dialogue.**
   - Tier 0 is the NEW route `POST /investigations/{id}/ask`. It reuses the thought-partner dispatch helper, replacing THREAD-CONTRACT.md §1.8 ("EXTEND `POST /thought-partner`"). `/thought-partner` is edited only after #3278 and codex-r15 land.
   - A turn gains `input`, `at {derived_asset_id, revision_id, span_id, offset_seconds}`, `model_choice` and `session_of`.
   - `scope` is `{project_id} | {document_id}`, with no Speak scope (ruling 16).
   - The per-scope context table.
   - The session rule (D-A).
   - A group answers in one voice, with span-level `origin_thread_id` (ruling 20). There is no `dialogue.round`.
   - The `thread.context_receipt` sibling event is returned by the ask response.
   - `read.book_answered` citations carry `source_refs`, and `/books/{id}/ask` gains `scope`.
9. **§1.9.**
   - `ContextItem.kind` adds `project`. It does not add `speak_project` (ruling 16).
   - A group turn's estimate is one dispatch's bound over the combined context.
10. **§1.10 merge** (D-M).
    - LB-24a's pack, preview and commit skeleton.
    - The draft stage: estimate, draft, revise.
    - A commit that requires `{draft_id, draft_digest}` and makes zero dispatches.
    - `target: "new_thread" | {into_thread_id}`, with `422 target_unavailable` until agents exist, and `thread.merged_in`.
    - `merged_from` members are export dependencies.
    - THREAD-CONTRACT.md §1.10 ("Members are never mutated beyond that record") is restated as "members are never rewritten; a target receives one append".
    - `/research/artifacts/compose*` is retired, and O-2's auto-fold is struck.
11. **§1.11.**
    - A serve-time gate for `source_block_kind='speak_claim'` blocks checks takedown plus the `record`, `attribute` and `publish` scopes. Share or export answers `422 speak_publish_required`.
    - From-investigation takes multiple and partial selections, an owner check and an idempotency key.
    - The rev-8.8 correction, THREAD-CONTRACT.md §1.11 ("Source merge (corrected in rev 8.8)"), stands. It gains LB-33's 410 body, the Q-B1 rule for `restore`, and LB-33b's receipt read if that is built.
12. **§1.11a.**
    - `source` gains two forms:
      - `{scope, query}`, the monologue;
      - `{companion_document: {project_id, lens: "reading"}}`, the Books notebook's opt-in prose write-up (LB-30). Its input is spend-free, and its generation is cap-admitted. The server snapshots the document's `content_hash` into the request identity.
    - The merge-draft form that revision 1 proposed, `{threads[], preview_digest}`, is struck (D-M).
    - `params` gains `listening_minutes` (1–120 at 150 wpm), `delivery` (default `audio`) and `voice`.
    - Also added:
      - `listening_estimate`;
      - never pad or cut (ruling 15);
      - one commit per chapter;
      - the audio rendition routes, with segments of whole served spans;
      - the rule that withheld spans are never narrated;
      - positions through §1.14 on `drv-<gen>`.
    - **Talking is built.** THREAD-CONTRACT.md §1.11a ("Future modalities (noted, not built)") is replaced: talking to an asset is built (§1.8, LB-21), and watching stays noted only (ruling 18).
13. **§1.12 companion document.**
    - The entry id is the sha of `(owner_user_id, scope, scope_id, node_id)` (LB-29). `evidence_index`'s primary key is `(owner_user_id, evidence_id)` (D-A; re-keyed in LB-26, with a cross-owner collision test).
    - Entries gain `anchors[]`, `chapter?` and `merge_ids[]`.
    - The `lens` parameter (value `reading`) and the `group` parameter.
    - Owner-read and public audiences.
    - `reading.position` leaves the staleness and trigger list, THREAD-CONTRACT.md §1.12 ("a `reading.position` or `read.book_answered` event landed on the document").
    - Twin notes enter only through promotion.
    - The MCP resources `antiek://threads/{id}` and `antiek://merges/{merge_id}` serve GatedText only, owner-bound, after w5-mcp.
14. **§1.12a Agents (NEW)** (D-A).
    - The promoted-thread identity, and the charter as a derived asset with CAS.
    - Membership with `reach: attached_only`, owner equality and `422 project_shared`.
    - Sessions per (agent, project).
    - Attach.
    - The seven-step assembler with no ambient step.
    - Context receipts.
    - `via: agent_call` research.
    - No memory writes until R15's proposal contract lands (O-6 as amended).
15. **§1.13 money.**
    - The spend-class table (§3 rule 5).
    - `record_dispatch`, and `mothership` on every hold and settlement (D-P).
    - THREAD-CONTRACT.md §1.13 ("Who can hit the cap (rev 6)") adds merge drafts, monologue text and audio, the narrated digest and autonomy continuations.
    - The unified `/flags` routes with `diligence_queue.project_id` (LB-32).
    - The roster read with `spawning_enabled` and `spawning_reason` (LB-28).
    - The autonomy envelope as a D4 exception only if the operator grants O-11, with per-flag consent as the fallback.
    - Inbox kinds: `speak_answer_received`, `speak_claims_proposed`, `monologue_ready`, `merge_draft_ready`.
16. **§1.14.** `GET /reading/continue` is NEW, with progress, correcting THREAD-CONTRACT.md §1.14 ("`GET /reading/continue` reads the table"). The prefs allowlist policy is set per ruling.
17. **§1.15 owner holes.**
    - The owner-scoped-from-day-one list adds `/projects*`, the transfers, `/flags*`, the agent, attach and context routes, and `/autonomy*`.
    - The pre-multi-user holes gain:
      - `/speak/projects`
      - `promote_investigation_to_deliverable`
      - `note_retrieval`
      - `/events/typed`, which takes a client `investigation_id` with no owner check (`app.py:2396-2426`)
      - the bare `{text}` form of `/speech/tts`
      - LB-33b's source-merge receipt read, if it is built
    - `GET /trajectory/{id}` stays listed and is not widened.
18. **§1.16 schema.** The rev-9 events:
    - `thread.merge_drafted`, `thread.merge_draft_revised`, `thread.merged_in`
    - `thread.context_attached`, `thread.context_receipt`
    - `agent.promoted`, `agent.charter_revised`
    - `agent.autonomy_consented` and `agent.autonomy_revoked`, only if O-11 is granted
    - `project.*`, including `project.product_left`
    - the fields on `thread.turn` and `BranchOrigin`
    - the first emitters of `seam.speak_to_write` and `seam.research_to_read`

    `dialogue.round` is withdrawn (ruling 20). Speak strings stay local.
19. **§1.18 delivery order.**
    - LB-1(c) is the gate.
    - The tiers of §3 are appended after W3.
    - LB-24a precedes every pack consumer.
20. **§1.19 Voice input (NEW).**
    - One transcribe route, bounded at 25 MB and run off the loop. The invitee route is bounded the same way.
    - Record-only metering.
    - Retention: no audio, and only the submitted (confirmed) transcript, written by the consuming route (ruling 17).
    - `voice_capture_event_id` is server-minted.
    - The TTS `source` gate, with the bare form recorded as ungated.
    - The provider is chosen through the lineup's `transcription` action.
    - The failure vocabulary of S20.
21. **§1.20 Speak read model (NEW).**
    - S22's routes: GETs that never write, counts that are `null` and never `0`, and invites that report `gated_G7`.
    - Ruling 6's request text and counts.
    - Takedowns honoured on every public listing (LB-34).
22. **Names settled** (DECISIONS reconciliation):

    | Concept | Settled name |
    |---|---|
    | Output anchor | `origin.output_anchor` |
    | Branch purpose | `purpose` |
    | Member order | `ordinal` |
    | Project list filter | `?product=` (presence) |
    | Merge draft route | `POST /threads/merge/draft` |
    | Dialogue scope | `scope: {project_id} \| {document_id}` |
    | Ask payload | `question` |
    | MCP thread resource | `antiek://threads/{id}` |
    | Voice hook | `useVoiceInput` |
    | Transfers | one `POST /projects/{id}/transfers`; Speak → Writing on the Speak side |
    | Interruption point | `at {derived_asset_id, revision_id, span_id, offset_seconds}` |

23. **Citation refresh.**
    - The derived-asset tables are at `schema.py:1267`, `:1326` and `:1348`.
    - `/thought-partner` is at `app.py:6654-6732`.
    - `InvestigationStartRequest` starts at `app.py:438`.
    - `commit_start_acu` sites are `app.py:2892` and `books.py:2241`.
    - The spawn-lineage write is at `app.py:2856-2867`.

**Lane A's requests of Part 1** (Part 2 draft §C), each mapped to the package that answers it:

| # | Lane A asks | Lane B's answer | Package |
|---|---|---|---|
| C1 | Serve `last_mode` and `shelf_count` on `GET /projects?product=`; homes read presence, never `home_product` | Yes, with `linked_project_ids[]` and the nullable aggregates | LB-17 |
| C2 | Carry `spawning_enabled` and `spawning_reason` on the Autonomous roster read | Yes, on `GET /autonomy/roster` | LB-28 |
| C3 | Name the retired-route body's alternatives with the T6 flows | Yes, `["adopt_reading_version", "merge_into_write"]` | LB-33 |
| C4 | Make the D-M routes answer with the Part 2 §A5 shapes, and `422 target_unavailable` distinct from 403 | Yes | LB-25, LB-24 |
| C5 | Put the context receipt on every session turn and group answer, in `thread.turn` or a sibling event the ask response returns | A sibling event, `thread.context_receipt`, returned in the ask response | LB-26, LB-21, LB-27 |
| C6 | Put the shared NFC offset fixture at a path both lanes import | `apps/reading/src/lib/api/__fixtures__/output_anchor_nfc_v1.json` (agreed) | LB-19 |
| C7 | Keep every data name at `reading`, including `lens=reading` | Yes; Part 1 introduces no `books` value | LB-17, LB-29 |
| C8 | Emit `seam.speak_to_write` and `seam.research_to_read` on those transfers | Yes, in the transfer's transaction | LB-18 |

---

## 6. Operator rulings: answered, delegated and open

Revision 1 asked twenty questions. The operator's second set of rulings and the three delegated decisions answer most of them. The cluster ids in brackets trace back to the cluster groundings.

| # | Question | Status | Answer, or the fallback until answered |
|---|---|---|---|
| O-1 [C18-1] | What is the "draft" shown before a merge? | **Answered by D-M** | A model-written, answer-shaped synthesis under an estimate, adopted verbatim at commit. It is not a §1.11a derivation. |
| O-2 [C18-2] | Merge into a new thread or into an existing agent? | **Answered by D-M** | Both, with a new thread as the default. Into an agent is one `thread.merged_in`. The auto-fold into a common parent is struck; the parent is only preselected. |
| O-3 [C18-3] | May owner-model (BYOT) launches have a parent? | **Open** | Fallback: owner-model launches keep refusing a parent (`app.py:2754`), and output branches run on the platform lineup with an estimate. Coordinate with #3278. |
| O-4 [C18-6] | What does a highlight of agent output offer? | **Answered by ruling 2** | Four verbs: Ask, Harden, Chase, and Flag for diligence. Harden is a paid child; Flag is consented and capped. |
| O-5 [C18-4] | How does a group of agents answer? | **Answered by ruling 20** | One synthesising voice with per-sentence attribution (LB-27). |
| O-6 [C18-5, Q-R29a, Q-R29b] | How does an agent grow, and what may cross projects? | **Answered by D-A** | Only through reviewed merges and explicit attaches, "never *implicitly* from turns". Reach is `attached_only`. `personal_reading` and Speak items are refs-only. Writes are refused once a project is shared. No agent writes memory until R15. |
| O-7 [Q-R27b vs Books] | Is the data key for Books `books` or `reading`? | **Answered by ruling 1** | `reading` everywhere, with no alias. D-P's `books`/`book` were withdrawn in DECISIONS' reconciliation. |
| O-8 [Q-R27a] | Is Autonomous Research a fourth tab forest? | **Answered by ruling 10** (with D-P) | No. It is a door over managed threads, and spawning stays off until LB-10 lands and the operator enables it. |
| O-9 | Where does Converse live? | **Answered by rulings 7 and 10** | A door outside the mode cycle, with no ⌘ key, reached through More and the prefix+shift+m picker. There is no fourth tree, so T9 holds. |
| O-10 [Q-R28a, Q-R28b] | Which transfers exist, and what do "whole" and "partial" mean? | **Answered by ruling 11 and D-P** | Five pairs. Whole appends presence; partial makes a linked project with references. R33 from Books is ruling 11's link, and promote-in-place survives only as "turn this book into a new project". |
| O-11 [Q-R28c] | A standing autonomy consent versus D4's per-flag consent? | **Open, and only the operator can grant it** (DECISIONS reconciliation) | Fallback: per-flag consent under D4 for every continuation (LB-28). |
| O-12 [Q-R28d] | Can Speak testimony leave through Write? | **Open** | Fallback: Write shows testimony to the owner and refuses share or export with `422 speak_publish_required` until Speak's publish flow has run. |
| O-13 | What may sit on a Books shelf? | **Answered by ruling 12** | Long-form assets of any type, books first, non-books marked. Agents only propose. |
| O-14 | What does the "autonomous notebook" mean, and what is it called? | **Answered by ruling 13** | A spend-free structured view in v1, with narrative prose opt-in under consent and the cap. The tab is named "Notebook", and the TipTap Notebooks become "My notes". |
| O-15 | What is the book agent's scope, and where is the Books–Research boundary? | **Open** (ruling 11 settles the link's reach) | Fallback: the book first, then the shelf and the owned library, plus read-only reach into a ruling-11 linked project. Open-web research runs only as explicit branches anchored to the book. |
| O-16 (new) | What spend class do conversational turns, ASR and TTS belong to? | **Open** | Fallback: record-only settlements (LB-23), counted in spend and never refused. If the operator rules them cap-admitted, LB-23's call sites switch to `reserve_dispatch` and `settle_dispatch`. |
| O-17 | Voice defaults | **Answered by rulings 14 and 17** | Turn-by-turn, with no raw audio, and only the confirmed transcript kept. Lane B withdraws its "voice asks send automatically". When voice sends is lane A's default 8, which the operator may overturn. |
| O-18 | Monologue scope, bounds and provider | **Answered by ruling 15** | Audio at MVP with the text alongside, the estimate first, and never pad or cut. 1 to 120 minutes, project context only. |
| O-19 | Speak intake | **Converse clause answered by ruling 16**; the intake part is open | Fallback: one step plus an `unconfirmed` flag the operator confirms (lane A's A19(6) builds on it), with contributor authorship after the rights review. |
| O-20 | What are "private inbound invites I got"? | **Answered by ruling 5** | A designed locked state until G7, with an optional bookmark of invite links, labelled as such. |

**Questions revision 1 decided without asking** (the cross-check's §3 #15). Lane A now carries each one as a default the operator may overturn, and lane B builds on those defaults:
- (a) A new Writing project never auto-spawns research (lane-A default 1; LB-17's `blank_deliverable`).
- (b) The context of the book is the book, its shelf and what the agents grounded in or opened (lane-A default 2; LB-29's thread set).
- (d) A Speak redraft is a new revision of the same deliverable (lane-A default 4; LB-15).
- (f) Agents do not propose account-memory facts before R15 (lane-A default 6; D-A).

**New questions for the operator:**
- **Q-B1.** "Does prod hold any `source_merge.committed` without a later `.restored`?" The evidence is `source_merge_body_commits` rows with no matching `source_merge_body_restores` row. Lane A carries the question in its operator summary.
  - **If no:** `restore` retires with the same 410 as the other routes in LB-33, and LB-33b is not built.
  - **If yes:** `restore` stays live, API-only once lane A's client removal lands, and LB-33b adds the receipt read.
  - **Fallback until answered:** `restore` stays live.
- **Q-B2 (mirrors lane A's Q-5 in `forensics/OPERATOR-QUESTIONS-LANE-A.md`; LB-35 spec Q1).** "May house ads and impression accrual run on non-book documents opened in the reader?"
  - For anything not from arXiv the backend sets `ad_eligible == servable` (`substrate/books/serve_guard.py@b41f4ec9b`, "ad_eligible"). Once LB-35 opens non-books, servable web pages and arXiv T1 papers would carry ad rails.
  - Ruling 12 admits non-books to interest shelves but says nothing about ads.
  - **Default until answered: off.** Lane A mounts no ad rail on `is_book: false`. The backend's ad logic is unchanged by LB-35, and a later ruling decides whether the server should refuse ad eligibility for non-books too.
- **Q-B3 (from the LB-35 spec, for the operator).** These carry their own defaults (spec §6):
  - Q2: is an upload of a whole book marked a non-book? The default is yes, by `document_type`.
  - Q3: `/ask` stays 404 on unregistered non-books; the default is that it stays out of scope.
  - Q5: `ip_holder_id` is null in the non-book fallback; the default is conservative null.
  - Q6: the takedown record is deleted on reinstate; the default is yes.
- **Q-B4 (from A06), ANSWERED by an operator ruling** (DECISIONS.md, 2026-09-27, A06 gating). The question was whether the "I wrote this" option (which sends `user_owned`, served publicly on main) should stay live before A06.
  - **The ruling:** a missing, errored or unsupported upload capability disables private-authored submission, with an honest "needs a server update" state. It never falls back to `user_owned`.
  - **Effect:** "I wrote this" goes to its disabled state as soon as the gate ships, which stops new public exposure.
  - **Where the gate lands:** in Undertaker's SPR-02 claim (PR #3539 owns `lib/sourceUploadApi.ts` and `modes/Sources/index.tsx`), or with lane A if those files are released.
- **O-11**, restated above because it is the one open exception to a signed decision.

---

## 7. Conflicts with existing contract text or decisions

| Where | Text today | Conflict | Resolution |
|---|---|---|---|
| B0 payload (`events.py:2546-2587@2be3e0d1b`) and §1.3 | `BranchAnchor.document_id` is required, `BranchOrigin` is document-only, and the `via` literal is closed. The docstring says a reader that finds a branch "knows the child ran". | R18 needs a branch origin in agent output. The docstring contradicts §1.3's rev-2 rule that a branch is a dependency, not proof. | Add `output_anchor`, `purpose`, `target` and `via: agent_call`, and fix the docstring, all before c2-export merges (rev 9 item 3). |
| §1.0, §1.6, Part 2 §2.1 and §2.2 | Research, writing and reading are the modes, with `mothership: research \| writing \| reading`. | R31 renames the product to Books. | **Resolved by ruling 1.** The rename is a label only, and every data name stays `reading`. Lane A's sprint plan still says `books` in A18(1) and §5, and needs the same edit as its Part 2 draft. |
| D-P against ruling 1 | D-P used `books` as a `home_product`/`products[]` value and `book` as a kind, with a `reading` alias for one release. | Ruling 1 keeps code ids. | **Recorded, then resolved by lane A's withdrawal** (DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27"). D-P's substance stands, with `reading` values. |
| §1.5 ("Standalone book (Q-A5)") | `kind: project \| reading`, and a standalone book is promoted in place. | R27 and R30 need per-product meaning and a primaryless interest shelf. D1 says one project appears in every mode. | D-P: `home_product` plus `products[]`, and `kind: project \| reading \| interest`. Promote-in-place narrows to "turn this book into a new project", and R33 is ruling 11's link. |
| §1.8 ("EXTEND `POST /thought-partner`") | The route shape is `/investigations/{id}/ask`. | Editing `/thought-partner` collides with #3278 and codex-r15. Persisted, scoped turns need their own route. | The ask route is new and reuses only the dispatch helper (rev 9 item 8). |
| §1.10 ("Members are never mutated beyond that record") | A commit creates a **new** merged thread, and the preview is the only pre-commit view. | R20 asks for a draft before accept. R21 asks to enrich a growing agent. | D-M: a draft is required and adopted verbatim with zero dispatches. `target` adds `{into_thread_id}`, and a target takes one `thread.merged_in`. |
| §1.11 (rev 8.8 corrected the old line) | "After #3432, its commit and restore are refused through `validate_commit_boundary`." | False: that function has no production caller, and source merge is live against T6. | Corrected in rev 8.8, THREAD-CONTRACT.md §1.11 ("Source merge (corrected in rev 8.8)"). LB-33 retires the routes. `restore` follows Q-B1, with LB-33b's receipt read only if prod holds committed merges. |
| §1.11a ("`research_context` (rev 8.7)") | At most five investigations. | Revision 1 made the merge draft a §1.11a derivation, which would have capped merge members at five. | D-M takes the merge draft out of §1.11a, so the cap does not apply. |
| §1.11a ("Future modalities (noted, not built)") | Talking to or watching an asset is noted, not built. | Ruling 18 confirms talking is built. | Talking is built (§1.8, LB-21), and watching stays noted (rev 9 item 12). |
| §1.12 staleness | A `reading.position` landing on the document makes it stale. | With R32's autonomous rebuilds, every position PUT (about 10 s apart while reading) would force a total rebuild. | Remove `reading.position` from staleness and from the triggers. |
| §1.12 and the companion stack | The owner is in the id material. | `make_evidence_id("claim", text, …)` (`projector.py:210-212@0af7a2b7b`) is text-keyed, and living notes rewrite the text in place. | Key on `(owner, scope, scope_id, node_id)`, with the primary key `(owner_user_id, evidence_id)` (LB-9 amendment, D-A). |
| §1.13 ("Who can hit the cap (rev 6)") | Diligence, daemon and reformat. | Merge drafts, monologues, audio and autonomy continuations are also cap-admitted. Turns, ASR and TTS have no class. | The spend-class table, with O-16 still open and record-only as the fallback. |
| D4 | No launch without per-flag consent. | R28's sub-agent-level management of autonomous research wants standing autonomy. | Open: only the operator can grant O-11. Until then, per-flag consent (LB-28). |
| O-6 (revision 1) | "Grows only from accepted merges, never from turns." | D-A allows explicit attaches too. | Amended by D-A to "never *implicitly* from turns". |
| T8, "agent tabs belong to the project" | An agent tab is a node of one project's tree. | LB-26 makes agents members of several projects. | Settled by D-A: T8 holds as membership. The agent tab in project P holds P's session, which belongs to exactly one project. |
| §1.0 citations of T11 | The cockpit row's doors cite T11. | T11 was a recommendation, not a ruling. | Cite rulings 4 and 10, which make Speak and Autonomous doors, with Speak in two panes (rev 9 item 1). |
| §1.14 ("`GET /reading/continue` reads the table") | The route is described as existing. | It does not exist on main (grep empty), and the store has only `get` and `put`. | Mark it NEW (LB-14). |
| §1.0 "project" row | `interview_projects` is at `schema.py:322-337`, and it is never reused. | The line has drifted to `:330-338`. R39's "My projects" names Speak projects. | Fix the citation. Speak's "My projects" means `interview_projects` under `/speak`, joined to the registry only through `member_kind: speak_project` (ruling 4). |
| C3 (lane A keymap) | "Do NOT bind Cmd+Left/Right or Cmd+F." | R25 says the agent pane "can be expanded with command F like the Omarchy flow" (K-12). | **Closed.** C3 is confirmed (DECISIONS, 2026-09-26), and prefix+f / ctrl+alt+f is R25's "command F" (lane-A default 7). |
| `config.yaml:150-158` | "`processing.transcription` computes USD … reports via `dispatch.call` events." | No such module exists on main. Whisper is unmetered. | Correct the comment (LB-12) and meter it (LB-23). |
| Caddy allowlist (`Caddyfile.j2:71`) | `/projects/*` on main. | Bare `GET` and `POST /projects` would be served the SPA HTML. | Fixed on the LB-2 branch as `/projects*` (`f39427b83`). The remaining new prefixes ship with their packages (§3 rule 6). |
| Ruling 17 against lane-A default 8 | The cross-check read ruling 17 as "never auto-send". Lane A's default 8 sends a conversational voice note when recording stops. | When voice sends is a UI question the ruling does not settle. | **Recorded, not resolved.** The server rule is the same either way: only the submitted transcript is kept, written by the consuming route. The timing is lane A's default, and the operator may overturn it. |
| Part 2 draft §B9 against ruling 17 | `voice_capture_event_id` comes back on the transcribe response and rides in the client's `input`. | Writing `voice.captured` at transcription time keeps a transcript the operator has not confirmed, and a client-supplied id can point at any event. | Lane B mints the id at the consuming route, which returns it (LB-12). Lane A adjusts §B9 at the co-sign. |
