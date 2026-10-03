# Operator decisions — antiek-mothership (binding for lanes A and B)

Recorded 2026-09-24 ~15:05 +03 by session 236c36bd (Antiek Nudge v2) from the operator's
answers to the htmlspec interview (AskUserQuestion). These override any default in the spec.

| # | Question | Operator answer | Consequence for the spec |
|---|---|---|---|
| D1 | How do Research and Writing relate? (**amended by D5: three motherships**) | **Two motherships, shared projects.** Separate Research and Writing shells, each with its own workstations over the same projects; you switch mothership to change mode. | Two shells (Research, Writing) share one project/workstation registry. A project is a workstation in both. Reading is embedded in both (it is not a third mothership). Switching mothership keeps the project context. (NOT the "one workstation holds both" model that was recommended.) |
| D2 | Hotkey model | **herdr prefix + direct chords.** A prefix key (herdr-style, e.g. ctrl+b) then a number/letter hops tabs and workstations; browser-safe direct chords (alt+1..9 tabs, ctrl+alt+1..9 workstations, cmd+K switcher) also work. | Both keymaps ship; one keymap table is the source of truth; every binding has a visible, discoverable twin (palette + cheat sheet). |
| D3 | Where does the human-facing companion document live? | **Tab + rail beside evidence.** Every workstation has a Companion tab for the project; each evidence document opens with a slim companion rail beside it (what subagents found in it; process and outcome one click deep). | Two renderings of one derived companion (project-level tab; per-evidence rail). Lane B guardrail: derived from research-artifact / html_projection projections, not a parallel document model. |
| D4 | Autonomy of diligence on flags | **Opt-in per flag, daily cap.** Flagging offers "diligence this"; accepted flags run in the background on the chosen model under a daily spend cap the user sets; results land in the thread + companion doc; an attention inbox notifies. | No auto-run without per-flag consent; a user-set daily cap is enforced before spend; an attention inbox surface (herdr-like notification) is required. |

## Lane split (agreed 2026-09-24 with Antiek Sweep v2, session a59f7aa2)

- **Lane A — Antiek Nudge v2 (236c36bd), branches `design/mothership-*`, board claim `mothership-ux-2026-09-24`:**
  A1 the two mothership shells + shared workstations + tabs + D2 hotkeys + switcher/attention inbox chrome;
  A2 reading embedded in both motherships; A3 highlight -> island + ask-without-highlight;
  A4 thread UX (list, ask-this-thread, merge UI, merge-into-document/fork UI, companion tab + rail rendering);
  A5 design-craft continuity (W1-W7, rubric re-score).
- **Lane B — Antiek Sweep v2 (a59f7aa2), branches `feat/mothership-*`, board claim `mothership-data-2026-09-24`:**
  B1 thread model (a thread IS an investigation: existing id, event log, spawned_from/start-payload lineage, passage_research anchor, plus missing anchor/addressability fields); B2 context merge engine; B3 companion docs (derived from research-artifact + html_projection projections); B4 fork/merge-into-document backend (HTML-projection fork lineage + Write documents); B5 autonomous diligence (D4).
- **Contract first:** `THREAD-CONTRACT.md` — lane B drafts types + endpoints, lane A drafts UI states; nobody builds against it until both sign in the file.
- **Lane A must not edit** (lane B in flight, fix/audit-wave5-c2-export @5e9b8f3c5): substrate/research_artifact/{context,build_body}.py, substrate/event_log/events.py, substrate/provenance/pointers.py, roles/note_taker/{living_note,distill_query}.py, QuestionEscalatedToResearchPayload.launched. UI needs -> contract fields.
- **Critic lineage:** codex gpt-6-sol for both lanes; MiMo/Kimi as bounded implementation lanes.
- **Ground truth:** origin/main 15e78e276, read-only worktree ~/Antiek/platform/.claude/worktrees/ground-main-20260924.
- **Merging:** only via Antiek Nudge's train.

