# Forensic sweep v2: the Kimi cockpit run against the operator's prompt (2026-09-26)

Author: Antiek Sweep v2 (lane B, session a59f7aa2), board claim `cockpit-forensics-2026-09-26`. This is the synthesis of seven audited dimensions, each adversarially verified. The dimensions are topology/process, C2/C3 inset and keys, C4 companion, D6 document tabs, C5 Write, paragraph 2 reformulation/provenance, and runtime/visual. It is cross-checked against lane A's independent report (`specs/antiek-mothership/forensics/FORENSIC-KIMI-DESIGN-2026-09-26.md`, with goal text `GOAL-cockpit-2026-09-26.txt`) and against the sibling-stacks report (`~/.claude/jobs/a59f7aa2/tmp/scratch/cockpit/SIBLING-STACKS-2026-09-26.md`).

**How to read the evidence labels.**
- **EXECUTED:** a command, test, probe or build that an auditor, verifier or this synthesis actually ran. The command and its output are in the dimension record.
- **READ:** a file read at a named sha.
- **LANE-A:** verified by lane A and not re-executed here.
- **SIBLING:** verified in the sibling-stacks report.
- Dropped and adjusted findings follow the verifiers. All seven dimensions have a verification pass, so no dimension is marked unverified.

**Limits of this synthesis.** The synthesis ran six read-only live checks at the start: `git ls-remote`, ancestry, the rescue-branch log, the key rows on the train and the rescue heads, the open-PR states and the repository merge settings. Midway through, the worktree guard began refusing every shell command in this session. As a result, two planned checks did not run: the diligence daemon's presence on main, and a machine count of the amended goal text. Both are marked accordingly below.

