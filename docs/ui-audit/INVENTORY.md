# INVENTORY — master UI surface inventory

Burn-down checklist for the UI-perfection effort, composed 2026-09-20 from the ten
audit reports in this directory (`00-foundation`, `01-shell`, `02-arcade`,
`03-brand-empty`, `10-modes-a` … `15-modes-f`). Every claim cites its report.
Branch: `ui/posthog-grade-polish`.

Totals across all reports: **36 P0 / 117 P1 / 120 P2 ≈ 273 findings-table rows**,
before dedup. After dedup the work reduces to **9 systemic fixes + ~8 surface PRs +
a P2 backlog** (§3). Counts are findings-table rows attributed per surface; systemic
rows that hit many surfaces at once are counted once in §1 and marked `†` in §2.

## 1. Systemic findings (deduplicated)

### S1 — Phantom Tailwind tokens: `ink-mute`, `ink-soft`, `ocean`, `danger`
- **What:** Classes referencing color names defined nowhere (`tailwind.config.js`,
  `tokens.ts`, `tokens.css`). Tailwind v3 JIT emits zero CSS for them. Muted text
  renders as inherited full ink in day mode; `text-danger` error text loses its red;
  every `ocean` accent (focus rings, selection states, drop targets) never renders.
  Probe-compile-verified by 01, 12, 14.
- **Evidence:** `text-ink-mute` ×362 refs / 98 files, `text-ink-soft` ×240, `ocean`
  ×62 (00 F1); `ink-mute`/`ink-soft`/`text-danger` 630 uses / 146 files (01); 504
  app-wide ink-mute+soft (14); ~60 in Write alone (15); `--ink-mute`/`--ink-soft`
  exist only in the `public/redesign.html` mock; `--ocean` exists nowhere (12, 15).
  Smaller dead-class siblings: `dark:bg-charcoal-3`, `bg-dashed`, `accent-primary`,
  `lm-loading` (14, 12, 01).
- **Reports:** 00 (F1), 01, 10, 11, 12, 13, 14, 15 — 8 of 10.
- **Fix:** Define `ink-mute`/`ink-soft` for real in the mandated three-way sync
  (tokens.ts + tokens.css + tailwind.config.js; likely aliasing `shadow-1`/`shadow-2`
  + night pairs), and add a **referenced-token-resolution guard** to
  `lint_tokens.ts` — the single highest-leverage gap (00 verdict: would have caught
  ~670 phantom refs). Fork noted by reports: define the names (00, 13, 14, 15) vs
  sweep-rename to `text-shadow-1 dark:text-moonlight` (10, 11, 12 offer both).
- **DISAGREEMENT — needs design decision:** `ocean`. 00 F1 says "resolve `ocean` to
  a brand accent or delete it"; 11 (Library `ring-ocean`) notes DESIGN_LANGUAGE §5.6
  **explicitly rejects** the SaaS-blue intent and prescribes `ring-sun`; 14 wants
  `var(--ocean)` defined or repointed to `aurora`/`sun-deep`; 15 leaves Write's whole
  selection accent language hanging on the answer. Do not pick silently.

### S2 — Raw default palette (emerald/red/amber/rose/blue) instead of state tokens
- **What:** Status chips, error boxes, grade buttons, toggles painted in Tailwind
  default-palette colors, evading the hex lint; contract reserves state to the
  `tokens.ts` `state` family (done=aurora, blocked=emperor, working=sun,
  muted=shadow-2) and danger to `emperor` only.
- **Evidence:** Loop3 whole surface (12); InvestigationsIndex + Explain chips (11);
  Outcomes emerald/rose grading, PrivacyDashboard emerald toggle + red-50 delete
  zone, PayoutsAudit/Replay pills (13); Settings red-700/300 + a third `rose-*`
  family, RW emerald/amber/orange chips (14); Stats/TrustCenter strips and MET chips
  (15); CreationStudio emerald, Backtest amber (10). Nearly all lack `dark:` pairs.
- **Reports:** 10, 11, 12, 13, 14, 15 — all six mode batches.
- **Fix:** One pass mapping semantics → state family with dark pairs; mint a
  documented `success` token if green semantics are real (13).
- **DISAGREEMENT — needs design decision:** 10/14/15 map "done/met" → `aurora` per
  `tokens.ts` state, but 11 flags aurora is reserved for AI-thinking (tokens.ts:310)
  and fails contrast on ice-0 (≈1.9:1); 13 suggests a new `success` token. Decide:
  promote aurora, or mint `success`.

### S3 — Hand-rolled error banners (copy-pasted `border-red-200 bg-red-50`)
- **What:** The identical off-token, dark-broken error strip is duplicated across
  12+ modes; beside it sit two other dialects (bare `text-emperor` lines,
  `AIActionFailure`).
- **Evidence:** 10 (×3), 11 (×6), 12 (×3 identical copies), 13 (×7 call sites),
  14 (×4), 15 (Stats, TrustCenter + "12+ sibling modes").
- **Reports:** 10–15. 12 names `Login.css:54` the best token-correct treatment.
- **Fix:** One shared `ErrorBanner` on emperor tints with dark pairs (mode-correct,
  per the Login recipe); replace every copy-pasted strip; give bare-line surfaces
  the retry-capable callout. Gate: vitest + lostpixel + axe-core.

