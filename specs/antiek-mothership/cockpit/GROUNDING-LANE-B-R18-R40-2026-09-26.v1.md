# Lane B grounding for the operator's addendum, R18 to R40

**Status.** This is draft input to THREAD-CONTRACT rev 9, Part 1. It is not signed, and nobody builds against it until rev 9 is co-signed by both lanes.

**Author.** Antiek Sweep v2 (lane B, a59f7aa2), synthesized from four cluster groundings: agent-output branching, projects and transfers, Books, and voice/Converse/Speak.

**Ground truth.** `origin/main` = `d61e5256d` (2026-09-26 23:33 +0300), abbreviated `@d61e525`. It was read read-only through `git show` and `git grep`. Two other heads are cited:
- the B0 and wave-5 export branch, `origin/fix/audit-wave5-c2-export` = `2be3e0d1b`, which is 64 commits ahead of main and 367 behind it;
- the companion stack, `origin/feat/companion-spr03` = `0af7a2b7b`.

**Evidence labels.** A citation is VERIFIED unless it is marked INFERRED. This synthesis re-read the load-bearing citations; the scripts are `~/.claude/jobs/a59f7aa2/tmp/scratch/synth/v1.sh` to `v5.sh`.

**Binding inputs.**
- The operator requirements are `forensics/REQUIREMENTS-2026-09-26.md`, R18 to R40, including the addendum quoted verbatim.
- The lane split is in `cockpit/GOAL-cockpit-2026-09-26-v2.txt`.
- The operator decisions are D1 to D6, C1 to C5, and T6, T7 and T9 in `DECISIONS.md`.
- The contract is THREAD-CONTRACT rev 7 (signed) and rev 8.x (under audit).

---

## 1. Verdict

Lane B can meet R18 to R40 without a new store.

**Which requirements lane B carries.** Three requirements (R22 to R24) belong to lane A and need only thin read seams from lane B. The other twenty compose over one of two things:
- stores main already has: investigations and their event logs, `write_folders`, `derived_asset_revisions`, `reading_state`, account memory, the Speak tables and the Midnight Oil ledger;
- structures the signed contract already commits lane B to build: the §1.5 registry, §1.8 turns, §1.10 merge, §1.11a reformat, §1.12 companion document and §1.13 ledger.

**What main is missing.** Main lacks behaviour, plus one missing axis per cluster:
- an addressable anchor into an agent's output;
- a draft before a merge is accepted;
- a product dimension on projects;
- a scope and participants on dialogue;
- a spend class for conversational and voice dispatches.

**What gates most of the work.** Three dependencies, none of them new:
- B0 and the wave-5 rights resolvers still sit on unmerged `fix/audit-wave5-c2-export`.
- The §1.11a stores are absent from main.
- LB-2, the project registry, has no commit yet.

**Forward fixes that should ship first.** Five defects on main, and one contract misstatement, need none of those dependencies:
1. `/voice/transcribe` and `/speech/tts` block the event loop of the single uvicorn worker.
2. Invitee voice answers skip the correction step, and they are authored as `__operator__`.
3. The Speak-to-Write path copies claim text, and a takedown never reaches the copy.
4. `promote_investigation_to_deliverable` checks no owner and mints a new deliverable on every call.
5. `GET /speak/projects` takes the write lock for a read and filters no owner.
6. The misstatement: §1.14 describes `GET /reading/continue` as reading the table, but that route does not exist.

**One contract change is time-critical.** On the unmerged B0 payload, `BranchOrigin` can point only into a document. The output anchor that R18 needs must therefore land before c2-export merges, or it will cost a second schema bump.

---

## 2. Requirement register

Status key:
- EXISTS: main meets the lane-B part.
- EXTEND: a named module gains a delta.
- NEW: defined here.
- lane A only: lane B supplies at most a read seam.

| R | Lane-B status | Key evidence (`@d61e525` unless noted) | WP |
|---|---|---|---|
| R18 highlight agent output, re-prompt a sub-agent | EXTEND | <ul><li>`HighlightToolbar.tsx:45-52`: the highlight becomes the question itself, and the withheld guard runs only in the client.</li><li>`app.py:2856-2867`: `spawned_from` is written best-effort and never sets `parent_event_id`.</li><li>`orchestration/loop_one/orchestrator.py:2085-2098`: the child's context omits both `spawn_context` and the parent.</li><li>`app.py:2754`: an owner-model launch refuses any parent.</li><li>`BranchOrigin` is document-only (`events.py:2546-2568@2be3e0d1b`).</li></ul> | LB-19, LB-20 |
| R19 harden an insight or chase a question; several lanes at once | EXTEND | <ul><li>`distill_routes.py:103-163`: insights and questions carry stable ids, and `challenge` refines a note in place.</li><li>`app.py:5077-5170`: question escalation to a reserved child.</li><li>No `parent_thread_id` filter exists.</li></ul> | LB-20 |
| R20 merge manually after seeing a draft | NEW | <ul><li>The only merge-like path is `/research/artifacts/compose` (`artifact_routes.py:103-105,374-398`). It is ungated, and its GET writes files.</li><li>`build_session_evidence_pack` (`orchestration/session_evidence_pack.py:195`) is reusable.</li><li>No `merged_from` exists outside twin notes (`substrate/twin_notes/store.py:101`).</li></ul> | LB-24, LB-25 |
| R21 merges group ideas for agents; a growing agent callable across projects | NEW | <ul><li>`write_folders` is node-only and emits no events (`substrate/write/folders.py:44-75`).</li><li>Account memory never promotes a prompt (`account_memory_context.py:1-10`).</li><li>`evidence_index` is absent from main.</li></ul> | LB-24, LB-26 |
| R22 redesigned homes | lane A only | Reads for the homes: no `/projects` route exists outside Speak; `/reading/continue` is absent (the grep is empty); the Speak index is `speak_routes.py:405-431`. | seams via LB-14, LB-16, LB-17 |
| R23 keys to jump between products | lane A only | The product registry is client-side (`apps/reading/src/shell/workflowTaxonomy.ts:36`). | none |
| R24 project keys and cockpit keys | lane A only | `order` and `pinned` exist in contract §1.5 only; `project_tabs` is absent from main. The "familiar mode" needs a derived `last_mode`. | seam via LB-17 |
| R25 an agent-first pane: one agent or a group | EXTEND (one agent), NEW (group) | <ul><li>`/thought-partner` is stateless (`app.py:6654-6732`). The client holds the history, and `investigation_id` defaults to `__sidecar__` (`:6719`).</li><li>No `thread.turn` event exists.</li><li>No participant primitive exists.</li></ul> | LB-21, LB-26, LB-27 |
| R26 an add-project key opens a create page | NEW | Five ad-hoc create calls, none idempotent: <ul><li>`POST /deliverables` (`app.py:3548-3578`), which takes no owner;</li><li>`POST /speak/projects` (`speak_routes.py:359-370`);</li><li>`POST /write/deliverables/from-investigation`;</li><li>`/books/import/*`;</li><li>the Midnight Oil preflight.</li></ul>`speak/biography_composition.py:85-154` is the precedent for a create that wires several surfaces. | LB-15, LB-17 |
| R27 a new project means something different per product | EXTEND | <ul><li>§1.5 `kind` is `project \| reading` in the contract only.</li><li>Autonomous research is a preflight only (`midnight_oil_routes.py:21-23`).</li><li>The folder owner defaults to `__operator__` (`folders.py:57`).</li></ul> | LB-17 |
| R28 whole or partial transfers | EXTEND (Research→Writing, Speak→Writing), NEW (Research→Autonomous, Research→Books) | <ul><li>`promote_context.py:196-242` does no owner check and creates a deliverable on every call.</li><li>`speak/write_composer.py:74-91` copies claim text into `outline_blocks`.</li><li>`speak/biography.py:98-122` composes every claim and ignores `interview_projects.deliverable_id`.</li></ul> | LB-15, LB-18, LB-28 |
| R29 agents that grow beyond projects | NEW | <ul><li>Memory is owner-scoped with reference provenance (`substrate/memory/models.py:10-25`).</li><li>`note_retrieval` scans every node with no owner filter (`substrate/context_pack/note_retrieval.py:75-82`).</li><li>No agent concept exists.</li></ul> | LB-26 |
| R30 casual-interest reading projects | EXTEND | <ul><li>`folders.py:57-75`: membership is node-only, with no role or order.</li><li>`GET /books/curate` (`books.py:1282`).</li></ul> | LB-17 |
| R31 Reading becomes Books; the rabbit hole | NEW product id (no data migration), EXTEND rabbit hole | <ul><li>`workflowTaxonomy.ts:36,115` has the id `read` and the label "Read".</li><li>Talk-to-book answers from "ONE book … only this book" (`substrate/books/book_qa.py:1-9`), on the route at `books.py:2262`.</li><li>`/read/:documentId` is stored in artifacts, so it is kept.</li></ul> | LB-17, LB-22, LB-14 |
| R32 an autonomous notebook in Books | EXTEND | <ul><li>The ratified per-investigation auto notebook (`docs/decisions/spr-06-auto-notebook-proposed.md`) is derived from `GET /research/{id}/distill`.</li><li>Bug: companion entry ids hash the claim text (`substrate/companions/projector.py:210-212@0af7a2b7b`), while living notes rewrite that text in place (`roles/note_taker/living_note.py:136`).</li></ul> | LB-29 (+ LB-9 amendment) |
| R33 Books may select a Research project | EXTEND | <ul><li>Filing puts a document in one investigation only (`events.py:465`).</li><li>The start request carries no `project_id` (`app.py:438`).</li><li>The Research–Read boundary decision is still PROPOSED.</li></ul> | LB-18, LB-29 |
| R34 voice input everywhere | EXISTS (capture and ASR), EXTEND (bounds, off-loop, metering, input provenance) | <ul><li>`read_voice.py:91-108` reads an unbounded body and calls the synchronous client.</li><li>The client uses synchronous `httpx` with a 120 s timeout (`acquisition/voice/client.py:105-113`).</li><li>`substrate/dispatch/config.yaml:150-158` claims a cost helper that does not exist.</li></ul> | LB-12, LB-23 |
| R35 Converse: talk to any project | NEW | <ul><li>The stateless thought partner (`app.py:6654-6732`).</li><li>Book ask is page-cited over one book (`books.py:2262-2480`).</li><li>The pattern of search restricted to given document ids exists (`substrate/books/meta_reading.py:204-225`).</li></ul> | LB-21 |
| R36 time-bound monologues | EXTEND | <ul><li>Meta-reading length box: 150 wpm, 1–120 minutes (`meta_reading.py:59,75-76,99-126`).</li><li>TTS is 8,000 characters, blocks the loop and has no server-side §9.0 check (`speech.py:19-38`).</li><li>The duration planner (`substrate/multimedia/planner.py:156-176`).</li></ul> | LB-30, LB-31 |
| R37 prompt by text and voice notes during a conversation | EXTEND (turns), NEW (interrupting a monologue) | <ul><li>The confirmed-transcript guard (`substrate/books/voice_note.py:168-172`).</li><li>No turn persistence exists on main.</li></ul> | LB-21, LB-30 |
| R38 Speak gathers insight by frictionless voice notes | EXISTS (private voice path), EXTEND (integrity and spend) | <ul><li>The invitee voice route (`speak_routes.py:1379-1504`) passes raw ASR to `submit_answer` (`:1480-1497`).</li><li>Authorship defaults to `__operator__` at tier 2, as `USER_CONTENT` (`acquisition/voice/adapter.py:61,124,201,214-218`).</li><li>The follow-up stub (`substrate/speak/async_interview.py:430-446`).</li></ul> | LB-13, LB-23 |
| R39 Speak manages my projects, inbound invites and public requests | EXISTS / EXTEND (my projects), NEW and G7-gated (inbound), EXISTS read-only (public) | `GET /speak/projects` takes a write lock for a read and has no owner filter (`speak_routes.py:405-431`). | LB-15, LB-16 |
| R40 Speak's three sections left, detail right | EXTEND (read models only) | The project page composes several calls (`apps/reading/src/modes/Speak/index.tsx:8-22`). | LB-16 |

