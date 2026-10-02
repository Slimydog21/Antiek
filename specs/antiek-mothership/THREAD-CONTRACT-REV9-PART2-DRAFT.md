# THREAD-CONTRACT rev 9, Part 2 (lane A): integrated draft

**Status: draft, unsigned, 2026-09-27.** Lane A (Antiek Nudge v2, 236c36bd) wrote it. It replaces the earlier deltas-only draft of this file, which is kept in git history.
- **What it is.** The whole of Part 2 (UI states), reconciled to lane B's `THREAD-CONTRACT-REV9-PART1-DRAFT.md` as of that file's 03:58Z revision. Part 1 names win.
- **Rounds.** It had two completeness and consistency critics (critique 3: 10 findings; critique 4: 1 medium and 4 low). Every finding is applied, except critique 4's fifth: it holds only if rev 8.11 is signed as draft v5 (v4 plus A10's kind scope and A7's rev-9 codes). If 8.11 is signed as v3, strike the three v4-only clauses listed under R9-46.
- **§1.4c.** Part 1's §1.4c (the Part 1 draft's lines 621–667) was re-verified byte-exact against `THREAD-CONTRACT-REV9-SECTION-1.4c-PIN.md` lines 11–57 (sha256 `a99c4950…c6821`) on 2026-09-27 at 05:50Z. Part 2 §2.3 separates Part 1's rules from lane A's own.
- **The gate.** Nothing builds against it until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT.

## Part 2 — UI states (lane A)

**Revision 9 (draft, 2026-09-27; unsigned).** Part 2 is reconciled to lane B's rev-9 Part 1 draft. Part 1 names win over lane A's draft names. Every rev-9 change is marked "(rev 9)".
- **The gate.** Nothing builds against a rule marked "(rev 9)" until rev 9 carries both lanes' signatures and a different-lineage audit ACCEPT (the rev-9 co-sign gate, Part 1 header, "Rev-9 co-sign gate (2026-09-27, agreed by both lanes)").
- **Citations.** Part 1 is cited by section number plus a short quoted anchor phrase, never by line number. A decision is cited by its `DECISIONS.md` heading and number.
- **Requests (rev 9).** Every "(needs Part 1)" marker names its request, R9-1 to R9-48. They are listed, each with the fallback lane A builds against, under "Rev-9 requests of Part 1" at the end of Part 2. The requests of earlier revisions follow the open questions.
- **All sections.** Every rev-9 refusal is top-level `{reason, detail?}`. Lane A narrows on `reason`, then on `detail` where the reason defines a closed sub-code; a legacy string `detail` equals `reason` (§1.0a "Error bodies"). No raw status code or server code reaches the UI: each maps to copy, or it is a logged lane-A bug. "Workstation" is retired as a UI noun; the UI noun is "project", the mode key and data values stay `reading`, and "Books" is a label only (§1.0; ruling 1). "Needs" gaps are marked "(needs Part 1)", each with the fallback lane A builds against.
- **No ownership leak (rev 9).** No copy anywhere says "not yours" or "isn't yours", or otherwise asserts that an item exists and belongs to someone else. Where Part 1 answers another owner's item exactly as a missing one, the UI shows exactly the missing copy (§1.15 "Existence is never disclosed"; "Another owner's private document answers exactly as a missing one"). Where Part 1 answers `403 not_owner`, the copy is neutral: it confirms neither that the item exists nor who owns it (for example "You can't use that here.").
- **Rev 8.11 carried (rev 9).** Rev 8.11 lands on 8.10 before rev 9, so rev 9's Part 2 carries its lane-A copy and rules, cited by item as "(rev 8.11 A10)": A1's null thread state (§2.4); A6's `seen_terminal_event_id` (§2.1, §2.4); A7's null counts and spend (§2.1); A10's `failure_reason` and `failed_before_start` (§2.4); C1–C6's Findings states and wire details (§2.7); Part D's informs (§2.11). Part B of 8.11 is withdrawn, because dialogues are rev 9's §1.8. Where 8.11's draft v5 differs from v3, v5 is followed (v5 = v4 plus A10's kind scope and A7's rev-9 codes). The rev-9 Part 1 draft does not yet restate these items (needs Part 1, R9-46).
- **Part 1 after this draft (rev 9).** §1.15's A06 round 2 is folded in: another owner's private document reads exactly as a missing one on every surface, private upload stays disabled until A06's activation receipt exists, and a private derivative that the server refuses has its copy (§2.2, §2.10, §2.11, §2.19).
- **§2.1 Project** (renamed from Workstation): the rev-9 row (`home_product`, `products[]`, `kind`, `derived_from_project_id`, `linked_project_ids[]`, `last_mode`, `default_mode`, `shelf_count`, `seed`); presence-only lists; `not_in_mode` with offers-gated transfer offers and disabled copy; "left on another device"; `not_found`; the landing rule ending in `default_mode`; the standalone book narrowed to the ruling-11 link plus T6.
- **§2.2 Tab:** output-anchor origins with no quote on a tab row; return-to-origin states for output passages; agent tab ids `agent:thread:<thread_id>`; the right tree; transient tabs and two-step Keep; `409 product_absent` and `mode_absent`; `no_record` from the thread read's 404.
- **§2.3 Island:** output selections (research output only, ruling 3) with four verbs and their own cost lines (ruling 2); output anchor states; the launch refusal copy; HTML reader selections under §1.4c `html-text/v1`; platform models only on an island launch (O-3 fallback).
- **§2.4 Thread list:** project lists by membership; lanes from `?parent_thread_id=`; `no_record`; `merge_failed` retired; `merged`; "Ask this thread" tier 0 branches a dialogue child.
- **§2.5 Merge (D-M):** preview, estimate, one paid draft (202, read route, cancel), free revise, commit of a named draft into a new thread or an agent; `draft_stale`, `already_merged`, `refused_capped`, Retry vs Try again; the compose page retired.
- **§2.6 Merge into document:** project-scoped target list; from-investigation made safe; Speak testimony under the serve-time gate; source merge's 410 names T6's flows.
- **§2.7 Findings:** staleness causes corrected; entry `anchors[]`, `chapter?`, `merge_ids[]`; node-keyed ids; no lens on the tab.
- **§2.8 Flags and inbox:** unified flags; the target-by-intent table (diligence only on insight, question, concept); server-state mapping; record-only spend; `consent_unavailable`; new inbox kinds with row copy; inbox `unavailable`.
- **§2.9 Books home:** "Books" label; Continue from `GET /reading/continue`; flat gate; to-read ships with rev 9; ruling-11 link.
- **§2.10 Gated text:** new bindings; `origin` rules; sentence marks; document rows; audiences; the private-upload gate (A06); read-aloud gate.
- **§2.11 Reformat:** two new source forms (monologue, notebook write-up); `input` and `mothership`; chapters; audio never stops a reformat; `use_probe`.
- **New sections:** §2.12 create page; §2.13 agent-first pane and sessions; §2.14 Converse; §2.15 Speak door; §2.16 Autonomous door; §2.17 keymap surfaces; §2.18 transfers; §2.19 Books surfaces; §2.20 voice input and read-aloud.
- **Contradictions resolved in integration** (Part 1 and DECISIONS decide): one disabled whole-scope offer copy set lives in §2.1, which §2.2, §2.17 and §2.18 reuse, and §2.18 keeps only its partial-scope lines (rev 9); linked projects show as a chip, never nested (§2.1, §2.17); off-lens Books threads show in §2.19's "Not about these books (n)" group; turn failure and ask refusal copy lives once in §2.13, with `ask_invalid · input` and `· context_items` given operator copy because Part 1 lists them as refusals that runtime state can cause (§1.8 "Refusals"); the thesis/component Flag copy is §2.3's; the `monologue_ready` row copy is §2.14's; the ruling-11 link copy is §2.1's; the `speak_publish_required` copy is §2.6's; the notebook write-up copy is §2.19's; §2.5 members read §2.4's `merged`; the retired source-merge 410 copy is §2.6's, and §2.11 points to it; the null-cap rule is §2.8's split between an unreachable ledger and `cost_unknown`, which §2.5 and §2.14 reuse; a `failed` reason's free-form `detail` never reaches the screen, by §2.11's rule, in §2.5, §2.8 and §2.13 too.

**Revision 8.10 (2026-09-27).** Part 2 is reconciled to Part 1 revs 8 to 8.10, one revision per GLM round, and signed with rev 8.10. What changed:
- **§2.11** is the rev-8 surface for C6. It covers:
  - the reformat flow, its estimate and binding, and the header with the plural model identity;
  - the five classes plus `generated` (connective templates only), `unsupported`, `unsourced`, unresolved spans, unplaced bites (listed below the document) and "Your edit";
  - lexical support below 0.35 per UAX #29 sentence;
  - hash drift as a read-time overlay with "was:";
  - probe to the core;
  - fork through the revisions route (full block text, `{carried, edited}`, rebase on `revision_moved`);
  - "Adopt as this project's reading version", with its route and refusal copy;
  - Write `informs` with its replace-all route and errors.
- **§2.10** adds `served · unsourced`, and a null origin renders the same way.
- **§2.9:** a reading-state 409 refetches and rebases (today it carries a string detail).
- **§2.2:** the restore PUT sends the retired node back unchanged (`pruned_at` included; equal on side, kind, ref, branch_origin and opened_by). `retired[]` is read in the tree's transaction, and paging stops on a null `next_before`. The body is bounded at 1,000,000 bytes, and depth is unbounded.

**Revision 7 (2026-09-26).** Part 2 is reconciled to Part 1 rev 7, which absorbed the cockpit decisions C1–C5 and the seams S1–S8 lane A signed. What changed:
- Every tab node has a `side` (left = document tabs, right = agent tabs). One tree per mode holds both panes, and the active tab is tracked per side.
- An agent-opened left tab records `opened_by` and the passage it came from.
- Retired tabs restore from their complete node.
- The right pane is named as such, never "companion". Its tabs are views of one thread each, plus the Findings tab.

The rev-7 requests follow the open questions; none blocks rev 7.

**Revision 6** reconciled Part 2 to Part 1 rev 6, which applied R5-1 to R5-6:
- Every item, entry, hunk and answer binds its named `GatedText` field (`content`, `insert`, `answer`, `excerpt`). §2.10 follows the rev-6 discriminated shape: `cite_only` is for quotations only, and each source carries its own gate.
- A carried-over hunk decision keys on `hunk_digest`.
- `stop_reason` drives every stopped state. Only threads the daily cap admitted (diligence, daemon and reformat threads, rev 8.1) can stop at the cap, so an island never offers "Raise today's cap".
- Tab numbers start from the server's `next_child_index`. A `409 number_conflict` is an ordinary rebase, not a bug.

**Revision 5** reconciled Part 2 to Part 1 revs 4 and 5, which applied R4-1 and R4-2:
- Every rights-bearing text renders from one `GatedText` rule (§2.10).
- Launch admission holds nothing, and the consent copy says so (§2.8).
- `stopped` carries its reason, including `cap_reached` and `cap_overshoot`.
- Merge members read `merge_pending` or `merge_failed` until the merge commits (§2.4). (Rev 9 retires `merge_failed`.)
- Restoring from history uses the server's `retired` descriptors (§2.2).
- To-read keeps flags whose document can't be resolved (§2.9).
- Changing the cap has its own route (§2.8).

The rev-5 requests follow the open questions. None blocks rev 5: each names the reading lane A builds against until it is answered.

**Revision 3** added these states:
- a thread tab's `no_record` and capacity-only `abandoned` (§2.2)
- anchor remap picks that persist (§2.3)
- a resumable merge (§2.5)
- revision 1 on first use (§2.6)
- `consent_stale`, the launch hold and `reserved` (§2.8)
- the withheld excerpt (§2.10)

**Revision 2** changes from rev 1:
- Counts, spend and estimates are nullable, and each null has a designed rendering.
- Tab numbers are allocated by the server and never reused.
- Merge and fork follow the rev-2 commit flows, including their stale and conflict states.
- A shared cite-only item state (§2.10) covers every rights-gated text.
- The inbox is durable, with cursor catch-up.

Each entry gives the surface, its states, its required fields (**Needs:**), and the events it reacts to.
Every surface designs every state. An unknown is never drawn as a zero or as empty: that rubric veto was
closed on five pages by W7.

**Nullable rendering rule.** A `null` count, spend or estimate renders as "—", with its reason on hover and on focus. The reasons are "Still counting", "Price unknown for this model" and "Ledger unreachable". Rev 9 adds (rev 9): "A cost today is unknown" (`cost_unknown`), "Thread records can't be read right now" (`logs_unreadable`), "No record of this thread" (`no_record`), "Priced once the conversation starts", "Page count unknown", "Not measured yet", "Outcome not recorded" and "Spend by project isn't recorded yet" (rev 8.11 A7), plus the section-specific reasons each section names. It never renders as `0`, `$0.00` or a blank. A known absence (for example `shelf_count` on a project not in Books, `not_in_product`) is not an unknown: nothing is drawn for it (rev 9).

**No raw codes (rev 9).** No raw status code or server code reaches the UI. Every refusal either has plain copy in its section or is a lane-A bug that is logged and never shown.

### 2.1 Project (shared by all three modes; D1/D5 as amended by C1; D-P; rev 9)

**The UI noun is "project" (rev 9).** "Workstation" is retired as a UI noun (§1.0 "A retired UI noun"). No new code name or wire field uses it. The rev-8.10 `workstation_id` is the project's `project_id`. A project is one registry row with one identity across the three modes. It is present in the modes its `products[]` lists (§1.0 "one identity across the three modes"; D-P). "Books" is a label only, and every data value stays `reading` (§1.0 "Every data name stays `reading`"; ruling 1).

- **States:**
  - `listed`: in a home, the `project.list` overlay or a mode switcher.
  - `active`: open in the current mode.
  - `archived`: `archived_at` is set. It applies to the whole project.
  - **`not_in_mode`** (rev 9): the project exists, but the current or chosen mode is not in its `products[]`. It is never drawn as absent, and a mode is never added silently. Mode switchers and the `project.list` overlay show the mode with its transfer offer (§2.18):
    - `kind: project`: "Open in <mode> — transfers the whole project (no model spend)" (T1).
    - `kind: reading` (a book project), for Research: "Turn this book into a new project — it gains Research and keeps its shelf (no model spend)" (T6).
    - **The offer is enabled only by `offers`** (§1.5a "tells the client, before any POST"). Lane A reads `offers.whole` from `GET /projects/{id}/transfer-candidates?to_product=<mode>&limit=1` when the switcher opens on that mode. While the read is in flight, the offer reads "Checking…". If the read fails, it reads "Couldn't check this mode. Try again." It is never enabled on a guess.
    - **Disabled offers (rev 9).** Each `offers.whole.reason` gets a disabled state and copy. This is the one copy set for a disabled mode offer; §2.2, §2.17 and §2.18 reuse it:
      - `transfer_not_supported` on a book project for Writing: "A book project can't open in Writing. Turn it into a new project first."
      - `transfer_not_supported` on an interest project, for any mode: "An interest project stays in Books."
      - `project_archived`: "Archived projects can't open in another mode. Unarchive it first."
      - `product_present`: nothing is offered, because the mode is present. The switcher refetches the row.
    - **Left on another device (rev 9).** A tab PUT or allocate in a mode the project has left answers `409 {reason: product_absent, product}` (§1.6 "Presence gates tab writes"). Lane A refetches the row and shows `not_in_mode` with the toast "This project left <mode> on another device. Its tabs are kept." The tree enters §2.2's `mode_absent`. Pending local tab operations for that mode are held, not dropped. If the operator opens the project in that mode again (T1), the kept tree reappears and they replay through §2.2's rebase. Lane A never retries the write while the mode is absent.
  - **`not_found`** (rev 9): `GET /projects/{id}` answers `404 project_not_found`. The answer is the same for a missing project and another owner's (§1.15 "Existence is never disclosed"). The copy is "This project can't be found." It offers "Back to projects".
  - **`signed_out`**: `401 authenticated_owner_required`. The copy is "Sign in to see your projects."
- **Needs** (§1.5, "Row shape (rev 9)"):
  - `project_id`: the same in Research, Writing and Books.
  - `title`, `order`, `pinned`, `archived_at?`, `created_at` and `updated_at` (LB-2, unchanged).
  - `home_product: research | writing | reading` (rev 9). It is immutable. It picks the create page and the default mode, and it never filters a home (§1.5 "it never filters a home").
  - `products[]` (rev 9): a non-empty subset of `research | writing | reading`. Homes, `mode.cycle`, the mode switchers and the transfer offers read it.
  - `kind: project | reading | interest` (rev 9). `primary_document_id` is required for `reading` and null for `interest`. A `reading` or `interest` project is always `products: [reading]`.
  - `derived_from_project_id?` (rev 9): set only on a project a partial transfer created. It drives the lineage chip (§2.18), and the `project.list` overlay indents the project under its source (§2.17).
  - `linked_project_ids[]` (rev 9): the ruling-11 links. The `project.list` overlay shows each as a chip ("Linked: <title>"), never as nesting, because both sides list each other (§2.17).
  - `last_mode: research | writing | reading | null` (rev 9). When it is null, `null_reasons.last_mode` is `no_tree`. It is never rendered; only the landing rule reads it.
  - `default_mode` (rev 9): never null. It is `home_product` while that is present, otherwise the first entry of `products[]`.
  - `shelf_count: int | null` (rev 9). It is shown only on Books surfaces, which list by presence, so it is normally set there. A null with `not_in_product` is a known absence, so no badge is drawn. Any other null renders "—" with its `null_reasons` entry. An empty shelf is a known 0 and renders as 0.
  - `seed` (rev 9): the stored seed, which §2.12's stored question reads after a reload.
  - `active: {left, right}`, per mode, from that mode's tab row (§1.6, rev 7).
  - `thread_counts: {running, needs_you, done_unseen} | null`. Counts cover the whole project across modes, with membership as the authority. `done_unseen` falls as threads are opened (§2.4 seen). Its one authority is `thread_seen`: a `done` thread counts as unseen while its completion event id is null or differs from the stored `seen_terminal_event_id`. The completion event is the thread's own terminal event. For a cascade session that is done by its leaves' aggregate and has no terminal of its own, it is the latest leaf terminal event. A null completion id always counts as unseen, so nothing done is ever hidden, and a new or backfilled completion always reads unseen (rev 9; rev 8.11 A6). The inbox's `seen_at` never drives it. A null with `null_reasons.thread_counts: logs_unreadable` renders by the nullable rule with the reason "Thread records can't be read right now" (`logs_unreadable`, rev 9). A null with no reason, which rev 8.11 serves whenever any member's `state` is null or a member or seen read fails, reads "—" with "Still counting" (rev 9; rev 8.11 A7). Counts are never computed over a partial set, so no count is shown beside an unknown member.
  - `spend_today: {cents, currency} | null`, rendered by the nullable rule. The reasons (rev 9) are "Ledger unreachable" (`ledger_unreachable`) and "A cost today is unknown" (`cost_unknown`). The figure covers the whole project. Part 1 serves no per-mode figure (§1.5 "Part 1 serves no per-mode spend figure in rev 9"), so lane A shows none. A null with no `null_reasons` entry, which rev 8.11 serves until §1.13 attribution ships, reads "—" with "Spend by project isn't recorded yet" (rev 9; rev 8.11 A7).
  - **Lists (rev 9).** `GET /projects?product=&include_archived=`. Every home lists by presence through `?product=`, never by `home_product` (§1.5 "This is the only presence filter"). Lane A never sends `?home_product=` or `?product=books`. A `422 filter_invalid` or `422 product_invalid` is a lane-A bug: log it and never show it.
  - **One project.** `GET /projects/{id}` returns the row plus `members[]` (§2.18 reads them).
  - **PATCH.** It accepts `title`, `order`, `pinned` and `archived`, and last write wins. A `422 project_patch_invalid` means lane A sent an immutable field. That is a lane-A bug: log it and never show it. A `404 project_not_found` (the project was removed on another device) enters `not_found` above, with its copy (rev 9).
- **Where a project key lands** (rev 9; DECISIONS 2026-09-27 "Where a project key lands"; §1.5 "It closes the landing rule's last fallback"):
  - `project.list` (prefix+w, ctrl+alt+w) opens the chosen project in the current mode when the project is present there. Otherwise it opens in `last_mode`, and otherwise in `default_mode`. `default_mode` equals `home_product` while that is present, so this is the DECISIONS rule. It also covers a project that has left its home product.
  - From a door outside the cycle (Home, Speak, Converse, Autonomous), it opens in `last_mode`, else `default_mode`.
  - The door keys ⌘J/E/Y/U always name their mode (ruling 8). If the active project is not present in that mode, the home shows it in one `not_in_mode` row at the top, with its offer. It is never silently missing.
- **The standalone book (rev 9; §1.5 "Standalone book, narrowed"; ruling 11).** "Add to project…" no longer promotes in place. A book project stays a book, and its two actions are:
  - **"Add to a research project…"**. The picker lists `GET /projects?product=research`, without the book itself. The action writes `POST /projects/{book_id}/members {member_kind: project, member_role: context, member_id: <research project>, link_back: true}`, which writes both rows in one transaction or neither (§1.5 "writes both rows"). §2.9 uses this copy too.
    - `201 added`: "Linked to <project>."
    - `200 already_member`: "Already linked to <project>."
    - `404 project_not_found`: "That project can't be found. Pick another."
    - `422 member_id_invalid` (a link to itself): the picker excludes this, so it is a lane-A bug. Log it and never show it.
    - The book keeps its id. Nothing reached through the link is written to.
    - "Remove link" is `DELETE /projects/{book_id}/members/{member_id}`, which also removes the reverse row.
  - **"Turn this book into a new project"**: T6 (§2.18), the only promotion in place left.
  - An interest project is not offered "Add to a research project…", because ruling 11 speaks of a book (lane-A choice, for the co-sign).