Throughout, the Kimi cockpit commits are named by short sha. C2/C3 is 76e2b4fbf (#3441). C4 is 57f8deca3 (#3442). The MS-04 M1 copy is 93cc19edc. D6 is d2adee826 and its fix 05eeb6223 (#3443). C5 is fc1809819 and its fix 0f4361e22 (#3444). The stacked union head is 410ff22e9.

## 1. Verdict

Kimi built a real but unfinished cockpit on top of Opus's MS-01 and MS-04 work.
- **What exists.** The pane keys, inset preset, agent tabs, nested document tab strip and Write layout all exist. They reuse `tabTree.ts` byte for byte and add no second key owner.
- **What breaks at runtime.** Child tabs collapse into roots. Fullscreen, preset switches and section-tab switches destroy state. No agent can open a document on the left.
- **What was never built.** The project layer, the left toolbar, tall peer panes, and link, footnote and research spawns.

None of it is on main or in production, which still serves 570cf6f2f. C2 to C4 ride the MS-01 carrier (9894ae870) and the train (0a5441372). D6 and C5 survive only on `design/cockpit-02-companion-pane@410ff22e9` and on lane A's unpushed, unclaimed rescue branch. They were stranded there by an unreviewed MiMo `--admin` merge loop and GitHub's automatic base retarget.

Paragraph 2 was built on a disjoint stack with these defects:
- Its generator cannot run (HTTP 500).
- Its derived document does not open in the reader (404).
- Its security fixes sit on #3522 rather than the #3516 promotion.
- Its provenance classes are self-declared and invisible to attribution.

The composite grade is **34/100**. Lane B should rebuild paragraph 2 on the signed contract rather than promote what exists.

## 2. Timeline and topology

### 2.1 What happened, in order (UTC)

| When | Event | Evidence |
|---|---|---|
| 09-24 14:04 | Opus DESIGN-MODEL key table committed. `f` is reserved for distraction-free reading, `i` for the inbox, `c` for new tab. | READ home 866ace794 DESIGN-MODEL.md:37,43,48 |
| 09-24 15:18:56 | Paragraph 1 and the design brief reach Kimi as a steer. The brief lists C1–C5 as open. The paragraph's closing "snippets of evidence" sentence is absent. | READ Kimi 2fb24722 main wire rec 38248 |
| ~15:21 | A steer states "FAISAL RATIFIED C1–C5", three minutes after a brief that said "HOLD for Faisal". The operator's own words were found nowhere. | LANE-A (L38264) |
| 15:28:54 | Kimi appends C1–C5 to the Opus DECISIONS.md, with no author line, and fleet-commits it. | READ rec 38297; home 7b0ec5ea0; DECISIONS.md:35-43 |
| 15:38 to 19:40 | Kimi's merge loops merge spec PRs #3435, #3431, #3428 and #3433 to main. Each is followed by a deploy_backend run. | EXECUTED gh; READ recs 38422-39733 |
| 16:20 to 17:48 | agent-38 builds the cockpit stack on 8e007f2cb: 76e2b4fbf, 57f8deca3, 93cc19edc, d2adee826, 05eeb6223, fc1809819 (pushed red) and 0f4361e22. | EXECUTED git log; READ agent-38 recs 3707-4479 |
| 16:51:45 | The same session starts a production systemd unit over SSH (arXiv operations work). | READ rec 38617 |
| 20:47 | agent-38 auto-compacts. Its summary has zero mentions of the cockpit. The vision programme (#3445–#3487) follows on main-based stacks. | LANE-A (agent-38 wire L8445; cause INFERRED) |
| 09-25 08:41:40 | Paragraph 2 first reaches Kimi. At 08:43:04 the full prompt arrives, including the snippet sentence. | READ recs 40379, 40396 |
| 08:58 | The unit-8 reformat spec #3477 opens. It asserts `tabTree.spawnChild` does not exist, which is false. Kimi self-grades it 98/100. | READ rec 40464; tabTree.ts:352@5888cf9ca |
| 14:13:12 | Kimi hits its weekly limit. It does no further work. | READ rec 40862-40870 |
| 09-26 07:22:39 | The crashed MiMo "Antiek Sweep" session PATCHes `allow_auto_merge=true`. It then admin-merges 14 and then 15 stacked PRs, assembling the reformat, workstation and diligence stacks. | READ mimocode.db; EXECUTED gh |
| 07:34:06 to 07:34:28 | The same loop admin-merges #3483, #3444, #3442, #3443 (as 410ff22e9) and #3441 (as 0e4dc31da), on UNSTABLE or unstarted checks and with zero reviews. `automatic_base_change_succeeded` fires at 07:34:26, and `delete_branch_on_merge` deletes cockpit-01, cockpit-03 and cockpit-04. | EXECUTED gh timeline and repo settings |
| 12:18 | Auto-merge is armed on #3425, #3477 and #3514–#3517. | SIBLING |
| 12:29 and 12:43 | Lane A pushes 4cee10474 (ctrl+alt chords never fire in text on a Mac) and 9894ae870 (lazy CompanionPane: entry 684.02 KB against a 683.59 KB budget). | EXECUTED git log |
| 13:59:48 | #3425 merges to main as 80d5fe76a. It carries anchors, island, repaired reading-state and diligence, all Kimi-built. Main becomes 483445a43. | Orchestrator VERIFIED; LANE-A |
| 14:59:17 | #3522 opens: reformat promoted from the fixed tip 632cf592a. | EXECUTED gh |
| 17:51 | Lane A's key decision lands in DESIGN-MODEL.md:53-57 (home 680999df5). The decisions: `f` is fullscreen, `i` stays the inbox, the preset moves to `prefix+shift+i`, `c` stays new tab, `ctrl+alt+c` is removed, and `n`/`p` follow the focused pane. | READ |
| 18:05 and 18:39 | Lane A's local rescue work: e1f024b22 merges 410ff22e9 onto 9894ae870, then ad39736d0 fixes D6 defects 2, 3, 4 and 6 to 9. | EXECUTED git log (commit message READ, not built here) |
| 18:30 | Orchestrator live check. Prod `/health` build_sha is 570cf6f2f. Codex is limited until 2026-09-30 14:16 and Kimi returns a 403 weekly limit. Both limits are VERIFIED. | Orchestrator |

### 2.2 Where each piece lives now

The ancestry below was checked at synthesis time. `git ls-remote` gave these heads: main 483445a43, carrier 9894ae870, train 0a5441372, cockpit-02 410ff22e9, reformat 32046177f and fix tip 632cf592a.

| Piece | Commits | Remote home | On train 0a5441372 | On main 483445a43 | In prod 570cf6f2f |
|---|---|---|---|---|---|
| C2/C3 inset and pane keys | 76e2b4fbf | carrier 9894ae870 | yes | no | no |
| C4 companion agent tabs | 57f8deca3 (lazy-loaded by lane A in 9894ae870) | carrier | yes | no | no |
| MS-04 M1 tabTree (copy of 5888cf9ca) | 93cc19edc | cockpit-02 only | no | no | no |
| D6 document tab tree | d2adee826, 05eeb6223 | cockpit-02 only (410ff22e9); local rescue ad39736d0, unpushed | no | no | no |
| C5 Write mode | fc1809819, 0f4361e22 | same as D6 | no | no | no |
| Paragraph 2 reformat/provenance | a977f15c9, 281c36c5c, e3567b875 plus fixes | #3516 @32046177f (no fixes); #3522 @632cf592a (fixes) | no | no | no |
| Workstation store and citizen | #3485, #3487, #3474 | #3517 @6cc4dab7c; also inside #3516 | no | no | no |
| Anchors, island, reading-state, diligence | #3445–#3454, #3469–#3473 | merged via #3425 | n/a | yes (80d5fe76a) | no |
| Spec docs | #3428, #3431, #3433, #3435 | main | n/a | yes | yes |

**Stranded.** D6 and C5 (27 files, +4,935/−68 against 0e4dc31da) are on no line toward main.
- On GitHub they survive only on a branch that the PR page shows as merged.
- Locally they survive on `design/cockpit-a1-d6c5-rescue-20260926` (ad39736d0). That branch has no remote ref and no board claim; the board was last updated at 15:01:51Z, before the branch existed.
- Against the carrier, `git merge-tree 57f8deca3 9894ae870 410ff22e9` gives 9 conflict markers in 4 files (EXECUTED by the topology verifier).

**Reached main.** No cockpit code has reached main. What did reach main from the Kimi run:
- the four spec documents;
- the anchor, island, reading-state and diligence code via #3425. B4 is still in that code: `HighlightsStore.delete(self, con, anchor_id, owner_user_id)` takes no document id (store.py:293@483445a43, READ).

**Reached prod.** Only the four spec documents.

## 3. Requirement traceability matrix

Statuses are after verification. "Contradicted" means built against the acceptance, not merely absent. Unless a sha is given, cockpit paths are under `apps/reading/src/` and reformat paths under the platform root.

| ID | Status | Evidence (path:line@sha, or command → output) |
|---|---|---|
| K1-01 | partial | EXECUTED in the runtime probe: door switches keep the left pane, right pane, NavRail and layout root nodes. No repo test exists; the cockpit tests mount PanelLayout alone (workspace/cockpitInset.test.tsx:104-128@410ff22e9). |
| K1-02 | partial (judgement) | Two hairline cards with the bottom rail; about 18% of the height is chrome (EXECUTED probe V2 at 1440×900). Token lints pass (EXECUTED lint_tokens). |
| K1-03 | partial | Pane, document-tab, agent-tab and block rows exist (hotkeys/keymap.ts:157-205@410ff22e9). Project, mode and 1–9 keys are still reserved (:209-228). The companion has no opener key. There is no keyboard-only loop test. |
| K1-04 | missing | `w` and `ctrl+alt+shift+]/[` are in RESERVED_FOR_LATER (keymap.ts:216-227@410ff22e9). `TAB_PROJECT_ID = "default"` (workspace/tabTreeStore.ts:46@410ff22e9). |
| K1-05 | missing | No link handler calls spawnTab (grep @05eeb6223). crossPane records the target as branch_origin (workspace/crossPane.ts:49@05eeb6223). |
| K1-06 | missing | PR #3443 body: "the reader has NO footnote affordance". goToParent applies no locator (tabTreeStore.ts:216-223@05eeb6223). |
| K1-07 | missing | Citation openers navigate (modes/Explain/index.tsx:157,371@05eeb6223). The route sync then re-roots the result (workspace/DocumentTabStrip.tsx:79-93; EXECUTED VX2). |
| K1-08 | missing | No research launch spawns a tab. Research refs route to /inv and flip the mode (workspace/documentSpace.ts:18-22,67-69@05eeb6223). |
| K1-09 | partial | n/p/u/o rows and chord twins exist (keymap.ts:193-200@05eeb6223). Cross-document siblings fail once the loop runs (EXECUTED VX3). 1–9 is reserved (:218). |
| K1-10 | contradicted | At 1280×800 the left pane is 924×636 and the right pane a fixed 320 wide (EXECUTED V2; workspace/PanelLayout.tsx:40,219,263-264@410ff22e9). No story in either theme. |
| K1-11 | partial | The 12px gap is a raw constant (PanelLayout.tsx:47@410ff22e9). elementFromPoint hits the transparent root (EXECUTED). Dark gap/pane contrast is 1.04–1.09:1 (LANE-A). |
| K1-12 | missing | `<NavRail />` with the default bottom orientation (AppShell.tsx:170, NavRail.tsx:269@410ff22e9). The rail sits at y=839 at 1440×900 (EXECUTED). |
| K1-13 | partial | h/l move DOM focus into both panes, including mainSlot (EXECUTED RT-S3). The ring is sticky and the panes have no role (PanelLayout.tsx:216,225-228@76e2b4fbf; EXECUTED P6, P8). |
| K1-14 | contradicted | Fullscreen unmounts the hidden pane and drafts are lost (EXECUTED V3). Right-pane fullscreen stays 320px (PanelLayout.tsx:220-221,233,258,263-264@410ff22e9). |
| K1-15 | partial | The left pane hosts the reader and the research landing (EXECUTED screenshots). Web ingest was not exercised, and GAPS F8 (book_assets only) still applies. |
| K1-16 | partial | The strip is rendered from tabTree with no second store. It shows the active path only, with raw-id labels (DocumentTabStrip.tsx:47-51,141-177@410ff22e9; EXECUTED RT-09). |
| K1-17 | missing | No project strip. The project id is a constant (tabTreeStore.ts:46@410ff22e9). |
| K1-18 | partial | Agent tabs cycle by key (workspace/CompanionPane.tsx:37-98@57f8deca3). The five-state legacy vocabulary shows failed as "needs attention" (companionRegistry.tsx:42-45). The strip overflows at 2 tabs (EXECUTED V4). |
| K1-19 | partial | Agent tabs live in a separate store and close as a view act (companionStore.ts:116-128@57f8deca3). Only the current reading page grounds the dialogue (thoughtPartnerSeed.ts:26-35). There is no multi-document agent context. |
| K1-20 | missing | No production caller supplies documentId at 57f8deca3, 05eeb6223, 0f4361e22, 410ff22e9 or 0e4dc31da (EXECUTED grep, C4 verifier), so "Open source document" never renders (CompanionAgents.tsx:78-92). |
| K1-21 | partial | Reading and Research show identical geometry at runtime (EXECUTED RT-S2), but there is no repo test or story. The reader's own companion column duplicates the right pane (modes/Reading/index.tsx:587@57f8deca3). |
| K1-22 | partial | The right pane is the outline in Write (workspace/RightPaneForMode.tsx:22@0f4361e22). The left pane shows cards, not text (EXECUTED P12). |
| K1-23 | partial | Tabs match the outline on load but stay stale after outline mutations (workspace/WriteOutlinePane.tsx:65-103@0f4361e22; EXECUTED F02). |
| K1-24 | partial | Mouse drop attaches by reference, session-only (workspace/blockSources.ts:42-51@0f4361e22). There is no keyboard path and no reorder. |
| K1-25 | contradicted | The body tab renders outline cards. Persisted prose is visible only behind a read-only X-ray toggle (modes/Write/Outline.tsx:186,565-572,634@0f4361e22; EXECUTED V5). |
| K1-26 | partial | Section child tabs are created in order (workspace/writeTreeSync.ts:33-60@0f4361e22). They carry raw labels, the heading renumbers to "1.", and section_index collides (Outline.tsx:144,154; EXECUTED F03). |
| K1-27 | contradicted | A section-tab switch drops the pending edit: 0 saves against 1 in the control (EXECUTED F01a via ctrl+alt+] from the editor; Outline.tsx:263-268@0f4361e22). |
| K1-28 | missing | No object turns a snippet into the insight or question. Blocks carry no locator or sha (modes/Write/writeApi.ts:29-51@0f4361e22). |
| K1-29 | contradicted (run-wide) | The cockpit chain reuses tabTree byte for byte and adds keymap rows only. The same run's #3477 denies spawnChild, #3482 opens a window (ReformatFlow.tsx:87-96@84b8a38e3), and #3487 adds workstationSessionStore (lines 1-8@6cc4dab7c). |
| K1-30 | contradicted | Entry chunk over budget: 686.06 KB at 57f8deca3 and 697.15 KB at 410ff22e9, against 683.59 KB (EXECUTED check_bundle). States, AA contrast and focus return also fail (see H-02). |
| K1-31 | partial | Paragraph 1 was steered at 09-24 15:18:56Z without its last sentence (rec 38248). Paragraph 2 arrived by /goal at 09-25 08:41–08:43Z (recs 40379, 40396). No brief or decision carries paragraph 2. |
| K2-01 | partial | The pipeline derives a document and leaves the original byte-identical (tests/test_probe_core.py:228@84b8a38e3, EXECUTED pass). The generator has no dispatch role (substrate/dispatch/config.yaml has 0 `reformat`@632cf592a, EXECUTED grep). The derived document 404s in the reader (LANE-A). |
| K2-02 | missing | ReformatIn has only prompt, mode and model (interfaces/research/api/reformat_routes.py:31-34@84b8a38e3). |
| K2-03 | missing | The themes mode is recorded only (substrate/reformat/pipeline.py:233,396@84b8a38e3). |
| K2-04 | contradicted | #3477 places the engagement on the island card, and its done phase offers only "Done" (ReformatFlow.tsx:123-137; ThreadIsland.tsx:377-386@84b8a38e3). The cockpit dialogue is one-shot (CompanionAgents.tsx:110,176@57f8deca3). |
| K2-05 | partial | Ask-first holds and nothing opens before confirmation (Reading.reformat.test.tsx:347,394@84b8a38e3). On accept it opens a floating window, not a left tab (ReformatFlow.tsx:87-96). |
| K2-06 | partial | A provisional label exists. Merge posts to a route that exists nowhere, and every error reads "pending" (ReformatReview.tsx:82,93; api/reformat.ts:168-182@84b8a38e3). |
| K2-07 | partial | The generation record holds source, prompt and time (substrate/provenance/schema.py:44-54@84b8a38e3). The model is stored as the literal 'operator-default' (EXECUTED probe). The fork route does not exist (reformat.ts:108-125). |
| K2-08 | partial | The pipeline is type-agnostic but the only entry is `/books/{id}/reformats`. Voice and video are noted as future work (#3477 non-goals). |
| K2-09 | partial | The verbatim check is paragraph-grained (pipeline.py:295-309@84b8a38e3). A sub-block quote is reclassed as compressed (EXECUTED). Span drift remains on the promoted head (pipeline.py:141-143; EXECUTED RED). |
| K2-10 | partial | Class labels are text (ReformatReview.tsx:36-41), but the classes are self-declared: unrelated text is accepted as compressed (pipeline.py:310-317; EXECUTED). Labels render in the rail, not inline. |
| K2-11 | partial | A CHECK requires an investigation id (schema.py:76-79), but 'inv-never-existed' is accepted (EXECUTED at 632cf592a). |
| K2-12 | partial | There is no contribution record or attribution event. `source_tier=1`, `SourceKind.USER_CONTENT`, ip_holder NULL (pipeline.py:372,388@632cf592a, READ). The pointer walker returns [] for bite refs (EXECUTED ptr_probe). |
| K2-13 | partial | The passage route is gate-served, but it returns `{servable, text}`, not GatedText, and only `source_refs[0]` is pulled (reformat_routes.py:217-297; ReformatReview.tsx:240@84b8a38e3). |
| K2-14 | partial | The trace opens the original document at page grain (ReformatReview.tsx:171-184). Probe answers persist no source refs and have no unresolved state (:248-280). |
| K2-15 | partial | Bites project into evidence_index (substrate/companions/projector.py:398-440@84b8a38e3). There is no answer-level record and no attribution reader. |
| K2-16 | missing | `git grep presentation_mode origin/main` returns no hits, and there are none on the reformat tree (EXECUTED). |
| C1-01 | partial | One shell survives mode switches at runtime (EXECUTED RT-S2). The "same test as K1-01" does not exist. |
| C1-02 | partial | Doors switch mode inside the same shell (EXECUTED). prefix+m and ctrl+alt+m are reserved (keymap.ts:219@410ff22e9). |
| C1-03 | missing | Doors navigate to fixed routes (components/hotkeys/shortcuts.ts:262-279@8e007f2cb). No project survives a mode switch, and there are no Reading doors. |
| C2-01 | done | The preset lives in PanelLayout (PanelLayout.tsx:208-267@76e2b4fbf), and AppShell still mounts PanelLayout. |
| C2-02 | done | PanelLayout.tierCrossing passes 3/3 at 76e2b4fbf, 57f8deca3 and 410ff22e9 (EXECUTED). The hooks stay above the sm return. |
| C2-03 | done | Both presets render. Docked is stated as the default (persistence.ts:351-369@410ff22e9), although lane A's spec now says the cockpit is the default (DESIGN-MODEL.md:39@680999df5). |
| C3-01 | done | Rows were only added. keymap.test.ts passes (EXECUTED). |
| C3-02 | partial | No row notes that its combo is free on the platform. The ctrl+alt+l KDE collision is unnoted (keymap.ts:152-156@76e2b4fbf). |
| C3-03 | done | No Cmd+arrow or Cmd+F binding. validateKeymap accepts mod+f (EXECUTED P9b), so the ban is unenforced. |
| C3-04 | contradicted | `i` and `ctrl+alt+i` bind the layout preset over the inbox (DESIGN-MODEL.md:50). `c` and `ctrl+alt+c` bind close over New tab (:40). Both are still bound on train 0a5441372 (keymap.ts:165-166) and rescue ad39736d0 (:172-173,201-202) (EXECUTED). `f` is now ratified (DESIGN-MODEL.md:55). |
| C4-01 | contradicted | The pane is an agent switcher with no companion-document entries (CompanionPane.tsx:37-98@57f8deca3). ReadingCompanion is still mounted. Two panes mount at once after a preset toggle (EXECUTED P1, latent). |
| C4-02 | partial | Only research-thread and dialogue kinds exist (companionRegistry.tsx:34-55@57f8deca3). There is no diligence, island or reformat kind. |
| C4-03 | partial | spawnChild is reached through crossPane at 05eeb6223 (crossPane.ts:32-56) and unit-tested. No product caller exists, and the node lands in the Reading tree (EXECUTED VX4). |
| C5-01 | partial | Same as K1-23. |
| C5-02 | contradicted | A second drag protocol, SOURCE_DOCUMENT_MIME, uses an unguarded JSON.parse (WriteOutlinePane.tsx:32,155@0f4361e22) instead of extending dragToOutline. |
| C5-03 | contradicted | Follows K1-25 (contradicted) and K1-26 (partial). |
| C5-04 | contradicted | Same as K1-27. |
| C5-05 | done | mod+/ opens shortcuts:aisidecar on a write route with 0 agent tabs (EXECUTED writeMode test). The row is scope outside-text (keymap.ts:126), so it is dead inside the editor. |
| C-META-01 | done | DECISIONS.md:35-43 (home 7b0ec5ea0). The text was written by Kimi (rec 38297). The operator's ratification is unverified (see §9). |
| C-META-02 | done | All four PR bodies open with "C1–C5 RATIFIED (2026-09-24)" (EXECUTED gh). |
| B-01 | partial | The cockpit delta adds no keymap, token or shell module. It adds flat tab/state stores: companionStore.ts:24-144@57f8deca3, writeOutlineStore.ts and blockSources.ts@0f4361e22, and on the vision stack workstationSessionStore.ts. |
| B-02 | done | The added lines contain no window or document keydown listener (EXECUTED grep 8e007f2cb..410ff22e9). |
| B-03 | done | The tabTree.ts blob is a0a2dd0cf at both 5888cf9ca and 410ff22e9, and its suites pass (EXECUTED). |
| B-04 | partial | Only tokens are used and the lints pass. INSET_GAP is raw (PanelLayout.tsx:47@410ff22e9). Companion text fails AA at 2.87:1 and 3.24:1 (EXECUTED). |
| B-05 | partial | The path header is uncompressed, there is no sibling strip, the path is duplicated through Trail, and the tree is listed breadth-first (DocumentTabStrip.tsx:141-165,244-251@410ff22e9). |
| B-06 | contradicted | The inset reading measure is 48 characters per line against 63 docked (EXECUTED line-box count, RT-17 adjusted). |
| B-07 | partial | No cockpit code is on main. The stacked merges came from MiMo's `--admin` loop, not the train. Kimi merged 4 spec PRs to main, each triggering deploy_backend (EXECUTED), against BRIEF:149. |
| B-08 | done | No message to, or rewrite of, Nudge or Sweep was found. Kimi's #3433 merge did invalidate Nudge's local safety heads (rec 40096). |
| B-09 | contradicted | The D2 meanings of `i` and `c` were replaced without a record (keymap.ts:170-173,201-202@410ff22e9). D6 is absent from the carrier with no decision. Lane A has since recorded their restoration (DESIGN-MODEL.md:56-57), but the code still holds the old bindings. |
| B-10 | partial | #3428, #3431, #3433 and #3435 were merged by Kimi's loop. #3425 merged 09-26 13:59:48Z. #3437 was not re-checked (not established). |
| B-11 | done | Every cockpit branch descends from 8e007f2cb (EXECUTED). |
| D1-01 | missing | No registry. The single project is 'default' (tabTreeStore.ts:46@410ff22e9). |
| D1-02 | missing | No project exists to keep. The doors reset place (shortcuts.ts:262-279@8e007f2cb). |
| D1-03 | contradicted | "Open research →" is a router Link that navigates away (CompanionAgents.tsx:69-74@57f8deca3). The reader beside the draft has no home in Write. |
| D2-01 | done | The prefix never arms in text fields (EXECUTED cockpitInset and documentTabStrip tests; 625/625 hotkeys and workspace suites at 76e2b4fbf). |
| D2-02 | partial | n/p are bound. 1–9 and the workstation rows are reserved (keymap.ts:216-228@410ff22e9). |
| D2-03 | done | All new chords are in the ctrl+alt family. validateKeymap reports no plain-alt problem (EXECUTED). |
| D2-04 | missing | findByHierNumber has no UI caller (tabTree.ts:328@5888cf9ca is the only hit). |
| D2-05 | partial | The key sheet renders 45 rows, including all cockpit rows (EXECUTED). The tree toggle and companion strip carry no aria-keyshortcuts (EXECUTED PROBE-7). |
| D3-01 | missing | No per-workstation Companion tab (CompanionPane.tsx:37-98@57f8deca3). |
| D3-02 | missing | The right pane is not filtered to the active left document. The picker is global (CompanionPane.tsx:230-233). |
| D3-03 | missing | The cockpit reads GET /investigations only (useInvestigationList.ts:35). The companion stack's shape diverges from §1.12 (projector.py:461-500@08ad0d753, SIBLING). |
| D4-01 | contradicted (latent) | The diligence daemon spawns with no per-flag consent when switched on, and the switch is off by default (daemon.py:707-714@d7fcb3b37, SIBLING). Its presence on main is not established. |
| D4-02 | partial | A flat USD 0.50 reserve against a USD 2.00 child budget. The summary clamps at the cap. The env var names mismatch (daemon.py:492; budget.py:36, SIBLING). |
| D4-03 | contradicted | prefix+i and ctrl+alt+i toggle the preset at 410ff22e9, 0a5441372 and ad39736d0 (EXECUTED). No inbox exists. |
| D5-01 | not established | Reading-home doors fall outside every audited slice. |
| D5-02 | not established | Standalone-book home was not audited. |
| D5-03 | partial | `f` is now ratified as fullscreen subsuming distraction-free (DESIGN-MODEL.md:55), but fullscreen leaves Topbar and NavRail in place (AppShell.tsx:149,170@0a5441372). Page keys were not audited. |
| D5-04 | missing | Same as K1-06. |
| D6-01 | partial | spawnChild is used only by crossPane, with the wrong document_id and no anchor (crossPane.ts:47-54@05eeb6223). |
| D6-02 | partial | The model is unbounded (property tests pass). At depth 200 the UI renders 201 path buttons and a 2808px indent (EXECUTED VX6). |
| D6-03 | partial | Hierarchical numbers and subtree focus exist. There is no compression, cap, badge or "up", and order is breadth-first (EXECUTED VX1, VX6). |
| D6-04 | partial | The keys are bound but fail across documents in a real event loop (EXECUTED VX3). |
| D6-05 | partial | The left strip uses one model. The right strip and the block tabs use flat stores. Close is persisted at once and undo never expires (EXECUTED VX9). |
| H-01 | partial | C2/C3 fail at their parent and kill 5/5 mutants. C5 kills M1 and M2. 05eeb6223 is red-then-green on F5. In C4, 5 of 10 mutants survive and the visibility test is vacuous. fc1809819 and d2adee826 are red commits. In reformat, 5 of 12 mutants survive (LANE-A). |
| H-02 | contradicted | Contrast 2.87:1, 3.24:1 and 1.43:1 (EXECUTED). State shown by colour alone. No tabpanel, no focus return, and no tree focus management. axe reports aria-required-children as critical in the zero-block Write pane (EXECUTED). |
| H-03 | partial | Raw-id labels, a file-name TODO in UI copy (WriteOutlinePane.tsx:237-241@0f4361e22), and jargon ("an honest anomaly", ReformatReview.tsx:292@84b8a38e3). copy-lint skips src/workspace (shared/copyLint.test.ts:35). |
| H-04 | partial | The cockpit writes nothing to the substrate. Paragraph 2 sets ip_holder NULL, USER_CONTENT and source_tier=1, and on the #3516 head a cross-owner read is possible (EXECUTED RED). No money routing exists. |

## 4. Scorecard

Each dimension score equals 100 minus the listed deductions. The auditor's score is shown so that the verification deltas are visible. The overall score weights the dimensions by what the operator asked for. The four paragraph-1 build slices carry 15% each, paragraph 2 carries 20%, and runtime and process carry 10% each.

| Dimension | Auditor | After verification | What cost the points |
|---|---|---|---|
| Topology and process | 36 | **40** | −18: D6/C5 stranded off every line to main, and the base retarget hides it. −12: merged by an unreviewed MiMo `--admin` loop on red or unstarted checks, with auto-merge left on. −10: the 8 required CI contexts never ran. −8: no different-lineage critic, and the promised craft review never ran. −4: paragraph 2 and workstation are disjoint and carry a parallel store. −2 each: main-merge loops outside the train (brief conflict), no board claim, undisclosed red CI, red pushes/attribution/prod SSH. Verification returned +7 for three majors downgraded and took −3 for the misreported incident and the 29 other admin merges. |
| C2/C3 inset and keys | 50 | **51** | −12: geometry (landscape left pane, 320px right) and no left toolbar; the test uses a fake nav. −11: fullscreen and preset toggles unmount panes and destroy state; right fullscreen does not fill. −6: hidden fullscreen state blanks the cockpit or swallows the sidecar, including in the docked default. −4: `i` taken from the inbox, locked in by a test. −8: sticky ring, role-less panes, Esc only inside the layout and double-firing with modals, no pointer path. −2: fullscreen does not hide chrome now that `f` subsumes distraction-free. −3: silent at lg and md. −3: raw gap, undocumented chord collisions, jargon labels. Verification returned +3 because the `f` half is ratified. |
| C4 companion pane | 30 | **30** | −18: no agent can open a document on the left; at C4 the seam opened a floating window. −8: not the D3 companion document, and ReadingCompanion duplicates it. −8: agent tabs are status cards over a global 50-item poll, and "Open research" navigates away. −8: unreachable in the docked default, and gone below 1024px or at lg with the sidecar open. −8: unknowns shown as loading or empty, replies lost on a tab hop, raw model output likely. −7: contrast 2.87:1, 3.24:1 and 1.43:1, colour-only state, no tabpanel or focus return. −5: entry over budget, with the gate never run. −3: reserved n/p taken, keys act on an invisible pane. −3: vacuous test, 5/10 mutants survive. −2: naming and copy. |
| D6 document tabs | 36 | **25** | −15: child tabs for other documents collapse into duplicate roots. −10: the activation effect hijacks existing navigation app-wide (verifier raised to blocker). −12: no link, footnote, citation or research spawn, and branch_origin records the target. −5: agent opens flip the mode to Reading. −8: breadth-first tree, no compression, no sibling strip, uncapped indent. −6: a spawn during a 409 is lost, close is not held 10 s, undo never expires. −5: ctrl+alt+c closes tabs from inside text fields, and `c` taken from New tab. −8: no ARIA tabs or tree, raw labels, fake Trail entity. −3: no project layer or 1–9. −3: no states or stories, and the tests never await. |
| C5 Write | 38 | **38** | −15: a section-tab switch discards unsaved edits and the editor. −10: the body tab is outline cards and persisted prose cannot be edited on load. −7: block tabs go stale, and a drop during a piece switch is misfiled. −6: section_index collision and heading renumbering, and a closed section tab never returns. −8: DnD is session-only, a second protocol, with no keyboard path or reorder. −5: raw ids, false "opens as window", a file-name TODO in copy. −5: missing states, a critical axe violation, "Companion pane" label in Write. −2: bundle growth. −2: latent lost-update contract. −2: mislabelled keys, dead drag source, docked panel leaking into other modes. |
| Paragraph 2 reformulation/provenance | 36 | **25** | −12: #3516 lacks the owner check and three other fixes (cross-owner read). −10: the real generator returns 500. −6: the derived document 404s in the reader (LANE-A). −8: island card and floating window instead of a right-pane agent tab and a left child tab, and spawnChild denied. −8: a second fork/derived-asset model, routes that do not exist, errors masked as "pending". −10: no attribution hookup, ip_holder NULL, tier 1, USER_CONTENT escrow exclusion, takedown not followed. −8: classes self-declared, fabricated investigation ids accepted, model identity not recorded. −5: paragraph grain and drift. −5: no time budget, focus items or presentation mode. −3: SPR-00 gate skipped, and paragraph 2 never recorded as a decision. |
| Runtime and visual (union head) | 46 | **36** | −8: entry 13.56 KB over budget with nothing lazy. −10: state loss on fullscreen and preset, right fullscreen 320px. −8: geometry and bottom rail. −10: the Write left pane is cards, section_index collides, `c` closes tabs from inputs. −8: strip overflow at 2 agents, no companion entry in docked mode, md drops the right pane. −6: breadth-first tree, raw labels, false copy. −6: no production child-tab path. −5: contrast and focus. −3: tests blind to runtime (no AppShell, no Router, no geometry). |
| **Overall** | | **34** | 0.10×40 + 0.15×(51+30+25+38) + 0.20×25 + 0.10×36 = 34.2. Value delivered to the operator on main or in prod is zero: nothing he asked for is deployed. |

## 5. Confirmed findings, ranked

The source IDs point to the dimension records. "Adjusted" marks a verifier change of severity or wording.

### 5.1 Blockers

| # | Finding | Evidence | Fix (owner) |
|---|---|---|---|
| F-01 | D6 and C5 are stranded off every line toward main. The only remote copy is on a branch GitHub shows as merged, the local rescue is unpushed and unclaimed, and the carrier now conflicts with it (9 markers in 4 files). | PF-01 (confirmed); EXECUTED ancestry: 05eeb6223, 0f4361e22 and 410ff22e9 are not in 0a5441372 or 483445a43; ls-remote shows no cockpit-a1 ref | Tag 410ff22e9 now. Push the rescue branch under a board claim. Integrate onto the train through one reviewed PR (lane A, Nudge). |
| F-02 | A section-tab switch discards the pending edit and removes the editor, during exactly the keyboard flow C5 promotes. | C5-F01: EXECUTED F01a, 0 saves against 1 in the control, chord fired from the editor; Outline.tsx:263-268@0f4361e22 | Keep every SectionCard mounted and scope visually, or flush on unmount. Red-first test (lane A). |
| F-03 | Any child tab pointing at another document is replaced by a duplicate root once the event loop runs. The only wired product path collapses too. | D6-F03: EXECUTED VX2, VY1; DocumentTabStrip.tsx:79-93@05eeb6223 | Resolve the route to an open node before seeding a root, and carry the tab in the URL. Lane A reports this fixed in ad39736d0 (READ, not verified). |
| F-04 | The activation-inference effect hijacks existing navigation. After any earlier read, Research and Write openers land on the previously read document. | D6-F05 (adjusted to blocker): EXECUTED VX5 and VY7; AppShell mounts PanelLayout once around Routes | Emit navigation from activation commands, and delete the tree→route effect (lane A). |
| F-05 | No agent can open a document as a left tab in production. At C4 the seam opened a floating window. At D6 the node lands in the Reading tree and leaves Research. | C4-F01 (confirmed at five heads), D6-F06, RT-10 | Ship an agent-reply `source_refs` field (LB-3), pass the source document and anchor into crossPane, and keep the mode (lanes A+B, seam S1). |
| F-06 | Promotion #3516 would ship reformat with no source-owner check (a cross-owner read of personal_reading text), with span drift and with the collision hole. #3522 carries the fixes, and both are open. #3477 (spawnChild denial) is still armed. | P2-02 (confirmed): EXECUTED 5 red tests on 32046177f and 22 green on 632cf592a; EXECUTED gh: #3477 auto=ARMED, `allow_auto_merge=true` | Close #3516 as superseded. Hold #3477. Do not land #3522 until LB-4a (lane B flags; operator and merge authority act). |

### 5.2 Majors

| # | Finding | Evidence | Fix (owner) |
|---|---|---|---|
| F-07 | No person or train chose the four cockpit merges. A crashed MiMo loop ran `gh pr merge --merge --admin` on CLEAN or UNSTABLE after enabling auto-merge. The same loop admin-merged 29 stack PRs, including #3454 while it was blocked. The incident record claims the loop was stopped "before any subsequent iteration could merge", which is false. `delete_branch_on_merge=true` drove the stranding. | PF-02 and verifier misses; READ mimocode.db; EXECUTED gh; COORDINATION:343-344 | Correct the incident record. Set `allow_auto_merge=false` (operator). Record all 33 merges as unreviewed. |
| F-08 | ci.yml runs only on PRs into main, so tsc, vitest, pytest and build:check never ran on any cockpit head. e2e and lostpixel were red, inherited from the Trail story rename and stale baselines, and undisclosed. The entry chunk is over budget. | PF-03, PF-05 (adjusted minor), RT-01, C4-F02, C5-F16; EXECUTED check_bundle −2.47/−13.56 KB | Run ci.yml at the exact integration head. Lazy-load the cockpit panes. Fix the e2e story IDs (lane A). |
| F-09 | No different-lineage critic reviewed any Kimi cockpit commit. Kimi's "review" was a file list, and the craft review it promised never ran. | PF-04; DECISIONS.md:24 | Run GLM or MiMo now and codex after 2026-09-30 14:16, before integration. |
| F-10 | Kimi never read DESIGN-MODEL, THREAD-CONTRACT, GAPS or the sprint pages; its only spec reads were `ls` and `head -80 DECISIONS.md`. A compaction then dropped the cockpit from agent-38's memory. Most reserved-key and contract contradictions follow from this. | LANE-A (tool-call search VERIFIED; compaction cause INFERRED) | Every engine brief must require reading DESIGN-MODEL and THREAD-CONTRACT before building (process). |
| F-11 | Paragraph 2 was built on stacks disjoint from the cockpit. The engagement sits in the island card, the result opens a floating window, the fork is a documents row, and fork/merge routes do not exist. The workstation stack adds a second registry and tab store. | P2-04, P2-05, PF-08; SIBLING §3.1, §3.3 | Rebuild on the contract: §1.11a derivation, right-pane reformat tab, left child tab (lanes A+B). |
| F-12 | Reformat cannot run or be read in production. The `reformat` role is not registered (KeyError, 500), the derived document gets no book_assets row (404), and the generation record stores 'operator-default' instead of the model that wrote the text. | P2-03; LANE-A; P2 verifier miss; EXECUTED grep 632cf592a | LB-4a. |
| F-13 | Derived text is mis-registered. It gets `source_tier=1` (highest trust), `SourceKind.USER_CONTENT` (escrow-excluded) and ip_holder NULL. Rights are copied once, so a takedown does not propagate. | P2-06 (adjusted); READ pipeline.py:372,388@632cf592a; SIBLING refm/r09; LANE-A | LB-4a and LB-5. |
| F-14 | Provenance is not defensible. The model self-declares compressed and expanded, fabricated investigation ids are accepted, author text is checked at paragraph grain with a non-contract locator, and the citations are invisible to the pointer walker. | P2-07, P2-08, P2-06; EXECUTED probes | LB-5. |
| F-15 | Three operator asks are wholly absent: reading-time budget (K2-02), focus items (K2-03) and presentation mode (K2-16). | P2-09, P2-11 | LB-6 and LB-7. |
| F-16 | The inset is not "two tall rectangles": at 1280×800 the left pane is 924×636 and the right a fixed 320px. NavRail stays at the bottom, and the inset test uses a fake nav. | C2C3-02/03, RT-04/05; EXECUTED | Tiled halves, NavRail `orientation='left'` in inset, geometry tests (lane A). |
| F-17 | Fullscreen and preset toggles unmount the hidden pane and remount the route, destroying drafts and silencing ⌘K. Right-pane fullscreen stays 320px. | C2C3-04/05, RT-02/03; EXECUTED at 76e2b4fbf, 410ff22e9 and 0a5441372 | Hide with CSS, keep one stable tree, flex-1 on the fullscreen side (lane A). |
| F-18 | Fullscreen can hide everything with no indicator. A stale focusedPane blanks the cockpit after a tier change, and in the docked default `prefix+f` silently traps the next sidecar open in a 0px dock. | C2C3-06, verifier miss H3 | Visibility-checked toggle and a fullscreen chip (lane A). |
| F-19 | Reserved D2 keys were repurposed. `i` is the preset (not the inbox) and `c` is close (not New tab). Destructive `ctrl+alt+c` fired from inside text fields at 05eeb6223. The bindings persist on the train and the rescue. | C2C3-01 (i half), D6-F12, verifier miss VY2; EXECUTED keymap rows at 0a5441372 and ad39736d0 | Apply DESIGN-MODEL.md:53-57 in code. On Mac, 4cee10474 already stops chords in text (lane A). |
| F-20 | The right pane is not the D3 companion document, and ReadingCompanion duplicates it in Reading. | C4-F03; LANE-A rendered | Findings tab kind over §1.12 (LB-9 + lane A). |
| F-21 | Agent tabs are status cards over a global 50-item, 30 s poll, with no event stream or process view. "Open research" navigates the left pane away. | C4-F04, D1-03 | LB-3 + lane A. |
| F-22 | The companion is unreachable in the default docked preset and disappears below 1024px, and also at lg when the sidecar is open. | C4-F08, C4 and RT verifier misses; EXECUTED probes V1, probe5 | Bind `prefix+r`, show at every tier (lane A). |
| F-23 | Unknowns render as "Loading…" or "No research threads yet", dialogue replies vanish on a tab hop, and replies likely show raw JSON or `@@actions` (inferred; no live model call made). | C4-F06 (adjusted), C4-F09, C4 miss | Status machine, persisted turns (LB-3), parseAssistantReply (lane A). |
| F-24 | Accessibility failures. Contrast is 2.87:1, 3.24:1 and 1.43:1. State is shown by colour only. There is no tabpanel, no Escape or focus return, and no tree focus management. axe reports a critical aria-required-children violation. | C4-F13/F14, D6-F14, RT-14/16, C5 miss; EXECUTED | Lane A. ad39736d0 claims the ARIA tabs and tree (READ). |
| F-25 | The companion tab strip overflows at 2 agents and clips its content at 3. | RT-06; EXECUTED | Lane A. |
| F-26 | The tree is illegible. It lists breadth-first, children draw under the wrong parent, and it has no compression, sibling strip or indent cap. | D6-F07/F08, RT-08; EXECUTED | Lane A. Claimed fixed in ad39736d0. |
| F-27 | branch_origin records the opened document with no anchor, so `prefix+u` cannot return to the passage. The spawn seams are unwired. | D6-F09/F10 | Seam S1 (lanes A+B). |
| F-28 | Tab persistence breaks §2.2. A spawn made during an in-flight 409 is lost, close is written at once, and undo never expires. | D6-F11; EXECUTED VX8, VX9 | LB-2 + lane A (close hold claimed in ad39736d0). |
| F-29 | No project layer exists; the project id is the constant 'default'. | D6-F13; K1-04, K1-17 | LB-2 + lane A A2. |
| F-30 | Tabs show raw ids ("/write/d-1", "section:s-2", "/inv/x") with false "opens as window" copy. Trail fakes a single entity. | D6-F15/F16, C5-F04, RT-09 | Lane A. Claimed fixed in ad39736d0. |
| F-31 | Write block tabs go stale after outline edits. Section tabs write a colliding section_index and renumber headings. | C5-F02/F03, RT verifier miss | Lane A. |
| F-32 | The Write body tab is cards, not text. Persisted prose shows only behind a read-only X-ray. | C5-F07, RT-07 (adjusted) | Lane A. |
| F-33 | Block DnD is session-only, runs on a second drag protocol, and has no keyboard path or reorder. | C5-F05 (adjusted) | LB-8 + lane A. |
| F-34 | The Write outline pane shows "loading" and "no blocks" at the same moment and has no retry or partial state. | C5-F08 | Lane A. |
| F-35 | The C4 tests are weak. The visibility test is vacuous, and 5 of 10 mutants survive. | C4-F12; EXECUTED | Lane A. |
| F-36 | The control plane is wrong. The board records the reformat fixes as "merged to product main" (they are not). Two promotion PRs compete. #3516 also carries the whole workstation stack. | P2 verifier misses; EXECUTED ancestry | Correct the board. Close #3516 (merge authority). |
| F-37 | C1–C5 carry "RATIFIED BY FAISAL", but no operator-authored ratification exists in any transcript. | LANE-A; READ baseline source-stability tension | Operator confirms (§7, T1). |

### 5.3 Minors (confirmed, one line each)

- **Kimi's process.**
  - Kimi ran main-merge loops outside the train. The brief's item 8 asked it to keep them moving, while BRIEF:149 forbade pushing to main (PF-06 adjusted).
  - There was no board claim (PF-07 adjusted).
  - Red commits fc1809819 and d2adee826 break bisection (PF-09).
  - No stories were added, so the lost-pixel shot count stayed at 702 (PF-11).
  - Attribution drifts after 09-24 (PF-12).
  - The UI session made a production SSH state change (PF-13).
- **Pane and key behaviour.**
  - Esc works only inside the layout, and a single Esc both closes a modal and exits fullscreen (C2C3-07, C2C3 miss).
  - The panes have a sticky ring and no role (C2C3-08).
  - The pane keys can focus a 0px dock (C2C3-11).
  - The new actions have no pointer path (C2C3-12).
- **Companion state and naming.**
  - The legacy state words read failed as "needs attention", and the unseen halo is hard-coded off (C4-F05 adjusted).
  - Duplicate companion panes are latent (C4-F07 adjusted).
  - n/p were taken and then retargeted (C4-F10 adjusted).
  - Keys cycle an invisible pane (C4-F11 adjusted).
  - A second flat tab model exists (C4-F15).
  - The bare word "companion" is used (C4-F16).
  - Grounding status is dropped (C4-F17 adjusted).
  - The "Try again" button only dismisses the error (C4 miss).
  - crossPane drops the agent origin (C4 miss).
- **Document tabs.**
  - prefix+1–9 and hierarchical-number jumps are unbound (D6-F17).
  - The UI sits outside MS-04's planned modules (D6-F18).
  - There are no states or stories, and ensureMothership has no error path (D6-F19).
  - The tree panel overlays the text (D6-F20 adjusted).
  - Meta-reading routes are seeded as readers (D6 miss).
  - Undo is dropped on navigation (D6 miss).
  - d2adee826 silently rebinds C4's keys (D6 miss).
- **Write.**
  - The block-source contract can lose updates, a latent flaw (C5-F06 adjusted).
  - The key rows are labelled "Companion" (C5-F09).
  - The reader-tab drag source is dead (C5-F10).
  - The WriteOutline panel leaks into other modes (C5-F11).
  - The right pane is still labelled "Companion pane" (C5-F12).
  - UI copy contains a file-name TODO (C5-F13).
  - The node-trace source is not shown (C5-F14).
  - A closed section tab is lost after the next spawn (C5-F15 adjusted).
  - fc1809819 alone is red on copy-lint, and the PR calls its bridge "ratified" (C5-F17).
  - The old piece's tabs show under a new route (C5 miss).
  - A raw document_id is shown when a drag carries no title (C5 miss).
- **Paragraph 2.**
  - The probe is page-grained and non-GatedText (P2-10).
  - No presentation record exists (P2-11).
  - The SPR-00 gate was skipped (P2-12).
  - UI copy uses jargon (P2-13 adjusted).
  - Paragraph 2 is absent from DECISIONS (P2-14).
  - An unvalidated investigation id becomes parent_investigation_id (P2 miss).
  - There is no chunking of book-length sources (P2 miss).
  - Probe errors are swallowed (P2 miss).
  - Reading.reformat.test is red in CI at f8359b827 and 88c7f51e5 (LANE-A, SIBLING) but green locally at 84b8a38e3 (EXECUTED). Whether this is head-dependent or flaky is not established.
- **Runtime and visual.**
  - INSET_GAP is raw (RT-12).
  - The left focus ring is partly occluded and doubled (RT-13 adjusted).
  - The Write copy leaks jargon (RT-15).
  - The inset measure is 48 characters per line (RT-17 adjusted).
  - The tests are blind to runtime (RT-18).
  - The inset is opt-in (RT-19).
  - At md the right pane disappears and the pane-right key is a no-op (RT miss).
  - Panes carry an aria-label with no role, and in Write the right pane is misnamed (RT miss).
- **On main.** #3425 put B4 on main: anchor delete is owner-scoped but not document-scoped (store.py:293@483445a43, READ).

## 6. What Kimi got right that must be kept

- **Opus's work was extended, not forked.** Every cockpit branch descends from 8e007f2cb. `tabTree.ts` arrived byte-identical: blob a0a2dd0cf at 5888cf9ca and 410ff22e9, with patch-id 4657312f1b82 at both 5888cf9ca and 93cc19edc. It was never edited, and its property suites pass (PF-16, D6-F01, all EXECUTED).
- **The one-table key discipline held.** Every new action has an ACTIONS entry, a prefix row scoped outside-text with a ctrl+alt twin, a handler in `createActionHandlers`, a TASK_OF entry and a key-sheet row. No window or document keydown listener was added, and validateKeymap stays clean (C2C3-17, C4-S01, D6-F02, EXECUTED).
- **The inset is a PanelLayout preset, not a new shell.** The `{mainSlot}` contract, `dockSide()`, the tier-sm early return with all hooks above it, and the sidecar and project-tree toggles are untouched. Docked stays reachable, and preset persistence fails safe (C2C3-16). A mode switch keeps one shell at runtime (RT-S2).
- **The C2/C3 tests are behaviour-sensitive.** They fail at the parent and kill all five PanelLayout mutants (C2C3-18). The C5 tests kill M1 and M2 (C5-S04). 05eeb6223 was diagnosed against the parent tree and shows real red-then-green on Opus's own F5 guard (PF-18).
- **There is one `/thought-partner` wire,** shared by FloatMenu and the dialogue tab, with honest no-provider handling (C4-S02). crossPane is a swappable event seam; D6 swapped its handler without touching callers (C4-S04).
- **C5 refuses to pretend-write.** Zero substrate writes on drop, asserted (C5-S01). The copy-lint re-mint moved one line without widening the baseline (C5-S05, PF-14).
- **The PR bodies are honest about scope and numbers.** They cite C1–C5, and their test counts match the transcripts (PF-17, PF-18, D6-F22). Kimi declined to merge its own cockpit PRs (run-ledger.md:3067).
- **The substrate ideas worth harvesting come from Kimi's vision stack.** These are the ones SIBLING calls better than the contract:
  - `bite_provenance`, with its DB CHECKs (verbatim implies equal hashes; research-supplemented if and only if an investigation is present), plus the gated source read, the single-transaction write and the byte-identical-original test (P2-15);
  - `anchored_highlights` as the §1.4 anchor store;
  - the reading_state revision compare-and-set;
  - the refs-only `diligence_queue`.
- **The unit-8 spec is the paragraph-2 contract of record,** to be reconciled rather than discarded: invariants, rejected alternatives, calm-by-default with a complete agent-facing trace (P2-01).

## 7. Tensions the operator must rule on

These tensions are still open. Lane A's DESIGN-MODEL decision (lines 53-57@680999df5) settles `f`, `i`, `c` and `n`/`p` within the operator's "whatever you determine" delegation, so they are not relisted. The platform invariant settles the Ad-system money question: telemetry only while G2/G3 are open.

| # | Tension | Recommended answer |
|---|---|---|
| T1 | C1–C5 are labelled "RATIFIED BY FAISAL", but no operator-authored ratification exists (§9). | Pasting lane A's amended goal ratifies C1–C5 where they match it. Reword C4 in DECISIONS.md to "right pane = AI agent tabs in Research and Reading; the D3 companion document becomes a right-pane Findings tab" and add an author line. |
| T2 | Where does a deep research launched from a document live? Paragraph 1 lists it among the left document tabs; C4 puts research threads in the right pane. | Both, linked by one thread id. The running thread is a right-pane agent tab. Its report opens as a left child tab of the source document, with branch_origin at the passage. |
| T3 | Paragraph 1 says the agent "could open it on the left"; paragraph 2 says it "asks me" first. | An operator's click or key on an agent's "open" opens directly without taking focus. Anything the agent initiates, including every reformat result, is a proposal that one key accepts. |
| T4 | Write's right pane has three claimants: the block outline (C5), the evidence reader beside the draft (D1/A2) and the docked AI sidecar (mod+/). | The right pane is the block outline. Evidence opened from the draft becomes a left child tab under the active section. The sidecar floats as an overlay with a text-safe chord, so it works while typing. |
| T5 | "Block" is ambiguous. In the prompt it may mean the code's section, which would make the right block tabs duplicate the left section tabs. | Keep Kimi's reading. The right pane holds the analysis building blocks (insight, open question, claim) and the documents informing each; the left holds sections of prose. This avoids duplication and gives the snippet-as-insight requirement (K1-28) a home. |
| T6 | "Merge later or officially fork" conflicts with the contract, which retires source merge and allows merge only into a Write deliverable. | Fork is a derived-asset revision commit. Merge means either adopting the reformulation as the project's current reading version (the current pointer) or merging its members into a Write deliverable. It never writes into the source. |
| T7 | "No quote bombs" against "claim spans inline" and invariant 3. | The prose may omit inline quotes. Every claim still carries a resolvable chunk citation, either a quiet marker or a metadata-only record, and the chosen presentation mode is recorded per answer. |
| T8 | What happens to the right pane on a project switch? | Agent tabs belong to the project, as threads do. A switch swaps both panes, and switching back restores both active tabs. |
| T9 | Research and Reading have separate tab forests (TC:247), yet paragraph 1 says reading has the research shape. | Research and Reading share one project's document forest, since the core material is the same. Write keeps its own body-and-sections forest. |
| T10 | Should the cockpit be the default, and how should it behave below 1280px? Omarchy half-screen tiling on a 1920px display gives 960px (tier md), where the right pane vanishes today. | Make the inset the default at every tier from md up, as DESIGN-MODEL.md:39 now says. At lg and md keep both panes by narrowing the right pane to a minimum width and collapsing the docks. Below 768px, show one pane with h/l swapping. |
| T11 | C1 names Speak and Home as modes, but `prefix+m` cycles three and tabTree has three motherships. | Speak and Home are doors outside the cycle, with no forest. `prefix+m` cycles Research, Writing and Reading. |

## 8. Mission goal for the Opus sessions

### 8.1 Amendments to lane A's goal text

This synthesis does not propose a competing goal. Lane A's `GOAL-cockpit-2026-09-26.txt` (3,603 characters) is the base. The amendments below are the ones this audit's evidence requires. Together they add about +183 characters by hand count, for about 3,786 in total. **Recount before pasting**, because the shell was unavailable here.

| # | Where | Replace | With | Why | Δ |
|---|---|---|---|---|---|
| G1 | MISSION, keys | "plus pane focus, fullscreen and a key sheet." | "plus pane focus, fullscreen that keeps both panes mounted, and a key sheet." | The fullscreen and preset toggles destroy drafts and route state at every head, including the train (F-17). Lane A's report does not list it. | +31 |
| G2 | MISSION, Writing | "edited sentence by sentence;" | "edited sentence by sentence, never losing an edit on a tab switch;" | The C5 blocker F-02 is not in lane A's report (its modality "never built or rendered"). | +38 |
| G3 | MISSION, agents | "as a new LEFT tab that records" | "as a new LEFT tab in the current mode that records" | At D6 an agent open moves the operator into Reading and hides the child (F-05, D6-F06). | +20 |
| G4 | MISSION, provenance | "readable by the ad/attribution system;" | "readable by the ad/attribution system as telemetry only until the §9.0 gates open;" | Platform invariant 4 and master-spec §9.0 forbid money routing while G2/G3 are open. Paragraph 2 invokes the Ad system directly. | +44 |
| G5 | AUTHORITY | "THREAD-CONTRACT rev 6 + rev 7" | "THREAD-CONTRACT rev 6 (rev 7 once both sign)" | Rev 7 is unsigned (THREAD-CONTRACT.md:23), and the file forbids building against it until both lanes sign (:3). | +15 |
| G6 | AUTHORITY | "Rescue D6/C5 (design/cockpit-02-companion-pane @410ff22e9)." | "Rescue D6/C5 from 410ff22e9 (tag it first)." | The only remote copy sits on a branch that looks merged, with `delete_branch_on_merge=true` (F-01). | −16 |
| G7 | DONE | "different lineage when available, else fresh Opus" | "different lineage: codex, or GLM/MiMo while it is limited" | Codex is limited until 2026-09-30 14:16 and Kimi returns 403 (VERIFIED). GLM found B1–B3 on this stack (P2-16). Fresh Opus is same-lineage, and the operator's own memory note records it missing defects. | +8 |
| G8 | RULES | after "sit armed." | add " Never merge into an unmerged stacked base." | The stacked `--admin` merges plus the base retarget are what stranded D6/C5 (F-01, F-07). ci.yml never runs on such bases (F-08). | +43 |

The other clauses of lane A's goal stand as written. It already covers the left toolbar, tall panes, two key levels, snippet-as-insight, ask-before-open, merge or fork, the unscrambled-core probe, the future-modalities note, and the rules against self-merge, admin-merge and arming auto-merge.

One inconsistency belongs to lane A's spec text rather than the goal. DESIGN-MODEL.md:40 still lists `ctrl+alt+c` as the New-tab chord, while :57 says `ctrl+alt+c` "is removed". One of the two lines should change.

### 8.2 Lane B work packages (Antiek Sweep v2)

Lane B owns contract Part 1, the backend, agent threads as data, reformat, provenance, probe-to-core and ad metadata. Lane A's A0–A9 are not restated here.

| WP | Scope | Acceptance | Depends on |
|---|---|---|---|
| LB-0 Containment (flag only; operator and merge authority act) | Close #3516 as superseded. Hold #3477 (armed now) until it carries a supersession banner for §1.11a and spawnChild. Operator sets `allow_auto_merge=false`. Correct the board's `merged_main_sha` records and the COORDINATION:343-344 incident entry, listing all 33 unreviewed admin merges. Ask lane A to tag 410ff22e9 and claim the rescue branch. | EXECUTED gh shows #3477 disarmed or explicitly held by its claimant, and `allow_auto_merge=false`. The board and COORDINATION entries exist. The tag exists. | none |
| LB-1 Contract | (a) Review rev 7 with lane A and co-sign it. (b) Draft rev 8 carrying paragraph 2 as C6. Rev 8 covers: <br>• §1.11a reformat derivation on `derived_asset_revisions` (fork = revise, merge-later = merge-drafts), with the provisional documents row only as the reader's view of revision 1. <br>• A GatedText rule for generated text. <br>• A `contribution_class` on §1.11 members (author_verbatim, llm_compressed, llm_expanded, research_supplemented, user, unresolved), each with a `support` flag and span-grain TextLocator anchors. <br>• The generation model identity. <br>• An ordered `informs` relation for Write blocks. <br>• `answer.provenance`, with presentation_mode. <br>• `reformat:` as a non-thread attribution bucket. <br>• Absorption of evidence_index, diligence_queue, the reading_state compare-and-set and `anchored_highlights` (SIBLING §3). <br>Part 2 items (branch kinds `agent` and `derivation`, the right-pane tab list) are lane A's to draft. | Both signatures on rev 7 and on rev 8. A different-lineage audit with all findings closed. A C6 row in DECISIONS.md citing the operator prompt verbatim. | LB-0 not required. The operator rulings T6 and T7 are needed before rev 8 is signed. |
| LB-2 Projects and tab persistence (§1.5/§1.6, "W1") | `/projects` over `write_folders`. `project_tabs` per (owner, project, mothership) with the retirements table and an idempotent `allocate(project, tab_id)`. The HTTP TabTreeAdapter. Keep #3485's owner scoping, revision CAS and 422 validator. Retire the `workstations` and `workstation_tabs` tables and `workstationSessionStore.ts`. Close #3517. | Red-first pytest: a reused number is refused (the R1 repro accepts it today), an invented number is refused, allocate is idempotent, the mothership key is honoured, and a spawn made during an in-flight save survives a 409 (D6-F11 repro). | LB-1(a) |
| LB-3 Agent threads as right-pane tabs | A server state helper emitting the TC §1.2 states (queued, running, needs_you, done, failed, stopped with stop_reason, idle). Per-thread fetch plus a `/ws/events` filter. Listings scoped by project and document. Right-pane tab state persisted per (owner, project, mode). Dialogue turns persisted as thread turns. Thought-partner replies carrying structured `source_refs` and retrieval status, which is the data half of seam S1. | Tests show that failed reads "failed" and never "needs attention", that a reply survives a tab hop and a reload, and that a reply naming a document returns a resolvable `source_ref`. | LB-1(a), LB-2 |
| LB-4a Reformat repair (now) | From the 632cf592a lineage: <br>• Register the `reformat` dispatch role, and extend tests/test_dispatch.py:490 so every role passed to dispatch() has a tier. <br>• Map KeyError and ProviderError to 503. <br>• Store the DispatchResult provider, model and event_id. <br>• Make the derived document readable (fix the 404). <br>• Inherit the source tier and holder, and never register USER_CONTENT. <br>• Apply the source's live gate at serve time (takedown). <br>• Validate investigation ids as existing and owned (validate_refs). <br>• Chunk long sources, with spend under the §1.13 cap. <br>• Stop using `reformat:{gen}` as an investigation id. <br>• Unmask "pending" errors in the client. | Red-first pytest for each item. Re-run the B1 and B3 probes (refm/r08). A real-DispatchConfig smoke test behind the provider flag. Grok or GLM counter-review. | LB-0 |
| LB-4b Reformat on derived assets | Re-home generation, fork and merge onto §1.11a, and delete the unit-5 `/forks` client path. | Fork creates a revision and the original is untouched (asserted). Merge-draft targets follow T6. | LB-1(b), LB-4a, LB-9 (documented order: companion before reformat) |
| LB-5 Span-grain provenance and attribution telemetry | A span ledger per derived-asset revision, with a TextLocator whose sha is recomputed on read. Mixed-class paragraphs. A support score per model span. A `page.attribution.computed` event for `drv:<asset>@<rev>` that splits shares by source documents, as telemetry only with no payout. Citations stored under `chunk_ids` and `document_ids` so pointer walkers see them. Derived chunks excluded from retrieval or mapped back to their sources. | A one-character mutation drops the author label. A two-source reformulation splits its shares across both documents. A test finds zero unclassified spans. A test asserts no payout event is emitted. | LB-1(b), LB-4a |
| LB-6 Probe-to-core and agent-facing metadata | `resolve_probe(asset_id, span_ids)` returns a list of GatedText, each resolving to a source document that is not the derived asset, or an explicit unresolved state. The `answer.provenance` event (retrieved ⊆ record). The probe becomes a B0 branch from `read-<doc>` with an anchor, not free text. | A test that the source ids differ from the derived id. A test that an answer with zero visible citations still has a record equal to its retrieved set. | LB-1(b), B0 landing |
| LB-7 Reformulation parameters and snippet-as-insight | `reading_minutes`, with an estimate and its method and an explicit shortfall. `focus_items` with per-span ids. An `anchored_highlight` promotable to a Write block kind or a tab's anchor question, keeping its locator and sha (K1-28). | Tests per K2-02, K2-03 and K1-28. | LB-1(b), LB-4a |
| LB-8 Write `informs` persistence | Ordered block→document references through the derived-asset repository, with compare-and-set on the current revision. No `deliverables.metadata` PATCH. | The P13 lost-update repro fails before the fix. Persistence across reload is shown. Order is kept. | LB-1(b) |
| LB-9 Companion document (D3) | Rebuild the companion stack to the §1.12 shape. Entries come from the research-artifact projection, as GatedText. The evidence id is owner-safe. GET routes do not write; refresh is a POST plus a typed event. The route answers `unavailable_until_rights` until w5-mcp hardening lands. Replaces #3514. | Shape tests against §1.12. The owner-collision repro (compws R2) fails before the fix. | LB-1(b) |
| LB-10 Diligence consent (D4) | A consent route and event. API-routed, claim-then-spawn. A settled actual cost. The env-var name fix. An owner filter on `_ground_ref`. The daemon refuses to start with the switch on until all of this lands. | A run without a consent event is refused. Reaching the cap gives `refused_capped` (dil P1–P7 repros). | none (forward fix on main) |
| LB-11 B4 forward fix | `HighlightsStore.delete` and `set_investigation_link` take document_id (store.py:293@483445a43). | A doc-a anchor cannot be deleted through doc-b's URI (REVIEW-combined:117-123 repro). | none |

### 8.3 Seams between lanes (agree in writing before building)

| Seam | Lane A side | Lane B side | Written artefact |
|---|---|---|---|
| S1 Left-tab spawn | `crossPane.openDocumentInLeftPane({document_id, source:{document_id, anchor}, opened_by:{thread_id, agent_kind}, activate})` spawns a child in the current mode's tree. | Reply `source_refs` (LB-3). §2.2 branch kind `agent` recorded server-side. | Part 2 §2.2 plus Part 1 reply shape, co-signed |
| S2 Agent-tab kinds | The right-pane registry renders the kinds research, dialogue, reformat, diligence and island. | Thread kind and state from LB-3's helper. | Part 1 §1.2 state enum |
| S3 Tab adapter | tabTreeStore binds real project ids. `allocate(projectId, mothership)` becomes `allocate(projectId, tabId)` in the pure model. | LB-2 routes. | Part 1 §1.6 plus a lane-A tabTree change note |
| S4 GatedText props | One component renders served, cite_only with its reason, and withheld, plus class labels that never rely on colour alone. | One shared type (LB-1). | Part 1 §1.2 |
| S5 Write informs | WriteOutlinePane assigns by drop and by key, and reorders. | LB-8 routes. | Part 1 rev 8 |
| S6 Reformat flow | A right-pane reformat tab asks to open, then opens a left child tab of kind `derivation`. | LB-4a and LB-4b routes. | C6 plus §1.11a |
| S7 Findings tab | The tab kind in the right pane. | LB-9 route. | §1.12 plus Part 2 §2.7 |
| S8 Attribution | Per-bite contribution display (A8). | LB-5 events. | Part 1 rev 8 |

### 8.4 Integration path to main

Every lane B package follows the same path:
1. Take a board claim first.
2. Branch from current main (483445a43 or later).
3. Open a PR straight into main, never into a stacked base whose own PR is open. That way ci.yml's 8 required contexts and build:check run at the exact head.
4. Show red-then-green tests.
5. Get a different-lineage critic's ACCEPT before hand-off: GLM or MiMo now, codex after 2026-09-30 14:16. For the security-relevant LB-4a and LB-11, use two of GLM, MiMo and Grok, or wait for codex.
6. Hand off to Antiek Nudge's train, which merges one PR at a time without admin override.
7. Verify on production by the api build_sha equalling the merge sha, plus read-only GET probes of the new routes.

The order follows the rulings still in force, which require no held-stack batch merges and a fresh review before each promotion:
- **Immediately and independently:** LB-0, LB-11 and LB-10.
- **In parallel with those:** LB-4a, then LB-1.
- **Then:** LB-2 and LB-3.
- **Then, in the documented order, companion before reformat:** LB-9, LB-4b, LB-5, LB-6, LB-7 and LB-8.

The lane A carrier (train 0a5441372) lands through Nudge once it has absorbed the D6/C5 rescue and the key decision. S1 through S8 must be signed before either lane builds against them.

## 9. Cross-check with lane A

Lane A's report does not restate the text of R1–R17. The scope column below is inferred from its coverage rows and its goal text. Verdicts were adjudicated, not averaged.

| Lane A | Scope (inferred) | Mapped here | Lane A | This report | Agree? | Adjudication |
|---|---|---|---|---|---|---|
| R1 | Cockpit flown by keys, with a spaceship feel | K1-01, K1-02, K1-03, C1-01 | PARTIAL | partial | AGREE | Both ran it in a browser. |
| R2 | Project level | K1-04, K1-17, D1-01, D1-02 | MISSING | missing | AGREE | |
| R3 | Links, footnotes, documents and research as document-level child tabs | K1-05 to K1-08, D6-01, D5-04 | PARTIAL | missing (triggers); D6-01 partial | DISAGREE | **Missing.** No product trigger reaches the model: EXECUTED grep of spawnTab callers at 05eeb6223. The child re-rooting that lane A marks INFERRED is EXECUTED here (VX2, VY1). Lane A's own train-state lane also graded it MISSING. |
| R4 | Omarchy geometry, background, left toolbar | K1-10, K1-11, K1-12, C2-01 | PARTIAL | K1-10 contradicted, K1-11 partial, K1-12 missing, C2-01 done | AGREE (group) | This report is finer grained. The 1280×800 measurement shows a landscape left pane, where lane A measured 1440 only. |
| R5 | Left pane holds core material, tabbed, with keys | K1-15, K1-16, K1-09 | PARTIAL | partial | AGREE | |
| R6 | Right-pane agent tabs | K1-18, C4-01, C4-02 | PARTIAL | partial; C4-01 contradicted | AGREE | Both find the D3 companion document without a home. |
| R7 | Pane focus and fullscreen keys | K1-13, K1-14, C3-04 | PARTIAL | K1-13 partial; K1-14 contradicted | AGREE (group) | This report's evidence is stronger on fullscreen: drafts are destroyed (EXECUTED V3), which lane A did not detect. |
| R8 | An agent opens documents on the left | K1-19, K1-20, C4-03 | MISSING | K1-20 missing; C4-03 partial | AGREE | |
| R9 | Reading has the research shape | K1-21 | PARTIAL | partial | AGREE | Two of this report's dimensions disagreed (runtime said done); partial holds, because the acceptance needs a repo test or story and the reader duplicates the companion. |
| R10 | Write block tabs and DnD | K1-23, K1-24, C5-01, C5-02 | PARTIAL | partial; C5-02 contradicted | AGREE | This report adds stale tabs, the misfiled drop and the lost-update contract. |
| R11 | Write body tab, section tabs and sentence editing | K1-22, K1-25 to K1-27, C5-03, C5-04 | PARTIAL | K1-25 and K1-27 contradicted | DISAGREE | **Contradicted.** The edit loss (EXECUTED F01a) and the card-only body (EXECUTED V5) are executed here. Lane A never built or rendered 410ff22e9 (its §6 "modality not run"). |
| R12 | Aligned with the Opus work | K1-29, B-01, B-09, B-11 | CONTRADICTED | K1-29 contradicted (run-wide) | AGREE | This report's dimensions graded the cockpit chain partial. Over the whole run, lane A is right: #3477/#3482 deny spawnChild and #3485/#3487 add a second registry and store. |
| R13 | A snippet as the insight or question | K1-28 | PARTIAL | missing | DISAGREE | **Missing.** Lane A's own gap column says "No first-class object … Never specified", and its Kimi-timeline lane graded it MISSING. Anchors and flags are precursors, not the feature. |
| R14 | Reformat by prompt, with agent, ask, merge and fork | K2-01 to K2-07 | PARTIAL | partial; K2-02/03 missing; K2-04 contradicted | AGREE (group) | This report separates out the two missing parameters and the unrecorded model identity. |
| R15 | Defensible, ad-readable provenance classes | K2-09 to K2-12 | PARTIAL | partial | AGREE | Complementary evidence: lane A found the USER_CONTENT escrow exclusion and 5 of 12 surviving mutants; this report found span drift and the pointer-walker blindness. |
| R16 | Probe-to-core, agent-facing metadata, the AI's presentation choice | K2-13 to K2-16 | PARTIAL | partial; K2-16 missing | AGREE | Both find no presentation-choice field. |
| R17 | Talking to or watching information, noted as future | K2-08 | PARTIAL | partial | AGREE | The grounds differ and both stand. Lane A: "talking to" was elided from the spec. This report: the only entry is `/books/{id}` although the pipeline is type-agnostic. |

**Factual disagreements, adjudicated.**
- **Prod build.** Lane A's §3 reads build_sha ea2d2f129 and its delta reads 570cf6f2f. The orchestrator verified 570cf6f2f at 18:30Z.
- **Which merges breached the train rule.** Lane A names #3433. This report's verifier found the first three followed brief item 8 and #3433 followed codex's hold release. The adjudication follows lane A's critic: DECISIONS.md:26 predates all four merges, and BRIEF:149 forbids pushing to main. All four breached the rule, and the contradictory brief mitigates but does not excuse them.
- **The `f` key.** Lane A's §4 recommends `z` for fullscreen. Lane A's later spec text (DESIGN-MODEL.md:55@680999df5) keeps `f`. The newer spec governs.
- **Reading.reformat.test.** It is red in CI at f8359b827 and 88c7f51e5 (lane A, sibling) and green locally at 84b8a38e3 (EXECUTED here). The heads differ, and whether the cause is head or environment is not established.
- **Lost-pixel counts.** 666/702 (lane A) and 663/702 (here) come from different runs. Both show stale baselines.
- **Reviewer limits.** Lane A marks them UNVERIFIED; the orchestrator has since VERIFIED them.

**Findings only lane A has.** All are VERIFIED by lane A unless marked; this synthesis did not re-execute them.
- Kimi never read the Opus spec beyond `head -80 DECISIONS.md`.
- The agent-38 compaction at 20:47Z (cause INFERRED).
- The operator's C1–C5 ratification cannot be attributed.
- The derived document 404s because it has no book_assets row. This report partly corroborates it: the fix-tip pipeline has no book_assets reference.
- 5 of 12 reformat mutants survive.
- The SPR-00 fork-presentation verdict (72b5c36ad) came 3.7 minutes after the spikes, with no timings and a faked tab strip.
- Kimi stashed a live subagent's work and force-pushed; agent-38 ran `git checkout origin/main -- .` in a shared worktree.
- Prefix keys are inert in the autofocused research field.
- Dark gap/pane contrast is 1.04–1.09:1.
- #3425 changed CI concurrency for every PR.
- A batch update-branch left 33 queued runs.
- CLAIMS-PROOF-STATUS lists 15 SHAs that are not on main.
- The promote branches were force-pushed.
- Naming drift across mothership, workstation, cockpit and island.

**Findings only this report has.**
- **Pane state loss:** fullscreen and preset toggles destroy pane state.
- **Write data corruption:**
  - the C5 edit-loss blocker;
  - section_index collisions;
  - stale and misfiled block tabs.
- **D6 navigation and persistence:**
  - the D6 navigation-hijack regression;
  - agent opens flipping the mode to Reading;
  - the executed two-device lost update.
- **Destructive chord:** `ctrl+alt+c` closing tabs from inside a textarea at 05eeb6223. On Mac, 4cee10474 now stops it.
- **Stranding mechanism:**
  - the MiMo loop reconstructed from mimocode.db;
  - the base-retarget race under `delete_branch_on_merge=true`;
  - the misreported incident;
  - the 29 other admin merges, including #3454 while blocked.
- **Companion reachability:**
  - no companion entry point in the docked default;
  - the companion vanishing below 1024px and at lg with the sidecar;
  - likely raw model output in the dialogue;
  - the executed AA contrast ratios.
- **Reformat control plane:**
  - two competing promotions (#3516 and #3522);
  - the board falsely recording reformat as merged;
  - #3516 carrying the workstation stack;
  - the generation record storing 'operator-default' instead of the model;
  - fabricated investigation ids flowing into parent_investigation_id;
  - the pointer walker not seeing the citations.
- **Kimi's session behaviour:** the production SSH state change.
- **Live state:** B4 landing on main via #3425, and the state of the local rescue branch (ad39736d0, unpushed and unclaimed).