### S4 — Missing `dark:` variants / dead dark hover
- **What:** `bg-ink text-white` controls with no dark pair (near-black on charcoal);
  unconditional `dark:bg-*` base classes that squash `hover:` at night (zero hover
  feedback); chips/banners without dark pairs.
- **Evidence:** 10 (ParkedQuestion launch button near-invisible at night — P0), 11
  (dark-hover squash on pills/rows), 12 (Map, NotebooksIndex, Multimedia
  `text-shadow-2` ≈1.9:1 at night), 13 (`bg-ink` active idiom ×4), 14
  (ArtifactOutlineShelf), 15 (Stats refresh).
- **Reports:** 10, 11, 12, 13, 14, 15.
- **Fix:** The `bg-ink` idiom dies with S5's LemonButton migration (dark-safe by
  construction); codemod `dark:hover:bg-slate-1` pairs where unconditional dark
  bases squash hover. Gate: lostpixel (night snapshots) + axe-core.

### S5 — Bespoke buttons/cards vs Lemon primitives
- **What:** Hand-rolled `bg-ink text-white` buttons (6+ in CreationStudio, more in
  Write/SpeakInvite/Notebook/Sources), hand-rolled `border-rule rounded-md`
  containers beside LemonCard, bespoke `<article>` grids beside LemonTable, Speak's
  5-copy `PANEL` recipe as a second card system, four divergent page-shell rhythms.
- **Evidence:** 10 (Billing/CrossGraphCitations/CreationStudio), 11 (raw `<button>`
  chrome), 12 (Loop3, Notebook), 13 (operator surfaces), 14 (Speak PANEL ×5,
  Sources), 15 (SpeakInvite, Write ×5).
- **Reports:** 10–15.
- **Fix:** Migrate to LemonButton/LemonCard/LemonTable/LemonInput; build one
  `ModePage` shell (page bg + width tiers + rhythm). 10 estimates the Lemon +
  error-callout pair clears ~a third of all mode findings. Gate: vitest + lostpixel.

### S6 — Off-scale arbitrary type (`text-[Npx]`)
- **What:** 1,033 arbitrary sub-ceiling `text-[Npx]` across 180 files (00 F6);
  histogram peaks 11px ×345, 10px ×267, 12px ×192, 13px ×138 — none on the named
  xxs/xs/sm scale; 8–9px uses below the 10px floor (01, 10, 14); `text-[12.5px]` is
  the de-facto chrome size (01). `lint_type_scale` governs only the >24px ceiling.
- **Reports:** all ten (00 F6 quantifies; 01–03, 10–15 list instances).
- **Fix:** Extend lint_type_scale below the ceiling with a grandfathered baseline,
  then codemod the 10/11/12/13px cluster onto `text-xxs/xs/sm` (00 verdict). Gate:
  lint:type + lostpixel.

### S7 — `h-screen` vs `h-full` rooting inside AppShell
- **What:** Mode roots sized `h-screen` inside AppShell's `flex-1 min-h-0` main slot
  are one topbar+rail too tall; bottom content clips under the rail.
- **Evidence:** Signals, SkillRules, SkillRuleDetail, Sources (14 — Settings/Speak
  do it right with `h-full`); OperatorDashboard `h-screen` shell, TrustCenter blank
  `h-screen` (13, 15).
- **Reports:** 14 (primary), 13, 15.
- **Fix:** `h-screen` → `h-full` on the five roots. Gate: lostpixel + vitest.

### S8 — Off-ladder z on overlays
- **What:** Overlays painted under the window/mascot bands: ProductsLauncher `z-50`
  under the z-60 mascot (01); FloatMenu inline `zIndex: 50` can slide under windows
  (14); ChunkModal `z-50` (14); LinkMonster modal `z-index: 20` (12); NavRail mobile
  `z-40`/`z-50` collide with named rungs (01); BrainPresence inline `zIndex: 1` (03).
- **Reports:** 01, 03, 12, 14.
- **Fix:** Rebuild overlays on LemonModal (z=100, focus trap, chunky chrome in one
  move) and consume `zIndex.popover` for FloatMenu; add named `mobileRail` /
  `scenePresence` rungs. Gate: vitest + axe-core (focus trap) + lostpixel.

### S9 — Motion system under-adopted; focus bundle dead
- **What:** `motion.ts` `enter` has zero consumers; ~10 files hand-roll hover lifts;
  CSS off-token durations (160/120/90ms, 1200ms scene crossfade over the 800ms
  ceiling); `feel-focus.css` imported globally with zero consumers while focus rings
  are ad-hoc (`ring-sun` ×8, phantom `ring-ocean` ×4, bare `outline-none`).
- **Evidence:** 00 (F7, F8, F11), 01 (Home, divergent springs), 02 (cartridge
  cards), 03 (120ms blink), 10 (CostMeter width animation), 11–15 (`transition-colors`
  passim, `animate-pulse`).
