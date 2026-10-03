# Completion map

**Generated 2026-10-03 11:08 UTC from live state.** Regenerate with `python scripts/completion_map.py` - do not hand-edit.

- `origin/main` = `1ea2db034a01d23e4eeebb51239d3ff6cccc1ea8` - *Merge pull request #3662 from Slimydog21/fix/read-lock-wait-default*
- production API `build_sha` = `debbb2df0d3a` - **13 commits behind main** - the backend deploys automatically once a gating workflow finishes, so this gap is merge latency, not a missing deploy step
- open pull requests: **64**
- measured grade against the frozen rubric: **60.4 / 100**

This file answers one question: **what is actually done, as of the sha above?** It exists because nothing in this repository previously said so, and a returning agent could not tell measured work from intended work.

Every claim below carries one of the frozen rubric's evidence classes. `REPORTED` never becomes `DEPLOYED`. `MERGED` is only claimed when `git merge-base --is-ancestor` proves the commit is on main.

## How the score is computed

Each dimension is scored out of 100 against a fixed 100-condition. The operational partial-credit rule, adopted so every round's number is comparable: **five checkpoints per dimension, 20 points each, credited only when reproduced at the stated evidence level. Partial reproduction earns zero, not ten.** A score is only comparable to another score taken under the same conditions - which is why this file records the conditions, not just the number.

Weights sum to 100: R1 and R2 carry 12 each; R6 carries 14 (the heaviest, because execution is where intention and reality diverge); R3, R4, R5, D7 and D8 carry 10 each; D9 and D10 carry 6 each.

## Score by dimension

| # | Ref | Dimension | Weight | Score | Weighted | Evidence class | Measured |
|---|---|---|---:|---:|---:|---|---|
| 1 | R1 | One cockpit, one core asset | 12 | 60 | 7.2 | VERIFIED LIVE | 2026-10-03 |
| 2 | R2 | Keyboard-first operation | 12 | 40 | 4.8 | VERIFIED LIVE | 2026-10-03 |
| 3 | R3 | Omarchy insets | 10 | 80 | 8.0 | VERIFIED LIVE | 2026-10-03 |
| 4 | R4 | Pane semantics | 10 | 80 | 8.0 | VERIFIED LIVE | 2026-10-03 |
| 5 | R5 | Writing shape | 10 | 60 | 6.0 | VERIFIED LIVE | 2026-10-03 |
| 6 | R6 | Execution | 14 | 60 | 8.4 | VERIFIED LIVE | 2026-10-03 |
| 7 | D7 | Craft standard | 10 | 80 | 8.0 | VERIFIED LIVE | 2026-10-03 |
| 8 | D8 | Delivery | 10 | 40 | 4.0 | DEPLOYED | 2026-10-03 |
| 9 | D9 | Evidence | 6 | 40 | 2.4 | REPORTED | 2026-10-02 |
| 10 | D10 | Spec quality and re-entry value | 6 | 60 | 3.6 | VERIFIED LIVE | 2026-10-03 |
| | | **Total** | **100** | | **60.4** | | |

## What moves each dimension

**R1 - One cockpit, one core asset (60/100, weight 12)** - Upheld. Docked two-pane default confirmed in a fresh browser; the live key sheet still claims the opposite. *(locators: `~/research/antiek-v1-forensics-20260930/review/D1-D2-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R2 - Keyboard-first operation (40/100, weight 12)** - Refuted from an inherited 60. An advertised binding (prefix+c) disarms without a picker; account-project selection exists in neither the table nor the UI. Fix blocked by the islands flake. *(locators: `~/research/antiek-v1-forensics-20260930/review/D1-D2-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R3 - Omarchy insets (80/100, weight 10)** - Upheld with measured pane rectangles at a stated viewport. *(locators: `~/research/antiek-v1-forensics-20260930/review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R4 - Pane semantics (80/100, weight 10)** - Upheld; the agent-opens-into-left-document-space seam was driven live. *(locators: `~/research/antiek-v1-forensics-20260930/review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R5 - Writing shape (60/100, weight 10)** - Refuted from an inherited 80. Drag-and-drop of a real source into an outline block IS reproduced and measured; the sentence-edit loop could not be reached because production answers 503 on the generate path. *(locators: `~/research/antiek-v1-forensics-20260930/review/D3-D4-D5-INDEPENDENT-VERIFICATION-20261003.md`, outside this repository)*

**R6 - Execution (60/100, weight 14)** - Up from 20. Re-measured after clauses 1 (#3641) and 2 (#3646) merged: real default prompt generation and opening the generated asset in the reader now reproduce. The fork/merge journey and research-provenance validation still fail. *(locators: `~/research/antiek-v1-forensics-20260930/review/D6-R6-REMEASUREMENT-20261003.md`, outside this repository)*

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
