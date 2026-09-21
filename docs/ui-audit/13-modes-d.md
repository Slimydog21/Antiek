# 13-modes-d — Mode surfaces: OperatorDashboard, Outcomes, OutcomesIndex, PayoutsAudit, Pricing, PrivacyDashboard, Reading, Replay

Audit baseline: `src/design/DESIGN_LANGUAGE.md` (Werner skin, PostHog pattern; "every colour is a token"), `src/design/FEEL_CONTRACT.md` (opaque-chunky elevation), `src/design/tokens.ts` + `tailwind.config.js` (canonical palette/radius/motion/type — type ceiling tested in `src/design/type-scale.test.ts`: xxs 10 / xs 12 / sm 14 / base 16 / lg 18 / xl 20 / 2xl 24px chrome ceiling). `npm run lint:tokens` run 2026-09-20: green (80 grandfathered hex, none in scope — zero hardcoded hex found in any scoped file).

## Surfaces

### OperatorDashboard
Entry: `apps/reading/src/modes/OperatorDashboard/index.tsx:52`. Single-pane operator console (`h-screen` flex shell, `max-w-5xl px-8 py-10` column). Serif `text-2xl` h1 + muted spec-citation lede; a "Substrate snapshot" card (6 stat tiles + pending-deletions + recent-payouts tiles linking to /stats, /privacy, /payouts) and four status-bucketed publisher sections (pre-onboarded / invited / claimed / opted out) with a raw "Mark notified" action button. Flat rule-bordered cards, no art; loading is a bare text line, error a bare `text-emperor` line.

### Outcomes
Entry: `apps/reading/src/modes/Outcomes/index.tsx:40`. Per-synthesis grading surface wrapped in `PanelHost` (no starters). Serif h1 + lede + mono `synthesis_id` line with backtest link; a "Grade now" card (raw textarea + three grade buttons coloured emerald/rose/shadow); a 3-up count-card row; a history list coloured emerald/rose per verdict. Honest empty/loading states.

### OutcomesIndex
Entry: `apps/reading/src/modes/OutcomesIndex/index.tsx:27`. Cross-investigation outcomes audit. Same shell, `max-w-4xl`; observer filter (raw input), bordered error banner, honest explanatory empty state, and a proper `LemonTable` (S10 acceptance) with mono id columns. Has stories + tests.

### PayoutsAudit
Entry: `apps/reading/src/modes/PayoutsAudit/index.tsx:37`. Read-only Stripe Connect transfer log. Same shell, `max-w-5xl`; status-filter pill row + recipient filter input; 5-up totals strip; bordered error banner; rows rendered as custom `<article>` 12-col grids with emerald/red/grey status pills rather than LemonTable. Has stories.

### Pricing
Entry: `apps/reading/src/modes/Pricing/index.tsx:19`. Public-facing calculator page (PostHog Wedge 6 template), `max-w-3xl`. `text-3xl` serif h1 (largest h1 in scope), three flat TierCards with mono margin chips, a three-slider cost calculator with running total, and a creator rev-share section. Pure client-side — no loading/error states needed. No stories.

### PrivacyDashboard
Entry: `apps/reading/src/modes/PrivacyDashboard/index.tsx:73`. First-class user surface (master-spec §13.3), `max-w-3xl`. Serif h1 + honest lede; live ε total; per-surface telemetry cards with a hand-rolled `ToggleSwitch` (role="switch", aria-checked, `focus-visible:outline-sun`, `duration-base ease-standard`, `opacity-disabled` — the motion/a11y exemplar in scope); architectural-guarantees list; a red "Delete everything" danger zone with request/cancel flow. No loading state. Has stories + tests.

