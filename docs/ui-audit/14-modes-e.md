# 14-modes-e :: Mode surfaces (ResearchWorkstation, Settings, shared, Signals, SkillRuleDetail, SkillRules, Sources, Speak)

Audit baseline: `src/design/DESIGN_LANGUAGE.md`, `src/design/FEEL_CONTRACT.md`, `tokens.ts`/`tokens.css`/`tailwind.config.js`, `motion.ts`/`motion.css`, `zIndex.ts`, `elevation.ts`. Lint state at audit time: `npm run lint:tokens` green (80 grandfathered), `npm run lint:type` green.

Two systemic facts established by compiling a probe against the repo's own `tailwind.config.js` (`npx tailwindcss -c tailwind.config.js`): **`text-ink-mute`, `text-ink-soft`, `text-ocean`, `ring-ocean`, `outline-ocean`, `bg-dashed`, and `dark:bg-charcoal-3` generate NO CSS** — they are dead classes; and `--ocean` is never defined in `tokens.css`, `index.css`, or anywhere under `src/`. Both facts are verified, not inferred.

## Surfaces

### ResearchWorkstation
Entry `modes/ResearchWorkstation/index.tsx:67` (routes `/` and `/inv/:id`). Idle home = `StartResearch embedded` (composer + folded-in MyResearch log) inside a `GlassSurface variant="glass"` landing card; active `/inv/:id` = `InvestigationCenter`, an opaque `GlassSurface variant="solid"` dense IDE (documented elevation exemption) composing `MasterMdViewer` (synthesis prose), `DistillView`, `SuggestedResearch`, `PasteIngest`, live `ThinkingStream` + `NotesPanel` aside, `HighlightToolbar`→`FloatMenu`, `ChaseThread`/`ChaseSlideOver` floating panels, `TrajectoryView` (raw log), `CascadeProposal` planner, `StyleWheel` + `ArtifactFeedbackReview` (artifact style rail, bespoke CSS), `ChunkModal` citation overlay, `PhaseRow`, `ChatInputArea` docked composer, `InvestigationSidebar` docked nav, `VoiceChaseButton`, `ManualSponsorFooter`, `ArtifactOutlineShelf`. ~25k LOC; the product's core loop.

### Settings
Entry `modes/Settings/index.tsx:61` (route `/settings`). Operator settings page: serif h1 + 3-tab tablist (Overview / Lineup / Decision tree, arrow-key accessible), then LemonCard sections (Environment, Passkeys, Models, Budget with progress bar, Prompt cost projection, AddModelPanel, UsagePanel, ComputeCapacityPanel, ToolConnectionsPanel, AntiekBenchPanel, "Coming later" honest roadmap card) and a DecisionTreePanel with candidates table + FallbackReceiptHistory. Page bg `bg-ice-2` (the `--page` alias — correct ramp step).

### shared (mode infrastructure)
`shared/HeaderBar.tsx` — deprecated no-op (returns null, dev-warns); kept per S12 rollback note. `shared/FloatMenu/FloatMenu.tsx:123` — THE shared selection→action float menu (Note/Dialogue/Search/Deep-research + Write-only rewrite/edit), mounted by Research, Read, Write hosts. Forced-dark chrome (`bg-ink text-bright`), viewport-clamped `position:fixed`, LemonButton actions, honest withheld/failure states.

### Signals
Entry `modes/Signals/index.tsx:36` (route `/signals`). Read-only signal-inventory publication: serif h1, schema-version meta line, mono filter input + LemonTag count, LemonTable of domain/ActionType/payload-class with a reserved "Emitted by" column rendered only when data exists. Honest loading/error/empty states.

### SkillRuleDetail
Entry `modes/SkillRuleDetail/index.tsx:27` (route `/skill-rules/:ruleId`). Single-rule view: back link, serif h1, content-addressed id, rule-text section, 2-col Metric grid (domain/kind/contributors/ε/confidence/extracted_at), §13.2 privacy note.

