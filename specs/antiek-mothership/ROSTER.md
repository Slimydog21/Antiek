# Lane A sprint roster (draft for index.html) — 2026-09-24

- **Branches:** `design/mothership-<nn>-<slug>`.
- **Merging:** only through Antiek Nudge's train.
- **Base:** every sprint that touches the shell stacks on the unmerged design chain, W1 tokens → W3
  shell/states/prose (which contains W1 `7144b8e6b`) + W7 crashes. Those branches touch the same files
  (AppShell, shell/*, PanelLayout, tokens), and building beside them would mean rewriting them.
- **Budget:** every sprint keeps the entry chunk under the 700 KB gz budget. New surfaces are lazy.
  After W7, headroom is about 3.4 KB; W3 alone leaves 60 B.

| Sprint | Wave | Goal | Depends on | Lane B needs |
|---|---|---|---|---|
| **MS-01 Shell stabilisation + one keymap** | 0 | Fix F1–F5 and F9. ONE keymap dispatcher and ONE table: herdr prefix (`ctrl+b`, configurable) + `ctrl+alt` chords (D2), rendered as a key sheet (`prefix+?`) and as `aria-keyshortcuts`. Migrate every existing binding. Rename ThreadBreadcrumb → Trail. Record in `docs/decisions` that D2 supersedes SPR-08's no-leader rule. | W1+W3 (+W7) chain | none |
| **MS-02 Craft carry-over** | 0 | Land the design chain in the train (W7 → W1 → W3 → W5). Finish W2 controls, W6 visual gates (the dark lostpixel axis) and W4 copy; the design workflow resumes them. | W1+W3 | none |
| **MS-03 Motherships + workstations chassis** | 1 | `/w/:workstationId/{research\|writing\|reading}/…` routing; the mothership switch keeps the workstation. Also: open-workstations list, switcher (`cmd+K` / `prefix+g`: workstations, tabs, documents, threads), shell sidebar, attention-inbox surface (#3078 P0 + #3088/#3092 P1/P2), and a local-first session with server sync when B lands. | MS-01 | workstation registry; session store; thread-by-owner/state list |
| **MS-04 Branch tab tree (the signature)** | 1 | Tab tree model and UI: path header, sibling strip, tree panel (virtualised at 174+ tabs), hierarchical numbers, `prefix+u/o/n/p/t`, prune / close-only with undo. Scale-tested. | MS-03 | server-side tab tree per account (contract 2.2) |
| **MS-05 One document door + reader pane** | 1 | `openDocument(id,{where,at})` and `openEvidence()` for every door (antiek-reader plan). Reader as a docked pane in Research and Writing. Citations, claims and source cards open in place. | MS-03 | serve non-book documents (F8); durable position |
| **MS-06 Reading mothership** | 2 | Reading home (continue / to-read / new). Kindle-grade reader (page keys, progress, distraction-free, prose layer). Footnote, reference and citation → child tab. Resume. | MS-04, MS-05; §7 of GAPS | to-read flags (intent read, actor); reading workstation kind |
| **MS-07 Islands + ask** | 2 | The Island primitive (IslandStore decouples it from the DOM selection; reading-physics anchoring; hinge physics; 390 px bottom sheet). Model picker, estimate, streaming and honest failure, kept/promoted. AskComposer with attachable context. Converge FloatMenu Dialogue, ChaseThread and the Write island. | MS-05; contract signed | thread continuation; text-quote locator; stream; estimate |
| **MS-08 Threads UX** | 3 | Per-document list (rail + margin marks) and per-workstation list (Threads tab + sidebar). Ask-this-thread composer. Merge flow (select → preview → conflicts → accept). Process tab on every thread kind. | MS-07 | GET threads by document/workstation; continuation; merge entity |
| **MS-09 Companion + merge-into-document + fork** | 3 | Companion tab (project) and rail (document) (D3). "Merge into…" flow. DiffReview (per-hunk accept or discard). Fork chip + lineage. | MS-08 | derived companion; merge-proposal; fork repository |
| **MS-10 Flags, consent, autonomy, inbox** | 3 | Flag actions (read / diligence) on passages, claims, questions and insights. Consent sheet (model, estimate, remaining cap). Autonomy settings (daily cap). Inbox items. "Keep digging". | MS-03, MS-08 | flag entity; consent event; cap ledger; daemon SpawnFn; `chase_mode` |
| **MS-11 Proof: rubric re-score + state matrices** | 3 | Independent rubric re-score (target ≥ 87.5%, no veto). Stories for every state of every new surface in both themes at 1280 and 390, on the lostpixel dark axis. Rendered walkthrough of the operator's day (the herdr-scale fixture: 20 workstations, 174-tab branch tree). | all | none |
