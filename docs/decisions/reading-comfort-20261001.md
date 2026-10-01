# Reading comfort and the library palette

Date: 2026-10-01. Candidate branch: `design/reading-comfort-20261001`.
Initial base: `origin/main` at `9140b555e7`, refreshed to `facb9bf280a35401c2a873f34b733571768102c6` before release preparation. This change is local and has not been deployed.

The operator wants digital reading to feel as inviting as a library and an open book: warmer pages, no blue dark-mode grounds, the existing interface green `#6ECB8F`, exact lime highlighter `#A9FF17`, and no yellow interface chrome.

After reviewing three [coral/magenta variations](../evidence/reading-comfort-20261001/mascot-magenta-variations.png), the operator selected A with more noticeable magenta legs and approved [the resulting mascot](../evidence/reading-comfort-20261001/mascot-selected.png). The selected character keeps its original coral body and warm brown-red contours, with full `#943D4A` magenta legs. Green and lime remain on controls, highlighting and occasional discovery/completion moments. The operator also requested hands for the Write pose; the other poses were approved. Main and production deployment are explicitly authorized after verification and coordination gates.

Latest mascot accessory steering adds an athletic basketball headband in the preserved UI green-teal `#6ECB8F`, reading "Antiek". The operator referenced Alex Caruso's continuous close-fitting sweatband, then liked sneaker options B and C and requested `#943D4A` magenta as their secondary shoe color. Built-in imagegen concepts were rejected; the operator explicitly selected their Krea API for regeneration. The [refined Krea B/C comparison](../evidence/reading-comfort-20261001/krea-athletic-magenta-comparison.png) and the selected source, prompt, job, model and packaging records are retained under `docs/evidence/reading-comfort-20261001/krea-athletic/`. Krea 2 Medium with the existing `antiek-brain-doodle-v1` LoRA produced the selected concept family; Krea's `google/nano-banana-pro` endpoint performed the reference edits. Two Krea 2 reference-conditioned runs left the accessories out and are recorded as failures to meet the brief, even though their API jobs completed. Those outputs, direct-font overlays and the unselected manual accessory compositor are preserved locally outside the release. The native headband prototype is also excluded. The operator selected B, requested technically exact `#943D4A`, and then clarified that Inter/Source Serif 4 should be inspiration rather than a direct type overlay. Original B shoes and image-integrated lettering are retained. Deterministic color verification fixes the magenta material fills to RGB 148, 61, 74; the operator approved the integrated result with "I like it!". The final 20-pose family uses baked transparent artwork, with hands and props retained in their corresponding pose roles. The approved idle artwork retains B's original sneakers. Other poses are Krea reference edits, rather than pixel-identical copies of the old illustrations. The authored tilt rotates the approved anchor five degrees; blinking changes only the eye regions. Full poses scale uniformly to their original optical bounds, preserving shoe proportions. [Final mascot family](../evidence/reading-comfort-20261001/mascot-selected.png).

The later [reading annotation handoff](reading-annotation-hierarchy-20261001.md) records prompt-based meaning and importance, black brackets/underlines, lime highlights and a magenta question hierarchy. That classifier and bracket design are deferred to the UI design agent. A preliminary manual color-picker experiment was removed from this release.

## Research method

I used Antiek's production connector, `acquisition.arxiv.client.search`, from this worktree, with the existing Python environment. Queries were `"dark mode"` in `cs.HC`, `"visual fatigue"`, and `"display luminance"`. The raw query responses and abstracts are saved locally at `research/reading-comfort-20261001/connector-search.json`. That directory is ignored by git. The standalone skill helper returned HTTP 400; the application connector succeeded. A subsequent version-specific `fetch_by_id` request returned HTTP 429 and activated the governor. I stopped arXiv API calls, then read the selected primary papers through their public HTML/PDF pages.

I excluded stereoscopic, VR, and driving-fatigue results from the basis for ordinary text reading. I added a controlled mobile-reading experiment and a polarity/proofreading study because the arXiv results alone did not test prolonged book reading. These are preprints and limited experiments, not a clinical prescription or a universal display calibration.

## Evidence and its limits

