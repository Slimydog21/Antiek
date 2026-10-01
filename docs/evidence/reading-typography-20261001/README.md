# Reading typography candidate

The separate typography candidate implements the [research decision](../../decisions/reading-typography-20261001.md). Source Serif 4 is the default at 20 nominal CSS pixels, 1.65 leading, 66ch maximum width, and natural tracking. This is a warm, restrained design judgment supported by a small portfolio and reader control, without a claimed universal performance ranking.

## Env Card

| Field | Value |
| --- | --- |
| Date, UTC | 2026-10-01 |
| Product repo root | `/Users/slimydog/Antiek/worktrees/reading-typography-20261001` |
| Frontend command cwd | Product root plus `/apps/reading` |
| Branch | `design/reading-typography-20261001` |
| Original evidence base | `b21200200fdace1ec3b7ed0e1a8bde683cd4d81e` |
| Release comparison base | `f2204666210de555ae6b74066d2a13d35ee5fd5e` |
| Candidate identity | Original local snapshot below; release preparation at `521d37888c4fef299315d243bc116a90925d4c09` on main `facb9bf28`; hashes in [candidate-source.json](candidate-source.json) |
| Node / npm | v25.6.1 / 11.9.0 |
| Python | `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3`, 3.11.2 |
| Font tooling | fontTools 4.61.1 with WOFF2/Brotli support; tooling only |
| LLM contacted this session | Research subagent used; no Antiek product provider invoked |
| Network required for gates | Locked asset reproduction and npx tooling; tests and font integrity check are offline |
| Browser | Real local Chrome; native UI and extension locators, plus CDP for inspection/emulation |

## Failure Dossier

This is a typography implementation, with three material integration defects caught during review. No Python/provider failure path applies.

### Signatures

`parseReadingTypography(unknown)` validates schema version 1 and allowlisted font IDs before making style values. `setReadingTypography(Partial<ReadingTypographyPreferences>)` applies a validated browser-local snapshot. `ReadingColumn` preserves its existing attribution/HTML contract and consumes that snapshot. No backend signature changed.

### Numbered failure chain

1. A preference changes the article font or size, while a nested research claim wrapper keeps `text-base leading-relaxed`. The body remains fixed. Removing those body utilities lets thesis, claims, rationale, and appendix inherit the preference. The [manuscript browser record](manuscript-browser.json) shows 24px and 45.6px leading on every tested body section, with compact audit labels.
2. Repeating `document.fonts.load` on an errored CSS font face does not create a new network request. The candidate gives reload/another-font guidance. A [blocked fresh Literata request](font-failure.json) rendered the passage in installed Georgia and exposed the status.
3. Changing glyph metrics moves a passage rect inside an unchanged outer box. ResizeObserver alone misses this case. The book-island measurement and manuscript layout effect now depend on typography and listen for completed font loads; cleanup removes listeners and cancels the manuscript debounce.

### Repro gate

[Geometry regressions](geometry-tests.log) passed 46 tests in the two affected files. In an isolated temporary copy, removing the typography dependencies and font-load listeners made both new cases fail: the book overlay remained at its old top and the manuscript did not remeasure. [Mutation log](geometry-mutant.log), expected exit 1. The real source was not mutated by this check.

### What repro does not prove

The regression supplies fixed DOM rectangles and event boundaries. It verifies the mounted production components' response and overlay position; it does not measure clinical comfort or reproduce a live backend investigation.

## Scope Map

### Entry points