### Reading
Entry: `apps/reading/src/modes/Reading/index.tsx:41`. The book reader — richest surface in scope. `flex h-screen`: hidden-on-mobile TOC sidebar (`TocPanel`), `max-w-2xl` prose column with serif title + servability `LemonTag`, gate-driven body (`ReadingColumn`), sun-edged honest notices for gated/taken-down/arXiv-link-unavailable states, `AdBorder` rails (border-edge rule, `HouseSlot` zero-buyer fill), `ArxivFrame` link-back card (proper `border-edge border-sun rounded-hog shadow-z1` — the FEEL exemplar), `Attribution` provenance chips, pager, plus floating chrome (`TalkToBook` thought-partner FAB/panel, `ReadingCompanion` rail with shared `Thinking` beat, `VoiceNote`, `ResearchThis`, shared `FloatMenu`). Sub-surfaces `MetaReading/index.tsx:38` (proposed-banner corpus synthesis with sun banner idiom) and `PersonalSpace/index.tsx:45` (self-organizing asset list with suggest-not-autoship filing) follow the same shell. Good LemonButton/LemonTag/LemonTextarea adoption throughout — the Lemon reference surface in this batch.

### Replay
Entry: `apps/reading/src/modes/Replay/index.tsx:21`. Trajectory replay wrapped in `PanelHost` with a docked-left `ReplayStepList` starter (step-pill nav, 5s polling, sun-wash hover). Serif h1 + mono investigation line with an emerald/grey live/offline WS pill; honest loading/empty/error states; body delegates to shared `TrajectoryReplay` (out of folder scope).

## Findings

