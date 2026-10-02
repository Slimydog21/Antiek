# 10-modes-a — Mode surfaces

Audit of eight mode surfaces against `src/design/DESIGN_LANGUAGE.md` (Werner skin / PostHog pattern, §5.6) and `src/design/FEEL_CONTRACT.md`, with general craftsmanship second. Both gates pass as shipped: `npm run lint:tokens` → OK (no new hex, 80 grandfathered); `npm run lint:type` → OK (no chrome text over the 24px ceiling via the arbitrary-value hatch). Zero hardcoded hex exists in any of these surfaces — every colour issue below is a *token-choice* issue (default Tailwind palette, dead classes, wrong ramp step), which the lints structurally cannot see.

One systemic finding colours the whole batch: **`text-ink-soft`, `text-ink-mute`, `border-ocean`, `bg-ocean/…`, `text-ocean` are dead utility classes.** They appear in no color key of `tailwind.config.js`, no CSS class, and no `--ocean`/`--ink-soft`/`--ink-mute` variable in `tokens.css` (verified by grep across `src/`). Tailwind 3.4 JIT drops them silently, so every element that relies on them renders with inherited/unstyled colour. Used app-wide (Write, Reading, Settings too); instances below are only the in-scope ones.

## Surfaces

### Backtest
Entry: `apps/reading/src/modes/Backtest/index.tsx:33`. Route `/backtest/:synthesisId`. A max-w-4xl report page: serif h1 + spec citation, a LemonCard "Synthesis" panel, a 3-col grid of six `Metric` tiles, and three LemonCard `DetailList` sections that dump up to 50 JSON-stringified rows each, plus a link to the outcomes grading view. Loading is an italic text line; the 404 path is folded into the error state. The most Lemon-primitive-adopting of the admin-style surfaces.

### Billing
Entry: `apps/reading/src/modes/Billing/index.tsx:41`. Operator usage/margin view for `GET /billing/summary/:user/:period`. Serif h1 header, a user/period input panel, a free-tier progress bar (sun fill ≥90%), two `CostCard` margin cards, and a totals section. All containers are hand-rolled `border-rule rounded-md` divs — no LemonCard anywhere, so no sun edge or chunky shadow. No dark-mode handling on several fills.

### Biography
Entry: `apps/reading/src/modes/Biography/index.tsx:39`. Two-phase consumer landing (the strongest surface in this batch): correct page ramp (`bg-ice-2 dark:bg-space-2`), BrainMascot idle/celebrate headers, a 3-step explainer list, a start form with ModelUsagePicker + LemonButton, and an M3 onboarding phase with three SurfaceCards and a sun-tinted invite section using AIActionFailure for errors. Copy is serif throughout and test-asserted. Deviations are scale/ceiling details, not structural ones.

### BrainstormStation
Entry: `apps/reading/src/modes/BrainstormStation/index.tsx:35`. Mode E workstation on PanelHost with two docked starters (`WatchForLaterPanel` left, `ThoughtPartnerPanel` right); the main slot renders either the `ParkedQuestion` detail + launch button (`ParkedQuestion.tsx:21`) or a centered EmptyState. ThoughtPartnerPanel (`ThoughtPartnerPanel.tsx:47`) is a full multi-turn chat: InsightLegoShelf search/drag source, a dashed "focus tray" drop target, ContextPicker, textarea, thread rendering. Honest empty/loading/error states throughout.

### Coordination
Entry: `apps/reading/src/modes/Coordination/index.tsx:33` (+ `CostConsent.tsx:410` as the sibling money view). Read-only operator surfaces: GateLedger (`GateLedger.tsx:57`) renders eight binding gates as LemonCards with LemonTag status pills and per-workflow impact rows; Roadmap (`Roadmap.tsx:60`) renders a reconciliation banner, DRW-critical-path LemonTags, and five LemonTable sprint rosters; CostConsent adds cost and escrow/consent LemonTables with honestly-stubbed margins. The most token-disciplined batch member — Lemon primitives, `text-emperor` for danger, honest empty states in every table.