### SkillRules
Entry `modes/SkillRules/index.tsx:33` (route `/skill-rules`). Read-only cross-user rules list: serif h1, 3 confidence counters, filter card (search/domain/confidence), rule rows linking to detail with confidence chips. Honest empty state keyed to the §13.9 gate.

### Sources
Entry `modes/Sources/index.tsx:96` (route `/sources`). Bulk-ingest console: document upload card (drag-drop, attestation radio + confirm checkbox, cancel), URL ingest form (kind/investigation/max-episodes), ConnectedToolSearch section, Recent-ingests list on LemonCard z1 rows with StatusBadges.

### Speak
Entry `modes/Speak/index.tsx:73` (route `/speak/:projectId`, via SpeakConsole). Warm landing-glass project page (GlassSurface over the Scene): back link, serif h1, Settings toggle, invite-link card with copy button, arriving-voices list, honest corroboration section (WernerThinking while working, AIActionFailure on fail), assembling-story section. Lanes (`lanes/YoursLane.tsx`, `PublicLane.tsx`, `PushesLane.tsx`) are the /speak index tab bodies sharing a `PANEL` card const; `Invites.tsx` email invite list; `SpeakSettings.tsx` gated econ/publish panel.

## Findings

| Severity | Location (file:line) | Issue | Fix direction |
|---|---|---|---|
| P0 | ResearchWorkstation/index.tsx:157,164,272; Speak/index.tsx:257,303,309…; Signals/index.tsx:92,111…; SkillRules/index.tsx:102…; + 239 total in scope (504 app-wide) | `text-ink-mute` / `text-ink-soft` are dead classes — not in tailwind.config.js, tokens.css, or index.css; verified by probe compile. The whole muted-text tier silently renders in inherited ink; day-mode hierarchy is broken product-wide and nobody can see it in code review | Add `ink-soft`/`ink-mute` (mapping onto the existing ramp, e.g. shadow-1/glacial-2 and a night pair) to tailwind.config.js + tokens, or sweep-replace with the working `text-shadow-1 dark:text-moonlight` idiom siblings already use |
| P0 | ResearchWorkstation/StyleWheel.css:1,6,10,25; StyleWheel.tsx:420,573; ArtifactFeedbackReview.css:28,51,96,102,104,123 | `var(--ocean)` referenced 12+ times, never defined anywhere under src/ — selected-option borders, fork links, focus outlines, docket accent all compute to inherited color; the component's primary affordance color is invisible | Define the token (or repoint to `aurora`/`sun-deep`) in tokens.css; better: fold both bespoke stylesheets into the token system (below) |
| P0 | Sources/ConnectedToolSearch.tsx:74,88,95 | `text-ocean` / `focus:ring-ocean` / `focus-visible:outline-ocean` — dead utilities (probe-compiled). The "Manage tools" link renders unstyled and the search inputs have NO focus ring — an accessibility break on a form | Replace with token classes (`text-aurora`/`text-sun-deep`, `focus:ring-sun`) |
| P0 | shared/FloatMenu/FloatMenu.tsx:180 | Inline `zIndex: 50` — inside the floating-panel band (2…50) and under workspace windows (z≥40, WINDOW_Z_BASE). The selection menu can paint UNDER a focused floating panel or a glass window, violating the FEEL_CONTRACT layer diagram | Use `zIndex.popover` (120) from design/zIndex.ts |
| P0 | ResearchWorkstation/ChunkModal.tsx:66,70 | Hand-rolled modal: `z-50` (under the window band; a citation modal can slide under a workspace window), `rounded-lg shadow-xl` (soft Tailwind shadow, off the chunky-offset contract), click-outside/Esc re-implemented | Rebuild on LemonModal (z=100, contract chrome) |
| P1 | Settings/index.tsx:282,346,464,792,935; Settings/UsagePanel.tsx:310,446; Settings/ToolConnectionsPanel.tsx:167,202,301; Settings/AddModelPanel.tsx:275,389,594; Settings/LineupPanel.tsx:150 | Error text in Tailwind `red-700/red-300` instead of the reserved `emperor` token ("danger only", the ONE danger hue) | `text-emperor` everywhere; add a dark pair convention |
| P1 | Settings/ComputeCapacityPanel.tsx:116,141,154,164; ToolConnectionsPanel.tsx:182,287 (red-950, red-700/40) | A THIRD red family (`rose-*`) plus raw red-* borders alongside emperor — three danger hues in one mode | Consolidate on `emperor` (+ emperor/opacity for tints) |
| P1 | MasterMdViewer.tsx:831-855,991; ChunkModal.tsx:146-148; DistillView.tsx:234; NotesPanel.tsx:300; PhaseRow.tsx:115; ThinkingStream.tsx:246; TrajectoryView.tsx:90; SkillRules/index.tsx:186; Sources/index.tsx:64; Settings/index.tsx:316-317; AddModelPanel.tsx:316-335; UsagePanel.tsx:363 | Tailwind `emerald-*`/`amber-*`/`orange-*` status colors — off-palette, and most carry NO `dark:` variant, so pastel chips/text sit on night cards unadapted | Mint semantic tokens (the state family already exists: `--state-done` = aurora, `--state-blocked` = emperor) and route success/warn through them with dark pairs |
| P1 | Signals/index.tsx:105; SkillRuleDetail/index.tsx:85; SkillRules/index.tsx:155; ChunkModal.tsx:92 | Error boxes `border-red-200 bg-red-50` — off-token, no dark variant (white-red box on a night page) | One shared error-banner recipe on `emperor` tints with dark pairs |
| P1 | Signals/index.tsx:79; SkillRules/index.tsx:76; SkillRuleDetail/index.tsx:62; Sources/index.tsx:219 | Mode roots use `h-screen` inside AppShell's main slot, which is already `flex-1 min-h-0` between Topbar and bottom rail — the surface is one topbar+rail taller than its slot; bottom content clips under the rail. Settings (index.tsx:199) and Speak (index.tsx:243) correctly use `h-full` | `h-screen` → `h-full` on the four roots |
| P1 | Signals/index.tsx:80; SkillRules/index.tsx:77; SkillRuleDetail/index.tsx:63 (bg-ice-0); Sources/index.tsx:219 (bg-ice-1) vs Settings/index.tsx:199 (bg-ice-2 == `--page`) | Four sibling utility pages paint three different page backgrounds; two use the CARD white as page | One page-bg recipe (`bg-ice-2 dark:bg-space-2`, or glass per the landing contract) |
| P1 | Speak/index.tsx:299; Speak/lanes/PublicLane.tsx:62; PushesLane.tsx:23,113; YoursLane.tsx:48; SpeakSettings.tsx:107 | Speak's `PANEL` card recipe (`border-2 border-ink rounded-md shadow-z1`) is a second card system beside LemonCard (`border-edge border-sun rounded-hog`) that Settings/Sources use — sibling surfaces with two brand cards | Move PANEL onto LemonCard (or add an `ink`-bordered LemonCard variant and use the primitive either way) |
| P1 | ResearchWorkstation/ChatInputArea.tsx:138 | kbd chip shadows are hardcoded hex `shadow-[2px_2px_0_0_#0F1419]` / `dark:#8A7300` — grandfathered literal, and the night value is the PRE-re-tone loud `#8A7300` (token is now `#84722F` via var). The twin kbd in StartResearch.tsx:706 correctly uses `shadow-z1` | Use `shadow-z1 dark:shadow-z1-night` |
| P1 | Sources/index.tsx:222,233,428,69 | h1/h2s are sans `font-semibold tracking-tight` — the only in-scope surface whose headers skip Charter serif; Signals/SkillRules/Settings/Speak all use `font-serif` | `text-2xl font-serif` h1 to match siblings |
| P1 | Sources/index.tsx:261,321 | `dark:bg-charcoal-3` — charcoal-3 does not exist in the night ramp (probe-verified dead); the upload card + result panel lose their dark background | `dark:bg-charcoal-2` (or the correct step) |
| P1 | Sources/index.tsx:240,331; ChunkModal.tsx:70; FloatMenu.tsx:188 (`rounded-md` fine, `shadow-lg` not) | `rounded-lg` (8px) is off the radius scale (4/6/10); `shadow-lg`/`shadow-xl` are soft default shadows where the contract's chunky offset `shadow-z*` is the brand mark | `rounded-hog` + `shadow-z1` family |
| P1 | Settings/index.tsx:402 | `bg-dashed` is a dead class (probe-verified) — the "spend unknown" budget-bar state renders as an invisible empty bar; the honest-empty intent is lost | Render a real hatched/dashed treatment (CSS var background-image) or the existing italic note alone |
| P1 | ResearchWorkstation/StyleWheel.css (whole file), ArtifactFeedbackReview.css (whole file) | Rogue styling subsystem beside the token system: `ui-serif,Georgia` instead of Charter, `160ms ease` transitions off the 80/150/800 motion scale, radius `.45rem/.25rem` off the 4/6/10 scale, font-weight 650/750, bespoke `0 3px 0 var(--rule)` shadow instead of `shadow-z*` | Rewrite both components on tokens + Lemon primitives; delete the stylesheets |
| P2 | 106× `text-[11px]`, 35× `text-[13px]`, 6× `text-[15px]` across scope (StartResearch.tsx:540; ChatInputArea.tsx:108; Speak/index.tsx passim; Settings/index.tsx:261,302,352…; SkillRules…; DistillView.tsx:214…; etc.) | Arbitrary px sizes bypass the named xxs(10)/xs(12)/sm(14)/base(16) scale — 11px and 13px are off-scale steps, 15px is neither sm nor base | Snap to named scale: 11px→xxs or xs, 13px→sm, 15px→sm/base |
| P2 | InvestigationSidebar.tsx:135; LineupPanel.tsx:202 (8px!),222,269; Speak/Invites.tsx:165 | `text-[9px]`/`text-[8px]` — below the type-scale floor (xxs=10px); 8px fails any legibility bar | Floor at xxs; if the meta doesn't fit, it isn't earning its place |
| P2 | SkillRuleDetail/index.tsx:68 | Back link has unconditional `dark:text-bright` next to `hover:text-ink` — night-mode link is always bright, hover does nothing; almost certainly meant `dark:hover:text-bright` | Fix the variant pairing |
| P2 | ResearchWorkstation/ArtifactOutlineShelf.tsx:87,116,151 | `border-rule` / `text-ink` with no `dark:` pairs on a surface that ships dark mode | Add `dark:border-charcoal-1` / `dark:text-bright` |
| P2 | Settings/LineupPanel.tsx:109 | `animate-pulse` (Tailwind default 2s sine) — off the motion scale (80/150/800); the loading dot free-runs outside the system | Drive the pulse from `--motion-*` or use the shared `Thinking` beat |
| P2 | Settings/index.tsx:209,766,802,886,895; UsagePanel.tsx:346,384,390,418; ToolConnectionsPanel.tsx:171,179 | Hairlines as `border-ink/10·15·20` (+ dark `/15·/20`) instead of the `rule` token — a second, ad-hoc hairline recipe beside `border-rule` | Standardize on `border-rule dark:border-charcoal-1` |
| P2 | shared/FloatMenu/FloatMenu.tsx:290; ResearchWorkstation index.tsx:271 | MenuButton has hover but no `:focus-visible` style (keyboard users get no focus indication in the menu); notes aside is `hidden lg:flex` — NotesPanel is unreachable below the lg breakpoint | Add focus rings; provide a small-screen path to notes |
| P2 | shared/FloatMenu/FloatMenu.tsx (mount) | Menu pops in with no enter transition; `motion.ts` `enter` primitive exists exactly for this and is unused | Wire `enter` with a `data-enter` attr |
| P2 | Max-width divergence: Speak max-w-2xl (index.tsx:244), Sources/SkillRuleDetail/Settings max-w-3xl, SkillRules max-w-4xl, Signals/MyResearch max-w-5xl | Five sibling surfaces, four content widths — no documented rule for which width a surface gets | Pick a two-tier rule (prose 3xl / data 5xl) and align |
| P2 | shared/HeaderBar.tsx:25 | Deprecated no-op kept for the S12 rollback window; still imported by WrestleApp (out of scope) — its own doc says delete after one zero-rollback sprint | Confirm cutover, delete file + last imports |
| P2 | Sources/index.tsx:316,323,417 | Primary buttons `bg-ink text-white` hand-rolled instead of LemonButton; `text-white` is a raw default color | LemonButton variant="primary" |
| P2 | SkillRules/index.tsx:120,133 | Text inputs carry no explicit bg (inherit page) while the sibling select at 143 sets `bg-ice-0 dark:bg-charcoal-2` — half the filter card is styled | Match input chrome (LemonInput) |