| ID | Path / trigger | Status | Evidence | Live product LLM |
| --- | --- | --- | --- | --- |
| T1 | Book Type dialog and attributed ReadingColumn | tested | `apps/reading/src/components/reader/ReadingTypography.test.tsx:36`; book-reader suite; [mobile](type-mobile.png) | no |
| T2 | Research manuscript Type, thesis, claims, rationale, appendix | tested | `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.tsx:294`; [computed body metrics](manuscript-browser.json); [render](manuscript-desktop.png) | no |
| T3 | Appearance settings | tested | `apps/reading/src/modes/Settings/AppearancePanel.tsx:51`; actual component in Settings story; [dark settings](settings-dark.png) | no |
| T4 | Persistence, cross-tab event, clear, remount, corrupt/blocked storage | tested | `apps/reading/src/lib/readingTypography.test.ts:5`; `apps/reading/src/components/reader/ReadingTypography.test.tsx:63` | no |
| T5 | Font assets, axes, version, notices, Unicode ranges, true styles | tested | [manifest](../../../apps/reading/public/fonts/reading/manifest.json), [font check](font-check.log), [actual glyph families](portfolio-platform-fonts.json) | no |
| T6 | Desktop widths and 320/390px dialog layout | tested | [Native choices and widths](widths.json); [320px record](browser-320.json), [390px record](browser-mobile.json) | no |
| T7 | Font request failure and installed-font recovery | tested | `apps/reading/src/components/reader/ReadingTypography.test.tsx:22`; real blocked-request [record](font-failure.json) | no |
| T8 | Passage/widget geometry after preferences and font completion | tested | `apps/reading/src/modes/Reading/Reading.islands.test.tsx:291`; `apps/reading/src/modes/ResearchWorkstation/MasterMdViewer.test.tsx:670`; [mutation](geometry-mutant.log) | no |
| T9 | Safari/Firefox, full assistive technology audit, wider script portfolio | untested | No such validation was performed | no |
| T10 | Real-reader comfort/comprehension experiment | untested | Proposal in the research decision; no participants recruited | no |
| T11 | Live backend/provider/release and palette-branch integration | untested | Separate scope and lane; local candidate only | not invoked |

### Explicitly out of scope

Palette, mascot, backend behavior, database changes, research-provider execution, and the proposed human trial. The operator subsequently authorized release, recorded below.

### Temptations resisted

No automatic font ranking, claimed percentage speed benefit, dyslexia treatment claim, sensing/telemetry feature, proprietary font redistribution, or unrelated reader refactor was added.

## Handoff Packet

### Env Card

The Env Card above pins the product checkout and tools. The harness root is `/Users/slimydog/Antiek`; it is a different checkout and is used only for the shared claim board.

### Not proved

- Reduced sustained fatigue, better comprehension than paper, or a universally easiest font. The review does not establish these outcomes for this candidate.
- Safari/Firefox, full screen-reader behavior, every font/script subset, 200% browser zoom, or live backend/provider paths.
- Integration with the separate reading-comfort branch or a production release. The candidate is published as PR #3603; production verification remains pending.

### Status

The original separate local candidate is complete. The operator subsequently authorized “Push to main and deploy”. Release preparation is in progress; no production claim is made before current-main reconciliation, independent review, exact-head CI, merge-slot coordination and direct production verification.

### Files touched

Typography store, controls, tests, stories, scoped CSS, generated font-face CSS, unchanged font assets/licenses/manifest, vendor script, and the research/evidence records. Four integration consumers change: ReadingColumn, BookReader, MasterMdViewer, and AppearancePanel. Two existing test files add typography geometry regressions; Reading.test.tsx checks that source-link-only arXiv views do not expose an ineffective type control. [Source hashes](candidate-source.json) list the concrete files.

### Milestones (checkboxes)

- [x] Review primary academic reading evidence and qualify its transfer limits.
- [x] Choose a warm professional default and five-face portfolio.
- [x] Vendor unchanged licensed files with full notices and hashes.
- [x] Implement preferences across books, research notes, and settings.
- [x] Verify persistence, fallbacks, styles, responsive controls, and annotation geometry.
- [x] Record bounded checks, visual evidence, reviewer findings, and open validation work.

### Gate results

Commands below run from the frontend cwd unless another cwd is stated. Full outputs are retained.

