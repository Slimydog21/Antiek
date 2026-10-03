# Operator walkthroughs, lane A

**Why this file exists.** The operator's prod-verification ruling (DECISIONS, 2026-09-26) says agents verify prod read-only: `build_sha` equals the merge SHA, plus GET probes. Flows that write are driven by the operator from a short checklist per sprint, which lane A writes. A sprint counts as verified on prod only when both are done.

**How to use it.**
- Run each checklist on https://antiek.ai after the sprint's merge SHA shows on `https://api.antiek.ai/health` as `build_sha`.
- Tick a box, or write what you saw next to it. Anything that differs is a defect; lane A fixes it red-first.
- Use a real project, not a demo one.

A10–A24 checklists are in `SPRINTS-LANE-A-A10-A24-2026-09-27.md`, one per sprint. They are copied here as each sprint lands.

---

## A0 · The MS-01 shell and keymap carrier

**Agent-side check.** `build_sha` equals the carrier's merge SHA. `GET /` and the entry chunk answer 200.

**Walkthrough.**
- [ ] **The prefix.** Press the prefix, then `?`. The key sheet opens and lists the cockpit keys. Esc closes it.
- [ ] **Keys inside text.** Type in any text box, including `h`, `l`, `f`, `i`, `[` and `]` on a Mac while holding ctrl+option.
  - The characters appear in the box (˙ ¬ ƒ and so on with option).
  - No pane changes, and nothing goes fullscreen.
- [ ] **Keys outside text.** Click an empty part of the page (outside any text box), then press ctrl+option+h and ctrl+option+l. Focus moves between the panes.
- [ ] **The agent pane.** It appears after a moment with "Loading agents…", never as a blank space.

## A1 · Document tabs and write mode in the cockpit (MS-04, C5; R3, R5, R10, R11)

**Agent-side check.**
- `build_sha` equals A1's merge SHA.
- The GET probes of `/projects/{id}/tabs/research|reading|writing` answer 200, or 404 before LB-2 lands. They are never 5xx.

**Walkthrough.** Each step names what to look for.

Tabs and branches:
- [ ] **Open a research project.** The document tabs run across the top of the left pane, and their labels are titles, never ids.
- [ ] **Branch from a footnote.** Follow a footnote or link in a document. A new tab opens as a child of it, with a small "↳" mark.
- [ ] **Move between tabs.** Press the prefix then `n`, then the prefix then `p`. You move between tabs in the pane that has focus.
- [ ] **Back to the parent.** Press the prefix then `u`. You are back at the exact passage the branch came from.
- [ ] **Close a tab.** Press the prefix then shift+x.
  - The tab closes, and "Undo" shows for about 10 seconds.
  - Undo brings it back in the same place with the same number.
- [ ] **Reopen after the undo window.** After Undo has gone, press the prefix then shift+t. The last closed tab comes back.
- [ ] **Close the last tab.** Close every tab in the pane. You land on that mode's home, and Undo brings the tab back.
- [ ] **Reload.** Reload the page. The same tabs come back in the same order, and the same tab is active.

Panes:
- [ ] **Fullscreen.** Press the prefix then `f`.
  - The focused pane fills the screen, and a "Fullscreen · Esc" chip shows.
  - Esc returns to two panes, with nothing reloaded and no draft lost.
- [ ] **One Esc at a time.** Open a dropdown or menu while fullscreen, then press Esc once. Only the menu closes, and the second Esc leaves fullscreen.
- [ ] **Agent tabs.** Focus the right pane (prefix, then `l`). Now `n`, `p` and shift+x act on the agent tabs, and never close a document on the left.
- [ ] **The layout switch.** Press the prefix then shift+i. The layout toggles between the inset and the docked layout, keeping the route and any draft.

Reading:
- [ ] **A book in the left pane (1024×768 window).** The text is readable, not a thin column.
  - A "Contents" button opens the chapter list over the page, and picking a chapter or pressing Esc closes it.
  - The reader's own side column is hidden, because the right pane serves that role.
- [ ] **The shelf.** Opening a book from the home shelf opens it as a new top-level tab, not as a branch.

Writing:
- [ ] **Switching sections.** Open a piece in Writing, type into section 1, and switch to section 2 before pausing. Switch back.
  - Your typing is still there.
  - Nothing says it failed to save.
- [ ] **Block tabs.** The right pane shows one tab per block. The block tabs cannot be closed.
- [ ] **Reload.** Reload. The text you typed is still there.

**Anything that fails** goes to lane A with the step and a screenshot.
