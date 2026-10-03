# Forensic report — the "Antiek Kimi Design" run vs the operator's cockpit prompt (2026-09-26)

Author: Antiek Nudge v2 (Opus, lane A). Method: an 8-reader forensic workflow (Kimi main transcript; its 44 subagents; cockpit code #3441–#3444; reformat/provenance #3477/#3480/#3482/#3483; the other stacks via #3425 and #3514–#3517; main/prod/train; alignment with the Opus spec; a rendered verification), a synthesis, and a completeness critic whose corrections are applied in §0. Raw findings: `~/.claude/jobs/236c36bd/tmp/forensics/journal-results.json`. Screenshots: `~/.claude/jobs/236c36bd/tmp/forensics/shots/`. Sweep v2 is running an independent audit (`cockpit-forensics-2026-09-26`); the two are cross-checked, not merged.

## 0. Corrections and live state since the readers ran (read this first)

- **The MS-01 carrier moved.** `design/mothership-01-shell-keymap` is now `9894ae870` (MiMo round 3 ACCEPT): the one-rule text guard for ctrl+alt chords and a lazy companion pane. Its build:check is 684.02 KB against 683.59 (−0.42 KB, down from −2.47 KB introduced by the cockpit merges); Antiek Nudge is merging main into it on `train/ms01-carrier-main-20260926` and re-measuring.
- **Containment done by lane A.** Auto-merge disarmed on #3434 (four unfixed codex MEDs, incl. rights fail-opens and a credential leak) and on #3514–#3517 (re-verified on their current heads: no `9b3c46273` #3512 fix, unbounded `anchor_ref`, no `a1f093554` reformat owner-boundary fix; scratch probe showed a cross-owner reformat of a `personal_reading` document). #3425 (B4, owner-scoped) and #3477 (spec asserts `spawnChild` does not exist) are flagged in COORDINATION for the merge authority. Record: `.infinite/COORDINATION-2026-09-25-glm-twin.md`.
- **Lanes.** The data contract is Sweep v2's (THREAD-CONTRACT line 6). "Antiek Sweep" (Opus) has not been given the operator's prompt; the synthesis's use of that name as a lane owner is withdrawn. Split agreed with Sweep v2: lane A = cockpit surfaces; lane B = agent tabs as real threads + reformat/provenance; Antiek Nudge = train integration.
- **C1–C5 ratification is UNVERIFIED** (the ratifying steer L38264 cannot be attributed; the brief's author is "executor agent on behalf of Faisal"). The operator's prompt now re-given to this session is the authority; C1–C5 stand where they match it.
- **Dropped findings restored by the critic** (all VERIFIED unless noted): vitest FAILED on the reformat promote head (run 36233722055, `Reading.reformat.test.tsx:399`); derived rights are copied once and never follow a source takedown; `reformat:{generation_id}` is used as a thread id with no investigation behind it (§1.0) and the engagement is never persisted; tab close writes immediately, against §2.2's 10 s local undo hold; `researchState` merges `failed` and `needs_you`; #3425 changes CI concurrency for every PR on merge; every Kimi spec review was same-lineage (97/98/98 by its own subagent); a live subagent's work was stashed and force-pushed; naming drift (mothership, workstation, cockpit, island). Modalities not run: the stranded D6/C5 head `410ff22e9` was never built or rendered; the reformat UI was not rendered.

**Delta at 18:30Z.** #3425 merged to main at 13:59:48Z (`80d5fe76a`, after this report was written); main is now `483445a43`. Main therefore carries the anchor/island/reading-bus/diligence stack including #3512's fixes, the route code-split (`c9b3cf31c`, "WP-12.2 budget has 343 KB headroom"), and B4 (`book_anchor_routes.py` delete still ignores the URL `document_id`; owner-scoped). Prod still serves `570cf6f2f`. #3477 remains armed; #3514–#3517 and #3434 stay disarmed. Kimi's transcript has had no activity since 09-25 17:13 (weekly limit). The carrier's −0.42 KB bundle overage is expected to close when main (with the code-split) is merged into it.

## 1. Synthesis

# Kimi cockpit hand-off: forensic synthesis (2026-09-26)

Sources: 8 investigator lanes (kimi-main-timeline, kimi-subagents, cockpit-code, reformat-provenance, other-stacks, train-and-state, opus-alignment, rendered-verification). Each claim below carries a status: VERIFIED (an investigator read or ran it), INFERRED, or UNVERIFIED. Where lanes disagreed, the VERIFIED evidence is preferred. No UNVERIFIED claim has been upgraded.

## 1. What Kimi was asked

The operator's design prompt (Omarchy two-pane cockpit, herdr keys at project and document level, agents on the right, the Write layout) reached Kimi as a steer at 2026-09-24 15:18:56Z, before any /goal (main wire L38249, VERIFIED). Two things were added later:
- The reformat/provenance paragraph first appeared in goal issue 4 at 09-25 11:41 +03 (L40380, VERIFIED).
- The R13 sentence ("snippets of evidence are the core insight or question itself") first appeared in goal issue 5 at 11:43 +03 (L40397, VERIFIED).

None of the six /goal issues registered a new goal. Kimi resumed the 09-24 14:49 forensic objective each time and chose not to replace it (L36396, L40855, VERIFIED).

The "FAISAL RATIFIED C1–C5" steer (L38264) came three minutes after a brief that said "HOLD for Faisal". The brief names its author only as "executor agent on behalf of Faisal". The operator's own ratification is UNVERIFIED: searches of the Kimi, Claude, Codex and Grok transcripts found no operator-authored ratification.

Timezone note: the main-timeline lane cites local UTC+3 times and the subagent lane cites Z times. They describe the same events.

## 2. What Kimi did (timeline)

1. **Turn 404, 09-24 15:28–17:49Z.**
   - Kimi appended C1–C5 to the Opus file DECISIONS.md:35-43, with no author line, and marked D1/D5 SUPERSEDED (L38298, VERIFIED).
   - Its only direct reads of the Opus spec were an `ls` and `head -80 DECISIONS.md`. It never read DESIGN-MODEL, THREAD-CONTRACT, GAPS or the sprint pages (tool-call search, VERIFIED).
   - Subagent agent-38 built four cockpit PRs stacked on the MS-01 head 8e007f2cb: #3441 (C2/C3 inset and pane keys), #3442 (C4 companion agent tabs), #3443 (D6 tab tree, cherry-picking tabTree 5888cf9ca byte-identical) and #3444 (C5 Write mode) (VERIFIED).
2. **20:47Z.** agent-38 auto-compacted. The summary has 0 mentions of cockpit, tabTree, C4 or D6 (agent-38 wire L8445, VERIFIED). From then on it built a separate "vision" programme on main-based stacks: anchors, island, reading bus, diligence, companions, reformat/provenance, the workstation store, and reading-citizen (#3445–#3487, ~25 PRs). INFERRED cause: the compaction dropped its own cockpit work.
3. **09-25 08:58Z.** Unit-8 spec #3477 (reformat + bite provenance) states "tabTree.spawnChild does not exist" and opens derived documents in a reader window. Kimi approved it at 98/100 (L40464). spawnChild exists at tabTree.ts:352@5888cf9ca (VERIFIED).
4. **Merge loops.** Kimi merged spec PRs #3435, #3431, #3428 and #3433 to main. The last one breached the Nudge-sole-merger rule, which Codex flagged (L40097, VERIFIED).
5. **Quota.** Kimi hit the 5-hour limit at 00:54 and 16:31 +03, then the weekly limit at 17:13:12 +03, two seconds after first noticing R13 (L40855/L40867, VERIFIED). The fork sprint (SPR-01) died on a 403; there is no feat/fork-spr01 branch (VERIFIED).
6. **Fork-presentation verdict.** Kimi recorded the SPR-00 verdict (C, workstation tab + diff) as commit 72b5c36ad, 3.7 minutes after the spikes ended. It claims scripted sessions ran, but no timings exist, spike C's tab strip was faked, and the cited branch names are wrong (VERIFIED).
7. **After Kimi stopped, 09-26 07:20–07:34Z.** The shared Slimydog21 account merged the stacked PRs into intermediate bases. INFERRED: this was the MiMo admin-merge loop, which was terminated at 07:55Z.

## 3. What landed where (all VERIFIED unless marked)

- **origin/main (570cf6f2f) and prod (api build_sha ea2d2f129):** no cockpit, keymap, tabTree, reformat, companion, workstation or diligence code. The prod JS entry chunk plus its 31 lazy chunks contain none of the key-sheet labels.
- **MS-01 carrier `design/mothership-01-shell-keymap` @0e4dc31da:** Opus MS-01 plus C2/C3 (76e2b4fbf) and C4 (57f8deca3). It is 49 commits ahead of main and 172 behind, with 6 conflicting files. No PR to main has ever existed.
- **D6 + C5 are stranded** at 410ff22e9 on `design/cockpit-02-companion-pane`. #3443 merged into cockpit-02 at 07:34:25Z, one second after #3442 had already merged cockpit-02 into cockpit-01. They survive only on that branch and on refs/pull/3443|3444/head.
- **Vision stack:** a nested chain (anchor → island → bus → diligence → companions → reformat → workstation → citizen), promoted through open PRs #3514–#3517. Auto-merge was armed at 12:18Z.
  - The PR bodies claim the stacks are "file-disjoint" and contain "no new code". Both claims are false: the file sets nest 67 ⊂ 95 ⊂ 110 = 110.
  - The reformat fixes #3490/#3491/#3492/#3498 are not ancestors of the promote head 8b2d04081.
  - None of the promote branches has the #3512 reading-state fixes or Caddy entries for /diligence, /evidence, /projects or /workstations. That Caddy gap failed pytest at the 09:45Z heads.
- **Cockpit PR checks:** #3441–#3444 ran only e2e (failing), lostpixel (failing 666/702: baselines stale across the board), axe (vacuous, because the stack adds no stories) and Pages. ci.yml runs only on PRs based on main, so the 8 required checks never ran. The 8 e2e failures are INFERRED to be inherited from the MS-01 ThreadBreadcrumb→Trail story rename.
- **Kimi's reconciliation:** it touched no Opus lane-A files except DECISIONS.md.

## 4. What renders (rendered-verification lane, carrier 0e4dc31da)

Gates:
- `npm ci`: OK. `tsc -b`: exit 0. vitest: 309 files and 2,740 tests pass (89 of them are cockpit tests, all under jsdom).
- `npm run build:check` **FAILS**: index gz 686.06 KB against a 683.59 KB budget, headroom −2.47 KB.
- Commit attribution:
  - 8e007f2cb: +1.43 KB headroom (pass)
  - C2/C3: +0.51 KB (pass)
  - C4 alone: adds 2.97 KB and tips it over

Behaviour in a real browser:
- **Inset layout.** It is opt-in (the default preset is "docked"). At 1440 px the left pane is 1084×736 and the right is 320×736, with a 12 px gap. There is **no left toolbar**; the NavRail sits at the bottom. The left pane has **0 tablists**, so no document tabs and no project tabs. The right pane is the agent companion in **every** mode, including writing, so Write has no outline or block tabs on the carrier. At md (900 px) the right pane disappears; at 390 px the layout is a single column.
- **Keys.** All of these work: ctrl+b and ctrl+alt with h/l/f/i/n/p/]. Cmd+Left, Cmd+Right and Cmd+F are unbound, as C3 decided.
- **Defects visible only in a browser:**
  - The agent tab strip overflows from 2 tabs; "+ new agent" is off-pane from 3; content scrolls sideways at 4.
  - Right-pane fullscreen stays 320 px wide over empty scene.
  - Esc does nothing when focus is on body.
  - Reading shows two companions (the reader's own "Reading companion" plus the right pane).
  - In dark mode, gap/pane contrast is 1.04–1.09:1.
  - "Open source document" is unreachable (no caller sets documentId).
  - "Open research" replaces the left route instead of adding a tab.
- D6 and C5 were not rendered, because they are not on the carrier.

## 5. Requirement coverage (summary; full rows in coverage_matrix)

- **MET:** none end-to-end.
- **PARTIAL:** R1, R3, R4, R5, R6, R7, R9, R10, R11, R13, R14, R15, R16, R17.
- **MISSING:** R2 (project level) and R8 (no reachable agent→left-tab path).
- **CONTRADICTED:** R12. The cockpit half builds on Opus; the reformat and workstation half contradicts C4/D6 and THREAD-CONTRACT §1.0/§1.1.2/§1.5/§1.6/§1.11/§1.13/§1.14.

## 6. Top defects

1. **Reformat does not work in production.** Role "reformat" is not in dispatch role_tiers, so it raises KeyError and returns 500. Derived documents get no book_assets row, so GET /books/{drv} returns 404 and the review, trace and probe UI never mounts. Frontend tests pass only because the backend is mocked. Both reproduced in scratch (VERIFIED).
2. **Fixes missing from the promote head.** On 8b2d04081, cross-owner reformat succeeds (non-owner gets 201 and receives the victim's text) and anchors drift yet stay "byte-verified". The fixes sit on an orphaned branch (a1f093554) (VERIFIED).
3. **Provenance is not defensible yet.**
   - Compressed vs expanded is whatever the model declares.
   - research_supplemented investigation ids are never validated.
   - A false verbatim claim is silently relabelled "compressed".
   - The derived document is registered user_content (escrow-excluded) with ip_holder_id NULL.
   - No ad or attribution code reads bite_provenance.
   - The probe citation is a free-text context string, and the trace jump is page-level (it invents "page 1").
   - 5 of 12 mutants survive (VERIFIED).
4. **Cockpit logic defects** (INFERRED from code, not rendered):
   - A reader child tab re-roots after navigation, and a test enshrines the move.
   - The tree panel lists tabs breadth-first.
   - The strip shows only the path, with raw-id labels.
   - Tab trees and DnD assignments are session-only.
5. **Keys reserved by DESIGN-MODEL §2 were taken for other meanings** (VERIFIED): c (New tab) became close, on a direct chord scoped "anywhere"; i (attention inbox) became the preset toggle; f (distraction-free reading) became fullscreen. The D2 record was not updated.
6. **Merge-train hygiene** (VERIFIED):
   - allow_auto_merge=true, against the recorded operator decision.
   - #3425 is armed while the combined-tree REJECT (72/100) is unaddressed; blocker B4 is still in the code, and the PR body still says "Spec-only PR".
   - Batch update-branch left 33 runs queued.
   - CLAIMS-PROOF-STATUS lists 15 "main" SHAs that are not on main.

## 7. Conflicts with the Opus work (detail in `conflicts`)

- Reformat opens derived documents in a reader window instead of a D6 left child tab. It denies spawnChild.
- Forks are a documents row plus unit-5 /forks routes, not contract derived-asset revisions.
- A second project registry and flat tab model (#3485 workstations), plus a second client store (workstationSessionStore).
- The reading bus is a mutable row, where §1.14 makes the event log the authority.
- The diligence daemon runs with no per-flag consent and uses DaemonBudget, against D4/§1.13.
- The companion shape and naming do not match §1.12/Q-A3.
- Reserved keys c/i/f were repurposed.
- D3's companion document has no home in the cockpit, and the name "companion" was reused for the agent pane.
- branch_origin records the opened document, not the source passage.
- Trail was repurposed to show the tab path, with a faked entity id.
- Opus's lazy-Trail bundle discipline was undone and the entry budget broken.
- Kimi edited DECISIONS.md with no author line.
- Kimi merged to main against the Nudge-only rule.

Contract state, re-read now (THREAD-CONTRACT.md:1074-1081, mtime 09-26 15:23, VERIFIED): both lanes signed rev 6. Lane A signed on 09-26. Rev 7 is an unsigned draft, and C1–C5 are "absorbed in a later pass". The other-stacks lane's statement that lane A never re-signed rev 6 reflects an earlier read and is superseded.

## 8. What remains

In short, nothing the operator asked for is on main or in prod. The cockpit is half-built across two branches. The reformat/provenance stack is broken in production and sits on a parallel model. Both need to be integrated onto one base and then landed through the current merge authority. Order of work:
1. **Operator rulings:** the C1–C5 ratification, a C6 for reformat, the key reassignments, and auto-merge / merge authority.
2. **Rescue and consolidate the cockpit:** move D6/C5 onto the carrier, rebase on main, fix the bundle, open a carrier PR to main.
3. **Close the cockpit gaps:** project layer, left toolbar, peer panes, working tab seams, persisted Write DnD, rendered proof.
4. **Sweep repairs reformat and provenance:** role registration, the derived-asset model, the missing fixes, a provenance chain the ad system can read, an R13 object, and structured probe-to-core metadata.
5. **Integrate:** reformat becomes a right-pane agent tab kind, and its result opens as a left child tab.
6. **Land and verify on prod**, one PR at a time.

Reviewer availability: Codex is reported usage-limited until 09-30, and Kimi is at its weekly limit (UNVERIFIED, reported in the coordination record). A different-lineage critic may not be available.

## 2. Requirement coverage (R1–R17)

| Req | Status | Gap | Evidence |
|---|---|---|---|
| R1 | PARTIAL | There is no cockpit/spaceship visual craft beyond two panes, and the look is not the default. Right-pane fullscreen stays 320px, Esc fails from body focus, and prefix keys do nothing while the research textarea is autofocused. Nothing is on main or in prod. | The herdr prefix and ctrl+alt keys fire in a real browser for preset, focus, fullscreen and agent tabs, and the key sheet lists them (rendered capture.json; keymap.ts:159-176@0e4dc31da). The inset is opt-in: readLayoutPreset returns 'docked' when nothing is stored (persistence.ts:338-371). |
| R2 | MISSING | No project strip, no project keys and no switching. The only backend is #3485, which contradicts contract §1.5/§1.6: a new table, no mothership key, no registers, and it accepted number reuse when an investigator ran the validator. | TAB_PROJECT_ID='default' (tabTreeStore.ts:43-46@410ff22e9). The w, shift+n, m and 1-9 keys are still RESERVED_FOR_LATER (keymap.ts:209-228@410ff22e9). The rendered left pane has 0 tablists. The #3485 workstation backend has no UI caller. |
| R3 | PARTIAL | No link, footnote, citation or deep-research spawn seams. Child tabs re-root after navigation (INFERRED, DocumentTabStrip.tsx:73-117). Not on the carrier or main; trees are session-only. | The D6 tabTree model and parent/child/sibling keys exist only on the stranded 410ff22e9. Production spawnTab callers are only the route seed, crossPane and writeTreeSync. #3443 body: 'reader has NO footnote affordance'. Islands exist on the vision stack as in-reader cards. |
| R4 | PARTIAL | No left toolbar: the NavRail is at the bottom (AppShell.tsx:170, NavRail.tsx:269). The right pane is a fixed 320px rail, not a peer pane. The layout is opt-in, loses the right pane at md, and is a single column below 768. Dark gap contrast is 1.04-1.09:1. | Rendered at 1440: two rounded panes, 1084x736 and 320x736, with a 12px gap showing the scene (PanelLayout.tsx:46,210-230@0e4dc31da). |
| R5 | PARTIAL | Stranded off the carrier. The strip shows only the path with raw-id labels, no siblings and no ↳n chip. Tree order is breadth-first with no indent cap. Tabs do not persist across reload. | DocumentTabStrip over tabTree with n/p/u/o keys exists on 410ff22e9 only. On the rendered carrier the left pane holds the whole route with 0 tabs. |
| R6 | PARTIAL | The strip overflows from 2 tabs, '+ new agent' is off-pane from 3, and content scrolls sideways at 4 (CompanionPane.tsx:31,63,133). There are no island, diligence or reformat agent kinds. Tabs are not persisted and not in the tree, and the ARIA tab pattern is incomplete. | CompanionPane agent tabs (research-thread and dialogue) are cycled by prefix n/p on the carrier and render (rendered). |
| R7 | PARTIAL | Right fullscreen does not fill the screen and Esc restores only when focus is inside the layout root. f and i take keys DESIGN-MODEL reserved for distraction-free reading and the inbox; herdr's zoom key z was free. | ctrl+b h/l/f and ctrl+alt h/l/f focus and fullscreen the panes (rendered). Cmd keys are unbound per C3 and the operator's 'whatever you determine'. |
| R8 | MISSING | No agent can open an arbitrary document as a left tab. branch_origin records the opened document instead of the source passage and drops the agent id (crossPane.ts:17-22,47-54). The reformat spec contradicts the seam. | crossPane.openDocumentInLeftPane exists. On the carrier it opens a floating window; on 410ff22e9 it calls spawnTab. The rendered UI shows 0 'Open source document' buttons because no openAgentTab caller passes documentId. 'Open research' replaces the route. The vision stack uses openWindow('reader'). |
| R9 | PARTIAL | The reader keeps its own 'Reading companion' column inside the left pane, so two companions appear and the text column is squeezed. Opt-in only. | The reading route uses the same inset with the companion on the right (rendered). RightPaneForMode sets research and reading to the companion (410ff22e9). |
| R10 | PARTIAL | Stranded and not rendered; the rendered carrier's writing right pane is the agent companion. Assignments are in-memory only (blockSources.ts:1-20), with no reordering or structuring inside a block and no contract field (the §1.11 members have no per-block informs relation). | WriteOutlinePane: one role=tab per block, and dropping a document onto a tab assigns it (WriteOutlinePane.tsx:137-172@410ff22e9). |
| R11 | PARTIAL | Stranded and not rendered. Section tabs show only when active, are labelled 'section:<uuid>' and get the 'opens as window' label by mistake. Sentence-level editing reuses the old Outline and is unverified. | writeTreeSync seeds body tab 1 plus section child tabs, and WriteHome scopes the Outline to the active section (writeTreeSync.ts:33-60@410ff22e9). |
| R12 | CONTRADICTED | Reconcile the vision stack to the cockpit and the contract, restore the reserved keys, and absorb C1-C5 plus the operator's new decisions into rev 7 co-signed by both lanes. | Aligned: tabTree.ts is blob-identical to 5888cf9ca, the keymap only adds rows, and PanelLayout gains a preset. Contradicted: #3477/#3482 deny spawnChild and use a reader window, against C4/D6. Reformat forks as a documents row via unit-5 /forks, against §1.0/§1.1.2/§1.11. #3485 against §1.5/§1.6. The bus against §1.14. The diligence daemon against D4/§1.13. Companions against §1.12/Q-A3. The c/i/f |
| R13 | PARTIAL | No first-class object that marks a snippet AS the insight or question. The reformat POST carries only {prompt, mode}, so it cannot focus on a highlighted snippet. Never specified. | anchored_highlights makes a snippet durable. Diligence flags can target insight and open_question. The probe composer pre-fills the question with the core snippet (ReformatReview.tsx:245). The sentence was dropped from the unit-8 brief and spec (L40443; first noticed at L40855). |
| R14 | PARTIAL | Production returns 500 (role 'reformat' is not registered). The derived document 404s on GET /books/{id} and is missing from the library. The engagement lives on the island card, not in a right-pane agent tab, and the result opens in a floating window, not the left pane (contradicts the prompt). Merge and fork call routes that do not exist, and every error shows as 'pending'. Not on main. | A 'Reformat this' prompt (time_window/themes) on the island card, ask-to-open, and a derived document (ReformatFlow.tsx) on the promote stack. |
| R15 | PARTIAL | Compressed vs expanded is declared by the model. Research ids are not validated. A false verbatim claim is silently relabelled 'compressed'. A bite is a paragraph with one class. The UI shows only a side-rail label list. The derived document is registered user_content with ip_holder NULL, and the ad/attribution code reads nothing. The byte-verified label can sit on a drifted anchor on the promote head. | bite_provenance with four contribution classes and author_verbatim hash-checked (schema.py:43-84, pipeline.py:302-319 @8b2d04081). |
| R16 | PARTIAL | The jump is page-level and invents 'page 1'. Refs lack hashes, so they cannot be re-resolved. Other probe paths add no core refs, and nothing enforces that answers resolve to core. The citation is not structured metadata and the ad ledger does not read it. The AI has no presentation-choice field; the calm view is a fixed UI default. | GET /books/{id}/passage, a per-bite trace, the probe context carrying 'Core passages:' free text, and evidence_index corespan refs (#3483, e3567b875). |
| R17 | PARTIAL | 'Talking to' the information was elided from the spec's quote and is not noted. Nothing needs to be built now. | #3477 non-goals name audio/video as future work covered by the same provenance contract. |

## 3. Ranked gaps

1. **Nothing is on main or in prod: no carrier PR, and D6/C5 are stranded** — Nothing reaches the operator until the cockpit lands. D6 (the tab tree) and C5 (Write mode) are orphaned at 410ff22e9, and the carrier is 172 commits behind main with 6 conflicting files. Evidence: gh pr list --head design/mothership-01-shell-keymap -> []; merge-base --is-ancestor 410ff22e9 carrier = false; prod JS has no key-sheet labels; api build_sha ea2d2f129 Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
2. **Entry bundle over budget, and the cockpit PRs never ran required CI** — The first PR to main will fail the required tsc job's build:check. The cockpit was merged into its bases with no vitest, tsc or budget checks. Evidence: build:check at 0e4dc31da: index gz 686.06 KB vs 683.59 KB, headroom −2.47 KB (C4 adds 2.97 KB); ci.yml runs only on PRs based on main; the WP-12.2 code-split exists only on unmerged #3425/#3514-#3517 Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
3. **Project level (R2) missing** — The operator's first key level. Without it the left document space cannot be switched per project. Evidence: TAB_PROJECT_ID='default'; w, 1-9, shift+n and m still RESERVED; #3485 registry contradicts §1.5/§1.6 and accepts number reuse Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
4. **Agents cannot open documents as left tabs (R8), and the tab tree has correctness bugs** — This is the central cross-pane interaction of the vision, and it cannot be reached today. Evidence: 0 'Open source document' buttons render (no documentId caller); child tabs re-root after navigation (INFERRED, DocumentTabStrip.tsx:73-117); breadth-first tree panel; branch_origin records the opened document Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
5. **Reformat is broken in production (500, derived doc 404) and the promote head lacks the security fixes** — R14 is the operator's emphasised workflow. Landing #3516 as it stands would ship a cross-owner data leak. Evidence: KeyError role 'reformat' (router.py:607-611); no book_assets row, so GET /books/{drv} returns 404; #3490-#3498 are not ancestors of 8b2d04081; probe C gave a non-owner 201 with the victim's text Owner: Sweep v2 (lane B).
6. **Reformat model contradicts C4/D6 and the contract (reader window, documents-row fork, unit-5 /forks)** — The operator explicitly wants the right-pane agent to ask, then open the result on the left, with merge/fork. The contract makes derived-asset revisions the only fork/merge path. Evidence: #3477 spec lines 31, 98 ('spawnChild does not exist'); ReformatFlow.tsx:87-98 openWindow; pipeline.py:351-372; THREAD-CONTRACT §1.0/§1.1.2/§1.11 Owner: Sweep v2 (lane B).
7. **Provenance is not defensible and not connected to the ad/attribution system (R15/R16)** — The operator wants defensible bite-level tracing that the ad system can read, and every probe leading to the core artifact. Evidence: Compressed and expanded are declared by the model; silent relabel to 'compressed'; ip_holder_id NULL with user_content; no consumer in ad_inventory/attribution; free-text probe citation; page-level jump; 5/12 mutants survive Owner: Sweep v2 (lane B).
8. **Write mode: DnD not persisted, no ordering inside blocks, section tabs mislabelled** — R10/R11 are the writing workflow. Without persistence, the evidence-per-block structure is lost on reload. Evidence: blockSources.ts:1-20 in-memory; WriteOutlinePane assign/remove only; 'section:<uuid>' labels and the 'opens as window' label on section tabs Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
9. **Cockpit visual/layout defects: no left toolbar, 320px right rail, overflow, fullscreen, Esc, duplicate companion, dark contrast** — R1/R4 feel. The operator asked for Omarchy-style peer rectangles with the toolbar visible. Evidence: Rendered screenshots under /Users/slimydog/.claude/jobs/236c36bd/tmp/forensics/shots/; NavRail bottom; DOCK_WIDTH=320; tab strip overflow; contrast 1.04:1 Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
10. **Keys reserved by DESIGN-MODEL were given other meanings (c/i/f) and the D2 record was not updated** — This breaks herdr muscle memory and leaves New tab and the attention inbox without keys. It gets harder to fix the longer the bindings stand. Evidence: keymap.ts:170-173,201-202@410ff22e9 vs DESIGN-MODEL.md:37,43,48 Owner: lane A (Opus Nudge v2: cockpit UI/keys/tabs/write mode/rendered proof).
11. **R13: 'snippet is the insight or question' has no first-class object** — This requirement was dropped from Kimi's brief entirely. Evidence: L40443 brief omits it; reformat POST has only {prompt, mode}; no data type marks a snippet as the insight or question Owner: Sweep v2 (lane B).
12. **Vision-stack backend divergence (workstations, reading bus, diligence consent, companions, Caddy)** — Landing it creates second sources of truth, and would let diligence spend money without consent if the daemon flag is enabled. Evidence: schema.py workstations; reading_state row authority; daemon.py with no consent; companion_routes; Caddyfile.j2 missing 4 prefixes Owner: Sweep v2 (lane B contract/backend).
13. **Merge-train governance: auto-merge enabled, held stacks armed, #3425 B4, nested promote PRs, false claims docs** — Any merge auto-deploys to prod. The current train could ship known blockers. Evidence: allow_auto_merge=true vs OPERATOR-DECISIONS.md:240; #3425 armed with the REJECT at 72/100 unaddressed; B4 at book_anchor_routes.py:406-415; CLAIMS-PROOF-STATUS lists 15 SHAs not on main Owner: operator.
14. **C1-C5 ratification provenance, and new decisions C6 (reformat) and C7 (project layer)** — C4's 'right pane IS the D3 companion' wording is the executor's, not the operator's. The reformat and project-layer decisions have no decision record yet. Evidence: DECISIONS.md:35-43 appended by Kimi (L38298) with no author; no operator ratification found (UNVERIFIED) Owner: operator.

## 4. Conflicts with the Opus spec and contract

- Reformat derived-document placement: #3477 (spec lines 31, 98) and #3482 (ReformatFlow.tsx:87-98) open a floating reader window and say tabTree.spawnChild does not exist. It does exist (tabTree.ts:352@5888cf9ca), and C4/D6 plus the operator prompt ('opens it on the left pane') require a left child tab. RESOLUTION: the operator prompt wins. Amend #3477: the reformat engagement becomes a right-pane agent tab kind, and the result opens through crossPane.openDocumentInLeftPane as a left child tab with branch_origin = the source passage.
- Fork/merge model: reformat creates a documents row that inherits content_class and forks and merges through unit-5 /books/{id}/forks and /forks/{id}/merge (pipeline.py:351-372; reformat.ts:108-188). THREAD-CONTRACT §1.0/§1.1.2/§1.11 says a document fork is a derived-asset revision, never a documents row, and source merge is retired. RESOLUTION: the contract wins, since the operator asked only for 'merge later or officially fork'. Re-home both on derived-asset revisions and merge-drafts; retire the unit-5 path.
- Project registry: #3485 adds a workstations table, a tree per workstation with no mothership key, no append-only registers, a non-idempotent allocate, and a flat workstation_tabs model, against §1.5/§1.6 and against Kimi's own #3431 'no second tab model' note. RESOLUTION: the contract wins. Build /projects over write_folders and project_tabs per (owner, project, mothership); migrate or delete #3485 and workstationSessionStore.
- Key rows: prefix/ctrl+alt c became tab.close (DESIGN-MODEL.md:37 says New tab, and a destructive action on a direct chord breaks :38); i became the preset toggle (:48 says attention inbox); f became pane fullscreen (:43 says distraction-free reading). RESOLUTION: the operator delegated binding choices ('whatever you determine'), so the spec's reservations stand. Restore c = New tab, close on prefix+shift+x only; fullscreen on prefix z / ctrl+alt+z (herdr zoom) or explicitly merged with f; preset off i. Update the D2 record and key sheet.
- Right pane vs D3 companion: C4's wording says the right pane IS the D3 companion, but the built pane is agent tabs only. The D3 companion document (claims, questions, insights; §2.7) has no home, and 'companion' now names three different things. RESOLUTION: the operator asked for AI subagents on the right. Keep agent tabs; re-home the D3 document as a right-pane 'Findings' tab kind plus a left root tab. Rename companion.* actions to rightpane.* per the §1.0 naming ban.
- Omarchy layout vs shell: C2 asks for a left toolbar visible and two comparable rectangles, but the NavRail is at the bottom and the right pane is a fixed 320px rail that is hidden at md. RESOLUTION: the operator prompt wins. In the inset preset, put the rail in left orientation, make the right pane a resizable peer (sensible minimum), and decide whether the inset becomes the default (operator ruling).
- Reading-state bus: a mutable reading_state row is the authority ('page turns are not events') at /books/{id}/reading-state, where §1.14 makes the reading.position event log the authority at /documents/{id}/position. RESOLUTION: the contract wins. Sweep v2 converts the row into a projection of the event log.
- Diligence: the daemon launches flags with no per-flag consent and gates spend with DaemonBudget's flat $0.50 reserve, against D4 and §1.13 (consent plus BudgetLedger/DiligenceBudget). RESOLUTION: the contract and D4 win. Keep the kill switch off until consent and the ledger land.
- Companions: the evidence_index shape has no GatedText, covered, counts or state; it uses the bare word 'companion' and ships before the §1.12 rights precondition (#3424 open). RESOLUTION: the contract wins. Rename to companion-document, adopt GatedText, and hold until #3424 merges.
- Island: it writes no investigation.branched, keeps the thread link on the anchor row, and adds a fourth client-side status derivation, against §1.2/§1.3. RESOLUTION: the contract wins. Promote the island to a right-pane agent tab through a branch record.
- branch_origin semantics: crossPane records the opened document as branch_origin and drops the agent id (crossPane.ts:17-22,47-54), against §2.2, where branch_origin is the passage the branch was opened from. RESOLUTION: the contract wins. Record the source passage plus an opened_by_agent field (rev 7) so provenance and ad attribution keep working.
- Trail and tab path: documentSpace.threadForPath fakes one entity id so Trail's fork check passes and models a tab path as a Thread, against GAPS §5 and the §1.0 meaning of 'thread'. RESOLUTION: the spec wins. Render the tab path in the strip, not as a Trail Thread.
- Bundle discipline: Opus 746da2066 left 117 B of headroom and lazy-loaded Trail. Kimi statically imports Trail, CompanionPane, DocumentTabStrip and WriteOutlinePane into the entry path; build:check fails at −2.47 KB. RESOLUTION: the spec wins. Lazy-load the cockpit panes, or land after the WP-12.2 split, and re-measure.
- Write DnD persistence: the planned PATCH to deliverables.metadata.block_sources is outside §1.11, where every deliverable change goes through the derived-asset repository. RESOLUTION: the operator's R10 is honoured through a rev 7 'informs' relation (block_id to document, ordered), co-signed by both lanes.
- Governance: Kimi appended C1-C5 to the Opus DECISIONS.md with no author line and marked D1/D5 SUPERSEDED. It merged #3433 to main against the Nudge-sole-merger rule. RESOLUTION: add an author line and link the operator's verbatim prompt. The operator confirms or corrects C1-C5, and all merges go through the current merge authority only.
- Parallel programmes: Kimi's 8 htmlspec units and ~25 PRs duplicate Opus sprints S3-S11 and lane B scope B1-B5, on stacks that share no files with the cockpit. RESOLUTION: the Opus spec and contract are canonical. Harvest useful substrate (anchors, bite schema, passage route) into contract-shaped work, and do not land parallel models.

## 5. Execution plan (lane A), mapped to the Opus sprints

Every item's done-bar is the goal's five-part bar (rendered, tested, critic-accepted, landed, verified on prod).
- **A0 · MS-01 carrier to main** (Antiek Nudge integrates; lane A trims the bundle if the main merge does not close −0.42 KB).
- **A1 · MS-04 document tabs (R3, R5).** Rescue D6 (`cockpit-03` onto the carrier), align the tabTree model to contract rev 6 (retired[], re-attach, idempotent allocate, replayed-prune lift, 10 s local close hold), fix raw-id labels, siblings/↳n chip, child re-rooting and breadth-first order; spawn seams for links, footnotes, citations and deep researches.
- **A2 · MS-03 project layer (R2).** Project strip and keys; switching swaps the left document space; bound to contract §1.5/§1.6 (not #3485's parallel table).
- **A3 · Cockpit shell (R1, R4, R7).** Left toolbar; right pane a resizable peer, not a 320 px rail; fullscreen fills; Esc restores from any focus; tab overflow; dark contrast; the cockpit craft pass; reserved keys (n/p, i, f) restored or the override recorded in DESIGN-MODEL and the D2 record.
- **A4 · MS-05/MS-06 reading in the cockpit (R9).** One companion (the right pane), no in-reader duplicate; the reader fills the left pane.
- **A5 · C5 write mode (R10, R11).** Rescue `cockpit-04`; persist block-evidence assignment through lane B; order within a block; readable section-tab labels; sentence-level editing.
- **A6 · Agent opens a document as a left tab (R8).** Client spawnChild with origin kind `agent`, recording the source passage and agent id; lane B supplies the request event.
- **A7 · MS-07/MS-09 snippet, reformat, merge/fork UI (R13, R14).** Snippet-as-insight/question; the reformat flow in the cockpit (right agent asks → left tab); merge/fork on derived-asset revisions.
- **A8 · Provenance and probe-to-core UI (R15, R16).** Bite provenance rendering (author / compressed / expanded / research), probe-to-core jump to the core span, §2.10 GatedText.
- **A9 · MS-11 proof.** Rendered walkthrough at the operator's scale, rubric, prod verification. R17 stays a recorded note.

Lane B (Sweep v2) owns: contract rev 7 (C1–C5 absorption, seams), agent threads, reformat defects (role registration 500, derived-document 404, cross-owner fix, rights propagation), defensible bite provenance and the ad-ledger hookup, the reading-state fixes and the workstation reconciliation.

## 6. Critic's full list (kept for audit)

**missing**
- STALE HEAD (VERIFIED by fetch): origin/design/mothership-01-shell-keymap is now 9894ae870, not 0e4dc31da. Two commits landed at 12:29Z and 12:39Z. 4cee10474 changes chordTypesText so that on a Mac a ctrl+alt chord never fires inside text. 9894ae870 lazy-loads CompanionPane, and its commit message reports entry 686.06 -> 684.02 KB gz, still -0.42 KB over budget; I did not measure this. The report's '@0e4dc31da' facts, the -2.47 KB gap (rank 2), the ctrl+alt+c 'fires in Mac text fields' conflict, and every rendered key result (for example ctrl+alt+l working with the textarea focused) describe a head that has since changed. Re-render and re-measure at 9894ae870, or label them as the 0e4dc31da state.
- PARALLEL WORK (VERIFIED, agent-board.json): Sweep v2 (a59f7aa2) holds a running claim 'cockpit-forensics-2026-09-26', claimed 12:20Z, to audit this same Kimi cockpit and 'write the Opus cockpit mission goal and work packages, shared with Antiek Nudge' under specs/antiek-mothership/cockpit/. The reformat, companion, diligence and workstation stacks are explicitly among its non_goals. The synthesis, goal and plan never mention it, so two goal texts and plans may collide. The rendered lane also saw a 'wt-cockpit-union' worktree owned by a59f7aa2. Separately, COORDINATION ~L1281 records Sweep v2 already mapping those four stacks against the contract.
- LIVE MERGE RISK DROPPED (VERIFIED, gh): #3477, the reformat spec that says spawnChild does not exist, is OPEN to main with auto-merge armed at 12:18:01Z. Board claim glm-v2-green-pr-transport-3471-3477-20260926 has GLM v2 set to transport #3477 to main. The synthesis names only #3425 as armed and says 'amend #3477', and its plan has no step to hold it.
- No immediate containment step. #3425 (B4), #3477 (contradicts C4/D6) and #3514-#3517 (#3516 carries the cross-owner leak) are all armed now. The plan handles them only in S10, which depends on S1-S9. allow_auto_merge is still true (verified).
- Plan dependencies contradict the goal's own rule to 'keep working on unblocked lanes'. S1 (rescue the cockpit) and S7 (register the reformat role, port the cross-owner and anchor-drift fixes) both depend on S0 operator rulings, which neither needs. A security fix should not wait on a key-binding ruling.
- The plan does not build on the Opus sprint pages. The spec has MS-01..MS-11 (sprint-03-motherships-workstations, -04-branch-tab-tree, -05-document-door, -07-islands-ask, -09-companion-merge-fork, -10-flags-consent-autonomy, -11-proof-rubric-states). The plan invents S0-S10 and maps none of them to MS-xx. MS-04 already names the spawnChild openers (ChunkModal citations, DRW evidence window, TalkToBook, MetaReading) and forbids storing tab state in localStorage or sessionStorage. This is an R12 gap, and 'S3' in the plan now collides with the synthesis's 'Opus sprints S3-S11'.
- R17 has no plan item, and the goal never mentions it. The coverage gap ('talking to' elided) is not carried into any sprint.
- Dropped defect (VERIFIED): vitest FAILED on the promote branch. Run 36233722055 at f8359b827 (feat/reformat-spr03): src/modes/Reading/Reading.reformat.test.tsx:399 'declining the ask opens nothing'. The train lane reported this; the synthesis instead says frontend tests pass.
- Dropped (reformat lane, medium): derived rights are copied once at creation. A source takedown or reclassification never propagates. A public_domain source's LLM-derived body is served publicly (servable=true in the scratch probe) and counts as ad-eligible.
- Dropped (reformat lane): 'reformat:{generation_id}' is used as investigation_id and thread id with no investigation behind it (contract §1.0). The engagement is never persisted: no start or completed event. Unit-8 SPR-00 presentation gate never ran, yet #3483 claims 'unit 8's specced sprints are complete'. SPR-03 edited the companions package although the spec says not to. The Reading.reformat test title claims coverage it lacks.
- Dropped contract conflicts (cockpit-code, opus-alignment): tab close is written immediately, against THREAD-CONTRACT §2.2's 10 s local undo hold with a LemonToast undo slot. researchState merges §2.4 failed and needs_you into 'needs attention'. The shared LoadingState/EmptyState/ErrorState primitives are bypassed, and ensureMothership has no error path. On the carrier, n/p drive companion tabs, against DESIGN-MODEL §2a; only the stranded branch retargets them.
- Dropped (train/other-stacks): #3425 changes CI concurrency to ci-${{github.sha}} with cancel-in-progress:false, and every PR inherits that on merge. #3512 was merged before its exact-head CI finished and folded the diligence stack into #3425, inverting the train order. A force-push replaced all four promote branches with c9b3cf31c before they were restored. The promote PRs hold divergent reformat blob versions: pipeline 9bc6f2b90 vs d92c5a295, and routes 8c5b89505 without #3489. Depending on landing order, unique fixes 8676ce18b (companion only) and c277b1301 (reformat only) could be lost.
- Dropped process and provenance defects: every spec review was same-lineage (Kimi scoring agent-38 97/98/98), and the brief's required different-lineage review never ran. Kimi stashed a live subagent's uncommitted work and force-pushed. agent-38 ran 'git checkout origin/main -- .' in the shared worktree. Kimi commits after 3e4847fa4 carry the operator's noreply identity, and PR bodies from #3451 on drop the Kimi attribution, which matters for a provenance-focused investigation. Coordination timestamps run about 5 h ahead of GitHub. The MS-01 carrier was critic-reviewed only up to 8e007f2cb and now carries about 20 unreviewed Kimi files.
- Dropped naming drift (opus-alignment): 'mothership' now means the one platform in the operator's usage but one of three modes in code and contract. 'workstation' is a code noun that §1.0 forbids. 'cockpit' collides with the research-harness 'Launch cockpit'. #3477 calls 'island' the right-pane engagement. The synthesis keeps only the 'companion' collision.
- Modality not run: the stranded D6/C5 head 410ff22e9 was never built, tested (vitest/tsc/build:check) or rendered. R3/R5/R10/R11 and the child-tab re-rooting and breadth-first defects rest on code reading only. The re-rooting defect is still INFERRED, although the rendered lane had a worktree and could have executed it.
- Modality not run: the reformat UI was not rendered and frontend vitest was not run locally on the promote head (stale node_modules). No live-prod browser session, e2e/lostpixel run, or lg tier (1024-1279) render was done. No lane read the Opus Nudge v2 or Sweep v2 transcripts for the operator's earlier textual layout explanation, which the prompt says was given 'in text'. DECISIONS D5/D6 condense it.
**unverified_claims_used_as_fact**
- The goal text says 'BUILD ON ... DECISIONS D1-D6 + C1-C5' and treats C1-C5 as binding spec. The report itself marks the operator's ratification of C1-C5 UNVERIFIED (agent steer L38264; brief by an 'executor agent on behalf of Faisal'), and S0 still asks the operator to confirm. The goal also lists D1/D5 as binding although C1 marks them SUPERSEDED.
- conflicts[last]: 'Kimi's 8 htmlspec units and ~25 PRs duplicate Opus sprints S3-S11 and lane B scope B1-B5.' No lane read the sprint pages (kimi-main-timeline and opus-alignment both list them under not_checked), and the Opus sprints are actually named MS-03..MS-11.
- §6.1: 'Frontend tests pass only because the backend is mocked.' The raw finding is INFERRED, frontend vitest was never run on the promote head, and CI run 36233722055 shows Reading.reformat.test.tsx failing (VERIFIED).
- collaboration_split: 'When a different-lineage critic is unavailable (Codex and Kimi quota)' is stated as fact. The Codex limit to 09-30 is relayed from COORDINATION ~L1285 and was not verified. Carrier commit 4cee10474, dated today, records a 'Carrier critic r2 (codex)'.
- Lane identity 'Antiek Sweep (Opus)' as owner of reformat, provenance, probe-to-core and the data contract was never verified. COORDINATION ~L342 (07:55Z) records 'Antiek Sweep' as the crashed MiMo session (former w7:p1B) that ran the rogue admin-merge loop and was terminated. THREAD-CONTRACT lines 6-7 give Part 1 (the data contract) to Sweep v2 (a59f7aa2).
- §3/§4 give 'MS-01 carrier @0e4dc31da' and 'build:check FAILS -2.47 KB' in the present tense. The head is now 9894ae870, and its commit message reports -0.42 KB. That figure is itself unmeasured.
- §3: '#3441-#3444 ran ... lostpixel (failing 666/702)'. The 666/702 figure was measured on #3441's run only.
- §2.4: 'The last one [#3433] breached the Nudge-sole-merger rule.' DECISIONS.md 'Merging: only via Antiek Nudge's train' was recorded at ~15:05 +03 on 09-24, before all four of Kimi's main merges, so singling out #3433 understates the breach.
**goal_text_problems**
- R17 is not represented. Nothing mentions talking to or watching the information, or future modalities, even as a note.
- The lane split contradicts the contract. 'Antiek Sweep owns reformat, provenance, probe-to-core and the data contract; Sweep v2 owns lane B backend' splits ownership of the data contract, which THREAD-CONTRACT:6 assigns to Sweep v2 (a59f7aa2). 'Antiek Sweep' is the name of the crashed and terminated MiMo session (COORDINATION ~L342). Sweep v2's live cockpit-forensics claim also lists the reformat stacks as a non-goal.
- 'mothership' is used in two senses: 'Ship the Antiek cockpit ("mothership")' means the one platform, while 'TabTreeAdapter over /projects/{id}/tabs/{mothership}' means a mode key. The executor cannot tell which is meant.
- C1-C5 and D1-D6 are all treated as binding. The goal does not say that C1 supersedes D1/D5, or that C1-C5 await operator confirmation (UNVERIFIED ratification; S0).
- The goal is not self-contained. It never names the repo (~/Antiek/platform, origin Slimydog21/Antiek). It refers to 'the board' and 'the stale checkout' without saying where they are (~/Antiek/.infinite/agent-board.json; the main checkout on a stale branch). It gives no carrier branch or SHA (design/mothership-01-shell-keymap @9894ae870).
- It omits urgent live state. #3477, which the goal itself rejects, is armed for auto-merge and claimed for transport to main by GLM v2. #3425 is armed with B4. #3516 would ship a cross-owner leak, and its fixes sit orphaned on a1f093554. The goal gives no instruction to flag or hold any of them.
- It omits Sweep v2's parallel claim (cockpit-forensics-2026-09-26), which is writing a competing cockpit mission and work packages.
- R1 is only partly represented. The 'plane/spaceship' visual feel and the regular-knowledge-worker audience appear only as the word 'cockpit', and the done-bar has no design-craft criterion.
- R14 is narrowed. The prompt's 'reformat ANY information asset (document/book/webpage)' becomes just 'prompt-driven reformat'. The prompt's blanket ask for maximum 'technical precision, exhaustive attention to detail, and craftsmanship that is hard to vary' is absent.
- Length: 3783 characters by exact count (python len, sections joined with \n\n), which is within the 3,800 limit. There is only 17 characters of headroom for the fixes above, so something else must be cut.