## Added 2026-09-24 ~15:35 +03 (operator message, verbatim intent)

| # | Decision | Operator's words (condensed) | Consequence for the spec |
|---|---|---|---|
| D5 | **A third mothership: Reading.** D1 becomes THREE motherships (Research, Writing, Reading) over shared projects. | "I also want a mothership for the reading product." Two use cases: **(i)** a Kindle / real-book replacement, with tabs to investigate the companion deep researches I trigger, or to open a footnote or reference, "where I can tunnel through a rabbit hole and open many documents in the tabs"; **(ii)** part of an ongoing research or writing project, "but I likely would open that project through the reading product": to deep-read something specific, something I or the agent previously flagged, or something new I know I have the time and energy to read. | The Reading mothership is entered by *what to read*: continue a book, the to-read queue (flags by the user OR an agent, per D4), or something new. A standalone book (use case i) needs a home even without a project: see Q-A5. Kindle-grade reading comfort is in scope: typography, position sync, page keys, progress, distraction-free mode. Footnote and reference resolution opens a branch tab, never a navigation away. |
| D6 | **Tabs are an infinitely nested tree (the logic tree).** | "the tabs that I navigate as sub branches from the document … if I create sub-branch from a sub-branch, I want that to be layered rather than only existing in two layers; I actually want it to be infinitely layered to represent the precision of the logic tree." | A tab has a parent tab. Opening a footnote, reference, citation, island or deep research from a tab spawns a CHILD tab. Depth is unbounded. The UI must stay legible at any depth: a breadcrumb path, a tree view, subtree focus, hierarchical numbering (e.g. 3.2.1) and keys for parent / child / sibling. The model is universal (a flat tab strip is a depth-1 tree) and first-class in Reading. |

## Added 2026-09-24 18:20 +03 — cockpit ratification (operator message, verbatim intent, supersedes where noted)

| # | Decision | Consequence for the spec |
|---|---|---|
| C1 | **One cockpit shell.** Research/Read/Write doors (mod+j/e/y, plus Speak/Home) are MODES inside one cockpit, not separate motherships. | D1/D5's two/three-mothership model is SUPERSEDED: one shell, the motherships become modes. D1/D5 content (shared projects, embedded reading, Reading's two use cases) survives as mode definitions. |
| C2 | **Omarchy inset two-pane is a layout preset INSIDE Opus PanelLayout** (gaps, background, left toolbar visible). | Extend PanelLayout with the inset preset; do NOT replace it. The full-viewport dock stays available as another preset. |
| C3 | **Keymap: keep D2 (herdr prefix + ctrl+alt chords + SPR-08 mod+[/]). Omarchy-feel aliases only where the browser is free. Do NOT bind Cmd+Left/Right or Cmd+F.** | Pane focus and fullscreen-pane land on prefix/chord bindings, not the browser-owned Cmd chords. D2's one-keymap-table source of truth and visible-twin rule are unchanged. |
| C4 | **The right pane IS the Opus companion (D3); each AI agent is a tab inside it.** Agents open documents as LEFT-pane tabs via the tab tree (D6). | D3's companion rail becomes the cockpit's right pane; agent sessions (research threads, dialogue, diligence) are tabs within it. Cross-pane action: an agent tab can open a document as a left-pane child tab (D6 tree). |
| C5 | **Write mode layout: right = one tab per outline building-block (with DnD source documents into each block); left = the full body first, then per-section tabs.** AI agents stay one keystroke away via the AI sidecar (mod+/). | Writing's right pane is the block-outline (not the agent companion — the sidecar covers agents in Write mode). Left pane: body tab first, granular per-section editing tabs after, forensic sentence-level editing preserved. |

## Operator rulings, 2026-09-26 (asked by lane A in-session; answered by the operator)

