<!-- Lane B (Antiek Sweep v2, a59f7aa2) cross-check of forensics/GROUNDING-LANE-A-R18-R40-2026-09-26.md against cockpit/GROUNDING-LANE-B-R18-R40-2026-09-26.md, 2026-09-27. Read-only subagent; evidence at origin/main d61e5256d. -->

# Cross-check of the R18–R40 groundings: lane A (UX) vs lane B (data)

**Refs.** `@main` = origin/main `d61e5256d` (checked: `git rev-parse`). `TC` = THREAD-CONTRACT.md as it stands now (1,688 lines, home commit `132444897`, 2026-09-27 00:27). Both groundings' TC line numbers have drifted, so TC lines below are current and each one is quoted. `DEC` = DECISIONS.md. Ruling numbers 1–21 are the second set (DEC:57–77). "A:" and "B:" mean the lane's grounding. Where a lane-A package number is lane A's own proposal, it is written in quotes, for example A's "LB-14", because it collides with lane B's numbering (see §0).

**Evidence.** Everything cited `path:line` below I read on `@main` with `git show` or `git grep`. The one exception is labelled. Midway through, the session was moved into worktree `lb34-takedown` and Bash was refused after that. The only check that affected was lane B's Caddy `@api_routes` claim, which stays UNVERIFIED here and is not load-bearing.

---

## 0. Two namespace collisions to fix before anything else

Both lanes number their proposals from LB-12 and from S9, with different meanings. Every cross-lane "depends on LB-n" and "S-n" reference is therefore ambiguous today. Lane B owns the LB namespace (Part 1), so lane A renumbers its references.

