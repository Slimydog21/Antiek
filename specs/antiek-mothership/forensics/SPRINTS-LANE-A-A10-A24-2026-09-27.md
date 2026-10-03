# Lane A sprints A10–A24 — the addendum (R18–R40), corrected

**Status: draft, 2026-09-27.** Lane A (Antiek Nudge v2) wrote it. It follows A0–A9 (`FORENSIC-KIMI-DESIGN-2026-09-26.md:203-212`) and applies the grounding critic's 20 corrections (`GROUNDING-LANE-A-R18-R40-2026-09-26.md` §6; dispositions in §9 below). Lane-B dependencies use Sweep v2's numbering, LB-12..LB-34 (`../cockpit/GROUNDING-LANE-B-R18-R40-2026-09-26.md` §3, plus LB-24a/32/33/34 agreed 2026-09-27).

**Pins.**
- `@main` = origin/main `d61e5256d`, unchanged at 2026-09-27 00:30 +03.
- `@rescue` = `design/cockpit-a1-d6c5-rescue-20260926`, at `a123723a1` on origin and `d2d8d43e7` locally (A1b in progress).
- Contract citations are `THREAD-CONTRACT.md@<home commit>` plus a quoted anchor phrase, never a bare line number (the rev-9 citation rule, agreed with lane B).

**Authority.** The operator's words (`REQUIREMENTS-2026-09-26.md`), the rulings in `../DECISIONS.md`, and the contract at its latest co-signed revision. This plan builds on the following and records any override in DECISIONS:
- the operator rulings of 2026-09-26: C1–C5, T6, T7, T9, the prod-verification ruling, and the 21 accepted recommendations;
- the delegated decisions D-P, D-A and D-M of 2026-09-27;
- lane A's defaults 1–8 of 2026-09-27;
- the naming and gate reconciliation after lane B's cross-check (DECISIONS, 2026-09-27).

---

## 0. The standard bar every sprint inherits (DB)

Each sprint's done-bar lists only its own items. Every sprint also carries the five-part DONE from GOAL v2 and the prod ruling. The bar is stated once here and applies by reference.

- **DB-1, rendered.**
  - **Coverage:** Playwright and Storybook at **1440, 1024, 900 and 390 px**, in light and dark.
  - **Geometry asserts:** no horizontal page scroll; pane widths within their tokens; no layout shift across a swap (CLS 0 on the asserted transition); focus visible.
  - **Stories:** every named state has a story in both themes, plus a lostpixel baseline.
- **DB-2, tested.**
  - `npm run test -- --no-color`, `npx tsc -b` and `npm run build:check` are green, with the entry chunk within budget.
  - `pytest` is green where backend files changed.
  - Every key is a row in the one keymap table and passes `validateKeymap`.
  - Every user-facing string passes copy-lint.
  - An unknown number renders `—` with its reason, never `0`.
  - No raw HTTP status reaches the UI.
- **DB-3, critic.** A different lineage (GLM or MiMo until codex returns on 09-30) reviews the exact head. Every finding is closed or recorded as an override in DECISIONS.
- **DB-4, landed.** The branch lands on main through the merge authority in `~/Antiek/.infinite/COORDINATION-2026-09-25-glm-twin.md`, with the required checks green at the exact head. Never self-merge, admin-merge, arm auto-merge, batch update-branch, or merge into an unmerged stacked base.
- **DB-5, verified on prod.**
  - `build_sha` equals the merge SHA.
  - Read-only GET probes of the new routes and assets pass. Agents never POST, PUT or DELETE on prod.
  - The operator has completed the sprint's **walkthrough checklist** (each sprint below ends with one).
- **R9, the rev-9 gate.** A sprint marked **R9** consumes a seam that is new in rev 9 (S9–S23). It does not start its build until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT (agreed with lane B, 2026-09-27). Until then, its pure-UI parts may be prototyped against fixtures on a branch that does not merge. Sprints not marked R9 build on rev 7/8 seams now.

## 1. Dependency map

| Sprint | Lane A deps | Lane B deps | R9 | Blocked on a ruling? |
|---|---|---|---|---|
| A10 Rebase; doors outside the cycle; homes release keys | A0, A1 | — | no | no |
| A11 Key hierarchy and the keymap surface scope | A10, A2 | LB-2 (LB-17 for the `products[]` filter, feature-detected) | partly | no (ruling 9) |
| A12 Project-first homes and the move into the cockpit | A10, A11 | LB-2, LB-17, LB-14, LB-32 (feature-detected) | yes | no |
| A13 Create-a-project page | A11 | LB-17, LB-15 | yes | no (default 1) |
| A14 Output island in the right pane; nested lanes | A1, A3, A10 | LB-3, LB-19, LB-20 | yes | no (ruling 2, O-4) |
| A15 MergeFlow with draft review | A14 | LB-24a, LB-24, LB-25 (re-scoped by D-M), LB-26 for "into agent" | yes | no (D-M) |
| A16 Solo agent pane, fullscreen restore, persisted dialogue | A3, A6 | LB-2, LB-3, LB-21 | yes (S13) | no (ruling 19) |
| A17 Voice prompt everywhere | A10 | LB-12 (the `input` field, feature-detected), LB-23 | partly | no (default 8) |
| A18 Books | A4, A12, A13, A11 | LB-14, LB-17, LB-18, LB-21, LB-22, LB-32, F8 (lane B, number pending) | yes | no (rulings 1, 11, 12) |
| A19 Speak door | A10, A11 | LB-13, LB-15, LB-16, LB-34 | yes (S22) | no (rulings 4–6) |
| A20 Books Notebook tab | A18 | LB-29; LB-30 `companion_document` source for item 3 | yes | no (ruling 13) |
| A21 Transfers | A13, A18, A19 | LB-18 | yes | no (D-P) |
| A22 Converse | A16, A17 | LB-21, LB-23, LB-30, LB-31 | yes | no (rulings 7, 14–16) |
| A23 Cross-project agents and groups | A15, A16 | LB-26, LB-27 | yes | no (D-A, ruling 20) |
| A24 Autonomous Research door | A13, A23 | LB-10, LB-28, LB-32 | yes | **O-11** for the standing envelope; per-flag consent (D4) until then |

A10 and the pure-UI half of A11 can start as soon as A1 lands. A16's solo pane, A17's recorder, and A19's layout against fixtures can be prototyped before R9.