## Verdicts

### ResearchWorkstation — bring to standard:
1. Define `--ocean` (or repoint to `aurora`) and then rewrite StyleWheel + ArtifactFeedbackReview on tokens/Lemon primitives, deleting both bespoke stylesheets (off-scale fonts, radii, weights, motion, shadows).
2. Rebuild ChunkModal on LemonModal (z=100, chunky chrome).
3. Replace the emerald/amber/orange status chips in MasterMdViewer/ChunkModal/NotesPanel/DistillView/PhaseRow/ThinkingStream/TrajectoryView with semantic state tokens, with dark pairs.
4. ChatInputArea kbd → `shadow-z1 dark:shadow-z1-night` (drop grandfathered hexes, kill stale `#8A7300`).
5. Fix ArtifactOutlineShelf dark pairs; snap text-[9px] (InvestigationSidebar) to the scale floor; route 11/13/15px sizes to the named scale.
6. Give NotesPanel a sub-lg path; keep the documented GlassSurface solid exemption as-is (it is contract-compliant).

### Settings — bring to standard:
1. All `red-700/300` → `text-emperor`; `rose-*` → emperor tints; `emerald-*`/`amber-*` readiness states → state tokens with dark pairs.
2. Repair the `bg-dashed` unknown-budget bar (it renders nothing today).
3. Standardize hairlines on `border-rule`; snap `text-[13px]` mono rows and the 8/9px LineupPanel meta to the named scale.
4. Replace `animate-pulse` with a motion-token beat.