### CreationStudio
Entry: `apps/reading/src/modes/CreationStudio/index.tsx:67`. Mode C on PanelHost: DeliverableSidebar docked left (deliverable list, create form, VoiceNoteCapture widget), BlockPalette docked right (search + HTML5 drag source), main slot = DeliverableDetail with Export dropdown, drag-target SectionCards with inline ProseEditor, and a dashed NewSectionForm. Functional but the chrome is all bespoke: every button is a hand-rolled `bg-ink text-white`, the Export dropdown uses a default soft `shadow-md`, and drop-hover uses default-palette emerald.

### CrossGraphCitations
Entry: `apps/reading/src/modes/CrossGraphCitations/index.tsx:32`. Operator-only POST form for `/cross-graph/citations`: four labelled id inputs, a federation toggle with conditional substrate-id field, a record button, and a session-local "recently recorded" list. Same hand-rolled section/input/button template as Billing.

### DeepResearchWorkspace
Entry: `apps/reading/src/modes/DeepResearchWorkspace/index.tsx:79` (PanelHost, no starters). The hero surface: ComposeBar → cascade PlanEditor (approve-gated Launch) → Monitor with per-research ResearchPanel steer cards in a responsive grid, aggregate CostMeter, HardCeilingEvidence band, the lazy ResearchWaitArcade (two Krea key-art cartridges, own var-driven CSS, focus-restoring Escape handling), and the SPR-03 organism Canvas (draggable BlockCards, SVG lineage Edges, BlockDetail overlay hosting the shared FloatMenu). Imagery, mascot reactions (useWernerResearchReactions), and wait-arcade art make this the most playful surface; also the one with the deepest bespoke-state drift (its own 8-state registry beside the canonical 5-state one).

## Findings