## 2. Register corrections applied here (from the critic)

- **R23-a** is EXTEND (lane A), not EXISTS. Doors drop the active project (`shortcuts.ts` door handlers @rescue), and Books, Converse and Autonomous have no doors. It is delivered by A11 (ruling 8: land on the home with the active project pre-focused; ruling 7: More and the prefix+shift+m picker).
- **R38-public** is "EXISTS behind a default-deny flag; not met in the default config". The flag is at `invitations.py:61-67@d61e5256d`; its prod value is UNVERIFIED. Its deltas are A19's designed locked state and LB-34's takedown predicate on `list_public_opportunities` (`substrate/speak/pushes.py:213-223@d61e5256d`).
- **R29** is split, and **R21c** becomes EXTEND to match R29-b:
  - R29-a, NEW: an agent's identity beyond one project (D-A: a promoted thread).
  - R29-b, EXTEND: many-to-many membership (`write_folder_members`, `folders.py:65-74@main`).
  - R29-c, EXTEND: budgeted context selection (`knowledge_reuse` select-within-budget; the assembler of D-A).
  - R29-d, NEW: evidence_index re-keyed to `(owner_user_id, evidence_id)`.
  - R29-e, NEW: an Agents group in the switcher.
- **R21-x** is dropped. It was the merge target "into agent", which is R21b. A15 cites R21b.
- **R36-truncation** belongs to lanes A and B. `scopeNarrationText` is client code (`apps/reading/src/api/tts.ts:135-139,246-250@main`), and removing its trim on monologue paths is an A22 item. `meta_reading._bound_to_budget` stays lane B's.
- **R30.** The two groundings disagreed: projects-transfers graded it NEW, and books graded it EXTEND, citing the contract's `kind: reading` and the rescue reading right pane. The synthesis chose NEW without saying so. The resolution: the interest project itself is NEW (`kind: interest`, `primary_document_id: null`, D-P), and the reading surface it opens into is EXTEND (A4 plus A18).
- **Conflicts list, corrected:**
  - C1 (Speak as a mode) against T11 (a door with no forest) is now **settled by ruling 4** (Speak gets its own two-pane door). This amends T11's "single surface" and is recorded in DECISIONS.
  - T8 ("agent tabs belong to the project") against cross-project agents is **settled by D-A**: the tab in project P holds P's session thread.
  - R26-c ("New piece" creates an unlinked piece, against ConnectResearch's "never an island") is **settled by default 1** (A13).
  - C3 against R25's "command F" (K-12) is **settled by default 7**.

## 3. The keymap surface scope (delivered in A11; A18, A19 and A22 depend on it)

VERIFIED: `KeymapScope` is only `"anywhere" | "outside-text"` (`apps/reading/src/components/hotkeys/keymap.ts:58@a123723a1`). Bare ←/→/space page keys, and the section keys that doors need, would hijack scrolling everywhere, and prefix+1..3 on a door would collide in `validateKeymap` with `tab.root` prefix+1..9.

**The delta.**
- A row may carry `surface?: "reader" | "speak" | "converse-player"`.
- **Effect:** a surface row fires only when the focused element is inside a node carrying the matching `data-key-surface`, and it never fires inside text.
- **Collision rule:** `validateKeymap` allows two rows on one chord only when their surfaces are disjoint, where a row with no surface is "everywhere except surfaces that shadow it". A surface row shadows a global row only when that global row is listed in the surface's `shadows[]`.
- **Doors:** tab-tree actions are inert on doors (A10), so Speak's prefix+1..3 shadow `tab.root` 1..3 inside `speak`, and nowhere else.

**Tests.**
- A duplicate chord across two overlapping surfaces fails validation.
- A shadowed global row does not fire inside its surface and fires outside it.
- Space inside the reader turns the page, and in a Research agent tab it scrolls.

## 4. Sprints

### A10 · Rebase onto main; doors outside the cycle; homes stop swallowing keys

**Requirements.** R22-c (Speak, Home and admin sit outside the mode chrome), R24-f, and the prerequisite for R18 and R40.

**Depends on.** A0 (the MS-01 carrier on main) and A1 (the D6/C5 rescue, A1b rounds closed). Not R9.

**Done-bar.**
1. The rescue lineage contains main at or after `d61e5256d`, so `island/ThreadIsland.tsx` and the island stack exist on the branch. `App.tsx` keeps main's lazy routes, and the entry chunk is within budget.
2. `mothershipForPath` returns null on `/`, `/home`, `/speak`, `/speak/*`, `/operator` and `/settings`, and on `/converse` and `/autonomous` once those routes exist.
   - Vitest shows that no `DocumentTabStrip` or `CompanionPane` is mounted there.
   - n/p/u/o/shift+x change no tree on `/speak`.
3. No home autofocuses a text field.
   - On `/`, prefix then `?` opens the key sheet on arrival. This asserts an existing row, which avoids the critic's A10↔A11 circularity.
   - The first printable key other than `?` focuses the composer and is typed into it.
   - Esc from the composer blurs to the page.
4. `ReadingCompanion` renders no source-merge preview or "rewrite source" control (T6: nothing writes into a source), asserted by a test.
   - "Restore the original" appears only on a document with a source-merge receipt, because lane B keeps `restore` live until the operator confirms none remain on prod.
   - The client callers of the retired routes (preview, apply, commit) are removed in the same PR as lane B's LB-33, or before it.

**Walkthrough (operator).**
1. Open antiek.ai. Nothing is focused. Press the prefix, then `?`: the key sheet opens.
2. Close it and type a letter: the composer takes focus with the letter in it. Press Esc: the page has focus again.
3. Open Speak: there is no tab strip or agent pane, and the tab keys do nothing.
4. Open a book: there is no "rewrite source" control anywhere.

### A11 · Key hierarchy: product, project and cockpit rows in the one table

**Requirements.** R23-a (EXTEND), R23-b, R24-c, R24-d, R24-e (ruling 9: tabs keep the digits, amending D2) and R26-a (ruling 9).

**Depends on.** A10 and A2 (the project layer bound to §1.5/§1.6), and LB-2 (`GET /projects`, `project_tabs`). The `products[]` filter uses LB-17 when it is present (feature-detected; R9). Everything else is on rev 7.

**Done-bar.**
1. The §3 surface scope, with its `validateKeymap` tests.
2. New rows, each with a prefix binding, and a ctrl+alt twin where a direct chord is safe. The reserved entries each row replaces (`RESERVED_FOR_LATER` in `apps/reading/src/components/hotkeys/keymap.ts@d2d8d43e7`) are removed.

   | Action | Keys |
   |---|---|
   | `mode.cycle` | prefix+m, ctrl+alt+m |
   | `mode.pick` | prefix+shift+m |
   | `project.list` | prefix+w, ctrl+alt+w |
   | `project.new` | prefix+shift+n, ctrl+alt+n |
   | `tab.root` 1..9 | prefix+1..9, ctrl+alt+1..9 |

3. **`mode.cycle`** keeps the project id and restores that mode's active `{left, right}` from the tab adapter. It cycles only the modes in the project's `products[]` (D-P); when `products[]` is absent, it cycles all three.
   - For a mode the project isn't in, `mode.pick` offers "Open in Writing — transfers the whole project (no model spend)" as an explicit action (A21), never a silent append.
4. **The door keys** ⌘J/E/Y/U land on the product home with the active project pre-focused, so Enter goes into its cockpit (ruling 8). Converse and Autonomous have no ⌘ door. They appear in More (⌘I) and in the `mode.pick` list, with digit accelerators (ruling 7).
5. **The `project.list` overlay** has one row per project (D-P), with mode badges from `products[]` and linked projects indented under their source.
   - Keys: digits, or j/k then Enter, open the project's cockpit. It opens in the current mode when the project is present there, otherwise in `last_mode`, otherwise in `home_product`; from a door outside the cycle it uses `last_mode`, else `home_product` (DECISIONS, 2026-09-27).
   - Esc restores focus to the invoking element.
6. **Scope of the right pane.** The right pane lists the agents attached to the active left tab, with an "All agents" chip (R24-d).
7. **The key sheet** renders Product, Project and Cockpit sections generated from the table, and every control's `aria-keyshortcuts` is generated from the same rows. It labels `pane.fullscreen` (prefix+f / ctrl+alt+f) as the "Command-F" of R25 (default 7).
8. DESIGN-MODEL's key table and D2 record the ruling-9 amendment.

**Walkthrough.**
1. In a project, press the prefix then `m`: the mode changes, the project stays, and the tabs you had in that mode come back.
2. Press the prefix then `w`: the project list appears. Pick one with a digit: its cockpit opens.
3. Press ⌘E: the Books home opens with your project highlighted. Press Enter: you are in its cockpit.
4. Press the prefix then `3`: the third tab opens.
5. Open the key sheet: it has three sections.

### A12 · Project-first product homes with a shared-element move into the cockpit

**Requirements.** R22-a and R22-b (including the right-pane product layer per home).

**Depends on.** A10, A11, LB-2, LB-17 (`?product=` presence, `last_mode`, `shelf_count`), LB-14 (the Books continue row) and LB-32 (To read, feature-detected). R9.

**Done-bar.**
1. The Research, Writing, Books and Home pages share one anatomy:
   - a continue row, with the active project pre-focused, where Enter launches its cockpit in `last_mode`;
   - a project list by **presence** (`GET /projects?product=`, never `home_product`, per D-P), with mode badges and linked projects indented;
   - nullable counts rendered `—` plus a reason;
   - a one-line create that opens `/new?product=` (A13).
2. **The right-pane product layer**, which the critic found missing:
   - Research: running threads, with state and spend (`—` when unknown).
   - Writing: the focused project's outline.
   - Books: To read, the read flags from `GET /flags?intent=read` (LB-32), feature-detected. Until the route exists, it shows "To read isn't available yet" rather than an empty list.
   - Speak's detail is A19's.
3. **States:** loading, empty, error with retry, partial and offline.
   - `WriteHome` no longer swallows a list error, asserted by a test.
   - The inset layout is the default at md and up (C2).
4. **The launch move.** Launching turns the focused row into tab 1.
   - It is a shared-element move of at most 200 ms on the `--motion` token, and an instant swap under reduced motion.
   - It causes no layout shift (asserted at the DB-1 widths).
   - `/deep-research` seeds a research tab.

**Walkthrough.**
1. Open the Research home: your recent project is highlighted and its running threads are on the right.
2. Press Enter: the row becomes the first tab without a jump.
3. Repeat with "Reduce motion" on: the swap is instant.
4. Open the Writing and Books homes: they have the same layout, with the outline and To read on the right.

### A13 · Create-a-project page: one create path per product

**Requirements.** R26-b, R26-c (default 1), R27-Research, R27-Writing, R27-Books, R27-Speak (link out) and R27-Autonomous (disabled state).

**Depends on.** A11, LB-17 (`POST /projects` and the seed union) and LB-15 (owner binding). R9.

**Done-bar.**
1. **Where it opens.** A lazy route `/new?product=` opens from `project.new` and from every SceneChrome primary, including "New piece", which no longer creates an unlinked piece (R26-c; tested).
2. **The product control** covers Research, Writing and Books (data values `research | writing | reading`, per D-P with ruling 1's names), and defaults to the product you came from.
   - Speak links to the Speak door's own create, because a Speak request is not a registry project (ruling 4).
   - Autonomous shows a disabled state with the reason "Spawning is off until consent lands" (D-P tightening 1).
3. **The body** mounts each product's existing composer, never a reimplementation:
   - Research: a question, which is **stored, not launched**, followed by a costed "Start research" step.
   - Writing: a blank piece labelled "No research yet", with a costed "Start research" offer (default 1).
   - Books: a book, or an interest with a title and optional prompt.
4. **Submit.**
   - It sends `POST /projects {home_product, kind, title?, seed, idempotency_key}`, with one key per page mount.
   - It follows `next` into the cockpit, with the new surface as tab 1.
   - A double press yields one project, asserted by a test.
5. **States:**
   - idle, submitting and offline;
   - error, which keeps the input;
   - 422 `seed_invalid`, which shows its reason next to the field;
   - 409 `idempotency_conflict`, which reloads the project.

   Esc returns focus to the invoker.

**Walkthrough.**
1. Press the prefix then shift+n from Writing: the create page opens on Writing.
2. Name a piece and submit: you land in its cockpit, it says "No research yet", and nothing was charged.
3. Switch the control to Books and pick a book: its reader opens as tab 1.
4. Click Autonomous: it explains why it is off.

### A14 · Output island in the right pane: read, select, chase or harden; nested agent lanes

**Requirements.** R18 and R19. Ruling 3 puts research-thread output first; dialogue replies follow. (A14's right-tree ids `agent:thread:<id>` serve R25-d, which A16 closes.)

**Depends on.** A1, A3 (the resizable right pane) and A10; LB-3, LB-19 (segments, anchors and the shared offset fixture) and LB-20 (branch from output, purposes, lanes). R9 (S9, S10).

**Done-bar.**
1. **Rendering.** The agent tab renders `GET /investigations/{id}/outputs` segments with exactly `content.text`. The shared NFC offset fixture passes on both sides.
2. **Selection.** `useFloatMenuSelection` is scoped to agent output, and a selection resolves to `output_anchor {segment_id, offsets, sha}`.
   - A withheld segment disables selection and shows the reason (the `422 output_not_servable` copy).
3. **The island.** prefix+a / ctrl+alt+a (row `island.open`, replacing the reserved `a`) opens the §2.3 island states:
   - estimating: an estimate, or `—` with its reason and an explicit confirm when the run is unpriced;
   - running, answered and kept;
   - promoted, which becomes a child right tab.
4. **Four verbs**, each with its own cost line (ruling 2, O-4):
   - Ask: a dialogue child, tier 0.
   - Harden: research, with purpose `harden`.
   - Chase: research, with purpose `chase`.
   - Flag for diligence: the consented, capped background form.
5. **Agent tabs live in the server tree**, with `side: right`, `parent_tab_id` pointing at the parent agent tab, and ids `agent:thread:<id>`.
   - A sub-sub-agent nests as a child, and n/p/u/o work on the right tree.
   - prefix+u scrolls to the segment and offsets.
   - The `localStorage` lineage (`useInvestigationTree.ts`) is deleted.
6. **The lane view** (`?parent_thread_id=`) lists children with purpose labels, and shows "passage withheld" when `quote_state` is withheld. Each lane shows its §2.4 state, and an unknown is never shown as 0.
7. **Focus** returns to the source span when the island closes.

**Walkthrough.**
1. Open an agent tab with a finished research, select a sentence, then press the prefix and `a`: four actions appear, each with its cost.
2. Pick Harden: a child tab appears under the agent on the right.
3. Press the prefix then `u`: you are back at the highlighted sentence.
4. Try to select a held-back passage: it says why you can't.

### A15 · MergeFlow with draft review in the pane

**Requirements.** R20, R21b ("accept into agent") and the UI half of R20-C1 (retiring the compose page). The shape follows D-M.

**Depends on.** A14, LB-24a (the §1.10 base), LB-24, and LB-25 as re-scoped by D-M. "Accept into agent" additionally needs LB-26; until then it is disabled with its reason (`422 target_unavailable`). R9.

**Done-bar.**
1. **A lazy `MergeFlow`** in the pane, never a new browser tab, with these states:

   | Group | States |
   |---|---|
   | Path | selecting → previewing → conflicts_shown → framing → estimating → drafting → draft_review → merging → merged |
   | Off-path | preview_stale, draft_stale, draft_failed, refused_capped, failed, suggestion |

   Selecting and merging use prefix-only rows.
2. **The preview.** It orders detected contradictions first, side by side and never averaged. Then items by source document, then by origin thread.
   - Every item shows its origin chip, gate and pointers.
   - The header carries the §2.10 counts.
   - The conflicts heading says the detector is structural, so zero never reads as "no conflicts".
3. **framing** requires a question. **estimating** shows `{estimate_cents | null, max_cents, model}` with the cap copy "Starts if $X of today's cap is free; it pauses if the cap runs out". An unknown price needs an explicit confirm.
4. **drafting** can be cancelled. **draft_failed** shows its reason, and Retry replays the same key without new spend.
5. **draft_review** shows:
   - the synthesis in T7's chosen presentation;
   - per-claim origin chips;
   - the claims list;
   - a collapsible "What the model was not shown".

   Its actions:
   - Accept as new thread (the default);
   - Accept into agent…, where the common parent is only preselected;
   - Edit draft, which marks operator-origin sentences;
   - Edit question and redraft, with a new estimate;
   - Discard.
6. **draft_stale** names what changed and offers Redraft. **preview_stale** re-previews while keeping the selection and the question. Neither ever regenerates silently.
7. **merged** appears only after the server confirms the merged thread's start event. Until then members read "Merging into …", and they read "Merge didn't complete" on `merge_failed`.
8. **Entry points.** ReadingCompanion's Saved chases and ArtifactOutlineShelf's "Draft merge" route to `selecting`, and the `target="_blank"` compose page is removed.
9. **Playwright paths:**
   - select → preview → frame → estimate → draft → review → accept lands a merged tab;
   - a second path asserts that Accept is disabled, with its reason, on a withheld draft and on a cap refusal.

**Walkthrough.**
1. Select two agent tabs and start a merge: a free side-by-side appears first.
2. Type a question: the estimate appears. Generate: the draft appears.
3. Edit one sentence: it is marked as yours.
4. Accept: a merged tab opens, and its first answer is exactly the draft you accepted.

### A16 · Agent-first solo pane, fullscreen restore, persisted dialogue

**Requirements.** R25-a, R25-b, R25-c, R25-d and R25-f. Ruling 19: solo is transient by key, at half the cockpit width with a 480 px minimum.

**Depends on.** A3 and A6; LB-2, whose tab PUT already accepts origin `agent` with a required `opened_by` (`BranchOriginKind` and `OpenedBy` in #3530's `apps/reading/src/lib/api/projectTabs.ts@c26773191`, answering `422 tab_origin_invalid` without it); LB-3 and LB-21 (one session per agent and project). R9 (S13); the solo pane itself is not. `transient` is rev 9 and belongs to A18, not here.

**Done-bar.**
1. **The state** is `soloPane: 'right' | null`, not a third preset. The right pane renders at `max(50% of the cockpit, 480px)` from a token, with the scene visible on the left.
2. **The key** is `pane.solo`: prefix+s / ctrl+alt+s. Both are free at `d2d8d43e7` and collision-checked.
3. **Fullscreen and Esc.**
   - solo → f → fullscreen → f or Esc → solo (tested).
   - prefix+h from solo reveals the left pane and exits solo.
   - Esc outside fullscreen exits solo.
4. **Dialogue tabs.** A dialogue tab is the (agent, project) session thread view, `agent:thread:<session_id>`. Its turns survive a tab hop, a reload and a device change (e2e against LB-21). Each turn shows its context receipt (D-A).
5. **Opening a document.** An agent reply's `source_ref` opens a left child tab with origin `agent`, `opened_by` and `anchor`, which reveals the left pane from solo or fullscreen. prefix+u returns to the passage.
6. **States:** no agent, loading, queued, running, failed, idle and offline.
7. **The one-shot fallback** appears only when the dialogue route is absent, by feature detection.

**Walkthrough.**
1. Press the prefix then `s`: the agent pane fills half the screen. Press `f`: it goes fullscreen. Press Esc: it goes back to half.
2. Ask it something and reload: the conversation is still there.
3. Click a source in its answer: the document opens on the left at that passage.

### A17 · Voice prompt in every composer

**Requirements.** R34 and R35-voice-out.

**Depends on.** A10; LB-12 for the `input` field (feature-detected, since `/voice/transcribe` works today) and LB-23 for settlements (not blocking).

**Done-bar.**
1. **One hook and one button.** `useVoiceInput` and `VoiceInputButton`, built on `useVoiceCapture`, are mounted in AISidecar, TalkToBook, ThoughtPartnerPanel, the cockpit agent composer, the island Ask composer, the reformat composer, MidnightOil and the Speak owner composer.
2. **When voice sends** (lane-A default 8, below):
   - In a composer that starts paid work (a research launch, reformat, or a merge question), voice fills an **editable draft** and never auto-sends.
   - In a conversational surface (a dialogue ask, or a Converse turn), the transcript shows and sends after a visible 1.5 s grace window. Enter sends at once, and Esc keeps it in the field for editing. It is then shown with the turn. This makes it ruling 17's confirmed transcript.
   - Launches carry `input {modality: voice, …}`.
3. **Consolidation.** `VoiceChaseButton`, `VoiceNote` and `VoiceSteeringInput` are migrated. The duplicate transcribe clients in `lib/api.ts` and `api/books.ts` are deleted, and a grep shows 0 callers.
4. **Keys and retention.** `voice.toggle` is prefix+v / ctrl+alt+v. Esc discards the recording. No audio is kept anywhere (ruling 17).
5. **States:**
   - idle;
   - recording, with elapsed time and a level meter that is safe under reduced motion;
   - transcribing and draft ready;
   - mic denied;
   - unavailable (503);
   - too long (413);
   - silent (400 `empty_audio`).
6. **Retirement.** `useSpeech` is retired from the ReadAloud paths.

**Walkthrough.**
1. In the Research composer, press the prefix then `v` and speak a question: the text appears, editable, and nothing starts until you press Enter.
2. In an agent conversation, send a voice note: it sends when you stop.
3. Deny the microphone once: it says so plainly.

### A18 · Books: label rename, book-first home, interest projects, detours

**Requirements.** R31a (ruling 1), R31b (warmth), R31c, R30 (ruling 12) and R33 (ruling 11, D-P tightening 2).

**Depends on.** A4, A11 (the `reader` surface), A12 and A13; LB-14, LB-17, LB-18, LB-21 (a book-scoped session for TalkToBook as a right-pane dialogue tab), LB-22, LB-32 (To read, feature-detected) and lane B's F8 package (non-book reader serving; number pending). R9.

**Done-bar.**
1. **The rename, checked by grep.**
   - No user-facing string in `apps/reading/src` names the product "Reading" or "Read"; verbs are allowlisted.
   - Code keys and routes are unchanged: `read`, `/library` and `/read/:id`. The mode key stays `reading` (ruling 1, reconciled 2026-09-27 in DECISIONS). "Books" is a label only.
   - `/books` redirects as a brand alias. ⌘E stays; ⌘B stays unbound as a door.
   - The TipTap "Notebooks" are relabelled "My notes" (O-14), so they don't collide with the Books Notebook tab (A20).
2. **The Books home.**
   - Continue (LB-14; unknown progress shows `—`), To read, New (a book or an interest), Your books, and From a research project (the R33 link).
   - Each section has designed states.
3. **"New interest"** creates a `kind: interest` project.
   - The left pane seeds root reader tabs in member order.
   - Keyboard reorder sends a shelf PUT with `expected_version`, and a 409 refetches.
   - Non-book assets are marked (ruling 12).
4. **Page keys.** ←/→/space are rows on the `reader` surface, and they never hijack scrolling elsewhere (tested).
5. **One companion.** The in-reader ReadingCompanion column is removed. TalkToBook becomes a right-pane dialogue tab on a book-scoped session, and its answer refs open left tabs (S18).
6. **The Books lens.**
   - The left pane admits reader and document tabs, with shelf members first.
   - A thread off the shelf is hidden in Books and visible in Research (a fixture test).
   - A whole transfer into Books lands on a "Which book(s)?" seed step, never an empty pane.
7. **Non-book documents (consuming LB-35; spec `cockpit/LB-35-SPEC-2026-09-27.md` §3).**
   - One `getBook` 404 no longer fails the whole open in `Reading/index.tsx`'s `Promise.all`; each part degrades on its own.
   - A non-book (`is_book: false`) carries a marker ("Article", "Paper", "Web page", from `document_type`) and the ToC empty state ("No chapters in this document"). Its progress is `—`, because it has no page count.
   - TalkToBook is hidden when `registered` is false.
   - `403 book_taken_down` renders the §2.10 withheld state.
   - **Ad rails stay off** for `is_book: false` until the operator rules (LB-35 Q1). The backend's `ad_eligible == servable` would otherwise put house ads and impression accrual on web pages and papers.
8. **Detours.** A detour is a child of the book with a depth chip, and prefix+u returns to the anchor. Until F8 lands, a detour or answer ref into a non-book asset opens as a document tab reading "Opens outside the reader for now", never a failed reader.
9. **Warmth** (R31b, which the critic found missing):
   - a reader measure of 60–72ch inside the pane at every DB-1 width of 900 and up, asserted on geometry;
   - day, night and paper themes;
   - visible progress, "page n of m", or `—` with its reason.

**Walkthrough.**
1. Open Books: the heading and rail say Books, and your current book is first.
2. Start an interest called "Airplanes" and add two books: they open as tabs in that order.
3. Turn pages with the arrow keys.
4. Ask the book a question on the right, then open a cited passage: it opens on the left.
5. Follow a footnote and press the prefix then `u`: you are back.

### A19 · Speak door: three sections left, detail right

**Requirements.** R38 (the UI half), R38-public, R39-projects, R39-invites, R39-public, R40-left, R40-right, R40-keys and R40-states. Rulings 4, 5 and 6 apply, plus default 5.

**Depends on.** A10 and A11 (the `speak` surface); LB-13 (arrivals and unconfirmed answers), LB-15, LB-16 and LB-34. R9 (S22).

**Done-bar.**
1. **Sections.** My projects, Invites and Public replace the Yours/Public/Pushes tablist, with counts from `GET /speak/sections` (null shows `—`).
   - Pushes is deleted: re-ping moves into the project detail, and the ranked list moves to Public with a Newest toggle.
2. **The detail pane.** `SpeakDetailPane` has three kinds (project, invite, public), keyed by `/speak/:projectId`, `/speak/invites/:id` and `/speak/public/:id`. There is no tab forest or agent pane.
3. **Invites** is the designed locked state (ruling 5): "Requests from other people arrive when sharing opens." Invite links you opened while signed in may be saved, labelled as bookmarks.
4. **Copy.** Requests are reframed as insight requests through `speakVocab`, with biography as one template (ruling 6). The gate-honesty and copy-lint tests pass.
5. **Keys.** prefix+1..3 select sections on the `speak` surface, and n/p and ↑/↓ move within the list. Tree actions are inert.
6. **Unconfirmed answers.** An unconfirmed invitee answer is marked "Unconfirmed transcript", with Confirm in the detail (LB-13 item 2).
7. **Public**, while open contribution is default-deny, lists requests and shows contribution as the designed locked state (R38-public).
8. **States:** loading, empty, error, busy (`503 speak_writer_busy`), gated (G7) and no selection. Below 768 px it collapses to one pane, and h/l swap between the panes.

**Walkthrough.**
1. Open Speak: there are three sections on the left and details on the right.
2. Pick a request: its invites, answers and re-ping are on the right.
3. Press the prefix then `3`: Public opens.
4. Open Invites: it explains honestly that it is locked for now.

### A20 · Books Notebook tab

**Requirements.** R32. Ruling 13: v1 spends nothing, and narrative prose is opt-in. Default 2 applies.

**Depends on.** A18 and LB-29; for item 3, lane B's §1.11a `companion_document` source (an LB-30 extension). R9 (S17).

**Done-bar.**
1. **Where it lives.** A Notebook right-tab kind in Books, reachable through n/p and the prefix+c picker (no new letter).
2. **Contents.**
   - Synthesis, insights, open questions and "Where the agents went", grouped by chapter when the book has a TOC.
   - Every entry is one click from its process (`anchors[]` open a left tab at the anchor).
3. **"Write it up as prose"** is an opt-in action under consent and the cap, with the estimate shown first. Until the `companion_document` source exists, the action is disabled and reads "Prose write-ups aren't available yet".
4. **States:** loading, empty-after-answer, stale with Refresh, refreshing, partial "n of m", `unavailable_until_rights` and error.
5. **Also:** it can open as a left tab and go fullscreen. "Import outline into Write" is kept.

**Walkthrough.**
1. After asking a book two questions, open the Notebook tab: both answers' insights are there, and each links back.
2. Nothing was charged.
3. Press "Write it up": it shows the cost first.

### A21 · Transfer actions across products

**Requirements.** R28, across these pairs:
- Research → Writing, whole and partial;
- Speak → Writing;
- Research → Books;
- Books → Research ("turn this book into a new project").

Research → Autonomous is A24's. The shape follows D-P.

**Depends on.** A13, A18, A19 and LB-18. R9 (S16).

**Done-bar.**
1. **The dialog.** Whole or Partial. Partial shows:
   - the candidate list, with each item's gate;
   - a preview of the target member set;
   - the target picker: a new linked project, or an existing project in that product.

   Unsupported pairs are never shown, and a 422 `transfer_not_supported` is unreachable from the UI (tested).
2. **Keymap rows and palette twins.**
   - "Open in Writing — transfers the whole project (no model spend)"
   - "Send part to Writing…"
   - "Deep read in Books"
   - Speak's "Send to Writing", labelled as creating or reusing a Writing project **from this request** (D-P). It uses a Speak-side route, not `/projects/{id}/transfers`, because a Speak request is not a registry project (ruling 4).
3. **Linked projects** carry a lineage chip, "derived from <source> · n members · <date>", plus "Re-transfer from source" and an honest "n new since transfer" (a client-side diff of `transfer-candidates` against the linked project's members; `—` with its reason when either read fails). Nothing re-syncs silently.
4. **Leaving and archiving.** "Leave <mode>" is separate from "Archive project", and the last remaining product cannot be left.
5. **States:**
   - promoting, insufficient_evidence, no_synthesis, and failed with retry;
   - for the picker: loading, empty and error;
   - `422 speak_publish_required` on share or export, shown as "Publish through Speak first".

**Walkthrough.**
1. From a research project, pick "Open in Writing": the same project opens in Writing, and your research is intact.
2. Pick "Send part to Writing" and choose two threads: a new linked piece holds only those.
3. From Speak, send a request to Writing: it says it creates a Writing project from the request.

### A22 · Converse door, session and monologue player

**Requirements.** R35, R35-speak-scope (ruling 16: excluded), R36, R37, R22-d (Converse home), R23-c (ruling 7) and R36-truncation (the lane-A half). Rulings 14 and 15 apply, plus default 3.

**Depends on.** A16 and A17; LB-21, LB-23, LB-30 and LB-31. R9 (S13, S21).

**Done-bar.**
1. **The home.** A lazy Converse home lists registry projects by presence, grouped Research / Writing / Books (no Speak), with "Talk" and "Explain in N minutes" (1–120) on each, plus past sessions (`?kind=dialogue&project_id=`).
2. **The door.** It is reached through More (⌘I) and the `mode.pick` list, outside the mode cycle, with no forest.
3. **The session** runs in the solo pane: text and turn-by-turn voice notes (A17 conversational rule), and an optional spoken reply per session.
4. **The monologue composer** shows the consent line: the estimate, the cap remaining, and the model. An unpriced run needs an explicit confirm.
5. **The player** hosts ActiveListeningPlayer in the pane, with the text alongside the audio (ruling 15). Its states:
   - generating (chapter n), synthesising N of M, and ready;
   - **shortfall**: "This project holds about 12 minutes for the 30 you asked for", with an offer to research. It never pads and never cuts.
   - refused_capped, failed and interrupted.
6. **Interjections.** Typing or a voice note during playback pauses it and offers "Resume at mm:ss". The interjection is marked in the transcript, and the ask carries `at {derived_asset_id, revision_id, span_id, offset_seconds}`.
7. **Player keys** are rows on the `converse-player` surface: space plays or pauses; ← and → move 15 s back or forward; shift+← and shift+→ go to the previous or next chapter. They share chords with the `reader` surface, which is allowed because the surfaces are disjoint (§3).
8. **R36-truncation.** `scopeNarrationText`'s trim (`apps/reading/src/api/tts.ts:135-139,246-250@main`) is removed on monologue paths. A test shows a 30-minute script reaching the player untruncated.
9. **Position** persists through `reading_state` on `drv-<gen>`; a 409 refetches and rebases.

**Walkthrough.**
1. Open Converse from More, pick a project and press Talk. Say something: it answers, and the conversation stays on reload.
2. Ask for "Explain in 10 minutes": it shows the cost first, then plays with the text beside it.
3. Interrupt with a question: it pauses and offers to resume where it stopped.

### A23 · Cross-project agents and agent groups in the UI

**Requirements.** R21a (the "what the agents see" link: A23(3)'s "Knows: …"), R21c (EXTEND), R29-a, R29-b, R29-c, R29-e and R25-e. D-A and ruling 20 apply. R29-d, the evidence_index re-key to `(owner_user_id, evidence_id)`, is lane B's (an LB-26 delta per D-A); A23(4)'s refs-only cross-project attach is its consuming test.

**Depends on.** A15, A16, LB-26 and LB-27. R9 (S12, S13).

**Done-bar.**
1. **The Agents group** in the switcher (`GET /investigations?agent=true`) shows each agent's title, project chips, state, last activity, and spend (`—` when unknown).
2. **"+ new agent"** offers:
   - "New agent…", which creates a dialogue thread and promotes it with a charter;
   - "Call an agent from another project…", which writes membership and opens or creates this project's session. A 403 or `422 project_shared` refusal shows its reason.
3. **The tab header** shows:
   - the charter title;
   - a home-project badge when this project isn't home;
   - the reach chip "Attached only";
   - "Knows: n threads · m merges", each item one click from its process.
4. **Attach.**
   - "Attach to agent…" is one keystroke from a left selection or a reply (an `island.open` target).
   - A withheld item is refused visibly. A cite_only item attaches as refs-only, with that label.
5. **The charter form** uses CAS: a 409 `revision_moved` shows "changed elsewhere" and rebases. The revision list is viewable.
6. **The group pane.**
   - 2–4 participants, drawn from the Agents list.
   - One synthesising voice, with per-sentence attribution chips (glyph plus name, AA in both themes).
   - A per-round bound is shown before sending.
   - The `partial` and "participant withheld" states.
7. **Remaining states:** loading, empty ("This agent knows nothing yet: attach or merge to teach it"), error, offline, refused, stale and withheld.

**Walkthrough.**
1. Promote an agent in project A. In project B, pick "Call an agent from another project": it joins B with its own conversation.
2. The header says what it knows, and each item opens its source.
3. Start a group of two agents: one answer comes back, with each sentence showing who said it.

### A24 · Autonomous Research door and hand-off

**Requirements.** R22-d (Autonomous home), R27-Autonomous and R28 Research → Autonomous. Ruling 10 and D-P tightening 1 apply.

**Depends on.** A13 and A23; LB-10, LB-28 and LB-32 (flags). The roster read carries `spawning_enabled` and `spawning_reason` (agreed with lane B). R9 (S23).

**Operator gate.** The standing envelope in item 4 is lane B's O-11, an exception to D4 that needs the operator's ruling. Until he rules, "Manage autonomously" uses per-flag consent under D4: each continuation is a consented flag, and nothing standing is written (DECISIONS, 2026-09-27).

**Done-bar.**
1. **The door.** A lazy door outside the mode cycle, reached through More and the `mode.pick` list. It has no "New autonomous project".
2. **The roster** lists managed agents grouped by home project, with each one's envelope state (live, expired, revoked or none), `max_cents`, `expires_at`, and spend (`—` when unknown).
3. **When spawning is disabled,** a persistent banner reads "Nothing will run while spawning is disabled", and the controls that would start work say why they are off.
4. **"Manage autonomously"** acts on agent tabs selected in a research project.
   - It opens a consent sheet with the estimate and the copy "Starts if $X of today's cap is free; it pauses if the cap runs out", and writes one envelope.
   - The envelope is validated through the reused Midnight Oil preflight.
   - Revoke is one key.
5. **Threads** stay openable as right tabs in their origin project.

**Walkthrough.**
1. Open Autonomous from More: it lists your managed agents, or says there are none.
2. While spawning is off, it says nothing will run.
3. From a research project, pick "Manage autonomously" on an agent: the consent sheet names the cost and the cap.

## 5. Contract rev 9, Part 2 (lane A's half): sections to draft

- **§2.1** accepts `home_product`, `products[]` and `kind` (D-P). Homes read presence.
- **§2.2** accepts `output_anchor` and `transient`. The mode key stays `reading` (ruling 1).
- **§2.3** accepts `output_anchor` wherever `anchor` is required.
- **§2.5 MergeFlow** takes the D-M states listed in A15.
- **§2.12** Create page (A13).
- **§2.13** Agent-first pane and sessions (A16, D-A).
- **§2.14** Converse (A22).
- **§2.15** Speak door (A19).
- **§2.16** Autonomous door (A24). This section is new; the critic found no Part 2 home for it.
- **§2.17** Keymap surfaces (§3).
- **§2.18** Transfers (A21).
- **§2.19** Books (A18, A20).

Every citation follows the rev-9 rule: `path@<commit>` plus a quoted anchor.

## 6. Lane-A default added by this plan (operator may overturn)

**8. When voice sends.**
- In a composer that starts paid work, voice fills an editable draft and never sends by itself.
- In a conversational surface (a dialogue ask or a Converse turn), a voice note sends when recording stops, with its transcript shown alongside it.

This reconciles lane B's O-17 ("voice asks send automatically") with consent before spend. It is recorded in DECISIONS alongside defaults 1–7.

## 7. What each sprint proves at the end (mission accounting)

The mission is done when all five DB parts hold for every requirement. Each requirement row R18–R40 names exactly one sprint that closes its lane-A half:

| Sprint | Requirement rows it closes |
|---|---|
| A10 | R22-c, R24-f |
| A11 | R23-a, R23-b, R24-c, R24-d, R24-e, R26-a |
| A12 | R22-a, R22-b |
| A13 | R26-b, R26-c, R27-Research, R27-Writing, R27-Books, R27-Speak |
| A14 | R18, R19 |
| A15 | R20, R21b |
| A16 | R25-a, R25-b, R25-c, R25-d, R25-f |
| A17 | R34, R35-voice-out |
| A18 | R30, R31a, R31b, R31c, R33 |
| A19 | R38, R38-public, R39-*, R40-* |
| A20 | R32 |
| A21 | R28 (all pairs except → Autonomous) |
| A22 | R35, R35-speak-scope, R36, R36-truncation, R37, R22-d (Converse), R23-c |
| A23 | R21a, R21c, R29-a, R29-b, R29-c, R29-e, R25-e |
| A24 | R22-d (Autonomous), R27-Autonomous, R28 → Autonomous |

Three rows have no lane-A sprint:
- **R24-a** is lane B (LB-2), bound in A2 and A11.
- **R24-b** is ruling 21 (close #3517).
- **R27-model** is D-P.
- **R29-d** is lane B's (the evidence_index re-key, an LB-26 delta per D-A), consumed by A23(4).
- **R33-C** is ruling 11 and D-P tightening 2.

R17 stays a recorded note (ruling 18). R20-C1 and R32-C close with A10(4) and LB-33.

## 8. Asks of lane B (all agreed, 2026-09-27)

1. **The roster read.** The Autonomous roster read (S23) carries `spawning_enabled: bool` and `spawning_reason: consent_route_absent | env_refused | cap_exhausted | enabled`, so A24(3) never infers it. Agreed.
2. **The LB-33 retirement body** is `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}`, naming the T6 flows, never a route string. Agreed. The UI copy for a retired call reads "Reformulations never change the source; adopt one as your reading version instead."
3. **F8, non-book reader serving,** is a lane-B package (number pending). A18 depends on it.
4. **The evidence_index re-key** to `(owner_user_id, evidence_id)` (R29-d) is an LB-26 delta per D-A.
5. **A §1.11a `companion_document` source** for the notebook's prose write-up (an LB-30 extension). A20(3) depends on it.

GLM plan review (2026-09-27, `glmf-codex`, ACCEPT_WITH_FIXES, 13 findings): 11 applied. Two were declined with evidence:
- **Finding 7:** LB-2 already accepts origin `agent` with a required `opened_by` (#3530 `projectTabs.ts@c26773191`).
- **Finding 13:** `spawning_enabled` was agreed after the reviewed copy was made.

## 9. Critic corrections: disposition

| # | Correction | Disposition |
|---|---|---|
| 1 | No owner for the §1.10 base or RightsGatedPack | **Lane B, LB-24a** (agreed 2026-09-27). A15 depends on it. |
| 2 | No owner for the unified flags route | **Lane B, LB-32.** A24 depends on it. |
| 3 | No rev-9 contract sprint | **Agreed gate R9**, binding on both lanes (§0). Part 2 sections are listed in §5. |
| 4 | Ruling authority mis-stated | Re-framed in §2. C1 against T11 is settled by ruling 4, T8 against cross-project agents by D-A, and inset-opt-in follows C2 (the inset is the default). |
| 5 | R23-a is EXTEND | Applied (§2, A11). |
| 6 | R38-public is gated off | Applied (§2, A19(7), LB-34). |
| 7 | R29 collapsed; R21c inconsistent | Applied (§2, A23). |
| 8 | R21-x unregistered | Re-pointed to R21b (§2, A15). |
| 9 | R36-truncation in the wrong lane | Applied: lanes A and B, closed by A22(8). |
| 10 | My LB-13 incomplete, overlapping LB-2 | Superseded by lane B's LB-17 (a delta on LB-2), plus D-P's corrections, which were sent to lane B. |
| 11 | Dependency gaps | (a) A16 depends on LB-2, which already accepts origin `agent` with `opened_by` (#3530). (b) A18 depends on LB-21 and LB-22. (c) A10(3) asserts prefix+`?`, not prefix+w. (d) and (e) were lane-B numbering in my draft and are superseded by lane B's own dependencies (LB-23 on the ledger). |
| 12 | Keymap schema gap | §3, delivered in A11. A18, A19 and A22 depend on it. |
| 13 | Done-bars omit the binding bar; widths wrong | DB-1..5 by reference (§0), at 1440/1024/900/390. A12's widths are fixed. |
| 14 | Uncheckable or ruling-dependent done-bars | A18(1) is a grep assertion. The rulings were answered on 2026-09-26 and 2026-09-27, so no bar says "per the operator ruling" any more. A12(2) adds the right-pane layer, and A18(8) adds warmth. The unrenamed-string list comes from grep, not a count. |
| 15 | Dropped operator questions | Lane-A defaults 1–6 in DECISIONS (2026-09-27), plus default 8 (§6), all listed for the operator. |
| 16 | Missing conflicts | §2. |
| 17 | Missing seams | (a) Non-book serving is F8, now a lane-B package (Sweep v2, 2026-09-27; number pending), and A18 depends on it. Until it lands, a non-book ref opens as a document tab reading "Opens outside the reader for now". (b) Listings: S12/S13 (`?agent=true`, `?kind=dialogue&project_id=`). (c) Nullable counts: §1.5 aggregates, rendered `—`. (d) The Autonomous Part 2 section: §5 §2.16. |
| 18 | Citations unpinned and drifted | The rev-9 citation rule (agreed with lane B). This plan pins SHAs, and its contract references are by section and anchor. |
| 19 | LB-12 scope (all four source-merge routes) | **Lane B, LB-33**, all four routes. The client side is A10(4). |
| 20 | R30 disagreement settled silently | Recorded in §2. |