| Severity | Location (file:line) | Issue | Fix direction |
|---|---|---|---|
| P0 | OperatorDashboard/index.tsx:143,304 · Outcomes/index.tsx:137 · OutcomesIndex/index.tsx:68,138,148 · PayoutsAudit/index.tsx:90 · Pricing/index.tsx:192 · PrivacyDashboard/index.tsx:181 · Replay/index.tsx:153 · Replay/ReplayStepList.tsx:88,101,111,148 · Reading/MetaReading/index.tsx:160 · Reading/PersonalSpace/index.tsx:127 · Reading/TocPanel.tsx:19,41 · Reading/AdBorder.tsx:69 · Reading/HouseSlot.tsx:29 · Reading/ReadingCompanion.tsx:96,127 | `text-ink-soft` / `text-ink-mute` are **phantom utilities**: neither colour exists in `tailwind.config.js` (colors block; `plugins: []`), `tokens.ts`, or `tokens.css` (no `--ink-soft`/`--ink-mute` either — grep confirms zero definitions; 86 files repo-wide use them). Tailwind v3 silently emits nothing, so every muted subtitle/meta line renders in inherited ink by day; only the paired `dark:text-starlight/moonlight` saves night mode. The muted text hierarchy the design assumes does not exist. | Define `ink-soft`/`ink-mute` for real — tokens.ts + tokens.css + tailwind.config.js in the mandated three-way sync (DESIGN_LANGUAGE.md:44-46) — or migrate every use to existing `text-shadow-1 dark:text-moonlight`. |
| P0 | Pricing/index.tsx:49 | h1 `text-3xl` = 30px, over the tested 24px chrome ceiling (`type-scale.test.ts:57`); every sibling h1 in scope is `text-2xl`. | Drop to `text-2xl font-serif` (or justify a marketing exemption in DESIGN_LANGUAGE). |
| P1 | Outcomes/index.tsx:178,184,196,197,217,222 | Grading semantics painted in raw Tailwind `emerald-700/600` + `rose-700/600` — off-palette hues that evade the hex lint; contract reserves accents to aurora (AI-thinking) and emperor (danger). No `dark:` variants: rose-700/emerald-700 text on charcoal at night. | Map falsified → emperor family, validated → aurora or sun-deep; add dark variants; consider a documented `success` token if semantics demand green. |
| P1 | Outcomes/index.tsx:190 | Indeterminate GradeButton `bg-shadow-2 hover:bg-shadow-1` has no dark variant — mid-grey slab on night chrome. | `dark:bg-slate-2 dark:hover:bg-slate-1` or equivalent token pair. |
| P1 | PrivacyDashboard/index.tsx:332 | ToggleSwitch on-state `bg-emerald-600` — off-palette green, no dark variant, on the most interactive control in scope. | Token the on-state (aurora or a documented success token). |
| P1 | PrivacyDashboard/index.tsx:291,293 | Sensitivity chips `bg-sun/10 text-amber-800` and `bg-red-50 text-red-800` — raw amber/red palette, no dark variants (dark-brown-on-charcoal at night). | Use sun-deep / emperor token pairs with dark variants. |
| P1 | PrivacyDashboard/index.tsx:375-410 | "Delete everything" zone built from raw `red-50/200/300/700/800/900` instead of the emperor danger token; no dark variants → light-pink panel floats on night chrome; mixes idioms by using `hover:bg-emperor/20` (401) inside the same red card. | Rebuild on emperor with tint/shade tokens + dark variants. |
| P1 | PrivacyDashboard/index.tsx:173-230 | No loading state: while `privacy`/`data` are null the page renders header only; every sibling shows a "Loading…" line. | Add loading paragraph (sibling idiom). |
| P1 | PayoutsAudit/index.tsx:110-111 | Active filter `bg-ink text-white` has no dark variant (near-black chip on charcoal); inactive chip's trailing `dark:bg-charcoal-1` duplicates its own base class, so `hover:bg-ice-4` fires unopposed at night — a light flash on hover. | Give active chip `dark:bg-bright dark:text-ink`; replace trailing dark class with `dark:hover:bg-slate-1`. |
| P1 | PayoutsAudit/index.tsx:172-176 | Status pills `bg-emerald-100 text-emerald-700` / `bg-red-50 text-emperor` carry no dark variants — light green/pink pills at night; emerald off-palette. | Token pairs with dark variants (e.g. emperor tints; aurora/slate for transferred/neutral). |
| P1 | PayoutsAudit/index.tsx:162-204 | Audit rows are a bespoke `<article>` 12-col grid while the sibling audit surface (OutcomesIndex) uses `LemonTable` — two table languages for the same job. | Port to LemonTable. |
| P1 | Replay/index.tsx:163 | Live pill `bg-emerald-100 text-emerald-700` — off-palette green, no dark variant. | Token pair (aurora/slate) with dark variant. |
| P1 | Reading/MetaReading/index.tsx:198 · Reading/TocPanel.tsx:38 · Reading/TalkToBook.tsx:311 · OperatorDashboard/index.tsx:327 | Repeated active-control idiom `bg-ink text-white` with no dark variant — near-black chips/buttons sink into charcoal night chrome. | `dark:bg-bright dark:text-ink` (or a selected-token pair) everywhere the idiom appears. |
| P1 | Reading/TalkToBook.tsx:252,267 | Floating thought-partner FAB + panel use soft Tailwind `shadow-lg`/`shadow-2xl` and `rounded-lg` (12px — not a radius token); FAB has no dark variant (ink-on-charcoal). FEEL_CONTRACT's chunky offset `shadow-z*` is the only sanctioned elevation for floating chrome. | `rounded-hog-lg` + `shadow-z3 dark:shadow-z3-night`; FAB `dark:bg-bright dark:text-ink`. |
| P1 | Reading/index.tsx:351,415,423,518 · Reading/TocPanel.tsx:19,36 · Reading/TalkToBook.tsx:271,309,323,338,377,382,399,436,506,513,526,534,543,552,560,565,571,595,622,634 · Reading/MetaReading/index.tsx:210,244,251,258,268,284,291,321 · Reading/PersonalSpace/index.tsx:136,167,189,290,299,316 · Reading/AdBorder.tsx:69 · Reading/HouseSlot.tsx:29,56 · Reading/ArxivFrame.tsx:122,124 · Reading/Attribution.tsx:75 · Reading/VoiceNote.tsx:122,138,146,151,162,178,204 · Reading/ReadingCompanion.tsx:83,114,127 · Replay/ReplayStepList.tsx:88,101,108,111,130,142,148 · OutcomesIndex/index.tsx:76,138,148 · OperatorDashboard/index.tsx:232,241,257,277 · PayoutsAudit/index.tsx:136,139,170,184,189,198 | Arbitrary font sizes bypass the tested named scale (xxs 10 / xs 12 / sm 14 / base 16): `text-[11px]`, `text-[13px]`, `text-[15px]` are off-scale entirely; `text-[10px]`/`text-[12px]`/`text-[14px]` duplicate xxs/xs/sm as literals. MetaReading's report body `text-[15px] leading-[1.7]` (251) is an untokenized prose measure. | Map to named scale utilities; for the 11/13/15px sizes either move to the nearest named step or argue a scale extension in tokens. |
| P1 | Pricing/index.tsx:105-142,202-212 | Calculator sliders are raw `<input type="range">` with browser-default styling (no sun accent, no focus ring), and `CalculatorRow` labels are `<p>` not `<label>` — no accessible name association. | Associate labels (htmlFor/id or wrap), style the range (accent-color token, focus-visible ring). |
| P1 | Outcomes/index.tsx:158 · OutcomesIndex/index.tsx:89 · PayoutsAudit/index.tsx:147 · PrivacyDashboard/index.tsx:202 · Replay/index.tsx:177 · Reading/MetaReading/index.tsx:217 · Reading/PersonalSpace/index.tsx:147 | The error banner `border-red-200 bg-red-50 text-emperor` is raw Tailwind red + no dark variants (light banner at night). Consistent across the repo, but off-token and unthemed. | One shared `ErrorBanner` on emperor tokens with dark variants; replace all seven call sites. |
| P2 | OperatorDashboard/index.tsx:324-330 · Outcomes/index.tsx:165-172,258-267 · OutcomesIndex/index.tsx:79-85 · PayoutsAudit/index.tsx:104-116,118-124 · PrivacyDashboard/index.tsx:398-413 · Reading/MetaReading/index.tsx:169-186 | Raw `<button>`/`<input>`/`<textarea>` on the operator surfaces while Reading (the sibling in this batch) uses LemonButton/LemonInput/LemonTextarea throughout — two control languages. | Migrate to Lemon primitives. |
| P2 | Outcomes/index.tsx:263 · Reading/TalkToBook.tsx:280,543,552 | `disabled:opacity-50` magic value; PrivacyDashboard/index.tsx:330 already uses the `opacity-disabled` token (0.65). | Standardize on `disabled:opacity-disabled`. |
| P2 | OperatorDashboard/index.tsx:218 | Trailing `dark:text-bright` next to `dark:text-moonlight` on the same element — conflicting dark classes; the intended dark hover is never delivered. | `dark:hover:text-bright`, drop the duplicate base class. |
| P2 | OperatorDashboard/index.tsx:154-159 | Error renders as a bare `text-emperor` line; loading as bare text — every sibling uses the bordered banner for errors. | Adopt the banner idiom (or its tokenized successor). |
| P2 | OperatorDashboard/index.tsx:211,227,240,256,301 · all sibling cards | Radius via `rounded-md`/`rounded` (coincidentally 6px/4px) instead of the named `rounded-hog`/`rounded-sm` tokens; only ArxivFrame.tsx:117 uses `rounded-hog`. | Use named radius utilities so radius is greppable as a token. |
| P2 | Reading/AdBorder.tsx:50 | Passive ad rail carries `border-edge` (2.5px) — twice the border weight of every surrounding 1px card; `min-h-[44px]` arbitrary. | 1px `border border-rule` unless the heavy edge is a deliberate slot marker; token the min-height. |
| P2 | Reading/TocPanel.tsx:35 | Inline `style={{ paddingLeft: 8 + level * 14px }}` — arbitrary 14px indent step off the spacing scale. | Spacing-scale multiples (e.g. level * 4 → px-4 steps). |
| P2 | Reading/index.tsx:347 · Reading/ReadingCompanion.tsx:75 | TOC `hidden md:block` with no mobile disclosure — mobile readers get no navigation; companion `hidden lg:flex` has no fallback surface. | A disclosure/overflow affordance for TOC below md. |
| P2 | Reading/HouseSlot.tsx:51 | `LemonTag colour="aurora"` on a house promo; contract reserves aurora for AI-thinking. | `muted` or `sun-deep`. |
| P2 | OperatorDashboard/index.tsx:138 (space-y-8) vs OutcomesIndex:63 / PayoutsAudit:85 / Replay:148 (space-y-6) vs Pricing:47 (space-y-10) | Page rhythm varies 6/8/10 between otherwise-identical shells. | One section rhythm for the `px-8 py-10` shell. |
| P2 | Outcomes/index.tsx:263 · PayoutsAudit/index.tsx:108 · Reading/HouseSlot.tsx:48 · Reading/TalkToBook.tsx:252 | Bare `transition-colors` (Tailwind default timing) and a transitionless `hover:opacity-90` FAB; PrivacyDashboard:330 shows the intended `duration-base ease-standard` form. | Add `duration-base ease-standard` (and a transition on the FAB). |
| P2 | OperatorDashboard · Outcomes · Pricing · Replay (no *.stories.tsx in those dirs) | DESIGN_LANGUAGE.md:77-84 makes Storybook the visual reference; four of eight surfaces have no stories (OutcomesIndex, PayoutsAudit, PrivacyDashboard, Reading do). | Add at least default/empty/error stories per surface. |

