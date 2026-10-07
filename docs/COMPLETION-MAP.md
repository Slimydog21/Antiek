# Completion map

**Generated 2026-10-07 14:59 UTC from live state.** Regenerate with `python scripts/completion_map.py` - do not hand-edit.

- `origin/main` = `e5e27fe6210e1f732bbabaf57f1498d5075dd102` - *Merge pull request #3666 from Slimydog21/fix/alert-delivery-honesty-20261003*
- production API `build_sha` = `7e6366dda9c9` - **11 commits behind main** - the backend deploys automatically once a gating workflow finishes, so this gap is merge latency, not a missing deploy step
- open pull requests: **71**
- measured grade against the frozen rubric: **68.0 / 100**

This file answers one question: **what is actually done, as of the sha above?** It exists because nothing in this repository previously said so, and a returning agent could not tell measured work from intended work.

Every claim below carries one of the frozen rubric's evidence classes. `REPORTED` never becomes `DEPLOYED`. `MERGED` is only claimed when `git merge-base --is-ancestor` proves the commit is on main.

## How the score is computed

Each dimension is scored out of 100 against a fixed 100-condition. The operational partial-credit rule, adopted so every round's number is comparable: **five checkpoints per dimension, 20 points each, credited only when reproduced at the stated evidence level. Partial reproduction earns zero, not ten.** A score is only comparable to another score taken under the same conditions - which is why this file records the conditions, not just the number.

Weights sum to 100: R1 and R2 carry 12 each; R6 carries 14 (the heaviest, because execution is where intention and reality diverge); R3, R4, R5, D7 and D8 carry 10 each; D9 and D10 carry 6 each.

## Score by dimension

| # | Ref | Dimension | Weight | Score | Weighted | Evidence class | Measured |
|---|---|---|---:|---:|---:|---|---|
| 1 | R1 | One cockpit, one core asset | 12 | 80 | 9.6 | VERIFIED LIVE | 2026-10-04 |
| 2 | R2 | Keyboard-first operation | 12 | 60 | 7.2 | VERIFIED LIVE | 2026-10-04 |
| 3 | R3 | Omarchy insets | 10 | 80 | 8.0 | VERIFIED LIVE | 2026-10-03 |
| 4 | R4 | Pane semantics | 10 | 80 | 8.0 | VERIFIED LIVE | 2026-10-03 |
| 5 | R5 | Writing shape | 10 | 60 | 6.0 | VERIFIED LIVE (LOCAL) | 2026-10-07 |
| 6 | R6 | Execution | 14 | 80 | 11.2 | VERIFIED LIVE | 2026-10-04 |
| 7 | D7 | Craft standard | 10 | 80 | 8.0 | VERIFIED LIVE | 2026-10-03 |
| 8 | D8 | Delivery | 10 | 40 | 4.0 | DEPLOYED | 2026-10-03 |
| 9 | D9 | Evidence | 6 | 40 | 2.4 | REPORTED | 2026-10-02 |
| 10 | D10 | Spec quality and re-entry value | 6 | 60 | 3.6 | VERIFIED LIVE | 2026-10-03 |
| | | **Total** | **100** | | **68.0** | | |

## What moves each dimension

**R1 - One cockpit, one core asset (80/100, weight 12)** - Up from 60. D1.4 closes: the cockpit is the default layout, confirmed in a fresh standalone profile AFTER A LOCAL SESSION LOGIN rather than only in Storybook - the question round 16 left open. #3668 changed LAYOUT_PRESET_DEFAULT to omarchy-inset and persists it on startup, so a fresh profile writes an explicit preset instead of null. An explicit stored choice, including docked, still wins. *(locators: `~/research/antiek-v1-forensics-20260930/review/ROUND-18-REGRADE-20261004.md`, outside this repository)*

**R2 - Keyboard-first operation (60/100, weight 12)** - Up from 40. D2.1 closes: both project round trips (Alpha->Beta->Alpha and the reverse), the Cmd+E recovery control, and a normal route resync all reproduce in a real browser with TRUSTED key events after #3691 added the project-context resync trigger. VERIFIED LIVE (LOCAL) - production was not observed, and the measurement says so. TWO CHECKPOINTS STILL FAIL and are scored zero: the inbox (inbox.toggle still maps to notBuiltYet) and literal single ownership. A NEW DEFECT WAS FOUND: trusted rapid previous/next loses the second navigation in 3/3 trials while settled retries work, which is a race rather than a missing binding. *(locators: `~/research/antiek-v1-forensics-20260930/review/ROUND-20-REGRADE-20261004.md`, outside this repository)*