| Gate | Command | Exit / result | Log |
| --- | --- | --- | --- |
| Type checking | `npm run typecheck` | 0 | [typecheck](typecheck.log) |
| Production build | `npm run build` | 0; large-chunk warning retained | [build](build.log) |
| Focused suites | `NODE_OPTIONS=--no-experimental-webstorage npm test -- src/lib/readingTypography.test.ts src/components/reader src/modes/Settings/AppearancePanel.test.tsx src/modes/Reading src/modes/ResearchWorkstation/MasterMdViewer.test.tsx` | 0; 355 tests / 33 files | [tests](tests.log) |
| Token lint | `npm run lint:tokens` | 0 | [tokens](tokens.log) |
| Type-scale lint | `npm run lint:type` | 0 | [type scale](type-scale.log) |
| Font integrity | `python3 scripts/vendor_reading_fonts.py --check` | 0; 52 manifest entries, 2,065,532 font bytes | [font check](font-check.log) |
| Locked reproduction | `python3 scripts/vendor_reading_fonts.py` | 0; fresh downloads match hashes | [reproduction](font-reproduce.log) |
| React changed scope | `npx --yes react-doctor@latest --verbose --scope changed --include-untracked` | 0; 84/100, existing BookReader complexity warning | [changed](react-doctor-changed.log) |
| React baseline comparison | Explicit source-file scans with complete source context at base and candidate | Both 84/100 with the same existing 1 error / 8 warnings; full-file scans exit 1 | [baseline](react-doctor-baseline.log), [candidate](react-doctor-candidate-files.log) |
| Geometry mutation | Two new cases in an isolated temporary copy with refresh removed | Expected 1; both fail for the targeted stale geometry | [mutation](geometry-mutant.log) |
| Diff whitespace | `git diff --check`, product cwd | 0 | Source inspection |
| Broad claim board | `python3 .infinite/validate-control-plane.py`, harness cwd | 0; final typography claim in review | [control plane](control-plane.log) |

Node 25's experimental webstorage conflicts with this Vitest/jsdom environment. The test command disables it; plain runs can fail before test bodies at localStorage.clear. This is an environment requirement, not a skipped behavior check.

### Decisions mid-flight

20px avoids shrinking the existing 19px prose and remains adjustable; it is not the 18-point optimum from Make It Big. Source Serif 4 supplies the warm book voice; Source Sans 3 is the plain contemporary alternative. Four custom families plus installed Classic keep the choice manageable. Original distributed subsets preserve license notices and full variable axes. Reload guidance replaces the ineffective failed-face retry. Typography-dependent geometry refresh preserves anchored widgets across reflow.

### Assumptions surfaced

The body audience and specimens are Latin reading material. Equal nominal size is an honest product preview, not an apparent-size-normalized experiment. The storage version and allowlist are the boundary; arbitrary font CSS is not accepted. Classic's exact rendering depends on installed fonts. Available pane width limits every width choice.

### Steelman rejected alternative

Changing only the global font would be quicker. It would leave research claims at fixed size, omit reader choice and persistence, leave failed loading unexplained, and miss anchored glyph positions when the root does not resize. Those gaps are covered by named regressions and actual browser inspection here.

### Open questions

Does the chosen default improve sustained comfort while maintaining comprehension in the intended audience? The research decision defines a feasible counterbalanced pilot. Wider script coverage needs a separate assessment. The palette owner and typography owner must reconcile shared consumer hunks before any later integration.

### Next sprint can start when

The next integration owner reviews this source snapshot, reconciles current main and the palette candidate, and runs checks on the resulting combined revision. Any performance/comfort claim needs the proposed reader study.

### Out-of-scope temptations

No new application dependency, palette revision, mascot work, provider call, ranking engine, source/rights rule, or automatic sensing feature.

## Craft and diff review

The bounded craft rubric scores 37/40, 92.5%, with no zero or critical failure. Corpus/assets fidelity 4; orientation 4; evidence preservation 3; durable preferences 4; information geometry 4; control precision 3; visual identity 4; accessibility 3; performance/longevity 4; verification discipline 4. Retrieval is unchanged and new search is outside scope. Brand cast is declined for this quiet typography task and remains with the separate palette lane. Scores of 3 reflect the bounded browser and assistive-technology evidence, rather than an unsupported release claim.

The signature element is the restrained Source Serif passage. Existing tokens supply chrome and surfaces; font controls use plain labels and native inputs. The dialog scrolls at short heights, typography adjustments stack in narrow containers, and the real rendered portfolio was inspected. No extra animation or character competes with research prose.

Diff review passed the applicable merge-bar checks: meaningful production behavior tests, established module locations, comments explaining failure/reflow reasons, no unused compatibility API, one typography scope, no package/lockfile changes, and error handling at storage/font boundaries. The research subagent's read-only reviews found no blocking issues after the claim-size, retry, and geometry corrections. This was not an independent model-lineage release review.