- **Reports:** all ten.
- **Fix:** Wire `enter` into LemonModal/panels; codemod lifts to `press`/`cardLift`;
  adopt-or-delete feel-focus.css and standardize on `ring-sun`; extend the motion
  guard to non-token durations; decide scene ambience as a documented fifth slot
  (00 F11). Gate: vitest + lostpixel.

## 2. Surface table

P0/P1/P2 = findings rows attributed to the surface, excluding the systemic rows in
§1 (marked `†` where a surface is a major carrier). Sorted by P0 desc, then P1 desc.

| Surface | Report | P0 | P1 | P2 | Verdict | Top fix |
|---|---|---|---|---|---|---|
| Multimedia | 12 | 2† | 2 | 4 | bring-to-standard | Dead `border/text-danger` error boxes → shared emperor banner (S1+S3) |
| Stats | 15 | 2† | 1 | 2 | bring-to-standard | Token + dark-variant error/warning strips (S3) |
| TrustCenter | 15 | 2† | 2 | 1 | bring-to-standard | Token MET chips + error strip; add loading state; `text-3xl`→`2xl` |
| ResearchWorkstation | 14 | 2† | 4 | 4 | bring-to-standard | Resolve `var(--ocean)` (S1 decision); rewrite StyleWheel/ArtifactFeedbackReview rogue CSS on tokens |
| BrainstormStation | 10 | 2† | 4 | 2 | bring-to-standard | `ocean` drop-tray (S1); launch button → LemonButton (invisible at night) |
| Render sites: Home + Biography celebrate | 03 | 2 | 1 | 0 | bring-to-standard | Persistent `mood="celebrate"` → idle / CelebrateBurst one-shot |
| Contract docs (DESIGN_LANGUAGE.md, brand README, PROFILE.md) | 00, 03 | 3 | 1 | 3 | bring-to-standard | Rewrite mascot/tokens sections to shipped brain + SPR-09 values (§3-Q6) |
| Loop3 | 12 | 1† | 1 | 2 | bring-to-standard | Emerald/red palette → state tokens w/ dark pairs (S2) — furthest from contract |
| Explain | 11 | 1† | 2 | 1 | bring-to-standard | De-emerald TierChip/ConfidenceChip → LemonTag tokens |
| InvestigationsIndex | 11 | 1† | 2 | 2 | bring-to-standard | Status chips → tokens.ts `state` family via LemonTag |
| Pricing | 13 | 1 | 1 | 2 | bring-to-standard | `text-3xl` under the 24px ceiling; associate slider labels |
| DeepResearchWorkspace | 10 | 1† | 5 | 5 | bring-to-standard | Private 8-state registry → extend + consume `shared/researchState.ts` |
| Wait-arcade experience | 02 | 1 | 3 | 5 | bring-to-standard | Policy `reducedMotion: hidden→offer` — reduced cartridges already exist |
| ProductsLauncher | 01 | 1 | 0 | 2 | bring-to-standard | Rebuild on LemonModal (fixes z-under-mascot, soft shadow, focus trap) |
| shared/FloatMenu | 14 | 1 | 1 | 3 | bring-to-standard | `zIndex 50` → `zIndex.popover` (120); chunky shadow; focus rings |
| Sources | 14 | 1† | 3 | 2 | bring-to-standard | Dead `text-ocean` focus rings (a11y break) + `dark:bg-charcoal-3` (S1) |
| SceneChrome | 01 | 1 | 2 | 1 | bring-to-standard | Dead "Ask" verb → route through workspace store like `toggleAISidecar` |
| Topbar | 01 | 1 | 2 | 2 | bring-to-standard | Wire or cut 3 dead account-menu items; breadcrumb labels from taxonomy |
| Panel system | 01 | 1 | 2 | 3 | bring-to-standard | Phantom kebab hotkey hints → implement bindings or strip; feed from bindings.ts |
| moodboard.stories.tsx | 00 | 1 | 0 | 1 | bring-to-standard | Retired `#E33C2D`/`#8A7300` swatches → token reads |
| Biography | 10 (+03) | 1 | 3 | 2 | bring-to-standard | Celebrate beat (above); h1 → `2xl`; sizes to scale |
| Home | 01, 03 | 1 | 2 | 2 | bring-to-standard | Celebrate beat (above); motion.ts `cardLift`/`press` + night shadows |
| Write | 15 | 0† | 3 | 5 | bring-to-standard | ~60 dead ocean/ink refs (S1); 4 `window.alert` → LemonToast; orphan Repository delete |
| Reading | 13 | 0† | 3 | 4 | bring-to-standard | TalkToBook floating chrome → FEEL elevation (`rounded-hog-lg` + `shadow-z3` night pair) |
| CreationStudio | 10 | 0† | 5 | 3 | bring-to-standard | Six bespoke ink buttons → LemonButton; emerald → aurora |
| PrivacyDashboard | 13 | 0† | 4 | 1 | bring-to-standard | Delete-everything zone off raw reds → emperor tokens + dark pairs |
| Notebook | 12 | 0† | 4 | 3 | bring-to-standard | Converge dual renderers (route hosts TipTap); `prompt()`/`confirm()` → LemonModal |
| Federation | 11 | 0† | 3 | 2 | bring-to-standard | Add loading state; token saved/error banners |
| PayoutsAudit | 13 | 0† | 3 | 2 | bring-to-standard | Bespoke row grid → LemonTable; dark-hover pill bug |
| Settings | 14 | 0† | 3 | 3 | bring-to-standard | red/rose/emerald → emperor + state tokens; fix dead `bg-dashed` budget bar |
| Signals | 14 | 0† | 3 | 1 | bring-to-standard | `h-screen`→`h-full`; page bg `ice-0`→`ice-2`; emperor error recipe |
| SkillRules | 14 | 0† | 3 | 2 | bring-to-standard | Same as Signals + emerald chip → state token |
| SkillRuleDetail | 14 | 0† | 3 | 1 | bring-to-standard | Same as Signals + back-link `dark:hover:` bug |
| SpeakInvite | 15 | 0† | 3 | 0 | bring-to-standard | Hand-rolled buttons → LemonButton; de-escalate emperor border on neutral notice |
| Backtest | 10 | 0† | 4 | 3 | bring-to-standard | Page bg → `ice-2/space-2`; amber metric → sun-deep; tiles → LemonCard |
| Billing | 10 | 0† | 4 | 3 | bring-to-standard | All containers → LemonCard; progress bar off `transition-all` |
| Outcomes | 13 | 0† | 2 | 2 | bring-to-standard | Emerald/rose grading → token accents + dark pairs |
| SpeakIndex | 15 | 0† | 2 | 1 | bring-to-standard | Create-form card → standard recipe; unify error dialects w/ retry |
| DocumentsIndex | 11 | 0† | 2 | 3 | bring-to-standard | Dark-hover squash on pills; LemonButton + `press` |
| Coordination | 10 | 0† | 2 | 1 | bring-to-standard | Page bg + shared error callout — otherwise the batch's model surface |
| NotebooksIndex | 12 | 0† | 2 | 2 | bring-to-standard | Dead dark hover on pills; create button → LemonButton |
| Replay | 13 | 0† | 2 | 2 | bring-to-standard | Live pill token + dark pair; named type sizes |
| Speak | 14 | 0† | 1 | 2 | bring-to-standard | `PANEL` recipe ×5 → LemonCard variant |
| Interview (panels) | 11 | 0† | 1 | 1 | bring-to-standard | Aurora on human informant violates reservation + 1.9:1 contrast — swap role colors |
| InterviewIndex | 11 | 0† | 1 | 2 | bring-to-standard | Emerald invite CTA → `bg-ink`/LemonButton primary |
| Library | 11 | 0† | 1 | 1 | bring-to-standard | `ring-ocean` → `ring-sun` (BookCard already does) — reference surface otherwise |
| ObjectiveCard | 12 | 0† | 1 | 2 | bring-to-standard | Shared emperor error notice; sizes to scale — otherwise closest to standard |
| OutcomesIndex | 13 | 0† | 1 | 1 | bring-to-standard | Tokenize banner; LemonInput — closest to standard in batch |
| Economics/AccrualView | 11 | 0† | 1 | 1 | bring-to-standard | Unmounted dead surface: wire into synthesis view or delete |
| Map | 12 | 0† | 1 | 2 | bring-to-standard | Dead dark hover; stale "Pricing + replay" group |
| LinkMonster | 12 | 0 | 1 | 2 | bring-to-standard | Bespoke modal → LemonModal (lm-skin class); self-host display fonts |
| Login | 12 | 0 | 1 | 3 | bring-to-standard | Focus ring `var(--aurora)` → `var(--sun)`; constellation/mascot name mismatch |
| ArcadeMount | 02 | 0 | 3 | 1 | bring-to-standard | Aspect distortion (`height:auto`+`aspect-ratio`); per-cartridge sr-only instructions |
| Ice Fishing cartridge | 02 | 0 | 3 | 0 | bring-to-standard | HUD font → `type.mono`; mode-blindness via `aliasFor(mode)` |
| Zombies cartridge | 02 | 0 | 2 | 1 | bring-to-standard | HUD text off moonlight (3.4:1) → night[8/9]; kill 6px compact band |
| Arcade engine core | 02 | 0 | 0 | 2 | bring-to-standard | Stale consumer comment; franchise genre tags → neutral |
| Key art | 02 | 0 | 0 | 2 | bring-to-standard | Decide/document illustration dialect vs house Krea style; alt-text decision |
| BrainMascot | 03 | 0 | 0 | 2 | bring-to-standard | Docblock rewrite (tilt removed); dead 3D scaffolding; scene prop wire-or-delete |
| BrainPresence | 03 | 0 | 1 | 1 | bring-to-standard | Inline `zIndex:1` → named ladder rung |
| mascotSceneMap | 03 | 0 | 1 | 1 | bring-to-standard | Penguin-era copy → brain voice; dead `scene` seam wire-or-delete |
| werner/animated wrappers | 03 | 0 | 2 | 1 | bring-to-standard | `#16C2C2` ×4 → aurora token; CaughtAFish penguin chrome re-author for brain |
| Favicon/marks/index.html | 03 | 0 | 2 | 3 | bring-to-standard | `<body>` off stone palette → `bg-ice-2 text-ink`; og meta; evict `public/redesign.html` |
| WorkflowStub | 01, 03 | 0 | 2 | 0 | split verdict (§5) | Off-scale sizes → named scale; decide the empty-mood slot |
| App route registry | 01 | 0 | 0 | 1 | bring-to-standard | Dead `lm-loading` class; auth veil size token |
| PanelWindowApp | 01 | 0 | 0 | 1 | bring-to-standard | Share title-strip treatment with PanelHandle |
| Window chrome | 01 | 0 | 1 | 3 | bring-to-standard | Unify arrive spring w/ panels; SVG icon idiom; `z-30` container |
| NavRail | 01 | 0 | 1 | 3 | bring-to-standard | Named `mobileRail` z-rung; token-derived dividers |
| Foundation: tokens.ts/tokens.css | 00 | 0 | 2 | 3 | bring-to-standard | Wire-or-delete zero-consumer exports/vars; resolve dual night strategy |
| Foundation: lints | 00 | 0 | 4 | 3 | bring-to-standard | Baseline re-mint (120→80) + count-parity CI; referenced-token guard (S1) |
| Foundation: motion/elevation/focus/zIndex | 00 | 0 | 3 | 3 | mixed (§4) | Wire `enter`; adopt-or-delete feel-focus; drop dead `ChromeMode`/`forceAbove` |
| Foundation: index.css | 00 | 0 | 1 | 0 | bring-to-standard | `.pdf-text-layer` debug `opacity:0.18` dims its own selection highlight → `0` |
| PenguinMascot | 01 | 0 | 0 | 0 | waived | Ratified interaction model, catalogued z, still floor |
| Shell integration (arcade gate) | 02 | 0 | 0 | 0 | waived | Disciplined gating; blemishes counted on wait-arcade |
| BrainMark | 03 | 0 | 0 | 0 | waived | Token-clean, correct idiom |
| SemanticReactions | 03 | 0 | 0 | 0 | waived w/ note | Re-check 800–1300ms one-shots at the batch rename |
| AIActionFailure | 03 | 0 | 0 | 0 | waived | Contract-correct honest failure |
| CrossGraphCitations | 10 | 0† | 4 | 2 | waived | Fix by inheritance when Billing's template twin lands |
| ThreadBreadcrumb/ThreadJump | 01 | 0 | 0 | 0 | waived | Honest integrity warning; only systemic sweeps apply |
| GlassSurface | 01 | 0 | 0 | 0 | waived | The reference primitive; the finding is SceneChrome doesn't use it |
| Hotkey components (KeyChip/HotkeyHud) | 01 | 0 | 0 | 0 | waived | Binding tables honest; lies live in PanelHandle/SceneChrome |
| LinkMonster lm-skin/fonts/takeover | 12 | — | — | — | waived (aspects) | `--lm-*` palette + display fonts sanctioned in tokens.ts:388-417 |
| zIndex.ts | 00 | 0 | 0 | 1 | waived w/ one fix | Catalogue-not-migration stance documented + test-pinned; delete/wire `forceAbove` |