- **C1–C5 confirmed.** Kimi's cockpit decisions stand: one shell with research, writing and reading modes (C1); the Omarchy inset layout (C2); pane-focus and fullscreen keys (C3); agent tabs in the right pane (C4); Write mode with block tabs on the right and body/section tabs on the left (C5). Lane A's key reconciliation is part of this: `n`/`p` act on the focused pane; `i` is the inbox; `prefix+shift+i` toggles the layout (DESIGN-MODEL §2). This replaces the earlier "ratification unverified" caveat.
- **T6, merge and fork of a reformulation.** Fork = a new revision of the derived asset (`revise`); the original revision stays. Merge = either adopt the reformulation as this project's reading version (a pointer) or merge its content into a Write deliverable. Nothing ever writes into the source.
- **T7, presentation of evidence.** The AI chooses per answer whether to quote, cite quietly, or keep citations in metadata only. Every claim still carries a resolvable citation, the full evidence record is always kept, and the choice is recorded per answer. This matches the operator's paragraph 2.
- **T9, tab forests.** One tab tree per mode for now (research, reading and writing each keep their own left/right tree per project). A shared research+reading forest is not adopted.
- **Prod verification (2026-09-26, asked by lane A).** Agents verify prod read-only: `build_sha` equals the merge SHA, plus read-only GET probes of the new routes and assets. Agents never POST, PUT or DELETE on prod, and agent sign-in is disabled there. Live flows that write are driven by the operator from a short walkthrough checklist that lane A writes per sprint (steps, expected screens, what to look for). A sprint counts as "verified on prod" when the read-only checks pass and the operator's walkthrough is done.

## Operator rulings, 2026-09-26 (second set): the addendum's recommendations

The operator accepted these recommendations from `forensics/GROUNDING-LANE-A-R18-R40-2026-09-26.md` §5 as written. Each can be overturned later. Three decisions (the project model, cross-project agents, and the merge draft) were delegated to lane A, to decide after consulting Fable 5.1; they are recorded separately below when decided.