## Inspect and reproduce

Start `npm run storybook -- --port 6193 --ci --no-open` from the frontend cwd. Stories are `reading-typography--reader`, `reading-typography--settings`, `reading-typography--manuscript`, and `reading-typography--portfolio`. Fixtures contain authored specimen text and no live user data. [Portfolio image](portfolio.png) shows the same passage in all five faces; [platform-font record](portfolio-platform-fonts.json) confirms real regular, italic, and bold glyphs. Some UI screenshots contain Chrome's Adobe extension bubble; that is not an Antiek control.

The font manifest captures unmodified binaries and adjacent complete OFL notices. Embedded Source Serif/Source Sans notices differ from the adjacent Google notices; both are preserved. Source Sans's variable-font family metadata says ExtraLight, while the verified rendered regular instance and CSS use weight 400.

## Release preparation, 2026-10-01

The original evidence above describes the local candidate on `b21200200`. Implementation commit `521d37888c4fef299315d243bc116a90925d4c09` rebased cleanly onto `facb9bf28`; all 69 original source hashes still match. PR #3603 is published against current main `f22046662`. The owners coordinate one merge slot: whichever current-base candidate first completes its gates may land; the second candidate must reconcile the shared consumers and verify the combined revision. No combined-palette runtime result is claimed.

Fresh checks on this revision passed: full frontend **388 files / 3,675 tests**, types, production build and bundle budgets, token/type-scale lint, and locked font integrity. The strict security scan returned **zero REAL findings**, LOW, 18 advisories; these are existing constants and OSV-verified patched dependency floors. Full command output is retained in `release-*.log`. None of these results establishes a production deployment.

GLM 5.3 independently reviewed the source and requested changes to the earlier palette-first release plan, duplicate visible Aa controls, and missing retained logs. The standalone release plan is now explicit, Type distinguishes the typography trigger, and all linked logs are retained. A fresh review of the repair revision is pending. All 24 accepted visual references were inspected at all three widths; [baseline receipts](visual-baselines.json) pin the authenticated CI artifact and hashes. Required contexts are measured from the live ruleset and the exact published head; the dependent pytest rollup also gates deployment. The served Cloudflare production assets and backend build SHA will be verified after merge.

### Exact-head CI repairs

Head `d908ef7ac95f33af48a4670416b0997a44bd080b` failed visual references and two existing asynchronous frontend tests. No assertions, timeouts, snapshots of runtime state, or thresholds were weakened. The write-key test now waits for route adoption and section seeding before selecting a child; the reformat test waits for its measured island glyph before clicking it. An independent read-only refuter confirmed that these are real readiness boundaries and that later semantic assertions still catch broken behavior. The focused pair passed 28 tests.

The 12 changed existing screenshot references capture intentional self-hosted serif/prose changes, including the synthetic PDF story whose existing Source Serif fallback now resolves. Twelve new references cover the four typography stories at 1280, 1024 and 768 pixels. The authenticated artifact predates the visible trigger rename from Aa to Type; current-head visual CI must validate the resulting caption/layout against these references. The normal 0.4% pixel threshold is unchanged. Stories now participate in the existing axe audit.

Install the font tooling with `python3 -m pip install -r scripts/reading_fonts_requirements.txt` from the frontend directory before `python3 scripts/vendor_reading_fonts.py --check`. The separate tooling pins do not change application dependencies. [Release source hashes](release-source.json) distinguish this repair from the original [candidate snapshot](candidate-source.json). [Preview receipts](preview-fonts.json) verify every one of the 52 font assets against the published preview, not production. The font availability warning covers regular Latin loading; other subsets/styles may use silent fallback.

The repaired source passed a fresh full frontend run: **388 files / 3,675 tests**, exit 0 ([log](repair-tests.log)). Type checking and production build/bundle checks passed, exit 0 ([types](repair-typecheck.log), [build](repair-build-check.log)). A newly created Python 3.11 virtual environment installed the pinned vendor requirements and passed the offline 52-entry asset check, exit 0 ([tooling](repair-font-tooling.log)).