## 3. Work queue (highest leverage first)

| # | Item | Scope | Reports | Blast radius | Gate that proves it |
|---|---|---|---|---|---|
| Q1 | ~~**Define `ink-mute`/`ink-soft` + referenced-token-resolution guard** in lint_tokens~~ **DONE (2026-09-20, branch ui/posthog-grade-polish)** — tokens defined three-way (tokens.ts/css + tailwind.config): `ink-soft` day #2A3441 / night #C4CCD7, `ink-mute` day #647380 / night #828C9C (AA-cleared steps of the mock's #6A7785/#7C8696, which fell to 4.25/4.44:1), `danger` = emperor alias via `--danger-rgb` channels so `bg-danger/10` resolves; sun-light Tailwind mirrors added (same drift class). Guard landed as `scripts/lint_token_refs.ts` (wired into `lint:tokens`; resolves utilities against the real Tailwind theme, scoped to design-token roots; 5 grandfathered refs owned by Q2/Q3/Q7/Q13); `check_token_parity.ts` extended to pin the new families; AA pairs pinned in tokens.contrast.test.ts. Lostpixel baselines will shift — regenerate deliberately at PR time | tokens.ts, tokens.css, tailwind.config.js, scripts/lint_tokens.ts; verify ~630 refs / 146 files render | 00 F1, 01, 10–15 | App-wide; one config change + new lint; big day-mode visual delta | lint:tokens (new guard), lostpixel, vitest |
| Q2 | **`ocean` design decision, then resolve** (define as aurora-role token, or codemod to `sun-deep`/`aurora`/`ring-sun` and delete) — includes `var(--ocean)` ×12 in StyleWheel/ArtifactFeedbackReview and Write's selection accents | tokens + tailwind.config + StyleWheel.css, ArtifactFeedbackReview.css, Library, Sources/ConnectedToolSearch, BrainstormStation, Write/* | 00 F1, 10, 11, 14, 15 | 6 surfaces; blocked on design call (§5-D1) | lint:tokens guard, lostpixel, axe-core (missing focus rings today) |
| Q3 | ~~**State-color pass**~~ **DONE (2026-09-21, branch ui/posthog-grade-polish)** — `success` minted per D2 (day #237242 / night #6ECB8F, AA-cleared as text on ice-0/ice-2 + space-2/charcoal-2 and as filled-chip pairs, pinned in tokens.contrast.test.ts; three-way synced via --success-rgb channels like Q1's danger; parity guard extended); `--state-done` re-pointed aurora→success so aurora is solely AI-thinking (D8); LemonTag gained a filled `success` colour. Raw palette status colours replaced across modes/: every `bg-emerald-100 text-emerald-700` chip → `bg-success/10 text-success`, emerald filled buttons → `bg-success` (+ `dark:text-ink`) / InterviewIndex invite CTA → bg-ink primary, rose/red error+status text → `text-danger`, red-tint boxes → `bg-danger/10` + `border-danger/40`, PrivacyDashboard delete-zone rebuilt on danger tints, amber warnings/readiness → sun family (`text-sun-deep dark:text-sun`), NotebookCanvas block-kind accents → sun/sun-deep/aurora per the blocks/ mapping, dead `bg-accent` capacity bar → `bg-success`. Q4's `border-red-200 bg-red-50` error strips untouched (their scope; they landed ErrorBanner mid-pass) | Loop3, Outcomes, PrivacyDashboard, PayoutsAudit, Replay, Settings, RW chips, Stats, TrustCenter, InvestigationsIndex, Explain, CreationStudio, Backtest, Notebook | 10–15 | ~14 surfaces; pairs naturally with Q4 | lint:tokens, lostpixel, axe-core (contrast) |
| Q4 | **Shared `ErrorBanner` on emperor tints + dark pairs**; replace the 12+ copy-pasted red-200/red-50 strips and bare-line dialects; recipe from Login.css:54 | new shared component + all mode call sites | 10, 11, 12, 13, 14, 15 | 12+ modes, one component | vitest, lostpixel, axe-core |
| Q5 | **Lemon adoption + `ModePage` shell**: bespoke ink buttons → LemonButton, hand-rolled containers → LemonCard, bespoke grids → LemonTable, page bg `ice-2 dark:bg-space-2` + width tiers + rhythm | CreationStudio, Billing, Backtest, Write, SpeakInvite, Speak (PANEL ×5), Notebook, Sources, Loop3, operator surfaces; new ModePage | 10–15 | Largest PR count; clears ~⅓ of mode findings (10); kills most S4 dark-pair debt | vitest, lostpixel, axe-core |
| Q6 | ~~**Contract staleness sweep**~~ **DONE (2026-09-20, branch ui/posthog-grade-polish)** — DESIGN_LANGUAGE.md rewritten to SPR-09 weathered values (sun-deep #9C8636/#84722F, sun-glow, sunLight/rule/barAccent/glass families added), radius names corrected (tokens `sm/md/lg`; Tailwind `rounded-hog`/`rounded-hog-lg`), grandfathered count corrected (120 mint / 80 live), penguin→brain mascot throughout; brand README re-authored around BrainMascot/BrainMark/BrainPresence with the idiom lockup + BrainPresence coexistence rule, four-slot restraint kept; PROFILE.md hexes corrected to token values (sun #FFD54A→#F5DF24, space-2 #0B1020→#0D1019 ×4, tokens.ts cited); moodboard emperor/aurora/night-shadow swatches now read tokens.ts; FEEL_CONTRACT layer diagram regenerated from Z_LADDER_ORDER (all ten rungs + FloatMenu/ChunkModal/BrainPresence violations documented as Q8-owned) + D9 ambience fifth slot documented (1200ms crossfade + 31–67s drift exempt from the 800ms interaction ceiling). Deferred to their code-owning passes: mascotSceneMap brain-voice copy and tokens.ts's stale SPR-09 drift comment ride with the Q11 rename; z-call-site fixes are Q8 | docs + design dir only | 00 F2/F3/F14/F19, 01, 02, 03 | Zero runtime risk; audits now agree with code | check_token_parity, lint:tokens, vitest |
| Q7 | **Dead UI sweep**: PanelHandle phantom hotkey hints (implement or strip, feed from bindings.ts); SceneChrome dead "Ask"; Topbar dead account menu; Write `window.alert` ×4 → LemonToast; Notebook `prompt()`/`confirm()` ×8 → LemonModal; dead classes `bg-dashed`/`accent-primary`/`dark:bg-charcoal-3`/`lm-loading`; AccrualView wire-or-delete; Write Repository orphan delete; HeaderBar delete | 01, 11, 12, 14, 15 surfaces | 01, 11, 12, 14, 15 | Lying-chrome fixes; small independent diffs | vitest, lint:type |
| Q8 | **Overlay PR (shell z + modal chrome)**: ProductsLauncher → LemonModal; FloatMenu → `zIndex.popover` + chunky shadow + focus rings; ChunkModal → LemonModal; LinkMonster modal → LemonModal; named `mobileRail`/`scenePresence` rungs | 01, 03, 12, 14 | 01, 03, 12, 14 | 4 overlays + zIndex.ts | vitest, axe-core (focus trap), lostpixel |
| Q9 | **DRW state registry** → extend `shared/researchState.ts` (paused/stopping/budget_halted) and consume `researchStateStyle`; FEEL card chrome on ResearchPanel/PlanEditor/ComposeBar | DeepResearchWorkspace | 10 | Hero surface, one PR | vitest, lostpixel |
| Q10 | **Arcade reduced-motion offer**: policy `hidden→offer` with reduced cartridges; HUD type/contrast/mode fixes; per-cartridge sr-only instructions | arcade/, ResearchWaitArcade | 02 | Flagged-off surface (`VITE_WERNER_RESEARCH_WAIT_ARCADE`) | vitest (progressCartridge harness), axe-core, lostpixel |
| Q11 | **Mascot restraint beats**: Home/Biography persistent celebrate → idle / CelebrateBurst; then batch Werner→Brain rename (wrappers, `--werner-*` vars) | Home, Biography, brand/ | 03 | Two routes + rename pass | vitest, lostpixel |
| Q12 | **h-screen→h-full** on Signals/SkillRules/SkillRuleDetail/Sources/OperatorDashboard roots | 14, 13 | 14, 13 | 5 roots, one-line each | lostpixel, vitest |
| Q13 | **Lint hardening**: token baseline re-mint 120→80 + count-parity CI assertion; type baseline re-mint; extend lint_type_scale below ceiling (grandfather 1,033); rgba/hsl scan; widen parity guard beyond sun family | scripts/ | 00 F4/F5/F6/F16/F17 | CI-only | lint:tokens, lint:type (self-proving) |
| Q14 | **Type-scale snap**: codemod 10/11/12/13px → `text-xxs/xs/sm`, kill 8/9px, settle the 12.5px chrome question — after Q13 lands the baseline | app-wide (180 files) | 00 F6 + all | Big but mechanical | lint:type, lostpixel |
| Q15 | **Motion + focus adoption**: wire `enter`; codemod hand-rolled lifts → `press`/`cardLift`; off-token durations → 80/150/800; feel-focus adopt-or-delete, `ring-sun` standard; scene-ambience fifth-slot decision | app-wide + design/ | 00 F7/F8/F11, 01–03, 10–15 | Broad, low-risk | vitest, lostpixel |
| Q16 | **P2 backlog**: icon idiom unification (SVG 24-grid, drop emoji), stories for 4 surfaces, page-width tiers, BookCard hsl hue clamp, media-well token, `...` → `…` sweep, mobile TOC affordance, WrestleApp upload a11y + no-id posture | passim | 01, 02, 10–15 | Incremental | vitest, lostpixel, axe-core |

Cross-ReportCitations note: CrossGraphCitations (waived) is fixed by inheritance in
Q4/Q5 — verify explicitly when Billing lands.

## 4. Waivers

| Surface | Report | Reason |
|---|---|---|
| PenguinMascot | 01 | Ratified interaction model, documented still floor, catalogued z, clamped geometry — no contract issues |
| WorkflowStub | 01 | Honest-empty contract fully implemented; only dead-class/off-scale sizes covered by global sweeps (03 disagrees — §5-D4) |
| ThreadBreadcrumb / ThreadJump | 01 | Integrity-warning honesty, correct roles, consistent mono idiom |
| GlassSurface | 01 | It is the reference primitive; the finding belongs to SceneChrome |
| Hotkey components (KeyChip/HotkeyHud) | 01 | Binding tables honest and token-clean; the lies live in PanelHandle/SceneChrome |
| zIndex.ts | 00 | Catalogue-not-migration stance documented and test-pinned; one fix: `forceAbove` |
| Arcade shell integration (gate) | 02 | Disciplined: no chunk load when ineligible, episode-keyed reset, focus restore |
| BrainMark | 03 | Token-clean, presentational, correct idiom at rail size |
| SemanticReactions | 03 | Brain-correct copy, semantic chrome; re-check timings at the batch rename |
| AIActionFailure | 03 | Contract-correct honest failure: one sentence, framed diagnostic, in-place retry, mascot-free by rule |
| CrossGraphCitations | 10 | Operator-only POST form; inherits the Billing template fixes (Q4/Q5) |
| LinkMonster `--lm-*` palette / display fonts / takeover | 12 | Sanctioned feature-scoped tokens (tokens.ts:388-417) |

## 5. Cross-report contradictions / open design decisions

| # | Question | Positions | Decide before |
|---|---|---|---|
| D1 | Does `ocean` exist? | 00 F1: define a brand accent or delete; 11: DESIGN_LANGUAGE §5.6 rejects the SaaS-blue, use `ring-sun`; 14: define or repoint to aurora/sun-deep; 15: Write's accent language hangs on it | Q2 |
| D2 | What color is "success/met/done"? | 10/14/15: aurora per tokens.ts `state`; 11: aurora is reserved for AI-thinking and fails 1.9:1 on ice-0; 13: mint a documented `success` token | Q3 |
| D3 | Muted-token strategy | Define `ink-mute`/`ink-soft` (00, 13, 14, 15) vs sweep-rename to `text-shadow-1 dark:text-moonlight` (10, 11, 12 offer both) | Q1 |
| D4 | WorkflowStub verdict | 01 waives it; 03 assigns off-scale type fixes + the dead `empty`-mood question | Q14 + Q16 |
| D5 | Page background | 10 P1: re-point six surfaces to `ice-2/space-2`; 12 P2: one system-level decision — or bless `ice-0` as the page | Q5 |
| D6 | `border-sun` on static chrome | tokens.ts `rule` "retires yellow from the default border role" vs DESIGN_LANGUAGE §5.6 "sun-yellow edge"; 01 asks for one adjudication | Q5 |
| D7 | Landing h1 vs 24px ceiling | 13/15: drop `text-3xl` to `2xl`; 01: defensible as landing "content" — adjudicate; 03 wants one landing-h1 step across Home/Biography/SpeakIndex | Q14 |
| D8 | Aurora as generic accent | 11 (role inversion on informant), 12 (aurora-as-link, "formally promote open-thread=aurora"), 15 (aurora pre-select): enforce the reservation or promote new roles into tokens | Q2/Q3 |
| D9 | Scene ambience vs motion ceiling | 00 F11: `sceneMotion` 1200ms crossfade + 31–67s drift live outside the 800ms scale; document a fifth slot or route through tokens | Q15 |
| D10 | Arcade cartridge day/night pinning | 02: siblings pin opposite fixed modes with no exemption — pass mode in via `aliasFor(mode)` or document a cartridge-scene exemption | Q10 |

## 6. Adjudications (decided 2026-09-20, goal: PostHog-grade UI)

| ID | Decision | Rationale |
|----|----------|-----------|
| D1 | `ocean` is NOT minted. Codemod all refs: `text-ocean`/`bg-ocean`/`border-ocean` → `sun-deep` family, `ring-ocean`/`focus-visible:ring-ocean` → `ring-sun`, `var(--ocean)` → `var(--sun-deep)`. | DESIGN_LANGUAGE §5.6 rejects the SaaS-blue; the refs are dead today so nothing visible regresses; sun is the brand accent and `ring-sun` has precedent. |
| D2 | Mint a real `success` token for done/met/passed states. Must pass WCAG AA (≥4.5:1) on ice-0 and space-2 in both modes; aurora stays reserved for AI-thinking. (DONE in Q3 — day #237242 / night #6ECB8F, AA pairs pinned in tokens.contrast.test.ts.) | aurora fails contrast (1.9:1 on ice-0) and has a reserved semantic; success is a distinct recurring need across ~14 surfaces. |
| D3 | Define `ink-soft`/`ink-mute` for real (DONE in Q1, 79c51d8e5). | 630 existing call sites express clear intent; renaming is churn without benefit. |
| D4 | WorkflowStub: bring to standard (03's verdict overrides 01's waiver). | Stricter reading wins on a user-visible stub. |
| D5 | One page background app-wide: page ramp `ice-2`/`space-2` (Biography's pattern). Codemod the six card-toned pages. | Consistency beats per-surface preference; contract already implies the page ramp. |
| D6 | Static chrome borders use `rule`/`edge`. `border-sun` stays ONLY on the ratified LemonCard primitive. | tokens.ts `rule` is the newer statement; LemonCard is the ratified exception. |
| D7 | Chrome/landing h1 obeys the tested 24px ceiling (`text-2xl`). No landing exception. | The ceiling is enforced by test; undocumented exceptions are how scales drift. |
| D8 | Aurora stays reserved for AI-thinking. Link/selection/human-speaker roles that leak aurora move to sun-deep or ink-soft as context dictates. | Reservation is what makes the thinking state legible. |
| D9 | `sceneMotion` 1200ms crossfade is ambience, not interaction: document a fifth "ambience" slot in FEEL_CONTRACT rather than forcing the 800ms interaction ceiling. | Ambient drift is a different category; the ceiling guards interaction feedback. |
| D10 | Arcade cartridges follow app light/dark mode (pass mode via `aliasFor(mode)`); no fixed-mode pinning without a documented exemption. | "Function is never lost" applies to theme too. |

## 7. Wave-3 follow-ups (queued 2026-09-21)

| ID | Item | Notes |
|----|------|-------|
| Q18 | Aurora-status leftovers → success (D2): ~18 sites (FloatMenu "Saved", VoiceToDraft "Added", StartResearch "Added to corpus", PasteIngest, PersonalSpace ×3, Speak/Invites completed, CostMeter, VisualReviewPanel "Reviewed", CostConsent ×2, Attribution, Multimedia:1007, NotebooksIndex:246, DocumentsIndex:206, StyleWheel:443, api/books.ts servabilityLabel) | From Q3b handoff |
| Q19 | Aurora question/insight unification (D11 below) | BlockCard vs QuestionCardBlock inversion |
| Q20 | ThoughtPartnerPanel:259 dead `dark:bg-charcoal-3`; Reading-mode `bg-ink` chips (TocPanel/MetaReading) dark variants | Q5/Q3b handoffs |
| Q21 | lemon/README.md: add ModePage entry | Q5 handoff |

**D11 adjudication (2026-09-21):** aurora's reserved semantic widens to "AI cognition: thinking AND emergent outputs (questions, insights)" — one role. Components distinguishing questions from insights use label/icon, not a second colour. BlockCard's sun-deep=questions inversion is a bug under D11; fix in Q19. SlashMenu's "Emergent question · aurora bar" is the canonical reading.