---

## 3. Lane-B work packages

### Rules every package inherits

1. **No parallel store.** Each concept has one home:

   | Concept | Store |
   |---|---|
   | Threads | Investigations and their logs |
   | Projects | `write_folders` and `write_folder_members` (§1.5) |
   | Derived text | `derived_asset_revisions` |
   | Positions | `reading_state` |
   | Durable memory | Account memory |
   | Money | `BudgetLedger` |

   The only new rows are those the contract names.
2. **Owner scope, reads and idempotency.**
   - Every new route is owner-scoped from day one (§1.15).
   - Every GET uses `connect_read` and writes nothing.
   - Every mutation takes an `idempotency_key` bound to a request identity: a repeat replays, and a mismatch answers `409 idempotency_conflict`.
3. **Rights.** Every rights-bearing text is a `GatedText`, and a model sees only served text. Speak material is additionally filtered, at the moment of use, by live consent and by takedown.
4. **Single writer.**
   - Writes go through the API process's `connect_write`.
   - Events go through `write_event_outbox` inside the same transaction, or through strict `emit_typed`.
   - No database lock spans a model call.
   - No daemon writes directly.
5. **Spend classes.** Every new dispatch belongs to exactly one class. This is new in rev 9 (§1.13) and pending ruling O-16.

   | Class | Members | Admission | Can stop at the cap |
   |---|---|---|---|
   | Research start | Branch from output, harden and chase lanes, agent-call research, "Research further" | ACU gate before start, then the run's research budget (as for islands) | No: stops with `user`, `cancel` or `budget` |
   | Cap-admitted generation | Merge drafts, monologue text, monologue audio, the narrated notebook digest, autonomy continuations, diligence, reformat | `DiligenceBudget` admission plus a `reserve_dispatch` hold per dispatch | Yes: `cap_reached`, `cap_overshoot` |
   | Conversational turn | Ask turns, Converse turns, group rounds, book ask, Speak interviewer follow-ups | None. Each request is bounded by `max_tokens`, and a record-only settlement is written | No |
   | Operator ASR and TTS | `/voice/transcribe`, `/speech/tts` | None. Bounded body or text, record-only settlement | No |
   | Third-party triggered | Whisper behind Speak token doors | A per-owner daily intake budget; `429 rate_limited` when it is spent | Not applicable |

6. **Edge.** A PR that adds a new top-level prefix must add it to the one-line Caddy `@api_routes` allowlist in the same change (`infrastructure/ansible/templates/Caddyfile.j2:71`). The full-glob guard (`tests/test_caddy_allowlist_coverage.py:176-230`) fails otherwise. The line today has `/projects/*`, which does not match bare `/projects`, so LB-2 changes it to `/projects*`. The line is a merge hotspot both lanes touch.
7. **Schema.** Event additions ride one sequenced bump per wave, with codegen in the same commit (§1.16). Speak event strings stay Speak-local and need no bump (`substrate/speak/events.py:10-23`).

### Order of the packages

| Tier | Packages | Gate |
|---|---|---|
| 0 | LB-12 to LB-16 | Forward fixes on main, independent of B0, LB-2 and §1.11a |
| 1 | LB-17 and LB-18 | LB-2 |
| 2 | LB-19 to LB-23 | B0 merged with the rev-9 origin, W2's rights-gated pack, LB-3, and the §1.13 ledger extension |
| 3 | LB-24 to LB-31 | W3 merge, §1.11a (LB-4b, LB-5) and LB-9 |

### LB-12 · Voice and TTS service hardening (R34)

**Scope**
- Move the provider calls in `/voice/transcribe` and `/speech/tts` off the event loop, using the `_off_loop` pattern already used at `speak_routes.py:1480-1497`.
- Bound the transcribe body at 25 MB on the server and refuse larger bodies with `413 too_large`.
- Take optional `thread_id`, `project_id` and `language`, each checked for existence and owner.
- Return `{transcript, language, duration_seconds, asr: {provider, model}, cost_cents | null}`. Cost is duration × $0.006 per minute, and `null` when the duration is unknown.
- Accept `input: {modality: text | voice, asr_model?, language?, duration_s?, edited}` on `POST /investigations` and store it on the start payload. The prompt stays `origin: operator`. Ask and reformat accept the same field as those routes land.
- Keep no audio.
- Correct the comment at `config.yaml:150-158`, which names a `processing.transcription` helper that does not exist.

**Acceptance (red-first)**
- `/health` answers within 200 ms while a stubbed transcription sleeps 2 s. This is red today: `read_voice.py:101` calls the synchronous client on the loop.
- A 25 MB + 1 byte body gets 413 before the provider is called.
- An unknown `thread_id` gets 404.
- `cost_cents` is `null`, never `0`, when the duration is missing.
- A voice-sourced launch records `input.modality: voice`.
- No audio file exists under the storage root after a transcription.

**Depends on:** none. Settlements arrive with LB-23.