No hardcoded hex in any scoped file (grep `#[0-9a-fA-F]{3,8}` clean; token lint green). Empty states are uniformly honest and calm — the strongest contract compliance in scope. Art: none of these surfaces uses Werner/brain art, which is correct for operator/utility surfaces under the "honest empty states, no marketing" principle.

## Verdicts

### OperatorDashboard
bring to standard:
1. Resolve phantom `text-ink-soft` (lines 143, 304) once the token question is settled systemically.
2. Give the Notify button (327) a dark variant and LemonButton form.
3. Fix the dead/conflicting `dark:text-bright` on the stats link (218).
4. Adopt the shared error banner (158) and named radius/opacity tokens.

### Outcomes
bring to standard:
1. Re-colour grading semantics off emerald/rose onto token accents with dark variants (178-197, 217-222).
2. Dark-variant the indeterminate button (190).
3. Swap raw textarea/buttons for LemonTextarea/LemonButton; `disabled:opacity-disabled`.
4. Map header lede to the fixed muted token (137).

### OutcomesIndex
bring to standard (closest to standard in scope — LemonTable, honest empty state, stories):
1. Fix phantom `text-ink-soft`/`text-ink-mute` (68, 138, 148).
2. Tokenize the error banner (89).
3. LemonInput for the observer filter (79-85); named type sizes for the arbitrary `text-[10/11/12px]`.