### shared — bring to standard:
1. FloatMenu zIndex 50 → `zIndex.popover` (120); `shadow-lg` → chunky `shadow-z*`; add focus-visible rings on MenuButton; wire `motion.enter`.
2. HeaderBar: schedule deletion per its own S12 note (last consumer is out of scope).

### Signals — bring to standard:
1. `h-screen`→`h-full`, page bg `ice-0`→`ice-2`, error box → emperor recipe with dark pair. (Otherwise the cleanest surface in scope: LemonTable/LemonTag, honest states, serif header.)

### SkillRuleDetail — bring to standard:
1. Same three fixes as Signals (h-screen, bg, error box) + fix the back-link `dark:` variant bug at line 68.

### SkillRules — bring to standard:
1. Same three fixes as Signals; replace emerald confidence chip with a state token + dark pair; give the filter inputs the same bg chrome as the select; align content width with the chosen tier.

### Sources — bring to standard:
1. Kill the dead classes: `text-ocean`/`ring-ocean` in ConnectedToolSearch (focus rings are missing today), `dark:bg-charcoal-3` ×2.
2. Serif h1 to match siblings; page bg → `ice-2`; `rounded-lg` → `rounded-hog`; hand-rolled ink buttons → LemonButton.
3. Replace the emerald "ingested" badge with a state token.

### Speak — bring to standard:
1. Move the `PANEL` recipe (5 copies) onto LemonCard or a documented LemonCard variant — one card system product-wide.
2. Snap the text-[11/12/13/15px] body/meta sizes to the named scale; text-[9px] in Invites up to the floor.
3. Keep the landing-glass root, WernerThinking beats, and honest gate copy — they are the reference implementation for the contract in this scope.
