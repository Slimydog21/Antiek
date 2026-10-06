# THREAD-CONTRACT rev 9, Part 1 (lane B): integrated draft

**Status: draft, unsigned, 2026-09-27.** Lane B (Antiek Sweep v2, a59f7aa2) integrated it from four cluster drafts and one critic's fix list.
- **The gate.** Nothing builds against a rule marked "(rev 9)" until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT. That is the rev-9 co-sign gate, THREAD-CONTRACT.md@e39840224 Part 1 ("Rev-9 co-sign gate (2026-09-27, agreed by both lanes)"). The exceptions are the tier-0 packages and the two signed halves that §1.18 names.
- **Where it goes.** This file is folded into `THREAD-CONTRACT.md` Part 1 after both lanes reconcile it with lane A's Part 2 draft (`THREAD-CONTRACT-REV9-PART2-DRAFT.md`) and the audit ACCEPTs. Until then it is a separate file, like lane A's draft.

**Base.** The signed rev 8.10, as `THREAD-CONTRACT.md` stands at home commit `e39840224` (signed by both lanes on 2026-09-27). Rev 9 amends it. Every signed rule stands unless a rule here, marked "(rev 9)", changes it.

**Code base.** `origin/main` = `b41f4ec9b`, read on 2026-09-27 with `git show` and `git grep` from the `lb2-projects-tabs` worktree after `git fetch`. The unmerged heads cited:

| Head | Branch | State |
|---|---|---|
| `ee6867a11` | `feat/lb2-projects-tabs-20260926` (LB-2, PR #3530) | open, not on main |
| `2be3e0d1b` | `fix/audit-wave5-c2-export` (B0 and the wave-5 resolvers) | unmerged |
| `6fcda87c5` | `fix/voice-offloop-20260927` (LB-12) | in flight |
| `2adfe06a8` | `fix/retire-source-merge-20260927` (LB-33, PR #3534) | open |
| `d3143a491` | `design/retire-source-merge-ui-20260927` (lane A's source-merge client removal, PR #3533) | open |
| `7d784d826` | `fix/public-opportunities-takedown-20260927` (LB-34, PR #3531) | open |
| `c0845e327` | `fix/reformat-repair-20260926` (the reformat lineage, PR #3527) | open |
| `f87a4db64` | `feat/companion-spr03` (the companion stack; grounding v2's `0af7a2b7b` is its ancestor) | unmerged |
| `88da9072b` | `fix/w5-mcp-hardening-20260923` (the MCP hardening) | unmerged |

**Inputs.**
- `THREAD-CONTRACT.md` Part 1, signed rev 8.10.
- `cockpit/GROUNDING-LANE-B-R18-R40-2026-09-26.md` (v2): packages LB-12 to LB-35 and its §5 "THREAD-CONTRACT rev 9 items (Part 1)", the primary checklist.
- `cockpit/CROSSCHECK-R18-R40-LANE-A-VS-B-2026-09-27.md`: the settled names and the seam gaps.
- `cockpit/LB-35-SPEC-2026-09-27.md`: the non-book reader contract (D1–D5, Q1–Q12).
- `DECISIONS.md`: "Operator rulings, 2026-09-26 (second set)", rulings 1–21 (binding); "Delegated decisions, 2026-09-27", D-P, D-A and D-M; "Naming and gates reconciled after lane B's cross-check, 2026-09-27"; and lane A's defaults 1–8.
- `THREAD-CONTRACT-REV9-PART2-DRAFT.md`: lane A's Part 2 draft. Its §C lists eight requests of Part 1; Appendix A answers each one.
- The shapes both lanes settled in conversation on 2026-09-27 (binding): every data name is `reading`, and only `interest` is a new kind; `origin.output_anchor`; `?parent_thread_id=`; the atomic seeded `POST /projects`; Speak → Writing on the Speak side; the names `purpose`, `ordinal`, `?product=`, `POST /threads/merge/draft`, `question`, `antiek://threads/{id}`, `useVoiceInput` and one registry transfers route; the dialogue scope union; `at`; the merge-session log; the server-minted `voice_capture_event_id`; the roster's spawning fields; `DELETE /projects/{id}/products/{product}`, `link_back`, `POST /investigations/{id}/attach` and the output-anchor fixture path; LB-33's 410 body and the Q-B1 rule; LB-35 at the rev-7 W1 row's level; the `companion_document` reformat source; and LB-26's `evidence_index` re-key.
- Four cluster drafts (registry: §1.0, §1.5, §1.5a; threads: §1.2–§1.4b, §1.8; merge and agents: §1.10, §1.12a; spend, reading and Speak: §1.11, §1.11a, §1.12, §1.13, §1.14, §1.18a, §1.20) and the critic's fix list over them (blockers B1–B7, majors M1–M25, minors m1–m12, citation items c1–c4). Appendix E records how each fix was applied.

**Citations (binding from rev 8.8).**
- A code citation is `path@<commit>` plus a quoted anchor phrase, never a bare line number. Every anchor here was checked by script to occur exactly once in that file at that commit. Paths are repo-relative and complete.
- A contract citation is `THREAD-CONTRACT.md@<commit> §x ("anchor")`, pinned at `e39840224`, and each anchor occurs once in that file.
- A decision is cited by its `DECISIONS.md` heading and number.
- INFERRED marks a fact that could not be read, and UNVERIFIED marks one that could not be checked at all.

## Change summary

| Section | Change (rev 9) | Package | Source |
|---|---|---|---|
| §1.0 | "Books" is a label; every data value stays `reading`. New words (shelf, presence, seed, lane, session, merge draft, transfer, and more). T11 citation replaced by rulings 4, 7 and 10. | LB-17 | ruling 1; D-P; naming reconciliation |
| §1.0a | NEW wire conventions: one error-body rule, citation markers as a transport encoding, the outbox API names, idempotency | all | critic M3, m3, m10 |
| §1.2 | `ThreadSummary` gains `origin`, `scope`, `participants[]`, `dialogue_kind`, `project_ids[]`, `agent`, `merge_ids[]`. Membership is the authority for `?project_id=`. New filters `document_ids[]`, `participant`, `agent`, `dialogue_kind`, `parent_thread_id`. One thread predicate. Dialogues start with `thread.dialogue_started`. | LB-17, LB-20, LB-21, LB-24, LB-26 | D-P, D-A, D-M; rulings 2, 3 |
| §1.3 | `BranchOrigin` gains `output_anchor`, `purpose` and `target`; `via: agent_call` reserved. Branch from output. The launch body gains `project_id`, `title`, `origin`, `kind`, `input` and `context_items`. | LB-19, LB-20 | rulings 2, 3 |
| §1.4, §1.4b | NEW `OutputAnchor` over agent output, validated by the one NFC validator, with the served-only quote rule and the shared fixture | LB-19 | ruling 3; lane A C6 |
| §1.4c | NEW `html-text/v1`, the canonical text projection of an HTML body. Pasted byte-exact from the section-level co-signed pin (SHA-256 `a99c4950a568…`, fixture `41e4825d3`), with lane B's notes outside it | Astra's A03 (projector, chunks, anchor map); lane A F8/§A3b | lane A pin; Astra co-sign; backend INBOX |
| §1.15 | NEW A06: private authored content (`user_authored_private`): the re-attestation matrix, token resolution, the capability route, "disable until confirmed", and the retrieval-denylist precondition | Astra's A06, with #3415's retained block | operator ruling 2026-09-27 (A06 gating); backend INBOX 00:10Z, 00:20Z (as narrowed 00:40Z), 00:30Z (as corrected 00:40Z); Astra's four round-2 amendments (specs/antiek-backend-forensic-20260927/children/private-authored-content/spec-review-round2.md and spec-review-resolution.md) |
| §1.5 | The registry per D-P: `home_product`, `products[]`, `kind: interest`, the seeded atomic create, presence reads, the shelf, leave, the ruling-11 link, typed `project.*` events, one member-table rebuild | LB-17 | D-P; rulings 4, 10, 11, 12 |
| §1.5a | NEW transfers T1–T6, candidates with `offers`, the lineage record, the seam events, Speak → Writing on the Speak side | LB-18 | D-P; rulings 4, 11; lane A C8 |
| §1.6 | Tab nodes gain `transient` and `branch_origin.output_anchor`; tab writes in a mode not in `products[]` answer `409 product_absent` | LB-17, LB-19 | D-P; S15 |
| §1.7 | The broadcast list, consolidated | all | critic m11 |
| §1.8 | Tier 0 is NEW `POST /investigations/{id}/ask` on dialogue threads: sessions per (agent, project), groups in one voice, receipts, `at`, Converse, the turn bound, book ask scope | LB-21, LB-22, LB-27 | D-A; rulings 14, 16, 18, 20 |
| §1.9 | `ContextItem.kind` gains `project`; one resolver for launch, ask and estimate | LB-21 | grounding item 9 |
| §1.10 | Merge rewritten per D-M: the merge-session log, estimate, a paid draft, free revisions, a zero-dispatch commit into a new thread or an agent | LB-24a, LB-25, LB-24 | D-M |
| §1.11 | Speak testimony gated at serve time, `422 speak_publish_required`, from-investigation repairs, source merge retired | LB-15, LB-18, LB-33, LB-33b | O-12 fallback; T6; Q-B1 |
| §1.11a | Monologue and notebook write-up sources, listening budgets, one commit per chapter, audio rendered by the server, voice input; talking is built | LB-30, LB-31 | rulings 13, 15, 17, 18 |
| §1.12 | The Books notebook lens, node-keyed entry ids, `merge_ids[]`, the MCP resources, twin notes only through promotion | LB-29, LB-26 | ruling 13; D-A |
| §1.12a | NEW agents: a promoted thread, charter with compare-and-set, membership with `reach: attached_only`, the seven-step assembler, attach, receipts, the `evidence_index` re-key; agents act only by answering | LB-26 | D-A |
| §1.13 | Five spend classes, `record_dispatch`, attribution on every ledger operation, per-dispatch halt scope, unified `/flags`, the roster, new inbox kinds | LB-23, LB-32, LB-28 | D-P tightening 3; D4; O-11, O-16 fallbacks |
| §1.14 | NEW `GET /reading/continue`; the 409 body; listening positions | LB-14, LB-31 | ruling 15 |
| §1.15 | One consolidated owner-scope list and hole list; one rule for missing and foreign references | all | critic M20, m2 |
| §1.16 | One bump table (v41/v42 order), every event in its bump, one server-owned event list | all | critic M16, B7 |
| §1.17 | Q-A5's answer narrows to the ruling-11 link and T6 | LB-17 | ruling 11 |
| §1.18, §1.18a | One delivery order for LB-12 to LB-35; non-book documents in the reader at the rev-7 W1 row's level, per the LB-35 spec | all; LB-35 | grounding item 19; ruling 12 |
| §1.19 | NEW voice input and speech output: transcribe persists nothing, the server mints the capture at submit, the TTS `source` gate | LB-12, LB-23 | rulings 14, 17 |
| §1.20 | NEW Speak read models: GETs that never write, counts that are `null` and never `0`, takedowns on every public listing | LB-15, LB-16, LB-34 | rulings 5, 6 |

---

## Part 1, rev 9 (lane B)

### 1.0 Vocabulary (binding on code, routes and event names): rev 9 deltas

Every rev-8 row that is not listed here stands unchanged.

**Books is a label, and `reading` is the data name (rev 9; ruling 1; DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27").**
- "Books" is the user-facing label of the reading mode and product. It appears on the rail, Home, the key sheet, the Library heading and "Your books".
- The client taxonomy keeps its id and changes only the label, which today is `apps/reading/src/shell/workflowTaxonomy.ts@b41f4ec9b` ("label: \"Read\"").
- Every data name stays `reading`:
  - the mode key (`project_tabs.mothership`);
  - the `home_product` and `products[]` values;
  - the `?product=` value;
  - the book-shaped `kind`;
  - the companion `lens`.
- Part 1 introduces no `books` value and no alias anywhere (lane A's request C7).
- The SPA path `/books` is only a brand-alias redirect (ruling 1).
- The existing API prefix `/books*` serves book assets (`interfaces/research/api/books.py@b41f4ec9b` ("async def get_book(document_id: str) -> BookDetail:")). It is unrelated to the label and unchanged.
- Code ids, `/library`, `/read/:documentId` and ⌘E stay.

**Rows changed (rev 9).**

| Word | Means | Never used for |
|---|---|---|
| cockpit (rev 7, C1; rev 9) | The one shell. Research, writing and reading are its modes. Home, Speak, Converse and Autonomous are doors outside the mode cycle (rulings 4, 7 and 10; lane-A default 3). Rev 7 cited T11 (THREAD-CONTRACT.md@e39840224 §1.0 ("Speak and Home are doors outside the mode cycle (T11)")), but T11 was a recommendation that DECISIONS never recorded as a ruling. | A second shell per mode, or a tab forest for a door (T9). In code and routes the mode key stays `mothership` (`/projects/{id}/tabs/{mothership}`). It names a mode, never the platform. |
| project (rev 9) | The data noun for one registry row. It is one identity across the three modes, present in the modes that its `products[]` lists (D-P; §1.5). | Speak's `interview_projects` (`substrate/graph/schema.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS interview_projects")), which is never reused and joins a project only as a `speak_project` link (ruling 4). Also never a per-mode or per-product object (D-P). |
| workstation (rev 9) | A retired UI noun. Lane A's rev-9 Part 2 says "project" (Part 2 draft §A1). | Code names and any new wire field. |
| companion document (rev 7; rev 9) | The derived data. Per project it is the companion tab. The cockpit shows it as the right pane's **Findings** tab (rev 7, C4; S7) and, in the reading mode, as the **Notebook** tab through `lens=reading` (ruling 13). Per evidence document it is the companion rail. | The bare word "companion" in code, which already carries five meanings (Q-A3, §1.12). |
| flag (rev 9) | A flag with `intent: read \| diligence` and a server-derived `actor: {kind: user \| agent, id}` (§1.13). A read flag is a `question.identified`-family event. A diligence flag is a `diligence_queue` row (THREAD-CONTRACT.md@e39840224 §1.13 ("Store for diligence flags (rev 8")). Both list through `GET /flags` (LB-32). | Feature flags or `*.flagged` actions. |

**Rows added (rev 9).**

| Word | Means | Never used for |
|---|---|---|
| Books | The user-facing label of the reading mode and product (ruling 1). | Any data value. No mode key, `home_product`, `products[]`, `kind`, `lens`, `?product=` value or event name is `books`. |
| `reading` (as data) | The one data name of the Books mode and product: the mode key, a `home_product` or `products[]` value, and `kind: reading`. | — |
| book project | `kind: reading`: a project born from one book. Its `primary_document_id` is required and must open in the reader (§1.5). | A book entity of its own. The book is its document; the project is a registry row. |
| interest project (ruling 12) | `kind: interest`: a Books project with a shelf and no primary document ("Airplanes"). | A `reading` project that is missing its primary. |
| home product (D-P) | `home_product`: the product a project was born in. It is immutable, and it picks the create page and the default mode. | A filter. No home lists by it. |
| presence (D-P) | A mode listed in a project's `products[]`. Homes, `?product=`, `mode.cycle` and the transfer offers read it. | Membership, and `home_product`. |
| seed | The first content that a create writes with the row, in one transaction (§1.5). | A second, product-native create call. |
| leave (a product) | Removing a mode from `products[]` (`DELETE /projects/{id}/products/{product}`, `project.product_left`). The mode's tree and members are kept. | Archive (`archived_at`, project-wide). |
| shelf | A Books project's ordered document members: the primary document first, then `member_role: shelf` rows by `ordinal`, books before non-books (ruling 12). | A copy of documents, or anything an agent writes. Agents only propose. |
| context member | A `member_role: context` row. It is one of: a document kept from a rabbit hole ("Keep"), an insight carried by a partial transfer, or a project linked by ruling 11. | A shelf item. |
| linked project (ruling 11) | A `project` context member plus its link back, so a book keeps its own id beside a research project. | A transfer, or a promotion in place. |
| transient tab | A left tab in the reading mode that lane A opened from an agent's answer ref, marked `transient: true` (§1.6, §1.12a). Keep makes its document a context member. | A member, or a tab the server writes. |
| Notebook (ruling 13) | The reading-mode view of the companion document. | The TipTap notebooks, which become "My notes". |
| agent (D-A) | A promoted thread, identified by its `thread_id`. Its charter is the derived asset `agent:<thread_id>`. In rev 9 it acts only by answering (§1.12a). | A store of its own, or an `agent_id` distinct from a thread id. |
| session (D-A) | The one dialogue thread per (owner, agent, project) that holds that project's turns with the agent. | The agent itself. |
| lane | A branch subtree (§1.3). | An entity. |
| merge session | The append-only `merge-<uuid4 hex>` log that holds one merge attempt's drafts and its commit record (§1.10). | A thread. It is never listed and never a parent, member or target. |
| merge draft (D-M) | A model-written, answer-shaped synthesis over a preview, adopted verbatim at commit (§1.10). | A §1.11a derivation. |
| transfer (D-P) | A presence append, or member references placed in another project, recorded as `project.transferred` (§1.5a). | A copy. |
| Converse (rulings 7, 16) | A door whose data is a plain dialogue scoped to a registry project. | A Speak surface. |
| monologue (ruling 15) | A §1.11a derivation with a listening budget. | — |
| voice input (ruling 17) | `input.modality` on a launch, ask or reformat. Only the submitted transcript is kept (§1.19). | Raw audio. |
| speak project (ruling 4) | An `interview_projects` row under `/speak`. It joins the registry only through `member_kind: speak_project`. | A §1.5 registry project, a `home_product` or a seed. |
| managed (ruling 10; D-P tightening 1) | `member_role: managed` on a thread's membership: the unit of the Autonomous door. "Autonomous" names only the door. | A product value, a mode, a create seed or a transfer target. |
| private authored content (A06) | `content_class: user_authored_private`: the operator's own notes and drafts. Owner-readable, never public-servable and never ad-eligible (§1.15). | The legacy `user_owned` class, which main serves publicly and which is never adopted into this one. |

**Persisted names that are never renamed (rev 9; ruling 1).**
- `/read/:documentId` (`apps/reading/src/App.tsx@b41f4ec9b` ("<Route path=\"/read/:documentId\""))
- `read.*` events and `read-<doc>` ids (§1.3)
- `personal_reading` (`interfaces/research/api/upload_routes.py@b41f4ec9b` ("_ATTESTATIONS: tuple[str, ...] = (\"user_owned\", \"personal_reading\")"))
- `reading_state` (`substrate/books/reading_state.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS reading_state"))
- `book_assets` (`substrate/graph/schema.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS book_assets ("))
- `anchored_highlights` (`substrate/books/highlights/schema.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS anchored_highlights"))
- the analytics event `reading_research_spun` (`apps/reading/src/lib/analytics.ts@b41f4ec9b` ("reading_research_spun: {"))
- the mode key `reading` (`substrate/projects/schema.py@ee6867a11` ("MOTHERSHIPS: tuple[str, ...] = (\"research\", \"writing\", \"reading\")"))

**Citation fix (rev 9).** The rev-7 "project" row cited `interview_projects` by a line range that has since drifted. Rev 9 cites it by anchor, as in the row above, and the rev-9 text carries no bare line numbers.

### 1.0a Wire conventions (NEW, rev 9)

These apply to every rule below.

**Error bodies (rev 9; one rule for all of Part 1).**
- Every refusal that rev 9 adds or changes answers top-level JSON with a `reason`, the code a client narrows on, as §1.6's error bodies already do (THREAD-CONTRACT.md@e39840224 §1.6 ("**Error bodies** are top-level JSON")).
- Where a reason defines one, `detail` is a closed sub-code listed with that reason, for example `{reason: "seed_invalid", detail: "product_invalid", field: "home_product"}`. One reason defines a structured `detail` instead: `draft_stale` (§1.10). Other fields (`ref`, `field`, `current`, `project_id`, …) are listed with each refusal.
- A refusal that already answers FastAPI's `{"detail": "<code>"}` keeps that string and gains `reason` equal to it. The change is additive, so existing callers keep working. This covers LB-2's refusals, B0's `422 parent_investigation_not_found`, and the existing string codes of `POST /investigations`, `/books/{id}/ask`, `/events/typed`, `/voice/transcribe` and `/speech/tts`.
- Rev 9 answers no `{"detail": {reason}}` wrapper, on new routes or existing ones.
- An unknown field in a rev-9 body is refused with the route's body code (for example `422 project_body_invalid`, or `422 {reason: ask_invalid, detail: unknown_field}`). It is never silently ignored.

**Model citation markers (rev 9).** A model cites by inline markers: `[[n]]` in a turn (§1.8) and `[[ref:<item_id>]]` in a merge draft (§1.10). The markers are a transport encoding between the model, or an editor, and the server:
- The server resolves them, strips them (each with one preceding space), and normalizes the text with `normalize_node_text` (§1.4b).
- Served text never contains a marker. Citations travel in span or sentence records whose `start` and `end` are Unicode scalar offsets into the served text, the §1.4b offset unit.
- The one place a marked form crosses the wire is the merge draft's edit encoding: `edit_text` on the read and `synthesis_text` on `revise` (§1.10).

**The outbox (rev 9).** "Through the outbox" means inside `eventful_transaction` with `enqueue_event` (`substrate/write/event_outbox.py@b41f4ec9b` ("def enqueue_event(")), followed after commit by delivery with `dispatch_pending_best_effort`. `write_event_outbox` is the table, not the API.
- `enqueue_event` refuses an `operation_id` or `event_id` reused with different bytes (`substrate/write/event_outbox.py@b41f4ec9b` ("outbox identity was reused with different event bytes")).
- So every idempotent flow below reads its own request record first, and never relies on that refusal to detect a replay.

**Idempotency (rev 9).** Every rev-9 mutation is idempotent in one of three ways:
- by an `idempotency_key` bound to a request identity: a repeat replays the first answer, and the same key with another identity answers `409 idempotency_conflict`;
- by a natural key, where a route says so (the members route, §1.5);
- by a compare-and-set version (the tab PUT, §1.6; the shelf PUT, §1.5; the charter PATCH, §1.12a).

**Owners and threads.** Missing and foreign references follow one rule (§1.15). Which log is a thread follows one predicate (§1.2).

### 1.2 Thread: rev 9 deltas

**Ground truth.** B0 is not an ancestor of `origin/main`, and main is at `EVENT_SCHEMA_VERSION` 40 (`substrate/schemas/events.py@b41f4ec9b` ("EVENT_SCHEMA_VERSION: int = 40")). B0 and the wave-5 resolvers are on the unmerged c2-export branch at 41 (`substrate/schemas/events.py@2be3e0d1b` ("EVENT_SCHEMA_VERSION: int = 41")). §1.16 gives the bump order.

**`ThreadSummary` gains these fields (rev 9).**

| Field | Source |
|---|---|
| `origin \| null` | The parent's `investigation.branched` event that names this thread. It is null for a thread that was not launched as a branch. Rules below. |
| `scope \| null` | For a `dialogue`, `{project_id} \| {document_id}` from its `thread.dialogue_started` (§1.8). It is null for every other kind, whose project and document are already fields. |
| `participants[]` | For a `dialogue`, the agent thread ids from `thread.dialogue_started`. It is `[]` for a plain dialogue, a book session and every other kind. |
| `dialogue_kind \| null` | Derived for a `dialogue`: `session` (one participant), `group` (two to four), `book` (a `{document_id}` scope), `branched` (a dialogue child of a research thread) or `plain` (otherwise: Converse and plain project dialogues). It is null for every other kind. |
| `project_ids[]` | Derived from membership: every registry project in which the thread has an `investigation` member row of any role, sorted. The start payload's `project_id` is the home project only (D-P). |
| `agent \| null` | §1.12a. Null unless the thread is promoted. |
| `merge_ids[]` | §1.10: every committed merge the thread took part in, as a member, a result or a target, in commit order. |
| `merged_from[]` | Signed NEW (§1.10). |

**One thread predicate (rev 9).** Every route that takes a thread, in its path or its body, asks one server helper, `thread_status(id)`. It answers exactly one of four values, tested in this order:
1. **`not_a_thread`** for an id in a namespace that never holds a thread:
   - `project-<project_id>`, the registry's event logs (§1.5);
   - `merge-<32 hex>`, the merge-session logs (§1.10);
   - the attribution buckets `read-spin`, `__sidecar__`, `__operator__` and `reformat:<generation_id>` (THREAD-CONTRACT.md@e39840224 §1.2 ("attribution buckets and are never listed as threads")).
2. **`absent`** for an id with no stored records at all.
3. **`reserved_only`** for a log that holds only B0's reservation record (§1.3).
4. **`thread`** for a log whose first start-family event is `investigation.start_requested`, `thread.dialogue_started` or `reformat.requested`; for a `read-<document_id>` log (a `reading` thread); and for a legacy log that the list's marker rule admits (`interfaces/research/api/app.py@b41f4ec9b` ("investigation_markers = {")). Rev 9 adds `thread.dialogue_started` and `reformat.requested` to that marker set, so a dialogue or reformat thread whose id does not start with `inv-` is listed.

Any other log is `not_a_thread`. A client-minted `investigation_id` in a reserved namespace (`project-`, `merge-`, `read-`, `reformat:` or a leading `__`) is refused before anything is written (§1.3 step 1, `investigation_id_reserved`).

The predicate is used everywhere a thread is named:
- `GET /investigations/{id}` answers `404 {reason: not_found}` unless the id is a `thread`. This is red today: the route answers `200 {status: "not_found"}` for an id with no rows and reads any log with rows as a thread (`interfaces/research/api/app.py@b41f4ec9b` ("Distinguishes ``not_found`` (no events at all)")).
- `GET /investigations` lists only `thread` logs. The `.jsonl` and sealed `.parquet` enumerations both apply it.
- The §1.3 parent check takes a `thread` only; anything else answers B0's `422 parent_investigation_not_found`.
- §1.10's members and `into_thread_id`, §1.12a's promotion, participants and attach items, and §1.5's seeds, transfers and agent memberships take a `thread` only.
- `POST /events/typed` refuses a client envelope whose `investigation_id` starts with `project-` or `merge-` (§1.16).

**Thread owner (rev 9).** A thread's owner is the `owner_user_id` on its first start-family event.
- A thread whose start carries none is owned by `__operator__`, the single-operator default the registry also uses (`substrate/write/folders.py@b41f4ec9b` ("owner_user_id  TEXT NOT NULL DEFAULT '__operator__',")). This is a pre-multi-user hole (§1.15).
- A `read-<document_id>` thread is keyed per document, not per owner. It is treated as `__operator__`'s, another §1.15 hole.
- How a route answers a thread that is missing or another owner's is §1.15's one rule.

**`origin` (rev 9).** The shape is `{kind, purpose?, anchor? | output_anchor?, target?, via, branch_event_id, parent_thread_id, quote_state: served | withheld | null}`.
- **Its source.**
  - It is read from the parent's log: the earliest `investigation.branched` naming this child that no `investigation.branch_abandoned` cancels.
  - It is never read from the child's own start payload, which carries no quoted text (§1.3).
  - A child named by several live branch events takes the earliest.
- **The served-only quote rule at read (rev 9).** `quote`, `prefix` and `suffix` come back only while the text they quote is served now.
  - An `output_anchor` is judged by its segment's live gate (§1.4b).
  - An `anchor` is judged by the document's live gate (the §1.2 quotation rule).
  - Otherwise the three fields are omitted and `quote_state` is `withheld`.
  - `quote_state` is null when the origin has nothing quotable: a `target`-only origin or a whole-thread origin.
  - When the parent's log does not read in full (`trajectory_read(...).complete` is false, `substrate/event_log/events.py@2be3e0d1b` ("class TrajectoryRead(NamedTuple):")), the quote is withheld, because what the segment stood on is unknown.

**A dialogue starts with its own event (rev 9; replaces THREAD-CONTRACT.md@e39840224 §1.2 ("created by `POST /investigations {kind: dialogue, question?}`")).**
- A dialogue's first event is NEW `thread.dialogue_started` (§1.8). It is never `investigation.start_requested`.
- Loop One runs the nine phases for every start-requested payload it receives (`orchestration/loop_one/orchestrator.py@b41f4ec9b` ("async def handle_investigation_start(event: Event) -> None:")). A dialogue that began with that event would start a paid research run the moment a guard was missed. A distinct start event cannot.
- `kind` comes from the first start-family event:
  - `investigation.start_requested` gives `research`, with the cascade kinds unchanged;
  - `thread.dialogue_started` gives `dialogue`;
  - `reformat.requested` gives `reformat`.
- A dialogue create is not a research start. It takes no ACU precheck or charge.
- `question` is not accepted on a dialogue create. A dialogue's first question is its first ask (§1.8), so a create never dispatches.

**State (rev 9 additions).** The one state helper gains four rules:
- **Dialogue.** A `dialogue` reads `running` while its newest `thread.turn_requested` has no `thread.turn` or `thread.turn_failed` for the same `(turn_id, attempt)`. Otherwise it reads `idle`. A dialogue has no terminal state, like `reading`, and Part 2 §2.4 already renders it that way. A failed turn is an outcome of that turn, never a thread state.
- **Promoted thread.** A promoted thread (§1.12a) reads `idle` when nothing of its own runs, never `done`.
- **Merged thread.** A thread whose start carries `merge_id` (§1.10) reads `done` once its start event is delivered, never `queued` or `running`, because it has no run of its own. No `investigation.completed` is written for it.
- **Pending merge.** A thread that a committed merge names but whose record has not yet been delivered reads `merge_pending(thread_id)`. The rev-3 `merge_failed` projection is retired, because every merge refusal happens before the commit transaction (§1.10).

**`no_record` (rev 9).** In the children listing and the project listing below, a thread that a live branch or a member row names but that has no stored log reads `state: no_record`, with every other derived field null. This is §1.3's unresolved dependency, shown rather than dropped. An unfiltered list enumerates stored logs, so `no_record` never appears there.

**Counts (rev 9 additions to THREAD-CONTRACT.md@e39840224 §1.2 ("Counts (answers the audit's claim-count gap)")).**
- **A dialogue.** `claim_count` and `source_count` stay defined over retrieval events, so a dialogue with a complete log reads a known `0`. Its evidence is on each turn's `answer.provenance` and context receipt (§1.8).
- **A merged thread.** The accepted draft is its first outcome:
  - `claim_count` is the length of the accepted draft's `claims[]`, plus the signed count over the thread's own `evidence.retrieve.delivered` events.
  - `source_count` is the number of distinct documents that the draft's `cited_refs` and the thread's own claim pointers resolve to.
  - Either is `null`, never `0`, when `trajectory_read` reports the session log or the thread's own log incomplete.
- **An agent that received a `thread.merged_in`** keeps its own counts. A merge into an agent is an attachment (D-M), not claims the agent made. Part 2's "Knows: n threads · m merges" chip reads `merged_from[]` and `merge_ids[]` instead.

**Endpoints (rev 9 deltas).**
- **`GET /investigations?project_id=<P>` (rev 9; D-P).** Membership is the authority.
  - It lists the caller's threads that have an `investigation` member row in P, of any role.
  - A start payload's `project_id` alone never lists a thread. A launch, a dialogue create and a merge commit each write the membership row (§1.3, §1.8, §1.10).
  - A member row whose log is `absent` (a launch whose start failed after its membership was written, §1.3) lists as a `no_record` row, never dropped.
  - **Legacy adoption.** When P is `kind: reading` or `kind: interest`, the list also includes legacy threads (no start `project_id`, no membership anywhere) that grounded in, opened or were filed on one of P's primary, shelf or context documents, by the `document_ids[]` rule below. No other kind adopts.
- **`GET /investigations?document_ids[]=<d>…` (rev 9).** It narrows to threads that grounded in, opened or were filed on any listed document, at most 1,000 ids:
  - **grounded in:** a retrieval claim's chunk or edge pointer resolves to the document, as §1.2 resolves `source_count`;
  - **opened:** the envelope `document_id`, or a passage link through `researches_for_passage` (the signed `document_id` filter);
  - **filed on:** `documents.investigation_id` filing.
- **The Books lens** (Part 2 draft §B8) is `?project_id=P&document_ids[]=<P's primary, shelf and context documents>`. It uses the same document set as the Notebook's thread set (§1.12). A thread off that set is hidden in the reading mode and stays visible in Research.
- **`GET /investigations?parent_thread_id=<id>`** lists a parent's children. The route takes only `limit` and `status` on main (`interfaces/research/api/app.py@b41f4ec9b` ("status_filter: Annotated[")).
  1. Rows are limited to the caller's threads. A parent that is not the caller's lists nothing.
  2. Children come from the parent's `investigation.branched` events in trajectory order: the sealed Parquet snapshot first, then the JSONL tail, as `trajectory_read` reads them. A child is listed once, at its earliest live branch.
  3. A branch that `investigation.branch_abandoned` cancels, matched by `branch_event_id`, is not listed. The abandonment is the proof that the child never started (THREAD-CONTRACT.md@e39840224 §1.3 ("Launch identity and abandonment (rev 3")).
  4. A parent whose trajectory predates B0 also lists the children that the legacy scan finds (THREAD-CONTRACT.md@e39840224 §1.3 ("Legacy lineage (rev 3)")). They come after the branched children, ordered by their start event's `emitted_at`, with `origin: null`.
  5. Each row is a full `ThreadSummary` with `origin`. A child with no stored log is the `no_record` row.
  6. `limit` applies to that order: 1 to 500, default 50, as today. The `kind`, `state` and `project_id` filters compose with it.
- **`?kind=dialogue`** lists dialogues. **`?dialogue_kind=plain|session|group|branched|book`** narrows them; Converse's past sessions are `?kind=dialogue&dialogue_kind=plain&project_id=`. **`?participant=<agent_thread_id>`** narrows to sessions that include that agent. **`?agent=true`** lists promoted threads (§1.12a).
- **`GET /investigations/{id}/outputs`** is NEW (§1.4b). **`GET /investigations/{id}/turns`** is NEW (§1.8). **`GET /investigations/{id}/context?project_id=`** is NEW (§1.12a).
- **`GET /investigations/{id}`** carries the same new fields as the list rows.
- **Owner scope.** Every rev-9 filter returns only the caller's threads, by the thread-owner rule above. The unfiltered list stays a pre-multi-user hole (§1.15).

**Agent tab kinds (rev 9 text for THREAD-CONTRACT.md@e39840224 §1.2 ("Agent tab kinds (rev 7; S2)")).**
- **dialogue:** a `dialogue` thread, created by `POST /investigations {kind: dialogue, scope, participants?[], title?}` (§1.8), with no research run. Its log holds only these events: `thread.dialogue_started`, `thread.turn_requested`, `thread.turn`, `thread.turn_failed`, `answer.provenance`, `thread.context_receipt` and `voice.captured`.
- **island:** a `research` thread spawned from a selection. The selection may now be in agent output (`origin.output_anchor`, §1.4b).
- An agent tab in project P holds P's session thread for that agent (§1.12a; T8 as membership).

### 1.3 Branch: rev 9 deltas

**`BranchOrigin` gains three fields (rev 9).** B0's payload (`substrate/schemas/events.py@2be3e0d1b` ("class BranchOrigin(_PayloadBase):")) holds only `{kind, document_id?, anchor?}`, and its kind set is closed (`kind: Literal["footnote", "reference", "citation", "selection", "research", "manual"]`).
```
BranchOrigin {
  kind: footnote | reference | citation | selection | research | manual,  // unchanged
  document_id?, anchor?,            // unchanged: a document passage (§1.4)
  output_anchor?,                   // NEW: a passage of a thread's output (§1.4b)
  purpose?: harden | chase | ask,   // NEW
  target?: {insight_id} | {question_id}   // NEW
}
```
- For `kind: selection`, exactly one of `anchor` and `output_anchor` is set.
- `output_anchor` requires `kind: selection`, a null `document_id` and a `purpose`.
- `purpose` may also accompany a document `anchor`, for an `ask` from a book passage (§1.8). Only an output branch requires it.
- The rules for `target` are under "Target" below.

**`via` (rev 9).**
- It gains `agent_call`, **reserved**. No rev-9 route writes it, because agents take no server-side actions in rev 9 (§1.12a, "What an agent can do"). It rides B0's payload now because adding it later costs a second schema bump. A later revision that defines an agent launch surface (with LB-10's claim-then-spawn) gives it a writer.
- `POST /investigations` records `via: chase` for a research child, as B0 already does (`interfaces/research/api/app.py@2be3e0d1b` ("branch_via: Literal[\"chase\", \"reserved_launch\"] = \"chase\"")). It records `via: api` for a dialogue child.

**The payload docstring (rev 9).** B0's `InvestigationBranchedPayload` docstring says that a reader who finds a branch "knows the child ran" (`substrate/schemas/events.py@2be3e0d1b` ("knows the child ran")). That contradicts THREAD-CONTRACT.md@e39840224 §1.3 ("What a branch means (rev 2 correction)"). The same change rewrites it: a branch is a durable dependency, and whether the child ran is recorded only in the child's own log.

**Timing (rev 9, time-critical).**
- These fields change B0's payload, and `_PayloadBase` forbids extra fields (`substrate/schemas/events.py@b41f4ec9b` ("``extra='forbid'`` is deliberate")), so nothing can ride along informally.
- They therefore land on the c2-export branch before it merges, so that B0 ships as one bump, whatever number it takes at merge (§1.16). If they miss that merge, they cost a second bump.

#### Branch from agent output (rev 9; R18, R19; rulings 2 and 3)

**The request.** `POST /investigations` is EXTENDed. `InvestigationStartRequest` has no `origin`, `kind`, `continue_from_parent`, `context_items`, `input`, `project_id` or `title` today (`interfaces/research/api/app.py@b41f4ec9b` ("class InvestigationStartRequest(BaseModel):")).
```
{
  question,                    // research: required, min 3 (unchanged); dialogue: must be absent
  kind?: research | dialogue,  // default research
  parent_investigation_id,     // required when origin is present
  origin?: BranchOrigin,
  investigation_id,            // client-minted; required on an output branch (the idempotency handle)
  continue_from_parent?: bool, // tier 1; on an output branch it is true, and false is refused
  context_items?: ContextItem[],  // §1.9
  input?: Input,               // §1.19
  project_id?,                 // NEW (signed NEW start field, §1.2): the home project; writes membership
  title?,                      // NEW (signed NEW start field): 1..200 scalars; defaults to the question
  scope?: {project_id} | {document_id},  // dialogue only (§1.8)
  model_choice?, operation_id? // unchanged: owner-model roots only (O-3, below)
}
```

**The response (rev 9).** `InvestigationStartResponse` (`interfaces/research/api/app.py@b41f4ec9b` ("class InvestigationStartResponse(BaseModel):")) gains three fields:
- `thread_id`, equal to `investigation_id`;
- `branch_event_id | null`;
- `voice_capture_event_id | null` (§1.19).

**Validation order, before `record_branch` (rev 9).** Each step refuses with nothing written and nothing charged. A refused request never writes a branch.
1. **Body.** A malformed or inconsistent body answers `422 {reason: launch_invalid, detail}`. `detail` is one of:
   - `origin_without_parent`
   - `investigation_id_required`
   - `investigation_id_reserved`: a client-minted id in a reserved namespace (§1.2)
   - `purpose_required`
   - `purpose_kind_mismatch`: `ask` needs `kind: dialogue`, and `harden` and `chase` need `kind: research`
   - `question_on_dialogue`
   - `spawn_context_with_output_anchor`
   - `continue_required`
   - `chase_mode_not_allowed`
   - `input` (§1.19)
2. **Parent.** The parent must be a `thread` (§1.2) and the caller's. Otherwise the answer is `422 parent_investigation_not_found`, as B0 already answers (`interfaces/research/api/app.py@2be3e0d1b` ("parent_stored = trajectory_read(effective_parent).stored")). Another owner's parent gets the same answer as a missing one.
3. **Project.** A `project_id` must name the caller's registry project. Otherwise `404 {reason: project_not_found}`. No presence is required: a launch from a Books project is a member of it whatever its modes.
4. **Anchor thread.** `output_anchor.thread_id` must equal the parent. Otherwise `422 {reason: output_anchor_invalid, detail: thread_mismatch}`.
5. **Event.** `output_anchor.event_id` must be in the parent's trajectory. Otherwise `409 {reason: output_anchor_stale, detail: event_missing}`.
6. **Path.** The path must be in the closed set for that event's `action_type` (§1.4b). Otherwise `422 {reason: output_anchor_invalid, detail: path}`.
7. **Hash.** The recomputed NFC segment hash must equal `segment_sha256`. Otherwise `409 {reason: output_anchor_stale, detail: segment_changed}`.
8. **Offsets and quote.** The §1.4b validator runs next. It refuses with `422 {reason: output_anchor_invalid, detail: offsets | selection | quote | prefix | suffix | normalization | segment_id | node_id}`.
9. **Served.** The segment's live gate must be `served`. Otherwise `422 {reason: output_not_servable, detail: <the segment's GatedText.reason>}`.
10. **Target.** See "Target" below. A failure is `422 {reason: launch_invalid, detail: target_mismatch | target_not_applicable | target_not_in_parent}`.
11. **Remote parent (INFERRED need).** A parent whose log is written off-host as a remote-exec cascade leaf, and has not been funneled, answers `409 {reason: parent_log_remote}`.
12. **Owner model.** An owner-model launch with a parent keeps answering `422 owner_model_root_required` until O-3 is ruled (`interfaces/research/api/app.py@b41f4ec9b` ("detail=\"owner_model_root_required\"")).

**What is written, in order (rev 9).** After validation, B0's order holds: branch, then charge (research children only), then the child's first event (THREAD-CONTRACT.md@e39840224 §1.3 ("Launch identity and abandonment (rev 3")). Rev 9 places two writes between the charge and the start:
1. **The branch.** The parent receives `investigation.branched {child_investigation_id, via, origin, spawn_context: "", question_id: null}`, written strictly (`substrate/event_log/branches.py@2be3e0d1b` ("def record_branch(")). `origin.output_anchor` holds the validated anchor. The server fills its `quote`, `prefix` and `suffix` from the served segment, and fills its `segment_id` and `node_id`. When the client sent those fields, they were checked equal.
2. **The charge** (research only).
3. **The voice capture,** for a voice `input` (§1.19): `voice.captured` strictly into the child's log, with an event id derived from the child id.
4. **The membership,** when `project_id` is given: one outbox transaction writes the `{investigation, <thread>, null}` member row and `project.members_changed {cause: launch}` (§1.5).
   - It precedes the start, so a started thread is never missing from its project.
   - If the start then fails, the member names a log that is `absent`. `?project_id=` lists it as a `no_record` row, the same unresolved dependency as B0's branch without a child.
   - An exact replay completes the launch and writes nothing twice, because the member row is keyed by `(project, thread)`.
5. **The start.** `investigation.start_requested` for research, or `thread.dialogue_started` for a dialogue. It carries `origin` **without** `quote`, `prefix` or `suffix`, `spawn_context: ""`, `project_id`, `title`, `input` and `voice_capture_event_id`.

B0's own refusals are unchanged: `409 reservation_parent_mismatch`, `409 investigation_id_conflict` and `503 branch_not_recorded`.

**One copy of the words (rev 9).**
- The selection's words exist only as the anchor's `quote`, in the parent's own log, beside the text they quote.
- The child's payload never holds them, so a later takedown is enforced in one place: the read-time gate in §1.2.
- Today the highlight becomes the question itself, and the only withheld guard is in the client (`apps/reading/src/modes/ResearchWorkstation/HighlightToolbar.tsx@b41f4ec9b` ("We refuse rather than spawn on a withheld body")). The server stores whatever `spawn_context` arrives.

**`chase_mode`.** A research child from output records `chase_mode: "off"`, and a request naming any other mode is refused, never silently overridden. HTTP launches already default to off (`substrate/schemas/events.py@b41f4ec9b` ("chase_mode: Literal[\"off\", \"depth\", \"duration\"] = \"off\"")). The rule binds once `chase_mode` joins the request (THREAD-CONTRACT.md@e39840224 §1.13 ("`chase_mode` joins `InvestigationStartRequest`")).

**Broadcast.** After the branch is written, `investigation.branched` is broadcast on the parent's `/ws/events` stream (§1.7). B0 broadcasts only on the chase path.

**The client lineage store.** The `localStorage` lineage (`apps/reading/src/hooks/useInvestigationTree.ts@b41f4ec9b` ("export function recordSpawnRelationship(")) is superseded by `?parent_thread_id=`.

**Loop One on an output branch (rev 9).** Today the start handler builds `InvestigationContext` with no `spawn_context` and no parent pack (`orchestration/loop_one/orchestrator.py@b41f4ec9b` ("parent_investigation_id=req.parent_investigation_id,")). This is EXTENDed for a research child whose start carries `origin.output_anchor` or `continue_from_parent: true`:
- It loads the parent's `RightsGatedPack` (LB-24a, §1.10) through `assemble_context_pack_with_reuse`, budgeted by `reuse_token_budget` (`substrate/context_pack/knowledge_reuse.py@b41f4ec9b` ("def assemble_context_pack_with_reuse(")).
- At run start it resolves the focus segment from the parent's event under the live gate. Served text becomes the focus. A segment that has turned non-served since the branch is left out and recorded as withheld.
- `context_pack.assembled` (`substrate/schemas/events.py@b41f4ec9b` ("class ContextPackAssembledPayload(_PayloadBase):")) lists the parent items and the focus, each with its gate.

**The three purposes (rev 9; ruling 2).**

| `purpose` | What it starts | Spend class (§1.13) | Stops with |
|---|---|---|---|
| `harden` | a research child that tests the selected claim | Research start: the ACU gate, then the run's research budget | `user`, `cancel`, `budget` |
| `chase` | a research child that pursues the selection | the same | the same |
| `ask` | a `dialogue` child with no run (tier 0) | none at create; each turn is conversational (§1.8) | never terminal |

- `purpose` is recorded and listed. In rev 9 it changes no Loop One phase: the operator's `question` frames the child (INFERRED, because no purpose-specific phase exists on main).
- **Flag for diligence** is the fourth verb (ruling 2). It is LB-32's `POST /flags` (§1.13): consented and capped, and never a branch.
  - A flag from output sends the segment's `node_id` as `{insight_id}` (role `insight`) or `{question_id}` (role `open_question`).
  - Rev 9 has no output-anchor flag target. A `thesis` or `component` segment has no `node_id`, so it offers Harden, Chase and Ask, and lane A disables Flag there with that reason.

**Target (rev 9).**
- `{insight_id}` and `{question_id}` name graph nodes. Their ids are content-addressed (`substrate/graph/insight_question.py@b41f4ec9b` ("def insight_node_id(")).
- **With an output anchor on a node segment** (§1.4b), `target` is required. It must name that node, as `insight_id` for role `insight` and `question_id` for role `open_question`.
- **With an output anchor on a `thesis` or `component` segment**, `target` must be absent.
- **Without an anchor** (`origin.kind: research`, launched from an insight or question card), the target must be a node that the parent's trajectory produced, read the way `distill_query` reads it (`roles/note_taker/distill_query.py@b41f4ec9b` ("if ntype in (\"insight\", \"question\") and nid not in seen:")).
- `ask` takes no target.

**Idempotency (rev 9).**
- An output branch requires the client-minted `investigation_id`. Lane A mints one per press and reuses it on every retry.
- An exact replay returns the first start. It writes no second branch, makes no second charge and sends no second broadcast. B0 decides a replay before the branch (`interfaces/research/api/app.py@2be3e0d1b` ("detail=\"investigation_id_conflict\"")).
- The same id with a different body answers `409 investigation_id_conflict`.

**No `hardened` projection in the MVP (rev 9, decided).**
- A harden child's outcome is the child itself. The lane shows its `state`, `stop_reason` and `excerpt` (a `GatedText`).
- A per-claim `supported | contested | inconclusive` would be a model judgement with no typed home and no evidence rule. It waits for a revision that adds a typed verdict to the child's terminal record, with that verdict's own provenance.
- Lane A agrees (Part 2 draft §A3). Reconsider if lane A shows the operator cannot read a harden outcome from the excerpt alone.

**Owner-model parents (O-3, open).** Until O-3 is ruled, an owner-model launch keeps refusing a parent (step 12). Output branches run on the platform lineup with the §1.9 estimate.

**Tier 1 (rev 9 restatement of THREAD-CONTRACT.md@e39840224 §1.8 ("Tier 1 (W2/W3): a follow-up research run with the parent's context.")).**
- `continue_from_parent: true` writes the §1.3 branch.
- Loop One then loads the parent's `RightsGatedPack`, exactly as it does for an output branch but with no focus.
- DRW's unconsumed follow-ups become this path's first caller, as signed.

**Acceptance (red-first).**
- The parent's log holds `investigation.branched` with `origin.output_anchor` and a quote that the server filled in.
- The child's start payload and `spawn_context` hold none of the selection's words. This is red today, because the server copies any client `spawn_context`.
- The child's `context_pack.assembled` lists the served parent items and the focus. This is red on main.
- Three children with distinct purposes list under `?parent_thread_id=` in branch order, each with its origin.
- A branch whose child has no log lists as `no_record`. An abandoned branch is not listed.
- After a takedown turns the segment withheld, `origin.quote_state` reads `withheld` and no quote is returned, although the event still stores it.
- A retry with the same `investigation_id` writes one branch and charges one ACU.
- A harden request with `chase_mode: depth` answers `422 launch_invalid`.
- A target naming a node other than the anchored one answers 422.
- A launch with `project_id` writes one member row and one `project.members_changed {cause: launch}`, before the start event. A replay writes neither again.
- A `project-<id>` or `merge-<hex>` id as `parent_investigation_id` answers `422 parent_investigation_not_found`.

### 1.4 Anchor: rev 9 deltas

- **`BranchAnchor` is unchanged.** It anchors into documents. An output anchor is a separate type (§1.4b), because its text lives in an append-only event: it never drifts and is never remapped. `POST /documents/{id}/anchors/remap` never takes one.
- **Carriers (rev 9; replaces THREAD-CONTRACT.md@e39840224 §1.4 ("The anchor is carried on the start payload")).**
  - `investigation.branched.origin` carries either type.
  - The child's start payload carries either type, without quote fields for an output anchor (§1.3).
  - Tab nodes carry either type, without quote fields for an output anchor (§1.6).
  - Flags carry neither. A flag names node ids (§1.3 "Flag for diligence"; §1.13).

### 1.4b OutputAnchor (NEW, rev 9; R18; ruling 3)

**Why a second anchor type.**
- `BranchAnchor` requires a `document_id`.
- `NodeTextAnchor` requires `quote`, `prefix` and `suffix` (`substrate/feedback/domain.py@b41f4ec9b` ("class NodeTextAnchor:")), so a withheld segment's text would travel in every payload that carries one.
- Lane A's `thread_ref{NodeTextAnchor}` is therefore replaced by `origin.output_anchor` (DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27").

**Type.**
```
OutputAnchor {
  thread_id,          // the thread whose log holds the event (= the branch parent)
  event_id,           // the event whose payload holds the segment
  path,               // JSON Pointer into the payload; closed set below
  segment_id?,        // "<event_id>#<path>"; server-derived; if sent, must match
  segment_sha256,     // sha256, lowercase hex, of the UTF-8 of the normalized segment text
  start, end,         // Unicode scalar offsets into that text, 0 ≤ start < end ≤ length
  selection_sha256,   // sha256, lowercase hex, of the UTF-8 of text[start:end]
  normalization?,     // "unicode-nfc-v1"; absent means the same
  quote?, prefix?, suffix?,  // only where the served-only rule allows (below)
  node_id?            // set exactly when the segment is node-backed; server-derived; if sent, must match
}
```

**Segments: the closed path set (rev 9).** A path not in this table is `422 {reason: output_anchor_invalid, detail: path}`.

| Event (`action_type`) | `path` | `role` | `node_id` | Phase |
|---|---|---|---|---|
| `synthesize.delivered` | `/thesis_summary` | `thesis` | none | 1 |
| `synthesize.delivered` | `/thesis_components/<i>/claim` | `component` | none | 1 |
| `synthesize.delivered` | `/thesis_components/<i>/confidence_basis`, when non-null | `component` | none | 1 |
| `graph.node.inserted`, `node_type: insight` | `/canonical_label` | `insight` | payload `node_id` | 1 |
| `graph.node.inserted`, `node_type: question` | `/canonical_label` | `open_question` | payload `node_id` | 1 |
| `note.emerged` | `/note_text` | `insight` | payload `node_id`, else `insight_node_id(note_text.strip())` | 1 (rev 9 addition) |
| `note.refined` | `/new_text` | the node's role | payload `note_id`, which carries the node id | 1 |
| `read.book_answered` | `/answer` | `answer` | none | 2, after LB-3 |
| `thread.turn` | `/answer/text` | `turn` | none | 2, after LB-3 |

The rows rest on these facts:
- **The thesis rows.** `thesis_summary` and `thesis_components` are on `SynthesizeDeliveredPayload` (`substrate/schemas/events.py@b41f4ec9b` ("thesis_components: list[ThesisComponent] = Field(default_factory=list)")). `claim` and `confidence_basis` are `ThesisComponent`'s only prose fields (`substrate/schemas/events.py@b41f4ec9b` ("confidence_basis: str | None = None")). No other thesis field is a segment in rev 9. The grounding left the field open as `<field>`; the auditor may strike the `confidence_basis` row.
- **The index.** `<i>` matches `0|[1-9][0-9]*` and is below `len(thesis_components)`.
- **`note.refined` names its node through `note_id`.** The note-taker writes the node id into that field (`roles/note_taker/living_note.py@b41f4ec9b` ("NoteRefinedPayload(note_id=note_node_id")). A `note.refined` segment's role comes from the node's type, found in this order:
  1. the same thread's `graph.node.inserted` for that id;
  2. a `note.emerged` for that id, which makes it `insight`;
  3. the live node row.

  If no type resolves, or the type is neither `insight` nor `question`, the event is not a segment.
- **`note.emerged` (rev 9 addition).** The grounding's phase-1 list left it out. It is added because `distill_query` reads it as a durable insight signal (`roles/note_taker/distill_query.py@b41f4ec9b` ("Mini dogfood / projector-off: note.emerged is the durable signal;")). Without it, a note's first version would not be addressable. The auditor may strike this row.
- **Merged threads (rev 9).** A merged thread's accepted draft lives on its merge session's log, not on the thread's own log (§1.10), so no row above addresses it. Merged-thread output is **not selectable in the MVP**: the outputs route lists no segment for the accepted draft. A later revision adds a draft-segment row that resolves the draft through the start event's `accepted_draft` and addresses the served, marker-free text (§1.0a "Model citation markers").

**Segment text and normalization (rev 9).**
- A segment's text is `normalize_node_text` of the string at `path`: CRLF and CR become LF, then NFC (`substrate/feedback/domain.py@b41f4ec9b` ("def normalize_node_text(")).
- When the segment is served, `content.text` is exactly that string. The client renders it verbatim and never normalizes.
- An empty text is not a segment.
- **Offsets count Unicode scalars, not UTF-16 code units.** They are Python `str` indices. A DOM selection must be converted, and the fixture proves the conversion.

**Validation reuses the one validator (rev 9).**
- The output validator builds `NodeTextAnchor(node_id=segment_id, node_text_sha256=segment_sha256, start_scalar=start, end_scalar=end, quote, prefix, suffix)`. Any of the last three that the client omitted are filled from the normalized segment.
- It then calls `validate_node_text_anchor(raw_segment_text, anchor)` (`substrate/feedback/domain.py@b41f4ec9b` ("def validate_node_text_anchor(")).
- That validator already enforces everything this anchor needs:
  - the `unicode-nfc-v1` tag;
  - the hash;
  - `0 ≤ start < end ≤ length` (`substrate/feedback/domain.py@b41f4ec9b` ("if not (0 <= anchor.start_scalar < anchor.end_scalar <= scalar_count):"));
  - the quote;
  - 32-scalar context (`substrate/feedback/domain.py@b41f4ec9b` ("max(0, anchor.start_scalar - 32)")).
- There is no second validator. Its refusals map one-to-one:

  | `validate_node_text_anchor` refusal | Answer |
  |---|---|
  | unsupported normalization | `422 {reason: output_anchor_invalid, detail: normalization}` |
  | node text hash does not match | `409 {reason: output_anchor_stale, detail: segment_changed}` |
  | offsets outside the text | `422 {reason: output_anchor_invalid, detail: offsets}` |
  | quote, prefix or suffix mismatch | `422 {reason: output_anchor_invalid, detail: quote \| prefix \| suffix}` |

- It then adds one check: `selection_sha256` must equal the hash of `text[start:end]`, or the answer is `422 {reason: output_anchor_invalid, detail: selection}`.
- The hash is checked before the offsets, which is the order §1.3 uses.

**The served-only quote rule (rev 9).** A quote of agent output leaves the server only while its segment is served. The rule applies in four places:
1. **At pin.** A branch requires `served` (§1.3 step 9). The quote is stored only in the parent's `investigation.branched`.
2. **At read.** `ThreadSummary.origin` returns the quote only while the segment is served now (§1.2).
3. **On tab rows.** A tab row never holds a quote of agent output (§1.6).
4. **On the outputs route.** The route returns `text_sha256: null` for any segment that is not served, because the hash of a short withheld text can be recovered by guessing.

**Gates by role (rev 9).**
- **`thesis` and `component`: the synthesis rule** (THREAD-CONTRACT.md@e39840224 §1.2 ("**Synthesis.**")). The gate is the wave-5 excerpt gate (`substrate/research_artifact/build_body.py@2be3e0d1b` ("def _excerpt_cleared(")), so the gate is `served` or `withheld`.
  - The gate is computed over everything the thread stood on, so every synthesis segment of a thread shares it.
  - `reason` follows the §1.2 mixed-source precedence. `lineage_unreconciled` applies while §1.3's legacy withhold covers a pre-B0 parent.
  - `origin` is `source`.
- **`insight` and `open_question`: the per-node export chokepoint** (`substrate/research_artifact/build_body.py@2be3e0d1b` ("def _exportable_text(")). The gate is `served`, `cite_only · not_servable` or `cite_only · unresolved`. Every version of a node shares the node's gate.
  - `origin` is `source` when the node resolves to a source.
  - A node that names no source is `operator` only when the event that wrote the segment was emitted with role `operator`. Otherwise it is `unsourced`.
  - The chokepoint serves such nodes as "the operator's own words" (`substrate/research_artifact/build_body.py@2be3e0d1b` ("the operator's own words.")). The label must not claim that for model-distilled text (INFERRED: sourceless research nodes exist).
- **`source_refs`.**
  - A component uses its `supporting_chunk_ids`.
  - The thesis uses the union of its components' refs.
  - A node uses its metadata pointers.
  - Each ref carries `document_id` and an `anchor` when it names a passage (THREAD-CONTRACT.md@e39840224 §1.2 ("Openable document refs (rev 7; S1)")).
- **Phase 2.** A `thread.turn` or `read.book_answered` segment is gated at read by the synthesis criteria over its cited refs (§1.8, "Answers are gated at read").
- **Dependency.** Both gates exist only on c2-export. The route therefore ships after that branch merges (LB-19 depends on it). Until then, main would withhold every synthesis segment.

**Currency and refinement (rev 9).** Events are append-only, so an output anchor never drifts. What changes is which segment is current.
- **A synthesis series.** The segments of the thread's newest `synthesize.delivered` are `current`.
- **A node.**
  - A segment is `current` when its hash equals the hash of the node row's live `canonical_label` and no later segment of that node has the same hash.
  - The newest event is not always the current text. `apply_refinement` writes `note.refined` even when that refinement loses the sequence race and leaves the row unchanged (`roles/note_taker/living_note.py@b41f4ec9b` ("Always writes a")).
  - The live row is the authority (`roles/note_taker/distill_query.py@b41f4ec9b` ("canonical_label`` is the single source of truth")).
  - A node whose row is gone has no current segment.
- **`current_segment_id`.** A non-current segment carries the current segment of its series, or null.
- **"Refined since you branched"** (Part 2 §A2) means the pinned segment reads `current: false` and has a non-null `current_segment_id`. The old anchor still validates against its own event.

**The route (rev 9).** `GET /investigations/{id}/outputs?after=<segment_id>&limit=<n>`
- It is owner-scoped, uses `connect_read` and writes nothing.
- A missing thread, another owner's thread and any id that is not a `thread` (§1.2) all answer `404 {reason: not_found}`.
- **Kinds.**
  - Phase 1 serves `research`, `cascade_session` and `cascade_leaf`.
  - `reformat` answers `422 {reason: use_probe, spans_route: "/derived-assets/{derived_asset_id}/revisions/{revision_id}/spans"}`, with the latest committed revision, or null.
  - `dialogue` and `reading` answer `422 {reason: outputs_not_supported, kind}` until phase 2 (LB-3; ruling 3).
- **The response:**
  ```
  {
    thread_id, kind,
    complete,            // trajectory_read(...).complete
    segments: [{
      segment_id, event_id, path, role, node_id | null,
      emitted_at, current, current_segment_id | null,
      text_sha256 | null,   // null unless content.gate is served
      content: GatedText
    }],
    next_after | null
  }
  ```
- **The order:**
  1. Synthesis segments in the trajectory order of their events. Within an event, the thesis comes first, then components by index, with `claim` before `confidence_basis`.
  2. Insight segments, grouped by node in the order of each node's first appearance (`distill_query`'s order). Within a node, versions run oldest first.
  3. Open-question segments, grouped the same way.
- **Paging.** `limit` is 1 to 500, default 500. `next_after` is null on the last page, including a page that is exactly full: the server reads one row past the page, as §1.6's retired page does.
- **`complete`.** `complete: false` means some stored records did not read. The segments shown are real, but others may be missing. Lane A says so rather than implying the list is whole.
- **Probe.** For an unauthenticated caller, the route answers the API's own JSON 401, never a 404 page or the SPA's HTML.

**The shared fixture (rev 9; lane A's request C6).**
- **Path.** `apps/reading/src/lib/api/__fixtures__/output_anchor_nfc_v1.json`, agreed with lane A on 2026-09-27. It sits beside #3530's `projectTabs.snapshot.json`.
- **How pytest reads it.** Pytest reads the file by path, as #3530 does (`tests/test_project_routes.py@ee6867a11` ("apps/reading/src/lib/api/__fixtures__/projectTabs.snapshot.json")). Vite refuses imports from the repo-root `tests/`.
- **One copy.** Neither lane keeps a copy. A change to the file is a contract change.
- **Shape.** One JSON object:
  - `fixture: "output_anchor_nfc_v1"`, `normalization: "unicode-nfc-v1"` and `context_scalars: 32`;
  - `cases[]`, each with `name`, `raw` (the payload string), `text` (`normalize_node_text(raw)`), `text_sha256`, `scalar_length`, `utf16_length` and `selections[]`;
  - each selection has `start`, `end`, `utf16_start`, `utf16_end`, `quote`, `prefix`, `suffix` and `selection_sha256`;
  - `refusals[]`, each with `name`, `text`, `anchor` and `expect: {status, reason, detail}`.
- **Required cases.** At minimum:
  1. ASCII only.
  2. CRLF and a lone CR in `raw`, each normalized to one LF scalar.
  3. A decomposed `e` + U+0301 that NFC composes, placed before and inside the selection, so `raw` and `text` differ in length.
  4. Astral scalars (U+1D538 and U+1F600) before and inside the selection, so the `utf16_*` offsets differ from the scalar offsets by the surrogate count.
  5. A selection that starts within the first 32 scalars, and one that ends within the last 32.
  6. A prefix of exactly 32 scalars that contains an astral scalar.
  7. `q` + U+0307, which NFC leaves uncomposed.
  8. Hangul conjoining jamo that NFC composes.
  9. A quote sent in NFD, which is accepted because the validator normalizes the quote.
- **Required refusals.**
  - `start = end`;
  - `end` past the length;
  - a quote, prefix or suffix mismatch;
  - normalization `unicode-nfd-v1`;
  - a `selection_sha256` mismatch;
  - a tampered `text_sha256`, which answers 409 `segment_changed`.
- **Lane B's test.** For every case:
  - `normalize_node_text(raw)` equals `text`;
  - the hashes match;
  - the validator accepts every selection, both with and without quote fields;
  - every refusal gives its stated status, reason and detail.
- **Lane A's test.** Its renderer's text equals `text`, its DOM-to-scalar conversion maps each `utf16_*` pair to `start` and `end`, and its SHA-256 over UTF-8 matches.

**Acceptance (red-first).**
- An anchor into a withheld segment answers `422 output_not_servable`.
- A tampered `segment_sha256` answers `409 output_anchor_stale`.
- A refined note yields a new segment. The old anchor still validates and reads `current: false` with a `current_segment_id`.
- A refinement that lost the sequence race is a segment that never reads `current`. This is red against a rule that the newest event wins.
- A reformat thread answers `422 use_probe`.
- `text_sha256` is null on every segment that is not served.
- The fixture's astral case proves that server offsets are scalar offsets.
- A merged thread's outputs list no segment for its accepted draft.

### 1.4c HTML reader text projection, `html-text/v1` (rev 9)

**What it is for.** The one canonical text of an HTML body. Chunk offsets, anchor maps, pins, highlights and probes all count against it. Plain-text bodies keep `unicode-nfc-v1` (§1.4).

1. **Authority.** The projection is computed from the **served body**: the exact UTF-8 string that `/full-text` returns and the reader mounts.
   - **Legacy bodies** served by sanitizer v1.4.0 are projected exactly as served. Hidden intent they already lost is not reconstructed, no bytes are relabelled as another sanitizer version, and nothing stored is rewritten on read.
2. **Parse.** The HTML fragment parsing algorithm is used, with context element `div` (HTML namespace) and the scripting flag **enabled**.
   - **Browser:** the reader sets `div.innerHTML` to the served string.
   - **Python:** an HTML5-conformant fragment parser runs with the same context and flag, for example html5lib `parseFragment(served, container="div", scripting=True)`. It is never stdlib `HTMLParser`.
3. **Excluded subtrees.** `script`, `style`, `template` (whose content is not in the tree), `noscript` and `head`, and any element carrying the `hidden` attribute. No CSS is evaluated.
4. **Text.** Text-node data is taken in document order, with entities decoded by the parser.
   - **Outside `pre`:** each run of ASCII whitespace (U+0020, U+0009, U+000A, U+000D, U+000C) collapses to one U+0020, **across adjacent inline text nodes**.
   - **Inside `pre`:** source whitespace is kept.
   - **U+00A0** is kept.
5. **Block separators.** One generated `\n` separates the content of adjacent blocks.
   - **The block set:** `p h1 h2 h3 h4 h5 h6 li dt dd blockquote pre figcaption caption td th tr div section article header footer aside nav table ul ol dl figure hr br`.
   - **Placement:** a separator is pending until content follows. Two generated separators never touch, and there is none at the start or end. An empty block produces nothing, and a nested block produces one separator per boundary.
   - **Trimming:** only collapsible whitespace adjacent to a generated separator is trimmed. Newlines inside `pre` are content, not separators.
6. **Normalization.** NFC (`unicode-nfc-v1`) is applied **once, to the final assembled string**, never per node.
7. **Offsets.** Offsets are Unicode scalar values over the projection, half-open `[start, end)`.
8. **Digests are distinct concepts.**
   - `NodeTextAnchor.node_text_sha256` stays the sha256 of the **whole normalized chunk**.
   - `TextLocator.text_sha256 = sha256(utf8(projection[start:end]))` is the **selection** digest.
9. **Binding to bytes.**
   - **What anchors carry.** Every persisted anchor on an HTML body carries `text_projection: "html-text/v1"` **and** `served_body_sha256`, the sha256 of the exact served UTF-8 bytes. A sanitizer version alone does not bind bytes. `/full-text` and the anchor map return both values.
   - **On reopen.** An anchor whose `text_projection` or `served_body_sha256` differs from the document's current values re-resolves by quote and context, or reads `unresolved`. It never moves silently.
10. **Chunks (A03).** Each chunk's text is an exact substring of the projection of its document's served body. The anchor map uses that projection, never guarded `raw_text`.
11. **Endpoints (lane A).**
    - **Mapping.** A DOM endpoint (node, UTF-16 offset, in the `div`-context DOM) maps to a projection scalar. A backward user selection is first put in document order.
    - **Snapping.** A start inside dropped whitespace snaps forward past generated separators, and an end snaps backward.
    - **Refusals.** No anchor is written for:
      - an endpoint that splits a composed NFC group (`splits_normalization_group`);
      - an endpoint that splits a surrogate pair (`splits_surrogate_pair`);
      - a collapsed range (`empty_selection`);
      - a range that snapping reduces to empty or reverses (`empty_after_snap`).
    - **Painting.** A composed scalar maps back to every DOM range that produced it.
12. **Pagination.** Pages follow the mounted DOM's block boundaries. Offsets stay global to the document.
13. **Fixture.** `apps/reading/src/lib/api/__fixtures__/html_text_projection_v1.json`, imported byte-for-byte by both suites (pytest reads it by path).
    - **Astra authored,** independently of any projector: the projections, their hashes and the normalization rules.
    - **Lane A owns:** the DOM paths, selections, refusals and `fragment_parse`.
    - **Field meanings:** `html` is projector input. The sanitizer cases pin `raw_input`, `served_html_target` and `served_html_legacy_v1_4_0`. DOM paths address the served string in the pinned context.
14. **Owners.**
    - **Backend (Astra):** the projector, chunking, the anchor map, resolve, backfill, and `served_body_sha256` on `/full-text` and in anchors.
    - **Lane A:** DOM mapping, mark painting, pagination and the endpoint rules.
15. **Execution gates, not co-sign blockers.**
    - (a) A real Python/browser differential over the fixture, plus malformed-tree cases (foster parenting, misnested inline and block, implicit tbody), mounting-context cases, and a sample of served production strings.
    - (b) HTML5 canonicalization and hidden-subtree stripping in the sanitizer is a separate backend change. It needs its own version bump, preserved security allowlists, idempotency and the existing security regression suite. Its owner is unclaimed.

**Provenance of §1.4c (lane B).** The block above is pasted byte-exact from `THREAD-CONTRACT-REV9-SECTION-1.4c-PIN.md` lines 11–57. That file's SHA-256 is `a99c4950a568240ecaeef71974fbf34a78e10e0067d8798d3c6870185a5c6821`. Astra (the backend) co-signed it at the section level with fixture commit `41e4825d3e039a213fdb47748a4ace5aeaaa017f` (backend INBOX and DECISIONS, "Rev 9 §1.4c co-signed at the section level"). Lane A diffs this block against the pin. It is not edited here: any change is a new pin, re-signed.

**Lane B notes to §1.4c** (outside the signed text):
- **(a) Storage.**
  - `anchored_highlights` gains the additive columns `text_projection` and `served_body_sha256` (`ADD COLUMN IF NOT EXISTS`).
  - Both are null on anchors over plain-text bodies (`unicode-nfc-v1`, §1.4) and on rows written before rev 9. Those re-resolve by quote and context on first reopen, per item 9, and never move silently.
  - `FullTextResponse` and the anchor-map response gain the same two fields.
  - The carrier's bump is in §1.16.
- **(b) Scope.** Derived-asset revisions keep §1.11a's per-block canonical text (html_projection block text, NFC; THREAD-CONTRACT.md §1.11a "Span partition and support"). §1.4c governs reader HTML bodies only, so the two projections never blur.
- **(c) Not binding yet.** §1.4c binds only when rev 9 as a whole carries both lanes' signatures and a different-lineage audit ACCEPT. Item 15's differential gates stay execution gates. The sanitizer canonicalization in item 15(b) is a separate backend change with no claimed owner.
- **(d) Owner line.** Item 14's backend "owner" line is coordination responsibility. It does not override existing board claims, including the Codex train session "Antiek Nudge"'s on A03, anchors or the reader.
- **(e) A03 chunk invariant, restated for §1.4.** For every body, a chunk's text is an exact substring of its document's served projection: `html-text/v1` for HTML, `unicode-nfc-v1` for text. The anchor map drops any chunk it cannot locate, so a chunk that breaks this is invisible to anchors, not merely misplaced.

### 1.5 Project registry (answers Q-A5; rev 9 extends LB-2 per D-P)

**What LB-2 built (rev 7; PR #3530 at `ee6867a11`, not on main).** LB-2's registry and tab code is cited at that head. Rev 9 extends it additively and keeps each of these unless a rule below says otherwise:
- **One registry.** It is `write_folders` plus `write_folder_members`, with no projects table (THREAD-CONTRACT.md@e39840224 §1.5 ("There is no new projects table.")). A folder's `name` is the project's title, and `/write/folders` stays Write's alias.
- **Additive columns.** Columns are added by `ALTER … ADD COLUMN IF NOT EXISTS` and read through COALESCE (`substrate/projects/schema.py@ee6867a11` ("add a column with a NOT NULL constraint, so readers COALESCE the new columns")).
- **Vocabularies.**
  - `kind` is `project | reading` (`substrate/projects/schema.py@ee6867a11` ("PROJECT_KINDS: tuple[str, ...] = (\"project\", \"reading\")")).
  - `member_kind` is `node | investigation | document | deliverable` (`substrate/projects/schema.py@ee6867a11` ("MEMBER_KINDS: tuple[str, ...] = (\"node\", \"investigation\", \"document\", \"deliverable\")")).
- **Owner.** The owner comes from middleware, never from the request (`interfaces/research/api/books.py@b41f4ec9b` ("Resolve ownership from middleware state, never from request data.")). Another owner's project reads as missing.
- **Member key.** A member is keyed by `(folder_id, node_id)`, so one id is one member. Re-adding an id under another kind answers `409 member_kind_conflict` (`substrate/projects/registry.py@ee6867a11` ("adding it again under a different kind is refused")). The wire calls the key `member_id`.
- **Promotion.** `PATCH {kind: project}` promotes a `reading` project in place (`substrate/projects/registry.py@ee6867a11` ("a reading project may only be promoted to a project")). Rev 9 removes it (PATCH, below).
- **Refusals** are FastAPI `{"detail": "<code>"}` bodies (`interfaces/research/api/project_routes.py@ee6867a11` ("return HTTPException(status_code=error.status, detail=error.code)")). Rev 9 adds `reason` equal to each code (§1.0a "Error bodies").
- **No events.** No registry write emits an event, because the folder payloads were never typed (`substrate/write/folders.py@b41f4ec9b` ("typed folder event payloads")).

**Row fields (rev 9).**

| Field (column) | Values | Written by | Rule |
|---|---|---|---|
| `home_product` | `research \| writing \| reading` | create only | Immutable. It picks the create page and the default mode, and it never filters a home (D-P). |
| `products[]` (`products VARCHAR[]`) | A non-empty subset of the three, in canonical order `research, writing, reading`, with no repeats | Create (`[home_product]`), a whole transfer (append), leave (remove) | Its values equal the mode keys, so presence joins `project_tabs.mothership` with no mapping. |
| `kind` | `project \| reading \| interest` | Create; Books → Research (`reading` → `project`, §1.5a T6) | Only `interest` is new. No other kind change exists. |
| `primary_document_id` | A document id, or null | Create (the `book` seed), or a partial transfer that creates a `reading` target | Required and reader-openable for `kind: reading`. Null for `interest` and for a project born as `project`. Immutable: a book turned into a project keeps it. |
| `derived_from_project_id` | A project id, or null | A partial transfer that **creates** this row (§1.5a) | Immutable, and never set on an existing row, so lineage is acyclic by construction. |
| `seed` (`seed_json VARCHAR`) | The accepted seed as canonical JSON, or null | Create | Immutable. Null on legacy rows, `/write/folders` rows and transfer-created rows. |
| `shelf_version` | `BIGINT`, starting at 0 | Every change to the shelf | The shelf's compare-and-set version. |

LB-2's `title`, `order`, `pinned`, `archived_at`, `created_at` and `updated_at` stay. No column holds `speak` or `autonomous` (ruling 4; ruling 10; D-P tightening 1).

**Invariants (rev 9).** They are checked in code on every write, as LB-2 checks its vocabularies (`substrate/projects/schema.py@ee6867a11` ("every column that holds")):
1. **Presence.** `products[]` is never empty. After a leave, `home_product` may be missing from it; it stays as the birth record.
2. **Book and interest rows are reading-only.** A `kind: reading` or `kind: interest` row always has `products = [reading]`. No transfer appends to either (§1.5a), and Books → Research (T6) changes the kind in the same write that adds `research`.
3. **Primary document.** `kind: reading` requires `primary_document_id`, and `kind: interest` requires it to be null.
4. **One book project per document.** An owner has at most one `kind: reading` row per `primary_document_id`. The create transaction checks this. The single writer serialises creates, so two creates cannot both miss it.

**Legacy and LB-2-era rows (rev 9).** A row whose `home_product` is null gets these values:
- A `kind: project` row gets `home_product: writing`. Its `products[]` is `[writing]` plus every mode that already has a `project_tabs` row for this owner and project.
  - A pre-LB-2 folder has no tab rows, so it lists under `?product=writing` only, as D-P requires.
  - The union matters only for a tree the operator built through LB-2's routes before LB-17 landed. It keeps that tree from becoming `not_in_mode`. This refines D-P's legacy clause for rows only LB-2 could write (Appendix C).
- A `kind: reading` row can only have been written by LB-2. It gets `home_product: reading, products: [reading]`.
- `seed` is null and `shelf_version` is 0.
- The first registry write after deploy stores these values once, in `init_projects_schema`. Until then, readers derive the same values, following LB-2's COALESCE pattern.

**Member fields (rev 9).**

| Column | Rule |
|---|---|
| `member_kind` | Gains `speak_project`, `derived_asset` and `project`. It is `NOT NULL DEFAULT 'node'` after the rebuild. |
| `member_role` | `primary \| shelf \| context \| managed \| agent`, or null. |
| `reach` | `attached_only` on `agent` and `managed` rows, and null on every other row (D-A). The server sets it; a request never does. |
| `ordinal` | Set exactly on `shelf` rows. It is 0-based and dense, and every shelf change rewrites it. |

**One rebuild of the member table (rev 9, LB-17).** DuckDB cannot add a CHECK by ALTER (`substrate/graph/schema.py@b41f4ec9b` ("ALTER a CHECK in place, so both migrations rebuild the table.")). DuckDB 1.5.4 in the platform venv refuses both `ALTER TABLE … ADD COLUMN … CHECK` ("Adding columns with constraints not yet supported") and `ALTER TABLE … ADD CONSTRAINT … CHECK` ("No support for that ALTER TABLE option yet!") (RUN).
- LB-17 therefore rebuilds `write_folder_members` once, as a new table plus a copy. It copies every row, keeps `(folder_id, node_id)` as the primary key, and recreates `idx_write_folder_members_node`.
- This rebuild is new in rev 9. It is **not** the rev-6 rebuild that §1.16 schedules for W3, which rebuilds `derived_asset_revision_members` (§1.11) and stays in W3.
- The rebuilt table carries:

  ```sql
  CHECK (reach IS NULL OR reach = 'attached_only'),
  CHECK (COALESCE(member_role IN ('agent', 'managed'), FALSE) = (reach IS NOT NULL)),
  CHECK (COALESCE(member_role = 'shelf', FALSE) = (ordinal IS NOT NULL))
  ```
- **Red-first.** A row with a null `member_role` and `reach = 'attached_only'` must be refused. The naive form `member_role IN (...) = (reach IS NOT NULL)` accepts it, because the comparison evaluates to NULL and a NULL CHECK passes.
- The vocabularies stay checked in code, so adding a value needs no second rebuild. A second `reach` value needs an operator ruling (D-A).

**Member kinds and roles (rev 9).**

| `member_kind` | `member_id` names | Roles | Written by |
|---|---|---|---|
| `node` | a graph node | null (a Write block), `context` | The members route; `/write/folders` blocks; a Research → Books partial transfer (`context`) |
| `investigation` | a thread | null, `agent`, `managed` | The members route; seeds; transfers; a launch with `project_id` (§1.3); a dialogue create (§1.8); a merge commit (§1.10) |
| `document` | a document | `primary`, `shelf`, `context` | The `book` seed or a `reading` transfer target (`primary`); the shelf PUT and Books transfers (`shelf`); Keep (`context`) |
| `deliverable` | a Write deliverable | `primary`, null | Seeds, Research → Writing transfers, Speak → Writing. The role is `primary` when the project has no primary deliverable yet. |
| `speak_project` | an `interview_projects.project_id` | null | Speak → Writing (§1.5a); the members route |
| `derived_asset` | a §1.11a derived asset | null, `context` | The members route |
| `project` | another registry project of the same owner | `context` | The members route, with `link_back` (ruling 11) |

- A project has at most one `primary` row per `member_kind`. A `document` primary equals `primary_document_id`.
- Aggregates never recurse through a `project` member.

**Role changes (rev 9).** A role changes only through a named operation:
- **Document.** `context → shelf` and `shelf → removed` happen only through the shelf PUT (below). `primary` never changes.
- **Investigation.** `null → agent`, `null → managed`, and `agent ↔ managed` go through the members route, under §1.12a's checks. Going back to a null role is a DELETE followed by a plain add.
- **Anything else** answers `409 {reason: member_role_conflict, member_role}`, naming the stored role.

**References and owners (rev 9).** Every route in this section is owner-scoped from day one (THREAD-CONTRACT.md@e39840224 §1.15 ("Every route this contract adds is owner-scoped from day one")). The one rule for missing and foreign references is §1.15's. Applied here:
- **Registry projects.** A registry project that is missing, or belongs to another owner, is `404 project_not_found`, as in LB-2. That covers the path project, a `project` member, a named transfer target and `derived_from_project_id`.
- **Threads named in a body** (seeds, transfers, `agent` and `managed` members) must be a `thread` (§1.2). Anything else answers `404 {reason: thread_not_found, ref}`. A thread whose recorded owner differs from the requester answers `403 {reason: not_owner, ref}`, following LB-15's rule until W1's owner-on-start lands.
- **Speak requests** follow LB-15's Speak owner predicate, the one `GET /speak/projects` uses after LB-15.
- **Documents** are corpus rows and are not owner-checked, except a private document (`user_authored_private`), which only its exact owner can discover; to anyone else it is a missing document, answered before any metadata, reference or context is read (§1.15 rule 4, A06).
  - Their `owner_user_id` defaults to `__operator__` (`substrate/graph/schema.py@b41f4ec9b` ("Sprint 11 multi-user schema prep: every row carries an owner_user_id")). An owner check would therefore refuse the operator's own books.
  - What governs a document is its rights gate (below). A missing document is `404 {reason: source_not_found, ref}`.
- **Derived assets** follow §1.11a's owner rule. A missing one is `404 {reason: source_not_found, ref}`, and a mismatch is `403 {reason: not_owner, ref}`.
- **LB-2's four kinds stay unchecked on the plain route.** For `node`, `investigation` (null role), `document` and `deliverable`, the members route keeps LB-2's behaviour and does not check that the id exists. The checks above apply to seeds, transfers, the three new kinds, and the `agent` and `managed` roles.

**One gate projection (rev 9).** Every document the registry lists (the shelf, the transfer candidates, `GET /reading/continue`, book-ask `source_refs`, flag documents) carries a flat `gate` and `reason`, the signed `GatedText` pair, computed one way:
- It starts from `servability_of(content_class, taken_down)` (`substrate/books/servability.py@b41f4ec9b` ("def servability_of(")).
- A servable status reads `served`.
- `personal_readable` reads `served` for the owner-read audience, the owner's own `personal_reading` document (`substrate/books/servability.py@b41f4ec9b` ("``personal_reading`` resolves to ``PERSONAL_READABLE``")). Today that audience is the single operator (LB-35 spec Q10). For any other audience it reads `cite_only · not_servable`.
- `gated_metadata_only`, which also covers a null or unrecognised class, reads `cite_only · not_servable`.
- `taken_down` reads `withheld · not_servable`.
- A member whose document no longer resolves reads `withheld · unresolved` with null metadata. It is never dropped.

**Actor (rev 9).** Registry writes take a server-derived `actor: {kind: user | agent, id}`, the signed §1.13 vocabulary. It never comes from the body.
- Every HTTP route acts as `{kind: user, id: <owner>}`. No rev-9 route acts as `agent`, because agents act only by answering (§1.12a, "What an agent can do").
- The registry functions still take the actor. An `agent` actor that adds or changes a `document`, `node` or `project` member, or writes the shelf, gets `403 {reason: agent_cannot_curate}`. A later agent surface therefore inherits the guard, and its test calls the function directly.
- Agents propose through their answers: lane A opens an answer ref as a transient tab (§1.6) and offers Keep or Read later, which the operator's press writes as `user` (ruling 12; Part 2 draft §B8).
- A body that carries `actor` is refused by LB-2's unknown-field codes, `422 project_body_invalid` or `member_body_invalid`.

#### Create: `POST /projects` (rev 9; LB-17; S14)

```
POST /projects
{
  home_product: "research" | "writing" | "reading",
  kind: "project" | "reading" | "interest",
  title?: string,                 // 1..200 after trimming (substrate/projects/registry.py@ee6867a11 ("TITLE_MAX = 200"))
  seed: Seed,
  idempotency_key: string         // 1..128 characters of [A-Za-z0-9_-]
}

Seed = an object with exactly one key:
  {question: {text}}                                                  // text: 3..2,000 characters
  {blank_deliverable: {deliverable_kind?}}                            // default "general_essay"
  {from_investigation: {investigation_id, node_ids?: [], deliverable_kind?}}
                                                                      // deliverable_kind: writing only; default "research_memo"
  {book: {document_id}}
  {interest: {title, seed_prompt?}}                                   // title 1..200; seed_prompt ≤ 2,000
```

**The seed matrix.** Any combination not in this table answers `{reason: seed_invalid, detail: seed_mismatch}`:

| `home_product` | `kind` | Seeds admitted |
|---|---|---|
| `research` | `project` | `question`, `from_investigation` |
| `writing` | `project` | `blank_deliverable`, `from_investigation` |
| `reading` | `reading` | `book` |
| `reading` | `interest` | `interest` |

- **No Speak or Autonomous create.**
  - There is no `speak` seed and no `speak` home. Speak creates stay on `POST /speak/projects`, which LB-15 binds to the owner (ruling 4).
  - There is no `autonomous` seed until LB-10 lands (D-P).
  - `template: biography` stays on the Speak side (ruling 6).
- A `home_product` of `speak`, `autonomous` or `books` answers `{reason: seed_invalid, detail: product_invalid, field: home_product}`.
- `question.text` needs at least 3 characters, because the launch that follows does (`interfaces/research/api/app.py@b41f4ec9b` ("question: str = Field(..., min_length=3)")).
- `deliverable_kind` must be one of Write's five kinds (`interfaces/research/api/app.py@b41f4ec9b` ("\"research_memo\", \"book_chapter\", \"biography_section\",")). Any other value is `seed_invalid · deliverable_kind_invalid`.

**What each seed writes.** The row, the seed's rows, the members, the `project_create_requests` row and `project.created` are all written in one `connect_write` transaction, through the outbox:

| Seed | Writes | `next` |
|---|---|---|
| `question` | Only the row. The question is stored in `seed` and is **not** launched, so nothing is spent until the operator presses Start (lane-A default 1). The launch that follows is `POST /investigations {question, project_id}` (§1.3), which writes its own membership. | `{kind: launch_first_question, ref: {question}}` |
| `blank_deliverable` | A deliverable, inserted with `insert_deliverable` under the request owner and the project's title, as `{deliverable, primary}`. It never launches research (lane-A default 1). | `{kind: open_mode, ref: {mothership: writing, deliverable_id}}` |
| `from_investigation`, research home | The thread as `{investigation, null}`. | `{kind: open_mode, ref: {mothership: research, thread_id}}` |
| `from_investigation`, writing home | The repaired promotion of §1.11 rev 9: a deliverable with one section whose blocks are the thread synthesis's pinned nodes as `graph_node` references, narrowed to `node_ids` when given. Members `{investigation, null}` and `{deliverable, primary}`. | `{kind: open_mode, ref: {mothership: writing, deliverable_id}}` |
| `book` | `primary_document_id` and `{document, primary}`. | `{kind: import_book, ref: {document_id}}` |
| `interest` | Only the row, with `primary_document_id` null. | `{kind: open_mode, ref: {mothership: reading}}` |

`from_investigation` on a writing home has two refusals:
- **No depositable synthesis** answers `seed_invalid · no_synthesis`. Today's route answers 404 in that case (`substrate/write/promote_context.py@b41f4ec9b` ("Returns ``None`` when the investigation has **no** depositable synthesis")).
- **A `node_id` outside the pinned set** answers `seed_invalid · node_not_in_synthesis`.

**Reader-openable (rev 9; per the LB-35 spec).** A `book` seed's document must be one the reader can open, meaning one `GET /books/{id}` answers 200 for (§1.18a):
- **Today** that means a document with a `book_assets` row. `GET /books/{id}` answers `404 book_not_found` without one (`interfaces/research/api/books.py@b41f4ec9b` ("async def get_book(document_id: str) -> BookDetail:")).
- **Once LB-35 lands** it means any `documents` row except an unregistered `derived` one (LB-35 spec D1). There is no closed long-form list.
- **Otherwise** the answer is `seed_invalid · not_reader_openable`.
- **Classification first (rev 9; LB-35 spec Q9).** A document whose `content_class` is null answers `seed_invalid · document_unclassified`. Chunk search serves a null-class document in full while the reader gives it a snippet, so it must be classified before it becomes a primary or a shelf item. LB-35 leaves this step to the shelf write, which is LB-17's.
- **The rights gate is not a reason to refuse a create.** A classified book whose content class is not servable still makes a project. The shelf and the reader show its gate by the one projection above, and they never drop it. Rev 9 reads LB-17's "must be servable in the reader" in this sense.

**Title.** The project takes `title` when it is given. Otherwise it takes, by seed:
- `question`: the question's first 200 characters;
- `book`: the document's `title`, or its id when the title is null;
- `interest`: `interest.title`;
- `from_investigation`: the thread's §1.2 title;
- `blank_deliverable`: "Untitled".

A bad title is `422 project_title_invalid`, as in LB-2.

**Atomicity (rev 9).** Either the whole create commits or nothing does. Two code facts constrain how that is built:
- **Block placement.** `place_block` refuses an eventful placement inside a transaction it does not own (`substrate/write/outline_block.py@b41f4ec9b` ("eventful block placement must own its transaction")). The writing seeds therefore place blocks inside the create's transaction and enqueue each block's event on that transaction's outbox. LB-17 extends the helper to allow that.
- **Promotion.** `promote_investigation_to_deliverable` (`substrate/write/promote_context.py@b41f4ec9b` ("def promote_investigation_to_deliverable(")) inserts its deliverable and section outside any transaction, then places each block in a transaction of its own.
  - Red-first: a fault injected after its first block leaves a partial deliverable on the base.
  - With rev 9, the same fault leaves no row, no deliverable, no block and no outbox row.

**Idempotency (rev 9).** NEW table `project_create_requests (owner_user_id, idempotency_key, request_sha256, project_id, created, created_at)`, with primary key `(owner_user_id, idempotency_key)`. It is written in the create's transaction.
- **Request identity** is sha256 over the canonical JSON of `{owner, home_product, kind, title, seed}`, with `title` null when absent.
- **Replay.** The same key with the same identity answers `200 {project, next, created}`. `created` is the first answer's value, and `project` is the row as it is now. Nothing is written, so there is no second deliverable and no second event.
- **Conflict.** The same key with another identity answers `409 {reason: idempotency_conflict, project_id}`. `project_id` lets lane A open the project that its stale mount created (Part 2 draft §B1).
- **One book project per document.** A `book` seed for a document that already has the owner's `kind: reading` row, archived or not, answers `200 {project, next, created: false}` with that project. It writes only the key row, so a replay of that key returns the same answer.

**Response.** `201 {project, next, created: true}`. `project` is the row shape given under **Reads**.

**The rev-7 body (rev 9).** LB-2 accepts the body `{title, kind, primary_document_id}` (`interfaces/research/api/project_routes.py@ee6867a11` ("unknown = sorted(set(body) - {\"title\", \"kind\", \"primary_document_id\"})")).
- Once LB-17 lands, that body is refused with `seed_invalid · seed_required`.
- In the same change, LB-17 moves LB-2's client (`apps/reading/src/lib/api/projects.ts@ee6867a11` ("export async function createProject(")) to the seeded body.

**Errors.**

| Status | Body |
|---|---|
| 401 | `authenticated_owner_required` (LB-2, unchanged) |
| 403 | `{reason: not_owner, ref}` |
| 404 | `{reason: thread_not_found, ref}` or `{reason: source_not_found, ref}` |
| 409 | `{reason: idempotency_conflict, project_id}` |
| 422 | `project_body_invalid` (an unknown field), `idempotency_key_invalid`, `project_title_invalid`, or `{reason: seed_invalid, detail, field}`. `detail` is one of `seed_required`, `seed_shape`, `product_invalid`, `kind_invalid`, `seed_mismatch`, `question_invalid`, `deliverable_kind_invalid`, `not_reader_openable`, `document_unclassified`, `no_synthesis` or `node_not_in_synthesis`. |

#### Reads (rev 9; LB-17; answers lane A's request C1)

`GET /projects?product=&include_archived=` and `GET /projects/{id}` read through `connect_read` and write nothing.
- **Presence filter.** `?product=research|writing|reading` lists the rows whose `products[]` contains that value. Without `product`, the list covers every presence. This is the only presence filter, and `home_product` never filters (D-P).
- **Refused filters.**
  - `?product=books`, or any other value, is `422 {reason: product_invalid}`.
  - `?home_product=` is `422 {reason: filter_invalid}`. A client built on lane A's superseded name then fails loudly instead of receiving an unfiltered list.
- **Archive filter.** It keeps LB-2's name, `include_archived`, which defaults to false (`interfaces/research/api/project_routes.py@ee6867a11` ("include_archived: bool = Query(default=False)")). The grounding's `archived=` refers to this parameter, and no second name exists.
- **Order.** LB-2's order stands (`substrate/projects/registry.py@ee6867a11` ("pinned first, then by order, then oldest first")).

**Row shape (rev 9).** LB-2's fields, plus:

| Field | Source |
|---|---|
| `home_product`, `products[]`, `kind`, `primary_document_id`, `derived_from_project_id`, `seed` | Stored. |
| `last_mode` | Derived. It is the mode in `products[]` whose `project_tabs` row for this owner and project has the newest `updated_at` (`substrate/projects/tabs.py@ee6867a11` ("updated_at = excluded.updated_at")). A tie goes to the earlier mode in canonical order. A tree in a mode the project has left is ignored. It is null when no present mode has a tree. |
| `default_mode` (NEW in rev 9) | Derived. It is `home_product` when present, otherwise the first entry of `products[]`. It is never null. It closes the landing rule's last fallback, because after a leave `home_product` can name an absent mode. |
| `shelf_count` | Derived: the primary document, if any, plus the `shelf` rows. It is null when `reading` is not in `products[]`. An empty shelf is a known 0. |
| `linked_project_ids[]` | Derived: this project's `project` members, oldest first. |
| `thread_counts` | THREAD-CONTRACT.md@e39840224 §1.5 ("`thread_counts` is `{running, needs_you, done_unseen}` over `GET /investigations?project_id=`"), over the project's threads, with membership as the authority (§1.2). |
| `spend_today` | THREAD-CONTRACT.md@e39840224 §1.5 ("`spend_today` is `{cents, currency: \"USD\"} \| null`"). It sums today's settlements and records (§1.13) that carry this `project_id`. |
| `null_reasons` | One entry per derived field that is null, and none for a field that is set. The possible entries are `{thread_counts?: logs_unreadable, spend_today?: ledger_unreachable \| cost_unknown, shelf_count?: not_in_product, last_mode?: no_tree}`. `cost_unknown` means a record touching this project today has an unknown cost (§1.13). |

- An unknown value is null with its reason, never `0`. LB-2's routes compute none of these yet.
- The list computes `thread_counts` in one pass over the logs per request, never with one scan per row.
- Part 1 serves no per-mode spend figure in rev 9. The `mothership` attribution on every ledger operation (§1.13; D-P tightening 3) keeps one derivable later.
- `GET /projects/{id}` returns the row plus `members[]`. Each member is `{member_kind, member_id, member_role, ordinal, reach, added_at}`.

#### PATCH (rev 9)

- LB-2's `title`, `order`, `pinned` and `archived` stand, with last write winning. An accepted PATCH writes `project.updated`.
- Rev 9 removes `kind` from PATCH. A book becomes a project only through Books → Research (§1.5a T6), which adds `research` in the same write.
- Sending `kind`, `home_product`, `products`, `primary_document_id`, `derived_from_project_id` or `seed` answers `422 {reason: project_patch_invalid, field}`.

#### Members route (rev 9; S12, S15; ruling 11; one rule for lanes A and B)

`POST /projects/{id}/members {member_kind, member_id, member_role?, link_back?}`.
- `member_kind` and `member_id` stay required, as in LB-2 (`interfaces/research/api/project_routes.py@ee6867a11` ("if sorted(body) != [\"member_id\", \"member_kind\"]:")). `member_role` and `link_back` are optional.
- **`reach` is server-set.** On an `agent` or `managed` row the server writes `reach: attached_only`. A body that carries `reach` answers `422 member_body_invalid`. The table CHECK is the backstop.
- **No `idempotency_key`.** The route is idempotent by its natural key, `(project, member_id)`. A body that carries `idempotency_key` answers `422 member_body_invalid`.
- The grounding's `ref` (S12, S15) is this `member_id`.

**Answers by the natural key.** Every accepted answer is `{status, member}`:
- A new member answers `201 {status: added, member}`.
- An existing member with the same kind and role answers `200 {status: already_member, member}` and writes nothing.
- A `context` request for a document that is already `primary` or `shelf` answers the same way. The stronger membership already keeps it, as with a Keep on a book that is on the shelf.
- An allowed role change answers `200 {status: role_changed, member}`.
- Another kind is `409 member_kind_conflict` (LB-2). Another role is `409 {reason: member_role_conflict, member_role}`.

**Roles admitted on this route.**

| `member_kind` | Roles |
|---|---|
| `node` | null or `context` |
| `investigation` | null, `agent` or `managed` |
| `document` | `context` only |
| `deliverable` | null |
| `speak_project` | null |
| `derived_asset` | null or `context` |
| `project` | `context` only |

- Any other role is `422 {reason: member_role_invalid}`, including `shelf` and `primary`. The shelf has its own route, and `primary` is written only by a seed or a transfer.

**Agent and managed rows (rev 9; D-A).** `{member_kind: investigation, member_role: agent | managed}` runs §1.12a's checks, in §1.12a's order, before anything is written:
1. The project is not the caller's: `404 project_not_found`.
2. The id is not a `thread`: `404 {reason: thread_not_found, ref}`.
3. The thread's owner is not the caller: `403 {reason: not_owner, ref}`.
4. The thread is not promoted: `422 {reason: not_an_agent}`.
5. Any project the agent belongs to, or would join by this write, is shared: `422 {reason: project_shared}`.

**The ruling-11 link.** The body `{member_kind: project, member_role: context, member_id: <other project>, link_back: true}` writes both rows (this project to the other, and the other back to this one) in one transaction, or neither.
- `link_back` is valid only with `member_kind: project`; otherwise the answer is `422 member_body_invalid`. It defaults to false.
- A link from a project to itself is `422 member_id_invalid`.
- The book keeps its id. A book session reads the linked project only through §1.8's narrowed link layer, and an agent reaches it only through an explicit attach (§1.12a step 7). Nothing reached through the link is ever written to (ruling 11; D-A).

**Delete.** `DELETE /projects/{id}/members/{member_id}` stands (LB-2). Rev 9 adds three rules:
- Deleting a `primary` row is `409 {reason: member_is_primary}`.
- Deleting a `project` member also deletes the reverse row when one exists, in the same transaction.
- Deleting a `shelf` row increments `shelf_version` and writes `project.shelf_changed`.

**Events.** Every accepted change writes `project.members_changed` through the outbox, in its own transaction. A change to `shelf` rows writes `project.shelf_changed` instead.

#### Shelf (rev 9; S15; ruling 12)

`GET /projects/{id}/shelf` returns:

```
{project_id, shelf_version, in_product, items: [
  {document_id, member_role: "primary" | "shelf", ordinal | null,
   title | null, author | null, document_type | null, is_book,
   gate: "served" | "cite_only" | "withheld", reason: "not_servable" | "unresolved" | null,
   progress: {page_index, page_count, pct} | null,
   adopted_version?: {derived_asset_id, revision_id}}
]}
```
- **Order.** The primary document comes first, then books by `ordinal`, then non-books by `ordinal`.
- **Book or not.** `is_book` is `document_type == "book"`, the LB-35 spec's rule (D1), never derived from having a `book_assets` row. A non-book is marked by `is_book: false` and its `document_type` (ruling 12).
- **Gate.** `gate` and `reason` come from the one gate projection above. An unresolved member is listed as `withheld · unresolved` with null metadata.
- **Progress** comes from the owner's §1.14 position. It is null when there is no position or no page count above 0.
- **Adopted version** is the project's reading-version pointer for that document, when one exists (THREAD-CONTRACT.md@e39840224 §1.11a ("`project_reading_versions (owner_user_id, project_id, source_document_id")).
- **`in_product`** says whether `reading` is in `products[]`. The GET answers either way, because a project that has left Books keeps its rows.

`PUT /projects/{id}/shelf {document_ids[], expected_version}`:
- **The list.** `document_ids[]` is the complete, ordered list of `shelf` rows. The primary document is not part of it.
- **Compare-and-set.** `expected_version` must equal `shelf_version`, which is 0 before the first write, as with §1.11a's reading-version PUT. Otherwise the answer is `409 {reason: version_stale, current}`, where `current` has the GET shape.
- **What changes.** A listed document that is a `context` member becomes `shelf`. A `shelf` row that is left out is removed from the project. Members of other kinds and roles are untouched.
- **Admission (ruling 12; per the LB-35 spec).** Long-form assets of any type are admitted, not only books, and a non-servable document is admitted and shows its gate. There is no closed document-type list. Each listed document is checked:
  - It must exist, or the answer is `404 {reason: source_not_found, ref}`.
  - It must be reader-openable (§1.5 create). Otherwise `422 {reason: shelf_invalid, detail: not_reader_openable, document_id}`.
  - It must be classified (LB-35 spec Q9). Otherwise `422 {reason: shelf_invalid, detail: document_unclassified, document_id}`.
- **Other refusals.**
  - A duplicate is `shelf_invalid · duplicate`.
  - Listing the primary is `shelf_invalid · primary_not_shelf`.
  - More than 1,000 items is `shelf_invalid · too_many`.
  - If `reading` is not in `products[]`, the answer is `409 {reason: product_absent, product: "reading"}`.
- **Accepted change.** It rewrites `ordinal` densely, increments `shelf_version`, writes `project.shelf_changed`, and answers with the GET shape.
- **No-op.** A PUT that changes nothing answers 200 with the version unchanged and writes no event.
- **Idempotent through the compare-and-set,** like §1.6's tab PUT. If a retried PUT's first attempt already landed, the retry gets `409 version_stale`, and its `current` already holds the retried list. The client treats an equal list as success.

#### Leaving a product (rev 9; S14; D-P)

`DELETE /projects/{id}/products/{product}`:
- A `product` outside the three values is `422 {reason: product_invalid}`.
- Leaving the last product is `409 {reason: last_product}`. A `kind: reading` or `kind: interest` row can therefore never leave `reading`.
- A product that is not present answers `200 {status: not_present, project}` and writes nothing, so a retry is safe.
- Otherwise the route removes the product, writes `project.product_left`, and answers `200 {status: left, project}`.
- **What is kept.** The mode's tab tree, its retirements and number registers, every member, the shelf and every thread all stay. The project stops listing under `?product=<product>`.
- **Leave is not archive.** This is "Leave Writing", never "Archive". `archived_at` is a separate, project-wide PATCH (D-P).
- **Coming back** is a whole transfer (§1.5a, T1). The kept tree reappears unchanged (T9).

#### Presence gates tab writes (rev 9)

Tab PUT and allocate in a mode that is not in `products[]` answer `409 {reason: product_absent, product}`; reads still answer. §1.6 carries the rule.

#### Standalone book, narrowed (rev 9; ruling 11)

This replaces THREAD-CONTRACT.md@e39840224 §1.5 ("Standalone book (Q-A5)") and §1.17's answer (THREAD-CONTRACT.md@e39840224 §1.17 ("**Q-A5:** `kind: reading`, promoted in place (§1.5).")).
- A standalone book is `kind: reading` with its `primary_document_id`.
- **"Add to a research project"** is the ruling-11 link above: two identities, each linking the other. The book is not promoted, and nothing reached through the link is written to.
- **"Turn this book into a new project"** is the only promotion in place left. It is the Books → Research transfer (§1.5a, T6): `kind` becomes `project` and `products[]` gains `research` in one write. The id, members, threads, shelf and primary document are unchanged.
- Part 2's two matching sentences narrow the same way (Part 2 draft §A1 already does).

#### Events (rev 9)

Rev 1 promised that the folder payloads would become typed events (THREAD-CONTRACT.md@e39840224 §1.5 ("notes were never registered become typed events")). Rev 9 delivers them as `project.*`:

| Event | Payload | Written by |
|---|---|---|
| `project.created` | `{project_id, home_product, kind, products[], primary_document_id?, derived_from_project_id?, seed_kind: question \| blank_deliverable \| from_investigation \| book \| interest \| null, via: create \| transfer \| speak_draft \| write_folders, initial_members[{member_kind, member_id, member_role, ordinal?}]}` | A create; a transfer or Speak send that creates a project; `POST /write/folders` |
| `project.updated` (added by rev 9 beyond the grounding's list) | `{project_id, fields[]}`, each field one of `title \| order \| pinned \| archived` | PATCH |
| `project.members_changed` | `{project_id, changes[{op: added \| removed \| role_changed, member_kind, member_id, member_role, previous_role?}], cause: members_route \| link_back \| transfer \| speak_draft \| write_folders \| launch \| dialogue \| merge_commit \| agent_call, transfer_id?}` (`agent_call` is reserved, like `via: agent_call`) | Any change to a member that is not a shelf row |
| `project.shelf_changed` | `{project_id, shelf_version, document_ids[], cause: shelf_put \| members_route \| transfer, transfer_id?}` | Any change to shelf rows |
| `project.product_left` | `{project_id, product, products[]}`, where `products[]` is the list after the leave | A leave |
| `project.transferred` | See §1.5a | A transfer or a Speak send |

- **The project log.** Each event is appended to the log `project-<project_id>`. That is the id LB-2 already puts on the tab broadcast's envelope (`interfaces/research/api/project_routes.py@ee6867a11` ("investigation_id=f\"project-{project_id}\"")).
  - Events go through the outbox in the mutation's own transaction.
  - A create uses the `operation_id` `project.created:<project_id>`. Every other event uses `next_aggregate_operation_id(action, aggregate_kind="project", aggregate_id=<project_id>)` (`substrate/write/event_outbox.py@b41f4ec9b` ("def next_aggregate_operation_id(")).
  - `operation_id` is unique in the outbox (`substrate/graph/schema.py@b41f4ec9b` ("operation_id TEXT NOT NULL UNIQUE")).
- **Delivery and push.** After commit, the route drains the log with `dispatch_pending_best_effort`, following the pattern at `interfaces/research/api/app.py@b41f4ec9b` ("dispatch_pending_best_effort(con, req.investigation_id)").
  - It broadcasts each delivered event on `/ws/events`, with the envelope's `investigation_id` set to `project-<project_id>` (§1.7).
  - If delivery fails, the intent stays pending, and the next write on that log delivers it.
  - **Startup recovery (rev 9, owned by LB-17).** `recover_pending_events` exists but has no production caller at `b41f4ec9b` (`substrate/write/event_outbox.py@b41f4ec9b` ("def recover_pending_events(")). LB-17 calls it at API startup, so an intent left pending by a crash still reaches its log even if that log is never written again. The call drains every producer's pending rows, not only the registry's (Appendix C). LB-24a adds a call after each `503 merge_pending` (§1.10) and relies on this startup wiring.
- **Never a thread.** A `project-*` log is `not_a_thread` (§1.2). It is never listed, never a parent, a member or a target, and `GET /investigations/project-<id>` answers `404 {reason: not_found}`.
- **Ids and enums only.**
  - No `project.*` payload carries a title, a question, a seed prompt or any document text. `GET /trajectory/{id}` is not owner-scoped (§1.15), so a payload that carried a title would publish it.
  - The payload models forbid extra fields (`substrate/schemas/events.py@b41f4ec9b` ("``extra='forbid'`` is deliberate")).
- **Schema.** The six `project.*` payloads ride the tier-1 bump (§1.16). `project.tabs.version_bumped` stays broadcast-only (§1.6).

#### `/write/folders` (rev 9)

It stays Write's alias over the same rows, owner-scoped as LB-2 made it (THREAD-CONTRACT.md@e39840224 §1.6 ("**`/write/folders` is owner-scoped too.**")). It now reads presence, like a Writing home:
- `GET /write/folders` and `/write/blocks/search?folder_id=` see only rows that have `writing` in `products[]`. Any other row answers `404 folder_not_found`, the same as a missing one.
- `POST /write/folders` creates a row with `home_product: writing, products: [writing], kind: project, seed: null`, and writes `project.created {via: write_folders}`.
- Adding or removing a block writes `project.members_changed {cause: write_folders}` for the `node` row, which has a null role.

**Filing (rev 1, unchanged).** `documents.investigation_id` filing and `topic_slug` still reconcile into membership (THREAD-CONTRACT.md@e39840224 §1.5 ("**Filing:** `documents.investigation_id` filing")).

**Edge.** Every route in this section sits under `/projects*`.
- LB-2 already put that prefix on the `@api_routes` line (`infrastructure/ansible/templates/Caddyfile.j2@ee6867a11` (" /projects* ")).
- Main still has `/projects/*` (`infrastructure/ansible/templates/Caddyfile.j2@b41f4ec9b` (" /projects/* ")), which serves the SPA to a bare `/projects`.
- Rev 9 adds no new prefix here.

#### Acceptance, red-first (LB-17 plus rev 9)

1. **Create idempotency.** A double press with one key yields one project. The same key with another body answers `409 idempotency_conflict` carrying `project_id`.
2. **Create atomicity.** A fault injected after the seed's deliverable insert leaves no registry row, no deliverable, no block and no outbox row. So does a fault after the first block of a `from_investigation` seed. The promotion path is not atomic on the base.
3. **Owner.** The row, the deliverable and the members carry the request owner, never the default `__operator__` (`substrate/write/folders.py@b41f4ec9b` ("owner_user_id: str = \"__operator__\",")).
4. **Reader-openable.**
   - A `book` seed whose document the reader cannot open answers `seed_invalid · not_reader_openable`.
   - A null-class document answers `seed_invalid · document_unclassified`.
   - A registered book with a non-servable class does create. Its shelf item reads `cite_only · not_servable`.
5. **Product values.** A `home_product` of `speak`, `autonomous` or `books` answers `seed_invalid · product_invalid`.
6. **Immutable fields.** A PATCH of `home_product` or of `kind` answers `project_patch_invalid`.
7. **Shelf guards.** A stale shelf PUT answers `409 version_stale` with `current`. A registry function called with an `agent` actor to write the shelf or add a document answers `403 agent_cannot_curate`.
8. **One book project.** A second `book` create for the same owner and document returns the same project with `created: false`.
9. **Legacy presence.** A legacy folder lists under `?product=writing` only. An LB-2-era project with a research tree lists under research and under writing.
10. **Whole transfer presence.** A project born in Writing and transferred whole to Research (§1.5a, T1) lists under both `?product=research` and `?product=writing`.
11. **Nullable aggregates.** `thread_counts` and `spend_today` are present on every row. With the ledger fault-injected unreachable, `spend_today` is null with `null_reasons.spend_today: ledger_unreachable`, never 0. With an unknown-cost record today, it reads `cost_unknown`.
12. **Member CHECKs.** The member table refuses `reach` on a row whose role is null (the NULL-CHECK trap). It also refuses any `reach` other than `attached_only`.
13. **Ruling-11 link.** The link writes both rows or neither, tested with a fault after the first row. A delete removes both rows.
14. **Refused names.**
    - `/tabs/books` answers `404 mothership_unknown`.
    - `?product=books` answers `422 product_invalid`.
    - `?home_product=writing` answers `422 filter_invalid`.
15. **Leave.** Leaving the last product answers `409 last_product`. Leaving Writing has three effects:
    - the project drops from `?product=writing`;
    - `GET …/tabs/writing` still answers;
    - `PUT …/tabs/writing` answers `409 product_absent`.
16. **Project log is not a thread.** `GET /investigations/project-<id>` answers `404 not_found`. This is red on the base.
17. **No titles in events.** A test titles a project with a sentinel string, serialises every `project.*` payload, and asserts the string is absent.
18. **`last_mode`.** It ignores a newer tree in a mode that the project has left.
19. **Write alias presence.** `GET /write/folders` omits a project that is not present in Writing, and a block add to that project answers `404 folder_not_found`.
20. **Pending intents.** A `project.created` left pending by a fault between commit and dispatch reaches its log at the next API start, with no further write.
21. **Members route.** A body with `reach` or `idempotency_key` answers `422 member_body_invalid`. A repeated add answers `200 already_member` and writes nothing.
22. **`is_book`.** A registered non-book (for example a `derived` view) reads `is_book: false`.

**Prod probes (DB-B, read-only).** `GET /projects` and `GET /projects/{id}/shelf` must answer with the API's own JSON: `401 authenticated_owner_required` when unauthenticated, never the SPA's HTML.

### 1.5a Transfers (NEW, rev 9; LB-18; per D-P and rulings 4, 10 and 11; S16)

**What a transfer is (D-P).** A transfer never copies content. It does one of two things, and it records `project.transferred` in the same transaction:
- **Whole:** it appends presence to the same project.
- **Partial:** it places member references in a new or a named project.

Any seeding a transfer does is also made of references: a Write deliverable of `graph_node` blocks, or a shelf of documents.

**Supported transfers (rev 9).**

| # | Source row | `to_product` | `scope` | `effect` | `selection` |
|---|---|---|---|---|---|
| T1 | `kind: project` | a product not in `products[]` | `whole` | `presence` | empty |
| T2 | `kind: project`, with `research` present | `writing`, not present | `whole` | `seed_deliverable` into this project | `investigation_ids[]`, plus optional `node_ids[]` |
| T3 | `kind: project`, with `research` present | `writing` | `partial` | `seed_deliverable` into a new or named project | the same fields, required |
| T4 | `kind: project`, with `research` present | `reading`, not present | `whole` | `seed_shelf` into this project | `document_ids[]` |
| T5 | `kind: project`, with `research` present | `reading` | `partial` | `seed_shelf` into a new or named `reading` or `interest` project, with insight nodes as context | `document_ids[]` and/or `node_ids[]`, required |
| T6 | `kind: reading` | `research` | `whole` | `promote_book` ("Turn this book into a new project") | empty |

- **T1 is D-P's whole transfer as written:** "it appends to `products[]` and writes one `project.transferred` event, so the same id opens in the target mode with its own tree (T9)". It covers four cases:
  - lane A's "Open in <mode>" on a `not_in_mode` project (Part 2 draft §A1);
  - a Writing project gaining Research (LB-17's acceptance);
  - a Research → Books whole transfer with no books picked yet, after which lane A's "Which book(s)?" step follows;
  - coming back after a leave, where the kept tree reappears.
- **T2 and T4** are T1 with seeding. They need `research` present, because the seeding reads research material.
- **T6** is ruling 11's one remaining promotion in place.
- **Book and interest rows (rev 9).** Invariant 2 of §1.5 keeps a `kind: reading` or `kind: interest` row reading-only. So a book project can gain Research only through T6, and it can never gain Writing; an interest project can gain nothing. Their "Open in <mode>" offers read `{available: false, reason: transfer_not_supported}` in `offers` (below), and lane A shows a disabled state (Appendix B).

**Not this route.**
- **Research → Autonomous** is `member_role: managed` on the thread's existing membership, written through `POST /projects/{id}/members {member_kind: investigation, member_id, member_role: managed}` (§1.5; §1.12a; LB-28). The server sets `reach`.
  - "Autonomous" is not a product value (D-P tightening 1), so there is nothing to append.
  - Spawning stays off until LB-10 lands and the operator enables it (ruling 10).
  - Until the operator rules on O-11, each continuation is a per-flag consent under D4 (§1.13).
- **Speak → Writing** lives on the Speak side (below), because a Speak request is not a registry project (ruling 4).
- **R33 from the Books side** is the ruling-11 link (§1.5), not a transfer.

**Refusals.**
- Everything outside T1–T6 answers `422 {reason: transfer_not_supported, to_product, scope, kind}`. That includes:
  - a `to_product` outside the three values, including `autonomous`, `speak` and `books`;
  - any transfer of an `interest` row;
  - any transfer of a `reading` row other than T6;
  - a partial transfer to `research`;
  - a partial transfer, or a whole transfer with a selection, from a row without `research`.
- A whole transfer into a product that is already present is `409 {reason: product_present}`.
- A transfer from or into an archived project is `409 {reason: project_archived, project_id}`.

#### Candidates (rev 9)

`GET /projects/{id}/transfer-candidates?to_product=&to_project_id=&cursor=&limit=` is owner-scoped, reads through `connect_read`, and writes nothing. `limit` is 1–200, default 50.

```
{
  to_product,
  offers: {
    whole:   {available: bool, reason: null | "product_present" | "transfer_not_supported" | "project_archived"},
    partial: {available: bool, reason: null | "product_present" | "transfer_not_supported" | "project_archived"}
  },
  items: TransferCandidate[],
  next_cursor: string | null
}

TransferCandidate =
  | {candidate_kind: "investigation", investigation_id, title, state, excerpt: GatedText,
     pinned_node_ids: string[] | null, unavailable_reason: null | "no_synthesis", already_in_target?}
  | {candidate_kind: "document", document_id, title | null, author | null, document_type, is_book,
     gate, reason, already_in_target?}
  | {candidate_kind: "node", node_id, investigation_id, content: GatedText, already_in_target?}
```
- **`offers`** tells the client, before any POST, which scopes this project can use for `to_product`. The UI therefore never meets `422 transfer_not_supported`, which Part 2 draft §B7 treats as a lane-A bug. For a `kind: reading` row, `to_product: research` offers `whole` (T6) only, and every other target offers nothing. For a `kind: interest` row nothing is offered.
- **To `writing`:** the project's `investigation` members, oldest membership first.
  - `title`, `state` and `excerpt` are §1.2's `ThreadSummary` fields.
  - `pinned_node_ids` are the pinned nodes of the thread's latest depositable synthesis: the set that the repaired promotion (§1.11) places.
  - A thread with no depositable synthesis is listed with `unavailable_reason: no_synthesis`. It is never dropped.
- **To `reading`:** documents first, then nodes.
  - **Documents** are the reader-openable documents (§1.5 create; per the LB-35 spec) that the project's member threads cite, resolved the way §1.2 resolves `source_count`, plus the project's `document` members. Books (`is_book`) come first. `gate` and `reason` come from §1.5's one gate projection, and a document the reader may not serve is listed with its gate, never dropped.
  - **Nodes** are the insight nodes (`node_type='insight'`, `substrate/graph/insight_question.py@b41f4ec9b` ("writers of ``node_type='insight'``")) of each member thread, taken from that thread's distill read (`interfaces/research/api/distill_routes.py@b41f4ec9b` ("@distill_router.get(\"/{investigation_id}/distill\", response_model=DistillationOut)")). That this read is the per-thread source of insight ids is INFERRED, from the grounding's R19 row.
  - A node's `content` is composed by the §1.10 rights-gated pack (LB-24a). Until LB-24a lands it is `withheld · unresolved`, failing closed. The node stays selectable by its id.
- **To `research`:** there are no items, because T6 takes no selection.
- **`to_project_id`**, when given, must be an owned project with `to_product` present. Each item then carries `already_in_target`, so lane A can show an honest "n new since transfer" (Part 2 draft §B7).
- **Paging.** The order is stable across pages, and `next_cursor` is null on the last page.

#### Transfer request (rev 9)

```
POST /projects/{id}/transfers
{
  to_product: "research" | "writing" | "reading",
  scope: "whole" | "partial",
  to_project_id?: string,                               // partial only: an existing target
  new_project?: {kind, title?, primary_document_id?},   // partial only, when to_project_id is absent
  selection: {investigation_ids?: [], node_ids?: [], document_ids?: []},
  idempotency_key: string                               // 1..128 characters of [A-Za-z0-9_-]
}
```
- **`new_project`** is added by rev 9. The grounding's shape left a new target's kind and title implicit.
  - Its `kind` is `project` for `writing`, and `reading` or `interest` for `reading`.
  - A `reading` target names its `primary_document_id`. That document must be one of `selection.document_ids` and must be reader-openable and classified (§1.5).
  - An `interest` target needs a `title`. Every other target defaults to the source's title.
- **Target fields by scope.** A partial transfer needs exactly one of `to_project_id` and `new_project`; otherwise the answer is `transfer_invalid · target_required`. A whole transfer takes neither; otherwise the answer is `transfer_invalid · target_not_allowed`.
- **Named target.** It must be owned (`404 project_not_found`) and must not be the source (`transfer_invalid · target_is_source`). It must not be archived (`409 project_archived`), and `to_product` must already be present on it (`transfer_invalid · target_not_in_product`).
- **A book already has its project.** Suppose a `new_project {kind: reading}` names a document that already has the owner's `kind: reading` row. The transfer then targets that row as if it had been named. `target_created` is false, and the row's `derived_from_project_id` is not set.

**Selection (rev 9).**
- **Normalised form.**
  - `investigation_ids` keep their order, because it is the section order. Repeats are dropped.
  - `document_ids` keep their order, because it is the shelf order. Repeats are dropped.
  - `node_ids` are sorted and made unique.
- **Bounds.** At most 50 investigations, 1,000 documents and 1,000 nodes. Beyond that the answer is `transfer_invalid · too_many`.
- **`selection_digest`** is sha256 over the normalised selection as canonical compact UTF-8 JSON: keys sorted, no whitespace, `ensure_ascii` off, as for §1.6's tree bound.
- **Request identity** is sha256 over the canonical JSON of `{owner, from_project_id, to_product, scope, to_project_id, new_project, selection_digest}`.

**Selection rules per effect.**
- `presence` and `promote_book` take an empty selection. Anything else is `transfer_invalid · selection_not_allowed`.
- `seed_deliverable`:
  - requires `investigation_ids` and accepts `node_ids`;
  - refuses `document_ids` with `transfer_invalid · selection_kind_invalid`;
  - requires each investigation to be a `thread` (§1.2) that is a candidate with a depositable synthesis, else `transfer_invalid · no_synthesis`, naming the investigations;
  - requires each node to be pinned by some selected investigation, else `transfer_invalid · node_not_in_selection`;
  - when `node_ids` is given, requires every selected investigation to keep at least one node, else `transfer_invalid · empty_section`.
- `seed_shelf`:
  - accepts `document_ids`, and, for a partial transfer only, `node_ids`;
  - refuses `investigation_ids` with `selection_kind_invalid`;
  - requires each document to be a candidate that the shelf admits (§1.5 shelf), else `transfer_invalid · not_reader_openable` or `transfer_invalid · document_unclassified`;
  - requires each node to be an insight, else `transfer_invalid · node_not_insight`.
- A partial transfer needs a non-empty selection, else `transfer_invalid · selection_required`.
- Anything outside the candidate set is `transfer_invalid · selection_not_candidate`, naming the ids.
- Items are re-validated at commit, so a stale candidate list cannot place a member that the source no longer holds.

#### What each effect writes (rev 9)

One `connect_write` transaction holds all of it, through the outbox:
- the registry changes and the members;
- any deliverable and its blocks;
- the `project_transfers` row;
- `project.transferred` and every seam event.

A fault anywhere leaves none of them. The `place_block` constraint from §1.5's writing seeds applies here too.

| Effect | Writes |
|---|---|
| `presence` | `products[]` gains `to_product`, and nothing else changes. The mode's kept tree, if any, reappears (T9). |
| `seed_deliverable` | Sections go into the target's `primary` deliverable, or into a new deliverable that becomes its primary. There is one new section per selected investigation, in selection order. Each section is built as the repaired promotion (§1.11) builds its one section: the synthesis's pinned nodes become `graph_node` blocks, and dangling nodes are placed, never dropped. `node_ids` narrows the sections. A later transfer appends new sections and never edits an existing one. **Whole (T2):** `products[]` gains `writing`. **Partial (T3):** each selected investigation also becomes an `{investigation, null}` member of the target. A new target is `{home_product: writing, kind: project, products: [writing], derived_from_project_id: <source>}`. |
| `seed_shelf` | Selected documents are appended to the target's shelf in selection order. A `context` document becomes `shelf`, and a document already on the shelf, or the primary, keeps its place. `shelf_version` is incremented. **Whole (T4):** `products[]` gains `reading`. **Partial (T5):** a new target is `{home_product: reading, kind: reading \| interest, products: [reading], primary_document_id?, derived_from_project_id: <source>}`. Its primary document is `{document, primary}`, and the other documents are `shelf` rows. Each selected node becomes a `{node, context}` member of the target and writes one `seam.research_to_read` (below). |
| `promote_book` | `kind` becomes `project` and `products[]` becomes `[research, reading]`. Nothing else changes. |

#### Record and listing (rev 9)

NEW table `project_transfers`:
```
project_transfers (
  owner_user_id      VARCHAR NOT NULL,
  transfer_id        VARCHAR PRIMARY KEY,        -- xfr-<uuid4 hex>
  idempotency_key    VARCHAR,                    -- null only for a keyless Speak send
  request_sha256     VARCHAR NOT NULL,
  source_kind        VARCHAR NOT NULL,           -- project | speak_project
  from_project_id    VARCHAR,                    -- set exactly when source_kind = 'project'
  speak_project_id   VARCHAR,                    -- set exactly when source_kind = 'speak_project'
  to_project_id      VARCHAR NOT NULL,
  to_product         VARCHAR NOT NULL,
  scope              VARCHAR NOT NULL CHECK (scope IN ('whole', 'partial')),
  effect             VARCHAR NOT NULL,           -- presence | seed_deliverable | seed_shelf | promote_book | speak_draft
  target_created     BOOLEAN NOT NULL,
  selection_json     VARCHAR NOT NULL,           -- the normalised selection
  selection_digest   VARCHAR NOT NULL,
  deliverable_id     VARCHAR,
  created_at         TIMESTAMPTZ NOT NULL,
  UNIQUE (owner_user_id, idempotency_key)
)
```
- **POST response.** `POST` answers `201 {transfer, source, target}`, where `source` and `target` are project rows. For a whole transfer they are the same row.
- **Replay.** A replay answers `200` with the same shape, with the rows as they are now, and writes nothing.
  - The replay check reads `project_transfers` before any write. That short-circuit is what keeps a retry to one transfer, one deliverable and no second seam event.
  - Without it, a fresh envelope under a reused `operation_id` would make the outbox raise (§1.0a "The outbox").
- **Conflict.** The same key with another identity is `409 {reason: idempotency_conflict, transfer_id}`.
- **Listing.** `GET /projects/{id}/transfers?direction=from|to|any&cursor=&limit=` defaults to `any`, with `limit` 1–200 and default 50.
  - It answers `{transfers[], next_cursor}`, newest first.
  - Each item is the record, with `selection` in its normalised form.
  - It also lists Speak sends into the project.
  - Lane A's lineage chip reads `derived_from_project_id` together with `?direction=to`.

#### Lineage event (rev 9)

`project.transferred {transfer_id, source_kind, from_project_id | null, speak_project_id | null, to_project_id, to_product, scope, effect, selection_digest, target_created}`.
- **Where it is written.** A registry transfer writes it on the source project's log. A Speak send writes it on the Writing project's log, because no registry source exists. Its `operation_id` is `project.transferred:<transfer_id>`.
- **Whole transfers.** `to_project_id` equals `from_project_id`.
- **The target's log,** when the target is a different project, receives either `project.created {via: transfer, derived_from_project_id}`, or `project.members_changed` and `project.shelf_changed` with `{cause: transfer, transfer_id}`.
- **`derived_from_project_id`** is set only when the transfer creates the target.
- The payload carries ids and enums only (§1.5 **Events**).

#### Seam events, written beside `project.transferred` (rev 9; lane A's request C8)

The typed seam events exist and have no emitter on main. The trail reader already reads them from every log (`interfaces/research/api/thread.py@b41f4ec9b` ("Scan every investigation's event log for ``seam.*`` events")).
- **T5 partial.** It writes one `seam.research_to_read {entity_id: <insight node id>, provenance_ref: <transfer_id>}` per selected node.
  - These go on the source's log, in the same transaction as `project.transferred`, with `operation_id` `seam.research_to_read:<transfer_id>:<node_id>`.
  - The payload fixes `entity_kind` to `insight_node` (`substrate/schemas/events.py@b41f4ec9b` ("class SeamResearchToReadPayload(_SeamPayloadBase):")). A selection of documents only writes none, and so does a whole T4.
- **Speak send.** It writes one `seam.speak_to_write {entity_id: <claim_id>, provenance_ref: <transfer_id>, contributor_interview_ids}` per composed claim (`substrate/schemas/events.py@b41f4ec9b` ("class SeamSpeakToWritePayload(_SeamPayloadBase):")).
  - These go on the Writing project's log, beside that send's `project.transferred`, with `operation_id` `seam.speak_to_write:<transfer_id>:<claim_id>`.
- **References only.** Seam payloads carry references, never content (`substrate/schemas/events.py@b41f4ec9b` ("a copied entity would show up here as inlined content")).
- **No other seams.** No other transfer writes a seam event. Main has no research → write seam type, and rev 9 adds none.
- **Server-owned.** Both seam types join §1.16's server-owned list, so a client cannot forge a hop on the trail.

#### Speak → Writing on the Speak side (rev 9; ruling 4; LB-15, LB-18)

EXTEND `POST /speak/projects/{speak_project_id}/draft` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("@speak_router.post(\"/projects/{project_id}/draft\")")). Its body today is `{public}` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("class DraftRequest(BaseModel):")).

```
request:  {public?: bool, claim_ids?: [], interview_ids?: [], to_project_id?: string, idempotency_key?: string}
response: today's fields, plus
          {project, transfer_id, filtered_claims[{claim_id, cause: taken_down | no_record_consent}]}
```

**Owner.** The owner is the request owner, from middleware. The Speak request must pass LB-15's Speak owner predicate; otherwise the route gives Speak's own not-found answer.

**The Writing project.**
- **Named.** `to_project_id` must name an owned project with `writing` present. Otherwise the answer is `404 project_not_found` or `409 {reason: product_absent, product: writing}`.
- **Found.** Without `to_project_id`, the route reuses the owner's project that holds `{speak_project, <id>}` and has `writing` present.
- **Created.** If there is no such project, the route creates `{home_product: writing, kind: project, products: [writing], title: <the request's title>}` and writes `project.created {via: speak_draft}`.
- **Ambiguous.** If there are several, the answer is `409 {reason: target_ambiguous, project_ids[]}`.

**Members.** The project gets `{speak_project, <id>, null}`, which is a link only (ruling 4), and `{deliverable, <deliverable_id>}`. The deliverable's role is `primary` when the project has none.

**The deliverable.** It is `interview_projects.deliverable_id` once that is set (LB-15; lane-A default 4). Today every call mints a new deliverable: the route passes none, and `assemble_outline` inserts one whenever none is given (`substrate/speak/biography.py@b41f4ec9b` ("if deliverable_id is None:")).

**Claims.**
- Only claims with no active takedown and a `record` consent are composed (LB-15). The consent scopes are at `substrate/speak/schema.py@b41f4ec9b` ("CHECK (scope IN ('record', 'attribute', 'publish'))").
- `claim_ids` or `interview_ids` narrow the set further; the scope is then `partial`. With neither, the scope is `whole`.
- Every excluded claim is listed in `filtered_claims` with its cause.

**One transaction.** The Speak tables live in the graph DB (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("Resolve + initialize the graph DB (base schema)")). These therefore commit together, through the outbox:
- the registry row and the members;
- the deliverable and its blocks;
- the `project_transfers` row, with `source_kind: speak_project`, `to_product: writing` and `effect: speak_draft`;
- `project.transferred` and the seam events.

**Idempotency.**
- **With a key.** `idempotency_key` replays the first answer, and a changed identity answers `409 idempotency_conflict`. The identity is computed over the normalised `claim_ids` and `interview_ids` (each sorted), `public` and `to_project_id`.
- **Why the key is optional.** In rev 9 the key is optional, because an existing caller sends none (`apps/reading/src/lib/speakApi.ts@b41f4ec9b` ("/draft`")).
- **Without a key.** A call is a new send, with its own `transfer_id` and seam events. The project and the deliverable are still reused through their natural keys.
- **Lane A's caller.** Lane A's A19 sends the key.

**Text in Write.** The composer copies claim text into `outline_blocks` (`substrate/speak/write_composer.py@b41f4ec9b` ("content = (b.body or b.label or \"\").strip()")). Rev 9 does not treat that copy as a precedent (D-P). Instead, §1.11 rev 9 gates `speak_claim` blocks at serve time and refuses share or export with `422 speak_publish_required` (O-12's fallback).

#### Errors (rev 9)

| Status | Body |
|---|---|
| 403 | `{reason: not_owner, ref}` for a selected thread with a recorded owner mismatch |
| 404 | `project_not_found` for the source or a named target; `{reason: thread_not_found, ref}` for a selected thread that is not a `thread`; `{reason: source_not_found, ref}` for any other missing selected item |
| 409 | `{reason: idempotency_conflict, transfer_id}`, `product_present`, `{reason: project_archived, project_id}`, `{reason: product_absent, product}` (Speak side), `{reason: target_ambiguous, project_ids[]}` (Speak side) |
| 422 | `{reason: transfer_not_supported, to_product, scope, kind}`; `{reason: transfer_invalid, detail, …}`, where `detail` is one of `selection_required`, `selection_not_allowed`, `selection_kind_invalid`, `selection_not_candidate`, `node_not_in_selection`, `node_not_insight`, `empty_section`, `no_synthesis`, `not_reader_openable`, `document_unclassified`, `too_many`, `target_required`, `target_not_allowed`, `target_is_source`, `target_not_in_product` or `new_project_invalid`; `idempotency_key_invalid` |

`422 speak_publish_required` is not a transfer error. It is §1.11 rev 9's refusal of a share or export that contains testimony.

#### Acceptance, red-first (LB-18 plus rev 9)

1. **Partial Research → Writing.** It places only the selected nodes, sets `derived_from_project_id` on the new target, and leaves the source's members unchanged. A whole transfer keeps the id.
2. **T4 and T6.** T4 keeps the id and adds `reading`. T6 keeps the id, members, threads and primary document, and changes the kind.
3. **Retry.** A retry with the same key yields one `project_transfers` row, one deliverable and one `seam.research_to_read` per node, and nothing a second time.
4. **Speak reuse.** Two Speak sends reuse one Writing project and one deliverable.
5. **Takedown after send.** A Speak claim taken down after the send has its block text withheld on the next serve (§1.11 rev 9). This is red on the base, because the copy survives.
6. **Testimony export.** A Write export that contains testimony answers `422 speak_publish_required` (§1.11 rev 9).
7. **Non-servable book.** It is a candidate with its gate and reason, and is never dropped.
8. **Books lens.** A thread off the shelf is hidden in the Books lens and visible in Research (§1.2).
9. **Unsupported transfers.** `to_product: autonomous`, and every pair outside T1–T6, answer `422 transfer_not_supported`. `offers` reports the same before any POST, including every offer on a `kind: interest` row and `to_product: writing` on a `kind: reading` row.
10. **Atomicity.** A fault injected after the `project_transfers` insert leaves no row, no member, no `project.transferred` and no seam event.
11. **Trail.**
    - After a T5 partial, the trail reader's `build_thread(<insight node id>)` shows a research → read hop whose `provenance_ref` is the `transfer_id`.
    - A T5 that selects documents only writes no seam event.
12. **Named target lineage.** A named target keeps its own `derived_from_project_id`.
13. **Present product.** A whole transfer into a product that is already present answers `409 product_present`.
14. **Leave and return.** Leaving Writing and then transferring whole back to Writing (T1) restores the kept tree unchanged, with its numbers.

**Prod probes (DB-B, read-only).** `GET /projects/{id}/transfer-candidates` and `GET /projects/{id}/transfers` must answer with the API's own JSON, never the SPA.

### 1.6 Tab tree: rev 9 deltas (LB-17, LB-19; S9, S15)

**What LB-2 allows today (PR #3530 at `ee6867a11`).**
- A node carries only the allowlisted keys (`substrate/projects/tabs.py@ee6867a11` ("\"hier_number\", \"branch_origin\", \"opened_by\", \"child_order\", \"last_visited_child_id\", \"pruned_at\",")). There is no `transient`, so lane A's transient tab (Part 2 draft §A2) is refused `422 tab_tree_invalid` today.
- `branch_origin` takes the keys `{document_id, anchor, kind}` (`substrate/projects/tabs.py@ee6867a11` ("_ORIGIN_KEYS = frozenset({\"document_id\", \"anchor\", \"kind\"})")) and requires `document_id` (`substrate/projects/tabs.py@ee6867a11` ("\"branch_origin.document_id is required\"")).
- A restore may not change what the tab is or where it came from (`substrate/projects/tabs.py@ee6867a11` ("_RESTORE_IDENTITY = (\"side\", \"kind\", \"ref\", \"branch_origin\", \"opened_by\")")).

**Mode keys are unchanged (rev 9; ruling 1).** `mothership` stays `research | writing | reading`, with no alias. An unknown key, `books` included, stays `404 mothership_unknown` (THREAD-CONTRACT.md@e39840224 §1.6 ("`404 mothership_unknown` covers an unknown mode key"); `interfaces/research/api/project_routes.py@ee6867a11` ("raise HTTPException(status_code=404, detail=\"mothership_unknown\")")). So `/tabs/books` answers 404, not the 422 that LB-17's acceptance list states.

**Presence gates tab writes (rev 9; D-P).**
- `PUT /projects/{id}/tabs/{mothership}` and `POST …/allocate`, for a mode that is not in the project's `products[]` (§1.5), answer `409 {reason: product_absent, product}` and write nothing.
- `GET …/tabs/{mothership}` and `GET …/retired` still answer, because a mode's tree is kept when the project leaves it.
- The checks run in this order: the project (`404 project_not_found`), the mode key (`404 mothership_unknown`), presence (`409 product_absent`), then the version and the body.
- **Why.** This is how the server keeps Part 2's "never a silent append" (Part 2 draft §A1, `not_in_mode`). A tab write can no longer give a project a mode that its `products[]` does not list. It changes LB-2's behaviour, which accepts a write in any known mode.

**`transient` (rev 9; S15; Part 2 draft §A2).** A node gains `transient?: bool`, default false, as an allowlisted key.
- **Who may set it.** `transient: true` is accepted only on a new node (a `tab_id` that is not in the accepted tree and has no unrestored retirement) that is on `side: left`, in `mothership: reading`, with `branch_origin.kind: agent` and `opened_by` present. Lane A opens such a tab from an agent's answer ref (§1.12a, "What an agent can do"). Anything else is `422 {reason: tab_origin_invalid, tab_id, detail: transient}`.
- **One direction.** An accepted node's `transient` may change only from `true` to `false`. `false` to `true` is `422 {reason: tab_tree_invalid, tab_id, detail: transient}`.
- **Keep** is two operator writes, in this order:
  1. `POST /projects/{id}/members {member_kind: document, member_id, member_role: context}` (§1.5). A retry answers `200 already_member`.
  2. A tab PUT that clears `transient` on that node.

  The server never edits a tree on a member write, because tabs are navigation state, not provenance. The member write comes first, so a tab never reads as kept while its document is not a member.
- **Close and restore.** Closing an unkept transient tab retires it like any other tab, with its complete node, and it is restorable. `transient` joins the "Unchanged means (rev 8.9)" identity (THREAD-CONTRACT.md@e39840224 §1.6 ("**Unchanged means (rev 8.9):**")): a restored node matches its retired node on `transient` too, except that `true` may become `false` in the restoring PUT.
- **Not membership.** A transient tab's document is not a project member until Keep, so it is not in the Books lens's document set (§1.2).

**Output anchors on tab nodes (rev 9; S9; moved here from the threads cluster's §1.4 text).**
- `branch_origin` keys gain `output_anchor`.
- `kind: selection` carries exactly one of `document_id` and `output_anchor`. `document_id` stays required on every other kind.
- The `output_anchor` keys are a subset of `{thread_id, event_id, path, segment_id, segment_sha256, start, end, selection_sha256, normalization, node_id}`.
- `quote`, `prefix` and `suffix` are refused. The GET returns tab rows verbatim with no gate, so a quote stored there would outlive a takedown of the text it quotes (§1.4b's served-only rule).
- The PUT checks shape only:
  - strings are bounded;
  - the hashes are 64 lowercase hex characters;
  - the offsets are integers with 0 ≤ `start` < `end`;
  - `path` matches the §1.4b grammar;
  - `segment_id` equals `<event_id>#<path>` when present.
- The PUT never reads a log. Any failure is `422 {reason: tab_origin_invalid, tab_id, detail}`.
- A restore's unchanged `branch_origin` includes `output_anchor`.

**Retirements.** A retired node's `node_json` is the whole node, so it carries `transient` and `branch_origin.output_anchor` like every other field (THREAD-CONTRACT.md@e39840224 §1.6 ("`node_json` is the whole Part 2 §2.2 node")).

**Acceptance (red-first).**
- A PUT in a mode the project has left answers `409 product_absent` and writes nothing; the GET of that mode still answers. This is red on LB-2.
- `transient: true` on a left `agent` node in the reading mode is accepted and returned. The same flag on a right node, in another mode, or on a non-agent node answers `422 tab_origin_invalid`. This is red on LB-2, which refuses the key.
- Clearing `transient` is accepted, and setting it again answers 422.
- A restored transient node keeps `transient` unless the restoring PUT clears it.
- An `output_anchor` with a `quote` answers `422 tab_origin_invalid`. A valid one round-trips unchanged.
- `/tabs/books` answers `404 mothership_unknown`.

### 1.7 Push: rev 9 deltas (one broadcast list)

The socket rules stand (THREAD-CONTRACT.md@e39840224 §1.7 ("Only **broadcast** events reach the socket")). Every event below is **broadcast** after it is durably written, on `/ws/events`, with the envelope's `investigation_id` set to the log it was written to. The socket carries no owner filter (§1.15), so a client treats every push as a nudge and refetches through an owner-scoped read.

| Event | Log | Section |
|---|---|---|
| `investigation.branched` (every launch path, not only chase) | the parent | §1.3 |
| `thread.dialogue_started`, `thread.turn_requested`, `thread.turn`, `thread.turn_failed` | the dialogue | §1.8 |
| `thread.merge_draft_requested`, `thread.merge_drafted`, `thread.merge_draft_failed`, `thread.merge_draft_revised`, `thread.merge_started` | `merge-<hex>` | §1.10 |
| `investigation.merged_into` | each member | §1.10 |
| the merged thread's `investigation.start_requested` | the new thread | §1.10 |
| `thread.merged_in`, `agent.promoted`, `agent.charter_revised`, `thread.context_attached` | the agent | §1.10, §1.12a |
| `project.created`, `project.updated`, `project.members_changed`, `project.shelf_changed`, `project.product_left`, `project.transferred` | `project-<id>` | §1.5, §1.5a |
| `project.tabs.version_bumped` (broadcast only, never appended) | `project-<id>` | §1.6 |
| `question.identified` (a read flag), `question.flag_declined` | the flag's log | §1.13 |
| `reformat.generated` (per chapter), `reformat.failed`, `reformat.audio_rendered`, `reformat.audio_render_failed` | the reformat thread | §1.11a |
| `companion_document.refreshed` | its scope | §1.12 |
| `speak.answer.received`, `speak.claims.proposed` | the Speak project's log | §1.13 inbox |

`answer.provenance` and `thread.context_receipt` are not broadcast. They are returned by the route that wrote them and read through that route's GET, so the socket never carries a receipt.

### 1.8 Ask and dialogue (rev 9 rewrite of tier 0; LB-21, LB-22, LB-27)

**What changes from rev 8.10 (rev 9).**
- **The route.** Tier 0 is a NEW route, `POST /investigations/{id}/ask`, on a `dialogue` thread only. It replaces THREAD-CONTRACT.md@e39840224 §1.8 ("EXTEND `POST /thought-partner`") and (THREAD-CONTRACT.md@e39840224 §1.8 ("The route shape is `POST /investigations/{id}/ask {question, context_items[]}`")).
- **What it reuses.** It reuses the thought-partner dispatch pieces:
  - `compose_thought_partner_prompt`;
  - `parse_thought_partner_response`;
  - `dispatch(…, "thought_partner", …)`, whose tier is set in `substrate/dispatch/config.yaml@b41f4ec9b` ("thought_partner: pro").
- **`/thought-partner` itself** (`interfaces/research/api/app.py@b41f4ec9b` ("\"/thought-partner\",")) is not edited while #3278 and codex-r15 own it. It keeps its `__sidecar__` default (`interfaces/research/api/app.py@b41f4ec9b` ("investigation_id=req.investigation_id or \"__sidecar__\"")).
- **Where turns live.** A turn never lands on a research thread or on an agent's own log (D-A).
  - "Ask this thread" branches a dialogue child: origin `{kind: research, purpose: ask}`, or a selection with `purpose: ask` (§1.3). It then asks on that child.
  - Asking a non-dialogue answers `422 {reason: not_a_dialogue, kind}`.
  - Rev 7's §2.4 wording, that the turn persists on the addressed thread, is superseded (Appendix B).
- **Talking is built** (ruling 18; §1.11a). Turns are turn-by-turn (ruling 14). There is no duplex route and no streamed audio input.

#### Dialogue threads (rev 9)

**Create.** `POST /investigations {kind: "dialogue", scope, participants?[], title?, investigation_id?, parent_investigation_id?, origin?}`

**`scope` is a union, `{project_id} | {document_id}`** (DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27"). It stays a union because TalkToBook needs a book scope.
- `{project_id}` must be a §1.5 registry project the caller owns. Otherwise `404 {reason: project_not_found}`. A Speak `interview_projects` id is not a registry project, so it answers the same.
- `{document_id}` must be an existing document the caller can read. Otherwise `404 {reason: document_not_found}`.
- Any other key, including any Speak key, or anything other than exactly one of the two, answers `422 {reason: scope_invalid, detail}`. There is no Speak scope (ruling 16).

**Kinds of dialogue.** Every dialogue is exactly one of these, and `ThreadSummary.dialogue_kind` (§1.2) names it:

| Dialogue (`dialogue_kind`) | `participants` | Parent | Scope | Its id |
|---|---|---|---|---|
| **Agent session** (`session`), or a **group** (`group`) (D-A; ruling 20) | 1 agent, or 2 to 4 | none | `{project_id}` | server-derived from its natural key |
| **Converse / plain project dialogue** (`plain`) | `[]` | none | `{project_id}` | client-minted `investigation_id` |
| **Branched dialogue** (`branched`; `purpose: ask`, or "Ask this thread") | `[]` | a research thread | `{project_id}`, the project whose tree holds the parent's tab | client-minted `investigation_id` |
| **Book session** (`book`; TalkToBook) | `[]` | `read-<document_id>`, set by the server | `{document_id}` | client-minted `investigation_id` |

**Sessions (rev 9; D-A).**
- A session is found or created on its natural key: the owner, the sorted participants and `project_id`.
- **The id.** It is `inv-` followed by the first 24 hex characters of `sha256("session" ␀ owner ␀ project_id ␀ join(",", sorted participants))`.
- **The start event.** `thread.dialogue_started` is written with `emit_typed(…, event_id=<deterministic from the thread id>, idempotent=True, strict_write=True)` (`substrate/event_log/events.py@b41f4ec9b` ("idempotent typed emission requires an explicit event_id")). Two concurrent creates therefore converge on one session, and neither needs a scan.
- A session create must not send `investigation_id`. If it does, the answer is `422 {reason: launch_invalid, detail: session_id_is_derived}`.
- The same agent in the same project always reaches the same session. From another project it reaches a different session, so T8 holds as membership.
- **Participants are checked at create and again at every ask.** Each participant:
  - must be a `thread` (§1.2) and a promoted agent (`agent.promoted` on its log, §1.12a). Otherwise `422 {reason: participants_invalid, detail: not_an_agent}`.
  - must be the caller's. Otherwise `403 {reason: not_owner, ref}`.
  - must be an `agent` or `managed` member of the scope project. Otherwise `422 {reason: participants_invalid, detail: not_a_member}`.

  The list as a whole:
  - may not repeat a participant: `{detail: duplicate}`;
  - may not exceed four participants: `{detail: too_many}`.

  Two combinations are refused:
  - a branched session: `{detail: branched_session}`;
  - participants on a document scope: `{detail: book_session_has_no_agents}`.
- **Until §1.12a lands,** any participant answers `422 {reason: participants_invalid, detail: agents_unavailable}`. Plain dialogues do not wait for it.

**A branched dialogue (rev 9).** It is validated like any §1.3 branch: the same order, codes and served check, with no charge.
- It writes `investigation.branched {via: api, origin}` into the parent, then the child's start event.
- A purpose `ask` with a document `anchor` requires `scope: {document_id: anchor.document_id}`. That makes it a book session anchored at the passage. Otherwise `422 {reason: launch_invalid, detail: scope_origin_mismatch}`.

**A book session (rev 9).**
- The server sets the parent to `read-<document_id>`. A client parent other than that answers `422 {reason: scope_invalid, detail: parent_mismatch}`.
- The branch is written with `via: api` and `origin {kind: manual | selection, document_id, anchor?}`.
- The validated document stands in for B0's parent-log check, so a book that has no `read-` log yet gets one from this write.
- `read-<doc>` is keyed per document, not per owner. That is pre-multi-user work, listed in §1.15.

**What a create writes (rev 9).** Validation comes first, then the branch (branched dialogues and book sessions), then one `connect_write` transaction through the outbox (`substrate/write/event_outbox.py@b41f4ec9b` ("Commit a mutation and its outbox intent under the global writer lock")). It holds two writes:
- `thread.dialogue_started {kind: "dialogue", scope, participants[], title | null, owner_user_id, project_id | null, parent_thread_id | null, origin | null}`, where `owner_user_id` comes from `request_owner_user_id`. On a document scope, the envelope's `document_id` is the scope's document, so the existing `document_id` filter finds it.
- For a `{project_id}` scope, the `write_folder_members` row `{member_kind: investigation, member_role: null}` and `project.members_changed {cause: dialogue}`. Membership is the authority for a project's threads (D-P).

**The response.** `200 {thread_id, investigation_id, start_event_id, branch_event_id | null}`, with the same body on a replay.
- A plain or branched dialogue replays on the same `investigation_id` with the same body.
- A different body, or an id that already holds another kind's start, answers `409 investigation_id_conflict`.
- `title` is 1 to 200 scalars when present. Before any turn, lane A shows "New conversation"; after that, the first question.

#### The ask (rev 9)

**The route.** `POST /investigations/{id}/ask`, where `{id}` is a dialogue. The body forbids unknown fields.
```
{
  question,                 // 1..2000 scalars after normalize_node_text (AskBookRequest's bound)
  input?: Input,            // §1.19; absent = {modality: "text"}
  at?: At,                  // "at" below
  context_items?: ContextItem[],  // ≤ 20 (the ComposeContextRequest bound), §1.9 kinds
  model_choice?: UserModelChoice, // owner BYOT, below
  confirm_unpriced?: bool,  // group turns only, below
  mothership?: "research" | "writing" | "reading",  // attribution only (§1.13); null from a door
  idempotency_key           // 1..128
}
```
- `question` is the settled payload name (DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27").
- The 20-item bound is `ComposeContextRequest`'s (`interfaces/research/api/app.py@b41f4ec9b` ("items: list[ContextItem] = Field(..., min_length=1, max_length=20)")).
- The body has no `system_context`, `history` or `operation_id`:
  - Context comes only from the context rules below. `/thought-partner` accepts client `system_context` (`interfaces/research/api/app.py@b41f4ec9b` ("system_context: str | None = None")), and a client could inject model context through it.
  - History is read from the session's own turns.
  - `idempotency_key` is the owner operation id.

**Refusals.**
- `404 {reason: not_found}`: the id is not a `thread` (§1.2), or it is another owner's.
- `422 {reason: not_a_dialogue, kind}`: the thread is not a dialogue.
- `422 {reason: ask_invalid, detail}`. `detail` is one of:
  - `question_empty` or `question_too_long`
  - `input`
  - `at`, `at_span` or `at_foreign`
  - `context_items` or `context_items_on_group`
  - `mothership`
  - `unknown_field`
- `404 {reason: not_found}` also covers an `at` asset that is not the caller's, as in §1.11a. `422 {reason: revision_not_committed}` covers an `at` revision still generating.
- `422 {reason: model_selection_invalid}`: the code main already uses (`interfaces/research/api/app.py@b41f4ec9b` ("if (req.model_choice is None) != (req.operation_id is None):")).
- `409 {reason: owner_model_unavailable}`: see "Owner BYOT" below.
- `422 {reason: participants_invalid, detail}`: participants are re-checked at every ask.
- `422 {reason: confirmation_required, detail: unpriced}`: the one code for an unpriced confirmation, shared with §1.10.
- `409 {reason: idempotency_conflict}`.
- `409 {reason: turn_in_progress, turn_id}`.

**Identity and idempotency (rev 9).**
- **The turn id.** `turn_id` = `turn-` followed by the first 24 hex characters of sha256(owner, thread id, `idempotency_key`).
- **The request identity** is the sha256 of canonical JSON over:
  - the owner;
  - the thread id;
  - the normalized `question`;
  - `input` and `at`;
  - `context_items` in the order sent;
  - `confirm_unpriced` and `mothership`;
  - `model_choice`, or the literal `"default"` when it is absent.
- **Model binding** mirrors THREAD-CONTRACT.md@e39840224 §1.11a ("Model selection (rev 8.2)"). Without a `model_choice`, the `thought_partner` role's model is resolved once, at admission, and recorded on `thread.turn_requested.model`. Every attempt of that turn uses the recorded model, even if the default changes.
- **What a repeat of the same key gets:**

  | The key's turn | A repeat with the same identity gets |
  |---|---|
  | answered | `200`, the first turn, `replayed: true`, and no dispatch |
  | open (admitted, no terminal) | `409 turn_in_progress {turn_id}`. The client waits for the WS `thread.turn` |
  | failed with `unavailable` or `interrupted` | attempt n+1, with the same `turn_id`, capture and model, and one new dispatch |
  | failed with `owner_model_outcome_unknown` | the same `503` again. It is never retried, because provider I/O may have happened (`interfaces/research/api/books.py@b41f4ec9b` ("status_code=503, detail=\"owner_model_outcome_unknown\",")). A new press takes a new key. |

  The same key with a different identity answers `409 idempotency_conflict`.

**Admission (rev 9; single writer, no lock across the model call).** One `connect_write` transaction runs through the outbox:
1. It refuses with `409 turn_in_progress` when the session's newest admitted attempt has no terminal event. Every turn event goes through the outbox, and the global writer lock serializes admissions, so two concurrent asks cannot both pass. A second ask with a different key is refused while one is open.
2. For a voice input, it enqueues `voice.captured` (§1.19).
3. It enqueues `thread.turn_requested {turn_id, attempt, seq, request_identity, question, input, voice_capture_event_id | null, at | null, context_items, model: {authority, provider, model}}`.

Each outbox `operation_id` is `turn:<turn_id>:<attempt>:<kind>`, which the UNIQUE constraint keeps single (`substrate/graph/schema.py@b41f4ec9b` ("operation_id TEXT NOT NULL UNIQUE,")). The rows are delivered, and `thread.turn_requested` is broadcast. The context is then assembled read-only, and one dispatch runs with no lock held.

**The terminal (rev 9).** An answered turn writes these three events in one second outbox transaction, with event ids deterministic from `(turn_id, attempt, kind)`:
- `thread.turn`;
- `answer.provenance {answer_event_id: <that thread.turn's id>, retrieved_refs[], cited_refs[], presentation_mode}` (T7; THREAD-CONTRACT.md@e39840224 §1.11a ("Answer provenance and presentation (T7, ruled 2026-09-26)"));
- `thread.context_receipt` (below).

A failed turn writes only `thread.turn_failed`, and no receipt (lane A reads a receipt on every **answered** turn, Part 2 draft §B2). After commit the events are delivered and `thread.turn` is broadcast. The dispatch is then settled record-only through LB-23's `record_dispatch` (§1.13), with `dispatch_id = <turn_id>:<attempt>` and `kind: ask_turn | converse_turn | group_turn`. That is the conversational spend class: no admission, bounded by the role's `max_tokens` (INFERRED: no per-role bound is declared, so the package sets one), and never refused by the cap (O-16 fallback).

**The context receipt (rev 9; one payload, lane A's request C5).** Every answered turn writes exactly one sibling event on the dialogue's own log, and the ask response returns it. Lane A never computes it.
```
thread.context_receipt {
  turn_event_id, project_id | null,
  items: [{item_id, kind, step | null, via: assembler | turn | link,
           participant_thread_id | null, included,
           reason: budget | withheld | refs_only | depth_limit | null}]
}
```
- `kind` is `charter | pack_item | draft | turn | attached | context_item | chunk`.
- `step` is the §1.12a assembler step (1 to 7) for an `assembler` item, and null otherwise.
- `via: link` tags an item that a book session reached through the ruling-11 link layer (below).
- `participant_thread_id` tags each item of a group turn with the participant whose assembly produced it.
- `depth_limit` extends D-A's closed set of three reasons (§1.12a); lane A and the operator accept it at the co-sign.
- It is refs-only: it holds no text, so a receipt never stores what was withheld.
- `answer.provenance` and the receipt are not broadcast (§1.7). They are returned by the ask and by the turn reader.

**`thread.turn` payload (rev 9).** The stored form holds refs and answer text, never context text:
```
thread.turn {
  turn_id, attempt,
  question, input, voice_capture_event_id | null, at | null,
  answer: {text, origin: source | unsourced, source_refs[]},
  answer_spans: [{span_id, start, end, cited_item_ids[], supported,
                  origin_thread_id | null, reason: mixed | unsupported | null}],
  context_items: [{item_id, kind, pointers[], participant_thread_id | null,
                   gate_at_turn, reason_at_turn | null}],
  project_id | null,
  session_of: {agent_thread_id, project_id} | null,     // solo agent sessions
  contributions: [{participant_thread_id, contributed, reason: withheld | budget | empty | null}] | null,  // groups
  unknown_markers,
  model: {authority: platform | owner_byot, provider, model, dispatch_event_ids[]},
  cost_cents | null
}
```

**Answers are gated at read (rev 9).** Every route that returns a turn projects it at read time:
- `answer` becomes a `GatedText` under the live gate. It is `served` while every cited ref resolves to a servable document for the owner-read audience, and `withheld` otherwise, with the §1.2 reason precedence.
- Each `context_items` entry becomes a `GatedText` in `context[]`, re-read from its source under the live gate. This covers the cite-only and withheld items too, as signed at rev 6.
- A takedown therefore withholds an old answer, and the log never serves stale text.
- The model saw only served text, so at turn time the answer was served (THREAD-CONTRACT.md@e39840224 §1.8 ("**Tier 0 (W2): a conversational turn with the thread's context.**")).

**Citations and spans (rev 9; §1.0a "Model citation markers").**
- **Markers.** Each context item the model is shown carries a server-assigned marker `[[n]]`, and the answer cites by marker. INFERRED: the thought-partner prompt has no inline markers today, so this is new prompt and parser work.
- **What the server does with them.**
  - It resolves the markers to items.
  - It strips them, and one preceding space each, from the text.
  - It normalizes the result (`normalize_node_text`).
  - It partitions the non-whitespace text into UAX #29 sentences, the §1.11a sentence unit.
- **Spans.** Each sentence is one span. Its `cited_item_ids` are the markers that immediately follow its characters. `start` and `end` are Unicode scalar offsets into `answer.text` (§1.4b), so phase 2 can anchor into turns.
- **Unknown markers.** A marker naming no shown item is dropped and counted in `unknown_markers`. It never becomes a ref, so `cited_refs ⊆ retrieved_refs` holds by construction.
- **Supported and origin.** A span is `supported` when it cites at least one resolved item. The answer's `origin` is `source` when any span is supported, and otherwise `unsourced`: served to its owner with the unsupported mark, never labelled "Generated".
- **`source_refs`.** Every cited pointer that resolves to a document carries `document_id` and a §1.4 `anchor` when it names a passage (S1), so lane A can open it as a left tab.
- **`presentation_mode`.** The dispatch declares it, per T7. When none is declared it records `cited_quietly` (a rev-9 default the auditor confirms against T7).
- **A book session is the exception.** It takes its citations from `book_qa`, which cites the chunks it retrieved (`substrate/books/book_qa.py@b41f4ec9b` ("citations=_citations_from_chunks(context_chunks),")). So `cited_refs` equals `retrieved_refs`, and `answer_spans` is `[]`. `book_qa` does not attribute sentences, and the server does not pretend it does.

**Context, by dialogue (rev 9).** The first matching row applies. Prior turns of this dialogue enter as history in every row: they carry no marker, cannot be cited, and are listed on the receipt.

| Dialogue | Context | Reads |
|---|---|---|
| Agent session (solo) | LB-26's seven-step assembler for the scope project (§1.12a). There is no ambient step, so the project's other members are read only when attached. Per-turn `context_items` follow, as `via: turn`. | never the agent's own log for turns; `session_of` is set |
| Group session (2 to 4) | Each participant's assembler output for the group's project, fitted within one `reuse_token_budget` (`substrate/context_pack/knowledge_reuse.py@b41f4ec9b` ("def reuse_token_budget(")). Every item is tagged with its participant. Per-turn `context_items` are refused (`context_items_on_group`), which keeps attribution total. | no participant's log is written |
| Book session (`{document_id}`) | `answer_book_question` over the document (`substrate/books/book_qa.py@b41f4ec9b` ("def answer_book_question(")), with `investigation_id` = the session, `history` from its turns, the owner-read policy tag and, for owner BYOT, `authorized_dispatch`. The narrowed link layer below may add a read-only layer. | writes only its own log |
| Branched dialogue | The parent's `RightsGatedPack` (LB-24a), plus the focus segment re-resolved under the live gate, plus `context_items` | never the scope project's members |
| Converse (project, no agent) | The member threads' gated packs; chunk search restricted to member documents (`substrate/graph/search.py@b41f4ec9b` ("document_ids: Sequence[str] \| None = None")); member deliverables at their current revision under the owner serve-time gate, with `derived_asset_block_informs`, where a `speak_claim` block is gated by §1.11 rev 9; and `context_items` | registry members only; never Speak (ruling 16) |

Three rules apply to every row:
- **The policy tag is server-derived.** The §9.0 policy tag comes from `_owner_read_policy_tag`, as `/thought-partner` already does (`interfaces/research/api/app.py@b41f4ec9b` ("Reuse the one reviewed owner-read resolver")).
- **No account memory in rev 9.** The ask reads no account memory. `/thought-partner` does (`interfaces/research/api/app.py@b41f4ec9b` ("memory_context = account_memory_context(request, req.prompt)")), but D-A's assembler is the one context source and has no memory step. Memory joins only after R15's proposal-and-confirmation contract, as a later revision's step.
- **Nothing is written back.** No ask path writes account memory, a linked project or a participant's log.

**The ruling-11 link layer in a book session (rev 9; narrowed per lane-A default 2).**
- **The trigger.** The document is the `primary_document_id` of exactly one of the caller's `reading` projects, and that project carries a ruling-11 link-back to a research project.
- **What joins.** Only the linked research project's threads that grounded in or opened one of the book project's shelf documents (primary or `shelf`), by §1.2's `document_ids[]` rule, and only their served material. Every item joins read-only and is tagged `via: link` on the receipt.
- **What never joins.** Any other thread or member of the linked project. Nothing is written to it (ruling 11).
- **Otherwise** the session reads the book alone.
- The shelf and library reach of O-15's fallback is on `/books/{id}/ask` (below), not on sessions.

**Owner BYOT (rev 9).**
- `model_choice` is the owner-model shape `{authority: "user_model", provider_id, model_id}` (`interfaces/research/api/settings_models_admin.py@b41f4ec9b` ("class UserModelChoice(BaseModel):")). It is parsed by hand, so a validation error never reflects the values back, as `AskBookRequest` does (`interfaces/research/api/books.py@b41f4ec9b` ("class AskBookRequest(BaseModel):")).
- It is usable in any dialogue whose scope the caller owns:
  - for `{project_id}`, `write_folders.owner_user_id`;
  - for `{document_id}`, `documents.owner_user_id`, as book ask checks it (`interfaces/research/api/books.py@b41f4ec9b` ("if owner_row is None or not isinstance(owner_row[0], str):")).

  The owner is compared with `authenticated_distinct_owner` (`interfaces/research/api/owner_byot_dispatch.py@b41f4ec9b` ("def authenticated_distinct_owner(request: Request) -> str:")). An unowned scope, a mismatched one, or a machine caller answers `409 owner_model_unavailable`.
- A project never holds a key of its own.
- **How it dispatches.**
  - A book session dispatches through the talk-to-book owner path that already exists (`interfaces/research/api/books.py@b41f4ec9b` ("dispatch_talk_to_book_byot,")).
  - Every other dialogue needs #3278's thread-partner owner dispatch. Until #3278 lands, those answer `409 owner_model_unavailable`. The Sidecar sends `model_choice` today, and `/thought-partner` ignores it (`apps/reading/src/components/AISidecar.tsx@b41f4ec9b` ("ThoughtPartnerRequest (app.py) does not read model_choice yet")).
- An ask in a branched dialogue is a conversational dispatch, not a launch, so O-3 does not govern it.

**The response (rev 9).**
```
200 {
  turn: {turn_id, event_id, attempt, question, input, voice_capture_event_id | null, at | null,
         answer: GatedText, answer_spans[], context[]: GatedText[], project_id | null,
         session_of | null, contributions | null, model, cost_cents | null,
         provenance: {answer_event_id, retrieved_refs[], cited_refs[], presentation_mode}},
  context_receipt: {event_id, turn_event_id, project_id | null, items[…]},
  replayed
}
```
- **A dispatch failure** writes `thread.turn_failed {turn_id, attempt, reason, detail?}`. `reason` is `unavailable`, `owner_model_unavailable`, `owner_model_outcome_unknown` or `failed`. The route answers `503 {reason, turn_id, attempt, voice_capture_event_id | null}`.
- **The answer arrives whole.** `dispatch()` returns complete text, as `/thought-partner` shows. In rev 9 the WS carries `thread.turn_requested`, `thread.turn` and `thread.turn_failed`, but no token stream.

**Recovery (rev 9).** An admitted attempt with no terminal past its lease is closed as `thread.turn_failed {reason: interrupted}`, with a deterministic event id. This happens at API startup and lazily at the next admission to that session. The lease sits above the provider timeout; its value is INFERRED and set by the package.

**Reading turns (rev 9, NEW).** `GET /investigations/{id}/turns?after=<turn_id>&limit=`
- It is owner-scoped, uses `connect_read` and writes nothing. `limit` is 1 to 200, and the answer carries `next_after`.
- It returns the projected turns in `seq` order, each with its receipt, plus `open: {turn_id, attempt} | null`.
- A session survives a reload through this route. `GET /trajectory/{id}` returns raw events with no live gate, so it is not the turn reader.

#### `at` (rev 9; R37)

**Shape.** `at` is `{derived_asset_id, revision_id, span_id, offset_seconds}`, lane A's four fields (DECISIONS "Naming and gates reconciled after lane B's cross-check, 2026-09-27").

**Checks.**
- The asset must be the caller's. Otherwise `404 not_found`.
- The revision must be committed. Otherwise `422 revision_not_committed`.
- `span_id` must be a span of that revision. Otherwise `422 {reason: ask_invalid, detail: at_span}`.
- The asset must come from a reformat thread whose parent is this dialogue (§1.11a, LB-30). Otherwise `{detail: at_foreign}`.
- `offset_seconds` must be ≥ 0 and finite.

**What the turn sees.** The turn sees the revision's spans in document order, up to and including `span_id`. Each span is a context item gated by its class rule (§1.11a), and a withheld span is listed but never shown to the model. `offset_seconds` is recorded for "Resume at mm:ss" and never cuts a span (ruling 15).

#### Voice input (rev 9; pointer)

`input`, the server-minted `voice_capture_event_id` and the retention rule are §1.19's. On an ask, `voice.captured` is enqueued in the admission transaction beside `thread.turn_requested`, and its id is returned in the answer, including a 503 answer. When voice sends is lane A's default 8; the server rule is the same either way.

#### Group dialogue in one voice (rev 9; ruling 20; D-A)

- **One object.** A group is a session with 2 to 4 participants, found or created on its natural key like a solo session. A fifth participant answers `422 {reason: participants_invalid, detail: too_many}`.
- **One ask is one dispatch.** One `thread.turn` is written on the group's own log. No participant's log is written. LB-23 records one settlement per group turn.
- **One voice, attributed per sentence.** Every span carries `origin_thread_id`, derived by the server from the participants of the items that sentence cites, never from the model's own claim:
  - the items belong to exactly one participant: that participant's thread id;
  - they belong to several: `null` with `reason: mixed`;
  - the sentence cites none: `null` with `reason: unsupported`.
- **Contributions.** Every participant is named in `contributions`.
  - `contributed` is true when at least one of its items was included in the dispatch.
  - Otherwise `reason` says why:
    - `withheld`: every assembled item was withheld;
    - `budget`: it had servable items and none survived the budget;
    - `empty`: nothing was assembled for it.
  - A withheld participant is named, never dropped.
- **The receipt** tags every item with `participant_thread_id`.
- **The bound before sending.** See "The turn bound" below. When the turn's price is unknown, the ask requires `confirm_unpriced: true`, or it answers `422 {reason: confirmation_required, detail: unpriced}`. The confirmation is part of the request identity.
- **Withdrawn.** `dialogue.round`, `round_id`, `speaker_thread_id`, `addressees` and per-participant turns are withdrawn (ruling 20).

#### Converse (rev 9; rulings 14 and 16)

- **Data.** Converse is a door whose data is a plain `{project_id}` dialogue over a registry project, listed from `GET /projects`.
- **Sessions.** They are plain dialogues, and past ones list under `GET /investigations?kind=dialogue&dialogue_kind=plain&project_id=` (§1.2), which leaves out agent sessions, groups and branched dialogues. A Converse surface on an agent uses that agent's session.
- **Turns.** They are turn-by-turn (ruling 14). A voice note is transcribed, then submitted as an ask with `input.modality: voice`.
- **Spoken reply.** It is `/speech/tts {source: {turn_event_id}}` (§1.19), which narrates only the answer's served text.
- **Monologues** are §1.11a derivations (LB-30). An interjection is an ask carrying `at`.
- **No Speak.** There is no Speak scope, no `speak_project` context kind (§1.9), and no Speak resolver (ruling 16).

#### The turn bound (rev 9)

**The route.** NEW `POST /investigations/{id}/ask/estimate {question, context_items[], model_choice?}`
- It is owner-scoped, uses `connect_read` and makes no dispatch.
- It assembles the context exactly as the ask would, through the §1.9 resolver.
- It answers `{cents | null, max_cents | null, basis: {model, input_tokens, max_tokens, participants}, status: ok | unavailable, reason?}`, the §1.9 estimate's shape plus `max_cents`.
- A group's figure is one dispatch's bound over the combined context (§1.9). An unknown figure is null with a reason, never 0.

#### Book ask scope and openable refs (rev 9; LB-22; the one copy)

`POST /books/{id}/ask` today answers over "THIS book only" (`interfaces/research/api/books.py@b41f4ec9b` ("Answer one talk-to-book turn, page-cited, over THIS book only.")). It takes `{question, history[], research_tier, model_choice?, operation_id?}` (`interfaces/research/api/books.py@b41f4ec9b` ("class AskBookRequest(BaseModel):")). Rev 9 adds:

- **`scope?: book | shelf | library`**, default `book`. `book` behaves exactly as today (regression).
  - **`shelf`** requires `project_id`. Without it the answer is `422 {reason: project_required}`.
    - Another owner's project, or a missing one, answers `404 project_not_found`.
    - The project must have `reading` in `products[]`, whatever its `kind`, so a `kind: project` shelf made by T4 qualifies. Otherwise `409 {reason: product_absent, product: reading}`.
    - `{id}` must be the project's primary or a `shelf` member. Otherwise `422 {reason: document_not_on_shelf}`.
    - Retrieval is restricted to the shelf's document ids, reusing the document-id restriction of the meta-reading search (`substrate/books/meta_reading.py@b41f4ec9b` ("document_ids=corpus_ids,  # owned corpus IN-clause")).
  - **`library`** covers every document the requester owns that the §9.0 gate lets retrieval read for that requester.
    - The owner's privileged tag applies to the owner's own `personal_reading` documents exactly as it does for `scope: book`.
    - It does **not** reuse `resolve_owned_corpus`. That function is library-wide, books-only and has no owner filter (`substrate/books/meta_reading.py@b41f4ec9b` ("owned = [a.document_id for a in list_book_assets(con, servable_only=True, limit=limit)]")).
    - LB-22 states the size bound of the id list.
- **`source_refs[]` on the response and on `read.book_answered`:** `[{document_id, anchor | null, document_type, gate, reason}]`, deduplicated by document and page.
  - `anchor` is a §1.4 anchor at the cited page when `page_resolved`, and null otherwise.
  - `gate` and `reason` come from §1.5's one gate projection, so a cited document the reader cannot serve comes back `cite_only · not_servable` with its `document_type`.
  - The existing `citations[]` is unchanged (`substrate/schemas/events.py@b41f4ec9b` ("class BookAnswerCitation(_PayloadBase):")).
  - Once LB-35 lands, a non-book ref opens in the reader (§1.18a).
- **Persistence.** The turn persists as today, as `read.book_answered` on `read-<id>` of the asked-from book. The payload gains `scope`, `project_id?` and `source_refs[]`.
- **Spend.** Book ask is a conversational turn (§1.13), settled through `record_dispatch` with `kind: book_ask` and `mothership: reading`, derived from the `/books/*` route. `ReadBookAnsweredPayload.cost_usd` already exists and may be null (`substrate/schemas/events.py@b41f4ec9b` ("class ReadBookAnsweredPayload(_PayloadBase):")).
- **An ask executes no action (rev 9; §1.12a).** An ask returns text and refs only.
  - A ref to a document outside the project is a proposal. Lane A offers Keep (§1.5 members route) or Read later (`POST /flags {intent: read, target: {document: {document_id}}}`, §1.13), and the operator's press writes it as `actor: {kind: user}`.
  - A work with no `documents` row has no target form in the §1.13 union. The answer returns it as an unresolved ref and nothing is filed (Appendix C).
  - `POST /books/marketplace/purchase-request` (`interfaces/research/api/books.py@b41f4ec9b` ("\"/books/marketplace/purchase-request\",")) is unreachable from any ask or agent path, asserted by a call-site test.
- **Existence and takedown.** The ask route's existence check stays `book_assets`, so an unregistered non-book answers `404 book_not_found`, as today (LB-35 spec Q3). A taken-down document answers `403 book_taken_down` before any retrieval or dispatch (LB-35 spec D3).

#### Ownership note (rev 9)

- The ask route and the turn reader are new files. They share only the dispatch helpers with `/thought-partner`.
- Any change to `/thought-partner` itself still waits for #3278 and codex-r15, or is coordinated on the board.
- Owner BYOT outside book sessions depends on #3278.

#### Acceptance (red-first)

- A turn survives a reload through `GET /investigations/{id}/turns`, and its dialogue lists under `?kind=dialogue&dialogue_kind=plain&project_id=`.
- Asks to one agent from the same project land on the same session, and from another project on a different session. No event is appended to the agent's own log.
- A book-scoped turn never contains a withheld page.
- `cited_refs ⊆ retrieved_refs` holds, and an unknown marker never becomes a ref.
- A key replay returns the first turn with no second dispatch, which is asserted by counting. A replay with another `model_choice` answers `409 idempotency_conflict`.
- A second ask while one is open answers `409 turn_in_progress`.
- A write on another route completes while a stubbed dispatch sleeps, so no lock spans the model call.
- A turn with `at` sees spans only up to `at.span_id`.
- A Speak scope answers 422.
- No path from a book session writes to a linked research project. This is asserted over that project's log and membership. A linked-project thread that grounded in no shelf document never reaches the session's context.
- An answered turn writes exactly one receipt; a failed turn writes none.
- **Groups.**
  - A group turn makes exactly one dispatch.
  - A sentence citing only participant A's items is attributed to A. Every span is a participant, or null with a reason.
  - A withheld participant is named.
  - A fifth participant answers 422.
  - No participant's log is written.
- **Voice.** A voice ask writes `voice.captured` holding the submitted text, with `audio_ref: null`, in the admission transaction. Its id returns on both a 200 and a 503.
- After a takedown of a cited document, the turn reader returns the old answer `withheld`.
- The ask never calls `account_memory_context`, and an unknown body field, such as `system_context`, answers `422 ask_invalid`.
- **Book ask.**
  - A reply naming another owned book returns a ref that resolves.
  - A document the reader cannot serve comes back `cite_only`.
  - `scope: book` is unchanged.
  - `shelf` without `project_id` answers 422, and on a project without `reading` presence answers `409 product_absent`.
  - A taken-down document answers `403 book_taken_down` before any dispatch.
- **Probes.** `GET /openapi.json` lists `scope` on `/books/{id}/ask`, and the ask, estimate and turns routes.

### 1.9 Attached context and estimates: rev 9 deltas (LB-21)

**Ground truth.** `ContextItem.kind` is `doc | insight` on main (`interfaces/research/api/app.py@b41f4ec9b` ("kind: Literal[\"doc\", \"insight\"]")), composed by `_compose_context` (`interfaces/research/api/app.py@b41f4ec9b` ("def _compose_context(")). Rev 1 extended the set to `doc | insight | thread | note` (THREAD-CONTRACT.md@e39840224 §1.9 ("EXTEND `ContextItem.kind` from `doc | insight`")).

**The kind set gains `project` (rev 9; grounding item 9).** It is `doc | insight | thread | note | project`. It does not gain `speak_project` (ruling 16).
- **Who may send it.** A launch's `context_items` (§1.3), an ask's `context_items` (§1.8, not on a group turn) and both estimates. Attach never takes it (§1.12a): an agent is given explicit items, never a whole project.
- **Resolution.** `{kind: project, id}` must name the caller's registry project; otherwise it is `missing` on the receipt, with the resolver's degraded posture. It resolves to the project's members exactly as §1.8's Converse row reads them:
  - the member threads' `RightsGatedPack`s (LB-24a);
  - member documents, through retrieval when the consuming route retrieves over them (an ask with a question), and otherwise as pointers only (`refs_only`);
  - member deliverables at their current revision under the owner serve-time gate, with `speak_claim` blocks gated by §1.11 rev 9.
- **What it never follows.** `speak_project` members (ruling 16) and `project` members (no aggregate recursion, §1.5).
- **Gates.** Each resolved item is a `GatedText`. The model sees only served text, a `cite_only` item as pointers, and a `withheld` item not at all. Every item is listed on the turn's receipt (§1.8).

**One resolver.** Launch context, ask context, `POST /investigations/estimate` (signed rev 2) and `POST /investigations/{id}/ask/estimate` (§1.8) share one resolver and one fit, so an estimate prices exactly what the consuming route would send.

**Group estimates (rev 9).** A group turn's estimate is one dispatch's bound over the combined context of its participants (ruling 20). An unknown rate is `status: unavailable` with a reason, never 0.

### 1.10 Thread merge (2.5; rewritten in rev 9 per D-M; LB-24a, LB-25, LB-24)

**What rev 9 changes (rev 9).** A merge becomes four steps over one **merge session**:
1. the free preview (signed rev 3);
2. an estimate;
3. one paid, model-written **draft**, which the operator may revise at no cost into child drafts;
4. a **commit** that adopts one named draft byte for byte and makes zero dispatches.

The commit also gains a **target**: a new thread (the default) or an existing agent (§1.12a).

**Ground truth (rev 9).**
- None of this exists on main at `b41f4ec9b`. These all have zero `git grep` hits: `RightsGatedPack`, `thread.merge_*`, `thread.merged_in`, `investigation.merged_into`, `agent.promoted`, `thread.context_attached` and `thread.context_receipt`.
- The resolvers and the excerpt gate exist only on the wave-5 export branch:
  - `services/html_projection/resolvers/substrate_refs.py@2be3e0d1b` ("def resolve_pin_sources("), ("def resolve_synthesis_sources(");
  - `substrate/research_artifact/build_body.py@2be3e0d1b` ("def _excerpt_cleared(").
- `build_session_evidence_pack` produces `PackChunk` rows whose `text` field is unconditional (`orchestration/session_evidence_pack.py@b41f4ec9b` ("class PackChunk(BaseModel):")). That is why the pack is built from source events, never from that function (signed rev 3).
- The per-dispatch ledger extension is NEW. The ledger has `reserve_call` (`substrate/midnight_oil/budget_ledger.py@b41f4ec9b` ("def reserve_call(")) and no `reserve_dispatch`.
- The edge allowlist carries ` /thread/* ` (the trail) and no `/threads*` (`infrastructure/ansible/templates/Caddyfile.j2@b41f4ec9b` ("@api_routes path /account/*")).

**The rights-gated pack (rev 3; identity and order rev 9).** The signed rev-3 and rev-6 rules stand:
- `RightsGatedPack` builds items from source events: each retrieval's `supporting_claims[]` with its `chunk_ids` and `edge_ids`, and each archived synthesis with its manifest pins.
- Every item passes the resolvers and carries `content: GatedText`.
- A claim whose sources are unresolved or not servable is `cite_only`. A synthesis that fails the excerpt gate is `withheld`.

Rev 9 adds three rules:
- **Item identity (rev 9).** `item_id` is derived from immutable events, so an item keeps its id across previews and a staleness report can name it.
  - A claim item is `pi-` + the first 24 hex of sha256 over the canonical JSON of `[origin_thread_id, event_id, "claim", index]`. `event_id` is the `evidence.retrieve.delivered` event, and `index` is the claim's position in its list (`substrate/schemas/events.py@b41f4ec9b` ("supporting_claims: list[SupportingClaim]")).
  - An archived-synthesis item is the same hash over `[origin_thread_id, synthesis_id, "synthesis", 0]`.
  - Logs are append-only. A thread's item set therefore only grows, and an item's `content` changes only when its resolution or its rights change.
- **Order (rev 9).** Items follow the request's member order, then event position within the member's log, then `index`. The preview, the estimate, the draft's fit and `grouping[]` all use this one order.
- **What a model is given (rev 9, D-M).**
  - A `served` item is given as text.
  - A `cite_only` item is given as `{item_id, gate: "cite_only", source_refs}` with no text. It can be cited and never quoted.
  - A `withheld` item is not given at all.
  - This is asserted at the dispatch seam: the withheld-chunk fixture's text never appears in a dispatch request body.

**Preview (rev 3; rev 9 additions).** `POST /threads/merge/preview {thread_ids[]}` keeps the signed answer: `{preview_digest, items[{item_id, content: GatedText, origin_thread_id}], conflicts[{claim_a, claim_b, reason}]}`.
- **Members (rev 9).** A preview needs two or more distinct thread ids.
  - Fewer than two, or a repeated id: `422 {reason: members_invalid}`.
  - An id that is not a `thread` (§1.2): no log, a reserved-only id, a merge-session id or a `project-*` id: `404 {reason: thread_not_found, ref}`.
  - Another owner's thread: `403 {reason: not_owner, ref}`.
  - There is no member cap. §1.11a's five-investigation limit never applies (D-M). What a model can be given is bounded by the draft's input bound, below.
- **Digest (rev 9).** The signed definition stands. Its canonical input begins with the sorted member ids, which makes the signed "binds the complete member set" literal. It also covers `incomplete_members[]`.
- **`incomplete_members[{thread_id}]` (rev 9).** A member whose log `trajectory_read` reports incomplete contributes no items and is named here. Such a preview can be inspected, but a draft over it is refused before any spend (below), so it can never be committed.
- **Writes nothing.** The preview uses `connect_read` only and writes no row and no event. It is owner-scoped, and an unauthenticated call gets the API's 401 JSON.

**The merge session (rev 9; agreed between the lanes 2026-09-27).** Every merge attempt has one append-only session log. It replaces lane B's earlier candidate, a reserved thread id: an into-agent merge never mints a thread, and a discarded draft would have left a reservation that the listings must hide.
- **Id.** `merge_id` = `merge-<32 lowercase hex of a uuid4>`, minted by the server at the session's first draft.
  - It satisfies the event-store id rule `[A-Za-z0-9_][A-Za-z0-9_.-]{0,199}` (`substrate/event_log/events.py@b41f4ec9b` ("def investigation_event_lock(")).
  - It never starts with `inv-`.
- **Binding.** A `merge_id` is bound to its session identity: owner, sorted member ids and `preview_digest`.
  - A draft request that names a `merge_id` whose identity differs answers `409 idempotency_conflict`.
  - A draft request without `merge_id` opens a new session.
- **What it holds.** Only the events below. Each goes through the outbox with `aggregate_kind: "merge_session"` and `aggregate_id: <merge_id>`:
  - `thread.merge_draft_requested`;
  - `thread.merge_drafted`, `thread.merge_draft_failed` and `thread.merge_draft_revised`;
  - one T7 `answer.provenance` per draft;
  - each draft's own `dispatch.call`;
  - at commit, `thread.merge_started`.

  The merge's result lives elsewhere: the new thread's start event, or the agent's single `thread.merged_in`.
- **Never a thread.** A session log is `not_a_thread` (§1.2). The settled text says "no `investigation.started`"; in code the start event is `investigation.start_requested`, and the governing rule is the list's marker set:
  - **Never listed.** A session log never carries `investigation.start_requested`, `investigation.spawned_from`, `investigation.completed`, `investigation.failed`, `investigation.chase_halted` or `cascade.launched`. The list admits a log whose id does not start with `inv-` only when it carries one of these (`interfaces/research/api/app.py@b41f4ec9b` ("investigation_markers = {")). A test pins that both the `.jsonl` enumeration and the sealed-`.parquet` enumeration (§1.2) skip session logs.
  - **`GET /investigations/{merge_id}` answers `404 {reason: not_found}`.** This is red today. The route reads any log that has rows as `in_progress`, and answers an id with no rows `200 {status: "not_found"}` (`interfaces/research/api/app.py@b41f4ec9b` ("Distinguishes ``not_found`` (no events at all)")). The client already maps a failed status fetch to not-found (`apps/reading/src/hooks/useInvestigation.ts@b41f4ec9b` ("404 or similar")).
  - **`GET /trajectory/{merge_id}`** answers as for an id with no log, and **`GET /trajectory`** skips session logs (`interfaces/research/api/app.py@b41f4ec9b` ("async def get_trajectory_collection(")). Both routes are unscoped pre-multi-user holes (§1.15), and serving drafts through them would widen those holes.
  - **Billing still counts the draft.** The billing aggregate walks every log (`interfaces/research/api/app.py@b41f4ec9b` ("def _billing_aggregate_from_dispatch_calls(")), so it still counts a draft's `dispatch.call`. That is intended.
- **Read.** A session is read only through the owner-scoped `GET /threads/merge/{merge_id}/draft` (below).
- **Discard.** There is no discard route and no discard event.
  - Discarding means the client leaves the session. The log stays as the audit, with no ghost thread, reservation or listing row.
  - A later commit of one of the session's drafts is still valid.
- **One commit per session.** `thread.merge_started` is enqueued under `operation_id` `merge_commit:<merge_id>`. `write_event_outbox.operation_id` is UNIQUE (`substrate/graph/schema.py@b41f4ec9b` ("operation_id TEXT NOT NULL UNIQUE")), so the database itself refuses a second commit.

**Estimate (rev 9).** `POST /threads/merge/draft/estimate {thread_ids[], preview_digest, question, model_choice?}` returns:
- `estimate_cents | null` and `max_cents | null`;
- `reason?: "unavailable"`;
- `assumptions {input_tokens, max_tokens, extras_cap_cents, model, given_items, not_shown_items}`.

Its rules:
- `input_tokens` counts exactly the given set that a draft pressed now would send, using the same fit function (below).
- `max_cents` is §1.13's per-call bound: input tokens × the input rate, plus `max_tokens` × the output rate, plus the extras cap. `estimate_cents` is the expected charge.
- An unpriced model returns both as `null` with `reason: "unavailable"`, never `0`.
- `assumptions.model` echoes what a draft pressed now would resolve. The estimate binds nothing (§1.11a "Model selection").
- A stale `preview_digest` answers `409 preview_stale`, so an estimate always prices the pack the operator is looking at. The preview's 403, 404 and 422 answers also apply.
- It writes nothing.

**Draft (rev 9, D-M).** `POST /threads/merge/draft {thread_ids[], preview_digest, question, model_choice?, merge_id?, project_id, mothership, confirm_unpriced?, idempotency_key}`

*The request.*
- `question` follows the launch rule (`interfaces/research/api/app.py@b41f4ec9b` ("question: str = Field(..., min_length=3)")) and is stored in NFC.
- `project_id` and `mothership` are the cockpit's active project and mode, with `mothership` one of `research | writing | reading`.
  - They attribute spend (§1.13; D-P tightening 3) and name the merged thread's home project.
  - The project must be the caller's, else `404 project_not_found`.
  - These two fields and `merge_id?` are additions to lane A's §A5 shape (Appendix B).
- `model_choice?` is validated against the owner's lineup. Absent, it means the operator default for the NEW `merge_draft` dispatch role.
- `confirm_unpriced: true` is required when the resolved model is unpriced. Without it the answer is `422 {reason: confirmation_required, detail: unpriced}`, the same code as §1.8, and nothing is written. The hold for an unpriced draft is sized by the `merge_draft` role's per-call maximum (INFERRED name; Appendix C).

*Identity and idempotency.*
- **The request identity** is sha256 over the canonical JSON of:
  - the owner and the sorted member ids;
  - `preview_digest` and the NFC question;
  - `model_choice`, or `"default"`;
  - `project_id` and `mothership`;
  - `merge_id`, or null.
- **The model binding.** The model is resolved once, at admission, and recorded. It is not part of the identity, so a retry under the same key replays even after the default has changed. This follows §1.11a's rev-8.3 binding, and it refines LB-25's "resolved model", which would have turned a changed default into a spurious `409 idempotency_conflict`.
- **Replay.** The request record's `operation_id` is `merge_draft:<sha256(owner ‖ idempotency_key)>`.
  - It is found through `event_for_operation` (`substrate/write/event_outbox.py@b41f4ec9b` ("def event_for_operation(")), so a retry of a session's first draft finds its `merge_id` although the client never received it.
  - The same key with the same identity replays the first answer.
  - The same key with another identity answers `409 idempotency_conflict`.

*Checks, in order, before anything is written (rev 9).*
1. Members, ownership and the project: the preview's 403, 404 and 422 answers, and `404 project_not_found`.
2. `preview_digest` is current: else `409 preview_stale`.
3. If `merge_id` is named, three checks apply:
   - it is the caller's, else `404 {reason: merge_not_found}`;
   - it is not committed, else `409 {reason: merge_committed, thread_id}`;
   - its identity matches, else `409 idempotency_conflict`.
4. No member is incomplete: else `422 {reason: members_incomplete, thread_ids[]}`.
5. At least one item is `served`: else `422 {reason: no_served_items}`. The synthesis gate (below) cannot clear a draft that stood on no served source, so such a draft could never be accepted.
6. Admission: `remaining_cents` must be at least `max_cents` (§1.13 admission, with no hold). Else `402 refused_capped`, and nothing is written, so a retry after "Raise today's cap" is judged afresh.

*Admission, in one `connect_write` transaction through the outbox (rev 9).*
- Mint `merge_id` for a first draft, and `draft_id` = `<merge_id>.d<n>`.
  - `n` is 1 plus the number of drafts already recorded for the session, computed inside the transaction; the single writer serialises it.
  - Because `draft_id` embeds `merge_id`, revise and commit find the session without an index.
- Enqueue `thread.merge_draft_requested` with this payload:
  - identity: `merge_id`, `draft_id`, `request_identity`, `idempotency_key`, `owner_user_id`;
  - the pack: `member_ids[]`, `preview_digest`, `preview_items[{item_id, origin_thread_id, content_sha256, gate}]`, `given_item_ids[]`, `not_shown[{item_id, gate, reason}]`;
  - the request: `question`, `model_choice`, `model`, `max_cents`, `project_id`, `mothership`;
  - `lease_expires_at`.

*Dispatch, outside the transaction.* No database lock is held across the model call (grounding §3 rule 4).
1. **The hold.** `reserve_dispatch(run_id, dispatch_id = "<draft_id>:0", max_cents, attribution)` places it, with `attribution = {thread_id: <merge_id>, project_id, mothership, spend_class: cap_admitted, kind: merge_draft, authority}` (§1.13 rev 9).
   - A refused hold answers `402 refused_capped` and records `thread.merge_draft_failed {draft_id, reason: cap_reached}` (§1.13 halt scope).
   - A retry under that key replays the refusal. A new press mints a new key.
2. **The answer.** The POST answers `202 {merge_id, draft_id, state: "drafting"}`.
3. **The call.** One dispatch runs. Its `dispatch.call` is written on the session log, which is the draft's attribution bucket.
4. **Settlement.** `settle_dispatch(dispatch_id, actual_cents)` settles the hold.
5. **The terminal record.** One transaction writes either `thread.merge_drafted` with the draft's `answer.provenance`, or `thread.merge_draft_failed`.

**Why the POST answers 202 (rev 9).**
- A draft is one model call over a pack that may be large, and Part 2 §A5 makes `drafting` asynchronous with Cancel. A synchronous answer would also run into the edge proxy's request timeout. That timeout is INFERRED from the Cloudflare Tunnel front and was not measured.
- Every answer carries `state: drafting | drafted | failed`.
- The result arrives through `GET /threads/merge/{merge_id}/draft?draft_id=` and the socket nudge.
- A replay of the POST after the draft finishes answers `200` with the full draft shape below, so lane A's request C4 holds whenever the draft exists.

**The given set (rev 9).**
- **The fit.** The server fits items in pack order until the `merge_draft` role's input bound: every `served` item as text, and every `cite_only` item as pointers.
- **What is not shown.** `not_shown[{item_id, gate, reason}]` lists every `cite_only` item, every `withheld` item and every served item that did not fit.
  - `reason` is the item's `content.reason`: `unresolved`, `not_servable` or `lineage_unreconciled`.
  - A served item that did not fit has reason `budget`.
- **Determinism.** The fit is a pure function of the pack and the bound, so the estimate and the draft agree.

**How the server types the model's output (rev 9; D-M "answer-shaped"; §1.0a "Model citation markers").**
- **Markers.** A citation is an inline marker `[[ref:<item_id>]]`, where `item_id` matches `pi-[0-9a-f]{24}`. Any other `[[` sequence is ordinary text.
- **Two forms of one text.**
  - The **edit text** is the NFC text with its markers. It is the canonical form for digests and for `revise`.
  - The **served text**, `synthesis.text`, is the edit text with every marker stripped (with one preceding space each) and normalized. It never contains a marker.
- **Sentences.** The server splits the served text into UAX #29 sentences, using §1.11a's pinned tokenizer. `sentences[{index, start, end, text | null, origin, claim_id | null, item_ids[]}]` carries each one, with `start` and `end` as scalar offsets into `synthesis.text` and `item_ids` as the markers that followed it in the edit text. A sentence with at least one marker is a **claim**. Every sentence has an `origin`:
  - `source`: model text carrying markers;
  - `generated`: sourceless model text that `connective-templates/v2` admits (§1.11a), with slots taken only from the question (`slot_source: question`);
  - `unsourced`: any other sourceless model text, always `unsupported` (§1.2 rev 8.8);
  - `operator`: text the operator typed, which occurs only in revisions.
- **Claims.** `claims[{claim_id, text | null, item_ids[], source_refs[]}]`:
  - `claim_id` = `cl-` + the first 24 hex of sha256 over the NFC sentence with its markers stripped and its sorted `item_ids`. A carried claim therefore keeps its id across revisions.
  - `item_ids` are the sentence's markers, in order. `source_refs` is the union of those items' refs, each with its own gate; openable refs follow §1.2's rev-7 rule.
  - Every `item_id` must name an item given to this draft as `served` or `cite_only`. Otherwise the whole draft is refused:
    - the session records `thread.merge_draft_failed {reason: unresolved_claim_ref, detail: {claim_index, item_id}}`;
    - the POST (or its replay) answers `422 {reason: unresolved_claim_ref, ref: <item_id>}`;
    - the spend is settled truthfully and shown as `cost_cents`, and nothing is retried on its own.
- **Presentation.** The model chooses `presentation_mode`: `quoted | cited_quietly | metadata_only` (T7).
- **Measures.** Each draft records `measures {sentences, referenced, generated, unsourced, operator}`. `referenced ÷ (sentences − operator)` is D-M's "under 50% of sentences carrying refs" trigger, so the trigger can be counted per draft.

**The synthesis gate (rev 9; D-M "the Synthesis gate").** A draft's `synthesis` is a synthesis (THREAD-CONTRACT.md@e39840224 §1.2 ("**Which gate (rev 6).**")), so it is `served` or `withheld`, never `cite_only`.
- **What it judges.** Exactly what the draft stood on:
  - the given set's pins, through `resolve_pin_sources` and `resolve_synthesis_sources`, under `_excerpt_cleared`'s final rule (`substrate/research_artifact/build_body.py@2be3e0d1b` ("return bool(sources) and all(s.resolved and s.servable for s in sources)"));
  - every member log reading complete, which is its rule (`substrate/research_artifact/build_body.py@2be3e0d1b` ("if trail.unreadable_investigation_ids:")).
- **Why it is not `_excerpt_cleared` called on the members.** That function walks the distilled nodes and syntheses of every `trail.investigation_ids` (`substrate/research_artifact/build_body.py@2be3e0d1b` ("inv_ids = trail.investigation_ids or (investigation_id,)")).
  - That walk includes items the model was never given, so it would withhold a draft for a source the draft provably did not see.
  - LB-25 factors out the pointer check. A test pins that a member's withheld synthesis does not withhold a draft that was not given it.
- **Re-judged at every read.** The gate is re-evaluated live on each read (the §1.11 serve-time rule). After a takedown:
  - `synthesis.text`, `edit_text`, `sentences[].text` and `claims[].text` become null;
  - the pointers stay.

**The draft shape (rev 9; lane A's §A5 shape, extended).** The fields marked † are additive, beyond §A5:
- `merge_id`†, `draft_id`, `parent_draft_id`†, `state`†, `draft_digest`;
- `synthesis: GatedText`, `edit_text | null`† and `sentences[]`†;
- `claims[]`;
- `answer_provenance {retrieved_refs[], cited_refs[], presentation_mode}`;
- `grouping[{origin_thread_id, item_ids[]}]`, `conflicts[]` and `not_shown[{item_id, gate, reason}]`;
- `measures`†, `preview_digest`†, `question`†;
- `cost_cents` and `model {provider, model, dispatch_event_id}`.

Rules for the shape:
- `synthesis.text` is the served, marker-free text, and `synthesis.origin` is `source`. The per-sentence origins are on `sentences[]`.
- `edit_text` is the marked edit encoding, served to the owner only while `synthesis` is served, for the editor and `revise`.
- `retrieved_refs` are the given set's refs, and `cited_refs` is the union of `claims[].source_refs`. `cited_refs ⊆ retrieved_refs` (T7).
- `draft_digest` = sha256 over the canonical JSON of:
  - `preview_digest`, the NFC question and the resolved model;
  - sha256 of the NFC edit text, markers included;
  - the canonical `claims[]` (ids and `item_ids`), and `presentation_mode`;
  - `parent_draft_id`, or null.
- **Events.** One transaction writes both:
  - `thread.merge_drafted` with this payload:
    - ids and digests: `merge_id`, `draft_id`, `parent_draft_id: null`, `draft_digest`, `preview_digest`;
    - the text: `edit_text`, `sentences[]`, `claims[]`, `presentation_mode`;
    - the pack: `given_item_ids[]`, `not_shown[]`;
    - `measures`, `cost_cents` and `model {provider, model, dispatch_event_id}`.
  - `answer.provenance {answer_event_id: <that event's id>, retrieved_refs[], cited_refs[], presentation_mode}`.

  LB-25's refs-only field list is kept and extended with the body, because the session log is the draft's one store (grounding §3 rule 1).
- **Attribution.** `page.attribution.computed {subject: "merge-draft:<draft_id>", shares[]}` takes §1.11a's form and is telemetry only (G2/G3).

**Failure, recovery, cancel and the cap halt (rev 9; §1.11a's pattern).**
- **Failure.** `thread.merge_draft_failed {merge_id, draft_id, reason, detail?, cost_cents | null}`.
  - `reason` is one of `cap_reached | unresolved_claim_ref | unavailable | interrupted | cancelled | failed`.
  - It shares `operation_id` `merge_draft_done:<draft_id>` with `thread.merge_drafted`, so a draft has exactly one terminal record.
- **Recovery.** At API startup and on a lease sweep, a request record with no terminal record past `lease_expires_at` settles its hold at the held amount (§1.13, unknown outcome) and records `interrupted`.
- **Cancel.** NEW `POST /threads/merge/draft/{draft_id}/cancel {}`.
  - While the draft is `drafting`, the server stops waiting and settles per §1.13: the actual charge when the provider reports one, else the full hold. It then records `cancelled`.
  - On a terminal draft it answers the current state unchanged (200).
  - It is owner-scoped: `404 {reason: draft_not_found}`.
- **The cap halt is scoped per draft** (§1.13 rev 9, "Halt scope"). A refused hold on one draft never refuses a later draft of the same session, and it is delivered as that draft's `thread.merge_draft_failed {reason: cap_reached}`, never as `investigation.cap_halted`. Red-first: a refused hold on draft 1 must not refuse draft 2 after the cap is raised.

**Revise (rev 9; D-M "an edit makes a child draft").** `POST /threads/merge/draft/{draft_id}/revise {synthesis_text, idempotency_key}`
- `synthesis_text` is in the edit encoding (markers included).
- **Refusals.**
  - An unknown draft, or another owner's: `404 {reason: draft_not_found}`.
  - A parent that is not `drafted`: `409 {reason: draft_not_ready, state}`.
  - A committed session: `409 {reason: merge_committed, thread_id}`.
  - `synthesis_text` over 65,536 UTF-8 bytes: `422 {reason: too_large}`.
- **No model, no spend.** No hold, no dispatch and no ACU. This is asserted by counting.
- **The server decides what is an edit.** The rule is the same as §1.11a's fork route (rev 8.10):
  - A sentence whose NFC hash, markers included, equals a sentence of the parent keeps the parent's origin and claim.
  - Every other sentence is `origin: operator`.
  - The client never names an origin.
- **Claims are recomputed** from the markers that survive the edit.
  - A marker naming a `served` or `cite_only` item of the draft's preview is accepted even when the model was not given that item. It joins the child's `retrieved_refs`, so `cited ⊆ retrieved` still holds.
  - A marker naming a `withheld` item, or an item that is not in the preview, answers `422 {reason: unresolved_claim_ref, ref: <item_id>}` and writes nothing.
- **Inherited.** The child takes the parent's `presentation_mode`, `given_item_ids`, `model` and `preview_digest`. Its `cost_cents` is 0.
- **Events.** One transaction writes both:
  - `thread.merge_draft_revised` with this payload:
    - lineage: `merge_id`, `draft_id`, `parent_draft_id`;
    - digests: `draft_digest`, `preview_digest`;
    - the text: `edit_text`, `sentences[]`, `claims[]`, `presentation_mode`;
    - `measures`.
  - the child's `answer.provenance`.
- **The answer** is `201` with the full draft shape.
- **Idempotency.** The `operation_id` is `merge_draft_revise:<sha256(owner ‖ key)>`, and the identity is sha256(owner, parent `draft_id`, NFC edit text). The same key and identity replay; the same key with another identity answers `409 idempotency_conflict`.
- **No compare-and-set.** Drafts are immutable, and a commit names exactly one, so no state is shared. Two devices editing one draft make two children, both kept in the lineage.

**Read (rev 9).** `GET /threads/merge/{merge_id}/draft?draft_id=`
- It is owner-scoped: an unknown session or another owner's answers `404 {reason: merge_not_found}`. It uses `connect_read` and writes nothing.
- It answers:
  - `merge_id`, `member_ids[]`, `preview_digest`, `project_id` and `mothership`;
  - `draft`, in the draft shape;
  - `lineage[{draft_id, parent_draft_id, state, origin: model | operator, created_at}]`;
  - `committed: {target: "new_thread" | "into_thread", thread_id, draft_id, committed_at} | null`.
- Without `draft_id`, `draft` is the session's newest draft. An unknown `draft_id` answers `404 {reason: draft_not_found}`.
- Text is gated live (the synthesis gate).

**Commit (rev 3; rewritten in rev 9 per D-M).** `POST /threads/merge {thread_ids[], preview_digest, draft: {draft_id, draft_digest}, question, target?: "new_thread" | {into_thread_id}, idempotency_key}`
- An absent `target` means `"new_thread"`.
- The server never infers a target and never folds into a common parent: O-2's clause is struck. Lane A preselects the common parent only when every member descends from it, and applies it only when the operator presses.

*Checks, in this order (rev 9).*
1. `draft` absent or null: `422 {reason: draft_required, detail: absent}`.
2. `draft.draft_id` unknown, or another owner's: `404 {reason: draft_not_found}`.
3. **Replay comes first.** Suppose the session already holds a `thread.merge_started` recorded under this key.
   - With the same request identity, the server resumes and answers as the first commit did. It runs no staleness check, because the merge was already decided.
   - With another identity, it answers `409 idempotency_conflict`.
4. The session was committed under another key: `409 {reason: merge_committed, thread_id}`.
5. The draft is not `drafted`: `409 {reason: draft_not_ready, state}`.
6. The commit does not name the draft that was reviewed: `422 {reason: draft_required, detail}`. All three details are lane-A bugs (Part 2 §A5): logged, never shown to the operator.
   - `digest_mismatch`: the stored `draft_digest` differs.
   - `members_differ`: the sorted `thread_ids` are not the draft's members.
   - `question_differs`: the NFC question is not the draft's.
7. Every member is a `thread` and the caller's: else `404 {reason: thread_not_found, ref}` or `403 {reason: not_owner, ref}` (signed step 3).
8. The target checks, below.
9. `preview_digest` is current: else `409 preview_stale`.
10. **The draft is current.** Its `preview_digest` must equal the current digest, and its synthesis gate must read `served` now. Otherwise the answer is `409 {reason: draft_stale, detail}`, where `detail` is structured and names what changed. The server finds it by diffing the recorded `preview_items` against the current ones:
    - `{kind: "member_changed", thread_id, added_item_ids[], removed_item_ids[]}`
    - `{kind: "source_changed", item_id}`: the item's content or its pointer resolution changed
    - `{kind: "rights_changed", item_id, gate_then, gate_now}`: the item's gate or `content_class` changed
    - `{kind: "member_incomplete", thread_id}`

    The server never regenerates the draft. Staleness means exactly that the preview digest changed. A member event that adds no pack item and changes no gate (a `thread.turn` or a seen mark, for example) never makes a draft stale. LB-25's acceptance item "a member event after the draft" is read as "a member event that changes the pack".

*Request identity (rev 4; two fields added in rev 9).* sha256(owner, sorted member ids, `preview_digest`, the reviewed conflict set, NFC question, `draft_digest`, canonical `target`), bound to the key.

*Writes (rev 9: one transaction, then delivery).*
- **What changes from signed rev 4.**
  - Signed steps 2–5 wrote one record at a time, and the settled 2026-09-27 text moves `thread.merge_started` from the new thread's log to the session log.
  - Rev 9 enqueues every record of the merge in **one** `connect_write` transaction through the outbox, so the records become durable together.
  - Delivery into each log is idempotent by event id: a reused id with different bytes is refused (§1.0a "The outbox").
- **The records:**
  1. **`thread.merge_started`** goes on the session log under `operation_id` `merge_commit:<merge_id>`. Its payload is `{merge_id, request_identity, idempotency_key, draft_id, draft_digest, preview_digest, member_ids[], target, thread_id}`.
     - For `new_thread`, `thread_id` is minted here as `inv-<12 hex>`, the launch's own form (`interfaces/research/api/app.py@b41f4ec9b` ("investigation_id = req.investigation_id or canonical_owner_id or f\"inv-")). A resume reuses it.
  2. **Each member** gets `investigation.merged_into {thread_id, merge_id, preview_digest}` on its own log, with event id `evt-mi-` + sha256(`merge_id` ‖ member)[:24]. For an into-agent merge, `thread_id` is the target.
  3. **The result:**
     - For `new_thread`: the new thread's `investigation.start_requested {question, owner_user_id, project_id, merged_from[], merge_id, accepted_draft {draft_id, draft_digest}}`, with event id `evt-ms-` + sha256(`merge_id`)[:24]. The same transaction writes the new thread's membership row in the session's `project_id` (`member_kind: investigation`, role null) and `project.members_changed {cause: merge_commit}` (§1.5).
     - Into an agent: `thread.merged_in` (below).

  Then the server drains the outbox for the session log, each member log, the result log and the project log.
- **The answer.**
  - `200 {merge_id, target, thread_id, merged_from[], state: "committed"}` comes only when every record has been delivered. A partial merge never reports success.
  - When the transaction committed but delivery is incomplete, the answer is `503 {reason: merge_pending, merge_id, thread_id}`. The merge is decided; a retry with the same key answers 200 once delivery completes.
- **Completion without the client (rev 9).** `recover_pending_events` runs at API startup, wired by LB-17 (§1.5 "Startup recovery"). LB-24a adds a call after every `503 merge_pending`, so a committed merge finishes even if the client never retries.
- **`merge_failed` is retired (rev 9).** Every refusal happens before the transaction, and every committed transaction completes. So no member ever holds the record of a refused commit.
  - Projections show `merge_pending(thread_id)` until the result event is delivered, and then list the merge in `merge_ids[]` (§1.2).
  - Part 2 §2.5's `failed` state (the 503) keeps its copy, "Nothing has run yet", and its retry on the same key.

*Zero dispatches (rev 9, D-M).* The commit calls no model, takes no hold, charges no ACU and starts no run. Red-first: counting `dispatch.call` events across all logs, and ledger holds, before and after a commit gives equal counts. Without the handler guard below, the test is red.
- **The handler guard.** Loop One runs a thread when its start event is broadcast (`interfaces/research/api/app.py@b41f4ec9b` ("Broadcast the start event so the orchestrator handler"); `orchestration/loop_one/orchestrator.py@b41f4ec9b` ("async def handle_investigation_start(event: Event) -> None:")).
  - The handler returns at once for a start whose payload carries `merge_id`.
  - The start is still broadcast, so clients see it (§1.7).
  - A client cannot forge such a start: `investigation.start_requested` is server-owned on `/events/typed` (§1.16).
- **No ACU.** The commit does not call `commit_start_acu` (`interfaces/research/api/app.py@b41f4ec9b` ("Meter 1 ACU for this start")). The draft was the metered work.

*The merged thread (target `new_thread`).*
- **First outcome.** Its first outcome is the accepted draft. It is read byte for byte from the session log through `merge_id`, and checked against `draft_digest` at every read; a mismatch reads `withheld · unresolved`. The bytes are never copied into the thread's own log. Its answer provenance is the draft's `answer.provenance`.
- **Kind and state.** Its `kind` is `research`, and it reads `done` once its start event is delivered (§1.2). No `investigation.completed` is written, so no `thread_done` inbox item fires for a merge the operator has just accepted. Later asks and continuations follow the normal rules.
- **Projections.**
  - `excerpt` is the draft's `synthesis`, gated live.
  - `spend_cents` counts only the thread's own dispatches, which are 0 at commit. The draft's cost belongs to the session and is read through the draft route.
  - `merged_from[]` is the members, and `merge_ids[]` is `[merge_id]`. The counts follow §1.2's merged-thread clause.
- **Not selectable in the MVP.** Its accepted draft is not an output segment (§1.4b).

**Into an agent (rev 9, D-M; live with LB-26).** `target: {into_thread_id}`
- **Until LB-26 lands:** `422 {reason: target_unavailable, detail: agents_unavailable}`, never 403 for that reason (lane A's request C4).
- **After LB-26:**
  - `into_thread_id` that is not a `thread`: `404 {reason: thread_not_found, ref}`.
  - Another owner's thread: `403 {reason: not_owner, ref}`.
  - A thread that is not promoted (§1.12a): `422 {reason: target_unavailable, detail: not_an_agent}`.
  - A target that is also one of the members: `422 {reason: target_unavailable, detail: target_is_member}`, because a thread cannot be merged into itself.
  - Any project the agent belongs to is shared: `422 {reason: project_shared}`. A merge into an agent carries material into every project the agent serves, so D-A's attach rule applies to it too.
- **What it writes (step 3).**
  - Exactly one `thread.merged_in {merge_id, merged_from[], accepted_draft {draft_id, draft_digest}, preview_digest}` on the agent's log, with event id `evt-mg-` + sha256(`merge_id`)[:24].
  - No thread is minted, no membership changes, and the agent's state is unchanged.
  - Members record `merged_into {thread_id: <agent>}` under the same pending rule.
- **How the agent reads it.** The §1.12a assembler reads it as an attachment: step 3 is the accepted draft, and step 4 is its `merged_from`. `thread.context_attached` is never written for a merge (D-M's naming choice).
- **One target per press.** "Both targets in one press" is not offered: a commit takes one target, and a session commits once.

**Lineage and dependencies (rev 9).**
- **Members are never rewritten, and a target receives one append.** This restates the signed "Members are never mutated beyond that record" (THREAD-CONTRACT.md@e39840224 §1.10 ("Members are never mutated beyond that record")).
- **Members are export dependencies.** `merged_from` members are export dependencies of the merged thread. A member whose log is missing, or reads incomplete, withholds the merged excerpt (`withheld · unresolved`), like an unresolved branch (§1.3).
- **`ThreadSummary.merge_ids[]`** lists every committed merge the thread took part in, as a member, a result or a target, in commit order. A pending merge shows `merge_pending(thread_id)` and is not listed.

**Push (§1.7; rev 9).**
- The merge-session events, `investigation.merged_into`, `thread.merged_in` and the merged thread's start event are broadcast (§1.7's list).
- **The socket's owner hole.** The socket has no owner filter today, a listed pre-multi-user hole (§1.15). A draft's text reaches the socket once, when it was served to its owner. That is no wider than any research event today.
- **Refetch.** Clients refetch through the owner-scoped read.

**Retirements (rev 9).** Two things retire. The compose hash-conflict list stays removed (signed rev 3).
- **The compose routes.** `/research/artifacts/compose*` retires once lane A's MergeFlow preview is on main.
  - Today `GET /research/artifacts/compose/draft-merge.html` renders with `write_draft_merge=True`, so a GET writes files (`interfaces/research/api/artifact_routes.py@b41f4ec9b` ("write_draft_merge=True,")). A test pins this red.
  - After retirement, the GET and `POST /research/artifacts/compose` both answer `410 {reason: "retired", alternatives: ["thread_merge"]}`, in LB-33's form (§1.11).
- **The auto-fold.** O-2's auto-fold into a common parent is struck.

**Suggestion (rev 3, unchanged).** `thread.merge_suggested` still reaches the operator through the inbox and is never applied silently. It opens at `selecting`.

**Edge (rev 9).** LB-24a's PR adds `/threads*` to `@api_routes` (grounding §3 rule 6). The existing ` /thread/* ` entry does not match `/threads/…`.

**Delivery and acceptance (rev 9).**
- **The packages.**
  - **LB-24a** delivers the pack, the preview and the commit skeleton.
    - `POST /threads/merge` answers `422 draft_required` to every request until LB-25 lands.
    - Tests drive the skeleton through its internal function with a fixture draft.
    - No model is called anywhere in the package.
  - **LB-25** delivers the estimate, draft, revise, cancel and read routes, and the commit's draft checks (items 1–6 and 10).
  - **LB-24** delivers the targets, `thread.merged_in` (after LB-26), `merge_ids[]` and the compose retirement.
  - If the base slips past W3 with no owner, preview-only ships with Accept disabled, never the compose page (D-M).
- **Red-first acceptance, from the pack to the commit:**
  1. A withheld chunk's text never appears in the preview. The fixture is red against a pack built from `build_session_evidence_pack`.
  2. The same text never appears in any dispatch request body.
  3. A `cite_only` item carries pointers only. A rights change re-keys `preview_digest`.
  4. The preview, the estimate and the read open no writer. The compose GET's file write is red today.
  5. A commit without a draft answers `422 draft_required`.
  6. The dispatch count at commit is 0, by counting.
  7. A claim with an unresolved item id answers `422 unresolved_claim_ref`.
  8. A revised draft is accepted byte for byte, and its parent stays in the lineage.
  9. A retrieval on a member after the draft gives `409 draft_stale {kind: "member_changed"}`. A `thread.turn` on a member does not.
  10. An exhausted cap answers `402 refused_capped` before any dispatch.
  11. A draft over six members is admitted.
  12. The merged thread's counts equal the accepted draft's.
  13. The draft writes nothing to member logs.
  14. `synthesis.text` never contains a `[[ref:` marker; `edit_text` does.
- **Red-first acceptance, from the target to the session:**
  1. `into_thread_id` answers `422 target_unavailable` before LB-26, never 403 for that reason.
  2. A merge into an agent writes exactly one `thread.merged_in`, and the agent's state is unchanged.
  3. Killing the process after the commit transaction, then restarting, completes the merge with the same ids and no dispatch.
  4. A second commit on a committed session answers `409 merge_committed`.
  5. A cross-owner member answers 403.
  6. `GET /investigations/{merge_id}` answers 404, and no listing shows a session.
  7. The merged start event never reaches Loop One's run path.
  8. A `project-<id>` as a member answers `404 thread_not_found`.
- **Prod probes (read-only).**
  - `GET /openapi.json` lists the preview, estimate, draft, revise, cancel, read and commit routes.
  - An unauthenticated `GET /threads/merge/merge-00000000000000000000000000000000/draft` answers the API's 401 JSON, never the SPA's HTML.

**If D-M is overturned.** If the operator, shown both shapes, says the grouping alone is the draft, the commit accepts `draft: null`, and the merged thread runs per signed §1.10. That is a one-line change with no migration. The other reconsider-if triggers are D-M's own. The unreferenced-sentence trigger is countable per draft from `measures`.

### 1.11 Merge into document and fork: rev 9 deltas (LB-15, LB-18, LB-33, LB-33b; O-12)

#### Speak testimony in Write (rev 9; LB-18 with LB-15; D-P "never copies"; O-12's fallback)

**What main does.** The Speak composer copies claim text into Write's `outline_blocks`, marking each block `source_block_kind="speak_claim"` with the claim id as `source_block_id` (`substrate/speak/write_composer.py@b41f4ec9b` ("source_block_kind=\"speak_claim\",")). After that, a takedown or a revoked consent never reaches the copied text.

**The serve-time gate extends to testimony (rev 9).** Rev 8.4's serve-time gate (THREAD-CONTRACT.md@e39840224 §1.11 ("**Serve-time gate (rev 8.4).**")) gains one block rule. Every response that carries deliverable body text recomposes each `speak_claim` block at serve time from its claim, never from the stored copy:
- the claim no longer resolves: the block is `withheld · unresolved`;
- an active takedown targets the claim, its interview or the project's subject (`substrate/speak/schema.py@b41f4ec9b` ("target_kind   TEXT NOT NULL CHECK (target_kind IN ('interview', 'claim', 'subject')),")): `withheld · not_servable`;
- a contributing interview lacks a live `record` consent: `withheld · not_servable`;
- otherwise, in the owner's editing view, the block is `served` with `origin: source` and a `source_ref` to the claim. The owner reads testimony that was collected with record consent.

The cached-render fingerprint includes each claim's takedown and consent state, so a takedown changes it (rev 8.4's caching rule).

**Share and export (rev 9; O-12's fallback).** A share, public page or export of a deliverable that holds any `speak_claim` block answers `422 {reason: speak_publish_required, claim_ids[]}`, unless Speak's publish flow has cleared every such claim. The flow is `check_public_publish` (`substrate/speak/publish_gate.py@b41f4ec9b` ("def check_public_publish(")), with the takedown check `is_blocked_by_takedown` (`substrate/speak/publish_gate.py@b41f4ec9b` ("def is_blocked_by_takedown(con: Any, claim: ClaimRecord) -> bool:")). The `attribute` and `publish` scopes are part of that flow. Which stored record counts as "cleared" is LB-18's to name, in its PR. This stands until the operator rules on O-12.

**The copies are not rewritten.** Stored blocks keep their bytes (history is append-only); only what is served is gated.

#### From investigation (rev 9; LB-15)

`POST /write/deliverables/from-investigation` (`interfaces/research/api/write_routes.py@b41f4ec9b` ("\"/deliverables/from-investigation\",")) binds the deliverable's owner but never checks the investigation's owner. It looks up the synthesis by id only and inserts a deliverable on every call (`substrate/write/promote_context.py@b41f4ec9b` ("def promote_investigation_to_deliverable(")). Rev 9 repairs it, and §1.5's `from_investigation` seed and §1.5a's `seed_deliverable` call the same repaired function:
- **Owner check.** Each investigation must be a `thread` (§1.2) whose recorded owner is the requester, a legacy thread counting as `__operator__`'s. Otherwise `404 {reason: thread_not_found, ref}` or `403 {reason: not_owner, ref}`.
- **Multiple and partial selections.** The body takes exactly one of `investigation_id` and `investigation_ids[]` (ordered, at most 50), plus optional `node_ids[]` that narrow the pinned sets. There is one section per investigation, in order, built as §1.5a builds `seed_deliverable`'s sections. A `node_id` outside every selected pinned set answers `422 {reason: node_not_in_synthesis, ref}`.
- **Idempotency.** An optional `idempotency_key` replays the first answer (one deliverable), and a changed body answers `409 idempotency_conflict`. It is optional in rev 9 because existing callers send none. Without a key, a call creates a new deliverable, as today.
- **Atomicity.** The deliverable, its sections, its blocks and their events commit in one transaction through the outbox (§1.5 "Atomicity").
- **The existing refusal.** No depositable synthesis keeps its 404 and gains `reason: no_synthesis`.

#### Source merge (rev 9: LB-33, and LB-33b only if Q-B1 is yes)

This replaces the bullets under THREAD-CONTRACT.md@e39840224 §1.11 ("LB-33 retires them"). The rev-8.8 correction, THREAD-CONTRACT.md@e39840224 §1.11 ("Source merge (corrected in rev 8.8)"), stands.

**Where it is (rev 9).**
- LB-33 is PR #3534 at `2adfe06a8`. It is open and not on main.
- Lane A's removal of every client caller, restore included, is PR #3533 at `d3143a491`. It lands before LB-33.
- LB-33 is tier 0, outside the co-sign gate.

**Retired routes (rev 9).** `POST /research/artifacts/source-merge/preview`, `/apply` and `/commit`:
- **The answer.** Each answers `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}` as a top-level JSON body, not FastAPI's `{detail}` wrapper (`interfaces/research/api/artifact_routes.py@2adfe06a8` ("def _source_merge_retired() -> JSONResponse:")).
- **Nothing runs first.** A handler declares no body parameter, so the reviewed packet is never parsed or validated. It returns before it opens a connection, takes a lock, reads a file, writes a receipt or emits an event. Every body, including none, gets the same 410.
- **The paths stay registered.** They are marked `deprecated` in OpenAPI, with 410 as their only documented status.
- **`alternatives` names T6's two flows** (lane A's request C3):

  | Value | The flow |
  |---|---|
  | `adopt_reading_version` | `PUT /projects/{project_id}/reading-versions/{source_document_id}` (§1.11a, "Merge later") |
  | `merge_into_write` | the §1.11 merge-draft flow into a Write deliverable |

- **No new event type.** No `source_merge.*` string is typed. THREAD-CONTRACT.md@e39840224 §1.16 ("`source_merge.*` strings are retired, never typed") is unchanged.

**Restore follows Q-B1 (rev 9).** Q-B1 asks the operator: "Does prod hold any `source_merge.committed` without a later `.restored`?"
- **The evidence** is the rows of `source_merge_body_commits` that no `source_merge_body_restores` row names by `commit_id` (`substrate/research_artifact/source_merge.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS source_merge_body_commits ("), ("CREATE TABLE IF NOT EXISTS source_merge_body_restores (")).
- **Until the operator answers, and if the answer is yes,** `restore` stays live as LB-33's branch keeps it (`interfaces/research/api/artifact_routes.py@2adfe06a8` ("Restore stays live below")). Once #3533 lands it is reachable only through the API. Its shipped shape:
  - Request: `POST /research/artifacts/source-merge/restore {document_id, parent_reading_thread_id, source_revision_id, twin_revision_id, expected_after_source_hash, expected_before_source_hash, acknowledge_restore, operator_reviewer?}`.
  - Refusals:
    - `409 source_merge_restore_acknowledgement_required` without `acknowledge_restore`;
    - otherwise a 409 carrying the store's reason: `source_merge_commit_not_found`, `source_merge_restore_binding_mismatch`, `source_merge_restore_body_unavailable`, `source_merge_source_document_not_found` or `source_merge_restore_current_hash_mismatch`.
  - A replay is idempotent through `restore_id`.
- **If the answer is no:** `restore` answers the same 410 in LB-33, and LB-33b is not built.
- **If the answer is yes:** `restore` retires with the same 410 once every listed receipt has been restored, or once the operator releases it in DECISIONS.

**The receipt read (LB-33b, rev 9; built only if Q-B1 is yes).**
- **Request.** `GET /research/artifacts/source-merge/receipts?document_id=`.
- **Response:**
  ```
  {document_id,
   receipts: [{commit_id, source_revision_id, twin_revision_id, parent_reading_thread_id,
               before_source_hash, after_source_hash, committed_at,
               restorable: bool,
               not_restorable_reason: null | "superseded_by_later_commit"
                                    | "source_changed_since_commit" | "body_unavailable"}]}
  ```
- **Which rows.** A receipt is a commit row for the document that no restore row names by `commit_id`. `committed_at` is the commit row's `created_at`. The list is newest first.
- **Why `commit_id` and `parent_reading_thread_id` are added (rev 9, beyond the grounding's shape).** The restore request takes `parent_reading_thread_id`, and the client must name exactly the commit it restores.
- **`restorable` mirrors restore's own refusals,** so lane A never offers a restore that would answer 409:
  - Restore picks the newest commit for `(document_id, source_revision_id, twin_revision_id)` (`substrate/research_artifact/source_merge.py@b41f4ec9b` ("ORDER BY created_at DESC")). An older commit with the same triple is therefore `superseded_by_later_commit`.
  - Restore refuses unless the source body's current hash equals `after_source_hash` (the store's `source_merge_restore_current_hash_mismatch`). Such a commit is `source_changed_since_commit`.
  - An empty `before_source_body` whose hash is not the empty-text hash is `body_unavailable`.
- **No writes.** The route reads through `connect_read`, takes no write lock and writes nothing.
- **Errors.** A missing `document_id` answers `422 {reason: document_id_required}`. A document with no merges answers `receipts: []`, never an error.
- **Owner scope.** Neither receipt table has an owner column, and `parent_reading_thread_id` is the per-document `read-<doc>` id. So the route admits only the operator identity, and any other caller gets `403 {reason: operator_only}`. It is listed with the pre-G7 holes (§1.15) and retires with `restore`. The edge already carries `/research/*`.

**Acceptance (red-first).**
- Preview, apply and commit each answer that 410 body. No `connect_write` opens (asserted), and no receipt row is written.
- Preview opens no writer. This is red on main, which opens `connect_write` for a route documented as "no-write".
- On Q-B1's answer:
  - if no, restore answers the same 410;
  - if yes, restore still restores a committed merge (regression).
- A grep of `apps/reading` finds 0 callers of the four routes once #3533 is in.
- LB-33b:
  - a restored commit is not listed;
  - a superseded commit reads `restorable: false`;
  - the GET writes nothing;
  - a non-operator caller gets 403.
- **Probes.** `GET /openapi.json` shows the three routes deprecated with 410, plus `GET /research/artifacts/source-merge/receipts` if LB-33b is built.

**Acceptance for the testimony gate and from-investigation (red-first).**
- A Speak claim taken down after it was sent to Write has its block text withheld on the next serve. This is red on the base, because the copy survives.
- A share or export that holds testimony answers `422 speak_publish_required` until the publish flow has cleared every claim.
- Promoting another owner's investigation answers 403, and two calls with one key create one deliverable.
- A fault after the first block leaves no deliverable (the promotion is not atomic on the base).

### 1.11a Reformat derivation: rev 9 deltas (monologues, the notebook write-up, audio, voice input, and other modalities; LB-30, LB-31)

**Two new `source` forms (rev 9).** `POST /reformats` and `POST /reformats/estimate` take exactly one of:

| Form | Since | What it is |
|---|---|---|
| `{document_id}` | rev 8 | reformulate a document |
| `{derived_asset_id, revision_id}` | rev 8 | reformulate a reformulation |
| `{scope: {project_id}, query}` | **rev 9** | a monologue (LB-30) |
| `{companion_document: {project_id, lens: "reading"}}` | **rev 9** | the Books notebook's opt-in prose write-up (LB-30; ruling 13) |

Any other shape, or more than one form, answers `422 {reason: source_invalid}`. The merge-draft form `{threads[], preview_digest}` that revision 1 of the grounding proposed is struck (D-M): a merge draft is not a §1.11a derivation.

**Two new request fields (rev 9).** Both apply to every form:
- **`input?: Input`** (§1.19; LB-12). It describes how the request's operator text was entered: `query` for a monologue, `prompt` for the other forms. For a voice input, the admission transaction enqueues `voice.captured` on the reformat thread, beside `reformat.requested`, and the answer returns its `voice_capture_event_id`. `reformat.requested` gains `input` and `voice_capture_event_id`.
- **`mothership?`**: `research | writing | reading`, attribution only (§1.13; D-P tightening 3). It is recorded on every hold of the generation, and null from a door outside the mode cycle.

Both are part of the request identity.

**The monologue source (rev 9).**
- **`scope`** takes the `{project_id}` arm of the dialogue-scope union only. O-18's answer is "project context only" (ruling 15), so `{document_id}` answers `422 {reason: source_invalid, detail: scope_document_not_supported}` in rev 9.
  - There is no Speak scope (ruling 16). `{speak_project_id}` or any other key answers `422 source_invalid`.
  - Another owner's project answers `404 project_not_found`, the same as a missing one (§1.5).
- **`query`** is 1 to 2,000 characters. It is operator-authored text, so the connective templates may quote it (rev 8.6).
- **`prompt`** is optional for this form and defaults to `query`.
- **Retrieval at admission.** The server searches the same document set that §1.8's Converse row searches, the project's member documents. The search runs under the §9.0 gate for the requester and never reaches the web. It snapshots the retrieved refs `{chunk_id, document_id, text_sha256}` into NEW `generation_records.scope_snapshot_json`.
- **What the generator is given.** Exactly the served text of those refs. A `cite_only` ref is given as a pointer, and a `withheld` ref is not given at all.
- **The core set** is the set of documents behind the snapshot's chunks. Rights follow rev 8.1 (THREAD-CONTRACT.md@e39840224 §1.11a ("Reformulating a reformulation: rights")).
- **The request identity** is unchanged apart from the two new fields: sha256(owner, source, prompt, params, input, mothership), per THREAD-CONTRACT.md@e39840224 §1.11a ("**Idempotency, state and recovery (rev 8.1).**"). The snapshot is recorded, not hashed into the identity, so a replay returns the first generation.
- **`parent_thread_id?`** is the Converse dialogue.
  - It must be the requester's `plain` dialogue (§1.2), and its scope must equal `source.scope`. Otherwise the answer is `422 {reason: parent_invalid}`.
  - The reformat thread then lists under `GET /investigations?parent_thread_id=`.

**Monologue params (rev 9).** `params` gains:
- `listening_minutes`: an integer from 1 to 120, at 150 words per minute. That is the reader's narration pace (`substrate/books/meta_reading.py@b41f4ec9b` ("NARRATION_WPM = 150")).
  - It may not be sent together with `reading_minutes`. Both together answer `422 {reason: params_invalid}`.
- `delivery: audio | text`, default `audio` (ruling 15). The text always renders alongside the audio.
- `voice?`, checked against the TTS provider's voices. An unknown voice answers `422 {reason: voice_invalid}`.
- `mode`: a `{scope, query}` source requires `mode: explain`. Any other mode answers `422 params_invalid`.

**The listening estimate (rev 9).** It is `listening_estimate {minutes, method: "words@150wpm" | "measured", shortfall: {available_minutes, reason: "thin_scope"} | null}`, carried on every `reformat.generated` and on the audio segment list. `method` becomes `measured` once every segment of the revision has been rendered (below).

**Never pad or cut (rev 9, ruling 15).**
- **The word budget** is `listening_minutes × 150`. It is split intro/body/recap at the planner's 10/82/8 (`substrate/multimedia/planner.py@b41f4ec9b` ("middle_minutes = round(request.target_minutes * 0.82, 2)")).
- **No padding.** The server never appends text to reach a budget, and the generator's instructions forbid filler.
  - When the committed script's estimate is below 90% of the request, `shortfall` is set, and `available_minutes` is that estimate.
  - The 90% threshold is lane B's proposal for the co-sign.
- **No cutting.** `_bound_to_budget` (`substrate/books/meta_reading.py@b41f4ec9b` ("def _bound_to_budget(text: str, word_budget: int) -> tuple[str, bool]:")) is never on the monologue path.
  - A chapter that comes back over its share is kept whole, and its length is reported.
  - Later chapters keep their planned shares. A total above the request is reported in `listening_estimate.minutes`, never trimmed.
- **No trimming on the client either.** The client never trims a script (Part 2 draft §B3).

**Chapters commit one at a time (rev 9).**
- **Revisions.** Revision 1 holds the first chapter (`operation: create`). Each later chapter commits the next revision of the same derived asset, bound to the same `generation_id`. The §1.11 revision rules and the §1.11a span and bite rules apply to each revision.
- **One event per chapter.** `reformat.generated` is written per chapter as `{generation_id, derived_asset_id, revision_id, chapter: {index, count, title?}, model, cost_cents, listening_estimate}`.
  - Its event id is deterministic from `(generation_id, revision_id)`. This amends rev 8.1's `(generation_id, state)` for chapter events only; `reformat.failed` keeps `(generation_id, state)`.
- **State.** The generation reads `generating` until its last chapter commits, then `committed`.
  - A committed chapter's spans answer 200 while later chapters generate.
  - The rev-8.3 `422 revision_not_committed` applies only to the revision that is still uncommitted.
- **Recovery** follows rev 8.1. An unfinished generation becomes `reformat.failed {reason: interrupted, committed_revision_id?}`. Its committed chapters stay servable.
- **Dispatch ids** are `<generation_id>:c<chapter>:<chunk_index>`, which refines rev 8.1's `<generation_id>:<chunk_index>` so that chunks of different chapters never collide.

**Estimate and admission (rev 9).**
- **The estimate.** `POST /reformats/estimate` accepts both new forms, and `assumptions` gains `tts_chars` and `voice`.
  - With `delivery: audio`, `max_cents` is the text maximum plus `tts_chars` × the TTS rate, rounded up. The rate comes from `substrate/dispatch/config.yaml@b41f4ec9b` ("input_per_mtok: 15.0  # per million characters").
  - The scope retrieval behind the estimate makes no model dispatch. That the embedding model is local is INFERRED.
- **The admission.** `POST /reformats` checks that combined maximum against `remaining_cents`, and `402 refused_capped` comes before any spend.
  - Admission reserves nothing (rev 4).
  - Each text chunk and each audio segment is still held on its own at dispatch (below).

**The notebook write-up source (rev 9).** It is `{companion_document: {project_id, lens: "reading"}}`.
- `lens` is exactly `"reading"` (lane A's request C7). `"books"` or any other value answers `422 source_invalid`.
- The project must be the requester's; otherwise the answer is `404 project_not_found`.
- **The input is spend-free.** It is the §1.12 Books-lens entries (LB-29) as served `GatedText`:
  - `served` entries give their text;
  - `cite_only` entries give pointers only;
  - `withheld` entries give nothing.
  - Building the input makes zero dispatches, and only the generation is held under the cap.
- **The snapshot.** The notebook's `content_hash` at admission is recorded as NEW `generation_records.source_content_hash`. The write-up's reader view carries `stale: true` whenever the current notebook's `content_hash` differs.
  - The request identity stays rev 8.1's (plus the two new fields).
  - This corrects the grounding, which put the hash in the identity. That would make an honest retry of the same press answer 409 after an unrelated rebuild; the recorded snapshot makes staleness visible instead.
- **The core set** is the documents that the entries' `source_refs` and `anchors` resolve to.
- **Lane A's A20(3)** ("Write it up as prose") stays disabled until LB-30 lands.

**Audio rendition (rev 9, LB-31).** A monologue's audio is cap-admitted spend (§1.13).
- **The server starts it (rev 9).** With `delivery: audio`, the server renders each chapter revision's audio as soon as that revision commits, as part of the same generation and under the admission `POST /reformats` already made, which priced the audio. No client call starts it. Its render identity is `(owner, asset_id, revision_id, voice)` with `voice` = `params.voice`, and its operation key is derived from the generation, so a recovery of the generation does not render twice.
- **`POST /derived-assets/{asset_id}/revisions/{revision_id}/audio {voice?, mothership?, idempotency_key}`** is for everything else: a re-render in another voice, a retry of failed segments (for example after "Raise today's cap"), or audio for a `delivery: text` revision.
  - Another owner's asset answers `404 not_found`, and an uncommitted revision answers `422 revision_not_committed`.
  - `voice` defaults to the generation's `params.voice`, and otherwise to the provider's default.
  - It plans the segments (below), then runs the §1.13 admission against the conservative maximum of the segments not already cached. A shortfall answers `402 refused_capped`, and nothing is dispatched.
  - It answers `202` with the segment list, and rendering runs off the event loop.
  - **Idempotency.** The identity is sha256(owner, asset_id, revision_id, voice). The same key with the same identity replays, and the same key with another identity answers `409 idempotency_conflict`. A new key for the same revision and voice reuses cached segments and dispatches nothing for them.
- **Each segment is held and settled on its own.** `reserve_dispatch` holds it and `settle_dispatch` settles it, with `kind: tts_segment` (§1.13).
  - A refused hold marks that segment `failed` with `reason: cap_reached`. The halt is scoped to that dispatch (§1.13 "Halt scope"): it refuses no other segment or render, and it never writes `investigation.cap_halted` into the reformat thread, whose generation may already be committed.
  - A render that ends with any failed segment writes NEW `reformat.audio_render_failed {generation_id, derived_asset_id, revision_id, voice, failed_segments[{n, reason: cap_reached | unavailable | failed}], cost_cents}` on the reformat thread, with an event id deterministic from the render's operation key. Lane A reads it as `refused_capped` when every failure is `cap_reached`.
- **The segment list and the stream are two routes.**
  - `GET …/revisions/{revision_id}/audio?voice=` is the segment list: `{revision_id, voice, segments: [{n, span_ids[], chars, duration_ms | null, state: pending | ready | failed | withheld, reason | null, url | null}], listening_estimate}`. A null `duration_ms` renders "—" (Part 2 draft §B3).
  - `GET …/revisions/{revision_id}/audio/{n}?voice=` streams one segment from the cache and never dispatches. It answers `200 audio/mpeg` while no span of the segment has a live gate more restrictive than it had at render. Once one does (for example, a core source is taken down), it answers `403 {reason: withheld}`. It answers `409 {reason: not_rendered}` while the segment is pending or failed, and 404 otherwise. A segment's `url` is this route.
- **Segments are made of whole served spans** (ruling 15).
  - Spans are taken in document order and grouped into segments of at most 3,500 characters of narrated text. A segment never crosses a chapter.
  - A single span above 3,500 characters is its own segment. No segment boundary ever falls inside a span.
- **Gated per span.** Each span's live gate is read at render:
  - a `served` span is narrated;
  - a `cite_only` or `withheld` span becomes the pinned spoken marker `withheld_marker/v1`, whose text LB-31 pins and §1.19's TTS gate shares. It is never the span's words. The marker is sourceless and asserts nothing.
  - The TTS request body is asserted at the provider seam to hold only served span text and markers.
- **The provider limit is UNVERIFIED.** A span longer than the provider's per-request limit is sent in sentence-aligned parts. Each part is its own dispatch `<segment_key>.<p>`, and the segment stays one audio file.
- **Dispatch id (rev 9).** It is `<generation_id>:tts:<segment_key>`, where `segment_key` = sha256(narrated text, voice, model), truncated to 32 hex digits.
  - The grounding's `<gen>:tts:<n>` would give one id to different requests after a voice change or a gate change, which rev 5 answers with `DispatchConflict`.
  - A content key makes a retry idempotent, so the retry is held and charged once, and gives a changed request its own hold.
- **The cache.** It is per owner and content-addressed by `segment_key`. Each entry stores its gate fingerprint, the ordered `(span_id, gate)` list at render.
  - It can be rebuilt: losing it costs only money.
  - This is generated audio, not a recording. Ruling 17 (no raw audio of voice notes) does not apply.
  - Its storage location is INFERRED: LB-31 names it.
- **Duration.** The measured duration of each rendered file replaces "words@150wpm".
- **The completion event.** When every segment of a revision is ready, NEW `reformat.audio_rendered {generation_id, derived_asset_id, revision_id, voice, segments: [{n, segment_key, duration_ms}], cost_cents}` is written on the reformat thread. Its event id is deterministic from `(generation_id, revision_id, voice)`.
- **The edge line** gains `/derived-assets*`, and `/reformats*` for LB-30 (§1.18).

**The listening position (rev 9)** is §1.14's row on `drv-<generation_id>`.

**Re-plan (rev 9: rule stated, route open).** The grounding says an interruption re-plan is "a `revise` with `listening_minutes = requested − elapsed` and the question as a `focus_item`" that leaves earlier revisions untouched. That conflicts with rev 8's identity `derived_asset_id = "reformat:<generation_id>"`, under which a new generation is a new asset. Rev 9 does not specify re-plan until LB-30 names its route and identity, and both lanes add them before LB-30 builds (Appendix C).

**Acceptance (red-first).**
- A 30-minute request on a thin fixture reports `shortfall` and does not pad.
- An over-budget chapter is delivered whole. This is red on the meta-reading path, which truncates.
- A grep asserts that `_bound_to_budget` is not reachable from the monologue path.
- Every chapter revision has zero unclassified spans.
- A short cap answers 402 before any dispatch, asserted by a counter at the provider seam.
- Chapter 1's spans answer 200 while chapter 2 is generating.
- A `{document_id}` monologue scope answers `422 source_invalid`.
- A `companion_document` source builds its input with zero dispatches, and a withheld entry's text never appears in the write-up's dispatch body.
- A voice `input` on a reformat writes `voice.captured` on the reformat thread and returns its id.
- Audio:
  - with `delivery: audio`, the first chapter's segments render with no client call;
  - withheld text never appears in a TTS request body;
  - no segment boundary falls inside a span;
  - a retried segment is held and charged once;
  - a voice change makes new holds, not a `DispatchConflict`;
  - a refused segment hold fails that segment only, writes `reformat.audio_render_failed`, and never `investigation.cap_halted`; after the cap is raised, `POST …/audio` renders it;
  - after a core takedown, `GET …/audio/{n}` answers 403 `withheld`;
  - the measured duration replaces the estimate.
- **Probes.** `GET /openapi.json` lists the two new forms, `input`, `listening_minutes`, `delivery` and the audio routes, plus `GET /derived-assets/{id}/revisions/{rev}/audio/{n}` (unauthenticated: the API's JSON 401, never the SPA).

**Other modalities (rev 9, ruling 18). This replaces THREAD-CONTRACT.md@e39840224 §1.11a ("Future modalities (noted, not built)"), and it is the one copy of that replacement.**
- **Talking to an asset is built.** It is a dialogue thread (§1.8): `POST /investigations {kind: dialogue, scope}` and `POST /investigations/{id}/ask`.
  - Its turns persist as `thread.turn`, with `answer.provenance` (T7), context receipts and openable refs. A turn is a thread event, not a derived asset.
  - A book scope delegates to talk-to-book.
  - A monologue it asks for is a §1.11a derivation with a listening budget, so its bites, spans and probes work exactly as for any reformulation.
  - An interjection into a monologue is an ask carrying `at {derived_asset_id, revision_id, span_id, offset_seconds}`.
  - A spoken reply is TTS over served text (§1.19).
- **Watching an asset (video) stays noted, not built.** A watch engagement would be a thread and its output a derived asset, with bites and probes working the same way. Rev 9 builds and promises nothing for it.

### 1.12 Companion document: rev 9 deltas (the Books notebook lens, LB-29; entries, MCP resources)

**The lens (rev 9).** `GET /projects/{id}/companion-document?lens=reading&document_id=&group=chapter`:
- **`lens`** is either absent (the rev-3 project companion over every member thread) or `reading` (the Books lens). Every other value, `books` included, answers `422 {reason: lens_invalid}`. There is no `books` value (ruling 1; lane A's request C7).
- **`document_id?`** narrows the entries to those grounded in that document.
  - The document must be a `primary`, `shelf` or `context` member of the project. Otherwise the answer is `422 {reason: document_not_in_project}`.
- **`group=chapter`** requires `document_id`. Without it the answer is `422 {reason: group_requires_document}`.
  - The response gains `groups: [{chapter: {title, page_index, level} | null, entry_ids[]}]`, in table-of-contents order from `book_assets.toc_json`.
  - Entries whose anchors resolve to no page fall into a final group with `chapter: null`.
- **Entries gain three fields (rev 9):**
  - `anchors[]`: §1.4 anchors into the document, each openable as a left tab (THREAD-CONTRACT.md@e39840224 §1.2 ("Openable document refs (rev 7; S1)"));
  - `chapter?`;
  - `merge_ids[]`: the committed merges (§1.10) whose accepted draft's `cited_refs` include one of the entry's pointers, in commit order. It is derived and never stored.
- **The thread set for `lens=reading`** follows lane-A default 2, which the operator may overturn, and uses the same document set as §1.2's Books lens:
  - the project's member threads, and the legacy threads that §1.2 adopts, that grounded in, opened or were filed on a primary, shelf or context document;
  - the owner's `read.book_answered` answers on `read-<d>` for those documents;
  - a ruling-11 linked research project's threads, but only those that grounded in or opened a shelf document (the same narrowing as §1.8's link layer).
- **Audiences.** The GET is owner-read: a `personal_reading` quote is served to its owner. An export or share uses the public audience, in which that quote is `cite_only`.
- **Spend** (ruling 13). The GET and every rebuild make zero model dispatches. Prose is only the opt-in §1.11a write-up.

**Rebuild triggers and staleness (rev 9).**
- The triggers are:
  - a terminal event;
  - a `thread.turn`;
  - a `read.book_answered`;
  - a resolved island;
  - a landed diligence run;
  - `project.shelf_changed`.
- **Correction.** `reading.position` is struck from the staleness list, THREAD-CONTRACT.md@e39840224 §1.12 ("a `reading.position` or `read.book_answered` event landed on the document"), which becomes "a `read.book_answered` event landed on the document". A position PUT arrives about every 10 seconds while reading and would otherwise force constant rebuilds.
- **The receipt** is the typed `companion_document.refreshed` of rev 3, gaining `lens?`. The companion stack's untyped `companion.rebuilt` on `read-<doc>` (`substrate/companions/watcher.py@f87a4db64` ("\"companion.rebuilt\",")) is never typed or read as a receipt.

**Entry identity (rev 9, the LB-9 amendment).**
- A node-backed entry's id is sha256 over `(owner_user_id, scope, scope_id, node_id)`, never over the claim text.
  - The stack hashes the text today (`substrate/companions/projector.py@f87a4db64` ("\"claim\", text, [f\"node:{nid}\", f\"doc:{document_id}\"]")).
  - Living notes rewrite that text in place, so the id would change on every refinement.
- A non-node entry keys on its stable source id in place of `node_id`: the thread id for a process entry, and the flag id for a flag entry. This list is INFERRED from the stack's `"process"` and `flag:` ids.
- The primary key moves from `evidence_id` alone (`substrate/companions/evidence_index.py@f87a4db64` ("evidence_id VARCHAR PRIMARY KEY,")) to `(owner_user_id, evidence_id)` in LB-26's re-key (§1.12a), as the lanes settled.

**Twin notes enter only through promotion (rev 9).** Signed rev 1 derives entries from each member thread's `ResearchArtifactBody` and `twin_note_taker`. Twin notes are model proposals, not graph truth (`substrate/twin_note_taker/promotion_planner.py@b41f4ec9b` ("Twin notes are model proposals, not graph truth.")). So a twin note reaches an entry only after a promotion plan has written it into a graph node through `promote_insight` or `promote_question`. An unpromoted twin note is never an entry, in any lens.

**MCP resources (rev 9; after the MCP hardening merges).** The MCP server lists `antiek://private/notes/…`, `antiek://public/notes/…` and `antiek://books/…` today (`tools/antiek_memory/__init__.py@b41f4ec9b` ("- antiek://books/{isbn}/{chunk_id}")). The hardening branch `fix/w5-mcp-hardening-20260923` (`88da9072b`) is unmerged. After it merges, rev 9 adds two resources:
- **`antiek://threads/{id}`** serves one thread's evidence base: the `evidence_index` rows of scope `thread` with that `scope_id` (§1.12a), as §1.12 entries whose text is `GatedText` only. For an agent it is the agent's own base.
- **`antiek://merges/{merge_id}`** serves one merge session as §1.10's read shape: the newest draft, or the accepted draft once committed, with text gated live.
- **Owner-bound.** Each answers only the session's own user, the thread's or the session's owner (§1.2), and otherwise answers as for a missing resource.
- **Never text that is not served.** A `cite_only` entry carries pointers only, and a `withheld` one carries neither text nor quote.

**The rights precondition is unchanged** (THREAD-CONTRACT.md@e39840224 §1.12 ("**Rights precondition.**")).

**Acceptance (red-first).**
- A living-note refinement keeps its entry id. This is red on the stack.
- Two owners rebuilding one document get distinct rows (with LB-26).
- A `personal_reading` quote is served to its owner and is `cite_only` on export.
- A `reading.position` event alone never triggers a rebuild.
- The GET and every rebuild make zero dispatches.
- An unrelated thread of a linked research project is absent.
- `lens=books` answers 422.
- An unpromoted twin note is never an entry.
- An MCP read of another owner's thread or merge answers as missing.
- **Probe.** `GET /projects/{id}/companion-document`.

### 1.12a Agents (NEW in rev 9, per D-A; LB-26)

**What an agent is (rev 9).** An agent is a promoted thread, and its id is its `thread_id`.
- There is no agents table and no `agent_id` anywhere in the MVP.
- An agent tab holds only a `thread_id` (§1.0).
- The charter is the derived asset `agent:<thread_id>`.

**Ground truth (rev 9).**
- Nothing here exists on main at `b41f4ec9b` (zero `git grep` hits).
- `derived_assets.asset_kind` admits `analysis` (`substrate/graph/schema.py@b41f4ec9b` ("'document', 'analysis', 'synthesis', 'composite'")).
- Membership keeps one row per id per project (`substrate/write/folders.py@b41f4ec9b` ("PRIMARY KEY (folder_id, node_id)")).
  - LB-2 adds `member_kind` as a plain column checked in code (`substrate/projects/schema.py@ee6867a11` ("plain VARCHAR, checked in code")).
  - LB-2 refuses re-adding an id under another kind (`substrate/projects/registry.py@ee6867a11` ("adding it again under a different kind is refused rather than guessed at")).
- Note retrieval scans the whole graph unless the caller narrows it (`substrate/context_pack/note_retrieval.py@b41f4ec9b` ("can pass ``restrict_node_ids`` to narrow it")).
- On the companion stack, `evidence_index` is keyed by `evidence_id` alone (`substrate/companions/evidence_index.py@f87a4db64` ("evidence_id VARCHAR PRIMARY KEY,")).
- The account-memory writer is `write_memory_item` (`substrate/memory/store.py@b41f4ec9b` ("def write_memory_item(")).

**Owners (rev 9).** A thread's owner is §1.2's thread-owner rule, a legacy thread counting as `__operator__`'s. The one rule for missing and foreign references is §1.15's. Applied here:
- A thread in the **path** (`POST /investigations/{id}/agent`, the charter PATCH, attach, the context route) that is not a `thread`, or is another owner's, answers `404 {reason: not_found}`.
- A thread in a **body** (a membership write, a participant, an attach item, a merge target) that is not a `thread` answers `404 {reason: thread_not_found, ref}`, and one with another recorded owner answers `403 {reason: not_owner, ref}` (D-A's "a mismatch answers 403").
- A project stays `404 project_not_found` whether it is missing or another owner's (§1.5).

**What an agent can do (rev 9).** In the MVP an agent acts only by **answering**, in a session (§1.8). No rev-9 route derives `actor: {kind: agent}`, and no server path acts for an agent.
- **Opening documents.** An answer's `source_refs` name documents and passages. Lane A may open any of them as a left tab with `branch_origin.kind: agent` and `opened_by: {thread_id: <the agent>, agent_kind}` (signed rev 7), and in the reading mode with `transient: true` (§1.6). The client writes that tab under the operator's session; the server never writes a tab.
- **Proposing.** A ref to a document outside the project is a proposal. Lane A offers Keep (the members route, `member_role: context`) or Read later (`POST /flags {intent: read}`), and the operator's press writes it as `actor: {kind: user}` (ruling 12; §1.8 book ask).
- **Research.** Research the operator launches from an agent's tab (Harden, Chase, "Research further") is an ordinary §1.3 branch from the agent's thread, with `via: chase` and the calling project's `project_id`. The launch writes the child's membership (§1.3), so step 5 of the assembler finds it, and its spend is a research start attributed to that project (§1.13).
- **`via: agent_call`** is reserved in B0's payload (§1.3) with no writer. A later revision that defines an agent action surface, with LB-10's claim-then-spawn and a server-derived agent actor, gives it one. Until then, the registry's `agent_cannot_curate` guard (§1.5) is tested by calling the registry functions directly.

**Promotion (rev 9).** `POST /investigations/{id}/agent {charter: {title, brief}, model_choice?, idempotency_key}`
- **Which threads (rev 9).** Only a `research` or `dialogue` thread can be promoted, which covers a merged thread. The rest answer `422 {reason: not_promotable, kind}`:
  - a session (a dialogue carrying `session_of`) or a group;
  - a `reformat`, `reading`, `cascade_session` or `cascade_leaf` thread.
- **Only when idle (rev 9).** A thread that is `queued`, `running` or `needs_you` answers `409 {reason: thread_active, state}`. The agent's own pack is thus fixed at promotion, and grows only by the paths in "The agent's own log", below.
- **The charter.** `title` is 1–200 characters, and `brief` is plain NFC text of at most 8,000 characters. Otherwise the answer is `422 {reason: charter_invalid, detail}`.
- **The model.** `model_choice` is validated against the owner's lineup and recorded.
- **Idempotency.** The identity is sha256(owner, `thread_id`, charter, `model_choice`), stored on the event.
  - The same key and identity replay.
  - The same key with another identity answers `409 idempotency_conflict`.
  - A thread that is already promoted answers `409 {reason: already_promoted, charter_asset_id}` to any other key.
- **The writes, in one `connect_write` transaction through the outbox:**
  - **The asset row.** `derived_assets {derived_asset_id: "agent:<thread_id>", title, asset_kind: "analysis", owner_user_id}`.
  - **Revision 1** (`operation_kind: create`). Its canonical HTML is the server's rendering of the charter: one heading block, then one paragraph block per blank-line-separated paragraph. Each block is a `user` member (§1.11 rev 6).
    - `review_id` is the promotion event's id, and `acknowledgement_version` is `"charter/v1"`: the operator's own submission is its review.
    - Both columns are NOT NULL (`substrate/graph/schema.py@b41f4ec9b` ("acknowledgement_version   TEXT NOT NULL")).
  - **The pointer.** The compare-and-set pointer is set at generation 1.
  - **The event.** `agent.promoted {charter_asset_id, charter_revision_id, model_choice?, request_identity}` goes on the thread's own log, with `operation_id` `agent_promote:<thread_id>`. The UNIQUE column means a thread is promoted once.
- **The answer** is `201 {thread_id, charter_asset_id, charter_revision_id}`.

**Charter revision, with compare-and-set (rev 9).** `PATCH /investigations/{id}/agent {charter, expected_revision_id, idempotency_key?}`
- It commits one `revise` on `agent:<thread_id>`, with compare-and-set on `derived_asset_current_revisions`.
- A moved revision answers `409 {reason: revision_moved, current_revision_id}`, the §1.11a rev-8.10 form. Lane A shows "Changed elsewhere" and rebases.
- A thread that is not promoted answers `422 {reason: not_an_agent}`.
- One transaction writes the revision, its members, the pointer update and `agent.charter_revised {revision_id, parent_revision_id}`.
- **`idempotency_key` is optional** (rev 9; matches lane A's §B2 body). The compare-and-set already makes a blind retry safe: a retry whose first attempt landed answers `409 revision_moved` with a `current_revision_id` equal to the charter it sent. When a key is sent, the same key and body replay the first answer.
- The answer is `{charter_asset_id, charter_revision_id}`. `GET /derived-assets/agent:<thread_id>/revisions` returns the charter's lineage (§1.11 flow, step 5).
- Only the operator revises a charter. No model or agent path calls this route.

**The agent's own log after promotion (rev 9).** It receives only these events:
- `agent.charter_revised`;
- `thread.context_attached`;
- `thread.merged_in` (§1.10);
- `investigation.branched` for the research launched from it (§1.3), and its `investigation.branch_abandoned`;
- `agent.autonomy_consented` and `agent.autonomy_revoked`, and only if the operator grants O-11.

It never receives a `thread.turn` (turns live on sessions, §1.8) or a retrieval. A test sends turns to the agent from two projects and asserts that the agent's log is byte-identical before and after.

**State and projection (rev 9).**
- A promoted thread reads `idle` when nothing runs (§1.2).
- `ThreadSummary.agent {charter_asset_id, charter_revision_id, home_project_id, project_ids[], managed, envelope?} | null` is entirely derived:
  - `home_project_id` is the start payload's `project_id`, or null.
  - `project_ids[]` lists the projects where the thread is an `investigation` member, sorted. Membership is the authority (D-P).
  - `managed` is true when any of its membership rows has `member_role: managed`.
  - `envelope` is present only if O-11 is granted.
- `GET /investigations?agent=true&project_id=` lists the caller's agents that are members of that project, with role `agent` or `managed`. Without `project_id` it lists all the caller's agents.
- The Autonomous roster lists `managed` agents from these rows (LB-28, §1.13).

**Membership (rev 9; the rows are §1.5's, LB-17; one rule with §1.5).** `POST /projects/{id}/members {member_kind: "investigation", member_id: <thread_id>, member_role: "agent" | "managed"}`
- **The body.** The member field is `member_id`, LB-2's name (`interfaces/research/api/project_routes.py@ee6867a11` ("if sorted(body) != [\"member_id\", \"member_kind\"]:")). Rev 9 admits `member_role` beside it. The server sets `reach`; a body that carries `reach` or `idempotency_key` answers `422 member_body_invalid`, because the route is idempotent by its natural key (§1.5).
- **`reach`.** The row gets `reach: "attached_only"`. The table's CHECK admits only that value on `agent` and `managed` rows, and null on every other row. A second value needs an operator ruling. The CHECK needs the table rebuild that §1.5 assigns to LB-17; until that rebuild, the acceptance item "a `reach` other than `attached_only` is refused by the table" is red, and a server check alone does not meet D-A.
- **The checks, in order:**
  1. The project is not the caller's: `404 project_not_found`.
  2. The id is not a `thread`: `404 {reason: thread_not_found, ref}`.
  3. The thread's owner is not the caller: `403 {reason: not_owner, ref}`.
  4. The thread is not promoted: `422 {reason: not_an_agent}`.
  5. Any project the agent belongs to, or would join by this write, is shared: `422 {reason: project_shared}`.
- **"Shared", defined (rev 9).** A project is shared when any principal other than its `owner_user_id` can access it.
  - No share store exists on main or on LB-2. This is INFERRED from their schemas: `write_folders` has one owner column.
  - The predicate `project_is_shared(project_id)` therefore answers false until G7's share store lands.
  - It ships now, with a test that flips it, so the refusal is live on the day sharing is.
- **One row, one role.** The primary key stays `(folder_id, node_id)`, so a thread holds exactly one role in a project.
  - An `investigation` member with a null role can move to `agent` or `managed`, and `agent` and `managed` can swap.
  - Going back to a null role means a DELETE followed by a plain add.
  - A member of any other kind answers `409 member_kind_conflict` (LB-2's refusal).
- **The answer** is `201 {status: added, member}`, or `200 {status: already_member | role_changed, member}`. The same transaction writes `project.members_changed` (§1.5).
- **Removal.** `DELETE /projects/{id}/members/{thread_id}` removes only that membership. The agent, its log, its other memberships and its home project are untouched.
- **T8 holds as membership (D-A).** The agent tab in project P holds P's session thread, which belongs to exactly one project.

**Sessions (rev 9; defined in §1.8, LB-21).**
- **Where turns live.** On one session dialogue per (owner, agent, project), with `participants: [agent_thread_id]` and `scope: {project_id}`. A group is the same object with 2–4 participants (LB-27).
- **Scope.** `scope` stays the union `{project_id} | {document_id}`.
- **Membership.** An agent session for project P needs the agent to be an `agent` or `managed` member of P, else `422 {reason: participants_invalid, detail: not_a_member}`, §1.8's code.

**The one assembler (rev 9, D-A).** `GET /investigations/{id}/context?project_id=`
- **Who uses it.** It is the one assembler for §1.8 asks, tier-1 continuations and LB-27 groups.
- **Access.** It uses `connect_read`, writes nothing, and is owner-scoped as above.
- **For an agent:**
  - `project_id` is required, else `422 {reason: project_required}`;
  - the agent must be an `agent` or `managed` member of that project, else `422 {reason: not_a_member}`.
- **The order (D-A).** Each item appears once, at its earliest step:
  1. The charter's current revision (`origin: operator`, `served`).
  2. The agent's own `RightsGatedPack` (§1.10).
  3. Its accepted drafts:
     - the draft named by each `thread.merged_in` on its log;
     - for a merged thread, also its own start's `accepted_draft`.

     Each is a synthesis `GatedText` under the §1.10 synthesis gate, judged live.
  4. The packs of its `merged_from` members, recursively through their own `merged_from`, to depth 8.
  5. Its own B0 children (the `investigation.branched` events on its log) that are members of the calling project. Each child contributes its pack.
  6. The turns of the session for this agent and the calling project, and of no other session. Each turn gives its question as operator text and its answer as its `GatedText`.
  7. The items attached in the calling project: the `thread.context_attached` events carrying that `project_id`, re-gated live.
- **No ambient step.** The calling project's other members are never read unless step 7 attached them or steps 4–5 reached them. Revision 1's fifth step, "the calling project's context", is removed. A ruling-11 linked project is reached only through an attach (step 7): the §1.8 link layer belongs to book sessions, not to agents.
- **Each item** is `{item_id, step, kind: charter | pack_item | draft | turn | attached, ref, origin_thread_id | null, content: GatedText, included, reason: null | budget | withheld | refs_only | depth_limit}`. The answer also carries `budget {tokens, used, basis: "reuse_token_budget/<role>"}`.
  - A `withheld` item reads `included: false, reason: withheld` and is never given to the model.
  - A `cite_only` item reads `included: true, reason: refs_only` and gives pointers only.
  - A `personal_reading` or Speak-derived item outside its home project also reads `refs_only` (O-6). Its home project is one where that document is a member, or where that Speak project's link (`member_kind: speak_project`) is. Speak items are also filtered by live consent and takedown at the moment of use (grounding §3 rule 3).
  - The budget is `reuse_token_budget(role)` (`substrate/context_pack/knowledge_reuse.py@b41f4ec9b` ("def reuse_token_budget(")), filled in step order and then pack order. An item that does not fit reads `included: false, reason: budget`. The fill is deterministic, so the same inputs always give the same receipt.
  - **`depth_limit` (rev 9)** is added beside D-A's three reasons. A `merged_from` member beyond depth 8 is listed with it rather than dropped silently (Part 2 draft §B2: "Nothing is dropped silently"). It extends D-A's closed set, so lane A and the operator accept it at the co-sign (Appendix C).
- **A thread that is not an agent** (the plain §1.8 cases):
  - step 1 is empty;
  - steps 2–5 read the thread itself;
  - step 6 reads the turns of the dialogue being asked;
  - step 7 is empty unless `project_id` is named.
- **The budget's role.** It is the dispatch role of the calling turn: `?role=`, defaulting to `thought_partner`, the ask's role (§1.8).

**Context receipts (rev 9; lane A's request C5).** Every answered turn that uses the assembler writes §1.8's one `thread.context_receipt` payload on the session's log. It is enqueued in the same outbox transaction as the `thread.turn` it describes, so an answered turn never exists without its receipt; a failed turn writes none. The ask response returns it. Lane A never computes it.

**Attach (rev 9, D-A).** `POST /investigations/{id}/attach {project_id, items[{kind: thread | doc | note | insight, id}], idempotency_key}`
- **The checks, in order:**
  1. The owner rules above.
  2. The thread is not promoted: `422 {reason: not_an_agent}`.
  3. The agent is not an `agent` or `managed` member of `project_id`: `422 {reason: not_a_member}`. (A session names the same fact `participants_invalid · not_a_member`, because there it is a participant check, §1.8.)
  4. A shared project: `422 {reason: project_shared}`.
  5. `items` must hold 1–50 entries with no repeats, else `422 {reason: items_invalid, index, detail}`.
  6. Each item must exist and be readable by the caller, else `404 {reason: item_not_found, index, ref}` or `403 {reason: not_owner, index, ref}`. A `thread` item must be a `thread` (§1.2).
- **No `project` kind.** An agent is given explicit items, never a whole project (§1.9).
- **Gated now.**
  - Any `withheld` item refuses the whole request with `422 {reason: item_withheld, index, detail: <the item's reason>}`, and nothing is written.
  - A `cite_only` item attaches with `refs_only: true`.
  - A `served` item attaches.
- **How items resolve.**
  - A `thread` item resolves through that thread's `RightsGatedPack`.
  - `doc`, `note` and `insight` items resolve through §1.9's context resolution. `ContextItem.kind` is `doc | insight` today (`interfaces/research/api/app.py@b41f4ec9b` ("kind: Literal[\"doc\", \"insight\"]")).
- **The event.** `thread.context_attached {project_id, items[{kind, id, refs_only}], via: "manual", attached_by, request_identity}` goes on the agent's log through the outbox, with `operation_id` `attach:<sha256(owner ‖ key)>`.
  - `attached_by` is derived by the server.
  - The same key and identity replay; the same key with another identity answers `409 idempotency_conflict`.
- **The answer** is `201 {event_id, items[{kind, id, refs_only}]}`.
- **Read-time gating.** The assembler re-gates each attached item at read, so an item taken down after attaching reads `withheld` in step 7.
- **Attachments stay in their project.** Only calls from `project_id` read them, so they never cross projects; merges into the agent do (§1.10).
- **One value of `via`.** `via` has the single value `manual`. A merge is never an attach (D-M).
- **Server-owned.** `thread.context_attached` and `thread.merged_in` are server-owned on `/events/typed` (§1.16). A forged one on an agent's log would reach steps 3 and 7.

**Note retrieval (rev 9).**
- Every agent path calls `retrieve_project_notes` with a non-null `restrict_node_ids`: the node ids that the assembler's steps 1–7 reached for this call.
- It is never "the nodes of the calling project", which would read the project's members ambiently.
- `None` scans the whole graph. A test asserts that no agent path passes `None`, and that an empty list returns nothing.

**The `evidence_index` re-key (rev 9; LB-26 owns it).** The id has no owner in its material (`substrate/companions/evidence_index.py@f87a4db64` ("def make_evidence_id(kind: str, identity: str, refs: list[str]) -> str:")). Two owners can therefore collide on one row.
- **The key.** The primary key becomes `(owner_user_id, evidence_id)`. The rebuild's refusal to write two live rows with one id then applies per owner.
- **A new scope.** `scope` gains `thread` (today it is `project` and `document`), both on `evidence_index` and on `companion_rebuild_receipts`. An agent's evidence base is scope `thread`, with its thread id as `scope_id`.
- **Migration by rebuild.** The module declares the table a rebuildable cache (`substrate/companions/evidence_index.py@f87a4db64` ("can be dropped and rebuilt from scratch with IDENTICAL ids")). So the re-key drops the table and rebuilds it rather than copying rows. DuckDB could not change a primary key or a CHECK in place anyway.
- **Ordering.** The re-key lands before any cross-project read (D-A). LB-29's node-keyed id material rides on the same key.
- **Red-first.** Two owners writing the same `evidence_id` get two rows, and neither owner reads or overwrites the other's. This is red against the single-column key.
- **The MCP resource.** `antiek://threads/{id}` (§1.12) serves an agent's scope-`thread` base, as `GatedText` only and bound to its owner.

**Growth and memory (rev 9, D-A).**
- **How agent state changes.** Durable cross-project state changes only through a reviewed, digest-bound merge (§1.10, into an agent) or an explicit attach.
- **O-6, amended.** O-6 now reads "never *implicitly* from turns". A turn writes only its own record and its receipt, on the session log. Red-first: after N turns in project P, the assembler for project Q returns identical steps 1–5.
- **No account-memory writes.** No agent path writes account memory until R15's proposal-and-confirmation contract lands (lane-A default 6). A test asserts the memory rows are unchanged across promotion, attach, a merge into the agent, session turns and research launched from the agent.

**Delivery and acceptance, LB-26 (rev 9).**
- **Depends on:**
  - LB-17: the membership rows, the `reach` CHECK and its rebuild;
  - LB-21: sessions;
  - LB-24a, LB-24 and LB-25: merges into an agent;
  - LB-9: the `evidence_index` store that the re-key changes;
  - LB-1(c).
- **Red-first acceptance:**
  1. An agent in two projects returns the same steps 1–4 in both. Each project sees only its own session turns and attachments.
  2. A document member of the calling project that was never attached is absent from the context. This is the no-ambient test.
  3. Budget truncation is reported per item with its reason, and each answered turn's receipt lists every assembled item.
  4. A cross-owner membership answers 403, and a project that is shared answers `422 project_shared`.
  5. The table refuses a `reach` value other than `attached_only`.
  6. A stale `expected_revision_id` answers `409 revision_moved`.
  7. No path writes the memory store.
  8. A research launch from an agent's tab with `project_id` is attributed to that project and found by step 5.
  9. A `personal_reading` item appears refs-only in another project.
  10. Attaching a withheld item is refused with its reason, and a `cite_only` item attaches refs-only.
  11. The `evidence_index` cross-owner collision test passes.
  12. The agent's own log is unchanged by turns.
  13. A running thread cannot be promoted.
  14. No agent path passes `restrict_node_ids=None`, and a linked project is absent from an agent's context unless attached.
  15. A forged `thread.context_attached` on `/events/typed` answers `422 server_owned_event`.
- **Prod probes (read-only).** `GET /investigations?agent=true` and `GET /investigations/{id}/context` each answer the API's JSON (401 when unauthenticated). The other routes are checked through `GET /openapi.json`.

**If D-A is overturned.** Ambient reach would be a new `reach` value under an operator ruling, not a new model. The receipts and O-6's refs-only rules stay as they are. A first-class agent entity would be a new store, against grounding §3 rule 1, and would be recorded as an override. The reconsider-if triggers are D-A's own.

### 1.13 Money and flags: rev 9 deltas (LB-23, LB-32, LB-28)

**Corrections to the grounding that shape this section** (evidence at `b41f4ec9b`):
1. **Diligence consent and launch do not exist on main.** Main ships only three diligence-flag routes (`interfaces/research/api/diligence_routes.py@b41f4ec9b` ("POST /diligence/flags (idempotent) · GET /diligence/queue ·")): create, the queue list and `dismiss`. `question.diligence_consented` has 0 hits in `*.py`. So LB-32's line "Consent, decline and launch stay on the shipped routes" is wrong: decline is the shipped `dismiss`, and consent and launch are the rev-3 routes, built in W2 (§1.18), not by LB-32.
2. **The diligence store holds only three kinds.** `diligence_queue.kind` is CHECK-constrained (`substrate/diligence/schema.py@b41f4ec9b` ("kind VARCHAR NOT NULL CHECK (kind IN ('concept', 'open_question', 'insight')),")). A diligence flag therefore cannot target `{anchor}`, `{claim}` or `{document}`.
3. **The to-read item has two fields named `reason`.** Signed rev 5 puts `reason: unresolved_document` on the same item that carries the flag's own `reason`. Rev 9 renames the marker `document_reason`.
4. **`BudgetLedger.debit` cannot record spend.** It refuses above the remaining balance and refuses a non-positive amount (`substrate/midnight_oil/budget_ledger.py@b41f4ec9b` ("def debit(")), so `record_dispatch` is a new operation.
5. **Main's daemon spawns without consent when the flag is on** (the roster, below).
6. **Invitee-triggered Speak follow-ups are third-party spend,** not conversational (the class table, below).

#### Spend classes (rev 9)

Every dispatch this contract adds belongs to exactly one class. The table replaces the implicit two-class split of THREAD-CONTRACT.md@e39840224 §1.13 ("**Who can hit the cap (rev 6).**").

| Class (`spend_class`) | Members (route) | Admission | Bound on the request | Can stop at the cap |
|---|---|---|---|---|
| **Research start** (`research_start`) | Harden and Chase from output (`POST /investigations {origin: {output_anchor}, purpose}`); research the operator launches from an agent's tab (§1.12a); "Research further" | The ACU gate before start, then the run's own research budget, as for islands | the research budget | No. It stops with `user`, `cancel` or `budget`. |
| **Cap-admitted generation** (`cap_admitted`) | diligence launches (`POST /flags/{flag_id}/launch`); the daemon's spawns and autonomy continuations (which are diligence launches); reformats (`POST /reformats`), including monologue text and the notebook write-up; monologue audio (rendered by the server, or `POST …/audio`); merge-draft generation (§1.10; a draft *edit* makes no model call, D-M) | `DiligenceBudget` admission (rev 4), then one `reserve_dispatch` hold per dispatch (rev 5) | the per-call upper bound (rev 5) | Yes: `cap_reached`, `cap_overshoot` (rev 6, rev 7), scoped as "Halt scope" says |
| **Conversational turn** (`conversational`) | ask, Converse and group turns (`POST /investigations/{id}/ask`; one dispatch per group turn, ruling 20); book ask (`POST /books/{id}/ask`); operator-triggered Speak follow-ups (`POST /speak/interviews/{interview_id}/followups`) | none | `max_tokens` on every request | No |
| **Operator ASR and TTS** (`operator_asr_tts`) | `POST /voice/transcribe`; `POST /speech/tts` (§1.19) | none | a 25 MiB body (LB-12); text of at most 8,000 characters (`interfaces/research/api/speech.py@b41f4ec9b` ("text: str = Field(min_length=1, max_length=8000)")) | No |
| **Third-party triggered** (`third_party`) | invitee ASR (`POST /speak/invite/{token}/voice`); invitee-triggered follow-ups (`POST /speak/invite/{token}/followups`) (rev 9 correction) | the per-owner daily Speak intake budget (below); `429 {reason: rate_limited}` when spent | a 25 MiB body (LB-13); `max_followups=3` per interview | Not applicable |

- **The rev-9 correction.** The grounding filed every Speak follow-up as a conversational turn. But the follow-ups route under `/speak/invite/{token}/` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("@speak_router.post(\"/invite/{token}/followups\")")) is driven by a token holder, not the operator. It therefore belongs with the other token-door spend under the intake budget. The operator's own route (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("@speak_router.post(\"/interviews/{interview_id}/followups\")")) stays conversational.
- **Existing sites outside the table.** Existing dispatch sites that no table row names stay outside the ledger until they are classified. This list is INFERRED and not exhaustive:
  - the reader voice-note distiller;
  - `/thought-partner`;
  - the machine TTS gateway `/multimedia/tts-gateway/synthesize`.
- **The lineup.** The NEW dispatch role `merge_draft` joins the lineup (§1.10), with an input bound and a per-call maximum for unpriced holds. Both names are INFERRED until LB-25 defines them.

#### One attribution on every ledger operation (rev 9; D-P tightening 3)

**The three operations share one attribution.**
```
reserve_dispatch(run_id, dispatch_id, max_cents, attribution)          // rev 5; attribution rev 9
settle_dispatch(dispatch_id, actual_cents)                             // copies the hold's attribution
record_dispatch(run_id, dispatch_id, actual_cents | None, bound_cents | None, attribution)   // NEW, LB-23

attribution = {
  thread_id?, project_id?, speak_project_id?,
  mothership: "research" | "writing" | "reading" | null,
  spend_class: research_start | cap_admitted | conversational | operator_asr_tts | third_party,
  kind, authority: platform | owner_byot
}
```
- **`kind` is one closed set** for holds and records:
  - held kinds: `diligence_run | reformat_chunk | tts_segment | merge_draft`;
  - recorded kinds: `ask_turn | converse_turn | group_turn | book_ask | speak_followup | asr | tts | speak_intake_asr | speak_intake_followup`.

  A research start is metered by ACU, not by these operations.
- **This replaces the rev-5 signature** `reserve_dispatch(run_id, dispatch_id, max_cents, thread_id, project_id)` (THREAD-CONTRACT.md@e39840224 §1.13 ("NEW `BudgetLedger.reserve_dispatch(run_id, dispatch_id, max_cents, thread_id, project_id)`")). The rev-5 fields are part of `attribution`, and the idempotency rule (same id, identical fields) covers the whole attribution.

**Where `mothership` comes from, route by route.** It is attribution only: validated against the closed set and never used to authorize anything.

| Route | `mothership` |
|---|---|
| `/books/*` (book ask) | `reading`, derived |
| `/write/*` | `writing`, derived |
| `POST /threads/merge/draft` | required in the body (§1.10) |
| `POST /investigations/{id}/ask`, `POST /reformats`, `POST …/audio`, `POST /speech/tts` | optional `mothership` in the body |
| `POST /voice/transcribe` | optional `?mothership=` |
| server-rendered monologue audio | the generation's `mothership` |
| Speak routes, the daemon, diligence launches | `null`: doors and background work outside the mode cycle |

**The storage.** One NEW attribution table, shared by all three operations: `midnight_oil_dispatches (dispatch_id PK, run_id, spend_class, kind, thread_id, project_id, speak_project_id, mothership, authority, hold_cents, bound_cents, actual_cents, cost_state: known | unknown, state: held | settled | recorded, created_at, settled_at)`.
- The spend ledger cannot hold an unknown cost as null: `midnight_oil_spend_ledger.amount_cents` is NOT NULL (`substrate/midnight_oil/budget_ledger.py@b41f4ec9b` ("amount_cents    BIGINT NOT NULL")).
- So the dispatch row carries the truth, and the ledger entry carries what was debited.

**`record_dispatch`, record-only settlement (rev 9, LB-23).**
- **Idempotency.** It is idempotent by `dispatch_id`. The same id with identical fields returns the first record and writes nothing. The same id with different fields raises `DispatchConflict`, as `reserve_dispatch` does (rev 5).
- **It never refuses.** It makes no ceiling check and accepts 0. The existing `debit` cannot serve here (correction 4).
- **One ledger transaction** does all of the following:
  - writes the dispatch row with `state: recorded`;
  - adds to the day's run `spent_cents` an amount chosen by what is known:
    - `actual_cents` when the cost is known;
    - `bound_cents` when the cost is unknown but the request had a bound (the conservative direction, as THREAD-CONTRACT.md@e39840224 §1.13 ("**Unknown outcome.**") settles at the full hold);
    - 0 when neither is known, for example an ASR call whose duration is unknown;
  - appends a spend-ledger entry with `event: "recorded"`;
  - marks the run `exhausted` when `remaining_cents ≤ 0`.
- **It never halts.** It writes no halt row and no `investigation.cap_halted`. Record-only threads never stop at the cap.
- **The first use of the day.** The day's run `diligence:<owner>:<day>` initializes at first use with the user-set cap (rev 4). `record_dispatch` may be that first use.
- **An unknown cost** is recorded as `actual_cents: null, cost_state: unknown`, never 0. For that day, `spend_today` on every project the record touches (`null_reasons.spend_today: cost_unknown`, §1.5) and `spent_today_cents` on `GET /settings/budget` read `null` with `reason: "cost_unknown"`.
- **Rounding.** A known cost rounds up to a whole cent per dispatch, so a known cost is never recorded as 0. The transcribe response's `cost_cents` (§1.19) is that same rounded figure.
- **Not the billing projection.** This is not `record_dispatch_for_billing` (`substrate/billing/aggregator.py@b41f4ec9b` ("def record_dispatch_for_billing(")), an in-memory billing projection over `dispatch.call` events. The two must not be conflated.

#### Halt scope (rev 9; amends rev 7's thread-wide halt)

Rev 7 made a refused hold or an overshoot a durable, thread-wide halt (THREAD-CONTRACT.md@e39840224 §1.13 ("**The halt is durable before it is announced (rev 7).**")). That fits a run, and it is wrong for a merge session or an audio render: a thread-wide `ThreadHalted` would refuse every later draft of the session, or every later render of a committed reformat, even after "Raise today's cap", and would write a terminal `investigation.cap_halted` into a thread that already committed.

Halt rows gain `scope: thread | dispatch` (`midnight_oil_dispatch_halts`, same primary key `(thread_id, dispatch_id)`):
- **`scope: thread`** (rev 7, unchanged): diligence launches, the daemon's spawns and a reformat generation's text chunks. `ThreadHalted` refuses every further hold for the thread, and the relay writes `investigation.cap_halted` as the thread's terminal record.
- **`scope: dispatch`** (rev 9): merge drafts, keyed `(thread_id: <merge_id>, dispatch_id: "<draft_id>:0")`, and audio segments, keyed `(thread_id: <reformat thread>, dispatch_id: "<generation_id>:tts:<segment_key>")`.
  - `ThreadHalted` does not apply. A refused hold refuses only that dispatch.
  - The relay delivers a refused-hold row as the flow's own failure record: `thread.merge_draft_failed {reason: cap_reached}` for a draft (§1.10), and the segment's `failed · cap_reached` state with `reformat.audio_render_failed` for a render (§1.11a). It records that event's id as `delivered_event_id`.
  - An overshoot row delivers nothing new, because the flow's terminal record already carries the billed `cost_cents`. The relay records that record's id as `delivered_event_id`.
  - It never writes `investigation.cap_halted`.
- **Red-first.** A refused hold on draft 1 does not refuse draft 2 after the cap is raised. A refused audio segment does not block a re-render after the cap is raised, and no `investigation.cap_halted` lands on a committed reformat thread. Under rev 7's thread-wide `ThreadHalted`, both tests are red.

#### O-16 and O-16b (open; rev 9 fallbacks)

- **O-16.** The operator has not ruled which class conversational turns and operator ASR/TTS belong to.
  - **The fallback** is record-only, as above: counted in spend and never refused.
  - **If the operator rules them cap-admitted,** each call site switches from `record_dispatch` to `reserve_dispatch` (holding the rev-5 per-call bound) plus `settle_dispatch`. A refused hold answers `402 {reason: refused_capped}` before the dispatch. Because these are single-dispatch requests, the refusal is a `scope: dispatch` halt, so a dialogue is never left halted. Lane A's Part 2 must then render `refused_capped` on ask, transcribe and TTS.
- **O-16b (new).** Does an owner-BYOT dispatch count against the platform daily cap? The fallback is that it is recorded with `authority: owner_byot` and counted, the conservative direction.

**Who can hit the cap (rev 9 amendment of rev 6).** The cap-admitted class is exactly the set of flows that can stop with `cap_reached` or `cap_overshoot`, and "Raise today's cap" belongs only on them. Rev 9 adds:
- monologue text;
- monologue audio;
- merge-draft generation;
- the notebook write-up;
- autonomy continuations.

Conversational, operator ASR/TTS and third-party dispatches never stop at the cap. Under O-16's fallback they can still exhaust the day for the classes that can stop. That is truthful, and O-16 decides whether it is wanted.

**The Speak intake budget (rev 9, LB-13 with LB-23).**
- **The budget.** It is per owner and per day, in cents. LB-13 sets the default in its PR, and the operator may change it.
- **The check.** Before dispatch, each invitee ASR and invitee-triggered follow-up checks that today's recorded intake plus the request's bound fits the budget.
  - Otherwise it answers `429 {reason: rate_limited}` with `Retry-After` set to the owner's next day, and nothing is dispatched.
  - The per-token and global rate limits (LB-13) answer the same 429.
- **The record.** Every intake dispatch goes through `record_dispatch` (`kind: speak_intake_asr | speak_intake_followup`, `speak_project_id` set). Invitee spend is therefore in `spend_today` and reduces `remaining_cents`.
- **The body bound.** The invitee body bound drops from 64 MiB (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("_MAX_VOICE_BYTES = 64 * 1024 * 1024")) to 25 MiB, with 413 before the provider is called.

**Acceptance (red-first, LB-23).**
- A transcription carrying a thread and a project writes one record with both, plus its `mothership`.
- A replayed `dispatch_id` writes nothing.
- `spend_today` rises by the recorded amount, and reads `null` with `cost_unknown` when any record that day is unknown.
- A record-only dispatch is never refused by the cap, and a later diligence admission sees the reduced `remaining_cents`.
- An exhausted run still accepts a record.
- An intake dispatch past the budget answers 429 and dispatches nothing.
- A hold and a record with the same `dispatch_id` and different attribution raise `DispatchConflict`.
- **Probe.** `GET /projects` showing `spend_today` (LB-17).

#### Unified flags (rev 9, LB-32)

**What main has.**
- The diligence queue: `POST /diligence/flags`, `GET /diligence/queue` and `POST /diligence/flags/{flag_id}/dismiss` (`interfaces/research/api/diligence_routes.py@b41f4ec9b` ("\"/diligence/flags/{flag_id}/dismiss\",")).
- The store is content-idempotent on `(owner, kind, object_ref)`, and a dismissed row is revived (`substrate/diligence/store.py@b41f4ec9b` ("(owner, kind, object_ref) — idempotent by construction")). Ids are `dfl-` plus 16 hex digits (`substrate/diligence/store.py@b41f4ec9b` ("return f\"dfl-{secrets.token_hex(8)}\"")).
- `GET /watch-for-later` (`interfaces/research/api/app.py@b41f4ec9b` ("List unsharpened open questions across all investigations.")) scans only `inv-*` logs, so it drops `read-<doc>` parks, and it filters no owner.
- There is no `/flags` route (0 hits), and `QuestionIdentifiedPayload` carries only `question_id`, `question_text` and `anchor_region_id` (`substrate/schemas/events.py@b41f4ec9b` ("class QuestionIdentifiedPayload(_PayloadBase):")).

**`POST /flags` (rev 3 shape, rev 9 fields).**
- **Request.** `{intent: "read" | "diligence", target, reason?, project_id?, source?: {thread_id?, document_id?}, idempotency_key}`.
- **Actor.** It is server-derived, per THREAD-CONTRACT.md@e39840224 §1.13 ("Flag identity and lifecycle (rev 3)"). Every rev-9 route acts as `{kind: user, id: <owner>}` (§1.12a "What an agent can do"). A body that carries `actor` answers `422 {reason: flag_body_invalid, detail: actor}`, the one rule shared with §1.5.
- **`reason`** is at most 280 characters, the queue's note cap (`substrate/diligence/schema.py@b41f4ec9b` ("NOTE_MAX_CHARS = 280")).
- **`source`** carries the queue's shipped `source_investigation_id` and `source_document_id`. The thread must be a `thread` (§1.2) and the requester's, and the document must be one of the requester's documents (the shipped rule). Otherwise the answer is `422 {reason: source_ungrounded}`.
- **Where each target goes (rev 9):**

  | intent | target | Store | Kind and ref |
  |---|---|---|---|
  | diligence | `{insight_id}` | `diligence_queue` | `insight`; an `insight` node must exist |
  | diligence | `{question_id}` | `diligence_queue` | `open_question`; a `question` node with that id must exist (INFERRED: every flaggable question id is a node id) |
  | diligence | `{concept: key}` | `diligence_queue` | `concept`; the key is normalized by the store |
  | diligence | `{anchor}`, `{claim}`, `{document}` | none | `422 {reason: target_invalid, detail: target_not_supported_for_intent}`. The queue's kind CHECK cannot hold them. |
  | read | `{document}`, `{question_id}`, `{insight_id}`, `{claim}`, `{anchor}` | a `question.identified` event | resolves to a document for the to-read projection |
  | read | `{concept}` | none | `422 target_invalid` |

- **Flagging agent output for diligence (rev 9; ruling 2's Flag verb).** A highlight of agent output sends the segment's `node_id`: as `{insight_id}` when the §1.4b role is `insight`, or as `{question_id}` when it is `open_question`. A thesis or component segment has no `node_id` and cannot be flagged; Harden applies there instead, and lane A disables the Flag verb. There is no output-anchor flag target (§1.3).
- **Continuing a managed thread (rev 9; LB-28's per-flag fallback).** Each continuation is a diligence flag on one of the managed thread's open questions, with `source.thread_id` set to the managed thread. This answers the cross-check's "kind `thread`" gap without rebuilding the queue.
- **Diligence writes** go through the shipped store in one `connect_write` transaction.
  - A new row answers `201`. An existing active row answers `200` untouched, and a dismissed row is revived to `queued`, also `200`.
  - `project_id` and the actor are set on insert only. A later flag naming another project returns the existing row with its stored `project_id`, so the client can see it.
- **The queue's new columns (rev 9):** `project_id`, `actor_kind`, `actor_id`, `idempotency_key` and `request_digest`, all nullable and added with `ADD COLUMN IF NOT EXISTS`. There is no table rebuild, and the kind CHECK is unchanged.
  - Legacy rows read `project_id: null` and `actor: null` with `actor_reason: "legacy"`.
- **Read writes.** A read flag is a `question.identified` event:
  - on `source.thread_id`'s log when one is given, and otherwise on `read-<document_id>` of the resolved document;
  - written through strict `emit_typed` or the outbox;
  - with `flag_id` = `question_id` = a server-minted `rfl-` plus 16 hex digits. The prefix routes `/flags/{flag_id}/…` to its store: `dfl-` goes to the queue, and anything else goes to the event log.
  - The payload gains `intent`, `actor`, `target`, `reason`, `project_id?`, `owner_user_id`, `idempotency_key` and `request_digest`. `question_text` carries the reason, or the target's title when no reason is given.
- **Idempotency.** The request identity is sha256(owner, intent, target, reason, project_id, source), and a key is unique per owner.
  - The same key with the same identity returns the first flag (200).
  - The same key with another identity answers `409 {reason: idempotency_conflict}`.
  - A key that reached an existing diligence row through content identity is not stored; its replay converges on the same row anyway.
- **Errors.**
  - `422 intent_invalid`, `422 target_invalid`.
  - `422 target_ungrounded`: no node of that type exists (the shipped `diligence_ref_ungrounded`).
  - `422 reason_too_long`, `422 source_ungrounded`, `422 flag_body_invalid`.
  - `404 project_not_found`: another owner's project reads as a missing one.
  - `409 idempotency_conflict`.

**`GET /flags?intent=read|diligence&project_id=&cursor=&limit=` (rev 9).**
- **`intent` is required.** Without it the answer is `422 {reason: intent_required}`. There are two stores, so there are two cursors.
- **Owner scope and reads.** The route is owner-scoped, reads through `connect_read` and writes nothing.
- **Paging.** Flags come newest first by `(created_at, flag_id)`.
  - `limit` runs from 1 to 100, default 50.
  - The cursor is an opaque keyset cursor, and `next_cursor` is null on the last page.
  - A flag inserted during paging lands before the cursor, so no page repeats or skips a flag.
- **`project_id`** lists flags whose stored `project_id` equals it. Legacy rows, with a null `project_id`, appear only without the filter.
- **Items:**
  ```
  {flag_id, intent, actor: {kind: user | agent, id} | null, actor_reason?: "legacy",
   target, reason: string | null, project_id: string | null, created_at, state,
   // diligence only, the shipped read-time projection:
   outcome: "completed" | "failed" | "stopped" | null, spawned_thread_id: string | null, receipt: object | null,
   // read only:
   document: {document_id, title, document_type, gate, reason} | null,
   document_reason: null | "unresolved_document"}
  ```
  `document.gate` and `document.reason` come from §1.5's one gate projection.
- **`state`:**
  - For diligence it is `queued | spawned | done | dismissed`, the shipped projection.
  - For read it is `open | done | declined`. A read flag is `done` when a sharpening event for its question exists (`QUESTION_ESCALATED_TO_RESEARCH`, `QUESTION_RESOLVED_BY_DOC` or `CROSS_DOC_QUESTION_ANSWERED`), which is the watch-for-later rule.
- **The read scan** covers every `inv-*` and `read-*` log. The owner is the payload's `owner_user_id`. Legacy parks without one list for the operator only, a pre-G7 hole. The scan's cost is the same bounded-scan risk as LB-18's.
- **The name collision (rev 9 correction).** Signed rev 5 says "the item carries `document: null` and `reason: unresolved_document`" (THREAD-CONTRACT.md@e39840224 §1.13 ("the item carries `document: null` and `reason: unresolved_document`")). That item also carries the flag's own `reason`, and one field cannot mean both.
  - The marker is `document_reason`, and the item's `reason` is the flag's reason.
  - An unresolved read flag is listed with `document: null` and `document_reason: "unresolved_document"`, never dropped.
  - Lane A's Part 2 §2.9 reads `document_reason`.

**`POST /flags/{flag_id}/decline` (rev 9 clarification).**
- For a `dfl-` id, it is the shipped dismiss: "dismiss is `decline`", per THREAD-CONTRACT.md@e39840224 §1.13 ("Store for diligence flags (rev 8").
- For a read flag, it writes NEW `question.flag_declined {flag_id}` on the flag's log.
- It is owner-scoped: another owner's flag answers `404 {reason: not_found}`.
- It is idempotent: a second decline returns the declined flag.

**Consent and launch** are the rev-3 routes, THREAD-CONTRACT.md@e39840224 §1.13 ("**Authenticated mutations (rev 3).**"). They are built in W2 (§1.18), not in LB-32, and LB-32 adds no launch path, so D4 is untouched.

**Aliases.**
- `GET /watch-for-later` and `GET /diligence/queue` stay as aliases until lane A moves its callers. THREAD-CONTRACT.md@e39840224 §1.13 ("The shipped `/diligence/flags*` routes stand") also holds for `POST /diligence/flags`, which writes the same store under the same content identity.
- The `/watch-for-later/{question_id}/launch` action stays the manual "read/run now" action (THREAD-CONTRACT.md@e39840224 §1.13 ("**No bypass.**")).

**What proceeds now, and what waits for the co-sign (rev 9).**
- **Proceeds now,** under the rev-3 and rev-8 signatures:
  - `POST /flags {intent, target, reason}` into the two stores, with the server-derived actor;
  - `GET /flags?intent=diligence`, with the cursor;
  - `decline`;
  - `idempotency_key` and `source`, which are additive and in S24's agreed shape;
  - the edge line's `/flags*`.
- **Gated on rev 9:**
  - `GET /flags?intent=read`, the to-read projection. Its only signed shape carries the rev-5 name collision, so it ships with `document_reason` once rev 9 is signed, never under the colliding name.
  - `project_id` on POST, meaning the queue column and the payload field.
  - `?project_id=` filtering. Until the delta lands it answers `422 {reason: project_filter_unavailable}`, never an unfiltered list. The filter itself is named in the signed rev-3 text, THREAD-CONTRACT.md@e39840224 §1.13 ("extended into `GET /flags?intent=&project_id=`"), with nothing to filter on yet.

**Acceptance (red-first).**
- Another owner's flags never appear.
- The GET takes no write lock and writes nothing.
- A diligence flag created with a `project_id` lists under that project and is stored in `diligence_queue`.
- An unresolved read flag is listed with its `document_reason`.
- A cursor page never repeats or skips a flag under concurrent inserts.
- An `actor` in the body answers `422 flag_body_invalid`.
- A replayed key returns the first flag, and a mismatched body answers 409.
- A diligence `{anchor}` target answers 422.
- A `read-<doc>` park appears. This is red against watch-for-later's `inv-` filter.
- **Probe.** `GET /flags?intent=diligence` (unauthenticated: the API's JSON 401).

#### The roster read (rev 9, LB-28; lane A's request C2)

**The route.** `GET /autonomy/roster` is owner-scoped, reads through `connect_read` and writes nothing. It answers:
```
{spawning_enabled: bool,
 spawning_reason: "consent_route_absent" | "env_refused" | "cap_exhausted" | "enabled",
 agents: [{thread_id, title, home_project_id, project_ids[], state,
           consent_mode: "per_flag" | "envelope",
           envelope: {max_cents, expires_at, spent_cents | null, state: "live" | "expired" | "revoked"} | null,
           spend_cents: int | null, spend_reason: null | "cost_unknown"}]}
```

**`spawning_enabled` is true exactly when `spawning_reason` is `enabled`.** The reason is the first failing condition, in this order:
1. **`consent_route_absent`.** LB-10's consent-bound, API-routed claim-then-spawn is not in this build.
   - This is computed from the build (the route's presence in the app's route table), never from configuration.
   - It is the answer at `b41f4ec9b`.
   - It must come first. On main, a truthy flag wires the diligence-queue flag source with no consent check (`orchestration/continuous/daemon.py@b41f4ec9b` ("flag_source = DbFlagSource(ensure_initialized(default_db_path()))")). The refusal in THREAD-CONTRACT.md@e39840224 §1.13 ("The daemon refuses to start with") is LB-10's and is not on main.
2. **`env_refused`.** `spawn_enabled` over the API process's environment is false (`orchestration/continuous/daemon.py@b41f4ec9b` ("ENV_DAEMON_SPAWN_ENABLED = \"ANTIEK_DAEMON_SPAWN_ENABLED\"")).
   - Both units load the same environment file. This is VERIFIED at template level: `infrastructure/ansible/templates/antiek.service.j2@b41f4ec9b` ("EnvironmentFile={{ antiek_secrets_file }}") and `infrastructure/ansible/templates/antiek-continuous-research.service.j2@b41f4ec9b` ("EnvironmentFile={{ antiek_secrets_file }}").
   - A template test pins both units to that file and asserts that neither sets the key through `Environment=`.
   - The API reads its own environment, which is loaded at unit start, so a change needs both units restarted. A systemd drop-in could still diverge; that remains a risk.
3. **`cap_exhausted`.** The day's run is `exhausted`, or its `remaining_cents ≤ 0`.
   - A day not yet initialized is not exhausted.
   - An unreadable ledger answers `503 {reason: ledger_unavailable}`, never a guessed reason. The four reasons are a closed set, and adding one needs both lanes.
4. **`enabled`.**

**Agents.**
- **Who is listed.** `agents` lists threads with a `member_role: managed` row in any of the owner's projects (D-P tightening 1). Until LB-26 and LB-28 write managed memberships, `agents` is `[]`.
  - Lane B proposes that the spawning half may ship ahead of LB-26 with `agents: []`, so that A24's banner can read it.
- **`consent_mode`** is `per_flag` (D4) unless the operator grants O-11 and the thread holds a live envelope.
  - `envelope` is null unless O-11 is granted.
  - The routes `POST` and `DELETE /investigations/{id}/autonomy` are absent until then.
  - Until then, each continuation is a per-flag diligence flag (above).
- **`spend_cents`** is today's ledger spend attributed to the thread: settled plus recorded. It is null with `cost_unknown` when any attributed record is unknown.
- **Timing.** The roster's p95 at the real count is recorded, because D-A's reconsider-if list names 250 ms.
- **The edge line** gains `/autonomy*`.

**Acceptance (red-first).**
- The roster reads `consent_route_absent` before LB-10, even with the flag on, and `env_refused` when the flag is off.
- The daemon refuses to spawn while the flag is off, even after LB-10.
- An unknown spend reads null.
- The GET writes nothing.
- An unmanaged thread is never listed or chased.
- **Probe.** `GET /autonomy/roster`.

#### Inbox kinds added by rev 9

| Kind | Source event | `ref` | `detail` |
|---|---|---|---|
| `speak_answer_received` | Speak-local `speak.answer.received` on the Speak project's log (LB-13; `substrate/speak/events.py@b41f4ec9b` ("project_id or \"speak-unscoped\",")) | `{speak_project_id, interview_id}` | — |
| `speak_claims_proposed` | Speak-local `speak.claims.proposed` (LB-13) | `{speak_project_id, interview_id}` | — |
| `monologue_ready` | a `delivery: text` monologue's final `reformat.generated`, or `reformat.audio_rendered` of its last chapter for `delivery: audio` | `{thread_id, derived_asset_id, revision_id}` | — |
| `merge_draft_ready` | `thread.merge_drafted` or `thread.merge_draft_failed` (§1.10) | `{merge_id, draft_id}` | `{state, reason?}` |

- `item_id` is the source event id (rev 2).
- For the Speak kinds, the owner is `interview_projects.owner_user_id`. The inbox reader accepts the two Speak strings by name, and they need no schema bump.

### 1.14 Reading position: rev 9 deltas (continue reading, the 409 body, listening positions; LB-14, LB-31)

**`GET /reading/continue?limit=` (NEW, rev 9, LB-14).**
- **This corrects THREAD-CONTRACT.md@e39840224 §1.14 ("`GET /reading/continue` reads the table"),** which describes a route with 0 hits on main.
- **Owner.** The owner comes from `_reader_owner_id(request)` (`interfaces/research/api/books.py@b41f4ec9b` ("def _reader_owner_id(request: Request) -> str:")), the reading-state routes' own boundary.
- **The store call.** It reads through NEW `ReadingStateStore.list_for_owner(owner, limit)`. The store has only `get` and `put` today (`substrate/books/reading_state.py@b41f4ec9b` ("class ReadingStateStore:")).
  - Rows come by `updated_at` descending, with `document_id` breaking ties.
  - `limit` runs from 1 to 50, default 20. Any other value answers 422.
- **No writes.** It reads through `connect_read` with a bounded external wait, and a lock timeout answers `503 {reason: reading_busy}`. It takes no write lock and writes nothing.
- **Items:** `{document_id, title, author, document_type, gate, reason, progress: {page_index, page_count, pct} | null, updated_at}`.
- **`progress`** is null unless a `book_assets` row with `page_count > 0` exists. `page_count` defaults to 0 (`substrate/graph/schema.py@b41f4ec9b` ("page_count               INTEGER NOT NULL DEFAULT 0,")), and the LB-35 fallback sets it to 0 (§1.18a), so a 0 count reads null, never 0%.
  - Otherwise `pct = floor(100 × min(page_index + 1, page_count) / page_count)`.
- **`gate` and `reason`** come from §1.5's one gate projection for the requester. A row whose document is gone lists with `title: null` and `withheld · unresolved`. It is never dropped.
- **No type filter.** A reformulation's reader view `drv-…` lists with `document_type: "derived"` (`substrate/reformat/pipeline.py@c0845e327` ("document_type=\"derived\",")) and its source's live gate. A non-book document (§1.18a) lists with `progress: null`. Lane A decides how each is presented.
- **The prefs allowlist stays empty** (`substrate/books/reading_state.py@b41f4ec9b` ("PREFS_V1_ALLOWLIST: frozenset[str] = frozenset()")) unless the operator rules otherwise.
- **The edge** already carries `/reading/*`.

**The 409 extension (rev 9: status and owner).**
- At `b41f4ec9b` both 409 sites of `interfaces/research/api/reading_state_routes.py` still answer only the string detail `reading_state_stale_revision: …`.
- Rev 9 assigns THREAD-CONTRACT.md@e39840224 §1.14 ("Extension (NEW, rev 8.7)") to LB-14, which touches the same store.
- **The body** is top-level JSON: `409 {reason: "reading_state_stale_revision", current}`.
  - `current` is the GET shape `{document_id, page_index, anchor_ref, prefs, revision, updated_at}`.
  - It is `null` when no row exists, which is the case of a PUT with `revision > 0` against no row.
  - Both sites answer it.
- Until it ships, the rev-8.7 refetch stays the contract.

**Listening positions (rev 9, LB-31).**
- A monologue's position is the §1.14 row on `drv-<generation_id>`. The text reader shares the same row, as one position per owner and document.
- **What `page_index` holds.** It is the reader page of the `drv-` view that holds the first span of the playing segment, and playback resumes at the start of that segment. That the view's pagination places each span on one page is INFERRED; a span that crosses a page takes its first page.
- **No offset inside a segment.** An offset within a segment is not persisted, because the prefs allowlist is empty and the 20-character `anchor_ref` must name a highlight. Persisting it needs an operator ruling on the allowlist, which is open (Appendix C).

**Acceptance (red-first).**
- A zero or unknown page count reads `progress: null`.
- While another process holds the writer, the GET answers a bounded 503 and takes no write lock.
- Another owner's rows never appear.
- The 409 carries `current`, and it is `null` when no row exists.
- **Probe.** `GET /reading/continue`.

### 1.15 Rights and owner preconditions: rev 9 (one list)

**Owner-scoped from day one (rev 9).** Every route rev 9 adds is owner-scoped from its first commit (THREAD-CONTRACT.md@e39840224 §1.15 ("Every route this contract adds is owner-scoped from day one")):
- **Registry (§1.5, §1.5a, §1.6):** `GET` and `POST /projects`; `GET` and `PATCH /projects/{id}`; the members `POST` and `DELETE`; the shelf `GET` and `PUT`; `DELETE /projects/{id}/products/{product}`; `GET …/transfer-candidates`; `POST` and `GET …/transfers`; the tab routes (LB-2).
- **Threads (§1.2–§1.4b, §1.8, §1.12a):** the rev-9 filters of `GET /investigations`; the dialogue create; `GET /investigations/{id}/outputs`, `/turns` and `/context`; `POST /investigations/{id}/ask` and `/ask/estimate`; `POST` and `PATCH /investigations/{id}/agent`; `POST /investigations/{id}/attach`.
- **Merge (§1.10):** `/threads/merge/preview`, `/threads/merge/draft/estimate`, `/threads/merge/draft`, `…/draft/{draft_id}/revise`, `…/draft/{draft_id}/cancel`, `GET /threads/merge/{merge_id}/draft` and `POST /threads/merge`.
- **Money and flags (§1.13):** `/flags*` and `/autonomy*`.
- **Reading (§1.8, §1.11a, §1.12, §1.14):** `/reading/continue`; the ownership checks of the two new §1.11a `source` forms; `/derived-assets/{id}/revisions/{rev}/audio*`; the `shelf` and `library` scopes of `/books/{id}/ask`; `GET /projects/{id}/companion-document?lens=reading`.
- **Speak (§1.5a, §1.20):** `/speak/sections`, `/speak/projects/{id}/detail` and the Speak draft extension.
- **Voice (§1.19):** the `thread_id` and `project_id` of `/voice/transcribe`, and the `source` of `/speech/tts`.
- **MCP (§1.12):** `antiek://threads/{id}` and `antiek://merges/{merge_id}`.

**Missing and foreign references (rev 9; one rule for every route).**
1. **A resource in the path** (a thread, project, merge session, draft, derived asset or flag) that is missing, is not of the route's type (for a thread, anything §1.2's predicate does not call a `thread`), or is another owner's answers `404` with the route's not-found reason: `not_found` for threads, derived assets and flags; `project_not_found` for registry projects (LB-2); `merge_not_found` for merge sessions; `draft_not_found` for drafts; Speak's own not-found for Speak projects. Existence is never disclosed.
2. **A thread named in a body** (seeds, transfers, merge members and targets, agent memberships, participants, attach items, flag sources, from-investigation) that is not a `thread` answers `404 {reason: thread_not_found, ref}`. One whose recorded owner differs from the requester answers `403 {reason: not_owner, ref}` (D-A's "a mismatch answers 403").
3. **A registry project named in a body** answers `404 project_not_found` whether it is missing or another owner's (LB-2).
4. **Any other body reference** (a document, a derived asset, a Speak item) that is missing answers `404 {reason: source_not_found, ref}`. Documents are corpus rows and are not owner-checked; their rights gate governs them (§1.5). A derived asset with another owner answers `403 {reason: not_owner, ref}`.
   - **Except a private document (A06, below).** A `user_authored_private` document is discoverable only by its exact owner: its `owner_user_id` equals the verified requester. Another owner's private document answers exactly as a missing one, `404 {reason: source_not_found, ref}`. That check runs before any of its metadata, references or context is read into the answer, so existence is never disclosed.
   - Legacy `user_owned` rows keep today's behaviour, which stays OPEN until PA06 (below).
5. **B0's shipped parent answer stands.** A parent that is not a `thread`, or is another owner's, answers `422 parent_investigation_not_found` (§1.3).
6. **Legacy threads.** A thread whose start records no owner is `__operator__`'s (§1.2).

**A06: private authored content (rev 9; the backend's A06; operator ruling 2026-09-27, "A06 private-authored upload gating").** This section states the settled rules. The implementation is the backend's, and #3415's re-attestation block is retained as described.

- **The class.** `user_authored_private` holds authored notes and drafts. Upload is its activation entry point.
  - The only other way a row gets the class is a verified same-owner private derivative (PA04). The caller and every source document's owner are verified and equal, and the output records its owner, the class and its lineage.
  - A derivation with mixed or unproven authority, or whose output schema cannot represent private lineage, is refused before anything persists.
  - It is owner-readable: it joins the owner full-read allowlist `PERSONAL_READABLE_CONTENT_CLASSES` (`substrate/books/serve.py@b41f4ec9b` ("owner_personal_reading")).
  - It is never in the public-servable set and never ad-eligible.
  - The legacy `user_owned` class stays as it is, with its exposure open by record; it is not reclassified.
- **Precondition, before any upload can mint the class.** The retrieval gate's non-privileged clause is a denylist (`substrate/graph/retrieval_gate.py@b41f4ec9b` ("content_class NOT IN ({placeholders}))")), so an unrecognised non-NULL class reaches non-privileged retrieval until someone adds it by hand.
  - Adding `user_authored_private` to that denylist is not enough. The canonical non-privileged chunk predicate **fails closed**: a non-NULL class it does not recognise is excluded. The same applies to #3264's `owner_body_sql` for owner-only arms.
  - Explicit legacy `user_owned` and NULL keep today's behaviour, deliberately and by record (OPEN). They are not relabelled.
  - Red-first controls:
    - A seeded unknown-class document is absent from graph, VSS, lexical and external-candidate hydration, and from direct `/chunks`.
    - A `user_authored_private` document with chunks is absent from non-privileged retrieval and present for its owner.
- **Order inside the upload's write.** Everything runs under one write lock, **before any write**:
  1. **Foreign-owner admission.** A foreign row never reaches a stored-attestation detail.
  2. **Token resolution.**
  3. **The re-attestation matrix.**

  A refusal writes nothing: no document, chunk, book record or sidecar.
- **The re-attestation matrix** (stored class → resolved requested class; backend INBOX 00:10Z):
  - same → same is idempotent;
  - `user_owned` → `personal_reading` is allowed (#3415's legacy rule, unchanged);
  - `user_authored_private` → `personal_reading` is allowed (restrictive authorship correction);
  - `personal_reading` → `user_authored_private`, any private class → a public class, and `user_owned` → `user_authored_private` (no adoption of a legacy row) are all `409 upload_attestation_conflict`, for the **same owner's** row only;
  - any other stored class, a takedown class included, is 409.
- **Token resolution** (00:20Z as narrowed at 00:40Z):
  - On a **fresh** owner-scoped write, both the explicit token `user_authored_private` and the legacy request token `user_owned` (a compatibility alias) mint `user_authored_private`. A fresh write never mints a public class.
  - The one legacy idempotent case (a stored legacy `user_owned` row re-uploaded with the alias stays `user_owned`, unchanged) applies **only** with independently proved exact-owner and full-source evidence.
  - It never adopts a row whose owner is the operator/global default (`__operator__`), which is every legacy row today.
  - **The default is to create the owner-scoped v2 row and leave the legacy row alone.**
- **What the upload answers.** `UploadResponse.content_class` is the class in effect after the call, never the one requested.
- **Advertising the token.** NEW `GET /sources/upload/attestations`. It is static, reads no DB and takes no lock, and it answers `{accepted: [...], authored_default: "user_authored_private", aliases: {"user_owned": "user_authored_private"}}`. It sits under the existing `/sources*` edge glob.
- **The client rule: disable until confirmed (the operator's ruling).**
  - Private-authored submission is enabled **only** when that route lists `user_authored_private`.
  - When the route is absent, errors, or does not list it, private-authored submission is **disabled**, with an honest "needs a server update" state.
  - The client **never** falls back to `user_owned` or to any legacy public behaviour for authored content, because on an API without A06 `user_owned` is served publicly. Publication consent is never inferred.
- **Recognising the class is not a separate step (the deployment composition).** Adding `user_authored_private` to the canonical vocabulary (PA01) immediately lets the generic programmatic writers accept it:
  - `register_source_document` (`substrate/rights/register.py@b41f4ec9b` ("def register_source_document("));
  - `register_book` (`substrate/books/ingest.py@b41f4ec9b` ("def register_book("));
  - `ingest_servable_book` (`acquisition/books/adapter.py@b41f4ec9b` ("def ingest_servable_book("));
  - `publish_converted_book` (`substrate/book_import/publish.py@b41f4ec9b` ("def publish_converted_book(")).

  Their owner defaults do not prove a verified subject, and the direct bridge and CLI paths already bypass vocabulary validation. The fixed Sources upload tuple and the EPUB Literal stay closed, so those HTTP endpoints do not open by themselves.
  - So PA01 recognition deploys only as part of **one verified composition**. That composition holds PA01 recognition, the relevant PA01–PA04 denial gates, and each actual producer's verified authority or pre-write refusal.
  - Each generic writer is a named entry in the PA04c producer ledger.
  - PA01 may be implemented locally under its exact claim, but it never deploys alone (Astra, `specs/antiek-backend-forensic-20260927/children/private-authored-content/vocabulary-activation-audit.md`).
- **Activation (PA05)** follows that composition and the real-login proof below. It waits until the PA01–PA04 denial gates are integrated, deployed and observed. Those gates cover:
  - body and chunk reads;
  - metadata and containers;
  - cached and saved references;
  - every present derivative producer: one ledger row each, with a tested fail-closed disposition, proved on its real serialized output rather than a helper;
  - attribution, training and export.
- **The activation receipt** records:
  - the deployed API SHA(s) carrying PA01–PA04, composed with #3264 and D-1. This is one verified composition that includes PA01 recognition and every generic writer's authority or refusal;
  - the frontend SHA that enforces the capability-disabled state;
  - the deployed **auth-foundation SHA**, the verified-subject foundation that maps a verified login to a durable owner. Its candidate is D2's local `3a307dace`, which is unmerged; its integration and independent proof are coordinated with that claim's owner;
  - **real supported login and code exchange** for two verified subjects, through the real middleware:
    - they yield distinct durable owner ids, and each id is stable on a repeat login;
    - each subject then uploads, reads its own document, and is denied the other's.

    Email delivery may be stubbed offline. Subject verification, principal assignment and cookie signing may not.
  - signed A, B and absent-owner probes on that deployed composition. These prove the downstream gates only, not that ordinary login produces those owners.

  A merged PR or a local test packet is not a deployed privacy result. Until the receipt exists, the capability route does not list the token and the client stays disabled.
- **Why real login is a prerequisite** (Astra, `specs/antiek-backend-forensic-20260927/children/private-authored-content/auth-subject-activation-prerequisite.md`).
  - On main, every login path mints the operator: the callback, the code claim, passkey and dev-login (`interfaces/research/api/auth.py@b41f4ec9b` ("mint_session_cookie("), all four call sites, lines 530, 633, 689 and 768, each with `user_id="__operator__"`).
  - A06 refuses the operator/default owner for a new private row. So until the auth foundation is deployed, no ordinary login can complete a private upload.
  - The gate is not weakened to get around this.
- **Dev-login stays the legacy operator bootstrap** (A20). It is not account-subject mapping, and A06 does not change it. This section grants no new auth architecture and adopts no historical owner.
- **Historical `user_owned`** stays OPEN until PA06's reviewed disposition has been executed and verified.

**Pre-multi-user holes (G7), the full rev-9 list.** The signed list stands (THREAD-CONTRACT.md@e39840224 §1.15 ("These routes take no owner filter today:")); rev 9 adds the rest:
- `GET /research/{id}/artifact.html` and `twin-notes.html` (signed).
- `GET /trajectory/{id}` and the collection `GET /trajectory` (signed for the first). Rev 9 makes both skip merge-session logs and otherwise does not widen them (§1.10).
- The unfiltered `GET /investigations` (signed); rev 9's filters are owner-scoped (§1.2).
- `/write/folders` and `/write/blocks/search` (signed), until LB-2's owner scoping merges.
- The `/twins` routes (signed).
- `WS /ws/events`, which has no owner filter (§1.7, §1.10).
- `POST /events/typed`, which takes a client `investigation_id` with no owner check (`interfaces/research/api/app.py@b41f4ec9b` ("async def post_typed_event(envelope: TypedEventEnvelope) -> EmittedEventResponse:")). Rev 9 narrows it by the server-owned list and the `project-`/`merge-` refusal (§1.16), not by owner.
- `promote_investigation_to_deliverable`, until LB-15's owner check (§1.11).
- `note_retrieval`, which scans the whole graph when `restrict_node_ids` is `None`. Agent paths never pass `None` (§1.12a).
- The bare `{text}` form of `/speech/tts`, which cannot be gated (§1.19).
- `/books/{id}/voice-note`, which writes into a client-named `investigation_id` (§1.19).
- `GET /speak/projects` and `GET /speak/projects/{id}`, until LB-15.
- `/speak/pushes` and `list_private_repings_at`, whose SQL has no owner predicate (§1.20).
- LB-33b's receipt read, operator-only, if it is built (§1.11).
- `GET /books/{id}`, which is library-wide, and the owner full-read, which has no per-document owner check (LB-35 spec Q10).
- The `read-<doc>` ids, keyed per document, not per owner (book sessions, book ask, read flags).
- Legacy `question.identified` parks with no owner (§1.13).
- `resolve_owned_corpus`, which has no owner filter (§1.8).
- Legacy threads with no recorded owner, which count as `__operator__`'s (§1.2).
- `project_is_shared`, which answers false until G7's share store exists (§1.12a).
- Uploads stamp no owner (rows default to `__operator__`), and their ids derive from the bytes alone. This lasts until A06's owner stamping and cross-owner rule land (above).
- Every login path mints `__operator__` (the callback, the code claim, passkey and dev-login). This lasts until the verified-subject auth foundation is deployed (A06's activation receipt, above); dev-login stays operator by design.

### 1.16 Schema sequencing: rev 9 (one table)

**The v41 collision (rev 9).** Main is at 40. Both unmerged carriers set 41: LB-2 (`substrate/schemas/events.py@ee6867a11` ("# v41: project.tabs.version_bumped")) and c2-export (`substrate/schemas/events.py@2be3e0d1b` ("# v41: Mothership B0")).
- Numbers are assigned at merge, in merge order. Every carrier below carries the renumber-at-merge preflight that the signed text gives c2-export (THREAD-CONTRACT.md@e39840224 §1.16 ("It carries a renumber-at-merge preflight")).
- Whichever of #3530 and c2-export merges second becomes 42, and each later carrier takes the next number at its merge.
- So B0 ships as one bump, whatever its number. It is not necessarily v41.

**One bump per carrier, with codegen in the same commit (rev 9).** The first package of a tier to merge carries its tier's whole bump and registers every payload of the tier, including payloads whose emitter lands later in the tier. The signed W1, W2 and W3 bumps stand; where a wave and a tier land in one PR, they share one bump.

| Bump | Carrier | Events and payload changes | Graph-schema changes |
|---|---|---|---|
| LB-2 | #3530 | `project.tabs.version_bumped` (broadcast only) | `project_tabs`, the retirement table, the number registers, the rev-7 registry columns |
| H | the first package that persists `html-text/v1` anchors (the backend's A03 or projector PR, expected) | none | `anchored_highlights` gains `text_projection` and `served_body_sha256` (§1.4c, lane B note (a)) |
| B0 | the c2-export merge | the signed B0 set (`investigation.branched`, `investigation.branch_abandoned`, `investigation.reserved`, `QuestionEscalatedToResearchPayload.launched`, the chase-halt reason `branch_not_recorded`); rev 9's `BranchOrigin.output_anchor`, `purpose` and `target`; `via: agent_call` (reserved); the docstring correction | none |
| F | LB-32's signed half (tier 1, proceeds now) | `question.identified` gains `intent`, `actor`, `target`, `reason`, `owner_user_id`, `idempotency_key` and `request_digest`; NEW `question.flag_declined` | `diligence_queue` gains `actor_kind`, `actor_id`, `idempotency_key` and `request_digest` |
| T1 | the first tier-1 package to merge (LB-17 expected) | `project.created`, `project.updated`, `project.members_changed`, `project.shelf_changed`, `project.product_left`, `project.transferred`; `question.identified` gains `project_id?`; `InvestigationStartRequestedPayload` gains `project_id` and `title` (signed W1 fields, needed by the `launch_first_question` launch) | the registry columns (`home_product`, `products`, `seed_json`, `shelf_version`, `derived_from_project_id`); **the `write_folder_members` rebuild** with its CHECKs; `project_create_requests`; `project_transfers`; `diligence_queue.project_id` |
| T2 | the first tier-2 package to merge (LB-24a expected) | `thread.dialogue_started`, `thread.turn_requested`, `thread.turn` (rev-9 fields; folded here from W2 because §1.8 rewrites it), `thread.turn_failed`, `answer.provenance`, `thread.context_receipt` (§1.8's one payload); `InvestigationStartRequestedPayload` gains `origin`, `input`, `continue_from_parent`, `voice_capture_event_id`, `merged_from`, `merge_id` and `accepted_draft`; `VoiceCapturedPayload`: `duration_seconds` becomes nullable, and it gains `edited` and `asr_model`; `read.book_answered` gains `scope`, `project_id?` and `source_refs[]`; `thread.merge_started` and `investigation.merged_into` (LB-24a's commit skeleton) | `midnight_oil_dispatches`; the halt table's `scope` column (LB-23) |
| T3 | the first tier-3 package to merge (LB-25 expected) | `thread.merge_draft_requested`, `thread.merge_drafted`, `thread.merge_draft_failed`, `thread.merge_draft_revised`, `thread.merged_in`; `agent.promoted`, `agent.charter_revised`, `thread.context_attached`; `agent.autonomy_consented` and `agent.autonomy_revoked` only if O-11 is granted; `companion_document.refreshed` gains `lens?`; `reformat.requested` gains `input` and `voice_capture_event_id`; `reformat.generated` gains `chapter` and `listening_estimate`; `reformat.failed` gains `committed_revision_id?`; NEW `reformat.audio_rendered` and `reformat.audio_render_failed` | the `evidence_index` re-key (drop and rebuild) and `scope: thread` on `evidence_index` and `companion_rebuild_receipts` (LB-26); `generation_records.scope_snapshot_json` and `source_content_hash` (LB-30); the audio cache (LB-31) |

- **The two member-table rebuilds are different tables.** The rev-6 rebuild that §1.16 schedules for W3 (THREAD-CONTRACT.md@e39840224 §1.16 ("the member-table rebuild in W3")) is `derived_asset_revision_members` (§1.11), and it stays in W3. The `write_folder_members` rebuild is new in rev 9 and rides T1 with LB-17.
- **The signed flag lifecycle** (`question.diligence_consented`, `…_declined`, `…_launched`, `…_refused`) stays in W2's bump.
- **Not typed.** `dialogue.round` is withdrawn (ruling 20). `companion.rebuilt` and every `source_merge.*` string are never typed. The Speak strings `speak.answer.received` and `speak.claims.proposed` stay Speak-local and need no bump.

**Server-owned events (rev 9; one list).** `POST /events/typed` accepts any typed payload today (`interfaces/research/api/app.py@b41f4ec9b` ("async def post_typed_event(envelope: TypedEventEnvelope) -> EmittedEventResponse:")). A forged event on these types would be read as the server's own. For example, a forged `thread.context_attached` or `thread.merged_in` on an agent's log would reach assembler steps 3 and 7 and carry context across projects; a forged `investigation.start_requested` would start a run with no ACU charge.
- It refuses every envelope whose `action_type` is in this list, with `422 {reason: server_owned_event, action_type}`:

  | Section | Server-owned types |
  |---|---|
  | §1.3 | `investigation.branched`, `investigation.branch_abandoned`, `investigation.reserved`, `investigation.start_requested` |
  | §1.5, §1.5a | `project.created`, `project.updated`, `project.members_changed`, `project.shelf_changed`, `project.product_left`, `project.transferred`, `seam.research_to_read`, `seam.speak_to_write` |
  | §1.8 | `thread.dialogue_started`, `thread.turn_requested`, `thread.turn`, `thread.turn_failed`, `answer.provenance`, `thread.context_receipt` |
  | §1.10 | `thread.merge_draft_requested`, `thread.merge_drafted`, `thread.merge_draft_failed`, `thread.merge_draft_revised`, `thread.merge_started`, `investigation.merged_into`, `thread.merged_in` |
  | §1.11a, §1.12 | `reformat.requested`, `reformat.generated`, `reformat.failed`, `reformat.audio_rendered`, `reformat.audio_render_failed`, `companion_document.refreshed` |
  | §1.12a | `agent.promoted`, `agent.charter_revised`, `thread.context_attached`, `agent.autonomy_consented`, `agent.autonomy_revoked` |
  | §1.13 | `question.identified` (it carries the server-derived actor), `question.flag_declined`, `question.diligence_consented`, `question.diligence_declined`, `question.diligence_launched`, `question.diligence_refused`, `investigation.cap_halted`, `launch.refused` |
  | §1.14 | `reading.position` |
  | §1.19 | `voice.captured`, once lane A's A17 has retired the client post |

- It also refuses any envelope whose `investigation_id` starts with `project-` or `merge-`, whatever its type, with `422 {reason: server_owned_log}`.
- Every other type a client posts today (for example `marginalia.noted`, `source.read` or `seam.read_to_research`) is unchanged. The owner hole on `/events/typed` stays listed (§1.15).
- The refusals keep the route's legacy string `detail` beside the new `reason` (§1.0a "Error bodies").

### 1.17 Answers to Part 2's open questions: rev 9 delta

- **Q-A5 (rev 9):** a standalone book is `kind: reading` with its `primary_document_id`. It joins a research project by the ruling-11 link (§1.5), and it is promoted in place only by "Turn this book into a new project" (§1.5a T6). This replaces THREAD-CONTRACT.md@e39840224 §1.17 ("**Q-A5:** `kind: reading`, promoted in place (§1.5).").

### 1.18 Lane B delivery order: rev 9 (one order for LB-12 to LB-35)

The signed steps B0, W1, W2 and W3 stand (THREAD-CONTRACT.md@e39840224 §1.18 ("Lane B delivery order (matches ROSTER first use)")). Rev 9 appends its tiers after them.

| Tier | Packages | Gate | Order inside the tier |
|---|---|---|---|
| 0 | LB-12 (its server half: off the loop, the 25 MiB bound, transcribe persists nothing, the TTS `source` gate), LB-13, LB-14, LB-15, LB-16, LB-33, LB-33b (only if Q-B1 is yes), LB-34 | Outside the co-sign gate: forward fixes that consume no rev-9 seam | LB-33 lands after lane A's #3533. LB-16 lands after LB-34's predicate. LB-16's count definitions ship as provisional (§1.20). |
| gate | LB-1(c) | Rev 8 signed (done at 8.10); rev 9 Part 1 drafted, audited by a different lineage, findings closed, and co-signed by both lanes | — |
| 1 | LB-17, LB-18, LB-32, LB-35 | LB-2 (#3530) merged, and LB-1(c) for the rev-9 deltas | LB-17 before LB-18. LB-17 wires `recover_pending_events` at startup. LB-32's signed half and LB-35's signed rev-7 half proceed before the co-sign; only their rev-9 deltas (`diligence_queue.project_id`; ruling 12's shelf admission, which is LB-17's) wait. |
| 2 | LB-24a first, then LB-19, LB-20, LB-21, LB-22, LB-23, and LB-12's consuming half (`input` and the server-minted capture) | The c2-export merge (B0 with the rev-9 origin fields, plus the wave-5 resolvers), LB-3, the §1.13 ledger extension, and LB-1(c) | **LB-24a precedes every pack consumer** (LB-20's output branches and tier 1, LB-21's branched dialogues, LB-25, LB-26). LB-22 also needs LB-17 (the shelf) and LB-35 (non-book refs). |
| 3 | LB-24, LB-25, LB-26, LB-27, LB-28, LB-29, LB-30, LB-31 | The W3 merge, LB-24a and LB-9. LB-30 and LB-31 also need §1.11a (LB-4b, LB-5); LB-25 does not (D-M). LB-28's spawning needs LB-10, and its envelope half waits on O-11. | LB-26 before any cross-project read (the `evidence_index` re-key). LB-24's into-agent target after LB-26. LB-28's roster spawning fields may ship ahead of LB-26 with `agents: []`. |

**Edge lines.** Each package that adds a top-level prefix adds it to the one-line `@api_routes` allowlist (`infrastructure/ansible/templates/Caddyfile.j2@b41f4ec9b` ("@api_routes path /account/*")) in the same PR, with the full-glob guard:
- `/projects*` (LB-2, already on its branch);
- `/threads*` (LB-24a);
- `/flags*` (LB-32);
- `/reformats*` (LB-30) and `/derived-assets*` (LB-31);
- `/autonomy*` (LB-28);
- `/inbox*` (W3's inbox).

`/reading/*`, `/speak/*`, `/books*`, `/voice/*`, `/speech/*` and `/research/*` are already present. The line is a merge hotspot that both lanes touch.

**Every package closes on the DB-B bar.** Red-first tests, mutants, the full sweep, a different-lineage critic's ACCEPT, the Nudge train, and read-only prod probes with `build_sha` equal to the merge SHA.

### 1.18a Non-book documents in the reader (rev 9 statement of the rev-7 W1 row; LB-35; details per the LB-35 spec)

THREAD-CONTRACT.md@e39840224 §1.18 ("non-book documents served to the reader (lane A F8)") promises this in W1. Rev 9 states the contract at that level. `cockpit/LB-35-SPEC-2026-09-27.md` owns the details.

**Today.**
- `GET /books/{id}` (`interfaces/research/api/books.py@b41f4ec9b` ("async def get_book(document_id: str) -> BookDetail:")) answers `404 book_not_found` for any document without a `book_assets` row.
- Text serving already resolves every `documents` row (`substrate/books/serve.py@b41f4ec9b` ("LEFT JOIN book_assets b ON d.document_id = b.document_id")). It does so through the single guard (`substrate/books/serve_guard.py@b41f4ec9b` ("This module is the ONE sanctioned caller of ``serve_full_text``")).

**Rev 9 (per the LB-35 spec, D1–D3).**
- **Which documents.** `GET /books/{id}` answers for every `documents` row except an unregistered `derived` one. There is no closed long-form list. The route resolves in this order:
  1. no `documents` row: `404 book_not_found`, as today;
  2. a registered `book_assets` row: today's detail, plus the markers below;
  3. no registered row and `document_type == "derived"`: `404 book_not_found` (a derived view opens only through its own registration, #3527);
  4. otherwise: the fallback detail below.
- **Markers, on `BookDetail` only.** `document_type` (verbatim), `is_book` (`document_type == "book"`, never derived from registration) and `registered` (whether a `book_assets` row exists). `BookSummary`, `/books` and `/library` are unchanged.
- **The fallback detail** has the same `BookDetail` shape: `page_count: 0`, `pagination_scheme: "none"`, `toc: []`, null `cover_uri`, `provenance`, `license_basis` and `ip_holder_id`, `taken_down: false`, and `servability` and `servable_full_text` from `servability_of(content_class, taken_down=False)`, the same projection as books.
- **No second body path.** Text stays on `/books/{id}/full-text` and `/owner-full-text`. A gated document returns the guard's bounded snippet, and a taken-down one returns no text.
- **Takedown reaches non-books** (D2, a rights precondition in the same PR). A takedown of a document with no `book_assets` row writes a takedown-record row there first, then the same purge as the registered path.
- **Ask.** `POST /books/{id}/ask` answers `403 book_taken_down` for a taken-down document before any retrieval or dispatch (D3). An unregistered non-book keeps `404` on `/ask` (LB-35 spec Q3).
- **Reading position.** A flowing document uses the §1.14 row, and `/reading/continue` reads `progress: null` for it, because its `page_count` is 0.
- **The rev-9 delta** is only ruling 12's shelf admission, which is LB-17's (§1.5 shelf), including the classification step of LB-35 spec Q9. The rest is the rev-7-signed W1 row.
- **Ads.** Lane A mounts no ad rail on `is_book: false` until the operator rules on Q-B2 (LB-35 spec Q1).
- **No writes.** The GET writes nothing. The edge already carries `/books*`.

**Acceptance (red-first; per the LB-35 spec §4).**
- A non-book with a `documents` row opens with its gate and the markers. This is red on main, which answers 404.
- A non-servable non-book returns no full text, as a book would.
- A taken-down non-book returns no text, and `/ask` answers 403 before the provider is called.
- A book's response is unchanged apart from the markers, and `/library` is byte-identical.
- An unregistered `derived` document answers 404.
- The GET writes nothing.
- **Probe.** `GET /books/{id}`.

### 1.19 Voice input and speech output (NEW, rev 9; LB-12 with LB-23; rulings 14 and 17)

**What main does.**
- `POST /voice/transcribe` reads the whole body and calls Whisper inline (`interfaces/research/api/read_voice.py@b41f4ec9b` ("audio = await request.body()")). It answers `{transcript, language, duration_seconds}`, with an unknown duration read as zero (`interfaces/research/api/read_voice.py@b41f4ec9b` ("duration_seconds: float = 0.0")).
- The client then posts `voice.captured` through `/events/typed` (`apps/reading/src/hooks/useVoiceCapture.ts@b41f4ec9b` ("action_type: \"voice.captured\"")), before the operator has confirmed the text.
- `POST /speech/tts` takes bare `{text, voice}` (`interfaces/research/api/speech.py@b41f4ec9b` ("text: str = Field(min_length=1, max_length=8000)")), so the server cannot know where the text came from.
- `POST /books/{id}/voice-note` accepts a client `audio_ref` (`interfaces/research/api/read_voice.py@b41f4ec9b` ("audio_ref: str | None = None")), which ruling 17 forbids.
- LB-12's branch (`6fcda87c5`) already moves both provider calls off the event loop and bounds the body at 25 MiB (`interfaces/research/api/read_voice.py@6fcda87c5` ("MAX_TRANSCRIBE_BYTES = 25 * 1024 * 1024"); `interfaces/research/api/speech.py@6fcda87c5` ("audio = await asyncio.to_thread(provider.synthesize, req.text, voice=req.voice)")).

**Transcribe (rev 9).** `POST /voice/transcribe?thread_id=&project_id=&language=&mothership=` with the raw audio as the body.
- **Off the loop.** The provider call runs in a thread, so `/health` answers while it waits (LB-12, tier 0).
- **The bound.** A declared `Content-Length` over 25 MiB is refused before any byte is read, and the streamed count is the authority: `413 {reason: too_large}` before the provider is called.
- **The query parameters** are optional attribution, never authorization:
  - `thread_id` must be a `thread` the caller owns (§1.2), else `404 {reason: thread_not_found, ref}`;
  - `project_id` must be the caller's registry project, else `404 project_not_found`;
  - `language` is a hint of at most 35 characters passed to the provider;
  - `mothership` is §1.13's attribution field.
- **The provider** is the lineup's `transcription` action (`substrate/dispatch/lineup_catalog.py@b41f4ec9b` ("ActionDef(\"transcription\", \"Transcription\"")).
- **The response.** `{transcript, language, duration_seconds | null, asr: {provider, model}, cost_cents | null}`.
  - `duration_seconds` is null when the provider does not report it, never 0.
  - `cost_cents` is duration × $0.006 per minute, rounded up to a whole cent (§1.13), and null when the duration is unknown.
- **It persists nothing.** It writes no event, and keeps no audio and no transcript. Its only write is LB-23's spend record (`record_dispatch`, `kind: asr`, `spend_class: operator_asr_tts`). It returns no capture id.
- **The failure vocabulary (S20).** `400 {reason: empty_audio}`, `413 {reason: too_large}`, `503 {reason: transcription_unavailable}`. Each keeps its legacy string `detail`. `429 {reason: rate_limited}` belongs to the invitee route (§1.13); the operator route answers it only if a later ruling adds an operator limit.

**`Input` on the consuming routes (rev 9).** Launch (§1.3), ask (§1.8) and reformat (§1.11a) take `input?: Input`:
```
Input = {modality: "text"}
      | {modality: "voice", edited: bool, asr_model?: string, language?: string, duration_s?: number | null}
```
- `{modality: "text"}` carries no other field.
- `voice` requires `edited`, and takes `asr_model?` (up to 128 characters), `language?` (up to 35 characters) and `duration_s?` (finite and ≥ 0, or null when unknown).
- Anything else is the route's `422 … input` refusal.
- Every one of these fields is client-asserted. The server records them and never derives rights or spend from them. ASR spend settles at transcribe.
- The prompt stays `origin: operator`.

**The server mints the capture at submit (rev 9; ruling 17).** The consuming route writes `voice.captured {source_kind: "user", transcript: <the submitted, normalized text>, transcript_status: "ok", language, duration_seconds, edited, asr_model, audio_ref: null}` on the target thread:
- on an ask, in the admission transaction beside `thread.turn_requested` (§1.8);
- on a launch, strictly into the child's log after the ACU charge and before the start event (§1.3), with an idempotent event id derived from the child id, so a retry finds it and a charge refusal precedes it;
- on a reformat, in the admission transaction beside `reformat.requested` (§1.11a).

The capture's event id is deterministic from the `turn_id`, the child id or the generation id. It is returned in that submit's answer as `voice_capture_event_id`, including on a 503. The start or turn payload carries it (§1.16 T2). The client never supplies it. What is submitted counts as the confirmed transcript; when voice sends is lane A's default 8, and the server rule is the same either way.

**The reader voice note (rev 9).** `POST /books/{id}/voice-note` is a consuming route of a confirmed transcript too.
- A non-null `audio_ref` answers `422 {reason: audio_ref_refused}` (ruling 17).
- It writes `voice.captured` with `audio_ref: null` on the log it distills into, in the same way, and returns `voice_capture_event_id`.
- Its client-named `investigation_id` stays a listed hole (§1.15).

**Retention (ruling 17).** No audio is kept anywhere. `audio_ref` is always null on these writes, and the `Input` type has no audio field. Object storage for voice stays dormant.

**Schema change (rev 9).** `VoiceCapturedPayload.duration_seconds` becomes nullable; it defaults to `0.0` today (`substrate/schemas/events.py@b41f4ec9b` ("duration_seconds: float = Field(ge=0.0, default=0.0)")), which records an unknown as zero. It also gains optional `edited` and `asr_model` (§1.16 T2).

**Speech output: the `source` gate (rev 9).** `POST /speech/tts {text? | source?, voice?, mothership?}` takes exactly one of `text` and `source`.
- **`source: {turn_event_id}`** narrates the answer's served text under the live gate (§1.8). A `withheld` answer answers `422 {reason: not_servable}` and never reaches the provider.
- **`source: {document_id, page_index}`** narrates only the text the reader serves for that page, through the serving guard. A withheld document answers `422 not_servable`. A page the server cannot resolve answers `422 {reason: source_invalid}`; which served-page function resolves a page is LB-12's to name.
- **A `cite_only` passage** inside a source is replaced by the fixed spoken marker `withheld_marker/v1`, shared with §1.11a's audio. It is never the passage's words.
- **The bound.** The narrated text, after resolution, is at most 8,000 characters. A longer source answers `422 {reason: too_long}`, and lane A narrates per page or per turn.
- **The bare `{text}` form** stays for operator-typed text only. It cannot be gated, because the server cannot know where the text came from, so it is recorded here as ungated and listed with the pre-G7 holes (§1.15). Lane A moves every rights-bearing read-aloud to `source` (A17 retires `useSpeech` on the ReadAloud paths).
- **Spend.** Each call is recorded through `record_dispatch` with `kind: tts` and `spend_class: operator_asr_tts`. The audio is streamed back and not kept.
- **Failures.** `503 {reason: tts_unavailable}` keeps its legacy string `detail`.

**Acceptance (red-first).**
- `/health` answers within 200 ms while a stubbed transcription sleeps 2 s. This is red on main.
- A 25 MiB + 1 byte body gets 413 before the provider is called.
- An unknown `thread_id` gets 404.
- `cost_cents` and `duration_seconds` are `null`, never `0`, when the duration is missing.
- A transcription writes no event to any log, and no audio file exists under the storage root after it.
- A voice launch records `input.modality: voice`. Its `voice.captured` holds the submitted (edited) text, not the raw ASR, with `audio_ref: null`, and the response returns its id.
- `/books/{id}/voice-note` with an `audio_ref` answers 422.
- A `/speech/tts` call whose `source` is withheld never reaches the provider, asserted at the provider seam.
- After A17, `/events/typed` refuses `voice.captured`.
- **Probes.** `GET /health` and `GET /openapi.json` listing the `input` and `source` fields.

### 1.20 Speak read model (NEW, rev 9; LB-16, with LB-15 and LB-34)

**Rules for every route in this section.**
- **Owner scope.** Owner-scoped reads filter on `interview_projects.owner_user_id` (`substrate/graph/schema.py@b41f4ec9b` ("CREATE TABLE IF NOT EXISTS interview_projects (")). `speak_projects` has no owner column.
- **No GET takes the writer.** Every GET reads through `_read`, which uses `connect_read` with a bounded external wait. A lock timeout answers `503 speak_writer_busy` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("raise HTTPException(status_code=503, detail=\"speak_writer_busy\") from exc")), with `reason` added (§1.0a).
  - Today `GET /speak/projects` and `GET /speak/projects/{id}` take the writer (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("with _translate(), _write(\"speak/api:list_projects\") as con:"), ("with _translate(), _write(\"speak/api:get_project\") as con:")). LB-15 and LB-16 move both to `_read`.
  - `list_private_repings_at` opens the writer itself (`substrate/speak/pushes.py@b41f4ec9b` ("db_path, purpose=\"speak/pushes.list_private\", timeout_s=timeout_s")), so the detail route never calls it. LB-16 adds a read-only variant.
  - A module test asserts that no GET handler reaches `connect_write`, including through a two-hop helper.
- **Counts are never a false 0.** A missing Speak schema, meaning no project was ever created, reads as zero rows. Any other unreadable count is `null` with a reason.

**Counts (rev 9, provisional; ruling 6).** LB-16 ships in tier 0, before the co-sign, so these definitions ship as **provisional**: the field names are fixed, and the co-sign may change a definition without renaming its field. They replace `count(*)` over every interview (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("\"(SELECT count(*) FROM interviews i WHERE i.project_id = p.project_id), \"")).
- **`contributed_voice_count`** counts interviews that meet all three conditions:
  - status is not `declined`;
  - at least one `transcript_turns` entry has `role: "informant"` (`substrate/speak/async_interview.py@b41f4ec9b` ("if t.get(\"role\") == \"informant\" and t.get(\"question_id\")"));
  - no active `speak_takedowns` row with `target_kind = 'interview'` targets it.

  A project whose turns JSON cannot be parsed reads `null` with `turns_unreadable`.
- **`invited_count`** counts interviews that are not `declined`, whether answered or not.
- **`pending_reping_count`** applies the reping rule read-only: status not `declined` or `completed`, an invite token present, and either pending questions or a status of `invited`, `in_progress` or `incomplete`.
  - It is `null` with a reason when pending questions cannot be computed for any row.
  - The shipped helper instead records a failed computation as `pending = 0` (`substrate/speak/pushes.py@b41f4ec9b` ("pending = 0")).
- **Every public voice count uses `contributed_voice_count`'s definition.** That covers `/speak/opportunities`, `/speak/pushes`, the feed's `interview_count` and `/speak/public/{id}`.
  - LB-34 lands first with its takedown predicate.
  - LB-16 then narrows the count, which today counts every non-declined interview (`substrate/speak/pushes.py@b41f4ec9b` ("AND i.status NOT IN ('declined')) AS voice_count,")).

**`topic_description` on the existing reads (rev 9, ruling 6).**
- `CreateProjectRequest` already takes `topic_description` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("topic_description: str | None = None")). `ProjectResponse` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("class ProjectResponse(BaseModel):")) and the list, feed and opportunities rows now return it.
- `interview_guide` is accepted on create (LB-15) and returned only on the owner's detail, never on a public route.

**`GET /speak/projects` rows (rev 9).**
- The rows gain `topic_description`, `contributed_voice_count`, `invited_count` and `pending_reping_count`.
- `interview_count` stays as the raw count of interviews and is never labelled "voices".
- LB-15's owner filter applies.

**`GET /speak/sections` (rev 9).** It answers:
```
{my_projects: {count, attention: int | null, attention_reason?: "inbox_absent"},
 invites: {count: null, state: "gated_G7"},
 public: {count, contribution: "live" | "gated_G7"}}
```
- **`attention`** counts the owner's projects with an unconfirmed answer or an unseen Speak inbox item. It stays `null` with `inbox_absent` until the W3 inbox lands, and it is never a partial count.
- **`invites`** is the designed locked state until G7 (ruling 5). The optional bookmark route is not in rev 9.
- **`public.count`** is the number of rows the LB-34 public listing returns. `contribution` is `live` exactly when `public_ecosystem_enabled()` holds (`substrate/speak/invitations.py@b41f4ec9b` ("def public_ecosystem_enabled() -> bool:")).

**`GET /speak/projects/{id}/detail` (rev 9).**
- **Owner scope.** Another owner's project, or a missing one, answers `404 {reason: not_found}`.
- **Response:**
  ```
  {project: {project_id, title, topic_description, interview_guide, subject_ref, subject_status,
             publish_intent, invitation_mode, deliverable_id | null, created_at},
   economics_gate: <the body of GET /speak/projects/{id}/economics>,
   invites: [{invite_id, interview_id, invite_path, required_consent_scopes[], created_at}],
   interviews: [{interview_id, who, status,
                 consent: {record, attribute, publish},   // each "granted" | "revoked" | "absent"
                 pending_questions: int | null, last_answer_at | null,
                 unconfirmed_answers: int | null, under_takedown: bool}],
   arrivals_unseen: int | null, arrivals_reason?: "inbox_absent",
   claims_summary: {total, by_verification: {unverified, multiply_attested, operator_attested, contradicted},
                    under_takedown},
   repings: [{interview_id, who, status, pending_question_count: int | null, invite_path}]}
  ```
- **`invite_path` carries the invite token, which is a credential.** It appears only on this owner route and is never logged.
- **`unconfirmed_answers`** is `null` with `not_tracked` until LB-13 item 2 stores `transcript_status`. Before that, invitee answers are never marked unconfirmed, so a 0 would be false.
- **`economics_gate`** reuses the read-only gate state of `GET /speak/projects/{id}/economics` (`interfaces/research/api/speak_routes.py@b41f4ec9b` ("@speak_router.get(\"/projects/{project_id}/economics\")")).

**`GET /speak/public/{project_id}` (rev 9; open).**
- **Opening the path.** It is opened in the auth middleware by a GET-only pattern match, never a prefix: the path starts with `/speak/public/` and has exactly three `/`. The match sits beside the open-contribute match (`interfaces/research/api/app.py@b41f4ec9b` ("and _p.endswith(\"/open-contribute\")")).
  - It is also listed beside `_OPERATOR_AUTH_OPEN_PATHS` (`interfaces/research/api/app.py@b41f4ec9b` ("_OPERATOR_AUTH_OPEN_PATHS: set[str] = {")) in the same comment.
  - The edge already carries `/speak/*`.
- **Response:** `{project_id, title, topic_description, subject_ref, voice_count, invitation_mode, contribution: "live" | "gated_G7", created_at}`.
- **Filtering.** The route uses LB-34's shared predicate:
  - a project is listed only when `publish_intent = 'will_be_public'` and it has no active subject takedown (`substrate/speak/pushes.py@7d784d826` ("AND t.target_kind = 'subject'"));
  - a claim takedown leaves the project listed, because claims are never part of this read;
  - an interview takedown removes that interview from `voice_count` (`substrate/speak/pushes.py@7d784d826` ("AND t.target_kind = 'interview' AND t.target_id = i.interview_id")).
- **Every miss answers the same `404 {reason: not_found}`,** whether the project is missing, private or under a subject takedown, so existence is not disclosed.
- **It never returns** `interview_guide`, invites, interviews, claims or tokens.

**Acceptance (red-first).**
- No GET in the module takes `connect_write`, and a held writer yields a bounded 503.
- A count is `null`, never 0, when it is unreadable.
- An invited interview with no answer counts in `invited_count` and not as a voice. This is red today.
- A project under a subject takedown is absent from the public detail, which answers 404.
- Another owner's project is absent from the sections and answers 404 on detail.
- `topic_description` given on create is returned by `ProjectResponse`, the list and the detail. This is red today.
- **Probes.** `GET /speak/public/{project_id}` (open: probed for its body), `GET /speak/sections` and `GET /speak/projects/{id}/detail`.

---

## Appendix A. Lane A's eight §C requests, answered

Lane A's Part 2 draft §C lists eight requests of Part 1. Each is answered here.

| # | Lane A asks | Answer | Where |
|---|---|---|---|
| C1 | Serve `last_mode` and `shelf_count` on `GET /projects?product=`; homes read presence, never `home_product` | **Yes.** The row serves `last_mode`, `shelf_count`, `linked_project_ids[]` and NEW `default_mode` (never null, the landing rule's last fallback), with `thread_counts` and `spend_today` nullable and `null_reasons` naming each null (including `cost_unknown`). `?product=` is the only presence filter; `?home_product=` answers `422 filter_invalid`. | §1.5 "Reads" |
| C2 | Carry `spawning_enabled` and `spawning_reason` on the Autonomous roster read | **Yes.** `GET /autonomy/roster` carries both; the reason is the first failing of `consent_route_absent`, `env_refused`, `cap_exhausted`, `enabled`, and `spawning_enabled` is true exactly when it is `enabled`. | §1.13 "The roster read" |
| C3 | Name the retired-route body's alternatives with the T6 flows | **Yes.** `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}` on source-merge preview, apply and commit; `restore` follows Q-B1. | §1.11 "Source merge" |
| C4 | Make the D-M draft, estimate and revise routes answer with the §A5 shapes, and make `422 target_unavailable` distinct from 403 | **Yes, extended.** The §A5 fields are all present. Additions lane A accepts at the co-sign (Appendix B): the draft POST answers `202 {merge_id, draft_id, state}` first and the full shape on replay or read; `project_id` and `mothership` are required; `merge_id`, `parent_draft_id`, `state`, `sentences[]`, `edit_text`, `measures`, `preview_digest` and `question` join the shape. `422 {reason: target_unavailable, detail: agents_unavailable \| not_an_agent \| target_is_member}` is never a 403. | §1.10 |
| C5 | Make the context receipt on every session turn and group answer part of `thread.turn` or a sibling event the ask response returns | **Yes, a sibling event.** One `thread.context_receipt` payload on every answered turn, written in the same outbox transaction as `thread.turn`, returned by the ask and by `GET /investigations/{id}/turns`, with group items tagged by `participant_thread_id`. Item key `item_id`; reasons `budget \| withheld \| refs_only \| depth_limit`. | §1.8 "The context receipt"; §1.12a "Context receipts" |
| C6 | Put the shared NFC offset fixture for output anchors at a path both lanes import | **Yes.** `apps/reading/src/lib/api/__fixtures__/output_anchor_nfc_v1.json`, one copy, read by pytest by path and imported by lane A byte for byte, with the required cases and refusals. | §1.4b "The shared fixture" |
| C7 | Keep every data name at `reading`, including `lens=reading`; never introduce a `books` value | **Yes.** No mode key, `home_product`, `products[]`, `kind`, `lens`, `?product=` or event name is `books`; each `books` input is refused (`/tabs/books` 404, `?product=books` 422, `lens=books` 422, `home_product: books` 422). | §1.0; §1.5; §1.6; §1.11a; §1.12 |
| C8 | Emit the typed `seam.speak_to_write` and `seam.research_to_read` on those transfers | **Yes.** `seam.research_to_read` per selected insight node on a T5 partial, and `seam.speak_to_write` per composed claim on a Speak send, each in the transfer's transaction with `provenance_ref: <transfer_id>`. Both are server-owned. | §1.5a "Seam events" |

## Appendix B. Part 2 edits these rules need (lane A confirms at the co-sign)

Lane A's draft says Part 1 names win. These are the places where a rev-9 Part 1 rule changes what lane A's draft sends or renders.

- **Error narrowing (all sections).** Every rev-9 refusal is top-level `{reason, detail?, …}`. `detail` is the closed sub-code where a reason defines one, and a legacy string `detail` equals `reason` on old codes. §B1's `seed_invalid` renders `detail` next to the field (for example `product_invalid`, `not_reader_openable`, `document_unclassified`), not `reason`.
- **§A1 projects.**
  - The landing rule's last fallback can use `default_mode`, because after a leave `home_product` can name an absent mode.
  - Tab writes in a `not_in_mode` mode answer `409 product_absent`.
  - The row also reacts to `project.updated`.
  - A book project's "Open in Writing", and every "Open in <mode>" on an interest project, reads `offers.whole = {available: false, reason: transfer_not_supported}`. Lane A supplies the disabled-state copy (§1.5a).
- **§A2 tabs.**
  - `branch_origin.output_anchor` carries no `quote`, `prefix` or `suffix` (`422 tab_origin_invalid`).
  - `transient: true` is accepted only on a new left node in the reading mode with `branch_origin.kind: agent` and `opened_by`; it may only go from true to false.
  - Keep is the members POST first, then the tab PUT that clears `transient`.
- **§A3 islands.** The output anchor also needs `thread_id`, `selection_sha256` and `normalization`; `segment_id` stays, derived and checked. Flag is disabled on thesis and component segments (they have no `node_id`), and Flag sends `{insight_id}` or `{question_id}`, never an anchor.
- **§A4 lanes.** `origin.quote_state` may be null, and a `no_record` row has every derived field null.
- **§2.4 "Ask this thread", tier 0.** It branches a dialogue child (`kind: dialogue`, `origin {kind: research | selection, purpose: ask}`) and asks there. Rev 7's "turn persisted on the addressed thread" is superseded.
- **§A5 merge.**
  - The draft request adds `project_id` and `mothership` (required), `merge_id?` and `confirm_unpriced?`. An unpriced draft needs `confirm_unpriced: true`, else `422 {reason: confirmation_required, detail: unpriced}`.
  - `POST /threads/merge/draft` answers `202 {merge_id, draft_id, state: "drafting"}`; the draft arrives through `GET /threads/merge/{merge_id}/draft` and the socket; a replay after it finishes answers 200 with the full shape.
  - `synthesis.text` is marker-free; `sentences[]` carry offsets and `item_ids`; `edit_text` carries the markers for the editor, and `revise` takes that encoding.
  - NEW `POST /threads/merge/draft/{draft_id}/cancel`.
  - New refusal details: `draft_required` (`absent | digest_mismatch | members_differ | question_differs`), `target_unavailable` (`agents_unavailable | not_an_agent | target_is_member`), `draft_stale` (`member_changed | source_changed | rights_changed | member_incomplete`), `merge_committed`, `draft_not_ready`.
  - `merge_failed` is retired; §2.4's and §2.5's rows that read it read `merge_pending` or the 503 instead.
  - The compose routes answer `410 {reason: "retired", alternatives: ["thread_merge"]}`.
- **§A6 and §B8 Books.**
  - `gate` and `reason` are flat everywhere (shelf items, continue items, flag documents, book-ask refs), from one projection: the owner's own `personal_reading` document reads `served`, and a taken-down one reads `withheld · not_servable`.
  - `is_book` is `document_type == "book"`. The shelf orders books before non-books, each by `ordinal`.
  - A Keep on a document that is already a member answers `200 already_member` with its role.
  - No rev-9 route acts as an agent, so lane A never meets `403 agent_cannot_curate`. Agent proposals are answer refs that the operator Keeps or files.
  - A shelf document must be classified (`shelf_invalid · document_unclassified`).
  - §2.9's unresolved to-read row reads `document_reason`, not `reason`, and the to-read projection ships once rev 9 is signed.
- **§B1 create.** `409 idempotency_conflict` carries `project_id`. A missing thread source answers `404 thread_not_found`, and any other missing source `404 source_not_found`; both take §B1's "That source no longer exists" copy.
- **§B2 sessions.**
  - Dialogue create takes no `question`. A plain or branched dialogue needs a client-minted `investigation_id`; a session create must not send one.
  - `answering` is a pending state: there is no token stream in rev 9. Retry reuses the key and re-dispatches only for `unavailable` or `interrupted`; `owner_model_outcome_unknown` needs a new press. `409 turn_in_progress` means wait for the WS `thread.turn`. A reload reads `GET /investigations/{id}/turns`.
  - The receipt item key is `item_id`, and `reason` adds `depth_limit`. Receipts exist on answered turns only.
  - An unpriced group turn sends `confirm_unpriced: true`. Per-turn attachments are refused on a group.
  - The charter PATCH's `idempotency_key` is optional, matching §B2's body.
- **§B3 Converse.**
  - Past sessions are `GET /investigations?kind=dialogue&dialogue_kind=plain&project_id=`.
  - A monologue's scope is `{project_id}` only (O-18).
  - With `delivery: audio` the server renders each chapter's audio itself. The segment list is `GET …/revisions/{rev}/audio`; each segment's `url` is the stream `GET …/audio/{n}`. A refused segment reads `failed · cap_reached`, and `reformat.audio_render_failed` nudges the player.
  - `POST /reformats` takes `input`, and returns `voice_capture_event_id` for voice.
- **§B4 Speak.** "Adds to <project>" sends `to_project_id`. A request linked to several Writing projects answers `409 target_ambiguous`. The three list counts ship provisional.
- **§B5 Autonomous.** Research → Autonomous is the members route with `member_role: managed` and no `reach`, never `/transfers`. The roster may ship with `agents: []` before LB-26.
- **§B7 transfers.** The pairs are T1–T6: "Open in <mode>" is T1 from any `kind: project` row, and a partial transfer to a new target sends `new_project`. `offers` keeps `422 transfer_not_supported` unreachable.
- **§B9 voice.** Already matches: the capture id arrives in the submit's answer, including on a 503. The transcribe response's `duration_seconds` may be null.
- **§A3b.** It cites Part 1 §1.4c (`html-text/v1`). §1.4c is now in this draft, pasted from the co-signed pin, so §A3b's endpoint rules (item 11) are Part 1 text.

## Appendix C. Open items, each with its fallback

**C.1 For the operator.**

| # | Question | Fallback until ruled |
|---|---|---|
| O-3 | May owner-model (BYOT) launches have a parent? | They keep refusing a parent (`422 owner_model_root_required`); output branches run on the platform lineup with the estimate. |
| O-11 | A standing, expiring autonomy envelope per agent, as an exception to D4? | Per-flag consent under D4 for every continuation; the envelope routes and `agent.autonomy_*` events do not exist. |
| O-12 | May Speak testimony leave through Write? | The owner reads it, gated at serve time; share and export answer `422 speak_publish_required` until Speak's publish flow has cleared every claim. |
| O-15 | The book agent's reach, and the Books–Research boundary | Book sessions read the book, plus the narrowed ruling-11 link layer; `shelf` and `library` scope only on `/books/{id}/ask`; open-web research only as explicit branches. |
| O-16 | The spend class of conversational turns and operator ASR/TTS | Record-only settlement (`record_dispatch`): counted and never refused. |
| O-16b | Does an owner-BYOT dispatch count against the platform daily cap? | Counted, recorded with `authority: owner_byot`. |
| O-19 | Speak intake confirmation and authorship | Invitee voice answers stay `unconfirmed` until the operator confirms them (LB-13 item 2); contributor authorship waits on the rights review. |
| Q-B1 | Does prod hold a committed source merge with no later restore? | `restore` stays live, API-only; LB-33b is built only if yes. |
| Q-B2 | May ads run on non-book documents in the reader? | Off: lane A mounts no ad rail on `is_book: false`. |
| Q-B3 | LB-35 spec Q2 (whole-book uploads marked non-book by `document_type`), Q3 (`/ask` stays 404 on unregistered non-books), Q5 (null `ip_holder_id` in the fallback), Q6 (takedown record deleted on reinstate) | Each spec default. |
| Prefs | May `reading_state.prefs` hold a listening offset inside a segment? | The allowlist stays empty; playback resumes at the segment's start. |
| Intake | The default per-owner daily Speak intake budget | A conservative default named in LB-13's PR and recorded in DECISIONS before it merges. |
| Q9 | Classifying null-class documents before they go on a shelf (LB-35 spec Q9) | The shelf, a `book` seed and T4/T5 refuse them (`document_unclassified`). |
| Defaults | Lane A's defaults 1–8, notably default 2 ("the context of the book") and default 8 (when voice sends) | As recorded in DECISIONS. |

**C.2 For the co-sign (lane A and the auditor).**

| # | Item | Default in this draft |
|---|---|---|
| 1 | `depth_limit` extends D-A's closed receipt reasons | Adopted; listed, never dropped silently. |
| 2 | The legacy-migration refinement: an LB-2-era `kind: project` row gains presence in each mode that already has a tab tree, and an LB-2-era `kind: reading` row migrates as `reading/[reading]` | As specified in §1.5. |
| 3 | Additions beyond the grounding: `project.updated`; `default_mode`; `new_project`; `offers`; `project.transferred` for Speak sends; the `project_create_requests` and `project_transfers` tables; `thread.dialogue_started`, `thread.turn_requested`, `thread.turn_failed`; `GET …/turns`; `POST …/ask/estimate`; the merge cancel route; `edit_text`; `dialogue_kind`; `reformat.audio_render_failed`; `server_owned_log` | Adopted as drafted. |
| 4 | Bounds and defaults: question 3..2,000; `seed_prompt` ≤ 2,000; `idempotency_key` 1..128; selection caps 50/1,000/1,000; shelf cap 1,000; `document_ids[]` filter ≤ 1,000; `blank_deliverable` → `general_essay`; writing `from_investigation` → `research_memo`; monologue shortfall at 90%; audio segments ≤ 3,500 characters; revise ≤ 64 KiB; charter brief ≤ 8,000; attach ≤ 50 items | As drafted. |
| 5 | The output-anchor rows for `note.emerged` and `confidence_basis` | Kept; the auditor may strike either. |
| 6 | `presentation_mode` defaults to `cited_quietly` when a dispatch declares none | Kept, pending the auditor's check against T7. |
| 7 | A sourceless insight node is `operator` only when its event's role is `operator`, else `unsourced` | As drafted; it overrides the chokepoint's "the operator's own words" label for model text. |
| 8 | `GET /investigations/{id}` answers 404 for anything that is not a `thread` (today it answers `200 {status: not_found}`) | Adopted; LB-24a audits the other callers. |
| 9 | `recover_pending_events` at API startup drains every producer's pending outbox rows | LB-17 wires it; its owners of the note-taker and memory outbox paths are told in the PR. |
| 10 | Tab writes refuse modes absent from `products[]` (changes LB-2) | Adopted. |
| 11 | The monologue re-plan route and identity | Unspecified: LB-30 names both, and both lanes add them before LB-30 builds. |
| 12 | A target form for an agent-proposed work with no `documents` row | None: the answer returns an unresolved ref and nothing is filed. |
| 13 | A `reading` project's member threads that ground in no shelf document are hidden in Books and the project has no Research presence | Lane A shows them from `?project_id=` without `document_ids[]`, in a group of their own, or the operator uses T6. |
| 14 | RESOLVED: Part 2 §A3b cited a Part 1 §1.4c that was not yet drafted | §1.4c is pasted byte-exact from the co-signed pin (file SHA-256 `a99c4950…`, fixture `41e4825d3`). |
| 15 | Which record counts as Speak's publish flow having "cleared" a claim | LB-18 names it in its PR. |
| 16 | `via: agent_call` stays reserved with no writer | Kept reserved, because adding it after B0 merges costs a second bump. |
| 17 | The receipt reason `via: link` for book sessions | Adopted. |

**C.3 Dependencies and INFERRED facts to confirm.**

| Item | Fallback |
|---|---|
| LB-2 (#3530) is not on main; every registry and tab rule assumes it merges before LB-17. | Tier 1 waits for it. |
| The `BranchOrigin` fields must ride c2-export before it merges. | Missing that window costs a second schema bump (§1.16). |
| Owner BYOT on non-book dialogues needs PR #3278. | Those asks answer `409 owner_model_unavailable`. |
| INFERRED: per-sentence attribution needs inline markers in the thought-partner prompt and parser. | New prompt and parser work in LB-21. |
| INFERRED: the turn lease and the conversational `max_tokens`; the `merge_draft` role, its input bound and its per-call maximum. | The packages set them and record them in the PR. |
| INFERRED: `409 parent_log_remote` for unfunneled remote-exec parents. | LB-20 confirms the funnel before shipping the refusal. |
| INFERRED: the edge request timeout behind the 202 on merge drafts. | 202 stands either way. |
| INFERRED: the distill read is the per-thread source of insight ids; the scope retrieval's embedding is local; flaggable question ids are node ids; the audio cache location. | Each package verifies before building. |
| UNVERIFIED: the TTS provider's per-request character limit. | 3,500-character segments, with sentence-aligned parts for a longer span. |
| Contract anchors are pinned at home commit `e39840224`. | Re-pin at fold-in if `THREAD-CONTRACT.md` has changed. |

## Appendix D. Corrections to grounding v2 (to fold into v3)

1. Diligence consent and launch are not shipped; decline is the shipped `dismiss`, and consent and launch are rev-3 routes built in W2 (§1.13).
2. `diligence_queue.kind` holds only `concept`, `open_question` and `insight`, so a diligence flag cannot target an anchor, claim or document (§1.13).
3. The signed rev-5 to-read item has two fields named `reason`; the marker is `document_reason` (§1.13).
4. `GET /books/{id}` returns metadata only; LB-35 adds no body route (§1.18a).
5. `book_assets.page_count` defaults to 0, so a 0 count reads `progress: null` (§1.14).
6. Invitee-triggered Speak follow-ups are third-party spend (§1.13).
7. `list_private_repings_at` takes the writer for a read and turns a failed computation into `pending = 0` (§1.20).
8. The TTS dispatch id `<gen>:tts:<n>` would collide across a voice or gate change; it is content-keyed (§1.11a).
9. The notebook's `content_hash` is recorded, not put in the request identity (§1.11a).
10. LB-33b's receipt needs `commit_id`, `parent_reading_thread_id` and `restorable` (§1.11).
11. `resolve_owned_corpus` cannot serve the library scope (§1.8).
12. `BudgetLedger.debit` cannot record spend; `record_dispatch` is new (§1.13).
13. Both systemd units load one environment file (VERIFIED at template level) (§1.13).
14. Main's daemon spawns without consent when the flag is on (§1.13).
15. `/tabs/books` answers `404 mothership_unknown`, not the 422 in LB-17's acceptance list (§1.6).
16. LB-17's acceptance item "born in Writing, transferred whole to Research" is unreachable under LB-18's four-pair table; whole transfers generalise to T1 (§1.5a).
17. Research → Autonomous is the members route's `managed` role, not a transfer (§1.5a).
18. The `write_folder_members` rebuild is new in rev 9; §1.16's W3 rebuild is `derived_asset_revision_members` and stays (§1.5, §1.16).
19. `recover_pending_events` has no production caller (§1.5).
20. `place_block` refuses an eventful placement it does not own, and `promote_investigation_to_deliverable` is not atomic (§1.5).
21. LB-2 and c2-export both set `EVENT_SCHEMA_VERSION` 41 (§1.16).
22. `note.emerged` is a durable insight signal and needs an output-anchor row (§1.4b).
23. The LB-35 spec has no closed long-form list; `is_book` is `document_type == "book"`, the fallback `page_count` is 0, and unregistered non-books stay 404 on `/ask` (§1.5, §1.18a).
24. The companion stack's head is `f87a4db64` (it merged main); the `evidence_index` anchors were re-read there (§1.12, §1.12a).
25. DuckDB 1.5.4 refuses both ways of adding a CHECK by ALTER (RUN) (§1.5).

## Appendix E. Integrator notes: how each critic fix was applied

Every fix in the critic's list was applied. Where the applied form differs from the fix as written, the note says how and why. No fix was rejected outright; three were applied with a variation (M9, M10, M16), and they are marked.

**Blockers.**
- **B1 (§1.19 missing).** Applied: NEW §1.19, with transcribe (off the loop, 413 over 25 MiB, owner-checked `thread_id` and `project_id`, persists nothing, no capture id, the response with `cost_cents | null`, `record_dispatch` `kind: asr`, the lineup's `transcription` action, S20's vocabulary), `Input`, the server-minted capture (moved here from §1.8), the TTS `source` gate with the spoken marker, the bare `{text}` form recorded as ungated, and the refusal of `audio_ref` on `/books/{id}/voice-note`.
- **B2 (§1.6 missing).** Applied: NEW §1.6 rev 9 with `transient` (who may set it, one direction, Keep as members-then-PUT, inclusion in the restore identity), the `409 product_absent` gate with its check order, and the output-anchor keys moved from §1.4.
- **B3 (§1.2 deltas).** Applied: `project_ids[]`, `?project_id=` with membership as the authority, `?document_ids[]=`, legacy adoption for `reading` and `interest` projects, and `project_id` and `title` on the launch body with the membership row and `project.members_changed {cause: launch}` in one transaction (§1.2, §1.3). The membership is written before the start, so a failed start leaves a `no_record` member rather than an unlisted running thread.
- **B4 (members route).** Applied the critic's one rule in §1.5 and §1.12a: `reach` is server-set and a body carrying it answers `422 member_body_invalid`; no `idempotency_key` (natural key); `agent` and `managed` rows run §1.12a's checks in that order; answers are `{status, member}`. §1.5a's Research → Autonomous body no longer sends `reach`.
- **B5 (receipts).** Applied the critic's payload, plus `via: link` for book sessions (M9c's tag) and a closed `kind` set. Receipts are written on answered turns only, registered in the tier-2 bump; "LB-21's bump" is read as the tier-2 bump, since the first tier-2 package to merge registers every tier-2 payload (§1.16). `depth_limit` is listed for acceptance (Appendix C.2).
- **B6 (LB-35).** Applied: §1.18a states only D1–D3 plus "per the LB-35 spec"; the closed list, `not_long_form` and the null `page_count` are gone; `is_book` and `registered` are markers; book ask stays gated on `book_assets`. In the registry, `is_book = document_type == "book"`, `document_not_long_form` is dropped, and LB-17 owns shelf admission, including Q9's classification step (`document_unclassified`).
- **B7 (server-owned events).** Applied: one list in §1.16 covering every event rev 9 says the server writes, plus the `project-`/`merge-` log refusal. The list also includes `investigation.start_requested`, because a forged start could otherwise run Loop One without an ACU charge, and it would pass the merge handler guard's `merge_id` test.

**Majors.**
- **M1.** Applied: one book-ask subsection, in §1.8, with the presence check (`reading ∈ products[]`, `409 product_absent`) and spend's codes; the threads copy is deleted.
- **M2.** Applied: one "Other modalities" replacement, in §1.11a.
- **M3.** Applied: one rule in §1.0a. Sub-codes are named `detail` everywhere; the registry's `cause` became `detail`, and the threads cluster's `{"detail": {reason}}` wrapper is dropped.
- **M4.** Applied: `422 {reason: confirmation_required, detail: unpriced}` in §1.8 and §1.10.
- **M5.** Applied for sessions (§1.12a cites §1.8's `participants_invalid · not_a_member`). The context route and attach keep `422 not_a_member`, because they have no participants; the note in §1.12a says so.
- **M6.** Applied: one gate projection in §1.5, flat `gate` and `reason`, used by the shelf, candidates, continue reading, book-ask refs and flag documents.
- **M7.** Applied: §1.13 "Halt scope" adds `scope: dispatch` for merge drafts and audio segments, delivered as `thread.merge_draft_failed` or a failed segment with `reformat.audio_render_failed`, never `investigation.cap_halted`; merge_agents' per-draft rule is folded in.
- **M8.** Applied: one `attribution` object on `reserve_dispatch`, `settle_dispatch` and `record_dispatch`; the `kind` set covers held and recorded kinds; a per-route `mothership` table, with optional `mothership` on ask, reformats, audio, transcribe and TTS.
- **M9 (variation).** (a) An agent reaches a ruling-11 linked project only through an attach (§1.12a step 7). (b) `restrict_node_ids` is the node ids that steps 1–7 reached. (c) A book session's link layer is narrowed to linked-project threads that grounded in or opened a shelf document, tagged `via: link`. The variation: ruling 11's "Books agents read the project" is served by (c), because a book session is the Books-side dialogue; §1.12a agents are served by (a). The registry's sentence now says exactly that.
- **M10 (variation).** Applied as "agents act only by answering in the MVP" (§1.12a): answer refs become client-opened transient tabs and operator-filed proposals; no route derives `actor: agent`. The variation: `via: agent_call` is kept as a reserved literal with no writer instead of being struck, because it rides B0's payload now and adding it after B0 merges costs a second bump. Agent-filed flags and agent-opened server tabs are struck.
- **M11.** Applied: one predicate, `thread_status`, in §1.2, used by `GET /investigations/{id}` (404), the parent check, merge members and targets, promotion, participants, attach, seeds, transfers and agent memberships.
- **M12.** Applied: flags from output send `node_id` as `{insight_id}` or `{question_id}`; there is no output-anchor flag target (§1.3, §1.4, §1.13).
- **M13.** Applied: the whole to-read projection (`GET /flags?intent=read`) waits for the co-sign and ships with `document_reason`; it never ships under the colliding rev-5 name.
- **M14.** Applied: `null_reasons.spend_today` gains `cost_unknown`.
- **M15.** Applied: LB-17 owns the startup wiring; LB-24a calls it after a `503 merge_pending`.
- **M16 (variation).** Applied: one table in §1.16 with the renumber-at-merge rule for #3530 and c2-export, a bump per carrier and tier, every event named, and the tier-1 `write_folder_members` rebuild. The variation: the fix said "the member-table rebuild moved to LB-17", following the registry draft. That draft misread §1.16: the signed W3 rebuild is `derived_asset_revision_members` (§1.11 rev 6), which stays in W3. The `write_folder_members` rebuild is a new, second rebuild owned by LB-17.
- **M17.** Applied: §1.11 rev 9 with the `speak_claim` serve-time gate (takedown and `record` at read; `attribute` and `publish` through Speak's publish flow), `422 speak_publish_required` on share and export, and the from-investigation repairs (owner check, multiple and partial selections, idempotency key, atomicity).
- **M18.** Applied: `POST /reformats` takes `input`; a voice input writes `voice.captured` in the admission transaction and returns its id.
- **M19.** Applied: the server renders a `delivery: audio` monologue's chapters as they commit; `POST …/audio` is for re-renders, retries and text revisions; the segment list and the stream are named apart.
- **M20.** Applied: one §1.15 list of owner-scoped routes and holes, including the four the critic named.
- **M21.** Applied: §1.12 adds `antiek://threads/{id}` and `antiek://merges/{merge_id}`, the twin-note promotion rule, and a definition of entry `merge_ids[]`.
- **M22.** Applied: §1.9 rev 9 adds `project` with its resolution and gates, and no `speak_project`.
- **M23.** Applied: one §1.18 order for LB-12 to LB-35.
- **M24.** Applied: book and interest rows read `offers.whole = {available: false, reason: transfer_not_supported}` except T6, and lane A supplies the disabled copy. T1 on book rows was not chosen, because §1.5's invariant 2 keeps them reading-only.
- **M25.** Applied: merged-thread output is not selectable in the MVP (§1.4b, §1.10), with the future draft-segment rule sketched.

**Minors.**
- **m1.** One vocabulary, `{kind: user | agent, id}`, and one rule: a body that carries `actor` is refused, on the registry and on `/flags`.
- **m2.** One per-route rule in §1.15, applied in every section.
- **m3.** One representation: served text is marker-free and citations travel in span or sentence records; the marked form is the merge draft's edit encoding only (§1.0a, §1.10).
- **m4.** `project.members_changed.cause` gains `dialogue`, `merge_commit` and `agent_call` (reserved); dialogue create and merge commit enqueue it.
- **m5.** The Books lens and the Notebook use one document set, primary, shelf and context documents (§1.2, §1.12).
- **m6.** A monologue's scope is `{project_id}` only, per O-18's answer.
- **m7.** The charter PATCH's `idempotency_key` is optional.
- **m8.** LB-16's counts ship provisional, with fixed field names.
- **m9.** `InvestigationStartRequestedPayload` carries `voice_capture_event_id` (§1.3, §1.16).
- **m10.** "Through the outbox" means `eventful_transaction` plus `enqueue_event` (§1.0a).
- **m11.** §1.7's broadcast list, consolidated, includes `question.identified`, `question.flag_declined` and `reformat.audio_rendered`.
- **m12.** `ThreadSummary.dialogue_kind` and `?dialogue_kind=`; Converse lists `plain` only.

**Citations.**
- **c1.** Every contract citation is pinned at home commit `e39840224`, the committed revision identical to the working file on 2026-09-27.
- **c2.** Every code citation uses a full repo-relative path.
- **c3.** The three multi-occurrence anchors were replaced or dropped; every anchor now occurs exactly once.
- **c4.** No quoted anchor carries a bare line number.

**Checked by script.** Every `path@<commit>` ("anchor") citation in this file was checked against `git show <commit>:<path>` (and the home copy of `THREAD-CONTRACT.md`): each anchor occurs exactly once, and no bare `path:line` citation remains.