1. Books rename scope. Recommendation: rename the user-facing label only (rail, Home, key sheet, Library heading 'Books', 'Your readings' → 'Your books') and keep code ids, routes (/library, /read/:id) and ⌘E. Add a /books SPA redirect as a brand alias. ⌘B stays unbound because it is bold in editors.
2. Harden vs Flag for diligence. Recommendation: two separate verbs. Harden is an immediate child research you launch and pay for per run. Flag for diligence stays the consented, capped background form.
3. Highlight inside a thought-partner (dialogue) reply in the MVP? Recommendation: research-thread output first. Dialogue replies follow once dialogues are real threads (LB-3), which the same work enables.
4. Speak's place. Recommendation: Speak gets its own two-pane door (sections left, detail right) with no agent tabs and no forest. This amends T11's 'single surface'. Speak requests join cockpit projects only as links (member_kind speak_project), never by sharing the interview_projects table.
5. Inbound Invites in Speak. Only operator identities can sign in, and invitees deliberately have no accounts until G7. Recommendation: ship Invites as a designed locked state now. Optionally save invite links you open while signed in (a bookmark; the token stays the credential), labelled as such.
6. Broaden Speak from remembrance to general insight requests, with biography kept as one template? Recommendation: yes. It is mostly copy and flow, and the backend already accepts requests with no subject.
7. Door keys for new products: the ⌘-letter space is full. Recommendation: Converse and Autonomous get no ⌘ door. Reach them through More (⌘I) and the prefix+shift+m picker, and leave the mod+g duplicate alone for now.
8. Door semantics. Recommendation: ⌘J/E/Y/U land on the product home with the active project pre-focused, so Enter goes into its cockpit, rather than skipping the home.
9. Keys. Recommendation: prefix+shift+n (plus ctrl+alt+n) is 'New project'. ctrl+alt+1..9 jumps to tabs, which amends D2, and projects use digits inside the prefix+w list. Next/previous project is deferred.
10. Autonomous Research placement. Recommendation: a door outside the mode cycle (like Speak and Home) whose surface manages agents across projects. Spawning stays off until the consent and claim-then-spawn work (LB-10) lands, and then you decide whether to enable it.
11. Books selecting a Research project. Recommendation: the book keeps its own identity and is added as a member of the chosen project with a link back. Books agents stay separate and read the project without writing to it. Promote-in-place is kept only for 'turn this book into a new project'.
12. May a Books interest project ('Airplanes') hold papers, articles and web pages as its main series, or only books? Recommendation: long-form assets of any type, with books first and non-book assets marked.
13. Should the book notebook spend model calls to write narrative prose on its own? Recommendation: v1 is a spend-free structured view over what the agents already produced. Narrative prose is an opt-in action under consent and the daily cap.
14. Converse voice: turn-by-turn voice notes (what exists; a 3–5 s round trip) or live duplex conversation? Recommendation: turn-by-turn for the MVP. Duplex needs a Realtime-class vendor, which the master spec defers.
15. Must a monologue ship as audio at MVP? Recommendation: yes for the headline use (paid per-span TTS with the estimate shown first), with text rendered alongside. When the project cannot honestly fill the time, the monologue reports the shortfall and never pads or cuts.
16. Can Converse talk to Speak projects? Recommendation: not in the MVP. Converse lists registry projects only, and Speak content arrives by transferring to Writing or Research first.
17. Keep raw audio of voice notes? Recommendation: no. Keep the confirmed transcript only (object storage stays dormant).
18. Confirm that talking to information (R17) is now built while watching (video) stays noted-only. Recommendation: confirm.
19. Solo agent pane: remembered per project or entered each time, and how wide? Recommendation: transient by key in v1, at half the cockpit width (minimum 480px). 320px is too narrow for a conversation.
20. Group of agents: one synthesising voice with per-sentence attribution, or each agent replying separately? Recommendation: one voice with attribution. It is cheaper and needs no new store.
21. PR #3517 (a workstations registry with no mode key) is open against main. Recommendation: close it in favour of contract §1.5/§1.6, keeping #3485's owner scoping, revision CAS and validator.

## Delegated decisions, 2026-09-27 (lane A, after consulting Fable 5.1; operator may overturn)

The operator delegated these three to lane A ("consult Fable 5.1 … make the decision that maximizes the technical precision, exhaustive attention to detail, and craftsmanship that is hard to vary"). Each was argued by two Fable 5.1 advocates and settled by a Fable 5.1 judge against origin/main d61e5256d. The judges' full output, with path:line evidence, is `forensics/FABLE-PANEL-DELEGATED-DECISIONS-2026-09-27.md`. Lane A adopted all three as written, with the one naming choice in D-M below.

**D-P · The project model: one registry, one identity across modes (confidence high).**
- **One registry, one project.** There is one project registry (§1.5 over `write_folders`). A project is one identity across the three cockpit modes and never a per-product object.
- **The row.**
  - `home_product` is `research | writing | books`. It is the birth product, immutable, and it picks the create page and the default mode.
  - `products[]` is a non-empty subset of `{research, writing, books}`. It drives the homes, `mode.cycle` and which transfers are offered.
  - `kind` is `project | book | interest`, with `reading` accepted as an input alias for one release.
  - `derived_from_project_id` points at the project a partial transfer came from.
- **Transfers.** A transfer never copies content.
  - **Whole:** it appends to `products[]` and writes one `project.transferred` event, so the same id opens in the target mode with its own tree (T9).
  - **Partial:** it creates a new or named project that holds member references only, plus the event with a `selection_digest`.
- **Tightening 1.** Speak and Autonomous are not product values.
  - Speak joins the registry only through `member_kind: speak_project` links (ruling 4). Speak → Writing creates or reuses a Writing project and reuses `interview_projects.deliverable_id`.
  - Autonomous is `member_role: managed` on threads inside their existing project (ruling 10). There is no autonomous create seed until LB-10 lands.