**R3 - Omarchy insets (80/100, weight 10)** - Upheld with measured pane rectangles at a stated viewport. *(locators: `~/research/antiek-v1-forensics-20260930/review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R4 - Pane semantics (80/100, weight 10)** - Upheld; the agent-opens-into-left-document-space seam was driven live. *(locators: `~/research/antiek-v1-forensics-20260930/review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R5 - Writing shape (60/100, weight 10)** - Up from 40 on #3741. CP1-3 reproduce: the left list AND right tabs both update on one click (the legacy-table count now reads canonical plus unmigrated legacy blocks, the right pane resyncs on outline mutations, and the selection is retained on focus). CP4 retains and submits the exact sentence but the provider-free server returns the configured 503, so no full apply credit - a correct environment response, not a suppressed request. CP5 still loses the assignment on reload while blocks and prose persist - measured, not fixed. *(locators: `~/research/antiek-v1-forensics-20260930/review/ROUND-22-REGRADE-20261007.md`, outside this repository)*

**R6 - Execution (80/100, weight 14)** - Up from 60. D6.5 closes: a claim with no stored core span now downgrades through the existing llm_expanded fallback (#3675), with the positive-span case still retained - both directions reproduced. The fork-merge authorization chain (#3674) is merged and DEPLOYED. D6.4 still fails: the reader's merge client is PRESENT-AND-WRONG - ReformatReview.tsx:82 sends generation_id as forkId and reformat.ts:173-190 posts to /forks/{id}/merge (404), while the registered routes want fork_id plus selected node items. *(locators: `~/research/antiek-v1-forensics-20260930/review/ROUND-18-REGRADE-20261004.md`, outside this repository)*

**D7 - Craft standard (80/100, weight 10)** - Upheld on re-measurement, with the known gate holes tested against current main rather than restated. *(locators: `~/research/antiek-v1-forensics-20260930/review/D7-D10-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**D8 - Delivery (40/100, weight 10)** - Fell from 80 on independent re-measurement. Two of five checkpoints reproduce: the reading code is on main, and the served API identity resolves to a commit that is an ancestor of main. Three do not, and the reason is EVIDENCE ACCESS rather than a regression: the production pane journey needs an authenticated browser, the served sha is 10 commits behind the measured main, and the production R6 journey answers 401. The scoring rule is explicit that an unverified live journey earns no credit, so this is unverified rather than proven absent. *(locators: `~/research/antiek-v1-forensics-20260930/review/ROUND-16-REGRADE-20261003.md`, outside this repository)*

**D9 - Evidence (40/100, weight 6)** - Partial. The lesson-noted record is strong; the underlying scorecard's own rubric substitution was the defect. *(locators: `~/research/antiek-v1-forensics-20260930/review/ANATOMY-REGRADE-20261002.md`, outside this repository)*

**D10 - Spec quality and re-entry value (60/100, weight 6)** - Upheld. The canon publication closed the round-15 blocker; no current completion map existed - this file is it. *(locators: `~/research/antiek-v1-forensics-20260930/review/D7-D10-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

## How a reader should use this

1. **Do not trust a score whose inputs have changed.** When a fix merges or a defect is found for a dimension, re-measure that dimension and edit its row above. A score carried forward because 'the tree is unchanged' is a statement about the diff, not the dimension. The one time this repository tested that practice, it was inflating two of seven dimensions.
2. **Partial reproduction earns zero, not ten.** Five checkpoints per dimension, 20 points each, credited only when reproduced at the stated evidence level.
3. **Prefer a command to a claim.** Every verdict needs an absolute locator: a file and line, a command with its output, or a URL with the computed value.

## What is deliberately not built

See the *What we deliberately have NOT built* section of `README.md`. An unbuilt thing that was never promised is not a defect; a promised thing that does not behave is.