**Risks**
- The operator's audio goes to OpenAI. Retention stays "never" (O-17).
- Spend is unmetered until LB-23.

### LB-13 · Speak intake integrity (R38)

**Scope.** Close the six gaps in R38:
1. Wire the interviewer dispatch, keeping `max_followups=3` and a bounded `max_tokens`. HTTP callers omit it today.
2. Store invitee voice answers with `transcript_status: unconfirmed`. They are kept out of claim extraction until the operator confirms them (O-19).
3. Author informant voice notes by their contributor handle through `speak_contributors`, with a contributor source kind, never operator tier 2 or `USER_CONTENT`. This waits on a rights review.
4. Add per-token and global voice rate limits, plus a per-owner daily Whisper intake budget that answers `429 rate_limited`.
5. Add the Speak-local strings `speak.answer.received` and `speak.claims.proposed` on the project log.
6. When `record` is revoked, exclude that interview's `voice_note` documents from every Speak-scoped retrieval.

**Acceptance (red-first).** Each gap reproduces red before its fix:
- An HTTP follow-up equals the stub string (`async_interview.py:440-446`).
- An unconfirmed invitee answer reaches claim extraction (`speak_routes.py:1487-1497`).
- The stored document's author is `__operator__` (`adapter.py:124,201`).
- A token past its hourly limit is still served.
- A revoked interview's chunks are still retrievable. This last one is INFERRED, since `consent.py:126-150` only flips flags.

**Depends on:** a rights review for item 3; LB-23 for settlements.

**Risks**
- Informant audio goes to OpenAI, and the operator's consent label reads only "Sharing a memory" (`apps/reading/src/modes/Speak/Invites.tsx:44-48`). The invitee copy is UNVERIFIED.
- Speak writes its events outside the database transaction (`substrate/speak/events.py`), so new strings go through the outbox.

### LB-14 · Continue reading (R22 Books home, R31)

**Scope**
- Add `ReadingStateStore.list_for_owner(owner, limit)`. The store has only `get` and `put` today (`substrate/books/reading_state.py:122,137`).
- Add `GET /reading/continue`, returning `{items[{document_id, title, author, document_type, gate, progress: {page_index, page_count, pct} | null, updated_at}]}`. `page_count` comes from `book_assets`.
- Keep the prefs allowlist empty unless the operator rules otherwise.

**Acceptance (red-first)**
- A document with no known page count returns `progress: null`, never 0%.
- While another process holds the writer, the GET answers a bounded 503 rather than hanging, and it takes no write lock.
- Another owner's rows never appear.

**Depends on:** none. The `/reading/*` glob already exists at the edge.

**Risks:** none beyond owner scoping.

### LB-15 · Owner, idempotency and takedown repairs on existing create and promote paths (R26, R28, R39)

**Scope**
- `promote_investigation_to_deliverable` checks the investigation's owner and takes an idempotency key. Today it looks up the synthesis by id only (`promote_context.py:196-201`) and inserts a deliverable on every call (`:232-242`).
- The Speak draft reuses `interview_projects.deliverable_id` once it is set, and composes only claims that are not under an active takedown and that hold `record` consent. Today `speak/biography.py:119-122` mints a new deliverable, and `:101-111` composes every claim.
- `POST /deliverables` and `POST /speak/projects` bind the request owner.
- `GET /speak/projects` filters by owner and reads through `connect_read`. This is coordinated with board claim `codex-speak-project-index-read-20260924`.

**Acceptance (red-first)**
- Promoting another owner's investigation is refused.
- Two calls with one key create one deliverable.
- A claim under takedown never lands in `outline_blocks` (repro against `write_composer.py:74-91`).
- Two Speak drafts produce one deliverable.
- Rows created through these routes carry the request owner, never `__operator__`.

**Depends on:** W1 owner-on-start for the full investigation owner check. Until then, the check reads the start payload's `owner_user_id` where it is present and refuses a mismatch.

**Risks**
- Collision with the codex claim and with PR #3011's owner binding.
- The serve-time gate for claim text already copied is LB-18's.

### LB-16 · Speak section read models (R39, R40)

**Scope.** Read-only routes, one call per pane:

| Route | Returns / behaviour |
|---|---|
| `GET /speak/sections` | `{my_projects: {count, attention}, invites: {count, state}, public: {count, contribution: live \| gated_G7}}` |
| `GET /speak/projects/{id}/detail` | Composed from the existing functions (`get_project`, the invite lifecycle, `async_interview.resume`, repings, `economics_mode`); fields listed below |
| `GET /speak/public/{project_id}` | An exact open path like `/speak/feed`, filtered by takedown |
| Invites section | Answers `state: gated_G7` (O-20) |

The detail route returns:
- `project`
- `economics_gate`
- `invites[]`
- `interviews[{interview_id, who, status, consent, pending_questions, last_answer_at, unconfirmed_answers}]`
- `arrivals_unseen`
- `claims_summary`
- `repings[]`

**Acceptance (red-first)**
- No GET in the module takes `connect_write` (a test over the route module), and a held writer yields a bounded 503.
- Counts are `null`, never `0`, when unreadable.
- A taken-down subject is absent from the public detail.
- Another owner's project is absent from the sections and answers 404 on detail.

**Depends on:** LB-15, or the codex claim, for the owner filter; LB-13 for arrivals. The seen state waits on the W3 inbox.

**Risks**
- A public route could leak `subject_ref`.
- Inbound invites stay honestly gated until G7 (invariant 5).

### LB-17 · Registry products, shapes, create seeds and the shelf (R22, R24, R26, R27, R30, R31)

**Scope.** Built on LB-2's registry, in the order of the fields.

*Folder fields*
- `home_product: research | writing | books | speak | autonomous` picks the create page and the home.
- `products[]` lists where the project is present, per D1.
- `kind: project | book | interest`, with `reading` accepted as an input alias for one release.
- `primary_document_id` is required for `book`, and must have a `book_assets` row. It is null for `interest`.

*Member fields*
- `member_kind` gains `speak_project`, `derived_asset` and `project`. A `project` member is a context link, and aggregates never recurse through it.
- `member_role: primary | shelf | context | managed | agent | null`.
- `ordinal`.

*`POST /projects {home_product, kind, title?, seed, idempotency_key}`*
- The seed union is:
  - `question`, stored but not launched;
  - `blank_deliverable`;
  - `from_investigation`;
  - `speak {subject_ref, publish_intent, topic}`;
  - `book {document_id}`;
  - `interest {title, seed_prompt?}`;
  - `template: biography`, delegating to `create_biography`;
  - `autonomous {charter}`.
- The registry row, the seed rows, the members and `project.created` are all written in one `connect_write` transaction through `write_event_outbox`.
- The response is `{project, next: {kind: open_mode | launch_first_question | import_book | invite | consent_envelope, ref?}}`.

*Reads and writes*
- `GET /projects?product=&lens=books&archived=` carries §1.5's aggregates plus `shelf_count` and `last_mode`, which is derived from the newest `project_tabs.updated_at` per mode.
- `GET /projects/{id}/shelf` and `PUT /projects/{id}/shelf {document_ids[], expected_version}` use compare-and-set.

*Mode key and events*
- The mode key becomes `books`, with `reading` as an alias on the tab routes.
- Typed `project.*` events (`created`, `members_changed`, `shelf_changed`).

**Acceptance (red-first)**
- A double press with one key yields one project, and the same key with a different body answers 409.
- A crash injected after the seed insert leaves no registry row.
- Speak and Write seed rows carry the request owner.
- `kind: book` with a non-book document answers `422 seed_invalid`.
- A stale shelf PUT answers 409, and an agent actor adding a shelf member answers 403.
- A second `book` create for the same owner and document returns the same project.
- `/tabs/reading` and `/tabs/books` address one row.
- Bare `GET /projects` reaches uvicorn at the edge.

**Depends on:** LB-2, LB-15.

**Risks**
- Owner defaults leak today in three places (`folders.py:57`, `POST /deliverables`, `create_project`).
- Legacy threads with no `project_id` are adopted by document only (LB-18).

### LB-18 · Transfers and the Books lens (R28, R33)

**Scope**
- `GET /projects/{id}/transfer-candidates?to_product=` returns threads, claims or long-form documents, each with its gate.
- `POST` and `GET /projects/{id}/transfers {to_product, scope: whole | partial, to_project_id?, selection, idempotency_key}`, with an outbox event `project.transferred {transfer_id, from_project_id, to_project_id, to_product, scope, selection_digest}`.
- Semantics:
  - **Whole:** the same project id gains `to_product` in `products[]`.
  - **Partial:** a new or named target project receives member references, never copies.