- **Reacts to** (rev 9; broadcast on `WS /ws/events` with the envelope's `investigation_id` set to `project-<id>`, §1.7). The socket has no owner filter, so every push is only a nudge. Lane A refetches through an owner-scoped read (§1.7 "a client treats every push as a nudge").
  - `project.created`, `project.updated`, `project.members_changed`, `project.shelf_changed`, `project.product_left` and `project.transferred`: refetch the row.
  - A rename, reorder, pin or archive from another device (`project.updated`): last write wins, shown as a quiet toast.
  - `project.product_left` for the mode on screen: the `not_in_mode` state above.
  - A thread changes state: refetch the counts.
  - `project.tabs.version_bumped`: §2.2.

### 2.2 Tab (a node in the branch tree, D6)

- **Tree fields (Needs):**
  - `parent_tab_id?`: null for a root tab. Depth is unbounded.
  - `side`: `left | right` (§1.6, rev 7). Left nodes are document tabs (the core material); right nodes are agent tabs, each a view of exactly one thread, plus the Findings tab. A child inherits its parent's side, with two exceptions that are always left: an agent-opened document (`agent`), and a reformat result (`derivation`, rev 8). A derivation's parent is the source document's left tab, or in writing the active section. A transient tab (below) is always left (rev 9).
  - `branch_origin?`: the exact passage the branch was opened from, and `prefix+u` returns there. It takes one of two shapes (rev 9):
    - **A document passage:** `{document_id, anchor, kind}`, where `anchor` is a `BranchAnchor` (§1.4). This is unchanged.
    - **An output passage (rev 9):** `{output_anchor, kind: selection}` (§1.6 "Output anchors on tab nodes"; §1.4b). `document_id` and `anchor` are absent. `output_anchor` carries only keys from `{thread_id, event_id, path, segment_id, segment_sha256, start, end, selection_sha256, normalization, node_id}`. Lane A copies the anchor the launch validated, from the child's `ThreadSummary.origin.output_anchor`, and drops its quote fields.
    - **No quote on a tab row (rev 9).** A tab never carries `quote`, `prefix` or `suffix` of agent output. The tab GET returns rows ungated, so a stored quote would outlive a takedown (§1.4b "The served-only quote rule"). The words shown in the tab's origin chip come from `ThreadSummary.origin`, and only while its `quote_state` is `served`. When it is `withheld` the chip reads "passage withheld". When it is null (a target-only or whole-thread origin) the chip shows no quote.
    - **No `purpose` or `target` on a tab row (rev 9).** The tab origin's keys are `document_id`, `anchor`, `kind` and `output_anchor` only (§1.6). The lane label ("hardening: …", "asking: …") reads `purpose` and `target` from `ThreadSummary.origin` (§2.4).
    - `kind` in the UI is footnote, reference, citation, island, research, manual, agent or derivation (§1.6, rev 7). The backend value for "island" is `selection` (§1.0), whether the passage is in a document or in agent output. `derivation` arrived with rev 8 (C6). `kind: selection` carries exactly one of `document_id` and `output_anchor`; every other kind requires `document_id` (§1.6).
    - A child with no passage (for example "Ask this thread", or Harden from an insight card) carries no `branch_origin`. Its `parent_tab_id` mirrors the branch (rev 9).
    - A `422 tab_origin_invalid` naming an output-anchor detail (a quote field, a bad hash, bad offsets, a bad `path`, or a `segment_id` that is not `<event_id>#<path>`) is a lane-A bug: log it and never show it.
  - `opened_by?`: `{thread_id, agent_kind}`, required when `kind` is `agent` (S1). The node opens in the **current mode's** tree and never switches the mode; when the agent's reply named a passage, the node's `anchor` is that passage's. When a promoted agent answered in a session, `thread_id` is the agent's thread, not the session's (rev 9; §1.12a "Opening documents").
  - `transient?: bool` (rev 9; §1.6 "Who may set it"). Default false. See "Transient tabs" below.
  - `hier_number`: for example `3.2.1`. Lane A computes it as `<parent's hier_number>.<k>`. `k` starts at the parent's server-maintained `next_child_index` in the latest snapshot, and rises by one for each further local spawn under that parent (§1.6, rev 6). The server registers it on the PUT, and it is final once accepted. It is never reused, and a closed or pruned node keeps its numbers: the register still names its `tab_id`.
  - `child_order[]`
  - `last_visited_child_id?`
  - `pruned_at?`: prune is a soft close. A pruned subtree stays recoverable from history, and restoring the same `tab_id`s reclaims their own numbers (R3-1, applied in rev 3).
- **Return to the origin (`prefix+u`) (rev 9).**
  - **A document passage.** `prefix+u` focuses the parent document tab and scrolls to the anchor, with the anchor states of §2.3. This is unchanged.
  - **A document passage on an HTML body (rev 9; §1.4c "Binding to bytes").** When the document's current `text_projection` or `served_body_sha256` differs from the one the anchor was made against, the anchor re-resolves by its quote and context, or it reads `unresolved` with §2.3's copy. It never moves silently (§1.4c "On reopen"). (needs Part 1, R9-1: §1.4 says "`BranchAnchor` is unchanged", so a tab's anchor has no field that records `text_projection` or `served_body_sha256`. Until Part 1 adds them, lane A re-resolves every tab anchor on an HTML body by quote and context on return.)
  - **An output passage (rev 9).** `prefix+u` focuses the tab that shows `output_anchor.thread_id`. That is normally the parent tab. If no such tab is open, lane A restores it from history or opens it. Lane A then reads that thread's `GET /investigations/{id}/outputs` (§1.4b "The route"), paging on `next_after`, until it finds the segment whose `segment_id` is `<event_id>#<path>` (needs Part 1, R9-2: a single-segment read; the fallback is paging). Events are append-only, so an output anchor never drifts (§1.4b "Currency and refinement"). What can change is whether the segment is current, whether it is served, and whether it was read. The states:
    - **`current`:** the segment reads `current: true`. Scroll to it and paint `[start, end)` over exactly `content.text`.
    - **`refined`:** the segment reads `current: false` with a non-null `current_segment_id` (§1.4b "Refined since you branched"). Scroll to the pinned version, paint it, and say "Refined since you branched." Offer "Show the current version", which scrolls to `current_segment_id`. The view never jumps to the new version by itself.
    - **`superseded`:** the segment reads `current: false` with a null `current_segment_id`. Scroll to the pinned version and say "This passage is no longer current, and nothing replaced it."
    - **`withheld`:** the segment's `content.gate` is not `served` (`text_sha256` is null). The segment renders by §2.10, nothing is painted over held-back words, and no quote is shown.
    - **`missing`:** the list ended (`next_after` null) with `complete: true` and no such segment. Open the thread at its top and say "The passage this came from is no longer in this thread's output."
    - **`partial_read`:** the list ended with `complete: false` and no such segment. Say "Some of this thread's records didn't load, so the passage can't be found right now." Offer Retry. Never imply the list is whole.
    - **`not_addressable`:** the route answers `422 outputs_not_supported` (a dialogue or reading thread before phase 2) or `422 use_probe` (a reformat thread). Open the thread at its top and say "This kind of thread can't point to an exact passage yet." For `use_probe`, offer the probe view (§2.11) at the `spans_route` it names.
    - **`thread_gone`:** the route answers `404 not_found`. The tab stays, and it says "The thread this came from has no record."
    - **`read_failed`:** a network error or a 5xx. Say "Couldn't load the passage." Offer Retry.
    - `409 output_anchor_stale` comes only from a launch (§1.3 "Validation order, before `record_branch`", steps 5 and 7), so it belongs to §2.3. Navigation never shows it (rev 9: Part 1 wins over lane A's draft here).
- **Addressing:**
  - `public_number` is allocated by `POST /projects/{id}/tabs/{mothership}/allocate {tab_id}` at spawn. It is project-wide (rev 9: "project" is the UI noun, §1.0 "workstation (rev 9)") and never reused, even after close. The call is idempotent per `tab_id`, so a retry from any device returns the same number (§1.6, rev 6).
  - **`numbering`**: the allocate call is in flight, or it failed.
    - The tab opens at once, with a dim placeholder in the number slot.
    - It is reachable by `prefix+n`/`p`, the tree panel (`prefix+t`) and the mouse, but not by `prefix+<digit>` (rev 9: `prefix+w` is now `project.list`, §2.17).
    - Lane A never invents a number locally, because a local guess could collide with another device's allocation.
    - A failed allocate retries with the next snapshot write, and the tab is never blocked. An allocate that answers `409 product_absent` is not retried until the mode is back in `products[]` (Persistence, rev 9).
  - **`numbered`**: the number is shown and addressable.
- **Operations:**
  - `spawn_child(parent, origin, kind, ref)`: allocate the number, then add the node. The hier number is computed from the snapshot, `retired_numbers` included. On a 409 it is recomputed before acceptance, so every local spawn survives with a number unique under its parent (R3-5).
  - `close(tab, mode: prune|lift_children)`, undoable for 10 s. The close is held locally through the undo window and written with the next snapshot only after the window lapses, so other devices never see a close that was undone. An undo after the write is also safe: the same `tab_id` reclaims its own numbers (R3-1).
  - `keep(tab)` (rev 9): for a transient tab only. See "Transient tabs".
  - `refocus_subtree(tab)`: view-only, no server write
  - `renumber`: never. Numbers are addresses.
- **Kinds:**
  - Left: `reader(doc_id)` and `document(write_doc_id)`.
  - Right: an agent tab of kind `research`, `dialogue`, `reformat`, `diligence` or `island`. Each holds a `thread_id` and never content (§1.2, rev 7; S2). Also on the right: `findings(project_id)`, the project companion document (§1.12; S7), and `flags(project_id)`.
  - A `dialogue` tab (rev 9; §1.2 "Agent tab kinds") shows one of: an agent session or a group (§2.13); a branched dialogue, from "Ask this thread" (§2.4) or from Ask on an output selection (§2.3); or a book session (TalkToBook, §2.19). Converse is a door with no tree, so a Converse dialogue is never a tab (default 3).
  - **Agent tab ids (rev 9).** An agent tab's `tab_id` is `agent:thread:<thread_id>`. For an agent in project P, `<thread_id>` is P's session thread for that agent (§1.2 "An agent tab in project P holds P's session thread"). The server derives the session id, and a session create must not send one (§1.8 "A session create must not send `investigation_id`"). So lane A mints the tab id only after the create answers with `thread_id`. Until then the right pane shows "Opening a conversation with <agent title>". (needs Part 1, R9-3: a `tab_id` grammar that admits ':'.)
    - Because the id is fixed per thread, reopening a closed agent tab restores its retired node (the same `tab_id` and numbers). It never adds a second node with that id.
    - The singleton `agent:dialogue` is retired. It survives only as a fallback when the API does not serve dialogue threads (`POST /investigations {kind: "dialogue"}`, §1.8 "Dialogue threads"), detected by feature. A refusal from that probe is never shown to the operator. (needs Part 1, R9-4: Part 1 names no capability signal for dialogue threads.)
  - In the reading mode, the companion document's right tab is labelled **Notebook** and reads `lens=reading` (rev 9; §1.0 "Notebook (ruling 13)"; §2.19).
  - Writing's right pane holds `block(block_id)` tabs (C5).
- **The right tree (rev 9).**
  - Agent tabs are nodes of the mode's one tree, with `side: right`.
  - A thread branched from an agent tab's output (Ask, Harden or Chase, §2.3) is a child node of that agent tab, with `branch_origin {output_anchor, kind: selection}`. It inherits `side: right`.
  - "Ask this thread" branches a dialogue child and asks there (§1.8 "\"Ask this thread\" branches a dialogue child"). Its tab is a `dialogue` child of the thread's tab. It carries no `branch_origin`, because a tab origin needs a document or an output passage (§1.6).
  - A sub-sub-agent nests as a child, and n/p/u/o work on the right tree as on the left.
- **Mode (rev 9 wording; the code key stays `mothership`).** `mothership: research | writing | reading` (§1.6 "Mode keys are unchanged"). The UI calls it the mode and labels `reading` "Books". There is no `books` value and no alias (ruling 1; §1.0 "Books is a label, and `reading` is the data name"). A tree belongs to one mode inside a project, and one tree per mode holds both panes (T9). Switching mode shows that mode's tree for the same project. Doors (Home, Speak, Converse, Autonomous) have no tree (§2.17).
- **Tab ≠ branch (agreed with lane B, 2026-09-24).** The tab tree above is *navigation state*. It is server-side per account (Q-A1), written through the single-writer API, and never a parallel store.
  - A *research branch* is *provenance*: a durable dependency from a parent investigation to a child (§1.3), plus `origin {kind, document_id?, anchor?, output_anchor?}` (rev 9).
  - The branch is written into the PARENT's log as the last step before the child starts. It does not prove the child ran; the child's own log says that.
  - An island's parent is the document's reading thread, `read-<documentId>` (§1.3 spin-research). So the islands a reader tab spawns hang under that thread in the logic tree. An island from agent output hangs under the thread whose output it selected (rev 9).
  - A tab of kind research, island or thread points at a `thread_id`. Its `parent_tab_id` mirrors the branch edge when it was spawned from research.
  - **Pruning or closing a tab never deletes a branch.** The companion document's "how I got here" reads the branch record, not the tab tree. The `agent` and `derivation` origins are navigation state only, and write no branch (§1.6, rev 7). `transient` is navigation state too; Keep writes a membership, never a branch (rev 9).
- **States:**
  - `open`
  - `focused`
  - `closed`, with undo for 10 s. On main, `LemonToast` has no undo slot (lifetimes 4/6/8 s), so MS-04 adds one with a 10 000 ms lifetime. Prune is the most destructive navigation act, so its undo outlives the longest existing toast.
  - `transient` (rev 9): a left tab in the reading mode whose document is not yet kept. See below.
- **Transient tabs (rev 9; S15; §1.6 "Who may set it").**
  - **When.** In the reading mode, a left tab that lane A opens from an agent's answer ref (a `source_refs` entry, §1.12a "Opening documents") is written with `transient: true`, `branch_origin.kind: agent` and `opened_by`. Lane A sets the flag only when the document is not already a project member, which it reads from `GET /projects/{id}` `members[]`. A member document opens as an ordinary tab. In Research and Writing an agent-opened tab is never transient.
  - **Only on a new node.** The server accepts `transient: true` only on a new node: a `tab_id` that is not in the accepted tree and has no unrestored retirement, on `side: left`, in `mothership: reading`, with an `agent` origin and `opened_by`. Anything else is `422 {reason: tab_origin_invalid, detail: transient}`, a lane-A bug: log it and never show it. Reopening a ref after its tab closed restores the retired node or mints a fresh `tab_id`. It never re-adds a retired id as new.
  - **What it shows.** A quiet chip in the tab and in the path header reads "Not kept · from <agent title>", and the tab offers **Keep**. Until Keep, the document is not a member, so the Books lens leaves it out (§1.6 "Not membership"; §2.19). Threads grounded only in it do not appear in Books.
  - **Keep** is two writes, in this order (§1.6):
    1. `POST /projects/{id}/members {member_kind: document, member_id: <document_id>, member_role: context}` (§1.5 "Members route").
    2. The next snapshot PUT clears `transient` on that node. It may only go from true to false; the reverse is `422 {reason: tab_tree_invalid, detail: transient}`, a lane-A bug, logged and never shown.

    The chip clears only after step 1 answers, so a tab never reads as kept while its document is not a member. Step 2 rides the ordinary debounced write, and it rebases like any other operation.
  - **Keep's answers** (§1.5 "Answers by the natural key"). The route is idempotent by its natural key, so a retry is always safe.
    - `201 {status: added}`: the chip clears, with a quiet toast: "Kept in <project title>."
    - `200 {status: already_member}`: the chip clears, with a quiet toast: "Already in this project." This includes a document that is already this project's book or on its shelf.
    - `409 member_role_conflict`: "This document is already in the project in another role, so nothing changed." The chip stays, and Keep is disabled with that reason.
    - `409 member_kind_conflict`: "This id is already in the project as something other than a document, so it can't be kept." The chip stays, Keep is disabled, and the case is logged.
    - `404 project_not_found`: "This project no longer exists." The project's gone state follows (§2.1).
    - `404 source_not_found`: "This document no longer exists." The chip stays, and Keep is disabled with that reason. Another owner's private document answers exactly the same (§1.15 "Another owner's private document answers exactly as a missing one"), so the copy is the missing copy and says nothing more (rev 9).
    - Any `422` (`member_body_invalid`, `member_role_invalid`): "Couldn't keep this document." It is logged as a lane-A bug, and no code is shown.
    - A network error or a 5xx: "Couldn't reach the server. Press Keep to try again."
    - No rev-9 route acts as an agent, so `403 agent_cannot_curate` never reaches this tab. The operator's press writes as the user (§1.5).
  - **Close and restore.** Closing an unkept transient tab retires it like any other tab, with its complete node, and the toast reads "Closed. It wasn't kept; you can restore it from history," with Undo for the 10 s hold. A restored node matches its retired node on `transient`, except that the restoring PUT may change it from true to false. Lane A clears it when the document has become a member since the close.
  - **Kept on another device.** On `project.members_changed`, lane A refetches the members. If the document is now a member, the chip clears and the next snapshot clears `transient`.
- **Thread-backed tab states.** The tab shows its thread's state (§2.4). Three more states can only be reached from a tab:
  - `no_record`: the thread read answers `404 {reason: not_found}`, or the parent's `GET /investigations?parent_thread_id=` lists the row as `no_record`. In rev 9 the read answers 404 for anything that is not a thread; it no longer answers 200 with `status: not_found` (§1.2 "One thread predicate"). This is a branched child whose first event never landed, or whose log was lost. The logs cannot tell these apart, so the branch stays a live dependency and fails closed (§1.3). A launch with a project writes the membership before the start, so a child whose start failed also lists under `?project_id=` as `no_record` (§1.3 "What is written, in order").
    - The tab says "No record that this thread started. Its branch stays open until it is reconciled." It offers Close, which closes the tab and never the branch.
    - It is never shown as running, and never called "abandoned".
  - `abandoned`: the parent's log holds `investigation.branch_abandoned` for this exact launch. It is written only by the refusing request, with `reason: capacity_refused`, or by an operator reconciliation with an attesting reason (§1.3). The tab says "Didn't start: no capacity", or gives the reconciliation's reason, and offers Close.
  - `spawn_refused`: the spawn answered `422 parent_investigation_not_found` or `409 reservation_parent_mismatch` (§1.2, §1.3), or, for an output branch, any rev-9 launch refusal (`launch_invalid`, `output_anchor_invalid`, `output_anchor_stale`, `output_not_servable`, `parent_log_remote`, `owner_model_root_required`; §1.3 "Validation order, before `record_branch`") (rev 9). The tab becomes a failed stub that keeps the origin passage, so nothing the operator selected is lost. It shows §2.3's copy for that reason.

  A tab never points at a reserved-only id, which is not listed and answers `404 not_found`. Reservations surface on the question that holds them (§2.8).
- **Needs:**
  - `tab_id` (agent tabs: `agent:thread:<thread_id>`, rev 9)
  - `public_number` (above)
  - `kind` plus a ref id
  - `title` (derived from the ref)
  - `mothership`: `research | writing | reading`, labelled Research, Writing and Books (rev 9)
  - `pane`: `{docked_kind?, docked_ref?}`
  - `transient?` (rev 9)
  - For an output origin: `GET /investigations/{id}/outputs` (§1.4b "The route (rev 9)"), and `ThreadSummary.origin {quote_state, …}` for the chip (§1.2 "The served-only quote rule at read") (rev 9)
  - For Keep: `GET /projects/{id}` `members[]` and `POST /projects/{id}/members` (§1.5 "Members route") (rev 9)
- **Persistence** (§1.6):
  - `GET /projects/{id}/tabs/{mothership}` returns `{tree, active: {left, right}, version, next_child_index, retired: [{closed_at, close_mode, node}]}` (§1.6, rev 7; R7-1).
  - `PUT` takes `{tree, active: {left, right}, expected_version}`. Lane A applies operations locally and writes debounced whole-tree snapshots.
  - **Error narrowing (rev 9; §1.0a "Error bodies").** Lane A narrows every refusal on the top-level `reason`, and on `detail` only where that reason defines a closed sub-code. On an old code, a string `detail` equals `reason`. No status code or reason string reaches the operator: each maps to the copy in this section, or it is a logged lane-A bug.
  - A `422 tab_origin_invalid` (a bad origin kind, an `agent` node without `opened_by`, an output-anchor shape fault, or `detail: transient`, rev 9) is a lane-A bug: log it and never show it to the operator.
  - **`409 {current}` state (`rebasing`):** another device wrote first. Take `current`, replay the pending local operations on top, and PUT again.
  - If a replayed operation targets a tab the other device closed, drop that operation and show one quiet toast ("A tab was closed on another device"). Never show a modal, and never lose a local spawn.
  - **A pending spawn whose parent closed remotely** re-attaches to its nearest surviving ancestor, or becomes a root (§1.6, rev 5). It keeps its origin, ref and thread and takes a fresh `hier_number`. The toast names where it went ("Moved under 3.2: its parent was closed on another device"). Restoring that parent later does not move it back.
  - **A replayed prune never closes a tab this device has not seen.** Children another device added under a tab this device pruned are lifted to the pruned tab's parent, with the same quiet toast. A prune closes only what the operator was looking at.
  - **Restore from history** reads the server's `retired[]` entries, `{closed_at, close_mode, node}`, where `node` is the complete tab node as it left the tree (§1.6, rev 7), including `transient` and `branch_origin.output_anchor` (rev 9; §1.6 "Retirements"). It is never a local guess. The 200 most recent come with the tree, read in the same transaction as the tree (rev 8.8). Older ones page through `GET …/retired?before=`; paging stops when `next_before` is null, which includes an exactly full last page (rev 8.8). A restored tab reclaims its own numbers. If its parent is not open, it attaches to the nearest surviving ancestor, as above.
  - **The restore PUT** (rev 8.8, synced with LB-2 #3530; precision rev 8.9) sends the retired node back unchanged, `pruned_at` included, and the server clears it. "Unchanged" means equal on `side`, `kind`, `ref`, `branch_origin` (with its `output_anchor`, rev 9) and `opened_by`, and on `transient`, except that `transient` may go from true to false in the restoring PUT (rev 9). A mismatch is `422 tab_tree_invalid` naming the fields, a lane-A bug. The node may differ only in `parent_tab_id` and `child_order` (the re-attach rule above), `last_visited_child_id`, a refreshed `title` or `pane`, and that one `transient` change. Lane A never strips `pruned_at` itself. It never sends `pruned_at` on a tab it is not restoring: a `422 tab_tree_invalid` for that is a lane-A bug, logged and never shown. The tree body is bounded at 1,000,000 bytes of canonical compact UTF-8 JSON, and depth is unbounded (§2.2). A tree that nears the bound is a lane-A bug to report (retired nodes live in `retired[]`, not in the body), never something the operator is asked to fix.
  - **`409 product_absent` (rev 9; §1.6 "Presence gates tab writes").** The PUT and the allocate answer `409 {reason: product_absent, product}` when this mode is no longer in the project's `products[]`, for example after "Leave Writing" on another device. Nothing is written, and it is not a rebase. The server checks the project, then the mode key, then presence, then the version and the body, so `product_absent` arrives before any `version_stale`.
    - The tree enters **`mode_absent`**. It stays readable, because the tab GET and the retired page still answer. Copy: "This project left <mode label> on another device. Your tabs here are kept, but new changes can't be saved in <mode label>." When `offers.whole.available` (§1.5a "Candidates"), it offers "Open in <mode label> — transfers the whole project (no model spend)" (§2.18). Otherwise it shows §2.1's disabled copy for the offer's reason.
    - Pending local operations stay on this device. They replay as a rebase if the project returns to this mode in this session, because a whole transfer brings back the kept tree unchanged (§1.5 "Leaving a product"). A spawned thread is never lost: its membership was written at launch, so it lists in the thread list (§2.4) whatever happens to its tab.
    - Lane A never opens a tree in a mode it knows is absent. The `not_in_mode` state (§2.1) offers the transfer instead. So `product_absent` is always a race, never the operator's error.
  - `404 mothership_unknown` (including any `/tabs/books`, §1.6 "Mode keys are unchanged") is a lane-A bug: log it and never show it (rev 9).
  - A tab-version bump broadcast from another device (§1.7): with no pending local operations, refetch and apply silently. With pending operations, rebase as above.
  - A 409 carries its reason (§1.6, rev 6). The first two rebase the same way, silently, with the toasts above:
    - `version_stale`: another device wrote first.
    - `number_conflict`: another device's accepted spawn moved a parent's counter past a pending local number. The pending spawn is renumbered from the new counter before it is accepted.
    - `product_absent` (rev 9) does not rebase; it enters `mode_absent`, above.
  - A `number_conflict` naming a tab this device restored from history would mean lane A sent a number the register gives another tab. That one is a lane-A bug: log it and rebase. It is never shown to the operator as their error.
  - A project survives a device change the way a herdr session survives a detach (rev 9 noun).
- **Reacts to** (rev 9; broadcast on `WS /ws/events`, §1.7 "one broadcast list"). Every push is a nudge: lane A refetches through an owner-scoped read.
  - `project.tabs.version_bumped`: the rule above.
  - `project.product_left` naming this mode: refetch the row, and enter `mode_absent` before any write fails.
  - `project.transferred` that adds this mode back: refetch the tree, leave `mode_absent`, and replay pending operations as a rebase.
  - `project.members_changed`: refetch `members[]`. A transient tab whose document is now a member clears its chip.
  - `investigation.branched` on a thread an open tab shows: refetch `?parent_thread_id=` so a child spawned elsewhere appears in the lanes (§2.4). The tree itself changes only through the tab version bump.

### 2.3 Island (A3)

**Rev 9 in brief.** An island now opens on two kinds of passage (rev 9):
- a document passage, anchored by a `BranchAnchor` (§1.4, unchanged);
- a passage of a research thread's output, anchored by an `OutputAnchor` (§1.4b, "Why a second anchor type").

Exactly one of the two is present. A selection in an HTML reader body is measured in the `html-text/v1` projection (§1.4c). "Island" stays the name of lane A's components only. Code, routes and events never say it (§1.0).

- **States:**
  - `idle`: an affordance on the selection, nothing spent
  - `composing`. (rev 9) The composer never fills the question with the selected words. The quote is shown beside the composer, read from the local selection. The server keeps the words only as the anchor's quote in the parent's log, so a later takedown is enforced in one place (§1.3, "One copy of the words").
  - `estimating`: cost shown before spend, from `POST /investigations/estimate` (§1.9, "Launch context, ask context"). This covers every research launch from an island: a document island, Harden and Chase (rev 9). It resolves one of two ways:
    - `estimate_ok` shows `{cents, basis}`.
    - `estimate_unavailable` shows the reason ("Price unknown for this model") and never a figure. Launch stays possible behind an explicit "Cost unknown" confirmation. An island is started by the operator, and the §1.13 cap reserves only diligence launches.
    - (rev 9) On an output branch the parent's context rides the run (§1.3, "Loop One on an output branch"). Whether the estimate prices that context is (needs Part 1, R9-5). Until Part 1 says so, the basis line reads "Before the parent thread's context".
  - `running`: streaming process steps and a partial outcome
  - `answered`
  - `failed`: an honest reason, with Retry. (rev 9) The reason is §2.4's failure copy, rendered only from `failure_reason` and `failed_before_start` (rev 8.11 A10), never from the per-thread GET's legacy `terminal_payload.reason`.
  - `unknown` (rev 9; rev 8.11 A1): the child's `state` reads null on a refetch. It takes §2.4's `unknown` copy, "State unknown", and is never shown as running, answered or failed.
  - `refused_capped`: the ACU gate refused the launch before start (`launch.refused`, §1.13). It is a response state, not a thread state, and it shows the gate's reason with a link to its setting.
  - `launch_refused` (rev 9): the launch was refused before anything was written or charged (§1.3, "Validation order, before `record_branch`"). It shows the copy under "Refusals of an island launch" below, never the server's code.
  - `stopped`, shown with its `stop_reason` (§1.2, rev 6):
    - `user` reads "Stopped".
    - `cancel` reads "Cancelled".
    - `budget` reads "Its research budget ran out", and offers "Research further" (§2.4 tier 1) with its own estimate.
    - `null`, from an older log, reads a bare "Stopped".

    An island is metered by the ACU gate before start and by its own research budget while running. It never stops with `cap_reached` or `cap_overshoot`, which only the cap-admitted diligence, daemon and reformat threads can (§1.13, rev 8.1), so it never offers "Raise today's cap". (rev 9) Harden and Chase children are research starts too (§1.13, "Spend classes"), so the same holds for them.
  - `kept`: collapsed to a margin mark. (rev 9) On agent output the mark sits on the segment in the agent tab.
  - `promoted`: now a thread tab. (rev 9) An output island promotes to a child right tab, `agent:thread:<child_thread_id>` with `side: right`, under the agent tab it came from. That tab's `branch_origin` carries the `output_anchor` without `quote`, `prefix` or `suffix`, because a tab write refuses them (§1.6, "Output anchors on tab nodes").
- **Needs:**
  - `anchor`: a `BranchAnchor` (§1.4): `document_id`, `source_locator?`, `region_id?`, `quote?`, `prefix?`, `suffix?`, `page_index?`. **Anchor states are UI states too:**
    - `resolved`: the island sits on its passage
    - `ambiguous`: the quote matches more than one place after re-projection, or matches once but its context changed. `POST /documents/{id}/anchors/remap` returns the candidates with a `score` (§1.4).
      - Show them in score order and let the operator pick; never jump silently.
      - The pick writes `anchor.resolved` on the owning thread, so it is asked once, not on every open.
    - `unresolved`: the passage is gone. Keep the island, marked "passage changed", with the stored quote shown.
  - Remap runs when the document's current text no longer matches the anchor's `source_locator.text_sha256`. A matching hash is `resolved` with no call.
    - (rev 9) On an HTML body, `text_sha256` is the selection digest over the `html-text/v1` projection, so the check is the slice at the anchor's offsets (§1.4c, "Digests are distinct concepts").
    - (rev 9) On an HTML body, remap also runs when the anchor's `text_projection` or `served_body_sha256` differs from the document's current values (§1.4c, "Binding to bytes"). See "Reader selections on HTML bodies" below.
  - Correction (§1.1.1): `passage_research` anchors by page today. `page_index` is that legacy read path.
  - `output_anchor` (rev 9): an `OutputAnchor` (§1.4b, "Why a second anchor type"): `{thread_id, event_id, path, segment_id?, segment_sha256, start, end, selection_sha256, normalization?, quote?, prefix?, suffix?, node_id?}`. It is present instead of `anchor` when the selection is in agent output. What the client sends is under "Output selections" below.
  - `project_id` (rev 9; was `workstation_id`): the active project. "Workstation" is a retired UI noun (§1.0, "workstation (rev 9)"). A launch sends it, so the thread becomes a member of the project before it starts (§1.3, "What is written, in order").
  - `attached_context[]`: `context_items[]` (§1.9: `doc | insight | thread | note`, and `project` in rev 9). **The attach UI does not ship until §1.9 lands (LB-21),** because unknown fields are silently dropped on main today.
  - `model_choice`: the #3400 dropdown value.
    - (rev 9) Every island launch has a parent: `read-<documentId>` for a document island, and the agent's thread for an output island. Until O-3 is ruled, an owner-model launch with a parent is refused (§1.3, "Owner-model parents (O-3, open)").
    - So on an island launch the dropdown offers platform models only. Each owner model is shown disabled with "Your own models can't start a branch yet."
    - (rev 9) The Ask verb is a conversation turn, not a launch, but its child is a branched dialogue, and every dialogue other than a book session answers `409 owner_model_unavailable` for an owner model until #3278 lands (§1.8, "Every other dialogue needs #3278"). So on Ask each owner model is shown disabled with "Your own models can't be used here yet", until a capability signal says owner models work on that dialogue (needs Part 1, R9-7). §2.4's "Ask this thread" and §2.13's sessions, groups and Converse follow the same rule.
  - `estimate`: `{cents, basis, status: ok|unavailable, reason?}` (§1.9). It is re-requested, debounced, when the model or the attached context changes.
  - `thread_id`, once it has started. **An island is a thread**, created when its first question is asked.
    - A document island branches from `read-<documentId>` with origin `selection` (§1.3).
    - (rev 9) An output island's research child branches from the agent's thread with origin `{kind: selection, output_anchor, purpose: harden | chase, target?}`. Its Ask child is a `dialogue` (below).
    - Agreed with lane B: `kept` and `promoted` are *presentation* states (margin mark vs tab), stored on the tab or anchor, not on the investigation. `merged_into` *is* investigation-level lineage (a merge record).
  - `investigation_id` (rev 9): client-minted once per press and reused on every retry of that press. An exact replay returns the first start, with no second branch, charge or broadcast (§1.3, "Idempotency (rev 9)").
  - `process_steps[]`: `{ts, kind, text, source_refs[]}`, a projection of `GET /trajectory/{id}` (§1.2), never a second store. Code, routes and events never say "island" (§1.0); only lane A's components do.
    - (rev 9) An Ask child's turns are read from `GET /investigations/{id}/turns`, never from `/trajectory`, which carries no live gate (§1.8, "Reading turns").
  - `outcome`: `{text, claims[], source_refs[]}`, with `claim_count | null` and `source_count | null` (§1.2) under the nullable rule.
    - (rev 9) A Harden child's outcome is the child itself: its `state`, `stop_reason` and `excerpt` (a `GatedText`, §2.10). There is no "supported" or "contested" badge (§1.3, "No `hardened` projection in the MVP").
- **Output selections (rev 9; R18, R19; rulings 2 and 3).**
  - **What is rendered.** The agent tab renders a research thread's output from `GET /investigations/{id}/outputs` (§1.4b, "The route (rev 9)").
    - Each segment carries `segment_id`, `event_id`, `path`, `role`, `node_id | null`, `emitted_at`, `current`, `current_segment_id | null`, `text_sha256 | null` and `content: GatedText`.
    - A served segment renders exactly `content.text`, never re-normalized, so the offsets hold. Any other gate renders by §2.10.
    - `complete: false` reads "Some of this thread's output couldn't be read, so this list may be missing parts." The segments shown are real.
    - Paging follows `next_after` until it is null.
  - **What can be selected.** Per ruling 3, the MVP selects research-thread output only: `research`, `cascade_session` and `cascade_leaf`.
    - Dialogue turns and book answers offer no selection until phase 2 (LB-3). The outputs route answers those kinds `outputs_not_supported`, and the tab renders them with no selection affordance.
    - A reformat thread answers `use_probe` with its spans route. Its passages are probed by §2.11, not selected here.
    - A merged thread's accepted draft is not selectable (§1.4b, "not selectable in the MVP"). It renders with no selection affordance, and the affordance reads "Selecting in a merged answer isn't available yet." (§2.5).
    - A segment whose `content.gate` is not `served` disables selection with "This passage is held back, so it can't be used to start research.", plus the §2.10 reason. Its `text_sha256` is null, so no anchor could be built anyway (§1.4b, "The served-only quote rule (rev 9)").
  - **Offsets.** Offsets count Unicode scalars in the segment text, never UTF-16 code units (§1.4b, "Offsets count Unicode scalars, not UTF-16 code units").
    - The client converts each DOM endpoint to a scalar offset.
    - `selection_sha256` is the SHA-256, in lowercase hex, of the UTF-8 of `text[start:end]`.
    - The shared fixture `apps/reading/src/lib/api/__fixtures__/output_anchor_nfc_v1.json` proves the conversion. Lane A's test imports it byte for byte. It checks that the rendered text equals `text`, that each `utf16_*` pair maps to `start` and `end`, and that the hashes match (§1.4b, "The shared fixture").
  - **The anchor the client sends.** `{thread_id, event_id, path, segment_sha256, start, end, selection_sha256, normalization: "unicode-nfc-v1"}`.
    - `thread_id` is the agent's thread, and `segment_sha256` is the segment's `text_sha256`.
    - `segment_id` and `node_id` may be sent, and must then match what the server derives.
    - The client sends no `quote`, `prefix` or `suffix`. The server fills them from the served segment into the parent's log (§1.3, "What is written, in order").
  - **The four verbs.** Each has its own cost line and its own launch (ruling 2):
    - **Ask:** a `dialogue` child, tier 0. It is a conversation turn: no admission, and the cap never stops it (§1.13, "Spend classes"). Cost line: "A conversation turn. Today's cap never stops it.", with the bound under "Ask" below.
    - **Harden:** a research child with `purpose: harden`, admitted by the ACU gate and bounded by its research budget. Cost line: "Research run to test this · about $X", from the estimate.
    - **Chase:** a research child with `purpose: chase`, in the same class. Cost line: "Research run to follow this up · about $X".
    - **Flag for diligence:** the consented, capped background form. Cost line: "Runs later, with your consent, under today's cap." It opens the §2.8 consent sheet.
  - **Harden and Chase.** One press sends `POST /investigations {question, kind: "research", parent_investigation_id, origin: {kind: "selection", output_anchor, purpose, target?}, investigation_id, continue_from_parent: true, project_id, title?, context_items?}` (§1.3, "Branch from agent output"). Here `parent_investigation_id` is the agent's thread.
    - `question` is the operator's own words, at least 3 characters. It is never the selection.
    - `target` follows §1.3 ("Target (rev 9)"). On an `insight` or `open_question` segment it is required and names that segment's node, as `{insight_id: <node_id>}` or `{question_id: <node_id>}`. On a `thesis` or `component` segment it is absent.
    - `chase_mode` is never sent, so the child records `off` and never chases on its own.
    - The child's states are the research states above. It stops with `user`, `cancel` or `budget` (§1.3, "The three purposes").
  - **Ask.** The first question creates the child and then asks on it (§1.8, "A branched dialogue (rev 9)"):
    1. `POST /investigations {kind: "dialogue", scope: {project_id}, parent_investigation_id, origin: {kind: "selection", output_anchor, purpose: "ask"}, investigation_id, title?}`.
       - It carries no `question` (§1.2, "`question` is not accepted on a dialogue create").
       - It sends no `continue_from_parent`, following §1.8's dialogue create body (rev 9). Part 1 says of an output branch that the field is "true, and false is refused" (§1.3, "on an output branch it is true, and false is refused"), but not whether a `kind: dialogue` output branch must send it, may send it, or is refused for sending it (needs Part 1, R9-44). Until Part 1 answers, a `launch_invalid · continue_required` on Ask is logged as a lane-A bug and reads "This couldn't start. Nothing was charged."
       - `scope.project_id` is the project whose tree holds the parent's tab.
       - The create charges nothing. A replay on the same `investigation_id` returns the same body.
    2. `POST /investigations/{child}/ask`, with the composer states, refusals and retry rules of §2.4 "Ask this thread", tier 0.

    Later questions in the same island ask on the same child. The child's context is the parent's rights-gated pack plus the focus segment, re-read under the live gate (§1.8, "Context, by dialogue").

    Once the child exists, the cost line's bound comes from `POST /investigations/{child}/ask/estimate` (§1.8, "The turn bound"). Before the first question there is no child to price, so the first bound is (needs Part 1, R9-6). Until then the first cost line shows "—" with "Priced once the conversation starts". The reply's `cost_cents` shows once it lands.
  - **Flag for diligence.** It sends `POST /flags {intent: "diligence", target, source: {thread_id}, project_id, idempotency_key}`, with `source.thread_id` set to the agent's thread, then opens the §2.8 consent sheet (§1.13, "Flagging agent output for diligence").
    - `target` is `{insight_id: <node_id>}` on an `insight` segment, or `{question_id: <node_id>}` on an `open_question` segment. Flag never sends an anchor.
    - A `thesis` or `component` segment has no `node_id`. There Flag is disabled with "Only an insight or an open question can be flagged. Harden tests this claim now." §2.8 uses the same copy.
  - **Output anchor states (rev 9).** An output anchor never drifts and is never remapped (§1.4, "never drifts and is never remapped"). For an output island, these states replace the document anchor states:
    - `current`: the pinned segment reads `current: true`.
    - `refined`: it reads `current: false` with a non-null `current_segment_id` (§1.4b, "Refined since you branched"). The island says "This passage was refined since you asked" and offers "Show the current version", which scrolls to the current segment. The pin never moves.
    - `superseded`: it reads `current: false` with a null `current_segment_id`. The island says "This passage is no longer current." The pinned segment still opens.
    - `withheld`: the origin's `quote_state` is `withheld`, or the segment's gate is no longer `served`. The island shows "Passage withheld" with the §2.10 reason and no quote, because the server has omitted it (§1.2, "The served-only quote rule at read").
- **Refusals of an island launch (rev 9).** Rev-9 refusals are top-level `{reason, detail?}` (§1.0a, "Error bodies"). Lane A narrows on `reason`, then on `detail`. Each refusal below writes nothing and charges nothing. The copy applies to output and document islands alike, wherever the code can arise. The island shows the copy, never the code:
  - `output_not_servable` (422): "This passage is held back, so it can't be used to start research." On Ask the copy is "This passage is held back, so it can't be asked about." Selection on that segment is then disabled with the same reason.
  - `output_anchor_stale` (409, `detail` `segment_changed` or `event_missing`): "This output changed. Select it again." The island reopens on the current segment with the selection cleared.
  - `output_anchor_invalid` (422, any `detail`): "That selection couldn't be pinned. Select it again." The `detail` goes to the client log for diagnosis.
  - `launch_invalid` (422) with `detail` `target_mismatch`, `target_not_applicable` or `target_not_in_parent`: "This passage no longer matches the insight it came from. Select it again."
  - `launch_invalid` with any other `detail`, `reservation_parent_mismatch` (409) and, on Ask, `scope_invalid` (422): "This couldn't start. Nothing was charged." These mean the client built the request wrongly, so the code goes to the client log.
  - `parent_investigation_not_found` (422): "The thread this came from is no longer available."
  - `parent_log_remote` (409): "This thread's record is still arriving from a remote run. Try again in a moment."
  - `owner_model_root_required` (422): "Your own models can't start a branch yet. Choose a platform model." The picker already prevents it.
  - `project_not_found` (404): "This project is no longer available."
  - `investigation_id_conflict` (409): "This was already started with different settings. Start it again." The next press mints a new `investigation_id`.
  - `branch_not_recorded` (503): "Couldn't record where this came from, so nothing started. Try again." Retry reuses the same `investigation_id`.
  - The ACU gate's refusal keeps its own state, `refused_capped`, above.
- **Reader selections on HTML bodies (rev 9; §1.4c, `html-text/v1`).** An island anchored in an HTML reader body counts its offsets in the `html-text/v1` projection. Plain-text bodies keep `unicode-nfc-v1` (§1.4c, "What it is for"). The mapping, snapping, refusal and inverse-map painting rules below are Part 1 text (§1.4c, "Endpoints (lane A)"). The mounting code, the `selection.toString()` ban, the CSS Custom Highlight API with its `<mark>` fallback, and the copy are lane A's (rev 9).
  - **Mounting.** The reader mounts the served string with `div.innerHTML` (React `dangerouslySetInnerHTML`). That is the fragment-parse context §1.4c pins: a `div`, with scripting on (§1.4c, "Parse"). DOM paths and offsets are taken in that tree.
  - **Which string.** The projection is of the served body, the exact string `/full-text` returns (§1.4c, "Authority"). A legacy v1.4.0 body is projected as served, with no relabelling and no rewrite on read.
  - **Mapping.** Each DOM Range endpoint (node, UTF-16 offset) maps to a projection scalar.
    - The projection is the final assembled NFC string. Its offsets are scalar and half-open. It has generated block separators, and whitespace collapses across inline nodes outside `<pre>`.
    - The client never uses `selection.toString()`.
    - A backward selection is first put in document order, which is not a reversal.
  - **Snapping.** A start inside whitespace the projection drops snaps forward past generated separators. An end snaps backward.
  - **Refusals.** None of these writes an anchor. The copy takes the place of the Ask affordance:
    - `splits_normalization_group` and `splits_surrogate_pair`: "That selection splits a character; select it again." The selection is never moved silently.
    - `empty_selection` (a collapsed range): no affordance appears, because nothing is selected.
    - `empty_after_snap` (snapping leaves nothing, or reverses the range): "That selection has no text in it. Select some words."
  - **Painting.** Marks are painted by the inverse map: the CSS Custom Highlight API, with a `<mark>` fallback. A composed scalar paints every DOM range that produced it.
  - **Pagination.** Pages follow the mounted DOM's block boundaries, so offsets stay global to the document (§1.4c, "Pagination").
  - **Binding.** Every persisted anchor on an HTML body carries `text_projection: "html-text/v1"` and `served_body_sha256`. The client reads both from `/full-text` or the anchor map (§1.4c, "Binding to bytes").
    - Where a `BranchAnchor` carries them is (needs Part 1, R9-1). That covers an island's anchor, a branch origin and a tab's `branch_origin`. §1.4 keeps `BranchAnchor` unchanged, and lane B's notes add the two columns only to `anchored_highlights` (§1.4c, "Lane B notes to §1.4c").
    - Until Part 1 names the place, an island anchor without them is checked by its slice digest alone, and any mismatch goes to remap. It never moves silently.
  - **Reopening.** An anchor whose `text_projection` or `served_body_sha256` differs from the document's current values re-resolves by quote and context through the remap route. If that fails, it renders `unresolved` (the anchor states above). It never moves silently.
  - **Fixture.** `apps/reading/src/lib/api/__fixtures__/html_text_projection_v1.json`. The projection half is Astra's. The DOM half is lane A's: the paths, selections, refusals and `fragment_parse`. Lane A's tests import it byte for byte (§1.4c, "Fixture").
- **Reacts to:**
  - stream events for its thread (research children)
  - (rev 9) `thread.turn_requested`, `thread.turn` and `thread.turn_failed` on an Ask child. Each is a nudge to refetch `GET /investigations/{child}/turns` (§1.7, "one broadcast list"). Receipts and provenance never arrive by socket.
  - (rev 9) `investigation.branched` on the parent: the new child appears in the parent's lanes (§2.4)
  - (rev 9) a refetched outputs page in which the pinned segment's `current` or gate changed: the output anchor state updates in place
  - cancel
  - model change before the question is sent

### 2.4 Thread list, lanes and "ask this thread" (A4)

- **States (list):**
  - `loading`
  - `empty`: "No threads on this document yet". (rev 9) The project view says "No threads in this project yet", and a thread with no branches says "No branches from this thread yet". Each is shown only after a real answer.
  - `error`: "Couldn't load threads.", with Retry
  - `ready`
- **What each list reads (rev 9).**
  - **Per document:** `GET /investigations?document_id=`.
  - **Per project:** `GET /investigations?project_id=`. Membership is the authority: a thread lists when it has an `investigation` member row in the project, of any role (§1.2, "Endpoints (rev 9 deltas)"). A `reading` or `interest` project also adopts legacy threads by its documents (§1.2, "Legacy adoption").
  - **In the reading mode:** the Books lens, `?project_id=&document_ids[]=` (§2.19).
    - The lens hides a `reading` project's threads that ground in none of its documents.
    - Lane A shows those from `?project_id=` alone, in §2.19's collapsed group "Not about these books (n)" (Appendix C.2 item 13's default).
  - **Lanes:** `?parent_thread_id=` (below).
  - **Dialogues:** `?kind=dialogue&dialogue_kind=`, for Converse (§2.14) and agent sessions (§2.13).
  - **A rename.** In rev 8.10 the row's `scope` field meant "document or workstation". It is now only which list is shown. Part 1's `ThreadSummary.scope` is the dialogue scope, `{project_id} | {document_id}`, and it is null on every other kind (§1.2).
- **States (row):**
  - `queued`
  - `running`
  - `needs_you`
  - `done`, with an `unseen` marker until the thread is opened (`thread_seen`, §1.5). (rev 9) The marker keys on the thread's completion event, as §2.1's `done_unseen` does, so a thread done with no completion id always shows it (rev 8.11 A6).
  - `failed` (rev 9; rev 8.11 A10). The headline and its sentence come only from `failure_reason` and `failed_before_start`, a closed set. The per-thread GET's legacy `terminal_payload.reason` is free text, and lane A never renders it. The UI never names a phase.
    - `failed_before_start: true` reads "Didn't start", followed by the sentence for its `failure_reason`:
      - `owner_model_unavailable`: "The model you chose isn't available. Pick another and try again."
      - `owner_model_outcome_unknown`: "We couldn't confirm the model's answer, so nothing started. Try again."
    - `failed_before_start: false` reads "Didn't finish", followed by:
      - `owner_model_unavailable`: "The model you chose stopped being available. Pick another and try again."
      - `owner_model_outcome_unknown`: "The model's answer didn't come back, so the run stopped. Try again."
    - `failed_before_start: null` reads "Didn't finish", with no claim that it started.
    - A null `failure_reason` adds no sentence. The failure renders by its state alone, with the headline above.
    - This is the one failure copy set for a thread; §2.2, §2.3 and §2.8 use it.
    - **Which kinds (rev 9).** "Didn't start" appears only on a `research` row, the one kind whose running state keys on `phase.enter` (rev 8.11 A1). A cascade leaf keys on `start_requested`, and a cascade session's synthesis-tail failure comes after its leaves ran (rev 8.11 A2). Rev 8.11 v5 A10 derives `failed_before_start` only for `research` and serves null for `cascade_leaf`, `cascade_session`, `reformat` and `reading`, so those rows read "Didn't finish" with no claim that it started. Lane A also never shows "Didn't start" on a non-research row, even if the field arrives `true`. A `reformat` row's failure takes §2.11's `reformat.failed` copy, never this set. The rev-9 Part 1 draft does not yet carry the kind scope (needs Part 1, R9-46).
  - `unknown` (rev 9; rev 8.11 A1): `state` is null. The thread's record could not be read completely (a layer failed to read, or the reader skipped a record it could not parse), and no terminal decides the state. A cascade session with no terminal of its own reads null when any leaf read is incomplete, before any leaf aggregate is taken. The row shows a neutral dot with "State unknown", and on hover and focus "Its record couldn't be read." It is never shown as working, failed or needing attention.
  - `stopped`, with its `stop_reason` (§1.2, rev 6):
    - `user`, `cancel` and `budget` read as in §2.3.
    - `cap_reached` and `cap_overshoot` read as in §2.8, and only those two offer "Raise today's cap". They can only occur on threads the daily cap admitted: diligence, daemon and reformat threads (§1.13, rev 8.1).
    - `null` reads a bare "Stopped".
  - `idle`: a thread with no terminal event, so it never shows as working. Three kinds of thread read it:
    - a `reading` thread;
    - (rev 9) a `dialogue` between turns;
    - (rev 9) a promoted agent when nothing of its own runs. An agent never reads `done` (§1.2, "Promoted thread.").
  - `merge_pending(thread_id)`: the member recorded `merged_into`, but the merged thread's record has not been delivered yet (§1.2, "Pending merge"). The row says "Merging into …", links the merged thread, and is not yet shown as merged.
  - `merged` (rev 9; was `merged_into(thread_id)`): the row keeps its own state and gains a "Merged into …" marker for each merge in which it was a member.
    - `merge_ids[]` lists every merge the thread took part in, as a member, a result or a target (§1.2, "as a member, a result or a target"), so the list alone cannot tell a member from the merged thread or a target agent.
    - Lane A resolves each `merge_id` through `GET /threads/merge/{merge_id}/draft` (§1.10, "Read (rev 9)"), as §2.7 does. It shows the marker only when this row is in the read's `member_ids[]` and is neither `committed.thread_id` nor the target agent that `committed.target` names.
    - The marker links to `committed.thread_id`. While the read is in flight, it reads "Merged" with no link. A `404 merge_not_found` makes that marker read "Merged (that merge can't be found)", with no link.
    - A merged thread itself shows no member marker. It reads `done` once its start is delivered (§1.2, "Merged thread.").
    - A target agent shows no member marker either. It keeps §2.13's "Knows" chip, which counts the merge.
  - **`merge_failed` is retired (rev 9).** Every merge refusal happens before the commit, so a member is never left holding a refused commit (§1.10, "`merge_failed` is retired"). A refused commit shows only on the merge surface (§2.5, including its 503). The member's row does not change.
  - `no_record` (rev 9): a thread that a live branch or a member row names but that has no stored log (§1.2, "`no_record` (rev 9)"). It reads "Started, but no record of it running".
    - Every other field is null, and each renders "—" with "No record of this thread".
    - It is never shown as running, and never called "abandoned".
    - It appears only in the lane and project lists, never in an unfiltered list.

  `capped` is not a row state: it is a pre-start refusal, shown on the launch surface and in the inbox (§1.1.4). Agreed with lane B: the state is *derived* by the one server helper keyed by `kind` (§1.2), never from a second state column.
- **Row kinds** (§1.2): `research`, `cascade_session`, `cascade_leaf`, `reading`, `dialogue` and `reformat` (rev 7). A cascade leaf nests under its session. Attribution buckets are never rows.
  - A `dialogue` row shows the conversation's title and last turn time. Before any turn the title reads "New conversation", and after that it is the first question.
    - Its states are `idle` between turns and `running` while a turn is open: a `thread.turn_requested` with no `thread.turn` or `thread.turn_failed` (§1.2, "State (rev 9 additions)"). A failed turn is an outcome of that turn, never a row state. It has no terminal state, like `reading`.
    - (rev 9) The row names its `dialogue_kind`: `session` reads "with <agent>", `group` "with <n> agents", `book` "about <book title>", `branched` "asking: …" (the lane label below), and `plain` "Conversation".
    - (rev 9) A dialogue's evidence is on each turn (§1.2, "Counts (rev 9 additions"), so the row shows no claim or source chips.
  - A `reformat` row shows the source title, the mode and the bound model. Its states follow §2.11's engagement: `running` while generating, `done` once committed, `failed` with the reason, and `stopped` with `cap_reached` or `cap_overshoot`.
  - Both open their right-pane agent tab (§2.2). A reformat row also offers its derivation's left tab once committed. The list and the tab read the same thread, so neither bypasses the other.
- **Lanes (rev 9; R19).** A lane is a branch subtree (§1.0). A thread's lanes read `GET /investigations?parent_thread_id=<id>` (§1.2, "Endpoints (rev 9 deltas)").
  - **Order.** Children come in branch order. Legacy children of a pre-B0 parent follow with `origin: null`. An abandoned branch is not listed.
  - **Nesting.** A lane's own lanes load with `?parent_thread_id=<lane>` when it is expanded, at any depth.
  - **Labels**, from `origin.purpose` and `origin.quote_state`:
    - `harden` reads "hardening: <quote>", `chase` reads "chasing: <quote>", and `ask` reads "asking: <quote>".
    - `quote_state: withheld` puts "passage withheld" in place of the quote.
    - `quote_state: null` means the origin quotes nothing: a `target`-only or whole-thread origin (§1.2, "The served-only quote rule at read"). The label then uses the child's `title`, for example "asking: <title>".
    - With no `purpose`, the label is the origin's kind and the title: "footnote: …", "reference: …", "citation: …", "from a passage: …" (`selection`), "follow-up: …" (`research`) or "branch: …" (`manual`).
    - `origin: null` reads "earlier branch: <title>".
  - **Each lane shows its own values:** its row state (above), its spend (`spend_cents | null`) and, for a research child, its `excerpt` (a `GatedText`, §2.10). An unknown is "—" with its reason, never 0.
  - **A `no_record` lane** reads "Started, but no record of it running", with every other field "—".
  - **Paging.** `limit` is 1 to 500, and the route has no cursor. Lane A asks for 500. When 500 rows return, the list says "Showing the first 500 branches". A cursor is (needs Part 1, R9-8).
- **Seen:** opening a thread sends `POST /investigations/{id}/seen {through_event_id}`, carrying the newest event id the view rendered. The server stores that event's trajectory position and only ever moves it forward (§1.5), so a late or out-of-order send is harmless.
  - (rev 9; rev 8.11 A6) The server also records `seen_terminal_event_id` when the sent event is the thread's completion event or comes after it. For a cascade session that is done by its leaves' aggregate and has no terminal of its own, sending the session's own latest event counts. The body stays exactly `{through_event_id}`.
  - A send that fails (`404 not_found`, `503 thread_log_unreadable` or a network error) is never shown. The `unseen` marker stays, and the next open sends again. A `422 event_not_in_thread` or `422 seen_body_invalid` is a lane-A bug: log it and never show it.
- **Needs** (§1.2 `ThreadSummary`):
  - `thread_id`, `title`, `kind`, `state` (rev 9 adds `no_record` in the lane and project lists; rev 8.11 A1 lets it be null)
  - `failure_reason: owner_model_unavailable | owner_model_outcome_unknown | null` and `failed_before_start: bool | null` (rev 9; rev 8.11 A10), on the list and on the per-thread GET alike
  - `anchor?`
  - `origin | null` (rev 9): `{kind, purpose?, anchor? | output_anchor?, target?, via, branch_event_id, parent_thread_id, quote_state: served | withheld | null}`. The anchor's `quote`, `prefix` and `suffix` come back only while the passage is served now.
  - `scope | null` (rev 9): the dialogue scope only
  - `participants[]`, `dialogue_kind | null`, `agent | null` (rev 9)
  - `project_ids[]` (rev 9): every project the thread is a member of
  - `model`
  - `spend_cents | null`
  - `last_activity_at`
  - `parent_thread_id?`
  - `merged_from[]`, `merge_ids[]` (rev 9), and, for the `merged` marker, `GET /threads/merge/{merge_id}/draft` per merge (`member_ids[]`, `committed {target, thread_id}`) (rev 9)
  - `excerpt` (a `GatedText`), for lanes
  - `claim_count | null`, `source_count | null`. Both are null while the log is incomplete, and render by the nullable rule ("Still counting"). A known `0` renders "0".
- **Ask this thread:**
  - **Where it is offered (rev 9).** On `research`, `cascade_session` and `cascade_leaf` rows.
    - A `dialogue` row continues that dialogue directly.
    - A `reading` row opens its book session (§2.19).
    - A `reformat` row's passages are probed by §2.11.
  - **Tier 0 (rev 9), a conversation turn.** "Ask this thread" branches a `dialogue` child and asks there. Rev 7's turn persisted on the addressed thread is superseded (§1.8, "Where turns live"). Lane A never asks a research thread directly.
    1. **The first question creates the child:** `POST /investigations {kind: "dialogue", scope: {project_id}, parent_investigation_id: <the thread>, origin: {kind: "research", purpose: "ask"}, investigation_id, title?}`.
       - It carries no `question`.
       - `investigation_id` is client-minted and reused on retry, and a replay returns the same body.
       - `scope.project_id` is the project whose tree holds the thread's tab (§1.8, "Kinds of dialogue").
       - Its refusals take §2.3's copy ("Refusals of an island launch").
    2. **Each question** is `POST /investigations/{child}/ask {question, context_items?, input?, model_choice?, mothership, idempotency_key}`.
       - `question` is 1 to 2,000 characters.
       - `mothership` is the current mode.
       - `idempotency_key` is minted once per press (§1.8, "Identity and idempotency").

    Later questions in the same composer ask on the same child. Reopening an "asking" lane continues it. The child's context is the parent's rights-gated pack plus `context_items` (§1.8, "Context, by dialogue").
  - **Composer states (rev 9):**
    - `idle`
    - `creating`: the first question only, while the child is created. It says "Starting the conversation".
    - `sending`
    - `answering`: admitted, with no reply yet. It says "Waiting for the reply". Rev 9 has no token stream: the reply arrives whole (§1.8, "The answer arrives whole"). The composer for this child stays locked until `thread.turn` or `thread.turn_failed` lands.
    - `answered`
    - `turn_failed`, with the reason's copy (§2.13 "Turn states")

    A reload reads `GET /investigations/{child}/turns`. A non-null `open` restores `answering` (§1.8, "Reading turns").
  - **The reply.**
    - `answer` and each `context[]` item are `GatedText`s, rendered by §2.10. A takedown withholds an old answer on the next read (§1.8, "Answers are gated at read").
    - `answer.origin: unsourced` marks the reply "No source supports this reply", and each unsupported span carries the same mark in place. It is never labelled "Generated".
    - `source_refs[]` open as left tabs (§2.2).
    - The context receipt renders as §2.13 renders receipts. It exists on answered turns only (§1.8, "The context receipt").
    - `cost_cents | null` renders by the nullable rule.
  - **Its cost.** The bound is `POST /investigations/{child}/ask/estimate {question, context_items[], model_choice?}`. It answers `{cents | null, max_cents | null, basis, status, reason?}` (§1.8, "The turn bound").
    - The line reads "A conversation turn · about $cents, at most $max_cents. Today's cap never stops it." Each null renders "—" with its reason.
    - Before the first question there is no child to price, so the first bound is (needs Part 1, R9-6). Until then it shows "—" with "Priced once the conversation starts".
  - **Refusals and failures of an ask.** The composer shows the copy, never the code. The one copy set for every dialogue ask is §2.13's ("Ask refusals" and "Turn states"); the question-field refusals below are part of it:
    - `ask_invalid · question_empty`: "Type a question first."
    - `ask_invalid · question_too_long`: "Questions can be up to 2,000 characters."
    - `ask_invalid · input`: "That voice note couldn't be used. Record it again or type the question."
    - `ask_invalid · context_items`: "One attached item can't be used. Remove it and try again."
    - Retry rules follow §2.13: Retry reuses the key only after `unavailable` or `interrupted`; `owner_model_outcome_unknown` and `failed` take a new press with a new key; `409 turn_in_progress` waits for `thread.turn`, then refetches; `409 idempotency_conflict` is a lane-A bug, and the next press mints a new key.
  - **Voice (rev 9; lane-A default 8, as refined).** An ask is conversational, so a voice note shows its transcript and sends it after a visible 1.5 s grace window. Enter sends at once, and Esc keeps the text for editing. `input` and `voice_capture_event_id` follow §2.20 and §1.8 ("Voice input (rev 9; pointer)"). The capture id also returns on a 503.
  - **Tier 1, a new research run.** `POST /investigations {question, parent_investigation_id, continue_from_parent: true, investigation_id, project_id, title?, context_items?}`, which writes a branch (§1.3, "Tier 1 (rev 9 restatement").
    - The composer labels it "Research further" and shows its own estimate (§1.9). An unknown price follows §2.3's "Cost unknown" confirmation.
    - (rev 9) The child appears in the thread's lanes. It offers platform models only, because it has a parent (§1.3, "Owner-model parents (O-3, open)").
    - (rev 9) Voice fills an editable draft and never sends by itself.
    - Its refusals take §2.3's copy.
  - The two tiers are distinct actions with distinct cost states, never merged into one ambiguous button.
- **Reacts to:**
  - stream events for research rows
  - (rev 9) `investigation.branched` on a listed thread: refetch its lanes
  - (rev 9) `thread.dialogue_started`, `thread.turn_requested`, `thread.turn` and `thread.turn_failed`: refetch the dialogue row and, when open, its turns
  - (rev 9) `investigation.merged_into` and the merged thread's start event: refetch the affected rows
  - (rev 9) `project.members_changed`: refetch the project list

  The socket carries no owner filter, so every push is a nudge to refetch through an owner-scoped read (§1.7, "one broadcast list"). Receipts and provenance never arrive by socket.

### 2.5 Merge (A4, lane B B2; rev 9: D-M, lane A §A5)

**What rev 9 changes (rev 9).** A merge now has four steps over one merge session (§1.10, "A merge becomes four steps"):
1. the free preview;
2. an estimate;
3. one paid, model-written draft, which the operator can revise for free;
4. a commit that adopts one named draft byte for byte and runs nothing.

The commit goes to a new thread, which is the default, or into an agent. The flow runs in the right pane and never opens a new browser tab. In writing mode it runs in the AI sidecar, as §2.11's engagement does (C5).

**Refusals (rev 9).** Every refusal is top-level `{reason, detail?, …}` (§1.0a, "Every refusal that rev 9 adds or changes answers top-level JSON with a `reason`"). Lane A narrows on `reason`, then on `detail`. `draft_stale` is the one reason with a structured `detail`. An old code that still answers a string `detail` also carries `reason` equal to it. No code reaches the UI. Each one either has the copy given below or is a lane-A bug, which is logged and never shown.

- **States (the path):**
  - `selecting`: two or more distinct threads. There is no member cap (rev 9; §1.10, "There is no member cap"), and §1.11a's five-investigation limit never applies. With fewer than two, or with a repeat, Preview stays disabled: "Pick at least two different threads." A `422 members_invalid` would be a lane-A bug.
  - `previewing`: the preview is free, and it says so: "Free. Nothing runs until you draft." Items render by §2.10, and the header carries the §2.10 counts.
    - The layout: contradictions first, side by side and never averaged. Then items by source document, then by origin thread. Within each group the server's order is kept (§1.10, "Order (rev 9)"). The preview, the estimate, the draft and `grouping[]` all share that order.
    - **A member still being recorded** (rev 9; `incomplete_members[]`): "Still being recorded: <thread title>. Its findings aren't in this preview yet, and it can't be drafted until it finishes." Draft stays disabled with that reason. This matches the draft's `422 members_incomplete`.
    - **A member that no longer exists** (`404 thread_not_found`, with `ref`): "<title> no longer exists." It leaves the selection, and one key re-previews.
    - **A thread that can't be used here** (`403 not_owner`, with `ref`): "One of these threads can't be used in this merge." It leaves the selection in the same way. The copy never says whose thread it is (rev 9).
  - `conflicts_shown`: `conflicts[]`, side by side. The heading reads "Contradictions found by structure. None found doesn't mean none exist", so a zero never reads as "no conflicts".
  - `framing`: the operator writes the merged thread's question, which the draft and the commit both require.
    - The question is 3 to 2,000 characters, and the counter says so.
    - Voice fills an editable draft and never sends by itself, because this composer starts paid work (lane-A default 8; rev 9).
    - **Nothing servable** (rev 9): when no preview item is `served`, Draft is disabled with "Nothing here can be shown to a model, so there's nothing to draft from." This matches `422 no_served_items`.
  - `estimating` (rev 9): `POST /threads/merge/draft/estimate`.
    - It shows `estimate_cents` beside `max_cents`, and the model as "Uses <model>" from `assumptions.model`.
    - The admission copy is "Starts if $<max_cents> of today's cap is free. If there isn't room, it doesn't start and nothing is charged." The server admits a draft only when the cap's remaining amount covers `max_cents` (§1.10, check 6). A draft is one call, so it never pauses partway. This replaces §A5's "it pauses if the cap runs out".
    - **What the model will see**, from `assumptions`: "The model will read n items. m items aren't shown to it." The count links to the list.
    - **The free cap** reads `GET /settings/budget`, as §2.8 does, and uses §2.8's split for a null (rev 9).
      - When `max_cents` doesn't fit, the sheet says "$Y of today's cap is free" and offers "Raise today's cap". Draft stays available, because the server's admission is the authority.
      - When `held_today_cents` is null, or `spent_today_cents` is null because the ledger can't be read, the sheet reads "Free cap today: unknown", and Draft is disabled with "Can't check today's cap right now".
      - When `spent_today_cents` is null because a cost today is unknown (`cost_unknown`, §2.8), the sheet reads "Free cap today: —", with the reason "A cost today is unknown". Draft stays available, with the line "The server checks the cap when you draft." One unknown-cost record never blocks every draft for the rest of the day (rev 9).
    - **Price unknown** (`estimate_cents` and `max_cents` both null, `reason: "unavailable"`): both figures render "—" with "Price unknown for this model", and never `$0.00` (§1.10, "An unpriced model returns both as `null`"). Draft then needs an explicit confirmation, "Cost unknown. Draft anyway?", which sends `confirm_unpriced: true`.
    - **The model.** A picker offers the lineup's models (`model_choice`). Changing the model fetches a new estimate, and the model is never swapped silently. The estimate binds nothing (§1.10, "The estimate binds nothing"). The model resolves once, at admission, and the draft names the model it actually used.
    - A `409 preview_stale` goes to `preview_stale`.
  - `drafting` (rev 9): asynchronous. The POST answers `202 {merge_id, draft_id, state: "drafting"}` (§1.10, "Why the POST answers 202"). The result arrives through the read route, after a socket nudge or an inbox item.
    - The copy is "Drafting…". It carries Cancel and the line "You can leave. The inbox tells you when it's ready."
    - Cancel sends `POST /threads/merge/draft/{draft_id}/cancel {}`. The draft then reads `draft_failed` with `cancelled`. On a draft that has already finished, Cancel answers the current state, and lane A renders that state.
    - Discard while drafting sends Cancel first.
  - `draft_review` (rev 9): the draft, read from `GET /threads/merge/{merge_id}/draft?draft_id=`.
    - **Header:** "Draft n · <model> · <cost>", with `cost_cents` rendered by the nullable rule. The draft lineage comes from `lineage[]`, one key per version: "Draft 1 (model) · Draft 2 (your edits)".
    - **The synthesis** renders in its recorded `answer_provenance.presentation_mode`, as §2.11 presents evidence (T7). `synthesis.text` is served without markers. Citations come from `sentences[]`: each sentence's `start` and `end` are offsets into that text, and its `item_ids` are the items it cites.
    - **Per-sentence origin**, from `sentences[].origin` and never inferred by lane A:
      - `source` shows its citation chips, each item with its own gate (§2.10);
      - `generated` shows "Generated";
      - `unsourced` shows "Unsupported: no source";
      - `operator` shows "Your edit", in the operator's own-words treatment.
    - **The claims list:** `claims[]`. Each claim shows the items it cites, and each item shows its origin thread and gate.
    - **Measures:** "n of m sentences cite a source", from `measures` (the referenced sentences, out of all sentences that are not operator sentences).
    - **"What the model was not shown"** opens expanded under the synthesis, and the operator may collapse it (rev 9). So the free preview stays visible under the draft, as D-M requires (DECISIONS D-M, "The free preview stays step one"). It lists `not_shown[]` with each item's gate chip and a reason in words:
      - `unresolved`: "Its source can't be found."
      - `not_servable`: "Its source can't be quoted here. The model could only cite it."
      - `lineage_unreconciled`: "Held back until its thread's history is reconciled."
      - `budget`: "It didn't fit in what the model can read at once."
    - The preview grouping (`grouping[]`) and `conflicts[]` stay one key away. Keeping those two one key away, rather than always in view, is a lane-A choice, for the co-sign against D-M (rev 9).
    - **Held back** (rev 9; §1.10, "Re-judged at every read"): the synthesis gate is judged live on each read. When it reads `withheld`, the text is gone and §2.10's withheld copy shows: "Held back: a source this draft stood on can't be shown now." Accept and Edit draft are disabled with that reason, and "Redraft" is offered. A commit would answer `draft_stale`.
    - **Actions:**
      - "Accept as new merged thread": the default and primary action (D-M, "'Accept as new merged thread' is the default"; rev 9).
      - "Accept into agent…": see below.
      - "Edit draft": see `editing` below.
      - "Edit question and redraft": this returns to `framing` with the question kept, then fetches a fresh estimate and makes a new paid draft. It stays in the same session and sends `merge_id`, because the session is bound to the members and the digest, not to the question (§1.10, "A `merge_id` is bound to its session identity").
      - "Discard": there is no route (§1.10, "Discarding means the client leaves the session"). The copy is "Discarded. Nothing more will be charged." What was already spent stays in the spend record.

      "Both targets in one press" is not offered.
    - **"Accept into agent…"** (rev 9):
      - **The picker** lists the active project's agents from `GET /investigations?agent=true&project_id=` (§1.12a, "lists the caller's agents that are members of that project"). "All your agents" drops `project_id`.
      - **A member of this merge** is listed but disabled: "An agent can't be merged into itself."
      - **The common parent** is preselected only when every member descends from it and it is an agent (`ThreadSummary.agent` is not null) (§1.10, "Lane A preselects the common parent only when every member descends from it"). It is never applied without a press.
      - **Before agents exist.** When the list is empty or the filter is refused, the action is disabled with "Agents aren't available yet". A `422 target_unavailable · agents_unavailable` on a commit sets the same disabled state for the session.
  - `editing` (rev 9): the editor loads `edit_text`, the marked encoding. Lane A draws each `[[ref:<item_id>]]` marker as a citation chip, which the operator can move or delete. The operator can add a chip from the preview's `served` or `cite_only` items. The copy reads "Saving an edit is free." Edit draft is disabled when `edit_text` is null (the synthesis is held back).
  - `revising` (rev 9): Save sends `POST /threads/merge/draft/{draft_id}/revise {synthesis_text, idempotency_key}`, with the text in the marked encoding.
    - The answer is `201` with the full draft shape. It becomes the current draft and joins the lineage, and its parent stays one key away.
    - The server decides which sentences are edits (§1.10, "The server decides what is an edit"). Changed sentences read "Your edit", and unchanged sentences keep their origin and claim. Lane A never names an origin.
    - **Refusals.** On every refusal the edited text is kept locally.
      - `422 too_large`: "This draft is too long to save. The limit is 64 KB."
      - `422 unresolved_claim_ref` (with `ref`): "A citation points at something held back or outside this merge. Remove it to save." The chip is marked in place.
      - `409 draft_not_ready`: lane A offers Edit only on a finished draft. It refetches and shows the draft's state.
      - `409 merge_committed`: see `already_merged`.
      - `404 draft_not_found`: a lane-A bug.
  - `merging`: the commit is in flight. The copy is "Accepting…".
  - `merged`: shown only on `200 {merge_id, target, thread_id, merged_from[], state: "committed"}`. The server sends that only when every record has been delivered, the merged thread's start event included (§1.10, "A partial merge never reports success"). A partial merge never reads as merged.
    - **Target `new_thread`:**
      - "Merged into a new thread." The merged thread opens as a right-pane agent tab.
      - Its first outcome is the accepted draft, read through `GET /threads/merge/{merge_id}/draft?draft_id=<committed.draft_id>` and rendered as in `draft_review`, without the actions. Lane A names `draft_id` because the session's newest draft need not be the accepted one.
      - It reads `done` (§1.2, "reads `done` once its start event is delivered"), and no "done" inbox item fires.
      - Its own spend is 0. The tab shows the draft's cost, "Draft cost <cost>", from the draft's `cost_cents` by the nullable rule.
      - A digest mismatch at read reads `withheld · unresolved` (§2.10).
      - Its text is not selectable for islands or branches in the MVP (§1.10, "Not selectable in the MVP"). The selection affordance reads "Selecting in a merged answer isn't available yet."
    - **Into an agent:** "Added to <agent>." No thread is minted, and the agent's state and own counts don't change. Its "Knows: n threads · m merges" chip counts the merge, from `merged_from[]` and `merge_ids[]` (§2.13).
    - Members read `merged` in §2.4 (rev 9: the rev-8.10 `merged_into(thread_id)` row state is renamed).
- **States (off the path):**
  - `preview_stale`: an estimate, draft or commit answered `409 preview_stale`. The digest covers the gated text, its pointers and the `content_class` of every source (§1.10), so a changed thread, a changed source or a changed right all land here.
    - Lane A re-previews at once, keeps the selection and the question, and says "Something in these threads or their sources changed since the preview". It never drafts or commits against a preview the operator has not seen.
    - **A fresh preview opens a new session** (rev 9). It has a new `preview_digest`, so the next draft omits `merge_id`. Earlier drafts stay in the old session's record.
  - `draft_stale` (rev 9): the commit answered `409 draft_stale`. The draft stays readable, and Accept is disabled. The copy names what changed, from `detail.kind`:
    - `member_changed`: "<thread> has new findings since this draft (n added, m removed)."
    - `source_changed`: "A source behind this draft changed." The item's chip is marked.
    - `rights_changed`: "A source's rights changed since this draft: it was <then>, now <now>." The gates are named in words: "shown", "citation only" or "held back".
    - `member_incomplete`: "<thread> is still being recorded."

    It offers "Redraft": re-preview, keep the selection and the question, fetch a fresh estimate and open a new session. It never regenerates silently (§1.10, "Staleness means exactly that the preview digest changed").
  - `draft_failed` (rev 9): from `thread.merge_draft_failed`, or from a replayed POST. Each reason has one copy, and each shows the charge by the nullable rule:
    - `cap_reached`: rendered as `refused_capped`, below.
    - `unresolved_claim_ref`: "The model cited something it wasn't given, so this draft can't be used. Charged: <cost>." It offers "Try again".
    - `unavailable`: "The model isn't available." It offers "Choose another model", which returns to `estimating`.
    - `interrupted`: "It stopped before finishing. Charged: <cost>." It offers "Try again".
    - `cancelled`: "You cancelled this draft. Charged: <cost>."
    - `failed`: "It failed before finishing. Charged: <cost>." A known `detail` sub-code gets its own sentence. Any other `detail` is logged and never shown, and the fixed sentence stands (rev 9; §2.11's rule; needs Part 1, R9-11: a closed `detail` set for `thread.merge_draft_failed`). It offers "Try again".

    **Retry and Try again are different** (rev 9; §1.10, "A retry under that key replays the refusal. A new press mints a new key."):
    - A retry of the same POST after a lost answer reuses the press's key. It never spends twice, and it replays the first answer, a recorded failure included.
    - "Try again" after a recorded failure is a new press. It mints a new key, shows a fresh estimate first, and stays in the same session (`merge_id`) while the digest is unchanged.

    This replaces §A5's "Retry replays the same `idempotency_key`, with no new spend", because a replay cannot produce a new draft.
  - `refused_capped` (rev 9): a `402 refused_capped` on the draft, or a draft that failed with `cap_reached`. The copy is "Today's cap has no room for this draft. Nothing ran." It offers "Raise today's cap", which is legitimate because merge drafts are cap-admitted (§1.13, "merge-draft generation"). After the cap is raised, drafting is a new press, judged afresh. A refusal on one draft never blocks a later draft of the same session (§1.10, "The cap halt is scoped per draft").
  - `already_merged` (rev 9): a draft, revise or commit answered `409 merge_committed`, with `thread_id`, because the session was already accepted, for example on another device (§1.10, "One commit per session"). The copy is "This merge was already accepted", with one key to open the thread.
  - `failed`: the commit answered `503 {reason: merge_pending, merge_id, thread_id}`. The merge is decided, but delivery is incomplete.
    - The copy is "The merge didn't finish. Nothing has run yet." Rev 9 adds a second line: "It's saved and will finish on its own. Retry checks now."
    - Retry uses the same idempotency key and answers 200 once delivery completes. Meanwhile, members read "Merging into …" (`merge_pending`, §2.4).
    - Nothing ever runs at a commit, so "Nothing has run yet" stays true (§1.10, "Zero dispatches").
  - `suggestion`: an automatic merge offered through the inbox (`thread.merge_suggested`, inbox kind `merge_suggestion`). It opens in `selecting` with the suggested members pre-selected, and it is never applied silently.
- **Needs** (§1.10):
  - **The preview:** `POST /threads/merge/preview {thread_ids[]}` returns:
    - `preview_digest`;
    - `items[{item_id, content: GatedText, origin_thread_id}]`, each `content` rendered by §2.10. `item_id` is stable across previews (rev 9).
    - `conflicts[{claim_a, claim_b, reason}]`;
    - `incomplete_members[{thread_id}]` (rev 9).

    It is free and writes nothing.
  - **The estimate** (rev 9): `POST /threads/merge/draft/estimate {thread_ids[], preview_digest, question, model_choice?}` returns:
    - `estimate_cents | null` and `max_cents | null`;
    - `reason?: "unavailable"`;
    - `assumptions {input_tokens, max_tokens, extras_cap_cents, model, given_items, not_shown_items}`.
  - **The draft** (rev 9): `POST /threads/merge/draft {thread_ids[], preview_digest, question, model_choice?, merge_id?, project_id, mothership, confirm_unpriced?, idempotency_key}`.
    - `project_id` and `mothership` are the active project and mode (`research | writing | reading`). They attribute the spend and name the merged thread's home project.
    - `merge_id` is sent only while the preview digest is unchanged (see `preview_stale`).
    - Lane A sends no other field. An unknown field is refused (§1.0a).
    - **Answers:**
      - `202 {merge_id, draft_id, state: "drafting"}`;
      - a replay after the draft has finished answers `200` with the full draft shape.
    - **Refusals, in the server's order:**
      - `404 thread_not_found`, `403 not_owner`: as in `previewing`.
      - `404 project_not_found`: "This project no longer exists."
      - `409 preview_stale`: goes to `preview_stale`.
      - `409 merge_committed`: goes to `already_merged`.
      - `422 members_incomplete {thread_ids[]}`: the "Still being recorded" copy.
      - `422 no_served_items`: the "Nothing servable" copy.
      - `402 refused_capped`: goes to `refused_capped`.
      - `422 confirmation_required · unpriced`: the price became unknown after the estimate. The "Cost unknown. Draft anyway?" confirmation shows again, and nothing was written.
      - `422 unresolved_claim_ref` (on a replay): goes to `draft_failed`.
      - `422 members_invalid`, `404 merge_not_found` and `409 idempotency_conflict`: lane-A bugs.
  - **The read** (rev 9): `GET /threads/merge/{merge_id}/draft?draft_id=` returns:
    - `merge_id`, `member_ids[]`, `preview_digest`, `project_id` and `mothership`;
    - `draft`;
    - `lineage[{draft_id, parent_draft_id, state, origin: model | operator, created_at}]`;
    - `committed: {target, thread_id, draft_id, committed_at} | null`.

    It carries everything needed to reopen the flow, so an inbox item or a reload needs no local state. A `404 merge_not_found` or `404 draft_not_found` reads "This merge draft no longer exists" (§1.15, "Existence is never disclosed").
  - **The draft shape** (rev 9; lane A's §A5 fields plus Part 1's additions):
    - `merge_id`, `draft_id`, `parent_draft_id`, `state`, `draft_digest`;
    - `synthesis: GatedText` (only `served` or `withheld`), `edit_text | null` and `sentences[{index, start, end, text | null, origin, claim_id | null, item_ids[]}]`;
    - `claims[{claim_id, text | null, item_ids[], source_refs[]}]`;
    - `answer_provenance {retrieved_refs[], cited_refs[], presentation_mode}`;
    - `grouping[{origin_thread_id, item_ids[]}]`, `conflicts[]` and `not_shown[{item_id, gate, reason}]`;
    - `measures {sentences, referenced, generated, unsourced, operator}`, `preview_digest` and `question`;
    - `cost_cents | null` and `model {provider, model, dispatch_event_id}`.

    A failed draft's reason is needed on this read (needs Part 1, R9-9).
  - **Revise** (rev 9): `POST /threads/merge/draft/{draft_id}/revise {synthesis_text, idempotency_key}` returns `201` with the full draft shape. It takes no model call and no spend.
  - **Cancel** (rev 9): `POST /threads/merge/draft/{draft_id}/cancel {}`. What it answers while the draft is still drafting (needs Part 1, R9-10).
  - **The commit** (rev 9): `POST /threads/merge {thread_ids[], preview_digest, draft: {draft_id, draft_digest}, question, target: "new_thread" | {into_thread_id}, idempotency_key}`. Lane A always sends `target`.
    - **Answers:** `200 {merge_id, target, thread_id, merged_from[], state: "committed"}`, or `503 {reason: merge_pending, merge_id, thread_id}`.
    - **Refusal copy:**
      - `404 thread_not_found` or `403 not_owner` on a member: as in `previewing`, then a re-preview.
      - `422 target_unavailable`:
        - `agents_unavailable`: "Agents aren't available yet." "Accept into agent…" stays disabled with that reason.
        - `not_an_agent`: "<name> isn't an agent."
        - `target_is_member`: "An agent can't be merged into itself."
      - `404 thread_not_found` on `into_thread_id`: "That agent no longer exists."
      - `403 not_owner` on `into_thread_id`: "This merge can't be added to that agent." The copy never says whose agent it is (rev 9).
      - `422 project_shared`: "This agent serves a shared project, so a merge can't be added to it."
      - `409 draft_not_ready`: "The draft isn't finished yet." Accept is disabled while drafting, so this is rare.
      - `409 preview_stale`, `409 draft_stale` and `409 merge_committed`: their states above.
      - `422 draft_required` (`absent`, `digest_mismatch`, `members_differ` or `question_differs`), `404 draft_not_found` and `409 idempotency_conflict`: lane-A bugs. Lane A logs them, re-reads the draft, and never shows them.
  - **Idempotency keys** (rev 9). Lane A mints one key per press and reuses it only for retries of that press:
    - one per Draft, Try again or Redraft;
    - one per Save of an edit;
    - one per Accept.

    A new preview mints new keys. The commit key is bound to the owner, the members, the digest, the reviewed conflicts, the question, `draft_digest` and `target` (§1.10, rev 4 plus rev 9). A `409 idempotency_conflict` anywhere means lane A reused a key for a different request. That is a lane-A bug: log it, mint a fresh key and re-preview. It is never shown as the operator's error.
  - **The result.** Each member records `merged_into` and is never otherwise changed. A target agent receives one `thread.merged_in`. `merged_from[]` and `merge_ids[]` come from `ThreadSummary` (§1.2).
- **Reacts to:**
  - **Draft events.** The socket nudges on `thread.merge_drafted`, `thread.merge_draft_failed` and `thread.merge_draft_revised`. Lane A refetches the owner-scoped read and never renders text from the socket (§1.10, "Clients refetch through the owner-scoped read").
  - **The inbox kind `merge_draft_ready`** (rev 9; §1.13 "Inbox kinds added by rev 9"), with `ref {merge_id, draft_id}` and `detail {state, reason?}`. The row copy is §2.8's. It opens the flow at `draft_review` or `draft_failed` from the read.
  - **Commit events.** `thread.merge_started`, each member's `investigation.merged_into`, the merged thread's `investigation.start_requested` and `thread.merged_in` update the member rows (§2.4) and open the merged tab.
  - **`project.members_changed {cause: merge_commit}`:** the project's thread list gains the merged thread.
  - **`thread.merge_suggested`**, through the inbox's `merge_suggestion`: opens `suggestion`.
- **Retirements (rev 9):**
  - **The compose page.** `/research/artifacts/compose*` answers `410 {reason: "retired", alternatives: ["thread_merge"]}`. Lane A removes the `target="_blank"` compose page. "Saved chases" and "Draft merge" open `selecting`, and an old link that meets the 410 opens `selecting` in the pane.
  - **`merge_failed`.** The rev-3 member state is retired (§1.10, "`merge_failed` is retired"). Members read `merge_pending` until the merge is delivered, and "Merge didn't complete" is never shown on a member.

### 2.6 Merge into document → fork (A4, lane B B4)

**Refusals (rev 9).** These follow §2.5's rule: top-level `{reason, detail?}`, narrowed on `reason` and then `detail`, and no code reaches the UI. A `422` on a route whose body lane A builds is a lane-A bug unless this section gives copy for it.

- **States:**
  - `choose_target`: a Write deliverable in this project. "Project" is the UI noun (rev 9; D-P).
    - **The list** is the `members[]` of `GET /projects/{id}` whose `member_kind` is `deliverable` (rev 9; §1.5, "`GET /projects/{id}` returns the row plus `members[]`").
    - `derived_asset_id = "write:<deliverable_id>"` is the only target (§1.11).
    - Write blocks are not a merge target. In W3 they gain thread provenance instead.
    - **No deliverable yet.** A project with no deliverable offers "Create a deliverable from this thread": `POST /write/deliverables/from-investigation {investigation_id, idempotency_key}`. Rev 9 makes the route owner-checked, atomic and idempotent by key (§1.11, "Rev 9 repairs it").
      - Lane A mints the key per press and reuses it on retry.
      - The copy per refusal:
        - `404 thread_not_found`: "This thread no longer exists."
        - `403 not_owner`: "A deliverable can't be started from that thread." The copy never says whose thread it is (rev 9).
        - `404 no_synthesis`: "This thread has no finished write-up to start from yet."
        - `409 idempotency_conflict` and `422 node_not_in_synthesis`: lane-A bugs, logged and never shown.
      - **Joining the project.** The new deliverable joins this project through `POST /projects/{id}/members {member_kind: deliverable, member_id: <deliverable_id>}`, which is idempotent by its natural key. Whether from-investigation files it itself (needs Part 1, R9-12).
  - `drafting`: `POST /derived-assets/{asset_id}/merge-drafts {source}`.
  - `diff_review`: accept or reject, per hunk.
    - Every hunk starts undecided, and nothing is decided by default.
    - Commit stays disabled, with the reason shown, until every hunk is decided.
    - The decisions go to `POST /merge-drafts/{draft_id}/review`, which returns the `review_id`.
    - **Mostly generated.** When the source revision is `mostly_generated`, the review needs an explicit confirmation: "Most of this is generated or unsupported. Merge it anyway?"
      - The confirmation is sent on the review, as typed `acknowledgements: ["mostly_generated"]` on `POST /merge-drafts/{id}/review`, and bound into its `review_id` (rev 8.5).
      - The commit keeps its literal `acknowledgement: "new_revision"`.
      - Without the confirmation, Commit stays disabled with that reason.
      - A `422 acknowledgement_required {missing}` on commit is a lane-A bug.
  - `committing`: `POST /derived-assets/{asset_id}/revisions {review_id, acknowledgement: "new_revision", idempotency_key}`. Only the explicit commit button sends the literal (R3-6).
  - `forked`: the new revision and its lineage (`GET /derived-assets/{asset_id}/revisions`). The original revision is untouched and one click away.
    - The first operation on a deliverable writes revision 1 from its current content (§1.11). The lineage labels it "Revision 1, as it was before the first merge", so the first fork always has an original to return to.
  - `base_moved`: the compare-and-set refused the commit with `409 revision_moved`, because the current revision moved after the review.
    - Say "The document changed while you reviewed", then re-draft against the new revision.
    - A decision carries over only to a hunk with the same `hunk_digest`: sha256 over its anchor and canonical `insert` (§1.11, rev 6). Every other hunk comes back undecided.
  - `failed`: "The merge into the document didn't complete. The document is unchanged." It offers Retry, which uses the same idempotency key (rev 9 copy).
- **Needs:**
  - **`source`:** `{thread_id} | {companion_entry_id}`.
    - A companion entry's id is node-keyed in rev 9, so it survives a refinement of the note (§1.12, "A node-backed entry's id is sha256 over").
    - **A merged thread as the source** (rev 9). Its outcome is the accepted draft on its merge session, not a synthesis of its own (§2.5). How a merge draft into Write is built from it, and how each sentence's `origin` maps to a member class (needs Part 1, R9-13). Until then, "Merge into a deliverable" on a merged thread is disabled with "Merging a merged thread into a deliverable isn't available yet."
  - **`target_asset_id`:** `write:<deliverable_id>`.
  - **From the draft:** `draft_id`, `base_revision_id`, `proposed_hunks[{hunk_id, hunk_digest, anchor, insert: GatedText}]` and `evidence_manifest` (§1.11, rev 6).
    - Each hunk renders by `insert.gate` (§2.10), and `insert.text` is the sanitized HTML:
      - `served`: the insertion, with its sources.
      - `cite_only`: the hunk offers the citation alone. Accepting it inserts a citation marker that the server builds from `insert.source_refs`, never quoted text.
      - `withheld`: the hunk cannot be accepted. Its accept control is disabled with the reason shown, and it can only be rejected. A `422 hunk_not_acceptable` on review would mean lane A sent one. That is a lane-A bug, never the operator's error.
    - Each hunk shows the provenance classes it carries, in §2.11's labels. `generated` is only validator-passed connective text. `unsupported` is its own class and holds the export back (rev 8.5). Classes survive the merge into Write (§1.11, rev 8.1).
  - **`review_id`.**
  - **Lineage fields.** `fork_id` is the new revision id, and `parent_version_id` is `parent_revision_id` (§1.11). Correction §1.1.2: this is not an HTML-projection lineage and not `create_document_version`.
  - **`lineage`:** the revision chain.
  - **The commit envelope** is exactly `{review_id, acknowledgement, idempotency_key}`. A 422 on legacy fields is a lane-A bug, not a user error.
    - The same revisions route takes a second body for a reformulation fork, `{base_revision_id, blocks, idempotency_key}` (§2.11; §1.11a rev 8.10). Lane A never mixes the two bodies.
  - **Source merge is retired, and the UI never offers it.**
    - Its routes answer `410 {reason: "retired", alternatives: ["adopt_reading_version", "merge_into_write"]}` (rev 9; §1.11, "`alternatives` names T6's two flows").
    - Lane A has no caller (#3533). If a stale path meets the 410, the copy is "Reformulations never change the source. Adopt one as your reading version, or merge it into a deliverable." It carries the two flows: §2.11's adopt and this section. This is the one copy for the retired source merge; §2.11 points here (rev 9).
    - **Restore** (rev 9). The UI does not offer "Restore the original" (§1.11, "Once #3533 lands it is reachable only through the API"). Until the operator answers Q-B1, restore is the operator's API step.
- **Serve-time gate for Write bodies (rev 8.4).** Every view of a deliverable's body re-checks each member against its source's gate as it stands now. That covers the editing view, the rendered projection, shared and public pages, and exports. Lane A renders two block states from it:
  - **Source withdrawn.** A quoted block whose source is no longer servable shows the server-built citation marker in place of the quoted words, labelled "Source withdrawn: shown as a citation". The rest of the block renders normally.
  - **Held back.** A block whose member is unresolved, legacy or unsupported shows no text and reads "Held back: <reason>". It keeps its §2.6 fixes, and the owner's editing view keeps the block visible so it can be fixed.
  - **Two gates.** The owner's editing view uses the owner-read gate. Shared, public and export views use the public gate. The same block can therefore read differently in the editor and on a shared page, and the editor labels it ("Shown to readers as a citation").
  - **No stale cache.** A changed source gate changes the render at once, because renders are keyed by the members' gate fingerprint. Lane A never caches body text client-side past a gate change.
  - **Speak testimony** (rev 9; §1.11, "The serve-time gate extends to testimony"). A block that Speak sent to Write is recomposed from its claim on every serve, never from the stored copy:
    - `withheld · unresolved`: "Held back: this testimony can't be found."
    - `withheld · not_servable`: a takedown, or a lapsed recording consent. It reads "Held back: this testimony can no longer be shown."
    - `served`: the owner's editing view shows the testimony with the claim as its source chip.
  - **Testimony that isn't cleared to leave** (rev 9; §1.11, "Share and export (rev 9; O-12's fallback)"). A share, public page or export answers `422 {reason: speak_publish_required, claim_ids[]}`. This is the one copy for it; §2.15 points here.
    - The copy is "This includes testimony from Speak that hasn't been cleared to publish (n claims). Clear it in Speak first."
    - The blocks whose source ref names one of those claims are marked in the editor, each opening its Speak request where it can be named.
    - Which Speak project to open for each claim (needs Part 1, R9-14).
    - Nothing is exported partially.
  - **An unsupported claim holds the export back** (rev 8.3). A merged `unsupported` member withholds the export of the deliverable's revision, as an unresolved member does, until it is fixed.
    - The revision reads "Held back: an unsupported claim in block N".
    - Each block names its fixes: delete the block, rewrite the claim, or attach evidence.
    - Attestation alone never clears it (rev 8.4). Generated connective text (member kind `generated`) passes.
    - **Attach evidence** (rev 8.5): `POST /derived-assets/{id}/blocks/{block_id}/evidence {source: {document_id, anchor}, expected_revision_id, idempotency_key}`. The block's unsupported sentences are re-scored one by one.
      - The answer's per-sentence scores drive the block view. Sentences that now pass lose their "Unsupported" mark and gain the evidence. Sentences that still fail stay marked, each with its score, so the operator sees exactly which sentence needs work.
      - A `409` on `expected_revision_id` rebases and re-asks.
- **Reacts to:**
  - Nothing is pushed for this flow.
  - A moved base arrives as `409 revision_moved` on commit, or on attach evidence.
  - A gate change arrives on the next read. Lane A refetches the body when the view regains focus and after any write, and never renders cached body text past a gate change.
  - A `thread.merged_in`, or a new merged thread, changes nothing here until the operator starts a merge into a document.

### 2.7 Findings tab and companion rail (D3, C4; data noun: companion document, §1.0/§1.12)

In the cockpit, the project companion document is the right pane's **Findings** tab (§1.12, rev 7; S7). The per-evidence companion rail stays inside the reader. Both are views of one model.
- **In the reading mode (rev 9).** The same document, read through `lens=reading`, is the **Notebook** tab (§2.19; §1.0 Notebook row, "The reading-mode view of the companion document"). In Books, the Notebook narrowed to the open book takes the rail's place, and the reader mounts no second companion column. In Research the rail stays inside the reader.

- **States:**
  - `loading`
  - `empty`: "No findings yet". Shown only after a real answer.
  - `error`: "Couldn't load findings." with Retry (copy rev 9).
  - `ready`
  - `stale`: the server's `state` says so, and it offers Refresh. The causes (rev 9, §1.12 "Rebuild triggers and staleness"; rev 8.11 C1 and C3):
    - newer thread events, a dialogue turn, a resolved island or a landed diligence run;
    - a shelf change (`project.shelf_changed`);
    - a new book answer on the document;
    - **drift** (rev 9; rev 8.11 C3): the served findings' hash differs from the receipt's `content_hash`, for example after a refinement logged outside the member threads, or a takedown since the refresh;
    - **never refreshed** (rev 9; rev 8.11 C1): `content_hash` is null and `entries` is empty.

    The copy per cause (rev 9):
    - an activity cause (the first three): "Newer activity since this was written";
    - drift: "The sources behind this changed since it was written.";
    - never refreshed: "These findings haven't been written yet.", with Refresh as the main action. It is never shown as `empty`.

    The body names no cause, so lane A can tell only the never-refreshed case, by its null `content_hash` (needs Part 1, R9-48). Until Part 1 names the cause, any other `stale` reads "This may be out of date: there's newer activity, or its sources changed, since it was written."

    A reading position alone never makes it stale (§1.12, "`reading.position` is struck from the staleness list"). Lane A never marks it stale on its own; only the server's `state` does.
  - `refreshing`: `POST …/companion-document/refresh` is in flight. The current entries stay readable underneath. On success, the receipt's `content_hash` replaces the old one. A failed refresh keeps the entries and says "Couldn't refresh. These findings are from before." with Retry (copy rev 9). A `503 receipt_not_written` is a failed refresh: the rows it built are never served until a retry succeeds, so the old entries stay, with that copy (rev 9; rev 8.11 C6).
  - `partial`: "n of m threads summarised", from `summarised_thread_count` and `total_thread_count` (R2-2, in rev 2). The threads not yet covered are listed by name, one click each.
  - `unavailable_until_rights`: the rights branches have not landed (§1.12 precondition). This is an honest state, never an empty one. The copy is "Findings open once source rights can be checked" (copy rev 9).
    - The GET then answers 200 with `{entries: [], content_hash: null, covered: {}, summarised_thread_count: null, total_thread_count: null, state: "unavailable_until_rights"}`. No partial line is drawn from the null counts. A refresh answers `409 unavailable_until_rights`, which shows the same copy (rev 9; rev 8.11 C1 and C2).
  - **The server's states (rev 9; rev 8.11 C1).** The wire `state` is exactly `ready`, `stale` or `unavailable_until_rights`, the three this section already names. `partial` and `empty` are lane A's derivations from the counts and entries, and `loading`, `error` and `refreshing` are request states.
- **Needs:** `GET /projects/{id}/companion-document` (tab) and `GET /documents/{id}/companion-document` (rail). Both return `{entries[], content_hash, covered: {thread_id: through_event_id}, summarised_thread_count, total_thread_count, state}`.
  - **Not found (rev 9; rev 8.11 C6).** A missing document and another owner's private document answer the same `404 document_not_found` (documents are otherwise not owner-checked: §1.5, "are corpus rows and are not owner-checked, except a private document"), and a missing project and another owner's the same `404 project_not_found`. The rail reads "This document can't be found.", and the tab takes §2.1's `not_found` copy. Either 404 comes before the rights switch, so neither discloses anything.
  - **No lens on the tab (rev 9).** The Findings tab sends no `lens`; `lens=reading` is the Notebook's (§2.19). A `422 lens_invalid` (§1.12, "Every other value, `books` included") is a lane-A bug: logged, never shown.
  - `entries[]`: `{entry_id, kind: claim|open_question|insight, content: GatedText, confidence?, thread_ids[], doc_ids[], updated_at, process_ref}` (§1.12, rev 6). The rev-5 `text` and `source_refs[]` live inside `content`. Each entry renders by `content.gate` (§2.10), never by whether a text field is empty.
    - **Held back by a source (rev 9; rev 8.11 C4).** The excerpt gate decides per member thread, so one source that can't be served withholds every entry drawn from that thread's body. The entry renders `withheld`, and its `content.source_refs` chips name the source that held it back (§2.10, "Which source held it back").
    - **Origin (rev 9; rev 8.11 C5b).** An entry's `content.origin` is `source` when it has at least one pin of its own, and `unsourced` otherwise, never `operator` or `generated`. An `unsourced` entry reads §2.10's "Unsupported: no source".
  - **Three more entry fields (rev 9;** §1.12 "Entries gain three fields"**):**
    - `anchors[]`: each opens its document as a left tab at that passage, never a navigation away.
    - `chapter?`: shown only in the Notebook's grouping (§2.19).
    - `merge_ids[]`: a chip, "In n merges". Each merge opens its merged thread, read from `GET /threads/merge/{merge_id}/draft` as `committed.thread_id` (§1.10, "Read (rev 9)"). A `404 merge_not_found` makes that chip read "That merge can't be found", with no link.
  - **Stable ids (rev 9).** An entry id is keyed to its graph node, not its text (§1.12, "never over the claim text"). A living-note refinement therefore keeps the entry's place, and lane A keys per-entry UI state (expanded, seen) by `entry_id`.
  - **Twin notes (rev 9).** Only promoted twin notes appear (§1.12, "An unpromoted twin note is never an entry"). Lane A never renders a twin note directly.
  - **Audience (rev 9).** The GET is owner-read (§1.12, "The GET is owner-read"). The operator's own `personal_reading` quote renders `served` here. Anything exported or shared uses the public audience, where that quote is `cite_only`.
  - the process link for each entry: `process_ref`, the object `{thread_id, event_id}` (rev 8.11 C6), one click deep to that step of the trajectory
  - a per-document filter, for the rail
  - a link to the agent-facing evidence base. Lane A renders only this link. For a thread it is the MCP resource `antiek://threads/{id}` (§1.12, "MCP resources"), shown as copyable text because a browser cannot open it. It is not shown until the MCP hardening merges, so it is never a dead link. The project-level resource is (needs Part 1, R9-15).
- **Reacts to** (rev 9; §1.7, "a client treats every push as a nudge"):
  - `companion_document.refreshed` for this scope: refetch. A receipt whose `lens` is `reading` belongs to the Notebook (§2.19).
  - thread terminal events, `thread.turn`, `project.members_changed` and `project.shelf_changed` for the project: refetch to read the server's `state`. The tab never infers staleness locally.

### 2.8 Flags, consent and the attention inbox (D4, lane B B5)

Rev 9 reconciles this section to Part 1 §1.13: "Unified flags (rev 9, LB-32)", "Spend classes (rev 9)", "Halt scope (rev 9; amends rev 7's thread-wide halt)" and "Inbox kinds added by rev 9". Every refusal arrives as top-level `{reason, detail?}` (§1.0a, "Every refusal that rev 9 adds or changes answers top-level JSON"). Lane A narrows on `reason`, and then on `detail` where the reason defines a closed sub-code. No status code and no code string reaches the screen (rev 9).

- **What can be flagged, and for which intent (rev 9).** Part 1's store table decides this (§1.13, "Where each target goes (rev 9)"):

  | Target | Read later | Diligence |
  |---|---|---|
  | `{insight_id}` | yes | yes |
  | `{question_id}` | yes | yes |
  | `{concept: key}` | no | yes |
  | `{anchor}` (a passage) | yes | no |
  | `{claim: {event_id, chunk_id?, edge_id?}}` (R3-4) | yes | no |
  | `{document: {document_id, anchor?}}` | yes | no |

  - Lane A offers "Diligence this" only where the table says yes. On a passage, a claim or a document, the flag menu offers "Read later". For diligence it says "Diligence isn't offered here. Start research on it instead." and points to the immediate verbs (§2.3). The rev-5 diligence flag on an anchor or a claim is withdrawn (rev 9). The diligence queue cannot hold those targets (§1.13, "A diligence flag therefore cannot target `{anchor}`, `{claim}` or `{document}`").
  - **On agent output** (§1.4b), Flag sends the segment's `node_id`: `{insight_id}` for role `insight`, and `{question_id}` for role `open_question`. Thesis and component segments have no `node_id`, so Flag is disabled there, with §2.3's copy: "Only an insight or an open question can be flagged. Harden tests this claim now." Flag never sends an anchor, because there is no output-anchor flag target (§1.13, "Flagging agent output for diligence"; rev 9).
- **Flag states:**
  - `flagged`
  - `reserved`: a question escalated to research whose child id is reserved but has not launched (§1.3). It says "Research reserved, not started". Starting it goes through consent like any diligence launch.
  - `consent_pending`: shows the model, the estimate `{cents, basis}`, and whether the launch fits.
    - X is the conservative maximum: the estimate × 1.5, or the tier's maximum when that is larger (§1.13). The sheet compares X with `daily_cap_cents − spent_today_cents − held_today_cents`, which is the ledger's own `remaining` (R4-1, applied in rev 4). From rev 9, `spent_today_cents` includes record-only spend: conversations, voice and Speak intake (§1.13, "`record_dispatch`, record-only settlement").
    - The copy is exactly "Starts if $X of today's cap is free; it pauses if the cap runs out" (§1.13, rev 5). Admission reserves nothing, so nothing on the sheet says "held".
    - When X does not fit, the sheet says so before Accept ("$Y of today's cap is free") and offers "Raise today's cap". Accept stays available, because the server's admission is the authority and a refusal lands as `refused_capped`.
    - When `held_today_cents` is null, or `spent_today_cents` is null because the ledger can't be read, the sheet shows "Free cap today: unknown". Accept is disabled with "Can't check today's cap right now", because admission cannot be checked against an unreachable ledger.
    - **(rev 9)** When `spent_today_cents` is null because a cost today is unknown (`cost_unknown`, §1.13, "is recorded as `actual_cents: null, cost_state: unknown`"), the sheet shows "Free cap today: —", and the reason on hover and focus is "A cost today is unknown". Accept stays available, with the line "The server checks the cap when you accept." The ledger is readable in this case, and the server still admits against its own balance. Part 1 says `spent_today_cents` reads null with `reason: "cost_unknown"` (§1.13, "An unknown cost"), but not where that `reason` sits on `GET /settings/budget`, for example `null_reasons.spent_today_cents` or a sibling `spent_today_reason` (needs Part 1, R9-16). Until it is placed, lane A reads a null `spent_today_cents` with no readable reason as an unreachable ledger. §2.5 and §2.14 use this split.
    - When the estimate's status is `unavailable`, consent is not offered. The sheet shows the reason and "Choose a priced model" (R3-2).
  - `consent_unavailable` **(rev 9)**: the consent routes are the rev-3 routes that W2 builds, and they are not on main (§1.13, "Diligence consent and launch do not exist on main"). While they are absent, "Diligence this" saves the flag and says "Starting flagged work isn't available on this server yet. Your flag is kept." Lane A needs a signal that tells an absent route apart from a missing flag (needs Part 1, R9-18). Until one exists, lane A reads a consent-route 404 that has no `reason` as this state.
  - `queued`
  - `running`
  - `done`
  - `failed`: the spawned thread failed. Its copy is §2.4's thread failure copy, from `failure_reason` and `failed_before_start` only, never from the per-thread GET's `terminal_payload.reason` (rev 9; rev 8.11 A10).
  - `consent_stale`: the launch answered `409 consent_stale` because the target moved after consent. The target is the thread's head event, or the anchor's text hash (§1.13). The copy is "This changed since you agreed", with the fresh estimate and one step to agree again.
  - `stopped`, with its reason (R5-4):
    - `cap_reached`: other work used today's cap after admission. It offers "Raise today's cap".
    - `cap_overshoot`: a provider billed past a bounded call. It shows the billed amount, because the overshoot is never hidden.
  - `refused`, with a reason from `question.diligence_refused`:
    - `refused_capped` offers "Raise today's cap"
    - `unavailable` offers "Choose another model"
    - `failed` reads "It couldn't start." A known `detail` sub-code gets its own sentence; any other `detail` is logged and never shown (rev 9; §2.11's rule; needs Part 1, R9-11). It offers Retry.
  - `declined`

  A consent is single-use. A retry after any refusal is a fresh consent: one step, with a fresh estimate. A double press is safe, because the launch consumes the consent idempotently by `consent_id`.

- **How the server's flag state maps to these states (rev 9).** `GET /flags` projects its own `state` (§1.13, "`state`:"). Lane A derives the UI state from it and never invents one:

  | Intent | Server `state` (and `outcome`) | UI state |
  |---|---|---|
  | diligence | `queued` | `flagged`. It becomes `consent_pending` while the sheet is open, and `refused` or `consent_stale` when the latest consent lifecycle event says so. |
  | diligence | `spawned` | the spawned thread's own state, read through `spawned_thread_id`: `queued` or `running` |
  | diligence | `done`, `outcome: completed` | `done` |
  | diligence | `done`, `outcome: failed` | `failed` |
  | diligence | `done`, `outcome: stopped` | `stopped`, with the reason from the spawned thread's `stop_reason` (§1.2) |
  | diligence | `done`, `outcome: null` | `done`. The result line reads "—", with the reason "Outcome not recorded". |
  | diligence | `dismissed` | `declined` |
  | read | `open` | `flagged` ("To read") |
  | read | `done` | `done` ("Read"): its question was sharpened |
  | read | `declined` | `declined` |

  - The list projection does not carry the consent lifecycle. A `refused` or `consent_stale` row that survives a reload needs it on the item (needs Part 1, R9-17). Until then, lane A shows those two states only while the consent events are in hand. After a reload the row reads `flagged`, and Accept re-runs the fresh consent, which is honest because every consent is single-use.
  - **Legacy rows.** `actor: null` with `actor_reason: "legacy"` renders "Flagged by: —", with the reason "Flagged before flags recorded who". `project_id: null` reads "Not filed under a project".

- **Accept is two calls behind one press.** `POST /flags/{flag_id}/consent` returns the `consent_id`, then `POST /flags/{flag_id}/launch {consent_id}` runs it (§1.13, rev 3; built in W2).
  - If the launch call fails after the consent has landed, Retry re-sends the launch with the same `consent_id`, so a retry never asks twice.
  - Run-now on a diligence flag always opens this consent sheet. The manual run-now at `/watch-for-later/{question_id}/launch` never bypasses it (§1.13, "stays the manual \"read/run now\" action").
- **Declining (rev 9).** Decline is `POST /flags/{flag_id}/decline`. For a diligence flag it is the shipped dismiss. For a read flag it writes `question.flag_declined` (§1.13, "`POST /flags/{flag_id}/decline` (rev 9 clarification)"). It is idempotent, so a second press returns the declined flag. A `404 not_found` reads "That flag no longer exists", and the list refetches.
- **Flagging (rev 9).** `POST /flags {intent, target, reason?, project_id?, source?: {thread_id?, document_id?}, idempotency_key}` (§1.13, "`POST /flags` (rev 3 shape, rev 9 fields)").
  - Lane A mints one `idempotency_key` each time the flag sheet opens, and never sends `actor`.
  - `reason` holds at most 280 characters. The field shows a counter from 240 and stops input at 280.
  - `source` names where the flag came from: the thread whose output or answer was flagged, or the document it was read in.
  - **Outcomes:**
    - `201` reads "Flagged".
    - `200` reads "This is already flagged". It covers an active row returned untouched and a dismissed row revived to `queued`.
    - When the returned `project_id` differs from the one sent, the row adds "It's filed under <project>." The server sets `project_id` on insert only.
  - **Refusals:**
    - `422 target_invalid · target_not_supported_for_intent` reads "This can be saved to read later, not sent for diligence", and offers Read later. The menu never offers that pairing, so reaching it is logged as a lane-A bug.
    - `422 target_invalid` on a read concept reads "A concept can't be saved to read later."
    - `422 target_ungrounded` reads "That question or insight no longer exists."
    - `422 reason_too_long` reads "Keep the reason under 280 characters."
    - `422 source_ungrounded` reads "The thread or document this came from can't be found."
    - `404 project_not_found` reads "That project no longer exists", and offers to flag without a project.
    - `409 idempotency_conflict` means a stale sheet. Lane A refetches the flag list and never shows it as the operator's error.
    - `422 intent_invalid` and `422 flag_body_invalid` (for example `· actor`) are lane-A bugs. They are logged, and the sheet reads "Couldn't save the flag. Try again."
- **Continuing a managed thread (rev 9).** Until the operator rules on O-11, each continuation of a managed agent is an ordinary diligence flag on one of that thread's open questions: `{intent: diligence, target: {question_id}, source: {thread_id: <the managed thread>}, project_id}` (§1.13, "Continuing a managed thread (rev 9; LB-28's per-flag fallback)"). It goes through this consent sheet like any other diligence flag, and nothing standing is written (D4). §2.16 says where it starts.
- **Who can hit the cap (rev 9).** "Raise today's cap" appears only on cap-admitted work: diligence launches, autonomy continuations, reformats (including monologue text and the notebook write-up), monologue audio and merge drafts (§1.13, "Who can hit the cap (rev 9 amendment of rev 6)"). It never appears on an ask, a Converse turn, a transcription or a spoken reply. The settings page adds one line: "Conversations, voice and Speak answers count toward today's spend but never stop at the cap." That is O-16's fallback. If the operator rules those calls cap-admitted, this line is removed, and `refused_capped` renders on ask, transcribe and TTS (§2.13, §2.20).
- **Inbox item kinds** (§1.13):
  - `thread_done`
  - `thread_needs_you`
  - `flag_consent`
  - `refused_capped` (rev 1's `cap_reached`, renamed to match Part 1)
  - `run_stopped`: a run the cap halted mid-flight, sourced from `investigation.cap_halted`. It covers a diligence launch, a daemon spawn or autonomy continuation, and a reformat generation's text (reformat engagements are cap-admitted, §1.13 rev 8.1). Its `detail` is `{reason: cap_reached | cap_overshoot, hold_cents, billed_cents?}` (§1.13, rev 6). A merge draft or an audio segment never raises it (rev 9): their cap halts are scoped to one dispatch and arrive as the flow's own failure (§1.13, "It never writes `investigation.cap_halted`").
  - `merge_suggestion`
  - `merge_draft_ready` **(rev 9)**: `ref {merge_id, draft_id}`, `detail {state, reason?}`, from `thread.merge_drafted` or `thread.merge_draft_failed` (§1.10; §1.13, "Inbox kinds added by rev 9").
  - `monologue_ready` **(rev 9)**: `ref {thread_id, derived_asset_id, revision_id}`. It fires on the last chapter's text for `delivery: text`, or the last chapter's audio for `delivery: audio`. A monologue that fails or stops has no inbox kind (needs Part 1, R9-19).
  - `speak_answer_received` and `speak_claims_proposed` **(rev 9)**: `ref {speak_project_id, interview_id}`, from Speak's own log (§1.20).
- **Inbox row copy (rev 9).** Each row names its subject from the ref's own read. A ref that can't be read keeps its row, which says "This item's source can't be opened" and still offers Mark seen, so no row is ever dropped. Rows that need an action sort first, as in the design model's inbox.

  | Kind | Copy | Action |
  |---|---|---|
  | `thread_done` | "<thread> finished" | Open |
  | `thread_needs_you` | "<thread> needs you" | Open |
  | `flag_consent` | "A flag is waiting for your consent: <reason, else the target's title>" | Opens the consent sheet |
  | `refused_capped` | "Didn't start: today's cap is used up" | "Raise today's cap" |
  | `run_stopped`, `cap_reached` | "<thread> stopped: today's cap ran out" | "Raise today's cap" |
  | `run_stopped`, `cap_overshoot` | "<thread> stopped: billed $B against a $H hold" | "Raise today's cap" |
  | `merge_suggestion` | "A merge is suggested" | Opens the merge at `selecting`, never applied silently |
  | `merge_draft_ready`, `drafted` | "Merge draft ready to review" | Opens the draft stage (§2.5) |
  | `merge_draft_ready`, `failed · cap_reached` | "Merge draft didn't finish: today's cap ran out" | "Raise today's cap", then draft again |
  | `merge_draft_ready`, `failed · cancelled` | "Merge draft cancelled" | Open |
  | `merge_draft_ready`, any other failure | "Merge draft failed" | Opens the draft stage with its reason |
  | `monologue_ready` | "Your explanation of <project> is ready" (§2.14's copy) | Opens the player on that revision (§2.14) |
  | `speak_answer_received` | "A new answer arrived in <Speak request>" | Opens `/speak/:projectId` (§2.15) |
  | `speak_claims_proposed` | "Claims were proposed from an interview in <Speak request>" | Opens `/speak/:projectId` (§2.15) |

- **Inbox states (rev 9):**
  - `loading`
  - `ready`
  - `empty`: "Nothing needs you". Shown only after a real answer.
  - `unavailable`: `/inbox*` is W3's route (§1.18, "`/inbox*` (W3's inbox)"), and it may not be on the server yet. The inbox reads "The inbox isn't available on this server yet." Its badge renders "—" with that reason, never 0. This is the same distinction Speak draws with `inbox_absent` (§1.20, "It stays `null` with `inbox_absent` until the W3 inbox lands"). Telling it apart from an ordinary error needs a signal (needs Part 1, R9-18).
  - `catching_up`: after a reconnect, lane A fetches from its last cursor. The badge keeps its last value and is marked "Catching up".
  - `offline`: rows stay as last fetched, marked "Offline — may be out of date".
  - `error`: "Couldn't load the inbox", with Retry.
- **Needs:**
  - `flag_id` **(rev 9)**: server-minted and opaque to lane A. It is `dfl-…` for a diligence flag and `rfl-…` for a read flag. A read flag's `flag_id` is its `question_id`.
  - `intent`: `read | diligence`
  - `actor {kind: user|agent, id} | null`, with `actor_reason?: "legacy"`. It is server-derived, and lane A never sends it. The label is derived too: "You" for the operator's own id, otherwise the agent's role name. No rev-9 route writes an agent actor (§1.13, "Every rev-9 route acts as `{kind: user, id: <owner>}`"), so the agent label waits for a later revision.
  - `target`: one of the forms in the table above. Flag-a-claim sends the retrieval event that stated the claim, plus its pointer, and is read-only from rev 9.
  - `reason: string | null`
  - `project_id: string | null`
  - `source` (POST only). The list items do not echo it (needs Part 1, R9-20).
  - The diligence projection: `outcome: completed | failed | stopped | null`, `spawned_thread_id | null`, `receipt | null`.
  - The read projection: `document: {document_id, title, document_type, gate, reason} | null` and `document_reason: null | "unresolved_document"`. `gate` and `reason` are flat and come from §1.5's one projection (§1.5, "One gate projection (rev 9)"). They render by §2.10, and the unresolved row is §2.9's.
  - The consent lifecycle: `question.diligence_consented`, `…_declined`, `…_launched` and `…_refused` (§1.13, "Diligence consent and launch do not exist on main"; W2's bump).
  - `daily_cap_cents`, `spent_today_cents | null` and `held_today_cents | null`, from `GET /settings/budget`. The sheet refetches these each time it opens and never reuses a figure from an earlier open.
  - "Raise today's cap": `PUT /settings/budget/daily-cap {cents}` (§1.13, rev 4). It takes effect for the next admission and re-opens an exhausted day. Lowering the cap below spent + held blocks new work but never cancels running work. The settings copy says exactly that.
  - **The flag list (rev 9)**: `GET /flags?intent=read|diligence&project_id=&cursor=&limit=` returns `{items, next_cursor}` (§1.13, "`GET /flags?intent=read|diligence&project_id=&cursor=&limit=` (rev 9)").
    - `intent` is required, so lane A keeps two lists with two cursors.
    - Items come newest first, and `limit` runs from 1 to 100. Paging stops on a null `next_cursor`.
    - Until the project filter ships, `?project_id=` answers `422 project_filter_unavailable`, never an unfiltered list. The list then reads "Filtering by project isn't available yet", and offers "Show all flags". Legacy rows with a null `project_id` appear only without the filter.
    - Lane A moves its callers off the aliases `GET /watch-for-later` and `GET /diligence/queue`.
  - **The list states (rev 9):**
    - `loading`
    - `empty`: "No flags yet". Shown only after a real answer.
    - `error`: "Couldn't load your flags", with Retry.
    - `filter_unavailable`
    - `ready`
  - **The inbox:**
    - `GET /inbox?after=<cursor>&limit=` returns `{items[{item_id, kind, ref, created_at, seen_at?}], next_cursor}`, and `POST /inbox/{item_id}/seen` marks an item seen.
    - The socket only nudges a refetch. On reconnect, lane A fetches from its last cursor, so nothing is missed while offline.
    - `item_id` is the source event id, so a nudge and a catch-up never duplicate a row.
    - An item is unseen while it has no `seen_at`. That drives only the inbox's own badge, never the project's `done_unseen` (§1.5).
- **Reacts to (rev 9):**
  - `question.identified` and `question.flag_declined` on the socket (§1.7): refetch the read list.
  - The consent lifecycle events: refetch that flag.
  - A spawned thread's state events and `investigation.cap_halted`: refetch that flag's row.
  - Any inbox nudge: fetch from the last cursor.
  - "Raise today's cap" returning: refetch `GET /settings/budget` and re-judge an open sheet's fit.

### 2.9 Books home and the to-read queue (D5; rev 9: R22, R31, ruling 1)

**The product label is "Books" (rev 9).** Every data name stays `reading` (§1.0, "Books is a label, and `reading` is the data name"): the mode key, `?product=reading`, `kind: reading` and `lens=reading`. The routes `/library` and `/read/:documentId`, the `read.*` events and ⌘E stay. `/books` is only a brand-alias redirect in the app. The API prefix `/books*` serves book assets and has nothing to do with the label. "Your readings" becomes "Your books".

- **Doors (rev 9):**
  - `continue` ("Continue")
  - `to_read` ("To read")
  - `new` ("New": a book or an interest)
  - `your_books` ("Your books", renamed from "Your readings")
  - `from_research` ("From a research project", the ruling-11 link)
- **Continue — Needs** (§1.14):
  - **The list (rev 9).** `GET /reading/continue?limit=` (§1.14, "`GET /reading/continue?limit=` (NEW, rev 9, LB-14)") replaces the rev-8 route, which never existed on main. Lane A sends the default limit, 20. Items are `{document_id, title, author, document_type, gate, reason, progress: {page_index, page_count, pct} | null, updated_at}`, newest first.
  - `GET /books/{id}/reading-state` reads one position from the `reading_state` table, the store of record (§1.14, rev 8.1). The position is synced per account and replaces the old per-browser-tab `sessionStorage` value.
  - **Progress (rev 9).** A null `progress` renders "—" with the reason "Page count unknown". It is never "0%" (§1.14, "a 0 count reads null, never 0%"). Non-book and flowing documents always read "—".
  - **Gate (rev 9).** `gate` and `reason` are flat, from one projection (§1.5, "One gate projection (rev 9)"), and render by §2.10:
    - `served`: a normal row. This includes the operator's own `personal_reading` document.
    - `cite_only · not_servable`: the row opens the reader's bounded preview and says "Preview only: this can't be shown in full here".
    - `withheld · not_servable` (taken down): "This document was taken down. Your place is kept." No text opens.
    - `withheld · unresolved`, with `title: null` (§1.14, "A row whose document is gone lists with `title: null`"): "Couldn't find this document. Your place is kept." It is never dropped.
  - **Row kinds (rev 9).** A non-book is marked from `document_type` ("Article", "Paper", "Web page", otherwise "Document"). A `document_type: "derived"` row is a reformulation's reader view, labelled "Reformulation", and it opens that view (§2.11). One that belongs to a monologue resumes the player at the start of its segment (§1.14, "Listening positions (rev 9, LB-31)"; §2.14).
  - **Where a row opens (rev 9).** When the operator has a `kind: reading` project whose `primary_document_id` is that document (from `GET /projects?product=reading`), the row opens that project's Books cockpit with the reader as tab 1. Otherwise it opens `/read/:documentId`.
  - **Busy (rev 9).** `503 reading_busy` (§1.14, "`503 {reason: reading_busy}`") reads "Couldn't load where you left off. Trying again in a moment." with Retry. It never renders as an empty row.
- **Continue — states (rev 9):**
  - `loading`
  - `empty`: "Nothing to continue yet". Shown only after a real answer.
  - `error`: a network failure or another 5xx. "Couldn't load where you left off." with Retry.
  - `busy`: the `503 reading_busy` copy above.
  - `ready`
- **Writing the position.** `PUT /books/{id}/reading-state {page_index, anchor_ref?, revision}` is the only writer (§1.14, rev 8.1). `revision` is the one lane A last saw.
  - **The 409 (rev 9).** `409 {reason: "reading_state_stale_revision", current}` (§1.14, "The 409 extension (rev 9: status and owner)"). Lane A narrows on `reason`; on the legacy body, the string `detail` equals the code (§1.0a, "keeps that string and gains `reason` equal to it").
    - When `current` is a row, lane A rebases on it with no refetch.
    - When `current` is `null` (§1.14, "It is `null` when no row exists"), no row exists, so lane A writes again from revision 0.
    - Until the body ships, lane A refetches with GET and rebases on the fresh row (§1.14, "Until it ships, the rev-8.7 refetch stays the contract").
    - Either way it never loses the newer position, and the 409 is never shown.
  - Lane A still writes sparingly:
    - once scrolling has settled for 10 s
    - on leaving the document: a tab switch, `visibilitychange` to hidden, or `pagehide` with `keepalive`
    - never when the anchor is unchanged

    That is at most one write per 10 s of reading, and "continue" still lands on the last passage read.
- **To read — Needs:**
  - **The list (rev 9).** `GET /flags?intent=read&project_id=&cursor=&limit=` (§1.13, "`GET /flags?intent=read|diligence&project_id=&cursor=&limit=` (rev 9)"). It comes newest first. "Show more" follows `next_cursor`, and paging stops when it is null.
  - **When it ships (rev 9).** The to-read projection ships only once rev 9 is signed (§1.13, "Gated on rev 9"). Until the route answers, To read reads "To read isn't available yet" and never shows an empty list.
  - **The project filter (rev 9).** Before its delta lands, `?project_id=` answers `422 project_filter_unavailable` (§1.13, "`422 {reason: project_filter_unavailable}`"). Lane A then lists the whole queue with the header "All projects: filtering by project isn't available yet". Legacy flags with a null `project_id` appear only in the unfiltered list.
  - **Items (rev 9):** `{flag_id, intent, actor | null, actor_reason?, target, reason | null, project_id | null, created_at, state: open | done | declined, document: {document_id, title, document_type, gate, reason} | null, document_reason}`.
    - `actor {kind, id}`, with the label derived as in §2.8. `actor: null` with `actor_reason: "legacy"` takes §2.8's copy: "Flagged by: —", with the reason "Flagged before flags recorded who" (rev 9).
    - `reason` is the flag's own reason.
    - `document.gate` and `document.reason` render by §2.10's chips.
    - `open` flags are listed. `done` flags collapse under "Done". A done flag is one whose question has been sharpened.
  - **The unresolved row (rev 9).** A flag whose document can't be resolved carries `document: null` and `document_reason: "unresolved_document"` (§1.13, "The marker is `document_reason`"). The rev-5 `reason` name is retired for this marker. The row says "Couldn't find the document for this", shows the flag's `reason` and target, and offers Dismiss. It is never dropped silently.
  - **Dismiss (rev 9)** is `POST /flags/{flag_id}/decline` (§1.13, "`POST /flags/{flag_id}/decline` (rev 9 clarification)"). It is idempotent, and the row moves to `declined`. A `404 not_found` means the flag is gone: the row is removed with the quiet toast "That item was already removed".
  - **Adding (rev 9).** "Read later" is `POST /flags {intent: read, target: {document: {document_id}}, idempotency_key}`, offered on answer refs (§2.19). The body never carries `actor`. A `422 flag_body_invalid` is a lane-A bug.
- **To read — states:**
  - `loading`
  - `empty`: "Nothing waiting". Shown only after a real answer.
  - `error`: "Couldn't load To read." with Retry (copy rev 9).
  - `ready`
  - `not_available` (rev 9): "To read isn't available yet".
- **Your books (rev 9).** `GET /projects?product=reading` lists by presence (§1.5, "`home_product` never filters"). It includes:
  - `kind: reading` rows, each showing its primary book;
  - `kind: interest` rows, each with its title and `shelf_count`;
  - `kind: project` rows with Books presence, labelled "Project · shelf of n" (rev 9). The label names the kind, never Research, because a Writing-only project can gain Books (§1.5a T1: "`kind: project` | a product not in `products[]`").

  `shelf_count` follows the nullable rule, with its `null_reasons` entry as the reason. A known 0 reads "No books yet".

  **States (rev 9):**
  - `loading`
  - `empty`: "No book projects yet. Start one with New." Shown only after a real answer.
  - `error`: "Couldn't load your books." with Retry.
  - `ready`
- **From a research project (rev 9; ruling 11).**
  - **The list.** Book projects linked to a research project are grouped under that project, from each row's `linked_project_ids[]` (§1.5, "Reads").
  - **States (rev 9):**
    - `loading`
    - `empty`: "No books linked to a research project". Shown only after a real answer.
    - `error`: "Couldn't load linked books." with Retry.
    - `ready`
  - **"Add to a research project…"** writes the link: `POST /projects/{id}/members {member_kind: project, member_role: context, member_id, link_back: true}` (§1.5, "The ruling-11 link"). Both rows are written, or neither. Its answers take §2.1's copy:
    - `201 added`: "Linked to <project>."
    - `200 already_member`: "Already linked to <project>."
    - `404 project_not_found`: "That project can't be found. Pick another."
    - `422 member_id_invalid` (a self-link) is unreachable from the picker. If it is ever received, it is logged as a lane-A bug.
  - The book keeps its identity. Nothing it reaches through the link is written to.
- **New (rev 9).** It opens the create page as `/new?product=reading`, with a book or an interest (§2.12).
- **Standalone book (rev 9; ruling 11).** This replaces rev 8's promote-in-place (§1.5, "Standalone book, narrowed"). A standalone book is a `kind: reading` project with `primary_document_id`. It has two actions (§2.1):
  - "Add to a research project…" (above);
  - "Turn this book into a new project", which is T6 (§2.18; §1.5, "the only promotion in place left").

  `PATCH {kind}` no longer exists. A `422 project_patch_invalid` is a lane-A bug.
- **Reacts to** (rev 9; §1.7):
  - `project.created`, `project.updated`, `project.members_changed`, `project.shelf_changed`, `project.product_left` and `project.transferred`: refetch Your books and From a research project.
  - `question.identified` and `question.flag_declined`: refetch To read from its first page.
  - No push carries a reading position. Continue refetches when the home regains focus.

### 2.10 Gated text (shared by 2.3, 2.4, 2.5, 2.6, 2.7, 2.11 and every excerpt; rev 9 adds 2.13, 2.14, 2.18 and 2.19)

Every rights-bearing text a route returns is a `GatedText` (§1.2, rev 6; `origin` rev 8.2): `{text | null, gate: served | cite_only | withheld, reason | null, origin: source | operator | generated | unsourced, source_refs[]}` (`unsourced` rev 8.8), where each source ref carries its own `gate` and `reason`. It binds as `excerpt`, `answer`, `context[]`, `content` and `insert`.
- **Where else it binds (rev 9).**
  - A turn's `answer` and `context[]` (§1.8, "Answers are gated at read").
  - A merge draft's `synthesis` (§1.10, "`synthesis: GatedText`").
  - An output segment's `content` (§1.4b, "content: GatedText").
  - A transfer candidate's `excerpt` or `content` (§1.5a, "Candidates (rev 9)").
  - An agent context item's `content` (§1.12a, "The one assembler").
  - A Books-lens notebook entry (§1.12, "The lens (rev 9)").
  - Each renders by this section.

The shape is discriminated:
- `served`: text set, reason null.
- `cite_only`: a quotation whose sources are unresolved or not servable. A citation stands in for the words.
- `withheld`: nothing stands in. A synthesis is only ever `served` or `withheld`, never `cite_only`. Syntheses include the thesis excerpt, an archived synthesis, a companion entry drawn from a body and (rev 9) a merge draft's synthesis, a turn's answer and a thesis or component output segment (§1.4b, "the gate is `served` or `withheld`").

When sources mix, the most restrictive gate wins.

**Where `origin` comes from (rev 9).** Lane A labels only from `origin`, never from whether a source is missing.
- **Output segments** (§1.4b, "Gates by role"):
  - A thesis or component segment is `source`.
  - An insight or open-question node that names no source is `operator` only when the event that wrote it had role `operator`. Otherwise it is `unsourced` (§1.4b, "is `operator` only when the event that wrote the segment was emitted with role `operator`").
  - The old chokepoint label "the operator's own words" is shown only for `origin: operator`, and never for model text.
- **Turns.** An answer is `source` when any sentence is supported, and otherwise `unsourced` (§1.8, "served to its owner with the unsupported mark").
- **Merge draft sentences** carry one of `source`, `generated`, `unsourced` or `operator` each (§1.10, "The server splits the served text into UAX #29 sentences").

**States.** Lane A renders from `gate` and `reason`. It never renders from whether `text` is empty, and it never drops an item.
- `served`: the text, with its source refs.
  - When `origin` is `generated`, the text carries the "Generated" label.
  - When `origin` is `operator`, it reads as the operator's own words (§1.2, rev 8.2).
- `served · unsourced` (rev 8.8): model text that has no source and that the connective validator did not admit.
  - It is served to its owner and always reads "Unsupported: no source", with the same mark as §2.11's unsupported class. It is never labelled "Generated".
  - A revision containing it holds its export back, and the export control says why: "Held back: unsupported text".
  - Before rev 8.8, such text arrived with a null origin. Lane A renders a null origin the same way and never guesses a class.
- **Sentence marks inside a served text (rev 9).** Some texts carry per-sentence records: a turn's `answer_spans[]` (§1.8, "Supported and origin") and a draft's `sentences[]` (§1.10, "The server splits the served text into UAX #29 sentences"). Each sentence then takes its own mark:
  - A sentence with `supported: false`, or with `origin: unsourced`, reads "Unsupported: no source" on that sentence only.
  - A draft sentence with `origin: operator` reads as the operator's own words ("Your edit").
  - A draft sentence with `origin: generated` reads "Generated".
  - The rest of a served text is unmarked.
  - After a takedown, a sentence or claim with `text: null` shows no words, only its pointers (§1.10, "the pointers stay").
- `cite_only · not_servable`: no text. It shows the source's title and locator and says "This source can be cited here but not quoted." The reference opens the source wherever the operator may read it.
- `cite_only · unresolved`: no text. It shows the stored pointers with the dangling treatment, which pairs colour with a text label and never relies on colour alone: "Source not found. The citation is kept; its text is not." It is never smoothed into a normal citation.
- `withheld · lineage_unreconciled`: an excerpt from a thread that predates branch records and has not been reconciled and attested (§1.3, rev 4, operator call #6). It shows no excerpt and says "Excerpt held back until this thread's history is reconciled. Its notes and artifact are unaffected."
- `withheld · unresolved`: evidence-derived text whose sources cannot be recovered. It reads "Held back: its sources can't be found".
- `withheld · not_servable`: a synthesis over sources that can't be served here. It reads "Held back: a source can't be shown here".
- **Which source held it back.** A non-served text lists its `source_refs` as small chips, each with its own gate and reason. The operator sees exactly which source withheld the text or reduced it to a citation, and each chip opens that source where the operator may read it.
- **Counts.** Every list header counts each kind, for example "12 items, 3 cite-only, 1 held back", so a preview never implies it shows everything. An unknown count renders "—" with its reason, never 0.

**Document rows (rev 9; §1.5, "One gate projection").** Some routes list documents rather than texts: the shelf, transfer candidates, continue reading, book-ask `source_refs` and flag documents. These carry a flat `gate` and `reason`, the same pair and the same projection everywhere. They render by the same states, with metadata in place of text:
- `served`: the normal row. This includes the owner's own `personal_reading` document when the owner reads it.
- `cite_only · not_servable`: the title and locator, with "Can be cited here, but not read here". Opening it shows the reader's cite-only state, never a failed reader.
- `withheld · not_servable` (for example, a takedown): "Held back: this document can no longer be shown".
- `withheld · unresolved`: the metadata is null. The row reads "Source not found. It stays on the list", with the dangling treatment. It is never dropped.

**Audiences (rev 9; §1.12, "a `personal_reading` quote is served to its owner").**
- A quote from the owner's own `personal_reading` document is `served` to the owner and `cite_only` in an export or share.
- An export or share preview renders the public audience's gates, never the owner's. Its header says "Your personal copies are quoted for you only; in an export they become citations."
- **Private authored text (A06; rev 9).** The class `user_authored_private` is owner-readable and never public-servable (§1.15, "It is owner-readable"). It joins the owner full-read allowlist, so it renders `served` to its owner, and it is never `served` in an export, share or public view. Lane A renders it by the same audience rule, with the copy "Your private writing is shown to you only".
- **Another owner's private document (A06 round 2; rev 9).** A `user_authored_private` document is discoverable only by its exact owner. To anyone else it is a missing document: every route answers it exactly as it answers a missing document (a body reference answers `404 {reason: source_not_found, ref}`), before any of its metadata, references or context is read (§1.15, "Another owner's private document answers exactly as a missing one"). So each surface shows its own missing copy for it, word for word, and nothing on screen says that such a document exists or whose it is. Write informs marks a row instead, with the same line for both (§2.11).
- **Private derivatives (A06 round 2; rev 9).** A derivative of private writing, such as a reformulation or a monologue over it, is private only when the caller and every source document's owner are verified and equal. A derivation with mixed or unproven authority, or whose output schema cannot represent private lineage, is refused before anything persists (§1.15, "A derivation with mixed or unproven authority"; "cannot represent private lineage"). §2.11 gives its copy.

**Private upload (A06; rev 9; DECISIONS "Operator ruling, 2026-09-27: A06 private-authored upload gating"; §1.15, "The client rule: disable until confirmed (the operator's ruling)").** The Sources upload's "I wrote this" option mints `user_authored_private`. It is enabled only once the server confirms the capability, and it never falls back to `user_owned`, which an API without A06 serves publicly.
- **Needs:**
  - `GET /sources/upload/attestations` (§1.15, "Advertising the token"), which answers `{accepted: [...], authored_default: "user_authored_private", aliases: {"user_owned": "user_authored_private"}}`. Lane A reads it when the upload surface opens, and again on Retry.
  - The existing upload's `UploadResponse.content_class` (§1.15, "What the upload answers").
- **States:**
  - `capability_checking`: the attestations read is in flight. "I wrote this" is disabled and reads "Checking…".
  - `capability_confirmed`: `accepted[]` lists `user_authored_private`. "I wrote this" is enabled, with the line "Private: shown to you only, never published." It sends the explicit token `user_authored_private`, never the alias.
  - `capability_absent_or_error`: the route is absent, errors, or answers without `user_authored_private` in `accepted[]`. "I wrote this" is disabled, with "Private upload needs a server update. Try again later." and Retry, which re-reads the route. Lane A never sends `user_owned` for authored content and never infers publication consent. The upload's other options are unaffected.
  - **Until A06 is activated (A06 round 2; rev 9).** Private upload stays in `capability_absent_or_error` until A06's activation receipt exists, which needs the deployed denial gates and a real-login proof for two verified subjects (§1.15, "Until the receipt exists, the capability route does not list the token"). Until then every login maps to the operator, and a new private row is refused for that owner (§1.15, "no ordinary login can complete a private upload"). So the disabled state is the honest one, and lane A has no other way to enable the option.
  - `attestation_conflict`: the upload answered `409 upload_attestation_conflict` (§1.15, "The re-attestation matrix"). This document is already stored under a rights setting that can't change this way. Nothing was written. The copy is "You've uploaded this document before with a different setting, so nothing changed."
  - **The result.** After a successful upload, the document's label is rendered from `UploadResponse.content_class` as returned, never from the class requested. `user_authored_private` reads "Private: shown to you only". Any other class reads that class's label. When it differs from what the operator chose, the line "Saved as <label>, not as private writing" is shown.
  - No status code or class string reaches the screen.

**Read aloud (rev 9; §1.19, "Speech output: the `source` gate").** Speech is gated text too.
- Every rights-bearing read-aloud sends `source` (`{turn_event_id}` or `{document_id, page_index}`), never bare text. The bare `{text}` form is used only for text the operator typed.
- A `cite_only` passage is spoken as the fixed marker `withheld_marker/v1`, never as its words. The on-screen text at that point shows the passage's cite-only state, so what is heard and what is shown agree. (The marker's spoken words: needs Part 1, R9-43.)
- `422 not_servable`: the read-aloud control is disabled with "This is held back, so it can't be read aloud."
- `422 too_long` (rev 9): a single page or turn can still exceed the bound (§1.19, "The narrated text, after resolution, is at most 8,000 characters"), so this is a real state, with §2.20's copy, "This is too long to read aloud in one go." (§2.14's copy for an answer). It is logged as a lane-A bug only if lane A sent a source that spans more than one page or turn.
- `503 tts_unavailable`: "Reading aloud is unavailable right now", with Retry.
- A monologue's audio segments follow the same rule per span (§1.11a, "Gated per span"). The player is §2.14.

**The excerpt marker.** The rev-4 `excerpt: {state, reason?}` marker is a projection of the excerpt's `gate` (R5-1, applied in rev 6). The excerpt is a synthesis, so the marker and the gate never disagree.

**Needs:**
- `GatedText {text | null, gate, reason | null, origin | null, source_refs[]}` (§1.2). Each source ref carries `gate` and `reason`, plus `document_id` and an `anchor` when it names a passage, so it opens as a left tab (§1.2, rev 7, S1).
- Rev 9 per-sentence records: `answer_spans[{span_id, start, end, cited_item_ids[], supported, origin_thread_id | null, reason}]` (§1.8, "Supported and origin") and `sentences[{index, start, end, text | null, origin, claim_id | null, item_ids[]}]` (§1.10, "The server splits the served text into UAX #29 sentences"). Offsets are Unicode scalar offsets into the served text (§1.0a, "Model citation markers"). Served text never contains a citation marker.
- The flat `gate` and `reason` on document rows (§1.5, "One gate projection (rev 9)").
- `POST /speech/tts {source, voice?, mothership?}` (§1.19, "Speech output: the `source` gate").
- `GET /sources/upload/attestations` and `UploadResponse.content_class` (§1.15, "Advertising the token") (rev 9).

**Reacts to:**
- Gates are judged live at every read (§1.8, "Answers are gated at read"; §1.10, "Re-judged at every read").
- When a hosting surface refetches after any of its events, a served item may come back `withheld`. Lane A renders the new gate in place. It never keeps the old words on screen, and it never keeps them in a client cache that outlives the refetch.
- The upload capability is read when the upload surface opens and on Retry. No push changes it (rev 9).
- No raw status code or server code reaches the screen. Every refusal above has its sentence.

### 2.11 Reformat, provenance and probe to the core (C6; rev 8, with T6 and T7 ruled 2026-09-26 and signed with rev 8; rev 9 changes marked)

This is the operator's paragraph 2, in the cockpit. The engagement lives in the right pane, and the result opens on the left. The line between the author's words and everything else is visible at every span (§1.11a).

**Where the engagement lives (C5, rev 8.2).**
- In research and reading, it is a right-pane agent tab of kind `reformat`.
- In writing, the right pane is the block outline, so the engagement runs in the AI sidecar. Its result opens as a left `derivation` child under the active section (T4).
- **Two more engagements are reformats (rev 9; §1.11a, "Two new `source` forms").** They follow every state below. Each keeps its own composer:
  - A Converse monologue, `{scope: {project_id}, query}`, whose player is §2.14.
  - The Books Notebook's "Write it up as prose", `{companion_document: {project_id, lens: "reading"}}` (§2.19). It runs as a right-pane `reformat` tab in the reading mode, and its input is the notebook's entries as served `GatedText`, built with no spend. Until LB-30 lands, the action is disabled with §2.19's copy, "Prose write-ups aren't available yet" (§1.11a, "stays disabled until LB-30 lands").
- The states below are the same in every place.

**The reformat engagement (right-pane tab, or the Write sidecar).**
- `composing`: the prompt, plus four optional choices:
  - the reading time, in minutes;
  - focus items: themes, questions, insights, or a highlight;
  - the mode: condense, expand, reorder or explain.
  - **The model.** A model picker offers the lineup's models (`params.model_choice`). When nothing is picked, a line names the resolved reformat default ("Uses <model>").
  - Changing the model, or a changed default, fetches a new estimate. The model is never swapped silently (§1.11a, rev 8.2).
  - **Binding (rev 8.3).** The estimate binds nothing. With no explicit choice, the model resolves once, at admission.
    - A retry under the same idempotency key replays that first generation, even if the default has since changed.
    - A new Generate press is a new key, and uses the current default.
    - Once admitted, the tab names the bound model.
  - **Voice (rev 9; §2.20; lane-A default 8).** The reformat composer starts paid work, so voice fills an editable draft and never sends on its own.
    - The request carries `input` (§1.19, "`Input` on the consuming routes"). It is `{modality: "voice", edited, asr_model?, language?, duration_s?}` for voice, and `{modality: "text"}` otherwise.
    - The answer returns `voice_capture_event_id`. Lane A reads it from there and never invents one.
  - **Mode attribution (rev 9).** Estimate and generate send `mothership`: the current mode, or null from a door outside the cycle (§1.11a, "attribution only"). It is part of the request identity, so a retry sends the same value.
- `estimating`: `POST /reformats/estimate {source, params, input?, mothership?}` returns `{estimate_cents | null, max_cents, reason?, assumptions}` (§1.11a, rev 8.1; `input` and `mothership` added in rev 9).
  - The tab states "Starts if $<max_cents> of today's cap is free" (§2.8's admission copy), with the estimate beside it.
  - With no figure, it shows the reason and never a number. Generating then needs an explicit "Cost unknown" confirmation.
  - `too_large` reads "This source is too large to reformulate in one pass". `source_not_servable` reads as in the failures below.
- `generating`: the thread is running, and its process steps stream as in §2.3.
- **Requests are idempotent.** Lane A mints an `idempotency_key` per press of Generate and reuses it on every retry of that press.
  - A `409 idempotency_conflict` is a lane-A bug, never shown to the operator.
  - The generation's own states are `requested → admitted → generating → committed | failed`.
  - **Chapters (rev 9).** A monologue commits one chapter revision at a time and reads `generating` until its last chapter commits (§1.11a, "Chapters commit one at a time"). A committed chapter can be opened while later ones generate.
- `proposed`: the agent asks "Open it on the left?" (`reformat.open_proposed`).
  - One key accepts: Enter, while the tab is focused.
  - The result opens as a `derivation` left child in the current mode.
  - Declining keeps an "Open" control on the tab, so nothing opens without the operator.
- `opened`: the tab shows which left tab holds the result, one key away.
- **Honest reading time.** When `reading_estimate.shortfall` is set, the tab says so: "The source can't honestly fit 15 minutes; this reads in about 22." Nothing is padded or cut silently. A monologue's listening shortfall is §2.14's.
- **One failure vocabulary (rev 8.3; narrowed on `reason` in rev 9).** Lane A narrows on the body's `reason` (§1.0a, "Error bodies"), never on the status code or a string `detail`. Each reason has one state and one copy.
  - **Refused before any thread exists.** This is an answer to Generate; nothing was started.
    - `too_large` (422): "This source is too large to reformulate in one pass."
    - `source_too_deep` (422): "This is a reformulation too many times over. Reformulate an earlier version."
    - `source_not_servable` (403): "Its source is held back, so it can't be reformulated."
    - `refused_capped` (402): "Today's cap has no room for this." Offers "Raise today's cap".
    - `project_not_found` (404, rev 9, for a monologue or write-up source): "This project no longer exists."
    - `source_not_found` (404, rev 9, for a `{document_id}` or `{derived_asset_id, revision_id}` source; §1.15, "Any other body reference"): "This source no longer exists." Another owner's private document answers exactly the same (§1.15, "Another owner's private document answers exactly as a missing one"), so the copy is the missing copy and says nothing more.
    - `not_owner` (403, rev 9, a derived-asset source): "You can't reformulate that." The copy never says whose it is.
    - **A private derivative refused (A06 round 2; rev 9; §1.15, "is refused before anything persists").** When a reformat's sources include private writing and its authority is mixed or unproven, or its output schema cannot represent private lineage, the server refuses it before anything is written. A Converse monologue (§2.14) and the Notebook write-up (§2.19) are reformats, so they take this copy too. Once Part 1 names the refusal (needs Part 1, R9-47), the copy is "This can't be made from private writing yet. Nothing was charged." Until then lane A can't tell it from other refusals, so an unrecognised refusal of Generate is logged and reads "This couldn't start. Nothing was charged."
    - `idempotency_conflict` (409): a lane-A bug, logged and never shown.
    - **Body refusals are lane-A bugs (rev 9).** These are logged and never shown: `source_invalid` (any `detail`, including `scope_document_not_supported`, because lane A never offers a document-scoped monologue), `params_invalid`, `parent_invalid` and an `input` refusal. `voice_invalid` is monologue-only, and its copy is §2.14's.
  - **Failed after admission** (`reformat.failed`; the thread exists and shows the reason):
    - `unavailable`: "The model isn't available." Offers "Choose another model".
    - `interrupted`: "It stopped before finishing. Nothing was saved." Retry reuses the same key.
      - **With committed chapters (rev 9).** When `committed_revision_id` is set, the copy is "It stopped before finishing. The chapters before it were saved." The committed chapters stay readable (§1.11a, "Its committed chapters stay servable").
    - `failed`: "It failed before finishing. Nothing was saved." Offers Retry. A known `detail` sub-code gets its own sentence. An unknown code never reaches the screen: it is logged, and the fixed sentence stands (rev 9; needs Part 1, R9-11: a closed `detail` set for `reformat.failed`). §2.5, §2.8 and §2.13 use this rule.
  - **Stopped by the cap mid-generation** (`investigation.cap_halted`). The thread reads `stopped` with `cap_reached` or `cap_overshoot` (§2.8), never "failed", and offers "Raise today's cap".
    - This holds only for the text chunks, which rev 9 keeps thread-scoped (§1.13, "a reformat generation's text chunks").
    - **Audio never stops a reformat (rev 9; §1.13, "Halt scope").** A refused audio segment reads `failed · cap_reached` on that segment only, through `reformat.audio_render_failed`. It never writes `stopped` onto a committed reformat, and the text stays readable. The player's copy is §2.14's.
  - **Legacy** (`409 legacy_generation`, or a revision whose `state` is `legacy`): a reformulation made before provenance tracking.
    - It stays readable. Its tab says "Made before provenance tracking. It can be read, but not probed, merged or reformulated until it's upgraded."
    - The probe, merge and reformulate controls are disabled with that reason.

**The derivation left tab (reader view `drv-<generation_id>`).**
- **Header:** "Reformulated from <source title> · <mode> · <model actually used> · revision n". The source is one key away: it opens the core document as a sibling left tab.
  - **The model** comes from `reformat.generated.model`, never an operator default. Since rev 8.10 that field is `{providers[], model, dispatch_event_ids[]}`:
    - there is one model, named once;
    - the providers are listed after it only when there is more than one ("<model> via A, B");
    - one dispatch event per generation window is reachable from the revision's receipt.
  - `cost_cents` renders by the nullable rule.
  - **A monologue's chapters (rev 9).** The header adds "chapter i of n" (with its title, when present) from that revision's `reformat.generated.chapter {index, count, title?}`, and the model named is that chapter's `model` (§1.11a, "One event per chapter").
  - **A stale write-up (rev 9).** When a notebook write-up carries `stale: true` (§1.11a, "carries `stale: true`"), the header reads §2.19's "Written from an earlier version of the Notebook" and offers "Write it up again". That is a new press, with a new estimate. The write-up never rewrites itself (needs Part 1, R9-21: which route or field carries `stale`).
- **Holders.** A reformulation of a reformulation resolves rights to its core sources (§1.11a, rev 8.1). When those sources have several holders, the header shows the holder set ("From 3 sources"), each opening its core, and never a single holder.
- **Mostly generated.** When sourceless plus unsupported words exceed 15% of the revision (`mostly_generated`, rev 8.2), a banner above the first span reads "Most of this is generated or unsupported text". The revision earns no attribution.
- **Held back:** when the source's live gate withholds it (a takedown or a reclassification), the whole view renders §2.10's withheld state: "This reformulation is held back because its source can no longer be shown."
- **Spans by class (A8).** Every span carries its class as a text label and a glyph, never colour alone. A persistent legend names all five classes.
  - `author_verbatim`: "Author". Upright text with a left rule, following the quotation gate (`served | cite_only`).
  - `llm_compressed`: "Condensed". `llm_expanded`: "Expanded".
  - `research_supplemented`: "Research", linking its thread.
  - **Generated.** Text whose `GatedText.origin` is `generated` reads "Generated" (§1.2, rev 8.2).
    - The server grants `generated` only to text matching one of its six non-assertive connective templates (`connective-templates/v2`, rev 8.6), such as "This section covers {X}.".
    - Any other sourceless text is `unsupported`. So is a span scored before rev 8.6 (`validator_version: null`, fail-closed).
    - Lane A never labels model text "Generated" on its own inference. Generated text never states a claim.
  - **Unsupported.** A claim that cannot cite a source reads "Unsupported", with the probe answer "No supporting source". It is never passed off as "Generated".
  - **Unsourced** (rev 8.8). Text whose `GatedText.origin` is `unsourced` reads "Unsupported: no source".
    - This includes a template sentence whose slot of 4 or more words appears verbatim in a core source's served text, because that slot is source text.
    - Such a sentence is never "Generated" and never shows "from your prompt".
  - **Unresolved spans** (rev 8.9; every span is exactly `placed` or `unresolved`). An `unresolved` span has a locator and no class. It is text that no bite covers, which only a legacy backfill produces.
    - It shows no class label and no glyph, only "Unresolved: this passage couldn't be placed", with the dangling treatment of §2.10.
    - It is never given a guessed class.
    - It weighs nothing in attribution, and it holds the export back, like `hash_ok: false`.
    - The legend lists it after the five classes.
  - **Unplaced bites** (rev 8.9, `unplaced_bites[]`). These are bites from the original reformulation that have no locator, so they cannot be drawn in the text.
    - They are listed below the document under "N passages from the original reformulation couldn't be placed".
    - Each item shows its declared class as declared ("declared: Condensed"), its source chips and the held-back mark.
    - Each one holds the export back, and the export control counts them ("Held back: 2 passages couldn't be placed").
    - The list is never collapsed to nothing. With zero unplaced bites, no list is shown.
  - **Your edits in a fork** (rev 8.9). An operator's edit in a new revision is an `origin: operator` bite with no class.
    - It reads "Your edit" in the operator's own-words treatment (§2.10).
    - It weighs nothing in attribution, and it is never marked unsupported.
    - Carried-forward spans keep their class, and earlier revisions never change.
  - **The provenance lens** (a key-sheet toggle) shows the labels inline at every span boundary. Otherwise they show on hover and on focus. The spans are focusable in reading order, so the lens works from the keyboard.
- **Weakly supported.** An `llm_*` span whose `support.score` (`rougeL-f1/v1`, two decimals) is below 0.35 gets a dotted underline and the label "Weakly supported".
  - On focus it shows its lexical support score and method. Rev 8.4 names this lexical support, and the UI never says "entails".
  - A null score with reason `not_computable` reads "Support unknown", never "supported".
  - Both marks mean the span earns no attribution. In a merge into Write, it becomes an `unsupported` member that holds the export back (rev 8.5), and its focus text says so.
  - Support is scored per sentence (UAX #29), so a failing sentence arrives as its own small span. A span's score is the lowest of its sentences.
- **Where the spans come from (rev 8.3; `unplaced_bites` rev 8.9).** `GET /derived-assets/{id}/revisions/{rev}/spans` returns:
  ```
  {revision_id, mostly_generated,
   unplaced_bites[{bite_id, derived_text_sha256, declared_class, source_refs}],
   spans[{span_id, locator, hash_ok, contribution_class, declared_class,
          support{score, method: "rougeL-f1/v1", tokenizer: "uax29/icu-<ver>", reason?},
          origin, unsupported, validator_version, content: GatedText}]}
  ```
  - The tokenizer arrived in rev 8.5. `validator_version` arrived in rev 8.6: it is `connective-templates/v2` on generated spans and null on sourced spans.
  - A sentence longer than a span's word cap arrives as its own span, and a sentence is never split.
  - Each span renders from these fields: the label from `origin`, `contribution_class` and `unsupported`, and the gate from `content`.
  - `404 not_found` reads "This reformulation no longer exists".
  - `409 legacy_generation` reads as Legacy above.
  - `422 revision_not_committed` shows the generating state, never an empty document. **In rev 9 it applies only to the revision still generating.** Committed chapters answer and render while later ones generate (§1.11a, "A committed chapter's spans answer 200 while later chapters generate").
  - **Not through `/outputs` (rev 9).** A reformat thread's text is never read from `GET /investigations/{id}/outputs`, which answers `422 use_probe` with `spans_route` (§1.4b, "A reformat thread answers `422 use_probe`").
    - Lane A follows `spans_route` without showing anything. It is routing, not a refusal.
    - A null `spans_route` means nothing is committed yet, so the tab shows the generating state.
    - The output-selection verbs of §2.3 (Ask, Harden, Chase, Flag for diligence) are never offered on a derivation. Its verb is "Probe the source" (below).
- **Integrity.** A span with `hash_ok: false` reads "Passage changed" (unresolved), never "verified". The revision's receipt shows its mismatch count ("2 verbatim claims did not verify").
  - **Hash drift is read-time** (rev 8.10). A drifted span arrives as `state: "unresolved"`, with null top-level `contribution_class` and `origin`. Lane A draws no class for it: it renders as an unresolved span, weighing 0 and holding the export back.
  - **What it was.** Its focus detail shows the stored values from `as_recorded {contribution_class, declared_class, origin}` as "was: Condensed". These values are present only on drifted spans. The operator sees what the passage was before it drifted, and lane A never renders the recorded class as current.
- **Audio of a derivation (rev 9).** A monologue's segments and their per-span gates are §2.14's. Every spoken passage follows §2.10's read-aloud rule.

**Probe to the core.**
- Selecting span(s) offers "Probe the source". The key is `island.open`: prefix+a or ctrl+alt+a (§2.17).
  - The probe creates a research thread branched from `read-<core document>` of the span's first core ref (§1.11a, rev 8.1). That thread appears as a right-pane `island` tab.
  - **Its project (rev 9).** The launch sends the active project's `project_id`, so the probe is a member of that project and lists under it (§1.3, "writes membership").
  - When the core can't be opened (`probe_core_inaccessible`), the offer reads "The source of this passage can't be opened, so it can't be probed", and nothing starts.
- Every answer is §2.10 `GatedText` that resolves to a **core** span, or reads "Unresolved" in words. Each resolved snippet opens the core document at that passage as a left tab (origin `agent`, `opened_by` the probe thread).
- "Show the core" on any span opens a peek card: `GET …/spans/{id}/sources`, rendered as `GatedText`, with "open on the left".
- A span with no source shows its generation record, the prompt and model that produced it, instead of a core snippet.

**How evidence is presented (T7, ruled 2026-09-26).**
- An answer follows its `presentation_mode`:
  - `quoted` shows inline quotes.
  - `cited_quietly` shows small citation markers.
  - `metadata_only` shows clean prose with an always-present "N sources behind this answer" disclosure. It lists `cited_refs`, then the rest of `retrieved_refs`.
- An answer never looks unsupported when it was supported. It also never looks supported when it was not: an unsupported sentence keeps §2.10's sentence mark in every mode (rev 9).
- **Where the record is (rev 9).**
  - A turn carries `provenance {answer_event_id, retrieved_refs[], cited_refs[], presentation_mode}` (§1.8, "The response").
  - A merge draft carries `answer_provenance {retrieved_refs[], cited_refs[], presentation_mode}` (§1.10).
  - In both, `cited_refs ⊆ retrieved_refs`.
- **A book session (rev 9).** Its `cited_refs` equals `retrieved_refs`, and `answer_spans` is `[]` (§1.8, "A book session is the exception").
  - Lane A draws no per-sentence attribution for it and no sentence marks.
  - The disclosure lists the cited refs once.
- **A recorded default (rev 9).** When the dispatch declared no mode, the server records `cited_quietly` (§1.8, "When none is declared it records `cited_quietly`"). Lane A renders the recorded mode as stored. T7 says the choice is recorded per answer, so lane A needs to tell a declared choice from a default (needs Part 1, R9-22).

**Fork and merge (T6, ruled 2026-09-26).**
- "Fork" commits a new revision, and the original stays one click away in the lineage.
  - **The route** (rev 8.10): `POST /derived-assets/{asset_id}/revisions {base_revision_id, blocks: [{block_id, text}], idempotency_key}`.
    - Lane A sends the full new text of each changed block. It never sends a class, model text or an unchanged block.
    - The server splits the sentences itself. An unchanged sentence carries forward with its class, and anything else becomes an operator edit ("Your edit").
  - **The answer** is `{revision_id, carried, edited}`. The fork's receipt reads "n sentences kept, m your edits", from those counts.
  - **Moved base.** `409 {reason: revision_moved, current_revision_id}` shows "This changed elsewhere". The edited blocks are kept locally, the view rebases on `current_revision_id`, and the operator re-applies with one key. An edit is never lost.
  - **One idempotency key** is minted per press of Fork and reused on retry.
- **"Adopt as this project's reading version"** sets the project pointer (rev 8.7). Part 1 names this flow `adopt_reading_version` (§1.11, "`alternatives` names T6's two flows").
  - **The route** is `PUT /projects/{project_id}/reading-versions/{source_document_id} {derived_asset_id, revision_id, expected_version}`, where 0 means none yet.
    - "Stop using this version" is `DELETE …?expected_version=`.
    - The answer carries the new `version`.
  - **Copy per refusal,** in the server's check order, narrowed on `reason` (rev 9):
    - `project_not_found` (404): "This project no longer exists".
    - `source_not_in_project` (422): "Add the source to this project first", with an Add action.
    - `not_a_reformulation_of_source` (422): a lane-A bug, logged. The action is never offered for another source.
    - `revision_not_committed` (422): "Still generating".
    - `source_not_servable` (403): "Its source is held back".
    - `version_stale` (409): refetch and show "Changed elsewhere", then ask again.
  - **Opening that source in that project** shows the adopted revision, labelled "This project's reading version", with one key to show the original source.
    - A takedown of the source still withholds it (the §1.11a live gate).
    - The source is never written.
- **"Merge into a deliverable"** is §2.6's merge-drafts flow, with members keeping their classes. Part 1 names it `merge_into_write`.
- **There is no "merge into the book".** Source merge is retired, and lane A has no caller of its routes (#3533).
  - If a retired route ever answers `410 {reason: "retired", alternatives: [...]}` (§1.11, "Retired routes"), it is logged as a lane-A bug.
  - The operator sees §2.6's one copy for it, "Reformulations never change the source. Adopt one as your reading version, or merge it into a deliverable.", with the two alternatives it lists offered as actions: "Adopt as this project's reading version" and "Merge into a deliverable" (rev 9).

**Attribution (G4).** Nothing about money appears in the UI. Attribution is telemetry-only until the §9.0 gates open.

**Write informs (S5)** is part of §2.6's block tabs. A block tab's ordered document list is assigned by drop and by key, and reordered by key.
- **Saving (rev 8.7).** `PUT /derived-assets/{asset_id}/blocks/{block_id}/informs {informs: [{document_id, anchor?}], expected_revision_id, idempotency_key}` replaces the whole list, and the order is the ordinal.
- `409 revision_moved` rebases on `current_revision_id` and re-applies the operator's order.
- `422 informs_invalid {index, detail}` marks the row at `index` in place, with one sentence per `detail` (rev 9; rev 8.11 D, which closes the set):
  - `too_many_entries` (at index 50): "A block can list at most 50 documents";
  - `duplicate_document` (at the second occurrence): "This document is already listed";
  - `document_not_readable`: "This document can't be found or read";
  - `anchor_other_document`: "This passage belongs to a different document";
  - `anchor_invalid`: "This passage can't be pinned. Pick it again.";
  - `entry_invalid`: "This row can't be saved".
  - The list is never silently trimmed.
  - Lane A narrows on `reason` and then on `detail`. Any other `detail` is logged and shows "This row can't be saved" on the row at `index`, and the code never reaches the screen. The rev-9 Part 1 draft does not yet name the set (needs Part 1, R9-23).
  - **No existence oracle (rev 9; rev 8.11 D5).** A missing document and another owner's private document answer the same `detail: document_not_readable` at the same `index`, so the row reads the same line for both and says nothing more. Rev 9's §1.15 rule 4 would answer a missing body document `404 source_not_found` instead, so the informs route needs an exemption from it (needs Part 1, R9-45). If a `404 {reason: source_not_found, ref}` arrives, lane A marks every row whose `document_id` is `ref` with the same line, "This document can't be found or read".
- **Persistence off (rev 9; rev 8.11 D5).** Until the W3 revision writer lands, a deliverable has no revision, and every informs PUT and GET answers 404. A missing asset and another owner's answer the same `404 not_found`. While it answers 404, S5 persistence is off: the block tab keeps the operator's list in view for this session and shows "Evidence links aren't saved yet for this piece.", with the reason on hover and on focus, "They save once the piece has its first saved version." The 404 is never shown as an error, and nothing is retried until a revision exists.
- **Reading (rev 9; rev 8.11 D2 and D3).** A block tab loads its list from `GET /derived-assets/{asset_id}/blocks/{block_id}/informs`, which answers the PUT's 200 shape at the current revision, and 404 exactly as the PUT does. `block_id` is the stable Write block id.
- **Generated sentences** can show "from your prompt" or "from your focus" on hover, from their `slot_source` (rev 8.7).
  - A template slot only ever comes from operator text, and only admitted `generated` sentences show it.
  - A sentence whose slot of 4 or more words matches served source text is `unsourced` (rev 8.8), and it shows "Unsupported: no source" instead.
  - Topic labels of 1–3 words stay admitted.
  - **In a merge draft (rev 9),** a generated sentence's slot comes only from the question (`slot_source: question`, §1.10), and it shows "from your question".

**Needs** (one list, named as Part 1 names them):
- **Reformats.**
  - `POST /reformats/estimate` and `POST /reformats` with `source` as exactly one of four forms (§1.11a): `{document_id}`, `{derived_asset_id, revision_id}`, and, new in rev 9, `{scope: {project_id}, query}` and `{companion_document: {project_id, lens: "reading"}}`.
  - Both also take `params`, `idempotency_key` (generate only), `input?` (rev 9) and `mothership?` (rev 9).
  - The generate answer carries `voice_capture_event_id` for a voice input.
- **Events.** `reformat.open_proposed`, and `reformat.generated {generation_id, derived_asset_id, revision_id, chapter?, model, cost_cents, listening_estimate?}`, which is per chapter in rev 9.
  - `reformat.failed {reason, committed_revision_id?}`.
  - `investigation.cap_halted`, for text chunks only.
  - `reformat.audio_rendered` and `reformat.audio_render_failed` (rev 9; rendered by §2.14).
- **Spans.** `GET /derived-assets/{id}/revisions/{rev}/spans` and `GET …/spans/{id}/sources`.
- **Fork.** `POST /derived-assets/{asset_id}/revisions`.
- **Reading version.** `PUT` and `DELETE /projects/{project_id}/reading-versions/{source_document_id}`.
- **Informs.** `PUT /derived-assets/{asset_id}/blocks/{block_id}/informs`, and `GET` on the same path (rev 9; rev 8.11 D2).
- **Probe.** The probe launch through `POST /investigations`, with `project_id` (rev 9).

**Reacts to:**
- `reformat.open_proposed`: the tab moves to `proposed`.
- `reformat.generated`: the tab refetches the spans of that revision. A monologue does this per chapter (rev 9).
- `reformat.failed`: the failure state, with the committed-chapters copy when `committed_revision_id` is set.
- `investigation.cap_halted`: `stopped`.
- `reformat.audio_render_failed` and `reformat.audio_rendered`: §2.14's player. The derivation's text state never changes.
- Any refetch re-reads the live gate. A takedown turns the view into its held-back state in place (§2.10).
- Every compare-and-set conflict (`revision_moved`, `version_stale`) rebases and keeps the operator's edit or order.
- `derived_asset.revised` for the deliverable, as a nudge: refetch the open block's informs through the GET, which also ends the persistence-off state once a revision exists. The event carries no document ids (rev 9; rev 8.11 D1).

### 2.12 Create page (R26, R27; D-P; default 1; rev 9, new)

One page creates every registry project, in one atomic call. Nothing paid starts from it.

- **Route.** It is `/new?product=research|writing|reading`, a lazy route. It is reached from:
  - `project.new` (prefix+shift+n, ctrl+alt+n);
  - every home's create line;
  - SceneChrome's "New piece", which no longer creates an unlinked piece (R26-c; default 1).

  It defaults to the product you came from. From a door with no product (Home, Converse), no product is chosen, and Submit waits for a choice.
- **The product control.** It offers Research, Writing and Books, with the data values `research | writing | reading` (§1.0 "Every data name stays `reading`").
  - **Speak** links out to the Speak door's own create, because Speak creates stay on the Speak side (§1.5 "There is no `speak` seed"; ruling 4).
  - **Autonomous** is shown disabled with "Spawning is off until consent lands". There is no autonomous seed until LB-10 lands (D-P tightening 1; ruling 10).
- **The body per product** follows the seed matrix (§1.5 "The seed matrix"). Each product mounts its existing composer and never reimplements it:

  | Product | `home_product`, `kind` | Seed sent | What the operator gives |
  |---|---|---|---|
  | Research | `research`, `project` | `{question: {text}}` | A question of 3 to 2,000 characters. It is stored, not launched. |
  | Writing | `writing`, `project` | `{blank_deliverable: {deliverable_kind?}}` | A title. The piece kind is optional, and when it is unset the server's default applies. |
  | Books, a book | `reading`, `reading` | `{book: {document_id}}` | A book from the library picker. |
  | Books, an interest | `reading`, `interest` | `{interest: {title, seed_prompt?}}` | A title of 1 to 200 characters, and an optional prompt of up to 2,000. |

  - **From a thread.** `from_investigation: {investigation_id, node_ids?, deliverable_kind?}` is reached only from a thread's "New project from this", which opens `/new?product=research|writing&from_investigation=<thread_id>`. In Writing, the operator may narrow the piece to some of the synthesis's pinned notes (`node_ids`).
  - There is no `speak` seed and no `autonomous` seed. The page never sends one.
  - (needs Part 1, R9-24: a picker field for reader-openable and classified documents; the fallback is the submit-time refusal copy below.)
- **Title.** It is optional. The placeholder names the fallback the server uses: "Uses the question as the title", "Uses the book's title", "Uses the interest's title", "Uses the thread's title", or "Untitled" for a blank piece.
- **Needs** (§1.5 "Create: `POST /projects` (rev 9; LB-17; S14)"):
  - `POST /projects {home_product, kind, title?, seed, idempotency_key}` returns `201 {project, next, created: true}`. There is no second, product-native call.
  - Lane A mints one `idempotency_key` per page mount (1 to 128 characters of `[A-Za-z0-9_-]`). It reuses the key on every retry, so a double press yields one project.
  - A replay answers `200` with the same shape.
  - `project` is §2.1's row.
- **`next` decides where the operator lands.** The new surface is always tab 1, allocated and written in the mode `next` names:

  | `next.kind` | `next.ref` | Where the operator lands |
  |---|---|---|
  | `launch_first_question` | `{question}` | The Research cockpit on the stored question, with a costed "Start research". |
  | `open_mode` | `{mothership: writing, deliverable_id}` | The Writing cockpit with the piece as tab 1. |
  | `open_mode` | `{mothership: research, thread_id}` | The Research cockpit with the thread as tab 1. |
  | `open_mode` | `{mothership: reading}` (an interest) | The Books cockpit on the shelf's add step, "No books yet. Add the first one." It is never an empty pane (§2.19). |
  | `import_book` | `{document_id}` | The book's reader as tab 1, in Books. |

- **The stored question (Research; default 1).** The question is stored in the row's `seed` and nothing is spent (§1.5 "The question is stored in `seed`").
  - "Start research" shows its estimate first, from `POST /investigations/estimate` (§1.9 "Launch context, ask context"). An unknown figure renders "—" with its reason, and starting then needs an explicit "Cost unknown" confirmation.
  - The launch is `POST /investigations {question, project_id}`, which writes its own membership (§1.5 "writes its own membership").
  - After a reload, the question is read back from `project.seed`. It is offered only until it has been launched (needs Part 1, R9-25: nothing links the launch back to the seed). Until Part 1 serves that link, lane A decides by research membership (rev 9):
    - Lane A reads `GET /investigations?project_id=&limit=500` and counts only research rows. Other writes also add `investigation` members: a dialogue create ("Talk", an agent session, §1.8 "What a create writes (rev 9)") and "Call an agent from another project…" (§2.13). So:
      - a row counts when its `kind` is `research` or `cascade_session`;
      - a `no_record` row counts, because a launch writes its membership before the start, and its kind can't be read;
      - a `dialogue` row never counts;
      - a row whose member row in `GET /projects/{id}` `members[]` has `member_role: agent` or `managed` never counts, because it is an agent, not this project's research.
    - "Start research" is offered only while no row counts. When one does, the offer is hidden, with "Research has started in this project".
    - While the read is in flight, the offer reads "Checking…" and is disabled. If the read fails, it stays disabled with "Couldn't check whether research has started. Try again.", with Retry. It is never offered on a guess, so a stored question is never launched twice.
- **"No research yet" (Writing; default 1).** The piece opens labelled "No research yet", with a one-key, costed "Start research" offer that never runs on its own.
  - The launch sends the same two calls as above. The running thread shows in Writing's AI sidecar (C5).
  - The project is not present in Research, because a launch writes membership only. "Open in Research — transfers the whole project (no model spend)" (T1, §2.18) is offered beside the running thread.
- **States:**
  - `idle`: the product control and its composer. Submit is disabled until the seed passes the client-side bounds, and the reason shows beside the field ("A question needs 3 to 2,000 characters").
  - `submitting`: the input is locked and Submit shows progress. Esc does not cancel a create that is already sent.
  - `created`: the page navigates by `next`.
  - `existing` (rev 9): a `book` seed for a document that already has the owner's book project answers `200 {project, next, created: false}` (§1.5 "One book project per document"). Lane A opens that project with the toast "You already have a project for this book. Opened it."
  - `error`: a network failure or a 5xx. The copy is "Couldn't create the project. Your input is kept." Retry reuses the same key.
  - `seed_invalid`: `422 {reason: seed_invalid, detail, field}`. Lane A narrows on `detail`, never on `reason`, and shows the copy beside the input that `field` names (Appendix B, error narrowing):
    - `question_invalid`: "A question needs 3 to 2,000 characters."
    - `not_reader_openable`: "The reader can't open this document yet."
    - `document_unclassified`: "This document hasn't been classified yet, so it can't start a book project."
    - `no_synthesis`: "This thread has no synthesis yet, so there's nothing to write from."
    - `node_not_in_synthesis`: "Some of the chosen notes aren't in this thread's synthesis. Choose again."
    - `seed_required`, `seed_shape`, `product_invalid`, `kind_invalid`, `seed_mismatch` and `deliverable_kind_invalid` mean the page composed a body the seed matrix does not admit. That is a lane-A bug: log it. The page keeps the input and shows "This couldn't be created as sent. Your input is kept." beside the field `field` names, or beside the product control when there is none.
  - `title_invalid`: `422 project_title_invalid`. The copy is "A title needs 1 to 200 characters."
  - `not_owner`: `403 {reason: not_owner, ref}`. The copy is "You can't create from that."
  - `source_not_found` (rev 9): `404 {reason: thread_not_found, ref}` or `404 {reason: source_not_found, ref}`. Both read "That source no longer exists" (Appendix B §B1).
  - `signed_out`: `401 authenticated_owner_required`. The copy is "Sign in to create a project."
  - `offline`: "You're offline. Your input is kept." Submit waits for the connection.
  - **A stale mount (rev 9).** `409 {reason: idempotency_conflict, project_id}` means this mount's key already created a project with a different body. Lane A fetches `GET /projects/{project_id}` and opens it. It is never shown as the operator's error.
  - `project_body_invalid` and `idempotency_key_invalid` (422) are lane-A bugs. Log them. The page shows "Something went wrong on our side. Your input is kept."
  - Esc returns focus to the invoker. No raw status or server code is shown in any state.
- **Reacts to:**
  - connectivity: `offline` and back to `idle`.
  - Nothing else. The POST's answer is the authority, so a `project.created` push for this page's own create is ignored.

### 2.13 Agent-first pane and sessions (rev 9; R25, R29; D-A; rulings 19, 20)

New in rev 9. The right pane can take over the screen, and every conversation in it is a saved dialogue thread. An agent is a promoted thread. In rev 9 it acts only by answering (§1.12a ("In the MVP an agent acts only by **answering**")). Part 1 names win throughout this section.

**The solo pane (ruling 19).**
- **State.** `soloPane: 'right' | null`. It is transient and set by key. It is never remembered per project. The right pane renders at `max(50% of the cockpit, 480px)`, from a token, and the scene stays visible on the left.
- **Keys** (§2.17). `pane.solo` is prefix+s or ctrl+alt+s. Fullscreen is prefix+f or ctrl+alt+f, the "command F" of R25 (default 7).
  - solo → fullscreen → (prefix+f again, or Esc) → solo.
  - Esc outside fullscreen exits solo.
  - prefix+h from solo reveals the left pane and exits solo.
- **Opening a document** from an answer reveals the left pane from solo or fullscreen (below).

**Which dialogues open here (rev 9; §1.8 ("Kinds of dialogue")).** Every one is a `dialogue` thread, and `ThreadSummary.dialogue_kind` says which kind:
- `session`: one agent in one project. It is the agent tab.
- `group`: two to four agents in one project (below).
- `plain`: a Converse conversation over a project (§2.14).
- `branched`: "Ask this thread" (§2.4).
- `book`: TalkToBook (§2.19).

**Session identity (rev 9; §1.8 ("Sessions (rev 9; D-A)")).**
- An agent tab in project P holds P's session with that agent: `participants: [agent_thread_id]`, `scope: {project_id: P}`. Its tab id is `agent:thread:<session thread_id>`.
- The server derives a session's id from its natural key: the owner, the sorted participants and `project_id`. Two devices that open the same agent in the same project reach the same session.
- **Lane A never sends `investigation_id` on a session or group create.** A `422 launch_invalid · session_id_is_derived` is a lane-A bug: log it and never show it to the operator. (rev 9)
- A plain, branched or book dialogue needs a client-minted `investigation_id`. Lane A mints it once per create and reuses it on retry. (rev 9)
- The same agent opened from another project is a different session (T8 holds as membership).
- A create takes no `question`. The first question is the first ask, so a create never spends. (rev 9)
- **Title.** Before any turn the tab reads "New conversation". After that it reads the first question.

**Needs (rev 9; routes and fields as Part 1 names them):**
- **Create:** `POST /investigations {kind: "dialogue", scope: {project_id} | {document_id}, participants?[], title?, investigation_id?}`. It answers `200 {thread_id, investigation_id, start_event_id, branch_event_id | null}`, with the same body on a replay (§1.8 ("Dialogue threads (rev 9)")).
- **Ask:** `POST /investigations/{id}/ask {question, input?, at?, context_items?[], model_choice?, confirm_unpriced?, mothership?, idempotency_key}` (§1.8 ("The ask (rev 9)")).
  - `question` is 1 to 2,000 characters. The composer shows a counter and blocks sending past the bound.
  - `input` is §2.20's. `at` is §2.14's.
  - `context_items` holds at most 20 items of the §1.9 kinds (`doc | insight | thread | note | project`). It is never sent on a group.
  - `mothership` is the current mode, for attribution only. It is null from a door.
  - Lane A mints one `idempotency_key` per press of Send.
  - `model_choice` offers owner models disabled on every dialogue except a book session, by §2.3's rule (R9-7) (rev 9).
- **The answer:** `200 {turn: {turn_id, event_id, attempt, question, input, voice_capture_event_id | null, at | null, answer: GatedText, answer_spans[], context[]: GatedText[], project_id | null, session_of | null, contributions | null, model, cost_cents | null, provenance: {answer_event_id, retrieved_refs[], cited_refs[], presentation_mode}}, context_receipt: {event_id, turn_event_id, project_id | null, items[]}, replayed}`.
- **Reading turns:** `GET /investigations/{id}/turns?after=<turn_id>&limit=` returns the projected turns in order, each with its receipt, plus `open: {turn_id, attempt} | null` and `next_after` (§1.8 ("Reading turns (rev 9, NEW)")). A session survives a tab hop, a reload and a device change through this route.
- **The turn bound:** `POST /investigations/{id}/ask/estimate {question, context_items[], model_choice?}` answers `{cents | null, max_cents | null, basis: {model, input_tokens, max_tokens, participants}, status: ok | unavailable, reason?}` (§1.8 ("The turn bound (rev 9)")).
- **Agent identity:** `ThreadSummary.agent {charter_asset_id, charter_revision_id, home_project_id, project_ids[], managed, envelope?} | null`, plus `merged_from[]` and `merge_ids[]` (§1.2; §1.12a ("State and projection (rev 9)")). The project's agents list is `GET /investigations?agent=true&project_id=`. The reach chip reads the member row's `reach` from `GET /projects/{id}`.
- **What an agent reads:** `GET /investigations/{id}/context?project_id=` (§1.12a ("The one assembler (rev 9, D-A)")). It feeds the "Knows" list. Lane A never assembles context itself.

**Turn states (rev 9).** This is the one turn-state and failure copy set for every dialogue ask: sessions, groups, "Ask this thread" (§2.4), the island Ask (§2.3), Converse (§2.14) and TalkToBook (§2.19).
- `composing`.
- `sending`: the ask is in flight.
- `answering`: the turn is admitted and waiting. There is no token stream in rev 9 (§1.8 ("The answer arrives whole")). The copy is "Working on an answer". A reload whose `open` names this turn returns here.
- `answered`: the answer renders by §2.10 and by its `presentation_mode` (§2.11, T7).
- `failed`: from the ask's `503 {reason, turn_id, attempt, voice_capture_event_id | null}`, or from a `thread.turn_failed` event. The copy is per reason:
  - `unavailable`: "The model isn't available right now." It offers Retry.
  - `interrupted`: "It stopped before answering. Nothing was saved." It offers Retry.
  - `owner_model_outcome_unknown`: "We couldn't tell whether your model answered. Asking again may be charged by your provider." It offers "Ask again".
  - `owner_model_unavailable`: "Your own model can't be used here yet. Use the platform model."
  - `failed`: "It couldn't answer." A known `detail` sub-code gets its own sentence. Any other `detail` is logged and never shown, and the fixed sentence stands (rev 9; §2.11's rule; needs Part 1, R9-11: a closed `detail` set for `thread.turn_failed`). It offers "Ask again".
- **Retry rule (rev 9; §1.8 ("What a repeat of the same key gets")).**
  - Retry reuses the same key. It is offered only for `unavailable` and `interrupted`, where the server re-dispatches as the next attempt.
  - "Ask again" is a new press with a new key. It is used for `owner_model_outcome_unknown`, which must never replay, and for `failed` (needs Part 1, R9-26: the repeat table does not say what the same key gets after `failed`).
  - A replay of an answered turn returns `replayed: true` and renders the first answer. Nothing is charged twice.
- A failed turn has no receipt. Only answered turns do.

**Ask refusals (rev 9; one copy each; no status code is shown):**
- `409 turn_in_progress {turn_id}`: "Still answering the last question." The composer keeps the text, and lane A waits for the socket's `thread.turn` before it enables Send again.
- `404 not_found`: "This conversation no longer exists."
- `422 revision_not_committed` (an `at` still generating): "That part is still being written. Ask again in a moment."
- `422 model_selection_invalid`: "That model can't be used. Choose another."
- `409 owner_model_unavailable`: as in failed, above. Until #3278 lands, only book sessions can use the operator's own model.
- `422 ask_invalid`, by `detail`: `question_empty`, `question_too_long`, `input` and `context_items` take §2.4's copy ("Type a question first."; "Questions can be up to 2,000 characters."; "That voice note couldn't be used. Record it again or type the question."; "One attached item can't be used. Remove it and try again.").
- `422 participants_invalid`, by `detail`:
  - `not_a_member`: "This agent has left this project. Call it in again to keep talking."
  - `agents_unavailable`: "Agents aren't available yet."
  - `not_an_agent`: "This thread is no longer an agent."
  - `too_many` and `duplicate`: lane-A bugs. The group picker caps at four and never repeats a participant.
- `403 not_owner`: "You can't talk to that agent."
- `422 confirmation_required · unpriced`: shows the "Cost unknown" confirmation (groups, below). The confirmed send is a new press with a new key, because `confirm_unpriced` is part of the request identity (needs Part 1, R9-27: whether a request refused before admission binds its key).
- `422 not_a_dialogue`, `422 ask_invalid` with any other `detail` (`at`, `at_span`, `at_foreign`, `context_items_on_group`, `mothership`, `unknown_field`) and `409 idempotency_conflict` are lane-A bugs: log them and never show them to the operator.

**Create refusals (rev 9):**
- `404 project_not_found`: "This project no longer exists."
- `404 document_not_found`: "This book no longer exists."
- `422 participants_invalid` and `403 not_owner`: as for the ask, above.
- `422 participants_invalid` with `detail` `branched_session` or `book_session_has_no_agents` (§1.8, "a branched session: `{detail: branched_session}`"): lane-A bugs, logged and never shown. Lane A never sends participants on a branched dialogue or on a document scope.
- `422 scope_invalid`, `422 launch_invalid`, `409 investigation_id_conflict`: lane-A bugs. For `investigation_id_conflict`, lane A mints a fresh id and creates again.

**Answers and what they cite (rev 9).**
- **The answer** is a `GatedText`. An answer with `origin: unsourced` reads §2.10's "Unsupported: no source". A span with `supported: false` carries §2.11's unsupported mark on that sentence.
- **Refs open on the left.** Each `source_refs` entry `{document_id, anchor}` opens a left child tab with `branch_origin.kind: agent`, `opened_by: {thread_id, agent_kind}` and the passage's `anchor`. `thread_id` is the agent's for a session, and the dialogue's otherwise (§1.12a ("What an agent can do (rev 9)")). prefix+u returns to the passage.
- **In the reading mode** the tab is opened with `transient: true` when the document is not already a member (§1.6 ("`transient` (rev 9; S15"); §2.2). Keep is two writes, in order: `POST /projects/{id}/members {member_kind: document, member_id, member_role: context}`, then the tab PUT that clears `transient`. A `200 already_member` counts as success. (rev 9, Appendix B §A2)
- **Refs outside the project are proposals** (rev 9). The ref offers Keep (the members route) or Read later (`POST /flags {intent: read, target: {document: {document_id}}}`). Nothing is filed until the operator presses one. A cited work with no document in the library reads "Not in your library" and offers nothing to file.
- **Book sessions** carry `answer_spans: []`, so they show page citations and no per-sentence chips (§1.8 ("A book session is the exception")).
- **Cost.** `cost_cents` renders by the nullable rule. Conversational turns are never refused by the cap (§1.13 ("Conversational turn")), so a turn never offers "Raise today's cap".
- **A voice turn** shows its transcript and a "From voice" mark (§2.20).

**The context receipt (rev 9; §1.8 ("The context receipt (rev 9; one payload")).**
- Every answered turn exposes its receipt, returned by the ask and by the turns route. Lane A never computes it. Nothing is dropped silently.
- **Needs:** `items[{item_id, kind, step | null, via: assembler | turn | link, participant_thread_id | null, included, reason: budget | withheld | refs_only | depth_limit | null}]`. The item key is `item_id`. (rev 9, Appendix B §B2)
- **Header.** It counts each outcome, for example "Given 14 · left out 3 (2 no room, 1 held back)".
- **Reasons, in words:**
  - `budget`: "Left out: no room in this turn".
  - `withheld`: "Held back: can't be shown to the model".
  - `refs_only`: "Given as a reference only".
  - `depth_limit`: "Left out: merged more than 8 levels deep". This extends D-A's three reasons; lane A accepts it at the co-sign (Part 1 Appendix C.2 item 1), because D-A's own rule is that nothing is dropped silently.
- **Kinds, in words:** `charter` "Charter", `pack_item` "Its research", `draft` "Merged draft", `turn` "Earlier in this conversation", `attached` "Attached", `context_item` "Added to this question", `chunk` "Passage".
- `via: link` reads "From the linked research project" (book sessions only).
- The receipt holds no text. Each item opens its process where it has one.

**Agent identity (D-A).**
- **The header shows:**
  - the charter title;
  - a home badge, "Home: <project>", when `agent.home_project_id` is not P;
  - the reach chip "Attached only";
  - "Knows: n threads · m merges". `m` is the count of `merge_ids[]`, and `n` is the count of `merged_from[]` (§1.2 ("reads `merged_from[]` and `merge_ids[]`")). (needs Part 1, R9-28: whether an agent's `merged_from[]` includes the members that `thread.merged_in` names, and whether attached threads count.)
- **"Knows" expands** to the context route's items, grouped by assembler step, each one click from its process. Its states (rev 9):
  - `loading`: "Loading what this agent knows…"
  - `ready`: the grouped items.
  - `error`: a network failure or a 5xx. "Couldn't load what this agent knows." with Retry. The chip's counts stay as they were.
  - `422 not_a_member` from the context route (§1.12a, "the agent must be an `agent` or `managed` member of that project, else `422 {reason: not_a_member}`"): "This agent has left this project." The session turns read-only, as under Reacts to.
  - `422 project_required`: a lane-A bug, logged and never shown, because lane A always sends `project_id`.
  - `404 not_found` from the context route: "That agent no longer exists." A missing agent thread and another owner's answer the same (§1.12a, "the charter PATCH, attach, the context route") (rev 9).

**Making an agent and calling it into a project (rev 9; §1.12a ("Promotion (rev 9)"), ("Membership (rev 9;")).**
- **"New agent…"** promotes an idle research or dialogue thread: `POST /investigations/{id}/agent {charter: {title, brief}, model_choice?, idempotency_key}`, which answers `201 {thread_id, charter_asset_id, charter_revision_id}`.
  - `422 not_promotable`: "This kind of thread can't become an agent." Sessions, groups, reformats and reading threads are not offered the action.
  - `409 thread_active`: "Wait until this thread finishes, then make it an agent."
  - `409 already_promoted`: lane A opens the existing agent. It is not an error.
  - `404 not_found`: "This thread no longer exists." A missing thread and another owner's answer the same (§1.15, "A resource in the path") (rev 9).
  - `422 charter_invalid`: marks the field in place: "A title of 1 to 200 characters, and a brief of up to 8,000."
  - `409 idempotency_conflict`: a lane-A bug.
- **"Call an agent from another project…"** writes membership, then opens or creates this project's session: `POST /projects/{id}/members {member_kind: "investigation", member_id: <agent thread_id>, member_role: "agent"}`. The body never carries `reach` or `idempotency_key`; a `422 member_body_invalid` is a lane-A bug.
  - `404 project_not_found`: "This project no longer exists."
  - `404 thread_not_found`: "That agent no longer exists."
  - `403 not_owner`: "You can't call that agent."
  - `422 not_an_agent`: "That thread isn't an agent yet."
  - `422 project_shared`: "This project is shared, so agents can't carry its material across."
  - `409 member_kind_conflict`: "That's already in this project as something else."
  - `200 already_member` or `role_changed` proceeds to the session.
- **"Remove from this project"** is `DELETE /projects/{id}/members/{thread_id}`. The copy says "The agent and its other projects are untouched."

**Charter edits (rev 9; §1.12a ("Charter revision, with compare-and-set")).**
- `PATCH /investigations/{id}/agent {charter, expected_revision_id, idempotency_key?}`. The key is optional. Lane A sends one per press of Save. (rev 9, Appendix B §B2)
- `409 revision_moved {current_revision_id}`: "Changed elsewhere." The edit is kept locally, the form rebases on `current_revision_id`, and the operator re-applies with one key. An edit is never lost.
- `422 not_an_agent` is a lane-A bug.
- `404 not_found` (§1.15, "A resource in the path"): "That agent no longer exists." The edit is kept locally (rev 9).
- The revision list is `GET /derived-assets/agent:<thread_id>/revisions`.

**Attach (rev 9; §1.12a ("Attach (rev 9, D-A)")).**
- **Where from.** "Attach to agent…" is one key from a left tab or selection, a thread tab, a Findings entry or a note. From a reply, it offers the reply's source documents.
  - A selection attaches its whole document as a `doc` item. Items carry `{kind, id}` only (needs Part 1, R9-29: a passage anchor on `doc` items).
- **Needs:** `POST /investigations/{id}/attach {project_id, items[{kind: thread | doc | note | insight, id}], idempotency_key}`, which answers `201 {event_id, items[{kind, id, refs_only}]}`. There is no `project` kind: an agent is given explicit items, never a whole project.
- **The picker shows each item's gate before sending.** A withheld item is disabled with its reason. A cite_only item is labelled "Refs only" and attaches as `refs_only: true`. The picker holds at most 50 items with no repeats, so a `422 items_invalid` is a lane-A bug.
- **Refusals:**
  - `422 item_withheld {index, detail}`: the whole request is refused and nothing is attached. The row is marked: "This item is held back, so nothing was attached. Remove it and try again."
  - `404 item_not_found {index}`: "That item no longer exists", on its row.
  - `403 not_owner {index}`: "You can't attach that", on its row.
  - `422 not_a_member`: "This agent isn't part of this project. Call it in first."
  - `422 project_shared`: the copy above.
  - `422 not_an_agent` and `409 idempotency_conflict`: lane-A bugs.
  - `404 not_found` (the agent in the path; §1.15, "A resource in the path"): "That agent no longer exists." Nothing was attached (rev 9).
- Attachments stay in P. Later receipts list them as "Attached". An item taken down after attaching reads "Held back" there.

**Groups (ruling 20; §1.8 ("Group dialogue in one voice")).**
- **Members.** Two to four agents, chosen from the project's agents list. Each must be an `agent` or `managed` member of P. A group is a session with `dialogue_kind: group`.
- **The bound before sending.** The composer shows the turn's bound from the estimate route: the estimate and "Up to $<max_cents>".
  - When `status` is `unavailable`, the figure reads "—" with the reason ("Price unknown for this model"). Send becomes "Send (cost unknown)", and a press sends `confirm_unpriced: true`. (rev 9, Appendix B §B2)
  - Rev 9 has no rounds (§1.8 ("Withdrawn")). Lane A's "per-round bound" is the turn's bound.
- **No per-turn attachments on a group.** The composer hides "Add to this question" on a group. Material reaches the agents through Attach. (rev 9, Appendix B §B2)
- **One answer, attributed per sentence.** Each sentence carries a chip from `answer_spans[].origin_thread_id`: a glyph plus the agent's name, AA in both themes, never colour alone.
  - `null` with `reason: mixed` reads "Several agents".
  - `null` with `reason: unsupported` reads "No source".
- **Who could not contribute.** A line under the answer names every participant whose `contributions` entry has `contributed: false`:
  - `withheld`: "<agent>: participant withheld".
  - `budget`: "<agent>: left out, no room this turn".
  - `empty`: "<agent>: had nothing on this".
- The receipt tags every item with its participant.

**Pane states:**
- `no_agent`: "No agent here yet", with "New agent…" and "Call an agent from another project…".
- `loading`.
- `idle` and `running`: a session reads `running` while a turn is open, and `idle` otherwise. It has no terminal state (§1.2 ("A dialogue has no terminal state")).
- `queued` and `running` on the agent header: the agent thread's own state. A promoted thread reads `idle` when nothing of its own runs. Research launched from the agent shows as lanes (§2.4).
- `failed`: the pane could not load. It offers Retry.
- `offline`: "Offline. Nothing was sent." The composer keeps the text.
- `empty`: "This agent knows nothing yet: attach or merge to teach it". Shown only when the context route answers with the charter alone.
- `refused`: any refusal above, with its copy.
- `stale`: the charter moved (`409 revision_moved`), handled as in "Charter edits".
- `withheld`: an old answer that a later takedown withholds reads §2.10's withheld state. The turns route already returns it that way.
- **Fallback.** The singleton `agent:dialogue` is retired. It returns only when feature detection finds no dialogue route, labelled "Conversations aren't saved yet" (R9-4).

**Reacts to** (§1.7 ("one broadcast list"); the socket only nudges, and lane A refetches through owner-scoped reads):
- `thread.turn_requested`: the turn shows `answering`, including a turn asked from another device.
- `thread.turn`: refetch `GET …/turns?after=` for the answer, its provenance and its receipt. The receipt and provenance are not broadcast.
- `thread.turn_failed`: the turn shows `failed`.
- `agent.promoted`, `agent.charter_revised`, `thread.context_attached` and `thread.merged_in` on the agent's log: refetch the header and "Knows".
- `project.members_changed`: refetch the membership. When the agent has left P, the session turns read-only with "This agent has left this project."

### 2.14 Converse (rev 9; R35–R37; rulings 7, 14–16, 18; default 3)

New in rev 9. Converse lets the operator talk to a project, or have it explained aloud. Its data is a plain dialogue scoped to a registry project (§1.8 ("Converse (rev 9; rulings 14 and 16)")).

**The door (rulings 7 and 16; default 3).**
- It is outside the mode cycle. It is reached through More (⌘I) and the `mode.pick` list (prefix+shift+m). It has no ⌘ door and no tab forest (T9). Tab-tree keys are inert here.
- **The home** lists registry projects from `GET /projects` (every presence), grouped under Research, Writing and Books by `default_mode`, with a chip for each other mode the project is present in. Speak requests are never listed (ruling 16).
- Each project offers "Talk" and "Explain in N minutes" (1 to 120), plus its past sessions.
- **Home states:**
  - `loading`;
  - `empty`: "No projects yet", with "New project" (§2.12). Shown only after a real answer.
  - `error`, with Retry;
  - `ready`;
  - `offline`.
- Counts and spend on a project row render by the nullable rule.

**Sessions (rev 9).**
- "Talk" creates a plain dialogue: `POST /investigations {kind: "dialogue", scope: {project_id}, investigation_id, title?}`, with a client-minted id and no participants.
- **Past sessions** are `GET /investigations?kind=dialogue&dialogue_kind=plain&project_id=`, newest first. This leaves out agent sessions, groups and branched dialogues. (rev 9, Appendix B §B3)
- **The session runs in the solo pane** (§2.13), with §2.13's turn states, refusals and receipts. It has no agent header.
- **What it reads.** The project's threads, documents and drafts, and never Speak (§1.8's Converse row). A line under the composer says "Talks over this project's threads, documents and drafts."
- The ask sends `mothership: null`, because Converse is a door.
- "Talk to an agent" on a project opens that agent's §2.13 session in the project instead.

**Input (ruling 14).**
- Text and turn-by-turn voice notes. There is no live duplex conversation.
- **A voice note follows §2.20's conversational rule** (rev 9, default 8 as refined 2026-09-27). The transcript shows and sends after a visible 1.5 s grace window. Enter sends at once, and Esc keeps it in the field for editing. The turn then shows its transcript with a "From voice" mark.

**Spoken reply (optional, per session).**
- A toggle, "Read replies aloud", is off by default. It is remembered for this session in this browser only.
- **Needs:** `POST /speech/tts {source: {turn_event_id: <turn.event_id>}, voice?}` (§1.19 ("Speech output: the `source` gate")). It reads only the answer's served text. A cite-only passage is read as a short fixed notice, never its words.
- **States:**
  - `speaking`, then done;
  - `422 not_servable`: "This answer is held back, so it can't be read aloud."
  - `422 too_long`: "This answer is too long to read aloud."
  - `503 tts_unavailable`: "Reading aloud is unavailable right now."
- The text stays readable in every state.

**The monologue, "Explain in N minutes" (rev 9; ruling 15; §1.11a ("The monologue source (rev 9)")).**
- **The composer** takes a question (1 to 2,000 characters), the minutes (1 to 120), the delivery (audio by default, or text) and an optional voice.
  - The scope is always this project. Lane A never sends `{document_id}` (O-18). (rev 9, Appendix B §B3)
  - It is a paid-work composer, so voice fills an editable draft and never sends by itself (§2.20).
  - **Its conversation (rev 9).** Every monologue names its Converse dialogue as its parent (§1.11a, "is the Converse dialogue"). Inside a session, that is the session. "Explain in N minutes" on a home row first reuses the plain session already open for that project in this door, or otherwise creates one exactly as "Talk" does, with a client-minted `investigation_id`. The player then runs in that session, and its interjections ask there. While the dialogue is being opened, Start reads "Opening a conversation…". If it can't be opened or created, Start is disabled with "Couldn't open a conversation for this. Try again.", with Retry, so a monologue never starts without a parent.
- **Needs:**
  - The estimate: `POST /reformats/estimate {source: {scope: {project_id}, query}, params: {mode: "explain", listening_minutes, delivery, voice?}}`. It answers `{estimate_cents | null, max_cents, reason?, assumptions}`, and `assumptions` carries `tts_chars` and `voice`.
  - The launch: `POST /reformats {source, params, parent_thread_id: <this Converse session>, input?, idempotency_key}`. For a voice query it returns `voice_capture_event_id`, which lane A reads from the answer and never invents. (rev 9, Appendix B §B3)
  - Lane A mints one `idempotency_key` per press of Start and reuses it on retry.
- **The consent line** comes before any spend:
  - "Starts if $<max_cents> of today's cap is free; it pauses if the cap runs out" (§2.8's admission copy), with the estimate beside it;
  - "Free cap today: $<remaining>" from `GET /settings/budget`, with §2.8's split and §2.8's copy for a null (rev 9):
    - When `held_today_cents` is null, or `spent_today_cents` is null because the ledger can't be read, it reads "Free cap today: unknown", and Start is disabled with "Can't check today's cap right now".
    - When `spent_today_cents` is null because a cost today is unknown (`cost_unknown`), it reads "Free cap today: —", with the reason "A cost today is unknown". Start stays available, with the line "The server checks the cap when you start."
  - "Uses <model>".
  - With no figure, it shows the reason and never a number, and Start needs an explicit "Cost unknown" confirmation.
- **Launch refusals:**
  - `402 refused_capped`: "Today's cap has no room for this." It offers "Raise today's cap".
  - `404 project_not_found`: "This project no longer exists."
  - `422 voice_invalid`: "That voice isn't available. Choose another."
  - `422 source_invalid`, `422 params_invalid`, `422 parent_invalid` and `409 idempotency_conflict`: lane-A bugs, logged and never shown.
  - After admission, §2.11's failure vocabulary applies (`unavailable`, `interrupted`, `failed`).

**The player** hosts ActiveListeningPlayer in the pane. The text always renders alongside the audio (ruling 15), from the `drv-<generation_id>` reader view, with §2.11's span classes.
- **Needs** (§1.11a ("The segment list and the stream are two routes")):
  - the segment list: `GET /derived-assets/{asset_id}/revisions/{revision_id}/audio?voice=`, which answers `{revision_id, voice, segments[{n, span_ids[], chars, duration_ms | null, state: pending | ready | failed | withheld, reason | null, url | null}], listening_estimate}`;
  - each segment's `url`, which is the stream `GET …/audio/{n}?voice=`;
  - the spans: `GET /derived-assets/{id}/revisions/{rev}/spans` (§2.11).
- **With `delivery: audio` the server renders each chapter's audio itself** as that chapter commits. Lane A makes no call to start it. (rev 9, Appendix B §B3)
- **States:**
  - `generating`: "Writing chapter n of m", from `reformat.generated.chapter {index, count}`. Chapter 1 plays while later chapters are written.
  - `synthesising`: "Making audio: N of M parts ready", from the segment states.
  - `ready`.
  - **`shortfall`**: `listening_estimate.shortfall` is set. "This project holds about <available_minutes> minutes for the <n> you asked for", with "Research further". That opens the Research composer for this project with the question filled in, as an editable draft; nothing starts without the operator's press. It never pads and never cuts.
  - `over_length` (rev 9): `listening_estimate.minutes` is above the request. "This runs about <m> minutes, longer than the <n> you asked for. Nothing was cut."
  - `refused_capped`: `reformat.audio_render_failed` lists only `cap_reached` failures. "Today's cap ran out before all the audio was made. The text is complete." It offers "Raise today's cap", then "Make the rest", which is `POST /derived-assets/{asset_id}/revisions/{revision_id}/audio {voice?, idempotency_key}` and reuses the parts already made. A launch's `402 refused_capped` never reaches the player: nothing was made, so it takes the launch refusal copy above (rev 9).
  - **"Make the rest" refusals (rev 9; §1.11a, "A shortfall answers `402 refused_capped`").** Lane A mints one key per press:
    - `402 refused_capped`: "Today's cap has no room for this.", with "Raise today's cap". The parts already made stay playable.
    - `422 revision_not_committed`: "Still being written." It is offered again once the chapter commits.
    - `404 not_found`: "This explanation no longer exists." A missing asset and another owner's answer the same (§1.15, "A resource in the path").
    - `409 idempotency_conflict`: a lane-A bug, logged and never shown.
  - `failed`: §2.11's copy. A render with `unavailable` or `failed` parts reads "Some parts couldn't be voiced" and offers Retry through the same audio route.
  - `interrupted`: `reformat.failed {reason: interrupted}`. "It stopped after chapter n. The chapters before it are kept."
- **Parts:**
  - `pending`: "Not ready yet". A stream answer of `409 not_rendered` reads the same.
  - `failed · cap_reached`: "Out of today's cap". (rev 9, Appendix B §B3)
  - `failed · unavailable`: "The voice service wasn't available for this part."
  - `failed · failed` (rev 9): "This part couldn't be voiced." It offers Retry through the same audio route.
  - `withheld`, or a stream answer of `403 withheld`: the part is skipped with "This part is held back". Its text shows §2.10's withheld state.
- **Durations.** A null `duration_ms` renders "—" with "Not measured yet". `listening_estimate.method: "words@150wpm"` reads "about m min"; `measured` reads the measured time.
- **Player keys** are rows on the `converse-player` surface (§2.17): space plays or pauses; ← and → move 15 s; shift+← and shift+→ move to the previous or next chapter.

**Interjections (R37; §1.8 ("lane A's four fields")).**
- Typing, or starting a voice note, while playing pauses playback and offers "Resume at mm:ss".
- The ask carries `at {derived_asset_id, revision_id, span_id, offset_seconds}`. `span_id` is the span being narrated at the pause. Lane A estimates it within the playing part from each span's narrated length (needs Part 1, R9-30: per-span timing within a part). `offset_seconds` records the exact point. The turn sees only spans up to `span_id`.
- The interjection is marked in the transcript: "Asked at mm:ss".
- `422 revision_not_committed` reads "That part is still being written. Ask again in a moment." `at`, `at_span` and `at_foreign` are lane-A bugs.
- `404 not_found` on an interjection reads "That part of the explanation can't be found." It covers an `at` asset that is missing or not the caller's, and the copy says nothing more (§1.8, "also covers an `at` asset that is not the caller's") (rev 9).
- **No parent, no interjection (rev 9).** An interjection asks on the monologue's parent dialogue. A player opened elsewhere (for example from Continue, §2.9) reads that parent from the reformat thread's `parent_thread_id`. When it is null, typing pauses nothing, and the composer is disabled with "Asking here needs the conversation this explanation came from."
- **Re-plan** after an interjection is not offered in rev 9. Part 1 leaves its route open (§1.11a ("Re-plan (rev 9: rule stated, route open)"); R9-31).

**Position (§1.14 ("Listening positions (rev 9, LB-31)")).**
- It is the `reading_state` row on `drv-<generation_id>`, shared with the text view.
- `page_index` is the reader page that holds the first span of the playing part. After a reload, playback resumes at the start of that part, labelled "Resumes at the start of this part". An offset inside a part is not saved until the operator rules on the prefs allowlist (Part 1 Appendix C, "Prefs").
- A `409 reading_state_stale_revision` refetches and rebases, as in §2.9 (rev 8.7). Lane A reads `current` from the body only once LB-14 ships it.

**No client trim (R36-truncation).** The client never shortens a monologue script. `scopeNarrationText`'s trim does not run on monologue paths.

**Reacts to:**
- `reformat.generated` (one per chapter): refetch the spans and the segment list.
- `reformat.audio_rendered`: the revision reads `ready`, with measured durations.
- `reformat.audio_render_failed`: `refused_capped` when every failure is `cap_reached`, otherwise `failed`. (rev 9, Appendix B §B3)
- `reformat.failed`: `failed` or `interrupted`.
- `thread.turn_requested`, `thread.turn` and `thread.turn_failed`: as in §2.13.
- The inbox kind `monologue_ready`, with `ref {thread_id, derived_asset_id, revision_id}` (§1.13 ("Inbox kinds added by rev 9")): "Your explanation of <project> is ready". It opens the player. §2.8's inbox row uses this copy.

### 2.15 Speak door (rev 9; R38–R40; rulings 4–6; defaults 4, 5)

New in rev 9. Speak collects insight requests from people. Its requests are not registry projects: they join a project only as links (ruling 4).

**Layout (ruling 4).**
- Two panes: sections on the left, detail on the right. There are no agent tabs and no tab forest. Tab-tree actions are inert on the door.
- The routes are `/speak`, `/speak/:projectId`, `/speak/invites/:id` and `/speak/public/:id`.
- Below 768 px it collapses to one pane, and h and l swap between the panes.

**Sections (default 5).** My projects, Invites and Public.
- **Keys** (§2.17): prefix+1..3 select a section on the `speak` surface. n/p and ↑/↓ move within a list.
- **Needs:** `GET /speak/sections` answers `{my_projects: {count, attention: int | null, attention_reason?: "inbox_absent"}, invites: {count: null, state: "gated_G7"}, public: {count, contribution: "live" | "gated_G7"}}` (§1.20 ("`GET /speak/sections` (rev 9)")).
- **Rendering:**
  - `my_projects.attention` null with `inbox_absent` reads "—" with "Attention isn't tracked yet". It is never a partial count.
  - Invites shows the locked state, never a number.
  - A null count reads "—" with its reason, never 0 (§1.20 ("Counts are never a false 0")).
- **The counts ship provisional** (§1.20 ("Counts (rev 9, provisional; ruling 6)")). Their labels are fixed, and the co-sign may change how a count is defined. (rev 9, Appendix B §B4)

**My projects.**
- **Needs:** `GET /speak/projects`. Its rows gain `topic_description`, `contributed_voice_count`, `invited_count` and `pending_reping_count`.
- **Labels:** "n voices" (`contributed_voice_count`), "n invited" (`invited_count`), "n waiting on a re-ping" (`pending_reping_count`). `interview_count` is never labelled "voices".
- A null count reads "—" with its reason. For `turns_unreadable` the reason is "Some answers can't be read".
- `empty`: "No insight requests yet", with "New insight request", which is Speak's own create (ruling 4). Shown only after a real answer.

**Detail: a project (§1.20 ("`GET /speak/projects/{id}/detail` (rev 9)")).**
- **Needs:** `GET /speak/projects/{id}/detail`, which answers:
  - `project {project_id, title, topic_description, interview_guide, subject_ref, subject_status, publish_intent, invitation_mode, deliverable_id | null, created_at}`;
  - `economics_gate`;
  - `invites[{invite_id, interview_id, invite_path, required_consent_scopes[], created_at}]`;
  - `interviews[{interview_id, who, status, consent: {record, attribute, publish}, pending_questions | null, last_answer_at | null, unconfirmed_answers | null, under_takedown}]`;
  - `arrivals_unseen | null`, with `arrivals_reason?`;
  - `claims_summary {total, by_verification: {unverified, multiply_attested, operator_attested, contradicted}, under_takedown}`;
  - `repings[{interview_id, who, status, pending_question_count | null, invite_path}]`.

  `topic_description` and `interview_guide` sit inside `project`, as Part 1 places them (rev 9).
- **Invite links are credentials.** `invite_path` carries the invite token. Lane A shows it only as a "Copy invite link" action. It never logs it, never sends it to analytics and never puts it in a URL lane A records.
- **Interviews.** Each shows who, the status, and each consent scope in words ("Recording: granted", "Attribution: absent", "Publishing: revoked"). An interview `under_takedown` reads "Taken down: not counted".
- **Unconfirmed answers** read "Unconfirmed transcript", with Confirm (LB-13 item 2; O-19's fallback). They are left out of claims until confirmed.
  - The Confirm route is not in Part 1 (needs Part 1, R9-32). Until it is named, Confirm is not shown.
  - A null `unconfirmed_answers` (`not_tracked`) reads "—" with "Not tracked yet", never 0.
- A null `arrivals_unseen` (`inbox_absent`) reads "—" with "Arrivals aren't tracked yet".
- **Claims** show the total, each verification group in words, and how many are under takedown.
- **Re-pings** list who is waiting, with `pending_question_count` by the nullable rule, and the existing re-ping action.
- The economics gate renders as today's panel.
- `404 not_found`: "This request no longer exists."

**Detail: an invite (ruling 5).**
- It is the designed locked state: "Requests from other people arrive when sharing opens."
- Invite-link bookmarks are not in rev 9. Part 1 has no route for them (§1.20 ("The optional bookmark route is not in rev 9")), and lane A stores no token in the browser, because the token is the credential. (rev 9)

**Detail: public.**
- **The list** is the LB-34 public listing, ranked, with a Newest toggle (needs Part 1, R9-34: the route that serves this section's list; lane A reads `GET /speak/opportunities` until it is named).
- **Needs:** `GET /speak/public/{project_id}`, which answers `{project_id, title, topic_description, subject_ref, voice_count, invitation_mode, contribution: "live" | "gated_G7", created_at}` (§1.20 ("`GET /speak/public/{project_id}` (rev 9; open)")).
- `voice_count` is labelled "voices".
- While `contribution` is `gated_G7`, contributing shows the locked state: "Contributing opens when sharing opens."
- `404 not_found`: "This request isn't public." The same copy covers a missing, private or taken-down request, so nothing about it is disclosed.

**Send to Writing (ruling 4; D-P; default 4; §1.5a ("Speak → Writing on the Speak side")).**
- **Needs:** `POST /speak/projects/{speak_project_id}/draft {public?, claim_ids?[], interview_ids?[], to_project_id?, idempotency_key}`. It answers today's fields plus `{project, transfer_id, filtered_claims[{claim_id, cause: taken_down | no_record_consent}]}`.
  - Lane A mints one `idempotency_key` per press of Send and reuses it on retry.
  - Choosing claims or interviews sends `claim_ids` or `interview_ids`.
- **Labels:**
  - "Adds to <project>" when the operator picks a Writing project. It sends `to_project_id`. (rev 9, Appendix B §B4)
  - Otherwise, "Sends to Writing: reuses the Writing project it went to before, or creates one from this request". Lane A cannot name that project in advance (needs Part 1, R9-33: the detail does not list the registry projects that link this request).
- **After sending,** the Writing project opens. `filtered_claims` is listed, never hidden: "n claims left out: k taken down, j without consent to record".
- **A redraft** is a new revision of the same deliverable (default 4).
- **Refusals:**
  - `409 target_ambiguous {project_ids[]}`: "This request is already in several Writing projects. Choose one." The picker lists those projects, and the choice resends with `to_project_id`. (rev 9, Appendix B §B4)
  - `404 project_not_found`: "That Writing project no longer exists."
  - `409 product_absent`: "That project isn't in Writing. Open it in Writing first, or choose another."
  - Speak's own not-found: "This request no longer exists."
  - `409 idempotency_conflict`: a lane-A bug.
- **Testimony in Write** (§1.11 ("Share and export (rev 9; O-12's fallback)")). A share or export of a Writing deliverable that holds Speak testimony may answer `422 speak_publish_required {claim_ids[]}`. It is rendered where share and export live, with §2.6's copy ("This includes testimony from Speak that hasn't been cleared to publish (n claims). Clear it in Speak first."), and it lists the claims, each opening its Speak request.

**States:**
- `loading`;
- `empty`: as above, per section;
- `error`, with Retry;
- `no_selection`: "Pick a request";
- `busy`: `503 speak_writer_busy`. "Speak is saving something else; try again in a moment", with Retry;
- `gated`: the G7 locked states above.

No raw status code is shown.

**Copy (ruling 6).** Requests are "insight requests". Biography is one template among them.

**Reacts to:**
- The inbox kinds `speak_answer_received` and `speak_claims_proposed`, each with `ref {speak_project_id, interview_id}` (§1.13 ("Inbox kinds added by rev 9")): a badge on the door and a row in the attention inbox (§2.8). Opening one opens `/speak/:projectId` with that interview in focus.
- The socket's `speak.answer.received` and `speak.claims.proposed`: refetch the sections and the open detail.

### 2.16 Autonomous door (R22-d, R27, R28; ruling 10; D-P, D-A; new in rev 9)

"Autonomous" names only the door. Its unit is `member_role: managed` on a thread's membership (§1.0, "the unit of the Autonomous door"). It is never a product value, a mode, a create seed or a transfer target (D-P tightening 1). Spawning stays off until LB-10 lands and the operator enables it (ruling 10). Until the operator rules on O-11, every continuation is a per-flag consent under D4 (DECISIONS, "The standing autonomy envelope needs the operator").

- **Door.** `/autonomous` sits outside the mode cycle. It is reached through More (⌘I) and the `mode.pick` list (prefix+shift+m). It has no ⌘ door (ruling 7) and no tab forest (T9). There is no "New autonomous project" (D-P), and the create page shows Autonomous disabled (§2.12).
- **States:**
  - `loading`
  - `ready`
  - `empty`: `agents: []`. It reads "No agents are managed yet. In a research project, choose Manage autonomously on an agent's tab." Shown only after a real answer. The roster may ship with `agents: []` before LB-26 (§1.13, "the spawning half may ship ahead of LB-26 with `agents: []`"), and the empty state is the honest reading then.
  - `ledger_unavailable`: the roster answered `503 ledger_unavailable`. It reads "Can't read today's cap right now, so this page can't say whether anything may run." Nothing is shown as able to run, no banner reason is guessed, and Retry is offered.
  - `error`: "Couldn't load your managed agents", with Retry.
  - `offline`: the last roster stays, marked "Offline — may be out of date". Controls that start work are disabled with "You're offline".
  - `refused`: an action was refused, with the copy below.
  - Only if the operator grants O-11: `envelope_live`, `envelope_expired` and `envelope_revoked`.
- **Needs:**
  - **The roster read**: `GET /autonomy/roster` (§1.13, "The roster read (rev 9, LB-28; lane A's request C2)"). It answers `{spawning_enabled, spawning_reason: consent_route_absent | env_refused | cap_exhausted | enabled, agents[{thread_id, title, home_project_id, project_ids[], state, consent_mode: per_flag | envelope, envelope | null, spend_cents | null, spend_reason: null | cost_unknown}]}`. `spawning_enabled` is true exactly when `spawning_reason` is `enabled`, and lane A never infers either one.
  - **The members route** for managing (§1.12a, "Membership (rev 9; the rows are §1.5's"): `POST /projects/{id}/members {member_kind: "investigation", member_id: <the agent's thread_id>, member_role: "managed" | "agent"}`. There is no `reach` and no `idempotency_key` in the body; the route is idempotent by its natural key.
  - `ThreadSummary.agent {charter_asset_id, charter_revision_id, home_project_id, project_ids[], managed, envelope?} | null` (§1.12a, "State and projection (rev 9)"), read on each session's agent (the single entry of a session's `participants[]`, or each agent participant of a group, below) to tell which right-pane tabs hold an agent (rev 9).
  - **The flags** of §2.8, for continuations.
  - `GET /settings/budget` and "Raise today's cap" (§2.8).
  - **The project a row is managed in.** The roster names an agent's home and member projects, but not which of them hold the `managed` role (needs Part 1, R9-35). Until Part 1 serves it, lane A reads `GET /projects/{id}` `members[]` for each id in `agent.project_ids[]`, and keeps the projects whose row for the agent has `member_role: managed` (§1.12a, "`project_ids[]` lists the projects where the thread is an `investigation` member"; §1.5, "Each member is `{member_kind, member_id, member_role, ordinal, reach, added_at}`") (rev 9).
- **Banner.** While `spawning_enabled` is false, a persistent banner reads "Nothing will run from here while spawning is disabled". Its second line gives the reason:
  - `consent_route_absent`: "The consent route isn't live yet. This build can't ask for your consent before spawning."
  - `env_refused`: "Spawning is switched off on the server. Turning it on needs a server change."
  - `cap_exhausted`: "Today's cap is used up", with "Raise today's cap" (§2.8).

  Under `enabled`, there is no banner. Lane A's draft read "Nothing will run while spawning is disabled"; rev 9 adds "from here" (rev 9). An ordinary Flag for diligence inside a project is D4's own path, and this door does not govern it.
- **Roster rows.** Rows are grouped by `home_project_id`, and a null home groups under "No home project". Each row shows:
  - the agent's title;
  - its state, in §1.2's thread-state words; a null `state` takes §2.4's `unknown` copy, "State unknown" (rev 9; rev 8.11 A1);
  - "Spent today": `spend_cents`, or "—" with the reason "A cost today is unknown" when `spend_reason` is `cost_unknown`, never $0.00;
  - its consent mode: `per_flag` reads "Asks you each time", and `envelope` reads "Standing consent up to $max until <time>" (O-11 only);
  - its projects, as chips from `project_ids[]`;
  - its pending continuations, which need `source` on the flag list's items (needs Part 1, R9-20). Until Part 1 serves it, the row omits them and links to the project's diligence flags (§2.8).
- **"Manage autonomously"** (the Research → Autonomous hand-off; rev 9). It acts on agent tabs selected in the right pane of a project in the research mode.
  - It writes the members route with `member_role: managed` for each selected agent. `member_id` is the agent's own `thread_id` (the session's participant), never the session's id. It never calls `/transfers` (§1.5a, "is `member_role: managed` on the thread's existing membership").
  - **Which tabs hold an agent (rev 9).** An agent tab holds P's session thread, a `dialogue` carrying `session_of`, and a session is never promoted, so the tab's own `ThreadSummary.agent` is always null (§1.2, "Null unless the thread is promoted"). Lane A therefore reads the session's agent: the single entry of a `dialogue_kind: session` thread's `ThreadSummary.participants[]` (or a turn's `session_of.agent_thread_id`), then that thread's `ThreadSummary.agent`. On a group tab, each participant whose `ThreadSummary.agent` is set is offered as its own selectable agent. Wherever this section says a tab "is an agent", it means this.
  - It is offered only when that agent's `ThreadSummary.agent` is set. On a tab with no agent participant (a research, reformat or plain dialogue tab), it is disabled with "Only an agent can be managed. Promote this thread first." (promotion is §2.13).
  - "Already managed" shows before any press when this project's `members[]` row for the agent has `member_role: managed`. `agent.managed` alone says only that some project manages it (§1.12a, "`managed` is true when any of its membership rows has") (rev 9).
  - It writes a membership and spends nothing, so it stays available while spawning is off. Its confirm line reads "Marks this agent as managed. Nothing runs from here until spawning is on, and each continuation asks for your consent."
  - **Answers:**
    - `201 added` and `200 role_changed` read "Now managed".
    - `200 already_member` reads "Already managed".
    - With several agents selected, the result lists each agent: "2 of 3 now managed. <agent>: <reason>".
  - **Refusals:**
    - `404 project_not_found` reads "That project no longer exists."
    - `404 thread_not_found` reads "That agent's thread no longer exists."
    - `403 not_owner` reads "You can't manage that agent." The copy never says whose agent it is (rev 9).
    - `422 not_an_agent` reads "Only an agent can be managed. Promote this thread first."
    - `422 project_shared` reads "This project is shared, so agents can't be managed in it."
    - `409 member_kind_conflict` reads "This thread is already in the project as something else."
    - `422 member_body_invalid` is a lane-A bug. It is logged, and the row reads "Couldn't save that. Try again."
- **"Stop managing"** swaps the role back with `member_role: "agent"`, which the members route allows (§1.12a, "`agent` and `managed` can swap"). It answers `200 role_changed`, and the row leaves the roster on refetch. The agent, its sessions and its other memberships are untouched. The swap names the project where the row is managed, found by the fallback under Needs until Part 1 serves it (needs Part 1, R9-35).
- **"Continue"** (per flag, D4). It opens the managed thread's output as a right tab in its project, focused on its open-question segments. There, Flag on an open question sends the continuation flag of §2.8 (`{question_id}` plus `source.thread_id`), and §2.8's consent sheet does the rest. Nothing standing is written.
  - While `spawning_enabled` is false, Continue is disabled, and its reason is the banner's reason (A24's "the controls that would start work say why they are off").
  - Part 1 does not say whether the server refuses a continuation launch while spawning is off (needs Part 1, R9-36). The UI rule stands either way.
- **If the operator grants O-11**, "Manage autonomously" also offers "Give standing consent…", an envelope consent sheet with:
  - the estimate;
  - `max_cents`, at most today's cap;
  - an expiry of at most 24 h;
  - the copy "Starts if $X of today's cap is free; it pauses if the cap runs out".

  It writes `POST /investigations/{id}/autonomy`, whose body and refusals Part 1 has not defined (needs Part 1, R9-37). Revoke is `DELETE /investigations/{id}/autonomy`, on one key from §2.17's table. The row shows `envelope.state`:
  - `live`: "Standing consent up to $max until <time>", with `spent_cents`, or "—" when it is null;
  - `expired`: "Standing consent expired at <time>. Continuations ask each time again."
  - `revoked`: "Standing consent revoked."

  Until O-11 is granted, these routes and states do not exist, and nothing on the page mentions them.
- **Threads.** Each managed thread opens as a right tab in its project, in the research mode.
  - If that mode is no longer in the project's `products[]`, the tab write answers `409 product_absent`. The row then reads "This project isn't open in Research any more", and offers "Open in Research" (§2.18).
  - Opening the project itself from this door follows the landing rule: `last_mode`, else `default_mode` (§1.5, "It is `home_product` when present, otherwise the first entry of `products[]`. It is never null.").
- **Reacts to:**
  - `project.members_changed` on `project-<id>` (§1.7, "one broadcast list"): refetch the roster.
  - `agent.promoted`: refresh which tabs can be managed.
  - A continuation's consent lifecycle events and the spawned thread's state events: refresh that row.
  - "Raise today's cap" returning, and the window regaining focus: refetch the roster, because `cap_exhausted` may have cleared.
  - Only if O-11 is granted: `agent.autonomy_consented` and `agent.autonomy_revoked`.

### 2.17 Keymap surfaces (rev 9; R24, R31, R40)

One keymap table stays the source of truth (D2). The key sheet (`prefix+?`) and every control's `aria-keyshortcuts` are generated from its rows, so they cannot drift from the handlers. Every direct chord has a prefix twin: the chord is a convenience, and the prefix is the guarantee. The rows not named here stand as in DESIGN-MODEL §2 (C3 confirmed 2026-09-26). No Part 1 route owns a key. The server reads the keys depend on are listed under **Needs**.

- **Surface scope (rev 9).**
  - A row may carry `surface?: reader | speak | converse-player`. These are UI names, not data names.
  - A surface row fires only when focus is inside a node carrying the matching `data-key-surface`, and never inside text.
  - A row with no surface fires everywhere except inside a surface that lists it in that surface's `shadows[]`. The existing `anywhere | outside-text` scope is unchanged.
- **The collision rule** (checked by `validateKeymap`):
  - Two rows share a chord only when their surfaces are disjoint.
  - A surface row shadows a global row only when that row is listed in the surface's `shadows[]`.
  - `speak` shadows `tab.root` 1..3. `reader` and `converse-player` share ←, → and space, which is allowed because they are disjoint.
  - Tree actions (`tab.root`, n/p, u/o, t, `prefix+c`, `prefix+shift+x`, `prefix+shift+t`) are inert on doors (Home, Speak, Converse, Autonomous), because a door has no tree (T9; ruling 4; default 3).
- **Rows added in rev 9:**

  | Action | Prefix | Direct chord | Where it fires |
  |---|---|---|---|
  | `mode.cycle` | prefix+m | ctrl+alt+m | outside text |
  | `mode.pick` | prefix+shift+m | none | outside text |
  | `project.list` | prefix+w | ctrl+alt+w | outside text |
  | `project.new` | prefix+shift+n | ctrl+alt+n | outside text |
  | `tab.root` 1..9 | prefix+1..9 | ctrl+alt+1..9 (D2 amended, ruling 9) | outside text; inert on doors |
  | `island.open` | prefix+a | ctrl+alt+a | outside text, with or without a selection (§2.3) |
  | `pane.solo` | prefix+s | ctrl+alt+s | outside text (§2.13) |
  | `voice.toggle` | prefix+v | ctrl+alt+v | the direct chord also fires inside the composer it fills; the prefix twin fires outside text (§2.20) |
  | reader page keys | ← (back), → (forward), space (forward) | none | `reader` only |
  | Speak section keys | prefix+1..3 (My projects, Invites, Public); n/p and ↑/↓ move within the list | none | `speak` only; shadows `tab.root` 1..3 |
  | player keys | space (play or pause), ← and → (15 s back or forward), shift+← and shift+→ (previous or next chapter) | none | `converse-player` only |

  - The reserved entries these rows replace are removed from the table.
  - **Not bound in rev 9.** Next and previous project are deferred (ruling 9), so DESIGN-MODEL's `ctrl+alt+shift+]` and `ctrl+alt+shift+[` project rows are not bound. D2's `ctrl+alt+1..9` for projects is amended to tabs, and projects take digits inside the `project.list` overlay instead (ruling 9). ⌘B stays unbound (ruling 1).
  - **Fullscreen.** C3 stands, and the browser's ⌘F stays Find. `pane.fullscreen` (prefix+f, ctrl+alt+f) is the "Command-F" of R25, and the key sheet labels it that way (default 7).
- **What each rev-9 row does.**
  - **`mode.cycle`** keeps the project and moves to the next mode, in the order research → writing → reading, among the modes in the project's `products[]` (D-P; §1.0 "presence (D-P)"). It restores that mode's `active {left, right}` from `GET /projects/{id}/tabs/{mothership}`. On an API that serves no `products[]` (before rev 9, detected by feature), it cycles all three. On a door with an active project, it enters that project's cockpit in `last_mode`, else `default_mode`, the same landing as `project.list` from a door (lane-A choice, for the co-sign).
  - **`mode.pick`** opens a picker: the three modes, labelled Research, Writing and Books, then the doors Home, Speak, Converse and Autonomous, each with a digit accelerator (ruling 7). A present mode opens directly. An absent mode shows its whole-transfer offer from `offers.whole` (§1.5a "Candidates"), and Enter on an available offer runs the transfer (§2.18), then enters the mode. It never appends a mode silently.
  - **`project.list`** opens an overlay with one row per project (D-P).
    - Each row shows mode badges from `products[]`, with the labels above.
    - A project with `derived_from_project_id` is indented under its source. A ruling-11 link shows as a chip ("Linked: <title>"), not as nesting, because both sides list each other (`linked_project_ids[]`).
    - Digits, or j/k then Enter, open the project.
    - **Where it lands** (DECISIONS 2026-09-27 "Where a project key lands", with Part 1's `default_mode`, rev 9): in the current mode when the project is present there; otherwise in `last_mode`; otherwise in `default_mode` (§1.5 "`default_mode` (NEW in rev 9)"). `default_mode` is `home_product` whenever that is present, so this keeps the ruling, and it also covers a project whose `home_product` it has left. From a door outside the cycle, it lands in `last_mode`, else `default_mode`.
    - Esc returns focus to the element that opened the overlay.
  - **`project.new`** opens the create page (§2.12) with the current mode's product preselected. From a door, no product is preselected.
  - **`tab.root` n** keeps its meaning (DESIGN-MODEL §2) and gains the `ctrl+alt+1..9` chord.
  - **Door keys (ruling 8).** ⌘J, ⌘E and ⌘Y open the Research, Books and Writing homes (C1), and ⌘U keeps its existing door, under the same rule. Each home opens with the active project pre-focused, so Enter goes into its cockpit in that mode. Converse and Autonomous have no ⌘ door; they are reached through More (⌘I) and `mode.pick` (ruling 7). The mod+g duplicate is left alone for now (ruling 7).
- **States:**
  - **Key sheet:** `closed` or `open`. Open, it renders Product, Project and Cockpit sections from the table. A surface row appears under the section of the product that hosts it, tagged with where it works ("in the reader", "in Speak", "in the player"). Every chord is listed beside its prefix twin.
  - **Focus scope**, decided on each key press: `global`, `in_surface(<name>)`, `in_text` or `on_door`.
  - **`mode.cycle`:** `cycled`, `single_mode` (one entry in `products[]`) or `products_unknown` (no `products[]` field).
  - **`mode.pick` rows:** `present`, `offer_loading`, `offer_available`, `offer_unavailable` (with its reason) or `offer_unknown` (the offers read failed).
  - **`project.list`:** `loading`, `ready`, `empty` or `error`.
  - **Door key:** `prefocused`, `not_present` (the active project is not in that product) or `no_active_project`.
- **Copy:**
  - A tree key on a door: nothing changes, and no toast appears. On a door, the key sheet shows tree rows dimmed with "Not on <door name>".
  - A surface key while focus is in text: it never fires, and the character is typed.
  - `single_mode`: a quiet toast, "<Project> is only in <mode label>. Press the prefix, then shift+M, to open it in another mode."
  - `mode.pick`, the current mode: "<mode label> · current".
  - `offer_available`: "Open in <mode label> — transfers the whole project (no model spend)". For a book project and Research (T6), the row reads §2.1's "Turn this book into a new project — it gains Research and keeps its shelf (no model spend)".
  - `offer_loading`: "Checking…"
  - `offer_unavailable`, by `offers.whole.reason` (rev 9; §1.5a "Book and interest rows (rev 9)"): §2.1's disabled copy.
    - `transfer_not_supported` on a book project to Writing: "A book project can't open in Writing. Turn it into a new project first."
    - `transfer_not_supported` on an interest project: "An interest project stays in Books."
    - `project_archived`: "Archived projects can't open in another mode. Unarchive it first."
    - `product_present` means another device already added the mode: lane A refetches the row and shows it as `present`.
  - `offer_unknown`: "—", with the reason "Couldn't check whether this project can open in <mode label>" on hover and on focus, plus Retry. The row stays disabled until the check answers.
  - `project.list` `empty`: "No projects yet. Press the prefix, then shift+N, to start one."
  - `project.list` `error`: "Couldn't load your projects." Retry.
  - Row counts follow the nullable rule, with the reason taken from `null_reasons`: `logs_unreadable` reads "Thread records can't be read right now", `ledger_unreachable` reads "Ledger unreachable", and `cost_unknown` reads "A cost today is unknown". A null with no `null_reasons` entry takes §2.1's copy: "Still counting" for `thread_counts`, and "Spend by project isn't recorded yet" for `spend_today` (rev 9; rev 8.11 A7). `shelf_count` shows only on projects in Books; `not_in_product` is a known absence, not an unknown, so no "—" is drawn for it.
  - Door key, `not_present`: the home opens with nothing pre-focused, and a line at its top reads "<Project> isn't in <mode label> yet." It is followed by that project's offer row, or by the disabled copy above.
  - Door key, `no_active_project`: the home opens with nothing pre-focused.
  - `voice.toggle` with no composer in reach: nothing records, and the key sheet tags the row "Needs a composer". Esc while recording discards the recording (§2.20).
- **Needs:**
  - `GET /projects` for `project.list`, and `GET /projects?product=<mode>` for the homes the door keys open (§1.5 "Presence filter"). Homes list by presence, never by `home_product`.
  - Row fields (§1.5 "Row shape (rev 9)"): `products[]`, `home_product` (never a filter), `last_mode`, `default_mode`, `kind`, `derived_from_project_id`, `linked_project_ids[]`, `thread_counts`, `spend_today`, `shelf_count`, `null_reasons`.
  - `GET /projects/{id}` for the active project's row on a door key.
  - `GET /projects/{id}/tabs/{mothership}` for `active {left, right}` on `mode.cycle` and on landing.
  - `GET /projects/{id}/transfer-candidates?to_product=<mode>&limit=1` for `offers.whole` on `mode.pick`'s absent rows (§1.5a "Candidates"). Only `offers` is read (needs Part 1, R9-38: an offers-only read; the fallback is a lazy read when a row gains focus).
  - `POST /projects/{id}/transfers` for the whole transfer, through §2.18, which owns its refusal copy.
  - Mode values `research | writing | reading`, labelled Research, Writing and Books (§1.0).
  - Client-only table fields: `action`, `keys`, `scope`, `surface?`, and `shadows[]` on each surface.
- **Reacts to** (broadcast on `WS /ws/events`, §1.7 "one broadcast list"):
  - `project.created`, `project.updated`, `project.members_changed`, `project.product_left` and `project.transferred`: refetch the affected row in an open `project.list` overlay, and recompute the `mode.cycle` set for the active project. A `project.product_left` for the current mode is handled by §2.2 (`mode_absent`).
  - Every push is a nudge. Lane A refetches through an owner-scoped read, because the socket carries no owner filter.

### 2.18 Transfers (R28, R33; D-P; rev 9, new)

A transfer never copies content (§1.5a "A transfer never copies content"). There are two scopes:
- **Whole:** the same project gains a mode. Its trees, seen positions, spend history and Findings stay intact, and the same id opens in the target mode with its own tree (T9).
- **Partial:** member references are placed in a new or a named project.

Every transfer spends nothing on models, and each action says "(no model spend)".

- **What is offered through `/projects/{id}/transfers`** (Part 1's T1–T6, §1.5a "Supported transfers (rev 9)"; Appendix B §B7):

  | # | From | Action (palette twin) | Scope | Selection |
  |---|---|---|---|---|
  | T1 | any `kind: project` row, to a mode it lacks | "Open in <mode> — transfers the whole project (no model spend)" | whole | none |
  | T2 | a `kind: project` row with Research, to Writing | "Open in Writing", with the optional step "Start the piece from these threads" | whole | threads, optionally narrowed to notes |
  | T3 | a `kind: project` row with Research | "Send part to Writing…" | partial | threads, optionally narrowed to notes (required) |
  | T4 | a `kind: project` row with Research, to Books | "Deep read in Books" | whole | documents |
  | T5 | a `kind: project` row with Research | "Send part to Books…" | partial | documents and/or insights (required) |
  | T6 | a book project (`kind: reading`), to Research | "Turn this book into a new project" | whole | none |

  - **T1 covers the plain cases.** These are "Open in <mode>" on a `not_in_mode` project (§2.1), a Writing project gaining Research, and coming back after a leave, when the kept tree reappears unchanged (§1.5 "The kept tree reappears unchanged").
  - A whole transfer to Writing with no threads chosen is T1. With threads, it is T2.
  - **Books from a research project (R33).** "Deep read in Books" opens the document candidates. Picking documents sends T4, and the project lands in Books with those documents on the shelf. "Skip for now" sends T1, and the project lands on the "Which book(s)?" seed step (§2.19), never an empty pane.
  - **From the Books side**, R33 is the ruling-11 link, not a transfer (§2.1 "Add to a research project…").
  - **T6** changes the book project's kind to `project` and adds Research. Its id, members, threads, shelf and primary document are unchanged.
- **Not through this route (rev 9):**
  - **Research → Autonomous** is `POST /projects/{id}/members {member_kind: investigation, member_id, member_role: managed}`, with no `reach` (§1.5a "Not this route"; Appendix B §B5). "Manage autonomously" lives in §2.16. Autonomous is not a product, so nothing is appended.
  - **Speak → Writing** is the Speak-side route (§2.15), because a Speak request is not a registry project (ruling 4).
- **Offers decide what is enabled** (rev 9; §1.5a "The UI therefore never meets"):
  - Each action reads `offers.whole` or `offers.partial` from the candidates read for its target mode. An action is enabled only when `available` is true.
  - **A disabled whole-scope action** (T1, T2, T4, T6) shows §2.1's disabled copy for its `offers.whole.reason`, the one copy set for a disabled mode offer (rev 9). For `product_present`, nothing is offered, because the mode is present, and the row is refetched.
  - **A disabled partial action** (T3, T5) shows this section's own lines for `offers.partial.reason` (rev 9):
    - `project_archived`: "Archived projects can't be transferred. Unarchive it first."
    - `transfer_not_supported` (for example a partial transfer from a project without Research, or from a book or interest project): "Send part needs this project's research. Open it in Research first."
  - The transfer dialog lists only available actions. The mode switchers show a disabled offer with its reason, so a mode is never silently absent (§2.1).
  - A `422 transfer_not_supported` answer is therefore unreachable. If one arrives, lane A logs a lane-A bug, refetches `offers`, and shows "This transfer isn't available."
- **Needs** (§1.5a "Candidates (rev 9)"; S16):
  - `GET /projects/{id}/transfer-candidates?to_product=&to_project_id=&cursor=&limit=` returns `{to_product, offers, items[], next_cursor}`. Lane A pages until `next_cursor` is null. Each item is rendered this way:
    - **Thread** (`candidate_kind: investigation`): `title`, `state` and `excerpt` (a `GatedText`, rendered by §2.10). A thread with `unavailable_reason: no_synthesis` is listed but not selectable, and reads "No synthesis yet, so there's nothing to place." It is never dropped. A null `state` takes §2.4's `unknown` copy (rev 9; rev 8.11 A1).
    - **Document**: `title`, `author`, `document_type`, `is_book`, and the flat `gate` and `reason` from Part 1's one gate projection (Appendix B §A6/§B8). Books come first, and a non-book carries its type marker. A document that can't be served is listed with its §2.10 state and stays selectable.
    - **Insight** (`candidate_kind: node`): `content` as a `GatedText`. Until LB-24a lands, it reads `withheld · unresolved` ("Held back: its sources can't be found") and stays selectable by its id (§1.5a "A node's `content` is composed by").
    - With `to_project_id`, each item carries `already_in_target`. Such an item reads "Already in <target>" and starts unselected.
  - `POST /projects/{id}/transfers {to_product, scope, to_project_id?, new_project?, selection: {investigation_ids?, node_ids?, document_ids?}, idempotency_key}` returns `201 {transfer, source, target}`. For a whole transfer, `source` and `target` are the same row. A replay answers `200` with the same shape.
    - Lane A mints the key when the operator presses Transfer, and reuses it for every retry of that press. A changed selection is a new press with a new key.
    - A whole transfer sends neither target field.
    - A partial transfer sends exactly one target: `to_project_id` for an existing project, or `new_project {kind, title?, primary_document_id?}` for a new one (rev 9).
  - `GET /projects/{id}/transfers?direction=to` returns this project's received transfers, newest first. The lineage chip reads it.
  - `GET /projects/{id}` gives the target's current `members[]` for the preview.
  - `DELETE /projects/{id}/products/{product}` is the leave, and PATCH `archived` is the archive (§1.5, "Leave is not archive").
- **Whole.** One confirm names the effect: "Open in <mode> — transfers the whole project (no model spend). Everything here stays as it is." After `201`, the same project opens in the target mode, using §2.1's landing rule for that mode.
- **Partial:**
  - **The candidate list** shows each item's gate. A header counts every kind ("12 items, 3 cite-only, 1 held back"), following §2.10.
  - **The client enforces the bounds** before sending: "At most 50 threads per transfer" and "At most 1,000 documents or insights per transfer".
  - **The target picker** offers two choices:
    - "A new linked project". To Writing, it is `new_project {kind: project, title?}`. To Books, it is `{kind: reading, primary_document_id}`, where the primary is one of the chosen documents and the picker asks "Which book leads?". It may instead be `{kind: interest, title}`, where a title is required.
    - "An existing project". The picker lists `GET /projects?product=<to_product>`, without the source and without archived projects.
  - **The preview** lists the target's member set after the transfer: its current members plus the selection, by kind ("The target will hold 4 threads and 12 documents; 3 are new"). Lane A composes it from the target's `members[]` and the selection. A target read that fails renders "—" with "Couldn't read the target", and Transfer stays enabled because the server re-validates at commit (§1.5a "Items are re-validated at commit").
  - **A book that already has its project.** When `new_project {kind: reading}` names a document that already has the owner's book project, the server uses that project and `target_created` is false (§1.5a "A book already has its project"). The toast reads "Added to your existing project for this book."
  - **After `201`,** the source is unchanged and stays open. The toast offers "Open <target>".
- **The lineage chip (rev 9).** It is shown only on a project whose `derived_from_project_id` is set, because that field is set only when a transfer creates the target (§1.5a "set only when the transfer creates the target").
  - **The chip** reads "derived from <source title> · n members · <date>". `n` and `<date>` come from the newest received transfer (`?direction=to`): the count of its selection and its `created_at`. If the source row answers `404 project_not_found`, the chip reads "derived from a project that's no longer available".
  - **"n new since transfer"** counts the source's candidates for this mode, read with `to_project_id=<this project>`, that are selectable and have `already_in_target: false`. If either read fails, it renders "—" with the reason "Couldn't compare with the source". It is never 0 on a failure.
  - **"Re-transfer from source"** opens the source's partial dialog with this project as the named target and the new items preselected. Nothing re-syncs silently.
- **Leaving and archiving (rev 9; §1.5 "Leave is not archive").** They are separate controls, and each names what it does.
  - **"Leave <mode>"** asks: "Leave <mode>? The project stops showing in <mode>. Its <mode> tabs, members and threads are kept, and Open in <mode> brings them back."
    - `200 left` refetches the row.
    - `200 not_present` is treated as success, because the mode is already gone.
    - `404 project_not_found` (the project is missing, or another owner's; §1.15, "A resource in the path"): §2.1's `not_found` (rev 9).
  - **The last mode.** When `products[]` has one entry, "Leave <mode>" is disabled with "This is the project's only mode. Archive it instead." A book or interest project therefore never offers "Leave Books". A `409 last_product` (a race) shows the same line.
  - **"Archive project"** asks: "Archive this project? It leaves every home. Nothing is deleted." "Unarchive" reverses it.
- **States:**
  - `choosing`: the scope, the selection and the target.
  - `previewing`: the target member set.
  - `transferring`: locked, with progress.
  - `transferred`: the whole landing or the partial toast above.
  - `failed`: a network failure or a 5xx. The copy is "The transfer didn't finish. Nothing was moved." Retry reuses the same key, and the replay check keeps it to one transfer (§1.5a "Record and listing (rev 9)").
  - For the candidate picker:
    - `loading`;
    - `empty`: "Nothing here to transfer yet." It is shown only after a real answer.
    - `error`: "Couldn't load what can be transferred. Try again."
- **Refusals, in plain words** (narrowed on `reason`, then on `detail`, §1.0a "Every refusal that rev 9 adds or changes"). No raw status or server code is shown.
  - `409 product_present` (a race): "It's already in <mode>." Lane A refetches the row and opens the project in that mode.
  - `409 {reason: project_archived, project_id}`: "That project is archived. Unarchive it to transfer."
  - `404 project_not_found` for the source: §2.1's `not_found`. For a named target: "That project can't be found. Pick another."
  - `404 {reason: thread_not_found | source_not_found, ref}`: "One of the chosen items no longer exists." Lane A refetches the candidates and keeps the rest of the selection.
  - `403 {reason: not_owner, ref}`: "One of the chosen items can't be moved from here." Lane A deselects it. The copy never says whose it is (rev 9).
  - `422 {reason: transfer_invalid, detail}` falls into two groups.
    - Races that the operator can fix. Lane A refetches the candidates, removes the named ids from the selection and shows:
      - `selection_not_candidate`: "Some chosen items are no longer in this project."
      - `no_synthesis`: "A chosen thread has no synthesis yet."
      - `node_not_in_selection`: "Some chosen notes aren't in the chosen threads."
      - `empty_section`: "Each chosen thread needs at least one note."
      - `not_reader_openable`: "The reader can't open a chosen document yet."
      - `document_unclassified`: "A chosen document hasn't been classified yet."
      - `node_not_insight`: "Only insights can go to Books."
      - `target_not_in_product`: "That project isn't in <mode> any more. Pick another."
    - Lane-A bugs, because the dialog composes the body: `selection_required`, `selection_not_allowed`, `selection_kind_invalid`, `too_many`, `target_required`, `target_not_allowed`, `target_is_source` and `new_project_invalid`. Lane A logs them and shows "Something went wrong on our side. Nothing was moved."
  - `409 {reason: idempotency_conflict, transfer_id}` means a key was reused for a different request. That is a lane-A bug: log it, mint a fresh key, and never show it.
  - `422 idempotency_key_invalid`: a lane-A bug, logged and never shown.
- **Reacts to** (§1.7, "one broadcast list"; each push is a nudge and is refetched through an owner-scoped read):
  - `project.transferred` on this project's log: refetch the row, the offers and the lineage chip.
  - `project.created {via: transfer}`, and `project.members_changed` or `project.shelf_changed` with `cause: transfer`: refresh "n new since transfer" and any open preview.
  - `project.product_left` and `project.updated` (archive): refetch the offers and the Leave control.
  - The seam events (`seam.research_to_read`) are server-written. The UI never writes or forges them.

### 2.19 Books surfaces: shelf, Notebook, detours, TalkToBook (rev 9; R30–R33; rulings 11–13; default 2)

The whole section is new in rev 9.

- **Shelf** (S15; §1.5, "Shelf (rev 9; S15; ruling 12)"):
  - **Needs:** `GET /projects/{id}/shelf` returns `{project_id, shelf_version, in_product, items[]}`. Each item is:
    - `document_id`, `member_role: primary | shelf` and `ordinal | null`;
    - `title | null`, `author | null`, `document_type | null` and `is_book`;
    - `gate` and `reason`;
    - `progress: {page_index, page_count, pct} | null`;
    - `adopted_version?: {derived_asset_id, revision_id}`.
  - **States (rev 9):**
    - `loading`
    - `empty`: no items. "No books on this shelf yet. Add the first one." Shown only after a real answer. A book project always lists its primary, so only an interest project's shelf, or a `kind: project` row's, can be empty (rev 9).
    - `error`: a network failure or a 5xx. "Couldn't load the shelf." with Retry.
    - `ready`
    - `read_only`: `in_product` is false (Left Books, below).
  - **Order.** The server's order is primary first, then books by `ordinal`, then non-books by `ordinal` (§1.5, "then books by `ordinal`, then non-books by `ordinal`"). Lane A renders that order and never re-sorts.
  - **Non-books (ruling 12).** `is_book` is `document_type == "book"` (§1.5, "never derived from having a `book_assets` row"). A non-book carries a marker from `document_type`: "Article", "Paper", "Web page", otherwise "Document".
  - **Gate.** `gate` and `reason` come from the one projection (§1.5, "One gate projection (rev 9)"), and render by §2.10:
    - `served`: this includes the operator's own `personal_reading` document.
    - `cite_only · not_servable`: "Can be cited, not shown in full here".
    - `withheld · not_servable` (taken down): "Taken down. It stays listed so you can see it was here."
    - `withheld · unresolved`, with null metadata: "Couldn't find this document", with "Remove from shelf".

    An item is never dropped.
  - **Progress.** It reads "page n of m". A null renders "—" with the reason "No position yet, or page count unknown". Part 1 does not say which (needs Part 1, R9-39).
  - **Adopted version.** When set, a chip reads "Reading version: revision n". It opens that reformulation (§2.11).
  - **Left Books.** When `in_product` is false (§1.5, "says whether `reading` is in `products[]`"), the project has left Books. The shelf still reads, editing is off, and it says "This project has left Books. Open it in Books to change the shelf." The "Open in Books" offer is §2.18's. A `409 product_absent` on a PUT takes the same copy.
- **Reorder, add and remove.** All three use `PUT /projects/{id}/shelf {document_ids[], expected_version}`.
  - `document_ids[]` is the complete, ordered list of `shelf` rows, with the primary left out. Lane A always sends the whole list, and the order is `ordinal`.
  - **Add.** Adding inserts a document into the list. A kept document (a `context` member) becomes a shelf item. (needs Part 1, R9-24: a picker field for reader-openable and classified documents; the fallback is the refusal copy below.)
  - **Remove.** Leaving an item out removes it from the project, not only from the shelf (§1.5, "A `shelf` row that is left out is removed from the project"). The control reads "Remove from this project", and the confirm says "Your place in it is kept".
  - **Keyboard reorder** moves the item at once and sends one debounced PUT.
  - **`409 version_stale {current}`:**
    - When `current`'s list equals the list lane A sent, the PUT already landed, and lane A treats it as success (§1.5, "The client treats an equal list as success").
    - Otherwise lane A re-applies the operator's pending move onto `current` and PUTs again with `current.shelf_version`. It shows the quiet toast "Changed elsewhere".
    - A move whose document is gone from `current` is dropped.
  - **Refusals.** A refused PUT changes nothing, so the shelf stays as it was, and the refused item is marked by its title (from `document_id`):
    - `422 shelf_invalid · not_reader_openable`: "This can't open in the reader yet, so it can't go on the shelf."
    - `422 shelf_invalid · document_unclassified` (LB-35 spec Q9): "This document hasn't been classified yet, so it can't go on the shelf."
    - `422 shelf_invalid · too_many`: "A shelf holds up to 1,000 items."
    - `404 source_not_found`: "That document no longer exists." Another owner's private document answers exactly the same, so the copy is the same (rev 9; §1.15, "Another owner's private document answers exactly as a missing one").
    - `404 project_not_found` (the project is missing, or another owner's; §1.15, "A resource in the path"): §2.1's `not_found` (rev 9).
    - `409 product_absent`: the "left Books" copy above.
    - `shelf_invalid · duplicate` and `shelf_invalid · primary_not_shelf` are lane-A bugs: logged, never shown.
  - **Agents only propose (rev 9;** §1.5, "Actor (rev 9)"**).** No rev-9 route acts as an agent, so lane A never meets `403 agent_cannot_curate`. If it ever does, that is a lane-A bug. An agent's suggestions arrive as answer refs, and the operator's press Keeps them, shelves them or files them as Read later (TalkToBook, below).
  - **Opening a non-book.** Once LB-35 lands (§1.18a), a non-book opens in the reader. It has no chapters ("No chapters in this document") and its progress reads "—" (§1.18a, "has the same `BookDetail` shape"). Until then it opens as a document tab that reads "Opens outside the reader for now", never a failed reader.
  - **No ad rail on non-books.** None is mounted on `is_book: false` (§1.18a, "Lane A mounts no ad rail on `is_book: false`") until the operator rules on Q-B2.
- **The Books lens** (§1.2, "The Books lens"):
  - **The thread list.** It is `GET /investigations?project_id=P&document_ids[]=<P's primary, shelf and context documents>`.
  - **What it hides.** A thread that grounded in, opened or was filed on none of those documents is hidden in Books and stays visible in Research. Kept (`context`) documents count, not only the shelf.
  - **The unreachable group (rev 9; Appendix C.2 item 13, "Lane A shows them from `?project_id=` without `document_ids[]`").** A `reading` or `interest` project has no Research presence, so its off-lens member threads would have nowhere to show. Lane A lists them from `?project_id=P` alone, in a collapsed group "Not about these books (n)". They are never dropped. The operator can also turn the book into a project (T6, §2.18). §2.4 uses this group.
  - **Transient tabs.** A transient tab's document is outside the lens until Keep (§1.6, "Not membership").
  - **The left pane** admits reader and document tabs, with shelf members first.
  - **Tree writes.** Tree writes in Books answer `409 product_absent` once the project has left Books (§1.6, "Presence gates tab writes"). The tree still reads, and it takes the "left Books" copy above.
  - **"Which book(s)?".** A whole Research → Books transfer with no books picked lands on this seed step (§2.18), never an empty pane.
- **Notebook** (S17; ruling 13; §1.12, "The lens (rev 9)"):
  - **Where it lives.** It is a right tab in Books named "Notebook". The TipTap Notebooks become "My notes". It is reached through n/p and the prefix+c picker. It can open as a left tab and go fullscreen, and "Import outline into Write" is kept.
  - **Needs:** `GET /projects/{id}/companion-document?lens=reading`, optionally with `&document_id=&group=chapter`.
    - **Narrowing.** Lane A sends `document_id` for the focused left tab's document when that document is a primary, shelf or context member (§1.12, "must be a `primary`, `shelf` or `context` member of the project"). Otherwise it sends none, and the Notebook covers the whole project.
    - **Grouping.** `group=chapter` is sent only with `document_id` (§1.12, "requires `document_id`"). The response then adds `groups: [{chapter: {title, page_index, level} | null, entry_ids[]}]` in table-of-contents order.
    - **The null-chapter group** comes last, under "Not placed in a chapter" (§1.12, "fall into a final group with `chapter: null`"). A book with no table of contents renders ungrouped, with no heading.
    - **Entries** take §2.7's shape, with `anchors[]`, `chapter?` and `merge_ids[]`. An anchor opens a left tab at that passage.
    - **Refusals:**
      - `422 document_not_in_project`: the focused document stopped being a member, for example after a removal on another device. Lane A drops the narrowing and shows the whole project, with the quiet note "That document is no longer in this project. Showing the whole shelf."
      - `422 group_requires_document` and `422 lens_invalid` are lane-A bugs: logged, never shown.
  - **What it covers (default 2;** §1.12, "The thread set for `lens=reading`"**).** The header says: "From this project's threads on these books, your questions to them, and linked research that read them." That covers three sources:
    - the project's member threads that grounded in, opened or were filed on a primary, shelf or context document;
    - the operator's book answers on those documents;
    - a linked research project's threads, but only those that grounded in or opened a shelf document.
  - **Contents:**
    - insights, open questions and claims, by entry kind, each one click from its process;
    - "Where the agents went": the threads the entries came from (`thread_ids[]`, `process_ref`) and the documents they drew on (`doc_ids[]`), each one click away. Lane A derives this list from the entries' fields. A process-entry kind is (needs Part 1, R9-40).
    - **Synthesis** (needs Part 1, R9-41). §1.12 has no synthesis entry or field. Until Part 1 names one, the Notebook shows no synthesis block and never composes one on the client.
  - **Audience.** The GET is owner-read, so the operator's own `personal_reading` quote renders `served`.
  - **States:** the §2.7 states, with Notebook copy:
    - `loading`
    - `empty`: "Nothing here yet. Ask the book a question, or research a passage." Shown only after a real answer.
    - `error`: "Couldn't load the Notebook." with Retry.
    - `ready`
    - `stale`: §2.7's copy per cause, with Refresh (rev 9; rev 8.11 C1 and C3). A null `content_hash` reads "These findings haven't been written yet."; until Part 1 names the cause (needs Part 1, R9-48), any other `stale` reads §2.7's combined line, never "Newer activity" alone, because that line is false for drift.
    - `refreshing`: as in §2.7, including a `503 receipt_not_written`, which keeps the old entries (rev 9; rev 8.11 C6).
    - `partial`: "n of m threads summarised".
    - `unavailable_until_rights`: "The Notebook opens once source rights can be checked".
  - **Refresh.** Which lens the refresh route rebuilds is (needs Part 1, R9-42). Until Part 1 names it, Refresh refetches the lens GET, and the stale line stays until the server's `state` changes.
  - **Spend.** The tab spends nothing (§1.12, "The GET and every rebuild make zero model dispatches").
  - **"Write it up as prose"** (ruling 13; §1.11a, "The notebook write-up source (rev 9)"). It is an opt-in action under consent and the cap, and it follows §2.11's reformat flow (estimate, binding, plural model identity).
    - **The estimate comes first.** It is `POST /reformats/estimate {source: {companion_document: {project_id, lens: "reading"}}, …}`.
    - **The consent line.** It shows the model and "Starts if $X of today's cap is free; it pauses if the cap runs out". It also says what the write-up won't see, counted from the entries on screen: "n cite-only and m held-back notes are not given to the model."
    - **Accept** sends `POST /reformats {source: {companion_document: {project_id, lens: "reading"}}, mothership: "reading", idempotency_key}`.
    - **An unknown price** renders "—" with "Price unknown for this model", and consent follows §2.8.
    - **`402 refused_capped`** reads "Today's cap can't cover this", with "Raise today's cap".
    - **The result** opens as a left derivation tab (§2.11).
    - **Stale write-up.** When the write-up's view carries `stale: true` (§1.11a, "`stale: true` whenever the current notebook's `content_hash` differs"), it reads "Written from an earlier version of the Notebook" and offers "Write it up again" with a fresh estimate. It never regenerates silently. §2.11's header uses this copy.
    - **Until LB-30 lands** the action is disabled and reads "Prose write-ups aren't available yet" (§1.11a, "stays disabled until LB-30 lands").
- **Detours** (D5, D6):
  - **The tab.** A detour opened from a footnote, link or citation in a book is a child of the book's tab. Its origin kind is `footnote`, `reference` or `citation` (§2.2).
  - **The depth chip** reads "Depth n", counted from the book's tab.
  - **Return.** prefix+u returns to `branch_origin.anchor`, the exact passage. It is never a navigation away.
  - **Keep.** A detour into a document that is not a member offers "Keep in this project", which is `POST /projects/{id}/members {member_kind: document, member_id, member_role: context}`:
    - `201 added`: "Kept".
    - `200 already_member`: it names the stored role (§1.5, "`200 {status: already_member, member}`"): "Already in this project: the main book", "…: on the shelf" or "…: kept".
    - Every other answer takes §2.2's Keep copy. So `404 source_not_found` reads "This document no longer exists.", the same for another owner's private document (rev 9).
  - **Non-books before LB-35.** A detour into a non-book opens as a document tab reading "Opens outside the reader for now".
- **TalkToBook** (S13, S18; §1.8, "A book session (rev 9)"):
  - **The session.** It is a right-pane dialogue tab on a book session: `POST /investigations {kind: "dialogue", scope: {document_id}, investigation_id}`.
    - The `investigation_id` is minted by the client. The create sends no `question` and no participants. The server sets the parent to `read-<document_id>`, and a replay on the same id returns the same body.
    - `404 document_not_found` reads "This book no longer exists.", §2.13's create copy. `422 scope_invalid` is a lane-A bug.
  - **Asking.** `POST /investigations/{id}/ask {question, input?, mothership: "reading", idempotency_key}`. The turn states and failure copy are §2.13's:
    - `answering` is a pending state, because rev 9 has no token stream.
    - `409 turn_in_progress` (§1.8, "`409 turn_in_progress {turn_id}`") waits for the WS `thread.turn`.
    - A reload reads `GET /investigations/{id}/turns`.
    - Retry reuses the key, but only after `unavailable` or `interrupted`.
    - `owner_model_outcome_unknown` takes §2.13's copy ("We couldn't tell whether your model answered. Asking again may be charged by your provider."). Asking again is a new press with a new key (§1.8, "A new press takes a new key").
  - **Answers.** A book session attributes no sentences (§1.8, "`book_qa` does not attribute sentences"). So the answer shows its refs as a list below it, with no per-sentence chips. It renders by §2.10. A takedown withholds an old answer (§1.8, "A takedown therefore withholds an old answer").
  - **Refs.** Each `source_ref` with a `document_id` opens a left tab at its anchor, or at the document's start when the anchor is null. Its gate shows as a §2.10 chip.
  - **Refs outside the project** open as transient tabs (§1.6, "`transient` (rev 9; S15; Part 2 draft §A2)"). Such a tab is a new left node in the reading mode, with `transient: true`, `branch_origin.kind: agent` and `opened_by` naming the session. It offers two actions:
    - **Keep.** First the members POST `{member_kind: document, member_id, member_role: context}`, then a tab PUT that clears `transient`, in that order (§1.6, "is two operator writes, in this order"). A `200 already_member` still clears it. `transient` only goes from true to false.
    - **Read later.** `POST /flags {intent: read, target: {document: {document_id}}, idempotency_key}`, confirmed with "Added to To read" (§2.9).

    Closing an unkept transient tab retires it, and it is restorable (§2.2).
  - **A work with no document row** comes back as an unresolved ref (§1.8, "returns it as an unresolved ref and nothing is filed"). It reads "This work isn't in your library, so it can't be opened or filed."
  - **The context receipt.** Items tagged `via: link` show as "From linked research: <project>" (§1.8, "The ruling-11 link layer in a book session"). Nothing is written to that project.
  - **Unavailable.** On a document whose `registered` is false (§1.18a, "Markers, on `BookDetail` only"), TalkToBook is hidden, with the line "Asking isn't available for this document yet."
- **Ask across books (rev 9; §1.8, "Book ask scope and openable refs"; O-15's fallback).** TalkToBook asks one book in a saved session. Asking across the shelf or the whole library uses the book ask route instead, because that reach is not on sessions (§1.8, "The shelf and library reach of O-15's fallback is on `/books/{id}/ask`").
  - **Where.** The TalkToBook composer carries a scope control: "This book" (the session, above), "This shelf" and "My library". Choosing either of the last two switches the composer to the book ask route. A line under the control says "Not saved as a conversation. Answers are kept on this book's reading record."
  - **Needs:** `POST /books/{id}/ask {question, history[], research_tier, model_choice?, scope: "shelf" | "library", project_id?}`. `{id}` is the book in focus. `scope: "shelf"` always sends the active `project_id`. The answer keeps its existing fields, including page `citations[]`, and adds `source_refs[{document_id, anchor | null, document_type, gate, reason}]`.
    - `history[]` holds this exchange's earlier questions and answers, kept in the view. There is no turns route for this path, so a reload starts a new exchange (lane-A choice, for the co-sign).
  - **When "This shelf" is offered.** Only when the project has `reading` in `products[]` and the book in focus is its primary or on its shelf, read from `GET /projects/{id}/shelf`. Otherwise it is disabled with "Put this book on the shelf to ask across it." "My library" is always offered.
  - **States:**
    - `composing`
    - `answering`: "Working on an answer". The answer arrives whole.
    - `answered`
    - `failed`: a network failure or a 5xx. "Couldn't get an answer. Try again.", with Retry, which resends the same question.
  - **The answer** shows its page citations, and below it `source_refs[]` as a list. Each ref is a document row by §2.10 ("Document rows"), with its gate chip and a type marker from `document_type`. It opens a left tab at `anchor`, or at the document's start when `anchor` is null. A ref outside the project opens as a transient tab with Keep and Read later, as for TalkToBook refs. An unresolved work reads as in TalkToBook.
  - **Cost.** A book ask is a conversational turn (§1.13, "Conversational turn"). It never stops at the cap and never offers "Raise today's cap". A cost it reports renders by the nullable rule.
  - **Refusals** (narrowed on `reason`; no code is shown):
    - `422 document_not_on_shelf`: "This book isn't on the shelf any more. Ask it alone, or pick a book on the shelf." The scope falls back to "This book".
    - `409 product_absent`: "This project has left Books, so its shelf can't be asked."
    - `404 project_not_found`: "This project no longer exists."
    - `403 book_taken_down`: "This book was taken down, so it can't be asked."
    - `404 book_not_found`: "Asking isn't available for this document yet." This is the same line as an unregistered document above.
    - `422 project_required`: a lane-A bug, logged and never shown, because "This shelf" always sends `project_id`.
  - **Reacts to:** `project.shelf_changed` and `project.product_left` re-judge whether "This shelf" is offered.
- **Reacts to** (rev 9; §1.7, "a client treats every push as a nudge"):
  - `project.shelf_changed`: refetch the shelf. With a pending local move, rebase as for a 409.
  - `project.members_changed`: refetch the membership (the Keep states and the lens document set) and the lens thread list.
  - `project.product_left` naming `reading`: the shelf and the tree turn read-only, with the "left Books" copy.
  - `companion_document.refreshed` with `lens: reading`: refetch the Notebook.
  - `thread.turn` on the book session: refetch its turns.
  - `reformat.generated` and `reformat.failed` for a write-up: as §2.11.

### 2.20 Voice input and read-aloud (rev 9; R34, R35-voice-out; ruling 17; default 8)

New in rev 9. The operator can speak in any composer. What is sent is always text the operator saw.

**One hook (§1.19 ("Transcribe (rev 9)")).**
- `useVoiceInput` is the only client of the transcribe route, with one `VoiceInputButton`. It is mounted in every composer: AISidecar, TalkToBook, ThoughtPartnerPanel, the cockpit agent composer (§2.13), the island Ask composer, the reformat and monologue composers, MidnightOil and the Speak owner composer. The duplicate transcribe clients are removed.
- **Key:** `voice.toggle` is prefix+v or ctrl+alt+v (§2.17).
- **Needs:** `POST /voice/transcribe?thread_id=&project_id=&language=&mothership=`, with the raw audio as the body. It answers `{transcript, language, duration_seconds | null, asr: {provider, model}, cost_cents | null}`.
  - The query parameters are attribution only, never authorization.
  - The route saves nothing and returns no capture id (ruling 17).
  - `duration_seconds` may be null, and lane A never turns it into 0. (rev 9, Appendix B §B9)

**States:**
- `idle`.
- `recording`: the elapsed time, and a level meter that stays still under reduced motion.
- `transcribing`: "Transcribing…".
- `draft_ready`: the text is in the field, editable, with a "From voice" mark.
- `sending_soon` (rev 9, conversational surfaces only): the 1.5 s grace window, below.
- `mic_denied`: "Microphone access is off. Turn it on in your browser to use voice."
- `unavailable`: `503 transcription_unavailable`, or no connection. "Transcription is unavailable right now."
- `too_large`: `413 too_large`. "That recording is too long." (rev 9: the state takes Part 1's name; lane A's draft called it `too_long`.)
- `silent`: `400 empty_audio`. "Didn't catch anything."
- A `404 thread_not_found` or `404 project_not_found` on transcribe is a lane-A bug. Lane A logs it and sends the same recording once more without `thread_id` and `project_id`, because they are attribution only (lane-A choice, for the co-sign). The recording stays in memory until that one retry answers (Retention). If the retry fails too, the state is `unavailable`.

**When it sends (default 8, as refined 2026-09-27).**
- **Composers that start paid work** fill an editable draft and never send by themselves: a research launch, Harden and Chase, a reformat, a monologue question (§2.14) and a merge question. Every surface not listed below behaves this way, including the Speak owner composer.
- **Conversational surfaces** show the transcript and send it after a visible 1.5 s grace window: an ask in any dialogue (§2.13, including "Ask this thread", the island Ask and TalkToBook) and a Converse turn (§2.14).
  - During the window, Enter sends at once, and Esc keeps the text in the field for editing. Typing into the field also stops the window.
  - Under reduced motion, the window is shown as text ("Sending in 1.5 s") rather than an animation.
  - A transcript is therefore sent only after the operator has seen it and not stopped it. That is ruling 17's "confirmed transcript".

**What is sent (rev 9; §1.19 ("The server mints the capture at submit")).**
- Launches, asks and reformats carry `input: {modality: "voice", edited, asr_model?, language?, duration_s?}`:
  - `edited` is true when the operator changed the text before it was sent;
  - `asr_model` is the transcribe answer's `asr.model`;
  - `language` is the transcribe answer's `language`;
  - `duration_s` is `duration_seconds`, and a null stays null.
- The server writes the capture when the confirmed text is submitted. Lane A reads `voice_capture_event_id` from that submit's answer, including a 503 answer. It never invents one, and it never posts `voice.captured` itself. (rev 9, Appendix B §B9)
- Typed text sends no `input`, or `{modality: "text"}`.

**Retention (ruling 17; §1.19 ("Retention (ruling 17)")).**
- No audio is kept anywhere. Esc while recording discards the recording.
- The recording is held in memory only until transcribe answers, then dropped. After a lane-A 404 on transcribe, it is held until the one attribution-free retry answers, then dropped (rev 9).

**Spend.** Operator transcription is recorded and never refused by the cap (§1.13 ("Operator ASR and TTS"); O-16's fallback). The composer shows no per-note cost. The spend counts in today's figure.

**Read-aloud (rev 9; §1.19 ("Speech output: the `source` gate")).**
- `useSpeech` is retired on the ReadAloud paths. Every read-aloud of text that carries rights goes through `POST /speech/tts {source, voice?, mothership?}`:
  - an answer: `source: {turn_event_id}` (§2.13, §2.14);
  - a reader page: `source: {document_id, page_index}`, one page per call.
- The bare `{text}` form is used only for text the operator typed.
- A cite-only passage is read as a short fixed notice (`withheld_marker/v1`), never its words. The reader says "Parts that can't be quoted are read as a short notice".
- **Refusals:**
  - `422 not_servable`: "This is held back, so it can't be read aloud."
  - `422 source_invalid`: "This page can't be read aloud."
  - `422 too_long`: "This is too long to read aloud in one go."
  - `503 tts_unavailable`: "Reading aloud is unavailable right now."
- The audio is streamed and not kept.

### Rev-9 requests of Part 1 (R9-1 to R9-48; rev 9)

Each "(needs Part 1)" marker above cites one of these. None blocks rev 9: each names the fallback lane A builds against until Part 1 answers it.

**Tabs and anchors**
- **R9-1** (§2.2, §2.3): `text_projection` and `served_body_sha256` on `BranchAnchor` wherever it is carried (tab nodes, branch origin, start payload) and on remap candidates; or a statement that tab anchors always re-resolve. Fallback: every HTML-body tab anchor re-resolves by quote and context; an island anchor is checked by its slice digest, and a mismatch goes to remap.
- **R9-2** (§2.2): a single-segment read, `?segment_id=`, on `GET /investigations/{id}/outputs`. Fallback: page on `next_after`.
- **R9-3** (§2.2): the `tab_id` grammar, admitting ':', and a statement that a `tab_id` with an unrestored retirement returns only through a restore. Fallback: lane A mints `agent:thread:<thread_id>` and treats a refusal as a lane-A bug.
- **R9-4** (§2.2, §2.13): a static capability signal for dialogue threads, like A06's attestations listing, or the exact refusal an older API gives. Fallback: feature detection; the probe's refusal is never shown.

**Launches, asks and estimates**
- **R9-5** (§2.3): an estimate body that accepts `parent_investigation_id`, `origin` and `continue_from_parent`, and prices the parent's pack. Fallback: the basis line reads "Before the parent thread's context".
- **R9-6** (§2.3, §2.4): a cost bound before the first question of a branched Ask, for example an estimate that takes the dialogue create body plus `question` and `context_items`. Fallback: "—" with "Priced once the conversation starts".
- **R9-7** (§2.3, §2.4, §2.13): a capability signal saying whether owner models work on a non-book dialogue (#3278 landed). Fallback: owner models are shown disabled on every dialogue except a book session, with "Your own models can't be used here yet".
- **R9-8** (§2.4): a cursor (`after` and `next_after`) on `?parent_thread_id=`. Fallback: 500 rows, "Showing the first 500 branches".
- **R9-44** (§2.3): whether `continue_from_parent` is required, allowed or refused on a `kind: dialogue` output branch (the island Ask). §1.3 says only that on an output branch it "is true, and false is refused". Fallback: the Ask create omits it, following §1.8's dialogue create body; a `launch_invalid · continue_required` is logged as a lane-A bug and reads "This couldn't start. Nothing was charged."

**Merge and Write**
- **R9-9** (§2.5): `failure {reason, detail?} | null` on the draft shape. Fallback: the reason comes only from the socket event or the inbox item's `detail`.
- **R9-10** (§2.5): cancel's answer shape while drafting, for example `{merge_id, draft_id, state, failure?, cost_cents | null}`. Fallback: lane A refetches the read after Cancel.
- **R9-11** (§2.5, §2.8, §2.11, §2.13): closed `detail` sets for `reason: failed` on `thread.merge_draft_failed`, `thread.turn_failed`, `reformat.failed` and `question.diligence_refused`, or a statement that `detail` there is log-only. Fallback: a fixed sentence per surface; any other `detail` is logged and never shown.
- **R9-12** (§2.6): whether from-investigation writes the project membership, for example an optional `project_id`. Fallback: an idempotent members POST follows it.
- **R9-13** (§2.6): how a merged thread builds merge-draft hunks into Write (the accepted draft's served sentences; each `origin` mapped to a member class). Fallback: the action is disabled with its reason.
- **R9-14** (§2.6, §2.15): `claims[{claim_id, speak_project_id}]`, or `speak_project_ids[]`, on `422 speak_publish_required`. Fallback: blocks are marked, and a Speak request opens only where it can be named.

**Companion, flags, inbox and spend**
- **R9-15** (§2.7): a project-level evidence-base MCP resource, or confirmation that it is per thread only. Fallback: the per-thread copyable URI, hidden until the MCP hardening merges.
- **R9-16** (§2.8, §2.5, §2.14): where the `reason: "cost_unknown"` that §1.13 ("An unknown cost") gives `spent_today_cents` sits on `GET /settings/budget`, for example `null_reasons.spent_today_cents` or a sibling `spent_today_reason`. Fallback: a null with no readable reason reads as an unreachable ledger.
- **R9-17** (§2.8): `consent: {state, reason?, consent_id?, at} | null` on diligence flag items. Fallback: `refused` and `consent_stale` show only while the events are in hand.
- **R9-18** (§2.8): a capability signal that tells an absent wave route (W2 consent and launch, W3 `/inbox`) from not-found. Fallback: a bare 404 with no `reason` reads as absent.
- **R9-19** (§2.8): an inbox kind, or `detail {state, reason?}`, for a monologue that fails or stops. Fallback: no inbox row; the player shows the state.
- **R9-20** (§2.8, §2.16): `source` echoed on `GET /flags` items, and a `?source_thread_id=` filter. Fallback: a roster row omits continuations and links to the project's flags.
- **R9-48** (§2.7, §2.19): the cause of a companion document's `stale` state, for example `stale_cause: activity | drift | never_refreshed`, so drift gets its own line (rev 8.11 C3). Fallback: a null `content_hash` reads as never refreshed; any other `stale` reads "This may be out of date: there's newer activity, or its sources changed, since it was written."

**Reformat and gated text**
- **R9-21** (§2.11, §2.19): the route or field that carries a write-up's `stale: true`, for example on the spans response. Fallback: no stale line until it is named.
- **R9-22** (§2.11): `presentation_mode_source: declared | default` on turn and merge-draft provenance (T7), or a refusal of undeclared dispatches. Fallback: the recorded mode renders as stored.
- **R9-23** (§2.11): the closed `detail` set for `422 informs_invalid`, which rev 8.11 D names (`too_many_entries`, `duplicate_document`, `document_not_readable`, `anchor_other_document`, `anchor_invalid`, `entry_invalid`) and the rev-9 Part 1 draft does not yet carry. Fallback: lane A builds against 8.11's six codes; any other `detail` reads "This row can't be saved" on the row at `index` (rev 9 update).
- **R9-45** (§2.11): the informs route's exemption from §1.15 rule 4, on lane A's condition from rev 8.11 D5: a missing document and another owner's private document answer the byte-identical `422 informs_invalid {index, detail: document_not_readable}`. Fallback: lane A reads either that 422 or a `404 {reason: source_not_found, ref}` as the same row line, "This document can't be found or read", marking the rows whose `document_id` is `ref`.
- **R9-47** (§2.10, §2.11): the refusal a reformat (a monologue and the Notebook write-up included) answers when a private derivative has mixed or unproven authority, or its output schema cannot represent private lineage (§1.15, "A derivation with mixed or unproven authority"; "cannot represent private lineage"). Fallback: an unrecognised refusal of Generate is logged and reads "This couldn't start. Nothing was charged."
- **R9-43** (§2.10): the spoken words of `withheld_marker/v1`, pinned in §1.19, so the on-screen caption matches. Fallback: the caption shows the passage's cite-only state.

**Registry and create**
- **R9-24** (§2.12, §2.19): `reader_openable` and `classified` (or `shelf_admissible` plus a reason) on the document listing the pickers read. Fallback: the submit-time refusal copy.
- **R9-25** (§2.12): a link from the stored `seed.question` to its launch, for example `seed_launched_thread_id | null`, set by a launch that carries `project_id` and `from_seed: true`. Fallback: "Start research" is offered only while `GET /investigations?project_id=` holds no research row: a `research`, `cascade_session` or `no_record` row counts, and a `dialogue` row, or a thread whose member row has `member_role: agent` or `managed`, never counts (rev 9 update).
- **R9-38** (§2.17, §2.1): an offers-only read across projects and modes, for example `limit=0` on transfer-candidates, or `offers_by_product` on the §1.5 row. Fallback: a lazy `limit=1` read on focus, with "Checking…".

**Sessions and agents**
- **R9-26** (§2.13): repeat-table rows for `failed` and `owner_model_unavailable`. Fallback: a new press with a new key.
- **R9-27** (§2.13): whether a request refused before admission (`confirmation_required · unpriced`) binds its key. Fallback: the confirmed send uses a new key.
- **R9-28** (§2.13): what an agent's `merged_from[]` holds after `thread.merged_in`, and whether attached threads count toward "Knows"; or `agent.knows {thread_count, merge_count}`. Fallback: counts of `merged_from[]` and `merge_ids[]`.
- **R9-29** (§2.13): an optional §1.4 `anchor` on `doc` attach items, or a statement that whole-document attach is intended. Fallback: the whole document.

**Converse, Speak and Autonomous**
- **R9-30** (§2.14): per-span timing (`span_offsets_ms[]`) within a measured segment, or acceptance of lane A's estimate. Fallback: an estimate from narrated length.
- **R9-31** (§2.14): the monologue re-plan route and its identity, before LB-30 builds. Fallback: re-plan is not offered.
- **R9-32** (§2.15): the Confirm route for unconfirmed transcripts, with its refusals and event. Fallback: Confirm is hidden.
- **R9-33** (§2.15): the registry projects that link a Speak request (Writing presence), on `GET /speak/projects/{id}/detail`. Fallback: the generic "Sends to Writing" label.
- **R9-34** (§2.15): the Public list route, its row fields and `sort=ranked|newest`. Fallback: `GET /speak/opportunities`.
- **R9-35** (§2.16): `managed_project_ids[]` on roster items, and optionally on `ThreadSummary.agent`, as an efficiency request. Fallback: for each id in `agent.project_ids[]`, lane A reads `GET /projects/{id}` `members[]` and keeps the projects whose row for the agent has `member_role: managed` (rev 9 update).
- **R9-36** (§2.16): whether a continuation launch is refused while spawning is off, for example `409 spawning_disabled`. Fallback: the UI disables Continue.
- **R9-37** (§2.16; only if O-11 is granted): the envelope POST body, bounds and named refusals. Fallback: none; the envelope is not offered.

**Books**
- **R9-39** (§2.19, §2.9): `progress_reason: no_position | page_count_unknown` on shelf and continue items. Fallback: the combined reason.
- **R9-40** (§2.19): a `kind: process` entry, or confirmation that lane A derives "Where the agents went" from `thread_ids[]`, `process_ref` and `doc_ids[]`. Fallback: the derivation.
- **R9-41** (§2.19): a synthesis entry kind, or `synthesis: GatedText | null`, on `lens=reading`. Fallback: no synthesis block.
- **R9-42** (§2.19): the refresh route's lens parameter, or a statement that one refresh rebuilds every lens. Fallback: Refresh refetches the GET.

**Rev 8.11 in rev 9**
- **R9-46** (header, §2.1, §2.4, §2.7, §2.11): the rev-9 Part 1 draft restates, or cites as standing, rev 8.11's lane-A-visible rules, none of which it carries yet: `state: null` (A1), `seen_terminal_event_id` and the completion event (A6), the null `thread_counts` and `spend_today` rules (A7), `failure_reason` and `failed_before_start` with the closed-set scope (A10), the companion document's `state` enum, drift, gating, origin and wire details (C1–C6), and the informs event, read route and 404 (D1–D5). Fallback: lane A builds against rev 8.11 as signed, which each item says rev 9 need not reverse. §1.5's `null_reasons` ("One entry per derived field that is null") has no code for 8.11 A7's nulls, so rev 9 either adds one (for example `spend_today?: not_attributed`, and says that a null member state gives `thread_counts: logs_unreadable`) or states that A7's reasonless null is superseded. Until then lane A reads a null with no entry as 8.11's ("Still counting"; "Spend by project isn't recorded yet"). Lane B has said rev 9 §1.5 will add `thread_counts: member_state_unknown` (a member state is null, or a member or `thread_seen` read failed) and `spend_today: not_attributed`. Lane A renders them with the same copy ("Still counting"; "Spend by project isn't recorded yet"). Three points follow 8.11's draft v4 and appear in neither v3 nor the rev-9 Part 1 draft, so rev 9 must carry or strike each: A1 v4, a record the reader could not parse makes `state` null (§2.4); A6 v4, a cascade session done by its leaves' aggregate completes at its latest leaf terminal event (§2.1); A6 v4, POSTing that session's own latest event marks it seen (§2.4). Rev 9 also carries A10's kind scope from 8.11 v5: `failed_before_start` is derived only for `research` and is null for every other kind. Fallback: "Didn't start" only on `kind: research`; any other row reads "Didn't finish", and a reformat row takes §2.11's copy (§2.4).