### Combined-main reconciliation

Palette PR #3596 merged to main as `0fa478338d4950dd8c0c10890f7c50b0d20454fd` at 09:48 UTC. Typography now reconciles onto that main in its own branch. The three source conflicts retain `reading-page` palette treatment alongside the typography prose/style hooks, keep both distinct Aa/Type controls with the palette header wrapping, and remove fixed manuscript ink utilities so Softer page light can inherit its approved ink. Appearance settings retain both typography and page light controls. The reader story exposes both entry points and uses a first-level book heading to follow its h1 fixture title without a skipped level.

The 12 conflicted existing visual references take the approved current-main palette bytes; the 12 typography references still describe the earlier palette. These are placeholders for the next honest comparison, not accepted combined references. Combined-source full frontend/build checks, current-head CI, a new independent review, fresh visual references, and direct combined browser/production proof remain pending. The preceding standalone ACCEPT and visual pass do not approve this combined revision.

The reconciled source passed **389 files / 3,690 frontend tests**, exit 0 ([log](combined-tests.log)), type checking ([log](combined-typecheck.log)), and production build/bundle gates ([log](combined-build-check.log)). This count includes the newly merged palette tests. Native Chrome shows distinct Aa/Type controls and the retained theme/page-light dialog. Current-head CI, independent combined review and accepted combined screenshots remain pending.

### Combined visual and contrast repair

GLM 5.3 accepted combined source `b9c4ae35772d006b61f2e70402e2f604d837605a` ([report](glm-combined-source-review.md)), with exact-head CI, fresh visual acceptance, accessibility, security and production gates still required. The authenticated current-head artifact contains 828 valid PNGs and 30 above-threshold differences. All 30 before/current pairs were inspected at 1280/1024/768px and accepted as the expected typography/palette/measure composition; only those references are replaced. [Receipt](combined-baselines.json). The normal 0.4% threshold and workflows are unchanged.

The direct Softer-page audit found one real Serious contrast defect in the manuscript confidence badge: green text on the tinted soft ground was 4.1:1 at 11px. Tinted confidence/recommendation labels now use theme ink while retaining their semantic fills. Repeated actual native axe scans pass on settled light and dark Softer pages. The screenshot artifact predates this foreground correction, so current-head visual CI must validate the small colour delta; the references are copied authentic images, not synthesized future output. [Browser observations](combined-browser.json), [320px dialog](combined-mobile.jpg), and [final source hashes](final-source.json) retain the limits and correction. The initial native standard-page result did not cover this Softer combination.

Focused existing component suites passed 44 tests in 3 files ([log](contrast-tests.log)); fresh types and production build/bundle gates passed ([types](contrast-typecheck.log), [build](contrast-build-check.log)). All other 78 source/context pins remain unchanged from the accepted combined source; a bounded different-lineage review of this final delta and the baseline receipt remains required. The fresh combined strict security report contains zero REAL findings and 18 existing LOW advisories ([report](combined-security.json)). No production verification is claimed yet.

### Enlarged-preview keyboard repair

GLM 5.3 accepted the pinned contrast repair and all 30 authentic baseline receipts at `250cf14f722edfbfd189155177d4d601c8555476` ([report](glm-contrast-source-review.md)). Its remaining checks included the final settings/portfolio native audits. Those audits exposed a real Serious `scrollable-region-focusable` failure: at 24px, the preview has 294px of content in a 238px viewport. The preview is now a named, keyboard-focusable region with a token-based focus outline. Actual PageDown moved scrollTop from 0 to 55.5px while focus stayed on that region ([observations](keyboard-browser.json), [screenshot](preview-keyboard.jpg)).

The repaired native settings scan reports zero violations, 29 passes and two incomplete results; the dark portfolio scan reports zero violations, nine passes and no incomplete results. These are bounded native axe observations, not a full screen-reader certification. The existing CI axe job remains informational. Production appearance boot and live reader validation still require the real deployment. The authenticated 30-reference artifact predates this focus repair, which only adds a focused outline; exact-head visual CI validates the final unfocused layout.