### PayoutsAudit
bring to standard:
1. Port the bespoke row grid to LemonTable (162-204) to match its sibling audit surface.
2. Fix the filter-pill dark-hover bug (110-111) and active-chip dark variant.
3. Dark-variant + token the status pills (172-176).
4. Tokenize error banner (147); named type sizes for the six arbitrary-size sites.

### Pricing
bring to standard:
1. Bring the h1 under the 24px chrome ceiling (49).
2. Associate slider labels and style the range inputs (105-142, 202-212).
3. Align section rhythm to the shell standard (space-y-10 → sibling value).
4. Fix phantom `text-ink-soft` caption (192); add stories.

### PrivacyDashboard
bring to standard:
1. Rebuild the Delete-everything zone on emperor tokens with dark variants (375-410).
2. Token the toggle on-state (332) and sensitivity chips (291, 293) with dark variants.
3. Add a loading state.
4. Keep ToggleSwitch's motion/focus/opacity-token pattern — promote it as the reference for sibling controls.

### Reading
bring to standard:
1. TalkToBook floating chrome onto FEEL elevation: rounded-hog-lg, shadow-z3 + night variant, dark variants on the FAB (252, 267).
2. Sweep the ~40 arbitrary font-size sites onto the named scale (largest offender: MetaReading report `text-[15px] leading-[1.7]`, 251).
3. Dark-variant the `bg-ink text-white` active chips (MetaReading:198, TocPanel:38, TalkToBook:311).
4. Lighten AdBorder's edge weight (50); tokenize TocPanel's indent step (35); mobile TOC affordance (index.tsx:347); aurora → muted on the house promo tag (HouseSlot:51).
5. Otherwise the Lemon-adoption, gate-honest states, and ArxivFrame's sun-edge card are the batch exemplars — preserve.

### Replay
bring to standard:
1. Token + dark-variant the live pill (index.tsx:163).
2. Tokenize the error banner (177) and phantom muted classes (153; ReplayStepList:88,101,111,148).
3. Named type sizes in ReplayStepList (six arbitrary-size sites).
4. Add stories.