- **Tightening 2.** R33 from the Books side is ruling 11's two-identity link: the research project gains `{member_kind: project, role: context}`, and the book keeps its id and links back. Research → Books whole is the presence append plus a shelf. Promote-in-place narrows to "turn this book into a new project".
- **Tightening 3.** Every §1.13 hold and settlement records `mothership`.
- **What the homes read.** Homes list by presence (`?product=`), never by `home_product`. "Leave Writing" (removing a product) is a separate control from "Archive project". Legacy `write_folders` rows migrate as `home_product: writing, products: [writing]`.
- **Reconsider if** any of these happens:
  - the operator says a Research project and its Writing counterpart are different objects;
  - G7's share unit must be per product;
  - the Books lens leaks in tests or in the walkthrough;
  - the row keeps growing product-specific NOT NULL columns;
  - per-product reporting outgrows the `mothership` column;
  - R29 is restricted so that membership stops being the authority for "threads of project X".

**D-A · Cross-project agents: an agent is a promoted thread with narrow, explicit reach (confidence high).**
- **Identity.**
  - An agent's id is its `thread_id`, promoted by `agent.promoted`. There is no agents table and no `agent_id` anywhere in the MVP.
  - Its charter is the derived asset `agent:<thread_id>`, revised with compare-and-set (`409 revision_moved`).
- **Membership.**
  - An agent belongs to projects through `write_folder_members {member_kind: investigation, member_role: agent | managed, reach: attached_only}`. `reach` is CHECK-constrained, so a second value needs a ruling.
  - Owner equality is required, and a mismatch answers 403. A membership or attach write answers `422 project_shared` when any member project has more than one owner.
- **Turns.** Turns live on one session dialogue per (agent, project), never on the agent's own log. A group is the same object with 2–4 participants.
- **What an agent reads**, through the one assembler (`GET /investigations/{id}/context?project_id=`), in this order:
  1. its charter;
  2. its own gated pack;
  3. its accepted drafts;
  4. its `merged_from` members, to depth 8;
  5. its own B0 children that are members of the calling project;
  6. the session's turns;
  7. items explicitly attached in the calling project.
  It never reads a project's members ambiently.
- **Receipts.** Every turn writes a context receipt listing what was included and what was dropped, with the reason (budget, withheld, refs_only).
- **Growth.**
  - Durable cross-project state changes only through a reviewed, digest-bound merge or an explicit attach.
  - O-6 is amended to "never *implicitly* from turns".
  - No agent path writes account memory until R15's proposal contract lands.
  - T8 holds as membership: the agent tab in project P holds P's session thread.
- **Reconsider if** any of these happens:
  - Autonomous gains schedules or concurrent brief editing beyond what a CAS `revise` can serialise;
  - the roster or daemon fold exceeds p95 250 ms at the real count;
  - G7 needs a shared agent;
  - after a sprint of use, the operator asks for ambient reach (flip `reach`, not the model);
  - another consumer mints an actor id;
  - per-project sessions read as amnesia;
  - R15 lands.

**D-M · The merge draft: a model-written draft under an estimate, adopted verbatim (confidence medium).**
- **The free preview stays step one.** The free §1.10 rights-gated preview is mandatory, and it stays visible under the draft as "what the model was / was not shown".
- **The draft.**
  - It is one model-written merged analysis, generated under an estimate and the daily cap.
  - It is typed as an answer-shaped synthesis: the Synthesis gate, T7 `answer.provenance`, and `claims[]` each carrying `item_ids` that resolve to served or cite_only pack items, else `422 unresolved_claim_ref`.
  - It is **not** a §1.11a reformat derivation, so LB-25 drops its LB-4b/LB-5 dependency and §1.11a's five-investigation cap does not bound merge members.