- The supported pairs:

  | Pair | Behaviour |
  |---|---|
  | Research → Writing | Several investigations, whole or partial, with optional `node_ids[]`. One section per investigation, `graph_node` references, and the deliverable registered as a member. |
  | Speak → Writing | Selected `claim_ids[]` or `interview_ids[]`, filtered as in LB-15. Adds a serve-time gate for `source_block_kind='speak_claim'` blocks: a live takedown and scope check, where `attribute` is needed to name the informant, and `422 speak_publish_required` on share or export. |
  | Research → Books, whole | This is the R33 lens: the project gains `books`, and the shelf is picked from the long-form candidates. |
  | Research → Books, partial | A new `book` or `interest` project with a shelf, plus a `member_kind: project` context link back. |
  | Books → Research | The §1.5 promotion. |

  Every other pair answers `422 transfer_not_supported`.
- `GET /investigations` gains `document_ids[]`, and legacy threads with no `project_id` are adopted by shelf document.

**Acceptance (red-first)**
- A partial Research → Writing transfer places only the selected nodes, and a whole transfer keeps the same project id.
- A retry yields one transfer and one deliverable.
- A Speak claim taken down after transfer has its block text withheld on the next serve. This is red today: the copy survives.
- A Write export containing testimony answers 422.
- A book that cannot be served is listed `cite_only` with its reason, never dropped.
- A thread outside the shelf is hidden in the Books lens and visible in Research.

**Depends on:** LB-17, LB-15, W1 owner-on-start, and the W3 member table for the Speak gate.

**Risks**
- Rights over testimony leaving Speak.
- Bypassing Speak's publish scope and its escrow path (`speak_routes.py:864-887`).
- The GET scan cost over every `.jsonl` log (`app.py:3079`).

### LB-19 · Output segments and anchors (R18)

**Scope**
- The `OutputAnchor` type (rev 9 §1.4b).
- `GET /investigations/{id}/outputs`, owner-scoped. It returns segments with `content: GatedText` in display order, drawn from `synthesize.delivered`, `graph.node.inserted`, `note.refined`, `read.book_answered` and, after LB-3, `thread.turn`.
- A reformat thread answers `422 use_probe` and points at §1.11a spans.
- Quotes are kept only for segments that were served when they were pinned.

**Acceptance (red-first)**
- An anchor into a withheld segment answers `422 output_not_servable`.
- A tampered `segment_sha256` answers `409 output_anchor_stale`.
- A refined note yields a new segment, and the old anchor still validates against its own event.
- A reformat thread answers 422.
- A shared fixture proves that the server's NFC offsets equal lane A's rendering of `content.text`.

**Depends on:** B0 merged, with `BranchOrigin.output_anchor` added **before** the merge; the wave-5 excerpt gate `_excerpt_cleared`; LB-3 for turn segments.

**Risks**
- Missing the c2-export merge window forces a separate schema bump.
- A synthesis cleared on the export branch may still withhold on main until wave 5 lands.

### LB-20 · Branch from output, with purpose and lanes (R18, R19)

**Scope**
- `POST /investigations` gains:
  - `origin: {kind: selection, output_anchor}`;
  - `purpose?: harden | chase | ask`;
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
- Loop One loads the parent's gated pack and the focus span into `InvestigationContext`.
- `chase_mode` is forced `off` for output branches.
- `?parent_thread_id=` lists children in branch-event order, with `ThreadSummary.origin`.
- Sealed `.parquet` logs are enumerated.
- An owner-model child is allowed per O-3.

**Acceptance (red-first)**
- The parent's log holds `investigation.branched` with `output_anchor`.
- The child's `context_pack.assembled` lists the served parent items and the focus. This is red at `orchestrator.py:2085-2098`.
- A withheld-segment anchor never puts text into the child's start payload. This is red today: the server copies whatever text arrives.
- Three children with distinct purposes list with their origins.
- A branch whose child has no log reads `no_record`.

**Depends on:** LB-19; W2's `RightsGatedPack`; the §1.9 estimate (absent on main); rulings O-3 and O-4.

**Risks**
- Every highlight is a paid start.
- A parent whose log is written off-host as a remote-exec cascade leaf needs `409 parent_log_remote` until that log is funneled (INFERRED).

### LB-21 · Dialogue scope, agent sessions and Converse turns (R25 one agent, R35, R37)

**Scope**
- **Create.** `POST /investigations {kind: dialogue, scope?, participants?[], title?}`. `scope` is one of `{project_id}`, `{document_id}` or `{speak_project_id}`.
- **Ask.** `POST /investigations/{id}/ask {question, input?, at?, context_items[], idempotency_key}`. It persists `thread.turn {question, input, at?, answer: GatedText, context[], project_id}` together with `answer.provenance`.
- **Context resolvers, one per scope.**

  | Scope | Context |
  |---|---|
  | Research project | Member threads' gated packs, plus chunk search restricted to member documents |
  | Write deliverable | The current revision under the owner serve-time gate, plus `derived_asset_block_informs` |
  | Book | Delegates to `book_qa`; the dialogue branches from `read-<doc>` with `via: api` |
  | Speak project | Interviews whose `record` consent is live and that are not under takedown, plus `speak_claims` |

- **Agent sessions.** Asking an agent from a project records the turn on that agent's session dialogue for the project (`participants: [agent]`, `scope: {project_id}`), never on the agent's own log.
- **The route.** This is a new route; `/thought-partner` is not edited while #3278 and codex-r15 own it.
- **Answer refs.** Answers carry `source_refs {document_id, anchor}`.

**Acceptance (red-first)**
- A turn survives a reload and lists under `?kind=dialogue&project_id=`.
- A book-scoped turn never contains a withheld page.
- Revoked interviews are excluded.
- `cited_refs ⊆ retrieved_refs`.
- A key replay returns the first turn.
- A concurrent writer is not blocked during the model call.
- A turn with `at` sees monologue spans only up to `at.span_id`.

**Depends on:** LB-3, W2's pack, LB-17, LB-13 item 6, and coordination with #3278 and codex-r15 on the board.

**Risks**
- Informants' words reach a model provider.
- Owner-read gating must never leak into shared views.
- Turns are unmetered until LB-23.

### LB-22 · Book ask scope and openable refs (R31)

**Scope**
- `/books/{id}/ask` gains `scope: book | shelf | library`: owned-corpus retrieval under the same gate, with `shelf` requiring `project_id`.
- `read.book_answered` citations carry `source_refs {document_id, anchor}`.
- An agent opens a document only as a proposal and never acquires one. `/books/marketplace/purchase-request` (`books.py:1310`) is unreachable from any agent path.

**Acceptance (red-first)**
- A reply naming another owned book returns a ref that resolves.
- A document that cannot be served comes back `cite_only`.
- `scope: book` behaves exactly as today (regression).
- An agent-initiated open of an absent document files a `read` flag and calls no acquisition route.

**Depends on:** LB-3; LB-17 for the shelf scope.

**Risks:** `read-<doc>` is keyed per document, not per owner, which remains pre-multi-user work.

### LB-23 · Record-only spend for unadmitted dispatches (R25, R34 to R38)

**Scope**
- NEW `BudgetLedger.record_dispatch(run_id, dispatch_id, actual_cents | None, thread_id, project_id, kind)`, idempotent by `dispatch_id`. An unknown cost is recorded as `cost_unknown`, never as `0`.
- Wired into `/voice/transcribe`, `/speech/tts`, ask turns, book ask and Speak follow-ups.
- `spend_today` includes these settlements.
- The Speak token-door intake budget refuses with 429.

**Acceptance (red-first)**
- A transcription carrying a thread and project writes one settlement with both.
- A replayed `dispatch_id` writes nothing.
- `spend_today` rises by the recorded amount, and reads `null` with a reason when any settlement that day is `cost_unknown`.
- A record-only dispatch is never refused by the cap, and a later diligence admission sees the reduced `remaining_cents`.