| Severity | Location (file:line) | Issue | Fix direction |
|---|---|---|---|
| P0 | BrainstormStation/ThoughtPartnerPanel.tsx:211, 228; BrainstormStation/InsightLegoShelf.tsx:96, 111 | `border-ocean`, `bg-ocean/10`, `hover:border-ocean`, `text-ocean` are dead classes (no `ocean` token anywhere). The focus-tray drop-active affordance and the Lego-chip tint never render — a functional drag-target state silently absent | Add an `ocean`-role token (or reuse `aurora`, the reserved AI accent) and re-point the four usages |
| P0 | DeepResearchWorkspace/ResearchPanel.tsx:22-42 | Private `STATE_LABEL`/`STATE_CLASS` 8-state registry duplicating `src/shared/researchState.ts`, whose header states "surfaces consume it and never define their own encoding." Colours diverge from the canonical map (`running`→`text-aurora`; canonical working=sun, blocked=danger with label "needs attention") | Extend researchState.ts with the DRW-only states (paused, stopping, budget_halted) and consume `researchStateStyle` |
| P0 | BrainstormStation/ParkedQuestion.tsx:64 | Primary "Launch investigation" button is `bg-ink text-white hover:bg-shadow-2` with **no dark: variants** — `#0F1419` ink fill on the `dark:bg-charcoal-2` main (#1B202A) is a near-invisible control at night | Use LemonButton variant="primary" (sun fill, dark-safe by construction) |
| P1 | Backtest/index.tsx:69; Billing/index.tsx:80; BrainstormStation/index.tsx:123; Coordination/index.tsx:68; Coordination/CostConsent.tsx:447; CrossGraphCitations/index.tsx:97 | Page scroll surface painted `bg-ice-0 dark:bg-charcoal-2` — the *card* tones, not the page ramp (day page = ice-2, night page = space-2 per tokens.ts `aliasFor`). Biography (index.tsx:96) does it right, so siblings disagree | Re-point all six to `bg-ice-2 dark:bg-space-2` |
| P1 | Backtest/index.tsx:75; Billing/index.tsx:86; Coordination/index.tsx:74; Coordination/Roadmap.tsx:67,105; Coordination/GateLedger.tsx:70,124,147; Coordination/CostConsent.tsx:194,336,355; CrossGraphCitations/index.tsx:103; CreationStudio/index.tsx:386,432 | `text-ink-soft` dead class — the intended muted day-mode hierarchy silently renders as inherited ink | Define the token or replace with `text-shadow-1` |
| P1 | BrainstormStation/ThoughtPartnerPanel.tsx:186,220,306,310; BrainstormStation/InsightLegoShelf.tsx:67,82,103; BrainstormStation/WatchForLaterFolder.tsx:76; CreationStudio/index.tsx:226,325,328,377; CreationStudio/BlockPalette.tsx:60,71; DeepResearchWorkspace/BlockCard.tsx:104; DeepResearchWorkspace/BlockDetail.tsx:88; DeepResearchWorkspace/HardCeilingEvidence.tsx:57,91 | `text-ink-mute` dead class (same systemic hole) | Same fix; one token addition clears the app-wide set |
| P1 | Backtest/index.tsx:90; Billing/index.tsx:120; CrossGraphCitations/index.tsx:120 | Error boxes use default-palette `border-red-200 bg-red-50` (no dark: variant — a pale-red box on the night card); `emperor` is the reserved danger token. Meanwhile DRW (index.tsx:201) does `border-emperor/40 bg-emperor/5` and Coordination uses bare `text-emperor` — three error idioms across siblings | One shared error callout on emperor tokens; adopt in all three |
| P1 | Backtest/index.tsx:191, 196 | Metric highlight uses default-palette `border-amber-300` + `text-amber-800` beside `bg-sun/10` — mismatched hue pair, both off-token | `border-sun-deep` / `text-sun-deep` over the sun wash |
| P1 | Billing/index.tsx:94, 131, 169, 199; CrossGraphCitations/index.tsx:125, 195 | Every container is a hand-rolled `border border-rule rounded-md` div — no sun edge, no chunky offset shadow. Sibling Backtest/Coordination use LemonCard on the same kind of content; §5.6's Werner mark is absent | Swap to LemonCard (elevation z1, title slot) |
| P1 | Biography/index.tsx:101, 257 | h1 `text-3xl` (30px) exceeds the 24px chrome ceiling — escapes via the named-utility hatch the type lint admits it doesn't scan | Drop to `text-2xl` |
| P1 | Biography/index.tsx:104, 191, 260, 308, 316, 371, 374; DeepResearchWorkspace/BlockCard.tsx:82, 103 | Arbitrary `text-[15px]` / `text-[13.5px]` / `text-[13px]` — off the named scale (xs 12 / sm 14 / base 16); sub-ceiling so the lint can't see them | Snap to scale steps (prose → `text-sm` or `text-base`) |
| P1 | BrainstormStation/InsightLegoShelf.tsx:103 | `text-[9px]` — below the scale floor (xxs = 10px) | `text-xxs` |
| P1 | CreationStudio/index.tsx:215, 439, 492; CreationStudio/DeliverableSidebar.tsx:99; CreationStudio/VoiceNoteCapture.tsx:55; BrainstormStation/ThoughtPartnerPanel.tsx:266; CrossGraphCitations/index.tsx:188 | Bespoke `bg-ink text-white hover:bg-shadow-2` buttons (some with partial/no dark handling) instead of LemonButton — six re-implementations of one primitive | LemonButton variant="primary"/"secondary" |
| P1 | CreationStudio/index.tsx:304, 394 | Default-palette emerald (`border-emerald-500 ring-emerald-300` drop hover, `text-emerald-700` save status) — `aurora` is the reserved positive/AI accent | aurora tokens |
| P1 | CreationStudio/index.tsx:220 | Export dropdown `shadow-md` — default soft shadow, off the chunky-offset brand mark (FEEL_CONTRACT opaque-card primitive) | `shadow-z1 dark:shadow-z1-night` (or LemonModal/menu primitive) |
| P1 | BrainstormStation/ThoughtPartnerPanel.tsx:279 | Error line `text-red-700 dark:text-red-300` default palette instead of `text-emperor` | emperor |
| P1 | DeepResearchWorkspace/ResearchPanel.tsx:60; DeepResearchWorkspace/PlanEditor.tsx:58; DeepResearchWorkspace/index.tsx:252 | Cards/containers use `border-2 border-sun` (2px) with **no shadow-z\*** — the FEEL contract's opaque-chunky card is `border-edge` (2.5px) + depth-mapped offset shadow; the hero surface's own cards miss the brand mark its sibling LemonCards carry | `border-edge` + `shadow-z1 dark:shadow-z1-night`, or LemonCard |
| P1 | DeepResearchWorkspace/CostMeter.tsx:46 | `transition-[width] duration-300` — animates width (motion.ts: GPU-cheap transform/opacity only) and 300ms is off the motion scale (80/150/800) | transform-scaleX bar, or `duration-base` |
| P1 | Billing/index.tsx:137 | `transition-all` animating the bar's width — same GPU/layout-thrash rule; `transition-all` also implicitly animates everything else | Same as CostMeter |
| P1 | DeepResearchWorkspace/PlanEditor.tsx:107 | Edit/+sub/remove controls revealed only via `group-hover:opacity-100` — keyboard/touch users can never reach them | Add `group-focus-within:opacity-100`; consider always-visible at `opacity-icon` |
| P1 | CreationStudio/index.tsx:150 | DeliverableDetail h1 is sans `font-semibold tracking-tight` while every sibling surface's title is `font-serif` (the notebook register) and none use tracking-tight | `font-serif` to match Backtest/Billing/Coordination |
| P2 | Biography/index.tsx:141, 184, 303, 382 | `border-2` (2px) vs the 2.5px `border-edge`; step-badge and CTA `border-ink` with no `dark:border-bright` (ink-on-charcoal invisible at night); SurfaceCard CTA hand-rolls `hover:-translate-y-0.5` with no transition class — a snapped, half version of motion.ts `cardLift` | border-edge; dark border variant; use LemonButton or motion.ts primitives |
| P2 | Backtest/index.tsx:86; Billing/index.tsx:126; CreationStudio/index.tsx:125-141 | Loading/empty states are bare italic text; DRW's Canvas uses the shared `Thinking` component and BrainMascot/Werner art exist for exactly these slots. No Doodles-style art on any of the admin surfaces' empty/loading states | Shared Thinking + a mascot/art slot per the four-slot restraint rule |
| P2 | Backtest/index.tsx:190, 235 | Metric tiles are plain divs while sibling sections are LemonCards (mixed container language on one page); DetailList rows render raw `JSON.stringify(r)` — substrate dump, not graded prose | LemonCard for tiles; shape rows into label/value pairs |
| P2 | Billing/index.tsx:96, 107; CrossGraphCitations/index.tsx:234-240 | `<label>` elements not associated with their inputs (no htmlFor/id, not wrapping) | htmlFor/id pairs |
| P2 | Billing/index.tsx:139, 227 | `bg-sun/100` (== `bg-sun`, odd literal) for ≥90% with no dark variant on the `bg-shadow-2` default fill; Row's `emphasize` ternary repeats `text-ink dark:text-bright` in both branches (dead conditional) | Clean up both |
| P2 | BrainstormStation/WatchForLaterFolder.tsx:65 | Selected row uses default `shadow-sm` soft shadow | Token shadow or drop it (the border-l already marks selection) |
| P2 | CreationStudio/index.tsx:373 | Prose display renders sans `text-sm`; serif (Charter) is the prose register per tokens.ts `type.serif` and the ProseEditor textarea itself is serif | `font-serif` on the read view |
| P2 | CreationStudio/BlockPalette.tsx:90 | `dark:border-slate-1 dark:bg-charcoal-2` applied unconditionally in dark mode (not hover-gated), so the hover affordance disappears at night | Scope dark variants to the base state, keep `dark:hover:` distinct |
| P2 | BrainstormStation/index.tsx:152-180; Coordination (all); Billing; Backtest; CrossGraphCitations | No mascot or feature art anywhere outside Biography/DRW — the playful half of "playful-but-precise" is absent from five of eight surfaces, whose empty states are text-only | One BrainMascot mood per empty state (four-slot rule permits empty) |
| P2 | DeepResearchWorkspace/ResearchPanel.tsx:75 | `opacity-60` magic value; the opacity tokens (`opacity-icon`/`opacity-disabled`) exist for this | `opacity-icon` |
| P2 | DeepResearchWorkspace/PlanEditor.tsx:78 | `paddingLeft: depth * 14` inline magic px | spacing-scale multiplier (var(--spacing) * 14 = 3.5rem is `pl-14` equivalent per depth is fine to keep, but express via a named constant) |
| P2 | DeepResearchWorkspace/Canvas/Edges.tsx:90 | Inline `style={{ fontSize: 10, fontFamily: "ui-monospace" }}` — bypasses the mono token (JetBrains Mono) and scale | font-mono text-xxs via a class or SVG attrs from tokens |
| P2 | DeepResearchWorkspace/Canvas/Canvas.tsx:234-341 | Block drag is pointer-only; no keyboard move for canvas blocks (cards are buttons, so detail is reachable, but position is not) | Arrow-key nudge on focused block emitting the same `block.positioned` event |
| P2 | DeepResearchWorkspace/ResearchWaitArcade.tsx:254-272 | Local re-implementation of `usePrefersReducedMotion` though `workspace/usePrefersReducedMotion` is imported by the gate in the same feature (index.tsx:56) | Import the shared hook |
| P2 | Coordination/CostConsent.tsx:246 | `text-emperor dark:text-emperor` — redundant dual variant (emperor is a static hex key; night emperor #FF6155 is unreachable via this class) | Note as known static-key limitation, or var-driven danger text |
| P2 | Backtest/Billing/Coordination/CrossGraphCitations page shell | `px-8 py-10 max-w-3xl/4xl` vs Biography `px-6 py-12 max-w-2xl` vs CreationStudio `px-6 py-6` vs DRW `p-4` — four page rhythms, no shared page-shell component | One ModePage shell component carrying max-w + padding |

## Verdicts

### Backtest — bring to standard:
1. Move page bg to `bg-ice-2 dark:bg-space-2` (index.tsx:69).
2. Replace `text-ink-soft` (index.tsx:75) with a real muted token.
3. Replace the red-200/red-50 error box with the shared emperor callout (index.tsx:90).
4. Re-token the Metric highlight to sun-deep (index.tsx:191,196) and put tiles in LemonCards.
5. Replace raw JSON rows with shaped label/value rows and adopt the shared Thinking/empty-state slot.

### Billing — bring to standard:
1. Page bg to ice-2/space-2 (index.tsx:80); wrap all four sections in LemonCard to restore the sun edge + chunky shadow (index.tsx:94,131,169,199).
2. Shared emperor error callout (index.tsx:120); replace `text-ink-soft` (index.tsx:86).
3. Fix the progress bar: no `transition-all` width animation (index.tsx:137), dark variant for the fill (index.tsx:139).
4. Associate form labels with inputs (index.tsx:96,107); drop the dead `emphasize` branch (index.tsx:227).

### Biography — bring to standard:
1. Drop h1 to `text-2xl` (index.tsx:101,257) to respect the 24px chrome ceiling.
2. Snap `text-[15px]`/`text-[13.5px]` to the named scale (index.tsx:104,191,260,308,316,371,374).
3. `border-2` → `border-edge`, and add `dark:border-bright` to the ink-bordered badge/CTA (index.tsx:141,184,382).
4. SurfaceCard CTA → LemonButton (index.tsx:378-385). Otherwise the closest surface to standard in the batch — keep the mascot/AIActionFailure pattern as the reference.

### BrainstormStation — bring to standard:
1. Resolve the dead `ocean` classes so the focus-tray drop state actually renders (ThoughtPartnerPanel.tsx:211,228; InsightLegoShelf.tsx:96,111) — P0.
2. LemonButton for Launch + Send; the Launch button is currently near-invisible at night (ParkedQuestion.tsx:64, ThoughtPartnerPanel.tsx:266) — P0.
3. Replace dead `text-ink-mute` everywhere; `text-[9px]` → `text-xxs` (InsightLegoShelf.tsx:103); red-700 → emperor (ThoughtPartnerPanel.tsx:279).
4. Page bg ice-2/space-2 (index.tsx:123); mascot in the EmptyState; drop `shadow-sm` (WatchForLaterFolder.tsx:65).

### Coordination — bring to standard:
1. Page bg ice-2/space-2 on both views (index.tsx:68, CostConsent.tsx:447).
2. Replace `text-ink-soft` instances (index.tsx:74; Roadmap.tsx:67,105; GateLedger.tsx:70,124,147; CostConsent.tsx:194,336,355).
3. Adopt the shared error callout for consistency with siblings (index.tsx:88, CostConsent.tsx:467). Lemon primitive usage is otherwise the model for the batch — smallest fix list here.

### CreationStudio — bring to standard:
1. Replace all six bespoke ink buttons with LemonButton (index.tsx:215,439,492; DeliverableSidebar.tsx:99; VoiceNoteCapture.tsx:55).
2. Emerald → aurora tokens (index.tsx:304,394); `shadow-md` → chunky token shadow on the Export dropdown (index.tsx:220).
3. Serif the deliverable h1 (index.tsx:150) and the prose read view (index.tsx:373).
4. Replace dead `text-ink-mute`/`text-ink-soft`; fix always-on dark fills in BlockPalette hover (BlockPalette.tsx:90); upgrade empty/loading states (index.tsx:125-141) to the shared pattern.

### CrossGraphCitations — waive:
Operator-only POST form; fix it by inheritance when the shared error-callout/page-shell components land for Billing (its template twin) rather than as its own pass.

### DeepResearchWorkspace — bring to standard:
1. Consume `shared/researchState.ts` instead of the private STATE_LABEL/STATE_CLASS registry, extending it for paused/stopping/budget_halted (ResearchPanel.tsx:22-42) — P0 contract violation.
2. Give ResearchPanel/PlanEditor/ComposeBar containers the FEEL-contract card chrome: `border-edge` + `shadow-z1` (ResearchPanel.tsx:60, PlanEditor.tsx:58, index.tsx:252).
3. CostMeter bar: transform-based, on-scale duration (CostMeter.tsx:46).
4. Keyboard access for plan-row actions (PlanEditor.tsx:107) and canvas block moves (Canvas.tsx:234).
5. Sweep dead `text-ink-mute` (BlockCard.tsx:104, BlockDetail.tsx:88, HardCeilingEvidence.tsx:57,91); token the Edges SVG text (Edges.tsx:90); `opacity-60` → `opacity-icon` (ResearchPanel.tsx:75); share the reduced-motion hook (ResearchWaitArcade.tsx:254).

*Cross-cutting: define real tokens for `ink-soft`/`ink-mute`/`ocean` (or delete the classes app-wide) and build one ModePage shell + one emperor error callout — those two moves clear roughly a third of the rows above across all eight surfaces.*