- **Editing.** An edit makes a child draft, with operator-origin sentences and no model call.
- **The commit.**
  - It names `{draft_id, draft_digest}`, adopts the draft byte-for-byte, and makes zero dispatches, asserted by counting.
  - Without a draft it answers `422 draft_required`. A stale draft answers `409 draft_stale` with its reason, and it never regenerates silently.
- **Targets.**
  - "Accept as new merged thread" is the default.
  - "Accept into agent…" writes one append on the named target, and answers `422 target_unavailable` until agents exist.
  - There is no auto-fold into a common parent (O-2's clause is struck); the parent is only preselected as a suggestion. "Both targets in one press" is not offered.
- **Naming choice (lane A).** A merge into an agent is recorded by exactly one event, `thread.merged_in {merge_id, merged_from[], accepted_draft {draft_id, draft_digest}, preview_digest}`. The assembler reads it as an attachment. `thread.context_attached` is used only for `via: manual`.
- **Reconsider if** any of these happens:
  - the operator, shown both shapes, says the grouping alone is the draft (commit then accepts `draft: null`; a one-line change);
  - drafts arrive mostly unreferenced (under 50% of sentences carrying refs);
  - lane B shows §1.11a spans are needed and can calibrate them on a merge fixture;
  - merge drafts become the dominant cap consumer;
  - the §1.10 base slips past W3 with no owner (ship preview-only, never the ungated compose page);
  - LB-26 misses the MVP;
  - the operator asks for "both in one press";
  - a single-writer stall appears on the commit path.

## Lane-A defaults for questions the grounding dropped, 2026-09-27 (operator may overturn)

The completeness critic found six questions in the raw grounding that never reached the operator (GROUNDING-LANE-A §6 item 15), plus lane B's conflict K-12. Lane A proceeds on these defaults and lists them for the operator. None of them spends money or crosses a signed decision.

1. **A Writing project with no research.** It may start empty ("No research yet"), with a one-key, costed "Start research" offer. Nothing paid starts without that press. This retires ConnectResearch's auto-spawn, and SceneChrome's "New piece" goes through the create page, so a piece is always a project member, never an island (R26-c).
2. **"The context of the book" (R32).** The book, its shelf, and what the agents grounded in or opened. It is not every document in a linked research project; this matches LB-29's thread set.
3. **Converse.** A product with its own home and a door outside the mode cycle (ruling 7: reached through More and the prefix+shift+m picker). Its session surface is the R25 agent-first pane. It has no tab forest of its own (T9).
4. **A Speak redraft** is a new revision of the same deliverable (T6; LB-15 reuses `deliverable_id`).
5. **Speak's sections** are three: My projects, Invites, Public. Invites is the designed locked state (ruling 5).
6. **Agents proposing account-memory facts.** Not in the MVP. Revisit when R15's proposal-and-confirmation contract lands, and then only as proposals the owner confirms (D-A).
7. **K-12, C3 against R25's "command F".** C3 stands, and the browser's ⌘F stays Find. The operator's "command F like the Omarchy flow" is served by the Omarchy-analogue fullscreen key, prefix+f / ctrl+alt+f, and the key sheet labels it that way. Overturn by recording an explicit C3 override.
8. **When voice sends.** In a composer that starts paid work (a research launch, a reformat, a merge question), voice fills an editable draft and never sends by itself. In a conversational surface (a dialogue ask, a Converse turn), a voice note sends when recording stops, with its transcript shown alongside it. This reconciles lane B's O-17 ("voice asks send automatically") with consent before spend (`forensics/SPRINTS-LANE-A-A10-A24-2026-09-27.md` §6).

## Naming and gates reconciled after lane B's cross-check, 2026-09-27

- **Ruling 1 governs data names; D-P's `books`/`book` values are withdrawn.** Ruling 1 keeps code ids. D-P's substance is unchanged: one registry, one identity across modes, and presence limited to three modes. Only its value names change:
  - the mode key stays `reading`, with no `books` alias;
  - `home_product` and `products[]` take `research | writing | reading`;
  - `kind` is `project | reading | interest`: the rev-7 `reading` kind for a book-shaped project, with only `interest` added (the in-flight LB-2 has `PROJECT_KINDS = ("project","reading")`).
  "Books" is the user-facing label everywhere, and `/books` is only a brand-alias route (`cockpit/CROSSCHECK-R18-R40-LANE-A-VS-B-2026-09-27.md` R27, R31).
- **The standing autonomy envelope needs the operator.** Lane B's O-11 (one expiring, revocable envelope per agent) is an exception to operator decision D4 ("no launch without per-flag consent"). A delegated lane-A decision cannot grant that; D-A's mention of O-11 describes the mechanism, not a ruling. Until the operator rules, A24 (the Autonomous door) uses per-flag consent under D4. Ruling 10 already keeps spawning off until LB-10 lands and the operator enables it. The O-11 ruling is asked in the operator summary with that fallback.
- **Where a project key lands.**
  - `project.list` (prefix+w) opens the chosen project in the current mode when the project is present there; otherwise in its `last_mode`; otherwise in its `home_product`.
  - From a door outside the cycle (Home, Speak, Converse, Autonomous), it opens in `last_mode`, else `home_product`.
  - The door keys ⌘J/E/Y/U always name their mode (ruling 8).
- **Seam shapes lane A accepts from lane B.**
  - `origin.output_anchor` replaces lane A's `thread_ref{NodeTextAnchor}`, which would carry withheld text in the payload.
  - Branch lists use `?parent_thread_id=`.
  - The create is the atomic seeded `POST /projects {…, seed, idempotency_key} → {project, next}`.
  - Speak → Writing is a Speak-side route, because a Speak request is not a registry project (ruling 4).
  - The monologue request uses lane B's `{source: {scope, query}, params: {mode, listening_minutes, delivery, voice?}, parent_thread_id}`.
  - `at` uses lane A's four fields `{derived_asset_id, revision_id, span_id, offset_seconds}`.
  - Session `scope` stays a union, `{project_id} | {document_id}`, because TalkToBook needs a book scope.
  - The voice hook is `useVoiceInput`.

- **Default 8, refined against ruling 17 (2026-09-27).** A conversational voice note (a dialogue ask, a Converse turn) shows its transcript and sends it after a visible 1.5 s grace window. Enter sends at once, and Esc keeps the text for editing. What is sent is therefore a transcript the operator saw and did not stop, which is ruling 17's "confirmed transcript". No audio is kept. Paid-work composers are unchanged: an editable draft that never sends on its own.

## Rev 9 §1.4c co-signed at the section level, 2026-09-27 (lane A and Astra)

- **What was signed.** The pinned text `THREAD-CONTRACT-REV9-SECTION-1.4c-PIN.md` at SHA-256 `a99c4950a568240ecaeef71974fbf34a78e10e0067d8798d3c6870185a5c6821`, paired with fixture commit `41e4825d3e039a213fdb47748a4ace5aeaaa017f` (branch `contract/html-text-projection-fixture-20260927`). The signers are lane A (author) and Astra (the Codex backend Undertaker; receipt in `specs/antiek-backend-forensic-20260927/INBOX.md` and its run-ledger). Lane A verified the file hash and the fixture SHA on disk before recording this.
- **The file is now immutable.** A change is a new dated revision that both sign again. Lane B pastes the section verbatim into rev 9 Part 1 as §1.4c. Lane B's separate "notes to §1.4c" (additive nullable columns; §1.11a's derived-asset projection kept distinct) sit outside the signed text.
- **Not yet binding.** The whole of rev 9 still needs both lanes' signatures and a different-lineage audit ACCEPT. The differential Python/browser gates (malformed trees, mounting context, sampled production strings) stay execution gates. No product or production acceptance is implied.
- **Owners are coordination, not claim overrides.** Item 14's "Backend (Astra)" owner line is a coordination responsibility. It does not override existing claims held by the Codex train session Antiek Nudge on the A03, anchor or reader work. Whoever builds a piece still takes or coordinates the board claim first.