**Depends on:** the §1.13 ledger extension (W3's `reserve_dispatch` and `settle_dispatch`); ruling O-16.

**Risks:** conversational spend can starve diligence admissions. That is truthful, and the ruling decides whether it is wanted.

### LB-24 · Thread merge with rev-9 targets (R20, R21)

**Scope**
- Signed §1.10: the rights-gated preview, `thread.merge_started`, `investigation.merged_into`, the merged start event, and `merge_pending`.
- Rev 9 adds:
  - `into_thread_id`, which appends `thread.merged_in {merge_id, merged_from[], accepted_draft, preview_digest}` to the target;
  - `merged_from` members counted as export dependencies;
  - `merge_ids` exposed on summaries.
- Retire `/research/artifacts/compose*` once lane A moves `ReadingCompanion` and `ArtifactOutlineShelf` to the preview.

**Acceptance (red-first)**
- A partial merge never reports success.
- A replay resumes from `merge_started`.
- An unresolved member withholds the merged excerpt.
- GET routes write nothing. This is red today: the compose draft GET renders files.
- Merging into a target leaves the target's state unchanged and lists the members under `merged_from`.

**Depends on:** W2's pack; the wave-5 resolvers `resolve_pin_sources` and `resolve_synthesis_sources`; rulings O-1 and O-2.

**Risks:** a merge spans several logs, so the pending pattern is mandatory.

### LB-25 · Merge drafts (R20)

**Scope**
- `POST /threads/merge/drafts {thread_ids[], preview_digest, question, into_thread_id?, model_choice?, idempotency_key}` creates a `reformat` thread whose §1.11a source is `{threads[], preview_digest}`.
  - Its core set is the documents that the pack items resolve to.
  - Member threads count as validated `research_supplemented` evidence.
  - Only served items reach the model; `cite_only` items are cited, never quoted.
- Generation is cap-admitted.
- An operator edit is a `revise` (T6).
- Commit requires `draft: {derived_asset_id, revision_id}`, a matching `preview_digest`, and `mostly_generated` in the acknowledgements when it applies.

**Acceptance (red-first)**
- A commit without a committed draft of the same digest answers `422 draft_required`.
- A withheld item's text never appears in the dispatch request body (asserted at the dispatch seam).
- An edited draft is the one accepted.
- A stale preview answers `409 preview_stale`.
- An exhausted cap answers `402 refused_capped` before any dispatch.

**Depends on:** LB-24, LB-4b, LB-5, the cap ledger, and ruling O-1.

**Risks:** the model is paid per draft, so the estimate must come first.

### LB-26 · Agents across projects (R21, R29)

**Scope**

*Identity*
- `POST /investigations/{id}/agent {charter, model_choice?, idempotency_key}` writes `agent.promoted`. `PATCH` writes `agent.charter_revised`.
- `ThreadSummary.agent` and `project_ids[]`.

*Membership*
- Membership is `{member_kind: investigation, member_role: agent}` in any number of projects, with owner equality enforced.

*Context*
- `GET /investigations/{id}/context?project_id=` is the one assembler, shared with §1.8, tier 1 and LB-27.
- It assembles, in this order:
  1. the charter;
  2. the thread's own gated pack;
  3. its accepted drafts;
  4. its `merged_from` members, recursively to depth 8;
  5. the calling project's context.
- It is budgeted by `reuse_token_budget`, and every item carries `included` and a `reason: budget | withheld`.

*Calls*
- Agent-call research is a B0 branch with `via: agent_call`, whose `project_id` is the calling project.
- `note_retrieval` is restricted through `restrict_node_ids` built from owned membership.
- No agent path writes account memory in this package (O-6).

**Acceptance (red-first)**
- An agent listed in two projects returns the same lineage context, plus each project's own context.
- Budget truncation is reported.
- A cross-owner membership answers 403.
- No path writes to the memory store (asserted over the store).
- Agent-call spend attributes to the calling project.
- An item derived from `personal_reading` appears refs-only in another project.

**Depends on:** LB-17, LB-21, LB-24 (with LB-25 for drafts), LB-9, and ruling O-6.

**Risks**
- Paraphrase can leak across projects even when quotes are gated.
- `/thought-partner` ownership, as in LB-21.

### LB-27 · Group dialogue (R25)

**Scope**
- A dialogue with 2 to 4 `participants[]`.
- `ask {addressees?[]}` runs sequential answers, and each answer sees the round's earlier served answers.
- Each answer is recorded as `thread.turn {round_id, speaker_thread_id}` in the dialogue's own log. A round commits as `dialogue.round {round_id, question, responses[{thread_id, turn_event_id | failed: reason}]}`.
- A per-round bound is shown before the round is sent, and an unpriced round needs explicit confirmation.
- Each participant answers with its own `/context` for the dialogue's project.

**Acceptance (red-first)**
- A failed participant yields `partial` with its reason, never a dropped answer.
- A key replay completes only the missing responses.
- A fifth participant answers 422.
- No participant's own log is written.

**Depends on:** LB-21, LB-26, LB-23, and ruling O-5.

**Risks:** the spend multiplies by the number of participants, which is why participants are capped and every round is bounded.

### LB-28 · Autonomy envelope and Research → Autonomous (R28)

**Scope**
- `POST /investigations/{id}/autonomy {max_cents, expires_at, model_choice}` writes `agent.autonomy_consented`, after validating the envelope through the Midnight Oil preflight (`substrate/midnight_oil/contracts.py:93-130`). `DELETE` writes `agent.autonomy_revoked`.
- The Research → Autonomous transfer promotes the selected threads in place, with `member_role: managed`. Each thread keeps its research-project membership.
- The daemon's scan is scoped to the owner's managed threads.
- Continuations are tier-1 `continue_from_parent` runs with `chase_mode`, held through `reserve_dispatch`, and branched with `via: chase`.

**Acceptance (red-first)**
- Nothing spawns without a live envelope.
- The envelope ceiling and the daily cap are both enforced.
- An unmanaged thread is never chased.
- A revocation stops the next admission.
- An expired envelope refuses.

**Depends on:** LB-10, LB-26, the §1.13 ledger, and ruling O-11.

**Risks**
- The standing consent is a scoped exception to D4.
- The daemon's gap scan reads every investigation today (`orchestration/continuous/daemon.py:1-30`).

### LB-29 · Books notebook lens (R32, R33) and the LB-9 amendment

**Scope**

*Amend LB-9*
- The entry id is the sha of `(owner_user_id, scope, scope_id, node_id)`, never of the claim text.

*New fields and parameters*
- `anchors[]` and `chapter?`, the chapter from `book_assets.toc_json`.
- `GET /projects/{id}/companion-document?lens=books&document_id=&group=chapter`.

*Thread set*
- Project threads.
- Legacy threads adopted by shelf or context document.
- The owner's `read-<d>` answers.

*Audiences and rebuilds*
- Two audiences: owner-read and public.
- The rebuild triggers are a terminal event, a `thread.turn`, a `read.book_answered`, a resolved island, a landed diligence run, or a shelf change. A `reading.position` event is **not** a trigger.
- A rebuild writes a typed `companion_document.refreshed`, never the untyped `companion.rebuilt` (`substrate/companions/watcher.py:319@0af7a2b7b`).

**Acceptance (red-first)**
- A living-note refinement keeps the entry id. This is red on the companion stack at `projector.py:210-212`.
- Two owners rebuilding one document get distinct ids.
- A `personal_reading` quote is served to its owner and is `cite_only` on export.
- A `reading.position` event alone never triggers a rebuild.
- The GET writes nothing.

**Depends on:** LB-9, LB-17, and the rights branches (wave 5, `fix/w5-mcp-hardening-20260923`).

**Risks:** the bounded scan (see LB-18).

### LB-30 · Monologue derivation (R36, R37)

**Scope**
- §1.11a gains:
  - `source: {scope, query}`, whose core set is the documents behind the retrieved chunks;
  - `params: {mode: explain, listening_minutes: 1..120, delivery: text | audio, voice?}`;
  - `parent_thread_id`, where the parent is the Converse dialogue.
- Chapters follow the planner's intro/body/recap ratios of 10/82/8 (`substrate/multimedia/planner.py:401-403`), with one `revise` per chapter.
- `listening_estimate {minutes, method, shortfall?}`.
- `/reformats/estimate` gains `assumptions.tts_chars` and `voice`.
- A re-plan is a `revise` with `listening_minutes = requested − elapsed` and the question as a `focus_item`.

**Acceptance (red-first)**
- A 30-minute request on a thin scope reports a shortfall rather than padding.
- Every chapter revision has zero unclassified spans.
- A short cap answers 402 before any spend.
- Chapter 1's spans answer 200 while chapter 2 is still generating.
- A re-plan leaves the earlier revision untouched.

**Depends on:** LB-4b, LB-5, LB-21, the cap ledger, and ruling O-18.

**Risks**
- Scope creep into web research. Research is offered only as an explicit branch.

### LB-31 · Monologue audio (R36)

**Scope**
- `POST /derived-assets/{id}/revisions/{rev}/audio {voice}` renders only served spans. A withheld or `cite_only` span becomes a fixed spoken marker and is never narrated.
- Segments are at most 3,500 characters. Each is one TTS dispatch, run off the loop and held under `reserve_dispatch` id `<gen>:tts:<n>`.
- A content-addressed cache holds segments per owner. It is keyed by the gate fingerprint and can be rebuilt.
- `GET …/audio/{n}` streams a segment.
- A measured duration replaces the estimate.
- The listening position uses `reading_state` on `drv-<generation_id>`.

**Acceptance (red-first)**
- Withheld text never appears in a TTS request body (asserted at the provider seam).
- A retried segment is held and charged once.
- The measured duration replaces "words@150wpm".
- After a core source is taken down, the next serve answers `withheld`.

**Depends on:** LB-30, LB-12, LB-23 and the ledger, and ruling O-18.

**Risks**
- The provider's per-request limit is UNVERIFIED; the 3,500-character segment is the hedge.
- A 30-minute script is about 27k characters, or about $0.41 of TTS (INFERRED arithmetic from `config.yaml:175`).

---

## 4. Seams with lane A (to be signed in writing)

S1 to S8 are signed at rev 7 and rev 8. The new seams are S9 to S23. Each row states what lane B serves, what lane A must send or render, and which lane-A UI waits on it.

| Seam | Lane B serves | Lane A sends or renders | Lane-A UI that waits |
|---|---|---|---|
| **S9** Output anchors (R18) | `GET /investigations/{id}/outputs` returns `segments[{segment_id: "<event_id>#<path>", event_id, path, role: thesis\|component\|insight\|open_question\|answer\|turn, node_id?, current, text_sha256, content: GatedText}]`. `POST /investigations {origin: {kind: selection, output_anchor}, purpose?, target?, kind?, question}` returns `{thread_id, branch_event_id}`. WS `investigation.branched` is broadcast on the parent. | Renders exactly `content.text` so the offsets hold. The tab node carries `branch_origin.output_anchor`, and `parent_tab_id` is the parent agent tab. `prefix+u` scrolls to `segment_id` plus the offsets. Drops the `localStorage` lineage (`useInvestigationTree.ts:89-96`). | Agent-output highlight menu, sub-agent tabs |
| **S10** Lanes (R19) | `GET /investigations?parent_thread_id=`. `ThreadSummary.origin {kind, purpose?, output_anchor \| anchor \| target, quote_state: served \| withheld}`, in branch order. | Lane labels ("hardening: …", "passage withheld"). | Right-pane lane view |
| **S11** Merge (R20) | `POST /threads/merge/preview`, then `POST /threads/merge/drafts`, then `GET /derived-assets/{id}/revisions/{rev}/spans`, then `POST /threads/merge {draft, into_thread_id?}`. WS `reformat.generated`, `thread.merge_started`, `investigation.merged_into`, `thread.merged_in`. | Part 2 §2.5 gains `drafting`, `draft_ready`, `draft_failed` and `draft_stale`. Accept is enabled only on a committed draft. | Merge UI |
| **S12** Agents (R21, R29) | `POST /investigations/{id}/agent`, `PATCH …/agent`, `GET /investigations?agent=true&project_id=`. `ThreadSummary.agent {charter: GatedText, promoted_at, model_choice, envelope?}` and `project_ids[]`. `GET /investigations/{id}/context?project_id=` returns items `{content: GatedText, included, reason?}`. `POST /projects/{id}/members {member_kind: investigation, member_role: agent}`. | A "what this agent knows" view and context chips. An agent tab holds only a `thread_id`. | Agent-first pane, cross-project agents |
| **S13** Dialogue (R25, R35, R37) | `POST /investigations {kind: dialogue, scope?, participants?[], title?}`. `POST /investigations/{id}/ask {question, input?, addressees?[], at?, context_items[], idempotency_key}`. WS `thread.turn` and `dialogue.round`. `ThreadSummary.scope` and `participants[]`. Answers carry `source_refs {document_id, anchor}`. | A scope picker unioning `GET /projects` and `GET /speak/projects`. Opens left tabs through S1. A round renders `partial` responses. | Agent-first pane, Converse |
| **S14** Projects (R22, R24, R26, R27, R30) | `POST /projects {home_product, kind, title?, seed, idempotency_key}` returns `{project, next}`; errors are `409 idempotency_conflict`, `422 seed_invalid {reason}`, `404 source_not_found` and `403 not_owner`. `GET /projects?product=&lens=&archived=` returns the aggregates plus `last_mode` and `shelf_count`. WS `project.created`. | A create page per `home_product`. Project keys launch into `last_mode`. | Homes, create pages, project keys |
| **S15** Shelf (R30, R31, R33) | `GET /projects/{id}/shelf` returns items `{document_id, title, author, document_type, gate, progress \| null, adopted_version?}`. `PUT …/shelf {document_ids[], expected_version}`. "Keep" is `POST /projects/{id}/members {member_role: context}`. WS `project.shelf_changed`. | Tab node `transient: true` for agent-opened left tabs. A keep action. A "Which book(s)?" step on first open. | Books left pane |
| **S16** Transfers (R28, R33) | `GET /projects/{id}/transfer-candidates?to_product=`. `POST` and `GET /projects/{id}/transfers`. WS `project.transferred`. Errors: `422 transfer_not_supported`, `422 speak_publish_required`. | Transfer flow with partial selection. | Transfers UI |
| **S17** Notebook (R32) | `GET /projects/{id}/companion-document?lens=books&document_id=&group=chapter`. Entries gain `anchors[]` and `chapter?`. | The Findings tab titled "Notebook" in Books, with the existing §2.7 states. | Books notebook |
| **S18** Book ask (R31) | `/books/{id}/ask {scope}`. Answers carry `source_refs {document_id, anchor}`. | `openDocumentInLeftPane` from answer refs. | Rabbit-hole tabs |
| **S19** Continue (R22, R31) | `GET /reading/continue` (LB-14). | Books home. | Books home |
| **S20** Voice (R34, R37) | `POST /voice/transcribe?thread_id=&project_id=&language=` returns `{transcript, language, duration_seconds, asr, cost_cents \| null}`. Errors: `400 empty_audio`, `413 too_large`, `429 rate_limited`, `503 transcription_unavailable`. `input {modality, asr_model?, language?, duration_s?, edited}` on launch, ask and reformat. | One `useVoiceInput()` hook: record, transcribe, show an editable field, submit with `input`. | Voice everywhere |
| **S21** Monologue (R36, R37) | `POST /reformats/estimate`, then `POST /reformats {source: {scope, query}, params: {mode: explain, listening_minutes, delivery, voice?}, parent_thread_id}`. WS `reformat.generated` per chapter. `POST …/audio`, then `GET …/audio/{n}` with a segment list `{segments[{n, span_ids, duration_ms \| null, url}]}`. The position is a `reading_state` PUT on `drv-<gen>`. | The player supplies `at` to ask. Shortfall copy. | Converse monologue player |
| **S22** Speak (R39, R40) | `GET /speak/sections`, `GET /speak/projects/{id}/detail`, `GET /speak/public/{project_id}`. Inbox kinds `speak_answer_received` and `speak_claims_proposed`, with `POST /inbox/{id}/seen` and a WS nudge. | Three left sections and a right detail layer. | Speak redesign |
| **S23** Autonomy (R28) | `POST` and `DELETE /investigations/{id}/autonomy`. `ThreadSummary.agent.envelope {max_cents, expires_at, spent_cents \| null, state}`. | Envelope consent copy, which must say "starts if free; pauses at the cap". | Autonomous Research view |

**Lane-A inputs lane B needs signed with these seams:**
- Part 2 §2.1 accepts `home_product`, `products[]` and `kind: project | book | interest`.
- §2.2 accepts `output_anchor`, `transient` and the `books` mode key.
- §2.3 accepts `output_anchor` wherever `anchor` is required.
- §2.5 gains the four draft states.
- The keymap resolution of C3 against R25's "command F" (conflict K-12).

---

## 5. THREAD-CONTRACT rev 9 items (Part 1)

Rev 9 is layered after rev 8.x is signed. Every item below is "(rev 9)".

1. **§1.0 vocabulary.**
   - **Books.** Books is the UI and product name, and its data key is `books`. `reading` stays the thread kind of `read-<doc>`.
   - **New words:**

     | Word | Means | Never used for |
     |---|---|---|
     | shelf | a Books project's ordered document members | |
     | context member | a document kept from a rabbit hole | |
     | transient tab | an agent-opened left tab | |
     | Notebook | the Books view of the companion document | |
     | agent | a promoted thread | a store |
     | lane | a branch subtree | an entity |
     | merge draft | a §1.11a derivation over a preview | |
     | transfer | membership plus a lineage event | a copy |
     | Converse | a door whose data is a scoped dialogue thread | |
     | monologue | a §1.11a derivation with a listening budget | |
     | voice input | `input.modality` | |
     | speak project | `interview_projects` under `/speak` | §1.5 |

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
     - `agent {charter, promoted_at, model_choice, envelope?} | null`;
     - `merge_ids[]`.
   - Filters gain `document_ids[]`, `participant`, `agent`, and `project_id` by membership plus birth project.
   - Legacy threads with no `project_id` are adopted by document for `book` and `interest` projects only.
   - NEW routes: `GET /investigations/{id}/outputs` (§1.4b) and `GET /investigations/{id}/context?project_id=`.
   - The project rule: the birth project rides the start payload, listing is by membership, and spend follows the calling project.
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
     path,              // closed set: /thesis_summary, /thesis_components/<i>/<field>,
                        // /canonical_label, /new_text, /answer, /answer/text
     segment_sha256,    // NFC segment text at pin
     start, end,        // Unicode scalar offsets, unicode-nfc-v1 (the anchored_highlights normalization)
     selection_sha256,
     quote?, prefix?, suffix?,   // only when the segment was served at pin
     node_id?
   }
   ```
   Events are append-only, so the anchor never drifts and needs no remap. "Refined since you branched" is derived from a newer `note.refined` for the same `node_id`.
5. **§1.5 registry.**
   - Folder fields: `home_product`, `products[]`, `kind: project | book | interest` with `reading` as an alias, and a nullable `primary_document_id` that must be `book_assets`-backed for `book`.
   - Member fields: `member_kind` adds `speak_project`, `derived_asset` and `project` (a context link, with no aggregate recursion); `member_role` and `ordinal` are added.
   - `POST /projects` with the seed union, idempotency and atomicity (LB-17).
   - The shelf routes.
   - Derived `last_mode` and `shelf_count`.
   - Typed events on the outbox: `project.created`, `project.members_changed`, `project.shelf_changed`, `project.transferred`.
   - Q-A5's promotion in place becomes the Books → Research transfer.
6. **§1.5a Transfers (NEW).** The five supported pairs, whole and partial semantics, candidates, the lineage event, and `422 transfer_not_supported` (LB-18).
7. **§1.6 tabs.**
   - `mothership: research | writing | books`, with `reading` accepted as an input alias for one release. Nothing migrates, since no `project_tabs` rows exist on main.
   - Nodes gain `transient` and `branch_origin.output_anchor`.
8. **§1.8 ask and dialogue.**
   - Tier 0 is the NEW route `POST /investigations/{id}/ask`. It reuses the thought-partner dispatch helper and edits `/thought-partner` only after #3278 and codex-r15 land.
   - A turn gains `input`, `at` and `addressees`.
   - The per-scope context table, including the Speak consent and takedown filter.
   - The agent-session rule.
   - `thread.turn` gains `{dialogue_id?, round_id?, speaker_thread_id?}`, and `dialogue.round` is added.
   - `read.book_answered` citations carry `source_refs`, and `/books/{id}/ask` gains `scope`.
9. **§1.9.** `ContextItem.kind` adds `project` and `speak_project`. The estimate covers a group round as the sum of its participants' bounds.
10. **§1.10 merge.**
    - The draft routes, and a commit that requires `draft`.
    - `into_thread_id` and `thread.merged_in`.
    - `merged_from` members are export dependencies.
    - The rule "members are never mutated" is restated as "members are never rewritten; a target receives one append".
    - `/research/artifacts/compose*` is retired.
11. **§1.11.**
    - A serve-time gate for `source_block_kind='speak_claim'` blocks checks takedown plus the `record`, `attribute` and `publish` scopes, and share or export answers `422 speak_publish_required`.
    - From-investigation takes multiple and partial selections, an owner check and an idempotency key.
12. **§1.11a.**
    - `source` gains three forms:
      - `{threads[], preview_digest}`, the merge draft;
      - `{scope, query}`, the monologue;
      - `{companion_document: {project_id, content_hash}}`, the narrated notebook digest, opt-in.
    - `params` gains `listening_minutes` (1–120 at 150 wpm), `delivery` and `voice`.
    - Also added: `listening_estimate`, one commit per chapter, the audio rendition routes, the rule that withheld spans are never narrated, and positions through §1.14 on `drv-<gen>`.
13. **§1.12 companion document.**
    - The entry id is the sha of `(owner_user_id, scope, scope_id, node_id)`.
    - Entries gain `anchors[]`, `chapter?` and `merge_ids[]`.
    - The `lens` and `group` parameters.
    - Owner-read and public audiences.
    - `reading.position` leaves the staleness and trigger list.
    - Twin notes enter only through promotion.
    - The MCP resources `antiek://merges/{merge_id}` and `antiek://threads/{id}/pack` serve GatedText only, after w5-mcp.