| Lane A's proposed id | Lane B equivalent | Gap |
|---|---|---|
| "LB-12" containment (source merge, opportunities takedown leak) | none | **B has no package** |
| "LB-13" registry rev 9 | LB-17 (on LB-2), part of LB-15 | |
| "LB-14" B0 on main, thread_ref, harden | LB-19 + LB-20 | |
| "LB-15" merge draft | LB-24 (§1.10 base) + LB-25 | |
| "LB-16" reading home, F8, agent origin | LB-14 (continue). Agent origin is already LB-2 | **F8 and /flags have no B package** |
| "LB-17" (A's critic: RightsGatedPack + §1.10 base, "number unused") | **collides with B's LB-17 (registry)**. §1.10 base = B's LB-24 | **pack has no B package** |
| "LB-18" book notebook | LB-29 | |
| "LB-19" voice metering | LB-12 + LB-23 | |
| "LB-20" Speak backend | LB-15 + LB-16 (+ LB-13) | |
| "LB-21" transfers | LB-18 (+ LB-15) | |
| "LB-22" Converse | LB-21 (+ LB-22, LB-27) | |
| "LB-23" monologues | LB-30 + LB-31 | |
| "LB-24" growing agents | LB-26 (+ LB-24 target) | |
| "LB-25" autonomous | LB-28 | **diligence `project_id` and /flags missing** |
| none | B's LB-13 (Speak intake integrity), LB-22 (book-ask scope) | A has no package for these |

Seams collide the same way. A's S9 is the project registry; B's S9 is output anchors. The mapping is A-S9→B-S14/S15, A-S10→LB-2 (signed §1.6), A-S11→B-S9/S10, A-S12→B-S11, A-S13→B-S12, A-S14→B-S13, A-S15→B-S20, A-S16→B-S21, A-S17→B-S19/S17, A-S18→B-S22, A-S19→B-S16, A-S20→B-S23. A-S21 (the hardened projection) has no B equivalent, and B-S18 (book ask) has no A equivalent.

---

## 1. Register cross-check, R18–R40

| R | Lane A | Lane B | Verdict | Evidence / resolution |
|---|---|---|---|---|
| **R18** | EXTEND, A+B. A10 (prereq), A14, A's "LB-14" | EXTEND. LB-19, LB-20 | **DISAGREE** (seam shape, one fact) | The facts agree: B0 is not on main (`6e395c0c8` is not an ancestor, and `InvestigationBranchedPayload` has 0 hits), and Loop One's context omits `spawn_context` and the parent pack (orchestrator.py:2085-2098). One B fact is wrong: `parent_event_id` *is* set, but to the child's own start event (app.py:2865), inside `contextlib.suppress` (:2856). A's "failed write is swallowed" is the accurate reading. On shape, A's `origin.thread_ref{…, anchor: NodeTextAnchor}` vs B's `origin.output_anchor` (§1.4b) plus `GET /investigations/{id}/outputs`: **B's shape wins.** NodeTextAnchor requires `quote/prefix/suffix` (feedback/domain.py:23-32), so text from a withheld segment would travel in the payload. B keeps the quote only when the segment was served. B must reuse `validate_node_text_anchor`'s rules (unicode-nfc-v1, 32-scalar context, domain.py:41-71) rather than write a second validator. A drops `thread_ref` from §2.2, §2.3 and S11. Per ruling 3, B's LB-19 MVP covers research output only; `thread.turn` and `read.book_answered` segments come after LB-3. |
| **R19** | EXTEND, A+B. A14, A's "LB-14" (`intent`, S21 `hardened`) | EXTEND. LB-20 (`purpose: harden\|chase\|ask`, `target`) | **DISAGREE** (B is missing a field) | Ruling 2 makes Harden (an immediate, paid child) and Flag (consented, capped) separate verbs. B's spend table already files harden under "Research start", which is consistent, but O-4's "Ask / Research further" framing is superseded. A expects a per-claim `hardened: supported\|contested\|inconclusive\|null` (S21); B has no projection. Flagging from output: `POST /diligence/flags` exists (diligence_routes.py:221) with kinds `concept\|open_question\|insight`, but `diligence_queue` has no `project_id` (diligence/schema.py:52-67). A's `GET /investigations/{parent}/branches` is not a B route; A should use `?parent_thread_id=`, which is already in the TC §1.2 filters. |
| **R20** | EXTEND. A15, A's "LB-15". R20-C1 is a CONFLICT → A's "LB-12" + A10 | NEW. LB-24, LB-25. Source merge is not mentioned | **DISAGREE** (B misses R20-C1; the draft identity differs) | Source merge is live, against T6 (DEC:48). `/research/artifacts/source-merge/{apply,preview,commit,restore}` sit at artifact_routes.py:399, 448, 490 and 543 (prefix `/research`, :53; A's citations drop it). Commit is gated only by `acknowledge_body_rewrite` plus preflight and CAS checks (:494-497). `validate_commit_boundary` has no production caller (derived_asset_boundary.py:61; tests only), yet TC:641 says commit and restore "are refused through `validate_commit_boundary`". **A is right**; B must retire all four routes and correct TC:641. On the draft, A's `POST /threads/merge/draft`→`{draft_id, draft_digest}` with `409 draft_stale` differs from B's `POST /threads/merge/drafts`→reformat thread + §1.11a revision, commit `{draft:{derived_asset_id, revision_id}}`, `422 draft_required`. B's store meets TC:126 "no new store" and T6's `revise`, but the decision is delegated to A (§5). The compose GET writes a file (artifact_routes.py:341-355, `write_draft_merge=True`), so both lanes are right: no member log is mutated, yet a GET writes. |
| **R21** | a EXTEND (B); b and c NEW (A+B). A15, A23, A's "LB-15", "LB-24" | NEW. LB-24, LB-26 (MCP in rev-9 §1.12) | **DISAGREE** (agent model; delegated) | The facts agree: `evidence_index` is off main, and `write_folder_members` is many-to-many but node-only (folders.py:65-75). The models differ. A: a dialogue thread plus `thread.context_attached{via: manual\|merge}`, turns on the agent's own log, reach limited to what is attached. B: `agent.promoted` plus a charter, growth only from accepted merges (O-6), turns on per-(agent, project) session dialogues, and reach that includes the calling project (LB-26 assembler item 5). The "into agent" target is `target:{agent_thread_id}` in A and `into_thread_id` + `thread.merged_in` in B. The MCP URI is `antiek://threads/{id}` in A and `…/{id}/pack` in B. |
| **R22** | EXTEND A+B (a, b); CONFLICT (c); NEW (d). A10, A12 | lane A only; seams via LB-14, LB-16, LB-17 | AGREE on ownership; seam names differ | `/reading/continue` has 0 hits on main, as both say; B's LB-14 serves it with `progress: null`. The list filter is `?home_product=` in A and `?product=` in B. R22-c is settled by rulings 4 and 10: Speak and Autonomous are doors outside the mode cycle. The R22-d listings exist in B (`?kind=dialogue&project_id=` in LB-21, `?agent=true` in S12). |
| **R23** | EXISTS (A's critic says EXTEND), lane A. A11 | lane A only | AGREE | Rulings 7 and 8 concern lane A only. |
| **R24** | NEW/EXTEND/CONFLICT, B (+A). LB-2, A's "LB-13", A11 | "lane A only"; `last_mode` seam | **DISAGREE** (ownership) | The project layer is B's LB-2 (Sweep §8.2; TC §1.5/§1.6). On main, `/projects` exists only on the Speak router (speak_routes.py:359+), there is no `project_tabs`, and `write_folders` is node-only (folders.py:55-75). LB-2 is in flight on `origin/feat/lb2-projects-tabs-20260926`, not on main. B should relabel R24 as "B: LB-2 (+LB-17)" and cite ruling 21 on #3517 (open, head `7e0c68e58`). #3485 merged only into `feat/reformat-spr03`. |
| **R25** | NEW/EXTEND/CONFLICT, A+B. A16, A23, A's "LB-22" | EXTEND (one agent), NEW (group). LB-21, LB-26, LB-27 | **DISAGREE** → ruling 20 = A | Group = one synthesising voice with per-sentence attribution. B's LB-27/O-5 (sequential `thread.turn{round_id, speaker_thread_id}` + `dialogue.round`, at most 4, a bound per round) must be rewritten to one answer with span-level `origin_thread_id`. B's conflict K-12 (C3 vs "command F") is closed: C3 was confirmed (DEC:47), so prefix+f is R25's expand key. The facts agree: /thought-partner is stateless with a `__sidecar__` default (app.py:6719), and `ContextItem.kind` is `doc\|insight` (app.py:1318). |
| **R26** | EXTEND (key), NEW (page), CONFLICT (semantics). A11, A13 | NEW. LB-15, LB-17 (`POST /projects {home_product, kind, title?, seed, idempotency_key}`→`{project, next}`) | **DISAGREE** (create flow) → **B** | A13 calls `POST /projects`, *then* the product-native create: two calls. B's atomic, idempotent seeded create is the only way LB-17's acceptance can hold ("a crash after the seed insert leaves no registry row"; one key yields one project). A changes S9 and A13 to send `seed` + `idempotency_key` and follow `next`. B must drop the `speak` seed (ruling 4). |
| **R27** | CONFLICT (model, delegated); EXTEND/CONFLICT/NEW per product. A13, A24 | EXTEND. LB-17 | **DISAGREE** (model pending; Speak and Books ruled) | The project model is delegated to A (§5). Ruling 4: drop `home_product: speak` and `seed: speak`. Ruling 1: keep `reading` as the book kind (the in-flight LB-2 already has `PROJECT_KINDS = ("project","reading")` in substrate/projects/schema.py) and only *add* `interest`. Autonomous spawning is env-gated off (daemon.py:86-93); ruling 10 keeps it off until LB-10 lands and the operator enables it. |
| **R28** | EXTEND/NEW per pair. A21, A24, A's "LB-21", "LB-25" | EXTEND/NEW. LB-15, LB-18, LB-28 | **DISAGREE** (Books, Autonomous, events, the Speak side) | The facts agree on Research→Writing and Speak→Writing: promote mints a new deliverable on every call, and `biography.py:119-122` inserts a new deliverable instead of reusing `interview_projects.deliverable_id`. **Research→Books:** ruling 11 reverses B's "whole = the project gains `books` = R33" (LB-18, O-10). **Research→Autonomous:** B's standing envelope needs O-11, which is unruled and an exception to D4; A's per-flag path fits D4, so B keeps it as the fallback. **Events: A is right.** `seam.speak_to_write` and `seam.research_to_read` are typed (events.py:3739, 3787), have no emitters, and feed the trail reader (seams/thread.py:57-65); B emits only `project.transferred`. **Speak→Writing** cannot use `/projects/{id}/transfers`, because after ruling 4 a Speak request is not a registry project. |
| **R29** | NEW (A's critic: mixed). A23, A's "LB-24" | NEW. LB-26 | **DISAGREE** (agent model; delegated) | The facts agree. B adds one A missed: `note_retrieval` has no owner filter (context_pack/note_retrieval.py:74-81). Both make evidence ids owner-safe (A: `(owner, evidence_id)`; B: sha of owner, scope, scope_id, node_id), and TC §1.12 allows either. |
| **R30** | NEW. A18, A's "LB-13" (`position`) | EXTEND. LB-17 (`interest`, `shelf`, `ordinal`, shelf CAS) | **DISAGREE** (scope) | Ruling 12: long-form assets of any type, books first, non-books marked. B's O-13 (book documents plus explicit adds) must widen; S15 already returns `document_type` for the marking. Non-book assets cannot open in the reader: `GET /books/{id}` answers 404 `book_not_found` without a `book_assets` row (books.py:2014-2026), and B has no F8 package even though TC:1110 (W1) assigns F8 to lane B. The ordering field is `position` in A and `ordinal` in B. |
| **R31** | EXTEND label-only (a); EXTEND (b, c). A18 | NEW product id; EXTEND rabbit hole. LB-17, LB-22, LB-14 | **DISAGREE** → ruling 1 = A | Label only; code ids, routes and ⌘E stay. That reverses B's R31 row, the `books` mode key, `home_product: books`, the `/tabs/books` alias and O-7. Rabbit hole: the agent origin already exists in TC §1.6 and is validated on the LB-2 branch (tabs.py:188-197). B's `transient` node field (S15) is not in A's Part 2. F8 gap as in R30. |
| **R32** | EXTEND. A20, A's "LB-18" (`GET /books/{id}/notebook`) | EXTEND. LB-29 (`/projects/{id}/companion-document?lens=books`) | **DISAGREE** (route and scope) | Both are spend-free in v1, and ruling 13 matches B's O-14. The route differs: per book (A) vs a per-project lens (B). B's route works only if every book is a project, which depends on the project model; otherwise B adds `lens=books` to the §1.12 per-document route. LB-29 fixes the notebook's thread set without asking the operator; tie it to ruling 11. |
| **R33** | EXTEND + CONFLICT (promote vs link). A18 | EXTEND. LB-18 (lens), LB-29 | **DISAGREE** → ruling 11 = A | The book keeps its own identity and becomes a member of the chosen project with a link back. Books agents read that project but never write to it. Promote-in-place survives only as "turn this book into a new project". |
| **R34** | EXTEND. A17, A's "LB-19" (cap-metered, `input_modality`, `voice_capture_event_id`) | EXISTS + EXTEND. LB-12 (off-loop, 25 MB, `input{…}`), LB-23 (record-only) | **DISAGREE** (five points) | (1) **B is right and A missed it:** both routes block the event loop. `/voice/transcribe` calls Whisper synchronously (read_voice.py:91-108, sync httpx in the client), and `/speech/tts` calls its provider synchronously (speech.py:28-38). (2) **A is right and B missed it:** the invitee voice bound is 64 MB (speak_routes.py:1180). (3) The metering class is open (O-16). B's record-only is consistent with TC:1024, where only DiligenceBudget-admitted threads can hit the cap. (4) `voice.captured` exists (events.py:3826), but B never links it; add `voice_capture_event_id`. (5) B's O-17 "voice asks send automatically" loses to A's "never auto-send" under ruling 17 ("keep the confirmed transcript only"). |
| **R35** | NEW + CONFLICT (Speak scope). A22, A's "LB-22" | NEW. LB-21 | **DISAGREE** → ruling 16 = A | B removes `scope:{speak_project_id}`, the Speak context resolver, the S13 union with `GET /speak/projects`, and the §1.9 `speak_project` context kind. A expects owner BYOT generalised to a project resource and `model_choice` on ask; B's ask has neither. Raw `/speech/tts` has no server-side §9.0 gate; B covers only derived-asset audio (LB-31). |
| **R36** | EXTEND + CONFLICT (truncation). A22, A's "LB-23" | EXTEND. LB-30, LB-31 | **DISAGREE** (seam shape, truncation) | Ruling 15: never pad **or cut**. B covers padding only, but `_bound_to_budget` truncates (meta_reading.py:128-136). The shapes differ: A sends `{mode, source:{project_id, document_ids?}, params:{listening_minutes, focus_items?}}`; B sends `{source:{scope, query}, params:{mode, listening_minutes, delivery, voice?}, parent_thread_id}`. B's audio segments (up to 3,500 characters) must be built from whole served spans. |
| **R37** | EXTEND. A22 (`at{derived_asset_id, revision_id, span_id, offset_seconds}`) | EXTEND/NEW. LB-21 (`at?`), LB-30 | AGREE (shape to pin) | Both are turn-by-turn, per ruling 14. B names `at` but never defines it; adopt A's four fields. |
| **R38** | EXTEND (reframe). R38-public EXISTS-flagged (A's critic: default-deny) | EXISTS private + EXTEND. LB-13, LB-23 | **DISAGREE** (complementary gaps) | B lacks ruling 6's support: `topic_description` is accepted on create (speak_routes.py:227) but absent from `ProjectResponse` (:230-236) and from the list (:405-431). A lacks B's intake defect: raw ASR goes straight into `submit_answer` (speak_routes.py:1485-1496). Open contribution is default-deny (invitations.py:61-67). |
| **R39** | EXTEND / CONFLICT (invites) / EXTEND (public). A19 | EXISTS/EXTEND; NEW G7-gated; public "EXISTS read-only". LB-15, LB-16 | **DISAGREE** (B misses the leak) | Unauthenticated `/speak/opportunities` (open path, app.py:1725) returns `subject_ref` (speak_routes.py:1044-1052) from a query with no `speak_takedowns` predicate (pushes.py:216-227), while `/speak/feed` has one. **A is right.** Invites: ruling 5 (locked state) matches B's `gated_G7`. The list labels every interview as a voice (count(*), speak_routes.py:414). |
| **R40** | EXTEND; CONFLICT resolved. A19, A10 | EXTEND (read models). LB-16 | AGREE (ruling 4) | A two-pane door with no forest. A's S18 calls map onto B's `/speak/sections`, `/speak/projects/{id}/detail` and `/speak/public/{id}`. Both drop the write lock on reads (`_write`, speak_routes.py:411). |

---

## 2. Seam gaps (exact names)

**Lane A expects these; lane B's grounding does not provide them:**
- `hardened` per-claim projection (A-S21, R19).
- `GET /investigations/{parent}/branches` (A-S11). Lane A should use B's `?parent_thread_id=`.
- `POST /investigations/{id}/attach` and `thread.context_attached` (A-S13, R21/R29). Pending the delegated decision.
- `target:{agent_thread_id}` on merge commit (B has `into_thread_id`), `draft_id`/`draft_digest` and `409 draft_stale` (A-S12).
- `voice_capture_event_id` in the `/voice/transcribe` response and on turns; `input_modality` (A-S15, S14).
- `model_choice` on ask, and owner BYOT generalised to a project (A-S14, R35).
- `GET /flags?intent=read\|diligence&project_id=` (A-S17, S20). 0 hits on main.
- `diligence_queue.project_id` and kind `thread` (A-S20, R28).
- Non-book reader serving, F8 (A's "LB-16(3)").
- `GET /books/{id}/notebook` (A-S17); B serves a project lens instead.
- `linked_project_id` (R33), `derived_from_project_id` (partial transfers).
- Nullable `thread_counts` and `spend_today` on project rows (A-S9). §1.5 promises them, but no B acceptance item delivers them and the in-flight LB-2 routes don't compute them.
- `topic_description`, `interview_guide`, and the `contributed_voice_count`, `invited_count` and `pending_reping_count` list counts (A-S18).
- Emission of `seam.speak_to_write` and `seam.research_to_read` (A-S19).
- `origin_thread_id` on answer spans (group dialogue, ruling 20).

**Lane B expects these; lane A's grounding does not provide them:**
- Tab node `transient` (S15; B's rev-9 §1.6).
- The `books` mode key. Void under ruling 1.
- `products[]` and `kind: project\|book\|interest` in §2.1.
- §2.5 states `draft_ready` and `draft_failed` (A has `draft_review` and `failed`).
- The S13 scope picker over `GET /speak/projects`. Void under ruling 16.
- The Books "keep" action (`member_role: context`).
- The "Which book(s)?" first-open step.
- Rendering exactly `content.text` for NFC offsets, with a shared fixture (LB-19).
- Inbox kinds `speak_answer_received` and `speak_claims_proposed` on the Speak door.
- "Project keys launch into `last_mode`" (A's A11 opens in the current mode; this is lane A's call).

**Same concept, different names.** Settle these in rev 9:

| Concept | Lane A | Lane B |
|---|---|---|
| Output anchor | `thread_ref` | `output_anchor` |
| Branch purpose | `intent` | `purpose` |
| Member order | `position` | `ordinal` |
| Project list filter | `?home_product=` | `?product=` |
| Merge draft route | `/merge/draft` | `/merge/drafts` |
| Dialogue project | `project_id` | `scope.project_id` |
| Ask payload | `text` | `question` |
| MCP thread resource | `antiek://threads/{id}` | `antiek://threads/{id}/pack` |
| Voice hook | `useVoicePrompt` | `useVoiceInput` |
| Transfers | per-pair calls | one `POST /projects/{id}/transfers` |

---

## 3. Lane A's §6 critic corrections, checked against main and lane B

| # | Correction | Concerns B? | Verified | Covered by B? | What B must add |
|---|---|---|---|---|---|
| 1 | Nothing owns the §1.10 merge base or the RightsGatedPack | Yes | `RightsGatedPack`: 0 hits on main **and** on `fix/audit-wave5-c2-export@2be3e0d1b`. Only the resolvers (substrate_refs.py:360,377) and `_excerpt_cleared` (build_body.py:71) exist, and only there. | **§1.10 base: yes**, in B's LB-24 (preview, `merge_started`, `merged_into`, merged start, `merge_pending`, replay). **Pack: no.** It is only "W2's RightsGatedPack" as a dependency. | A new package, not "LB-17" (taken): the pack adapter over source events, gated on the c2-export merge, with a red-first withheld-chunk fixture. Make LB-20, 21, 24, 25, 26, 29, 30 and 31 depend on it. |
| 2 | The unified `/flags` route has 0 hits on main | Yes | 0 hits for `"/flags` in interfaces; `diligence_queue` has no intent or project_id (schema.py:52-67). | **No.** LB-22 even presumes one ("files a `read` flag"). | A package for `POST /flags` and `GET /flags?intent=&project_id=` per TC §1.13, with a nullable `project_id` on `diligence_queue`. |
| 3 | No sprint drafts or co-signs rev 9 | Yes | Rev 8 is "draft … unsigned" (TC:23); rev 7 is signed. | **Partly.** B's §5 lists 22 rev-9 items but has no package, done-bar or signature plan. | An LB-1(c): sign rev 8, layer rev 9, get a different-lineage audit with findings closed, both signatures, and a DEC row for each override. Gate Tiers 1–3 on it. |
| 4 | T8, T10 and T11 are recommendations, not rulings | Yes | DEC records only T6, T7 and T9 (DEC:48-50); T8/T10/T11 appear only in the Sweep §7 table. | **No.** B's O-9 and the §1.0 row cite T11 as authority. | Cite rulings 4 and 10, which adopt the door model and amend Speak to two panes. Add a §7 row for T8 ("agent tabs belong to the project") vs LB-26's multi-project membership, pending the delegated decision. |
| 5 | R23-a EXISTS is really EXTEND | No | — | — | — |
| 6 | R38-public EXISTS is really gated off, with a takedown leak | Yes | invitations.py:61-67 is default-deny; pushes.py:216-227 has no predicate; speak_routes.py:1044-1052 returns `subject_ref`; app.py:1725 opens the path. | **No.** B's R39 says "EXISTS read-only". Only the new `GET /speak/public/{id}` is filtered. | The takedown predicate on `list_public_opportunities` (and `/speak/pushes`, UNVERIFIED) with a red-first test; relabel R38/R39 public. |
| 7 | R29 was collapsed; R21c should be EXTEND | Mildly | folders.py:65-75 is many-to-many. | B also files NEW. | Optional relabel of the membership piece as EXTEND. |
| 8 | R21-x (merge "into agent") has no register row | Yes | — | **Yes** (LB-24 `into_thread_id` + `thread.merged_in`, O-2). | Settle the shape with A (§2). |
| 9 | R36-truncation is on the wrong lane | Yes (backend half) | meta_reading.py:128-136 truncates. | **No.** LB-30 guards against padding only. | A "never cut" acceptance item on the monologue path (ruling 15). |
| 10 | A's LB-13 done-bar is incomplete and overlaps LB-2 | Yes (it is B's LB-17) | — | Partly. LB-17 already builds on LB-2 and has `speak_project`. | Add `linked_project_id` (ruling 11), an acceptance item for nullable `thread_counts`/`spend_today`, and a gate on the delegated project model with a fallback. Drop `speak` (ruling 4). |
| 11 | Dependency gaps (a)–(e) | Partly | (a) The agent origin is already validated on the LB-2 branch (tabs.py:188-197). | (a) Covered by **LB-2**, not by A's "LB-16". (b) TalkToBook as a session: B's LB-21 and LB-22. (d) In B's numbering, LB-14 is Continue reading, so "re-point LB-6 to LB-14" is wrong; LB-6 stays on "B0 via the c2-export merge". (e) B's LB-23 already depends on the §1.13 ledger, not LB-10. | State that B0 is not an LB package. |
| 12 | Keymap schema gap | No | — | — | — |
| 13 | Done-bars omit the per-sprint bar | Yes | GOAL v2 DONE; prod ruling at DEC:51 | **No.** B's packages have red-first pytest only. | By reference on every LB: critic ACCEPT, landed through the train, prod `build_sha` plus a read-only GET probe list per package, no prod writes. |
| 14 | Uncheckable or ruling-dependent done-bars | Yes | — | B lists O-rulings as dependencies but not which are now answered. | Mark as answered: O-4 (in part, ruling 2), O-5 (20), O-7 (1), O-9 (7, 10), O-10 (11, in part), O-13 (12), O-14 (13), O-17 (14, 17), O-18 (15), O-19's Converse clause (16), O-20 (5). Still open: O-1, O-2 and O-6 (delegated), O-3, O-11, O-12, O-15, O-16. Give each a fallback. |
| 15 | Dropped operator questions | Yes | — | B *decides* (a) no auto-spawn (the `blank_deliverable` seed), (b) the book's context (LB-29's thread set) and (d) a redraft = the same deliverable (LB-15), without asking. (c) and (e) are settled by rulings 7, 4 and 5. (f) is folded into O-6. | List (a), (b), (d) and (f) as operator questions. |
| 16 | Missing conflicts (R26-c, C1 vs T11, T8) | T8 | — | No | The T8 row (see #4). C1 vs T11 is now settled by rulings 4 and 10. |
| 17 | Missing seams | Partly | books.py:2014-2026 | (a) F8: **no.** (b) Cross-project agent and session listings: **yes** (LB-21 `?kind=dialogue&project_id=`, S12 `?agent=true`). (c) Counts: partly. | Add F8 and the counts. |
| 18 | Contract citations are unpinned and have drifted | Yes | TC is now 1,688 lines (`132444897`); the refusal claim is at TC:641 and future modalities at TC:914. | B cites mostly by section. | Pin to a home commit and quote anchors. |
| 19 | LB-12 should also retire apply and preview | Yes | `apply` (:399) and `preview` (:448) both open `connect_write`, although preview's docstring says "no-write"; TC:1095 says `source_merge.*` strings are retired. | **No.** B retires only `compose*`, and only after lane A moves (LB-24). | Retire all four source-merge routes in a Tier-0 package, independent of LB-24. |
| 20 | R30's grounder disagreement was settled silently | No | — | B's EXTEND matches A's Books grounder | — |

---

## 4. Second-set rulings that change lane B's grounding

| # | Ruling | Lane-B text now wrong | How it must change |
|---|---|---|---|
| 1 | Books is a label only; keep the `reading` key | R31 row ("NEW product id"); LB-17 (mode key `books` with a `reading` alias, `home_product: books`, the `/tabs/reading`≡`/tabs/books` acceptance, `kind: book` replacing `reading`); O-7; rev-9 items 1 (§1.0 "data key is `books`"), 5 and 7 (`mothership: research\|writing\|books`); §4 "§2.2 accepts the `books` mode key"; §7 row 2 | Keep `reading` everywhere: mode key, `home_product`, and the book `kind`. Add only `interest`. This matches the in-flight LB-2 `MOTHERSHIPS = ("research","writing","reading")`. |
| 2 | Harden vs Flag are two verbs | O-4 ("Ask" / "Research further") | Close O-4 on ruling 2: harden = an immediate paid child (the Research-start class, already in B's table); flag = consented and capped. Keep `purpose: ask` only if lane A renders it. Accept or reject A's `hardened` projection in writing. |
| 3 | Research-thread output first | LB-19's segment sources | Phase 1: `synthesize.delivered`, `graph.node.inserted`, `note.refined`. `thread.turn` and `read.book_answered` come after LB-3. |
| 4 | Speak gets its own two-pane door; links only | LB-17 `home_product: speak` and `seed: speak {…}`; LB-18's Speak→Writing via `/projects/{id}/transfers`; LB-21 `scope:{speak_project_id}`; O-9 citing T11 | Speak creates stay on `POST /speak/projects` (owner-bound in LB-15). A Speak request joins a project only as `member_kind: speak_project`. Speak→Writing becomes a Speak-side route (extend `/speak/projects/{id}/draft`). Cite ruling 4. |
| 5 | Invites: a locked state now; optional bookmark | O-20 (two readings) | Answered: `gated_G7` in LB-16 stands. Optionally add a later bookmark route (the token stays the credential, and the row is labelled as a bookmark). |
| 6 | Broaden Speak to insight requests | LB-15/LB-16 omit the request text | Return `topic_description` on ProjectResponse, the list, feed, opportunities and detail; accept `interview_guide` on create. The `template: biography` seed stands. |
| 7 | No ⌘ door for Converse or Autonomous | none | O-9 is consistent; cite ruling 7. |
| 8 | Doors land on the home with the project pre-focused | S14 "Project keys launch into `last_mode`" | Recast `last_mode` as a field lane A may use, not a prescribed behaviour. |
| 9 | Keys | none | — |
| 10 | Autonomous is a door; spawning stays off until LB-10, then the operator decides | LB-28, O-8 | Add an explicit operator-enable gate, with a test that the daemon refuses while `ANTIEK_DAEMON_SPAWN_ENABLED` is off even after LB-10. The envelope (O-11) remains an unruled D4 exception, so keep a per-flag fallback. |
| 11 | A book joins a Research project as a linked member | LB-18 ("Research→Books whole is the R33 lens", "Books→Research = the §1.5 promotion"); O-10; rev-9 item 5 ("Q-A5's promotion becomes the Books→Research transfer"); LB-29's thread set; LB-21/LB-26 reach | Selecting a project adds the book as a member with a back-link. Books agents read that project and never write to it (a reach rule plus a test). Promote-in-place only for "new project from this book". |
| 12 | Interest shelves: any long-form type, books first | O-13; LB-17's shelf admission | Admit any long-form `document_type`, order books first, mark non-books, and add F8 serving. |
| 13 | The notebook is spend-free in v1 | none (O-14 matches) | Mark O-14 answered. |
| 14 | Converse voice is turn-by-turn | none (O-17 "turn-based") | Mark it answered. |
| 15 | Monologue audio at MVP, estimate first, never pad or cut | LB-30 (`delivery` optional, no cut rule); LB-31 (segments) | Audio is the default for monologues. Add "no truncation" (meta_reading.py:128-136). Segments are made of whole served spans, gated per span. O-18 is answered. |
| 16 | Converse: no Speak in the MVP | LB-21 scope and Speak resolver row; the dependency on LB-13 item 6; the S13 union; §1.9 `speak_project`; O-19's last sentence | Remove or defer all of these. |
| 17 | No raw audio; keep the confirmed transcript only | O-17 "voice asks send automatically" | Record, transcribe, show an editable draft, send on confirm. `input.edited` already implies that flow. |
| 18 | Talking to information is built; watching is noted | Rev-9 list (no item) | Replace TC:914 "Future modalities (noted, not built)": talking is built (§1.8, LB-21), watching stays noted. |
| 19 | Solo pane is transient | none | Persist nothing for it. |
| 20 | A group answers in one voice with attribution | LB-27; O-5; rev-9 items 8 (`thread.turn{round_id, speaker_thread_id}`, `dialogue.round`), 9 (estimate = sum of participant bounds) and 18 (event `dialogue.round`); the S13 `addressees`; LB-23's "group rounds" | One dispatch per group turn over the participants' contexts, with span-level `origin_thread_id`. No per-participant turns, no `dialogue.round`. |
| 21 | #3517 closes | none (B's LB-2 in Sweep §8.2 already says so); the R24 row is silent | Cite it on R24. |

---

## 5. The three decisions delegated to lane A: which LB packages move

The implementation stays with lane B (GOAL v2: "merge drafts, cross-project agents, transfers"), so each outcome rewrites B text.

**The project model.**
- *One registry plus `home_product` (A's §5 Q1).*
  - LB-17 stands, trimmed per rulings 1 and 4, and gains `derived_from_project_id`.
  - `products[]` survives only as a record of whole transfers, since under D1/C1 every project is openable in every mode.
  - LB-18: whole = same id + `project.transferred` (already in B); partial = a new project with `derived_from_project_id` (B's lineage event alone is not enough).
  - LB-2 adds `interest` to its kinds. LB-29's per-project lens works. LB-21's Converse home can group by `home_product`.
- *Typed per product, no cross-mode sharing.*
  - Drop `products[]` and `last_mode`. A whole transfer becomes a new project that refers back.
  - The D1/C1 override is recorded in DEC. The shelf and notebook routes become per product.
- *One project across modes, no product field.*
  - Drop `home_product` and the per-product seed union. `next` carries the product-native first step.
  - Homes filter by member kinds. LB-28's `autonomous` seed has no home.

**Cross-project agents.**
- *A's recommendation: a long-lived thread with a home project and memberships; reach = what is attached, its own children and its merges; no account-memory writes.*
  - LB-26 drops or softens `agent.promoted`/charter into an optional standing brief.
  - It adds `POST /investigations/{id}/attach` and `thread.context_attached`.
  - It removes the "calling project's context" step from the assembler.
  - LB-21's per-(agent, project) session rule must be reconciled with A's "memory = its own `thread.turn` history".
  - LB-24's into-agent target becomes `context_attached{via: merge}` (or it keeps `thread.merged_in`).
  - LB-27's participants are attached threads. §1.12a and the T8 row are rewritten.
- *A first-class agent entity.* A new store, against B's rule 1. LB-26 is rewritten with a table and routes, recorded as an override.
- *No cross-project reach (T8 holds).* Membership is limited to the home project. R21c and R29 are deferred explicitly, with operator sign-off.

**The merge draft.**
- *A model-written draft under an estimate, adopted verbatim (A's Q6; also B's O-1).*
  - LB-25 stands. Settle the identity: B's §1.11a revision vs A's `draft_id`/`draft_digest`.
  - Add the acceptance item "commit dispatches nothing" and the `origin_thread_id`, grouping and conflicts fields.
  - Map "member changed after the draft" to `409 preview_stale` or add `draft_stale`.
  - The targets depend on the agents decision. B's extra "fold into the common parent" target needs lane A's consent.
- *A free structured grouping.*
  - LB-25 is deleted. LB-24 commits on `preview_digest`, with grouping in the preview (the `cascade_session.join_and_merge` precedent).
  - The merge-draft spend-class row and the `merge_draft_ready` inbox kind go. The analysis runs after commit, as TC §1.10 says today.
- *Both: a free preview, then an optional paid draft.* LB-25 becomes optional, and "Accept disabled until LB-25" is split per path.

---

## 6. Edits lane B's grounding needs, by priority

1. **Publish the LB and seam crosswalk (§0).** Lane A's "LB-12…LB-25" and "S9…S21" collide with lane B's ids, and A's critic's "LB-17 is unused" is false.
2. **Apply ruling 1.** Reverse O-7; keep the `reading` mode key, `home_product` value and book `kind`; add only `interest` (this matches the in-flight LB-2).
3. **Add a Tier-0 containment package.** Retire `/research/artifacts/source-merge/{apply,preview,commit,restore}`, correct TC:641, and add the `speak_takedowns` predicate to `list_public_opportunities`, all red-first.
4. **Add the RightsGatedPack package** (W2, gated on the c2-export merge) and wire it into the dependencies of LB-20, 21, 24, 25, 26, 29, 30 and 31.
5. **Apply rulings 20, 16, 11 and 4:** rewrite LB-27 as one voice; remove Converse's Speak scope; rewrite R33 and Research→Books in LB-18 and O-10; drop `speak` from LB-17 and move Speak→Writing to a Speak-side route.
6. **Add the missing owners:** `/flags` with `diligence_queue.project_id`; F8 non-book reader serving; LB-1(c) for rev-8 signing, rev-9 co-sign and audit.
7. **Voice:** add `voice_capture_event_id`, drop auto-send (ruling 17), set the invitee bound to 25 MB, and decide the TTS §9.0 gate on raw `/speech/tts`.
8. **Monologue:** make audio the default, add "never cut", build segments from whole served spans (ruling 15), and pin the `at` shape.
9. **Speak read model:** `topic_description`, `interview_guide`, list-row counts, and "voices" counting contributions only (ruling 6).
10. **Fix the register:** R24 is B's (LB-2, #3517 per ruling 21); R39-public is not EXISTS (the leak); R18's `parent_event_id` fact.
11. **Seams:** emit `seam.speak_to_write` and `seam.research_to_read` beside `project.transferred`; decide on `hardened`; add BYOT and `model_choice` on ask; add acceptance for the nullable `thread_counts` and `spend_today`.
12. **Governance:** close K-12 (C3 confirmed), close O-4 (ruling 2), replace T11 citations with rulings 4 and 10, add the T8 conflict row, and mark the answered O-rulings (§3 #14).
13. **Gate on the delegated decisions:** LB-17, 18, 24, 25, 26 and 27, each with a fallback (§5).
14. **Add the standard DONE bar to every LB** by reference: critic, train, prod `build_sha`, read-only GET probes, no prod writes.
15. **Add rev-9 item TC:914** (talking built, watching noted; ruling 18) and pin every TC citation to a home commit.