## Operator ruling, 2026-09-27: A06 private-authored upload gating (relayed from Astra by the operator)

- **The rule.** A missing, errored or unsupported private-authoring capability **disables** private submission, with an honest "needs a server update / try again" state, until the capability is confirmed. The capability is the static `GET /sources/upload/attestations` listing `user_authored_private`. Once it is confirmed, the explicit new token (or the server's alias, for old clients) is safe on fresh writes.
- **Why.** The client must never fall back to `user_owned` for authored content. On an API without A06, `user_owned` is served publicly: `substrate/books/servability.py:83` maps it to PLATFORM_AUTHORED, and `constants.py:530,539` lists it as servable. Passing existing tests does not establish privacy.
- **Effect today.** No capability route exists on prod yet, so the Sources "I wrote this" option (which sends `user_owned`) goes to its disabled state as soon as the gate ships, stopping new public exposure of authored uploads.
- **Who builds it.** The files belong to Antiek Undertaker v2's claim `ffx-spr-02-reader-servability-uploads-20260927` (PR #3539). Lane A has asked Undertaker to fold the gate into #3539, or to release the files.
- **Supersedes** lane B's 00:30Z fallback proposal ("404 or error → send user_owned"). Lane B has already retracted it.

## MCP public partition confirmed, 2026-09-27 (Astra and the principal; relayed by the operator)

- **Sole implementation.** #3424 (`fix/w5-mcp-hardening-20260923`, lane A) is the only implementation of `search_public`. There is no extraction and no competing rewrite. #3264 drops its released `search_public` hunk at rebase.
- **The partition.** MCP public = the canonical §9.0 gates **AND** `PUBLIC_GRAPH_CONTENT_CLASSES ∩ SERVABLE_CONTENT_CLASSES`. Legacy `user_owned` and NULL rows are **negative MCP controls**.
- **Fixes accepted.** Lane A's F-A (a designed provider failure) and F-B (lexical recall over the same gated partition, plus a count of rows not yet indexed) are accepted.
- **Counts.** Unindexed counts cover the public partition only, never a private or unknown row.
- **The root audit will verify:**
  - a query-positive unembedded public match;
  - an embedded matching takedown staying negative;
  - a designed provider failure;
  - hydration under the same rights snapshot.
- **Still open, separately:** the D1/PA02 composition proof.

## Lane-A defaults recorded 2026-09-29 (P0-1 C6 + G-X4; operator may overturn)

Recorded by the p0-runorder execution lane while wiring the forensic packet's RUN ORDER. C1–C2 already rule the chassis; these two entries close the confirmatory residual and the G-X4 question so no sprint waits on them.

**C6 · Disposition of FFX SPR-01's shared-workspace layout (confirmatory residual).**
- C1–C5 remain law: one cockpit shell; Research/Read/Write are **modes**; Omarchy inset is a **preset inside** `PanelLayout` (inset is the default).
- **Default:** keep the FFX shared-workspace layout (the layout that landed via #3542) as a **third C2 preset** alongside inset and docked. It is already in prod and the operator has used it; retiring it is a loss without a replacement. Both presets remain reachable via `prefix+shift+i` (DECISIONS 2026-09-26 ruling).
- **Overturn to:** retire it with a written note naming what supersedes it — only if the operator says the cockpit preset fully replaces it.
- **Not blocking.** Executions proceed on C1–C2 regardless.

**G-X4 · Prefix Settings control.**
- **Default:** **no Settings control** for the `ctrl+b` prefix. The default `ctrl+b` works without one (GAPS §8). `prefix+?` key sheet remains the discoverability surface.
- **Overturn to:** add a `prefix+,` / Settings row in the one keymap table if the operator wants a key-rebind UI.