14. **§1.12a Agents (NEW).**
    - An agent is a promoted thread, with a charter event and a revision event.
    - The context assembler.
    - Cross-project membership with owner equality.
    - Session dialogues per (agent, project).
    - `via: agent_call` research.
    - No memory writes until ruling O-6 allows accepted proposals.
15. **§1.13 money.**
    - The spend-class table (§3 rule 5).
    - `record_dispatch`.
    - "Who can hit the cap" adds merge drafts, monologue text and audio, the narrated digest and autonomy continuations.
    - The autonomy envelope as the one scoped exception to D4 (O-11).
    - Inbox kinds: `speak_answer_received`, `speak_claims_proposed`, `monologue_ready`, `merge_draft_ready`.
16. **§1.14.** `GET /reading/continue` is NEW, with progress. The prefs allowlist policy is set per ruling.
17. **§1.15 owner holes.** The owner-scoped-from-day-one list adds `/projects*`, the transfers and the agent routes. The pre-multi-user holes gain:
    - `/speak/projects`
    - `promote_investigation_to_deliverable`
    - `note_retrieval`
    - `/events/typed`, which takes a client `investigation_id` with no owner check (`app.py:2396-2426`)
18. **§1.16 schema.** The rev-9 events are:
    - `thread.merged_in`
    - `dialogue.round`
    - `agent.promoted`, `agent.charter_revised`
    - `agent.autonomy_consented`, `agent.autonomy_revoked`
    - `project.*`
    - the fields on `thread.turn` and `BranchOrigin`

    Speak strings stay local.