| Primary source and version | What was measured | Decision it supports and limits |
| --- | --- | --- |
| [While and Sarvghad, 2409.10841v2](https://arxiv.org/html/2409.10841v2), 2024-10-04 | Crowdsourced bar, line and scatterplot tasks across age groups. Methods recruited 135 people and retained 104 after exclusions; the abstract reports 134. The final sample was 52 younger and 52 older participants. Individual performance and preference varied across polarity. | Keep both themes and a device-following choice. This tests visualization performance, not long-form reading or eye fatigue. It does not justify declaring dark mode universally superior. |
| [Shrestha et al., 2409.10895v1](https://arxiv.org/pdf/2409.10895v1), 2024-09-17 | Student survey and e-learning prototype feedback. Methods report 650 survey participants and 120 prototype participants; a results table totals 707. Many respondents preferred dark mode and reported less strain. | Make dark reading available and easy to select. Self-reported comfort and inconsistent denominators cannot establish a causal reduction in eye strain. |
| [Corcoran and Corcoran, 2203.16546v1](https://arxiv.org/html/2203.16546v1), 2022-03-30 | Dark-adaptation rationale for astronomers and an analysis of 614 retained conference posters. | Offer a dim-room reading option. This is a domain-specific argument, not a controlled fatigue trial. |
| [Jennings, Treanor and Brettle, 2312.00475v2](https://arxiv.org/abs/2312.00475v2), 2023 preprint with revised version | Twenty consultant pathologists selected luminance for microscopy and displays. All preferred display settings below 500 cd/m²; 90% selected at most 350 cd/m². | Brightness preferences need user control. Pathology images and calibrated luminance do not establish a book-reading target or map to a CSS hex. Only the abstract was available for this source. |
| [Datson, 2602.17670v1](https://arxiv.org/pdf/2602.17670v1), 2026-02-19 | Pilot with 10 participants, BBC Sounds interfaces, bright/dim rooms and a 2017 LCD MacBook Pro. Participants selected higher device brightness in dark mode. Energy depended on brightness; the dark/light interface content did not produce a significant energy difference on that LCD. | Avoid an energy-saving claim and remind readers about device brightness. Hardware and behavior matter. This did not test book reading. |
| [Liu and Luo, 2021, DOI 10.2352/issn.2169-2629.2021.29.42](https://library.imaging.org/admin/apis/public/api/ist/website/downloadArticle/cic/29/1/art00009) | Twenty observers aged 18–24 rated achromatic text/background combinations on OPPO Find X3 displays at 100, 250 and 500 cd/m² and five ambient-light levels. Comfort depended on ambient and display luminance. Lower display brightness was more comfortable in low ambient light; grey combinations often beat extreme endpoints. | Provide softened endpoints and suggest reducing device brightness in dim rooms. The sample, phones and task were narrow. The experiment did not test parchment hues or show that warm CSS colors prevent fatigue. |
| [Piepenbrock et al., 2014](https://pubmed.ncbi.nlm.nih.gov/25135324/) | Pupil size and proofreading performance under positive and negative polarity. The abstract reports smaller pupils and better proofreading with dark text on a light ground. | Keep Paper as a full reading option. Proofreading performance and pupil size are not a direct measure of prolonged reading comfort. Only the abstract was read. |

The research supports choice, avoidance of extreme endpoints, and attention to room/device brightness. The parchment and walnut hues are an aesthetic interpretation of the operator's library brief. The papers do not prove those hues are optimal. CSS controls relative colors; it cannot set a display's luminance in cd/m² or sense the room's illuminance.

## Applied design

| Role | Paper | Library at night |
| --- | --- | --- |
| App ground | `#F3EBDD` | `#211E19` |
| Reading page | `#F9F3E8` | `#29251F` |
| Reading ink | `#2C2823` | `#E6DECE` |
| Softer page | `#E8DFCF` | `#211E19` |
| Softer ink | `#2C2823` | `#C7BBA7` |
| Primary button / tab fill | `#6ECB8F` | `#6ECB8F` |
| Green semantic ink / success fill | `#237242` | `#6ECB8F` |
| Error text / destructive fill | `#8A403B` / `#8A403B` | `#D49B94` / `#8A403B` |
| Highlighter and its ink | `#A9FF17` / `#2C2823` | `#A9FF17` / `#2C2823` |
| Mascot body / legs | Original coral / `#943D4A` | Original coral / `#943D4A` |

The semantic CSS tokens, RGB channels, TypeScript mirror, canvas ramps, translucent fills, browser theme-color and pre-paint bootstrap agree. Dark grounds and neutral text now use charcoal, walnut and linen. Legacy sun names now resolve to the preserved interface green, including primary buttons, selected tabs and pale green surfaces. Links and AI fills use green. Amber and purple status colors use neutral ink while retaining their explicit state and action labels. Errors and destructive actions use the operator's muted red; successful milestones, the Approved stamp and decorative attention trails use green. Shadows use walnut or near-black. Contrast corrections preserve the existing green roles. The model picker's measured label has a neutral card fill; the command palette's selection wash is 80% green so its dark ink stays readable.

### Additional palette evaluation

These are local contrast measurements against the actual reading card, not comfort findings from the papers. Paper is `#F9F3E8`; the night card is `#29251F`. The exact dark red and forest green cannot serve as small text on the night card.

| Offered color | Measured pair | Decision |
| --- | --- | --- |
| Red `#8A403B` | 6.61:1 on Paper; 2.09:1 on night card | Fits the warm book palette. Apply it to destructive fills and Paper error text. Night error text uses the lighter `#D49B94`, which measures 6.47:1 on the night card. Green and lime remain the main decorative accents. |
| Green `#3C6731` | 5.99:1 on Paper; 2.30:1 on night card | Fits the light forest-green family. Retain the current light green role and the explicitly requested `#6ECB8F` mascot/night green rather than add another interchangeable green. |
| Black `#25231A` | 14.25:1 on Paper | Fits the warm neutral family. The current walnut/charcoal ramp already serves this job; retain that coordinated ramp. |
| Gold `#8B6324` | 4.87:1 on Paper | Retain this exploration color in the palette record. It is not used for interface chrome because the operator removed yellow; brown-red remains in the mascot and danger role. |
| Cream `#CDC3B5` | 8.75:1 on night card; red on this cream is 4.19:1 | Fits as a night neutral. Keep the existing lighter paper ramp and linen text; using this exact cream as the main paper would also make the offered red/cream small-text pair fail 4.5:1. |

### Revised offered palette, retained alongside the original

The operator explicitly requested preservation of the earlier swatches. The preceding table keeps all five. These additional swatches remain in the design record, rather than introducing unused decorative colors throughout the reading UI.

| Offered color | Contrast on Paper / night card | Fit and current use |
| --- | --- | --- |
| Magenta `#943D4A` | 6.28:1 / 2.19:1 | Selected mascot leg/detail pigment. Also reserved in the annotation handoff for open questions and confusion. It needs a contrast treatment when used as an underline on the night page. |
| Rich magenta `#9A3346` | 6.48:1 / 2.13:1 | Retained alternative from mascot options B/C; A was selected. |
| Green / shaded green `#0D8F49` | 3.77:1 / 3.66:1 | Compatible decorative green, but below 4.5:1 for small text on both cards. Keep the requested interface green and its readable Paper counterpart. |
| Black `#1A2E21` | 13.05:1 / 1.06:1 | Reserved for notable-information underlines/brackets in the annotation handoff. It needs a contrast treatment on the night page; retain walnut reading ink for this release. |
| Gold / olive `#82893B` | 3.40:1 / 4.05:1 | Retained exploration swatch. The quiet interface continues to use green/lime accents. |
| Paper / sage `#8FA891` | 2.32:1 / 5.93:1 | Compatible night neutral, but a sage main page would reduce magenta small-text contrast to 2.70:1. Keep the lighter warm paper page. |
| Linework `#423530` | 10.66:1 / 1.29:1 | Compatible warm linework, including 5.39:1 against the coral mark. The original raster contours remain and the vector mark uses its coordinated walnut ink. |

The `Aa` control beside the book title opens the app's small portalled appearance dialog. It lets readers select Follow device, Paper or Library at night, then Standard or Softer page light. The same page-light preference is available in Settings. It persists locally, applies before first paint, updates other tabs, and remains usable when storage is blocked. Its copy says: "For a dim room, try Softer and lower your device brightness." Softer affects book prose and the research manuscript reader; it does not dim controls or apply a screen-wide opacity layer.

Native selection, saved inline anchors and sanitized HTML marks use the exact highlighter pigment with fixed walnut ink in either theme. Drifted anchors retain their dashed underline and 70% opacity, with separately checked composited contrast.

The raster mascot family imports versioned athletic PNGs. The offline `build_mascot_athletic.py` step prepares the selected Krea references, fixes magenta material fills to RGB 148, 61, 74, removes the outer background and enclosed space between the legs, and preserves each pose's optical scale. Its provenance records all 20 output hashes, dimensions, byte sizes and exact magenta pixel counts, plus source/input hashes and Krea job identities. The runtime has no mascot color filter or text overlay. Existing accessibility labels, decorative-image rules, style passthrough, reduced-motion behavior and four public moods remain. The vector home mark consumes the coral/magenta tokens. Completion fish and sparkle accents retain green/lime. Original assets remain available.

The initial Write repair was a targeted built-in imagegen edit adding two rounded hands grasping the pencil. The original `write-512.png` is retained, and `write-hands-20261001.png` has a provenance sidecar with the source, operator request and edit prompt. This retained repair is the reference for the Krea athletic Write pose. Its final 512 px PNG keeps both hands grasping the pencil and is 219 KiB before optical normalization; the exact packaged size is in asset provenance.

Typography retains Charter for reading, Inter for controls, and JetBrains Mono for metadata. The reader title wraps its controls when space is narrow. The dialog fits the viewport and escapes floating-reader clipping. Escape and backdrop dismissal return focus to `Aa`.

## Verification

The palette passed 276 focused tests across 28 files, including consumed contrast pairs, token/TypeScript/RGB parity, no-JS dark color fallback, pre-paint restoration, blocked storage, cross-tab updates, settings, anchor rendering, attention-trail rendering and research narration. Final mascot and SpeakIndex checks pass all 37 tests across six files. Three intentional snapshots update only asset paths and the green-button border. `npm run typecheck`, `npm run lint:tokens` and `npm run build` pass. The build retains its existing warning for large JavaScript chunks. The contrast guard has zero newly failing inherited call-site pairs. Four obsolete baseline exceptions were removed because those pairs now pass. No failing pair was added to its allowlist.

Historical yellow/chroma pins were replaced with the new explicit green/lime contract. The keycap token retains contrast against neutral shortcut-key grounds. Green login buttons, tickets and primary Lemon buttons now use fixed walnut borders. The old yellow-face boundary assertion now checks that actual fixed-ink-on-green pair.

React Doctor previously scored 78/100 on the 23-file changed scope; the final changed-scope scan is recorded in verification data. An earlier 12-file scan scored 84/100. Both report exactly the same existing book-reader warning, with cyclomatic complexity 45 and cognitive complexity 50. The warning count and measured complexity did not increase; the score comparison spans different file sets. The change adds a control without adding branches to the book-reader function.

Browser evidence below uses the production reader components in Chrome at 1440×900 and 390×844. Pointer opening, tab focus, Escape focus return, and backdrop dismissal were exercised. Theme/page-light states were set programmatically for the visual comparisons; choice changes and persistence are covered by unit tests. The Softer preference and exact anchor/selection colors were also inspected after an actual reload.

The local browser uses a read-only fixture API with invented book prose and one seeded saved anchor. It does not authenticate to production, write user data, or exercise a paid provider.

Final loaded reader and phone captures are refreshed after the selected mascot changes. These are local fixtures, not production proof. Previews: [Paper reader](../evidence/reading-comfort-20261001/reader-paper.png), [Softer night reader](../evidence/reading-comfort-20261001/reader-night.png), [phone appearance dialog](../evidence/reading-comfort-20261001/mobile-appearance.png), [library with matching workflow mascot](../evidence/reading-comfort-20261001/library-night.png), and [Settings appearance](../evidence/reading-comfort-20261001/settings-night.png). [Verification data](../evidence/reading-comfort-20261001/verification.json) records inspected colors, viewport bounds and input methods. The final mobile dialog is 358 px wide inside a 390 px viewport, portalled to the body; native-control focus is keyboard reachable and Escape returns focus to Reading appearance. Its shadow resolves to near-black rather than green.

The earlier local code review covered the appearance dialog, borders and muted-red status semantics. Its filter verdict is historical and does not establish acceptance of the final baked mascot implementation. Kimi K3 returned actual ACCEPT verdicts for the theme definitions, preferences/modal/consumers and guards on the exact 24-file scope. All reviewed source hashes match. Raw commands, packets, verdicts and failed attempts are retained locally in `/tmp/antiek-comfort-external-review-final-20261001/`. The mascot/accessory portion and full deliverable still require the separate final review before integration. Kimi read supplied source; it did not inspect raster visuals or run tests.

The final full frontend suite passes all 387 files and 3,671 tests with four workers. A concurrent build/art run previously hit three reader async timeouts in two files; the bounded rerun kept every assertion and timeout unchanged. Brand and SpeakIndex tests also pass, as do typecheck, token parity/lint, type-scale lint, production build and JavaScript bundle budgets. No failing assertion was skipped or added to an allowlist. The final `hardenx . --strict --json` exited zero with LOW band, zero REAL findings and 18 advisories. Seven are secret-shaped backend fixtures/configuration and eleven are dependency advisories; none is a new theme finding. Main and production are not yet updated.

### Scoped craft review

The scope is the theme, mascot colors and reading appearance control. Corpus fidelity, retrieval, evidence traversal and living-artifact lifecycle are unchanged and excluded from this candidate's design score; this is not an audit of those existing product systems.

| Applicable dimension | Score / 4 | Evidence |
| --- | --- | --- |
| Orientation | 3 | Existing route/title retained; small `Aa` control beside the title. |
| Information geometry | 4 | Desktop prose measure retained; title controls wrap at phone width; dialog fits and escapes bounded reader clipping. |
| Control precision | 3 | Native labelled choices, existing modal focus trap, real pointer/Tab/Escape evidence, unit-tested persistence and storage failure. Native browser selection changes were not separately proved. |
| Visual identity | 4 | Warm paper/charcoal, Charter reading type and restrained green/lime accents follow the operator's book/library brief. CSS/TS/RGB consumers agree. |
| Brand cast | 4 | Existing pose grammar and placement retained; baked Krea artwork has verified magenta material fills; vector mark consumes the same pigments; Write retains two hands and the pencil. |
| Accessibility | 3 | Consumed contrast and composited highlights pass; visible focus, labelled native controls, reduced motion retained. Native screen-reader output remains untested. |
| Performance/longevity | 3 | No new runtime dependency or image filter; semantic HTML and existing motion behavior. The 20 PNGs total 6,009,335 bytes versus 4,587,549 bytes for the referenced originals. Workflow artwork remains 512 px. JavaScript bundle budgets pass; the images load when their corresponding poses render. |
| Verification discipline | 4 | Rendered outputs inspected, measured bounds saved, focused and brand suites passed, independent local corrections completed, unproved claims listed. |

Total: **28/32 (87.5%)** for this bounded scope. Question-form self-review: the reading control adds no persistent panel; borders continue to communicate existing control structure; Charter remains assigned to reading; prose and native controls remain useful with mascot and motion removed. Bold color is concentrated in the mascot and the reader's actual highlighting. Both offered palettes remain in this record; extra gold/yellow chrome is not introduced. This score does not waive the separate integration review gate.

## Not proved

Reduced eye fatigue, improved relaxation, superiority over a physical book, calibrated physical luminance, and comfort across ages, vision differences and display types need human testing. A suitable follow-up compares both themes and both page-light settings during sustained reading in dim and bright rooms, records actual display luminance and room illuminance, and measures comfort alongside reading accuracy.

Production deployment, native screen-reader output, Safari/Firefox rendering and PDF canvas recoloring have not been tested here. PDF pixels keep their source colors; the document theme applies to the surrounding reader and selectable text UI.