Focused controls tests pass nine cases ([log](keyboard-tests.log)), with fresh type checking ([log](keyboard-typecheck.log)) and production build/bundle gates ([log](keyboard-build-check.log)) also passing. Only ReadingTypography and readingTypography.css differ from the prior 79-pin source snapshot; the other 77 pins remain unchanged ([keyboard source snapshot](keyboard-source.json)). A fresh bounded different-lineage review and exact-current-head CI remain required before merge.

The fresh strict security scan after the keyboard repair returns zero REAL findings and 18 existing LOW advisories ([report](keyboard-security.json)).

Manual inspection of the two incomplete settings rules found an unsupported aria-label on the specimen paragraph. That label is removed, while the actual comparison characters remain inside the named preview region. The repeated native scan has zero violations and one incomplete rule limited to the existing Theme/Motion decorative down arrows; their named combobox controls and visible Dark/System choices remain readable. The updated source hashes and focused logs include this semantic repair. All linked keyboard logs are explicitly retained despite the repository log ignore rule.

### Current-main writer-lock reconciliation

GLM 5.3 independently accepted the final keyboard source at `43b78db86ff60e5b327318d267bc604cbfcd9a0f` ([report](glm-keyboard-source-review.md)). Exact-head frontend, type, keystone, declared-bar, visual and browser checks passed; pytest shard 2 also passed. Before the remaining shards completed, main advanced to `f8dd2a9f3cc7b4d6d2ac7a1f40f895d2cf764459`, the approved PR #3589 writer-lock fix. The separate typography candidate merges that current main without conflicts. All 79 prior font/palette source pins remain identical, and all four incoming backend/test files are copied byte-for-byte from main ([83-pin snapshot](main-f8dd-source.json)). No typography pixels, controls, preferences or geometry logic change in this reconciliation.

Merged-state typography controls pass nine tests ([log](main-f8dd-controls-tests.log)); the production build, its type compilation and bundle gates pass ([log](main-f8dd-build-check.log)). The incoming backend suites pass 33 tests under isolated local TestClient settings ([log](main-f8dd-python-tests.log)). The first local run inherited host operator-auth settings and returned 401 before the targeted route behavior, producing 23 failures ([original log](main-f8dd-python-host-auth.log)); the second process explicitly empties the token/email/service-token environment fields used by local auth, consistent with the unit-test development configuration. No source, assertion or production security policy is changed to obtain that pass. The fresh strict scan reports zero REAL findings and 18 existing LOW advisories ([report](main-f8dd-security.json)).

The preceding current-head passes remain historical after this necessary main update. A fresh bounded independent review, exact new-head CI and direct production proof still gate the resulting merge revision. The new head will be pushed once and left intact while CI completes.

### Current-main telemetry and read-lock reconciliation

All twelve release contexts and terminal primary CI passed for `0b824cd14d4bc6140e88f1d018e0c07e487b707c`. Main then advanced to `a3c0ad7afaa5f066637c9c457082550d73b0ee86`, including telemetry retry delivery, typed database-read conflicts mapped to HTTP 503 with Retry-After, and five verified tooling/security fixes. Their fifteen changed paths have no overlap with the typography candidate. This separate candidate merges current main without conflicts and retains every incoming file byte-for-byte. All 83 prior source/context pins and all 828 visual references remain unchanged ([98-pin snapshot](main-a3-source.json)); the new pins record inherited context, not authored backend or telemetry changes.

Merged-state typography controls and the incoming telemetry retry suite pass 15 tests in two files ([completion log](main-a3-frontend-tests.log)). Incoming read-conflict, read-fallback and shard-weight suites pass 35 tests with the same isolated local TestClient auth configuration explained above ([raw log](main-a3-python-tests.log)). Production type compilation, build and existing bundle budgets pass ([log](main-a3-build-check.log)). The fresh strict security scan returns zero REAL findings ([report](main-a3-security.json)). No application dependency, assertion, visual threshold or production security policy is changed by this reconciliation.

The preceding twelve green contexts describe the prior head. A fresh independent source review, exact updated-head CI, and actual production typography/font/bootstrap and reader observations remain release gates. A healthy API response is not proof of a working reader: the premerge live site still failed to open a public book while its API reported the palette deployment. That limitation must be recorded and rechecked after deployment.