19. **§1.18 delivery order.** The tiers of §3 are appended after W3.
20. **§1.19 Voice input (NEW).**
    - One route with bounds, run off the loop.
    - Record-only metering.
    - Retention: none.
    - The provider is chosen through the lineup's `transcription` action.
    - Input provenance.
    - The failure vocabulary of S20.
21. **§1.20 Speak read model (NEW).** S22's routes: GETs that never write, counts that are `null` and never `0`, and invites that report `gated_G7`.
22. **Citation refresh.**
    - The derived-asset tables are at `schema.py:1267`, `:1326` and `:1348`.
    - `/thought-partner` is at `app.py:6654-6732`.
    - `InvestigationStartRequest` starts at `app.py:438`.
    - `commit_start_acu` sites are `app.py:2892` and `books.py:2241`.

---

## 6. Operator rulings needed

Each ruling carries a recommended answer, and lane B keeps working on unblocked packages meanwhile. The cluster ids in brackets trace back to the cluster groundings.

| # | Question | Recommended answer | Blocks |
|---|---|---|---|
| O-1 [C18-1] | What is the "draft" shown before a merge? | A generated merged analysis with span provenance, shown after the free evidence preview. A merge commits only on an accepted draft, as the operator worded it. The preview ships earlier, with Accept disabled until LB-25. | LB-24 commit, LB-25 |
| O-2 [C18-2] | Merge into a new thread or into an existing agent? | Both. Default to a new merged thread. Fold into the common parent when every member descends from it, or into an agent the operator names. | LB-24 |
| O-3 [C18-3] | May owner-model (BYOT) launches have a parent? | Yes, when the caller owns the parent. The model defaults to the parent's, and an estimate is shown. Coordinate with #3278. | LB-20 |
| O-4 [C18-6] | What does a highlight of agent output offer? | Two costed actions: "Ask" (a dialogue child, tier 0) and "Research further" (tier 1). Harden and chase default to research. | LB-20 |
| O-5 [C18-4] | How does a group of agents answer? | Sequentially: each sees the round's earlier answers, with @-address for a subset, at most 4 participants, and a bound shown per round. | LB-27 |
| O-6 [C18-5, Q-R29a, Q-R29b] | How does an agent grow, and what may cross projects? | It grows only from accepted merges, never from turns. Its context is served GatedText. Items from `personal_reading` and Speak are refs-only. Cross-project context is allowed within one owner and shown as chips, and becomes "no" once a project is shared (G7). No durable agent memory in the MVP; memory proposals wait for R15's proposal path. | LB-26 |
| O-7 [Q-R27b vs Books] | Is the data key for Books `books` or `reading`? | `books` for every new enum (mode key, `home_product`), with `reading` accepted as an input alias for one release. The thread kind `reading` and every persisted name stay unchanged. Nothing persisted is migrated, since no rows exist. This resolves a disagreement between two clusters. | LB-17, Part 2 §2.2 |
| O-8 [Q-R27a] | Is Autonomous Research a fourth tab forest? | No. It is an agent-first view (R25) over managed agents, and documents open in the research tree of the agent's project. | LB-28, lane A |
| O-9 | Where does Converse live? | A door outside the mode cycle, like Speak (§1.0, T11). Sessions are dialogue threads on the chosen project, and opened reading goes into that project's existing mode tree. There is no fourth tree, so T9 holds. | LB-21, lane A |
| O-10 [Q-R28a, Q-R28b] | Which transfers exist, and what do "whole" and "partial" mean? | Five pairs: Research → Writing, Speak → Writing, Research → Autonomous, Research → Books, Books → Research. **Whole** keeps the same project id and adds the product (D1); Research → Books whole **is** R33's "select a Research project in Books". **Partial** creates a new project with member references and a lineage event. Every other pair is refused. | LB-18 |
| O-11 [Q-R28c] | A standing autonomy consent versus D4's per-flag consent? | One immutable envelope per agent: `max_cents` no greater than today's cap, expiry of 24 h at most, revocable, and consumed by the same ledger. Per-flag consent stays the rule everywhere else. | LB-28 |
| O-12 [Q-R28d] | Can Speak testimony leave through Write? | Only through Speak's publish flow. Write shows testimony to the owner and refuses share or export with `422 speak_publish_required`. | LB-18 |
| O-13 | What may sit on a Books shelf? | Any `document_type='book'` document, plus anything the operator adds explicitly. Agents only propose. | LB-17 |
| O-14 | What does the "autonomous notebook" mean, and what is it called? | A zero-spend view that updates itself. An LLM-narrated digest is opt-in per press and admitted under the cap. The Books tab is named "Notebook", and lane A relabels the TipTap Notebooks "My notes"; the data noun stays "companion document". | LB-29 |
| O-15 | What is the book agent's scope, and where is the Books–Research boundary? | The book first, then leads from the shelf and the owned library. Open-web research runs only as research threads anchored to the book. Notebook and meta-reading synthesis stay owned-corpus only. This also closes the pending `spr-08-meta-reading-boundary` decision. | LB-22, LB-29 |
| O-16 (new) | What spend class do conversational turns, ASR and TTS belong to? | Record-only settlements on the day's run: they count toward spent and `spend_today`, are never refused by the cap, and are bounded per request. Speak token-door Whisper has a separate daily intake budget that answers 429. | LB-23, LB-27 |
| O-17 | Voice defaults | Keep audio: never. Turn-based, not realtime, per `config.yaml:170-171`. Voice asks send automatically; distilling into notes, parks or claims waits for confirmation. | LB-12, LB-21 |
| O-18 | Monologue scope, bounds and provider | Project context only, with an honest shortfall and an explicit offer to research. 1 to 120 minutes. OpenAI `gpt-4o-mini-tts` on the operator key, estimate first, admitted under the cap. | LB-30, LB-31 |
| O-19 | Speak intake | One step plus an `unconfirmed` flag that the operator confirms at review. Informant content is contributor content mapped through `speak_contributors`, with accrual escrow-only. The invite consent copy must disclose AI transcription and model processing before Converse or a monologue may use Speak material; until then the Speak scope is excluded from both. | LB-13, LB-21 |
| O-20 | What are "private inbound invites I got"? | If it means requests from other people, it is an honestly gated section until G7. If it means responses to the operator's own invites, that already exists in the My projects detail. | LB-16 |

---

## 7. Conflicts with existing contract text or decisions

| Where | Text today | Conflict | Proposed resolution |
|---|---|---|---|
| B0 payload (`events.py:2546-2587@2be3e0d1b`) and §1.3 | `BranchAnchor.document_id` is required, `BranchOrigin` is document-only, and the `via` literal is closed. The docstring says a reader that finds a branch "knows the child ran". | R18 needs a branch origin in agent output. The docstring contradicts §1.3's rev-2 rule that a branch is a dependency, not proof. | Add `output_anchor`, `purpose`, `target` and `via: agent_call`, and fix the docstring, all before c2-export merges (rev 9 item 3). |
| §1.0, §1.6, Part 2 §2.1/§2.2, and C1 | Research, writing and reading are the modes, with `mothership: research \| writing \| reading`. | R31 renames the product to Books. | `books` for new enums with a `reading` alias; persisted names unchanged (O-7). |
| §1.5 and Q-A5 | `kind: project \| reading`, and a standalone book is promoted in place. | R27 and R30 need per-product meaning and a primaryless interest shelf. D1 says one project appears in every mode. | `home_product` plus `products[]` reconcile D1 with R27, and `kind: project \| book \| interest`. Promotion becomes the Books → Research transfer (O-10). |
| §1.8 tier 0 | "EXTEND `POST /thought-partner`", with the route shape `/investigations/{id}/ask`. | Editing `/thought-partner` collides with #3278 and codex-r15. Persisted, scoped turns need their own route. | The ask route is new and reuses only the dispatch helper (rev 9 item 8). |
| §1.10 | A commit creates a **new** merged thread. The preview is the only pre-commit view. "Members are never mutated beyond that record." | R20 asks for a draft before accept. R21 asks to enrich a growing agent. | A draft is required, `into_thread_id` is added, and a target takes one `thread.merged_in` append (O-1, O-2). |
| §1.12 staleness | A `reading.position` landing on the document makes it stale. | With R32's autonomous rebuilds, every position PUT (about 10 s apart while reading) would force a total rebuild. | Remove `reading.position` from staleness and from the triggers. |
| §1.12 and the companion stack | The owner is in the id material. | `make_evidence_id("claim", text, …)` (`projector.py:210-212@0af7a2b7b`) is text-keyed, and living notes rewrite the text in place. | Key on `(owner, scope, scope_id, node_id)` (LB-9 amendment). |
| §1.13 "Who can hit the cap" | Diligence, daemon and reformat. | Merge drafts, monologues, audio and autonomy continuations are also cap-admitted. Turns, ASR and TTS have no class. | The spend-class table (O-16). |
| D4 | No launch without per-flag consent. | R28's sub-agent-level management of autonomous research needs standing autonomy. | A bounded, expiring envelope per agent as the one scoped exception (O-11). |
| §1.14 | "`GET /reading/continue` reads the table." | The route does not exist on main (grep empty). The store has only `get` and `put`. | Mark it NEW (LB-14). |
| §1.0 "project" row | `interview_projects` is at `schema.py:322-337`, and it is never reused. | The line has drifted to `:330-338`. R39's "My projects" names Speak projects. | Fix the citation. Speak "My projects" means `interview_projects` under `/speak`, joined to the registry only through `member_kind: speak_project`. |
| C3 (lane A keymap) | "Do NOT bind Cmd+Left/Right or Cmd+F." | R25 says the agent pane "can be expanded with command F like the Omarchy flow". | Lane A's to resolve with the operator: either an explicit override of C3 recorded in DECISIONS, or the operator accepts the existing prefix/chord fullscreen binding as the "command F" of R25. Lane B has no stake beyond recording the conflict, which crosses a signed decision. |
| `config.yaml:150-158` | "`processing.transcription` computes USD … reports via `dispatch.call` events." | No such module exists on main. Whisper is unmetered. | Correct the comment (LB-12) and meter it (LB-23). |
| Caddy allowlist (`Caddyfile.j2:71`) | `/projects/*`. | Bare `GET/POST /projects` would be served the SPA HTML. The full-glob CI guard would catch it only once the route exists. | `/projects*` in LB-2. Each new prefix ships with its route (§3 rule 6). |
