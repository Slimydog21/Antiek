# 12-modes-c — Mode surfaces: LinkMonster, Login, Loop3, Map, Multimedia, Notebook, NotebooksIndex, ObjectiveCard

Audit baseline: `apps/reading/src/design/DESIGN_LANGUAGE.md`, `FEEL_CONTRACT.md`,
`tokens.ts`/`tokens.css`/`tailwind.config.js`, `elevation.ts`, `motion.ts`/`motion.css`.
`npm run lint:tokens` and `npm run lint:type` both pass (80 grandfathered hex; type
ceiling clean). Zero hardcoded hex in any scoped non-test file — colour findings are
about **class-level** token use, not literals.

## Surfaces

### LinkMonster
Entry: `apps/reading/src/modes/LinkMonster/LinkMonster.tsx:63` (route `/link-monster`, lazy in `App.tsx:117`). Full-screen fixed takeover: a p5 canvas stage (`monsterSketch.ts`, Weirdmageddon-incinerator scene drawn from the registered `linkMonster` token family) behind a centered header, a bottom "paste bar = the monster's mouth", a right "Monster Menu" rail of recent feeds, and a bespoke detail modal. Reduced-motion collapses to a static scene. Chrome is plain CSS (`LinkMonster.css`) reading `--lm-*` vars.

### Login
Entry: `apps/reading/src/modes/Login/index.tsx:54`. Split "access desk" landing: left column is wordmark + Charter-serif hero + email-code form (LemonInput/LemonButton) with passkey alternative; right column is a scenic "handoff world" with a constellation orb (class names say `__werner`, the render is `renderConstellation`, not the Werner mascot), speech bubble, 3-step handoff ticket. Receipt variants (approve / approved) reuse the shell. Styles in `Login.css`, token-driven with a dark `prefers-color-scheme` block and its own reduced-motion block.

### Loop3
Entry: `apps/reading/src/modes/Loop3/index.tsx:49`. Operator checklist for the 5 RL-unlock criteria: header, 3 status tiles, one card per criterion (mono name, MET/NOT MET badge, audit-note textarea, flip button). Reads `/loop-3/status`, writes `/loop-3/checklist`. Plain Tailwind, no Lemon primitives, emerald/red default-palette colours throughout.

### Map
Entry: `apps/reading/src/modes/Map/index.tsx:67`. Static route directory: serif h1 + lede + keyboard-hint chips, then 4 grouped sections of link cards (title / mono path / description) in a 2-col grid. No data fetching, no states.

### Multimedia
Entry: `apps/reading/src/modes/Multimedia/index.tsx:201`. Three-column workbench (360px brief / fluid plan-review / 320px rail) plus a full-width approved-playback section. Heavy LemonButton/LemonInput/LemonTag/LemonTextarea use; sub-panels: `ReconciliationPanel`, `KnowledgePanel` (twin finalize + sandboxed iframe viewer), `LocalProductionPanel`, `LocalAudiblePanel`, `ActiveListeningPlayer` (Media Session API + checkpointed resume), `VisualReviewPanel` (authorize→generate→contact-sheet→attest), `VoiceSteeringInput`. Honest empty/error/loading states everywhere; offline fixture data clearly labeled "Offline example".

### Notebook
Entries: `apps/reading/src/modes/Notebook/index.tsx:30` (route `/notebook/:notebookId`, renders `NotebookCanvas.tsx` — a read-mostly block list with hover block controls, double-click/⌘Enter prose editing, and a `prompt()`-driven "+ add block" picker) and `Editor.tsx:134` (TipTap editor with slash menu + autosave, mounted as the `NotebookEditor` workspace panel via `EditorPanel.tsx`/`PanelRegistry.tsx:77`). Also `AutoNotebook.tsx:58` (`/notebook/auto/:id`, derived narrative view with honest empty state, loop nav, prompt-telemetry ledger) and `blocks/*.tsx` (nine TipTap node views, mostly LemonCard-based with sun-edge chunky chrome). Two parallel block renderers (Canvas vs TipTap) coexist and have diverged visually.

### NotebooksIndex
Entry: `apps/reading/src/modes/NotebooksIndex/index.tsx:34`. Serif header + honesty banner pointing at the auto-notebook, a "New notebook" form, content-class filter pills, and a LemonTable of notebooks (title/id, updated, LemonTag class). Loading/error/empty states present.

### ObjectiveCard
Entry: `apps/reading/src/modes/ObjectiveCard/index.tsx:323` (route `/objective`). Read-only ops document: serif header + generated-at line, then six LemonCards (dispatch tier matrix with LemonTables, gap-scoring constants, retrieval gates, quality thresholds, budget caps, reuse gate) with per-section honest "None reported" fallbacks and a read-only footer line.

## Findings

| Severity | Location (file:line) | Issue | Fix direction |
|---|---|---|---|
| P0 | `Multimedia/index.tsx:1014`, `Multimedia/index.tsx:1056` | `border-danger bg-danger/10` — `danger` is not a colour in `tailwind.config.js`; JIT emits **zero** rules (verified: compiled the config against these files, 0 matches for `danger`/`ink-mute`/`ink-soft` while `text-emperor`/`text-shadow-1` emit). The API-error box renders as a neutral grey-bordered box with default text — no danger signal at all, and the contract reserves danger to `emperor`. | `border-emperor bg-emperor/10 dark:…` or a shared Lemon error banner. |
| P0 | `Multimedia/KnowledgePanel.tsx:302`, `KnowledgePanel.tsx:314`, `KnowledgePanel.tsx:353`, `Multimedia/ReconciliationPanel.tsx:223` | `text-danger` — dead class (same proof). Error text inherits the surrounding ink/bright colour instead of reading as danger; also breaks sibling consistency (neighbours use `text-emperor`). | `text-emperor` (or a `danger` alias token → emperor in the config). |
| P0 | `ObjectiveCard/index.tsx:65,264,292,310,363`, `Notebook/Editor.tsx:390`, `Notebook/blocks/ClaimCardBlock.tsx:43`, `blocks/NoteBlock.tsx:18,27`, `blocks/QuestionCardBlock.tsx:26,31,69`, `blocks/LatexBlock.tsx:70,86`, `blocks/ImageBlock.tsx:62`, `blocks/ChatExchangeBlock.tsx:29,39,58`, `blocks/CrossDocLinkBlock.tsx:26,35`, `blocks/MasterSectionBlock.tsx:27`, `blocks/RegionEmbedBlock.tsx:44,57` | `text-ink-mute` — dead class app-wide (98 files); the muted-secondary text silently inherits full ink instead. Same for `--ink-mute`/`--ink-soft` CSS vars: defined only in the `public/redesign.html` mock, not in `tokens.css`. | Add `ink-soft`/`ink-mute` to `tailwind.config.js` colors + `tokens.css` vars (day/night pairs exist in the mock), or sweep to `text-shadow-1 dark:text-moonlight`. |
| P0 | `Loop3/index.tsx:109,163`, `Map/index.tsx:76,116`, `NotebooksIndex/index.tsx:112,119`, `Notebook/index.tsx:166`, `ObjectiveCard/index.tsx:52,165,216,243,256,261,283,316`, `AutoNotebook.tsx:69,231,484` | `text-ink-soft` — dead class (same family). Every surface lede in scope renders near-black instead of the intended soft ink; only the `dark:text-starlight` half works. | Same fix as ink-mute (one token-system patch fixes both). |
| P0 | `Loop3/index.tsx:120,156,186,217,223` | Raw Tailwind default palette for state: `border-red-200 bg-red-50`, `bg-emerald-100 text-emerald-700`, `bg-emerald-700`, `border-emerald-500 bg-emerald-50`. Violates the state-token contract (`tokens.ts` `state`: done=aurora, blocked=emperor — "state colour is a token, never a raw hex") and §5.6 (generic SaaS palette). No `dark:` variants — `bg-emerald-100`/`bg-red-50` render as glaring pastel panels at night. | Map met/unmet to the state family (`aurora` done / `shadow-2` muted, cf. `shared/researchState.ts`); error → emperor with a dark pair. |
| P1 | `ObjectiveCard/index.tsx:370`, `NotebooksIndex/index.tsx:182`, `Loop3/index.tsx:120` | Identical hand-rolled error box `text-emperor border border-red-200 bg-red-50` — mixes the emperor token with default-palette `red-*`, no `dark:` variant (bright red-50 panel on the night sky). Three copies of the same wrong component. | One shared error notice styled like `Login.css:54` (`border-left var(--emperor)` + `color-mix` veil), which is mode-correct. |
| P1 | `Notebook/NotebookCanvas.tsx:292,308,330,190` | Block-kind accents in raw default palette: `border-emerald-300` (claim), `border-amber-300` (note), `border-blue-300` (question), `hover:bg-red-50` (delete). No dark variants; also contradicts the TipTap blocks (`NoteBlock.tsx:12` uses `border-sun`, `QuestionCardBlock.tsx:20` uses `border-aurora`) — same block types, two different colour codes. | Reuse the blocks/ token mapping (sun=note, aurora=question, LemonCard=claim); delete hover → `hover:text-emperor` only. |
| P1 | `Notebook/NotebookCanvas.tsx:370,380,390,400,405,414,419` and `:183` | `window.prompt()` ×7 and `window.confirm()` for content entry/deletion — native dialogs bypass the Lemon layer (FEEL z-ladder: LemonModal at 100), no styling, no token compliance. | LemonModal-based block picker forms; LemonModal confirm for delete. |
| P1 | `Notebook/NotebookCanvas.tsx:154` | Block controls reveal is `opacity-0 group-hover:opacity-100` only — no `group-focus-within`; keyboard users tab into invisible ↑/↓/× buttons. | Add `group-focus-within:opacity-100` (and `focus-visible` rings). |
| P1 | `Map/index.tsx:108` | Dark-mode hover is a no-op: `hover:bg-ice-1 dark:bg-charcoal-2` where the page bg is already `dark:bg-charcoal-2` — cards give zero hover feedback at night. | `dark:hover:bg-charcoal-1` (one ramp step up). |
| P1 | `NotebooksIndex/index.tsx:169` | Same dead dark hover: inactive filter pill `bg-ice-3 dark:bg-charcoal-1 … hover:bg-ice-4 dark:bg-charcoal-1` — dark hover == dark base. | `dark:hover:bg-slate-1`. |
| P1 | `NotebooksIndex/index.tsx:153`, `Notebook/NotebookCanvas.tsx:102` | `bg-ink text-white` buttons: `ink` is static `#0F1419` in the Tailwind config, so at night the primary action is a near-black pill on a `#1B202A` page — the affordance nearly vanishes. Siblings use LemonButton. | LemonButton `variant="primary"` (it owns the day/night pairing). |
| P1 | `Login/Login.css:36` | Focus rings use `outline: 3px solid var(--aurora)` — aurora is a reserved accent (AI-thinking states only, `tokens.ts:309-314`). FEEL-S5 rings elsewhere are sun/ink (e.g. `SlashMenu.tsx:271` `outline-sun`, `AutoNotebook.tsx:290`). | Swap ring to `var(--sun)` / ink. |
| P1 | `Notebook/AutoNotebook.tsx:263,364`, `Notebook/NotebookLoopNav.tsx:63`, `Notebook/blocks/QuestionCardBlock.tsx:20,59` | `text-aurora`/`border-aurora` used as a generic link/accent colour ("continue in Write", "open source", question bar) — reserved-accent drift. `QuestionCardBlock` documents aurora as "the open thread colour", but that role is not in `tokens.ts`. | Links → `text-sun-deep dark:text-sun` (the `RegionEmbedBlock.tsx:35` pattern), or formally promote "open thread = aurora" into tokens. |
| P1 | `LinkMonster/LinkMonster.tsx:217-310` + `LinkMonster/LinkMonster.css:244-263` | Bespoke modal: `z-index: 20` (off the named ladder in `zIndex.ts` — below `windowBase` 40), no Escape handler, no focus trap, backdrop dismissal via `onMouseDown` only, while `LemonModal` (z=100) exists. | Port to LemonModal with an lm-skin class, or at minimum Esc + focus trap + ladder-conformant z. |
| P1 | `Notebook/Editor.tsx:389`, `Notebook/blocks/ImageBlock.tsx:67` | Off-scale arbitrary sizes: `text-[10.5px]`, `text-[13.5px]` — between every named step (xxs 10 / xs 12 / sm 14). | Snap to `text-xxs`/`text-xs`/`text-sm`. |
| P1 | `Multimedia/index.tsx:1154-1162` | "Unsourced claim guard" panel: `text-ink` / `text-shadow-2` with **no** `dark:` variants — near-black text on the night card (the `bg-sun/10` veil over `charcoal-2` does not rescue it). Every surrounding element carries the dark pair. | Add `dark:text-bright` / `dark:text-moonlight`. |
| P1 | `Multimedia/ActiveListeningPlayer.tsx:390,445,475,557,559,561`, `Multimedia/LocalAudiblePanel.tsx:183` | `text-shadow-2` without `dark:` — `#384858` on `#1B202A` ≈ 1.9:1 at night, below any readable floor (contrast with sibling lines that do carry `dark:text-moonlight`). | Add `dark:text-moonlight`. |
| P2 | `LinkMonster/LinkMonster.css:4` | Runtime `@import` of Google Fonts (Bungee Shade, Share Tech Mono) — external, render-blocking network dependency for a product surface. | Self-host the two display faces in the font pipeline (the lm skin itself is sanctioned in `tokens.ts:396`). |
| P2 | `LinkMonster/LinkMonster.tsx:55-59,174,276-295` | Emoji iconography (🖼 🎬 🎙 📝 🥨 ⚠) while sibling surfaces use lucide (`ActiveListeningPlayer.tsx:3`). Emoji render platform-dependent, off the precise register. | Lucide icons or a documented lm-glyph set. |
| P2 | `Login/Login.css:33-35,149` | Motion off-scale: `transition … 90ms ease` — the motion scale is `fast 80ms` with `ease-standard` cubic-bezier (`tokens.ts:350-360`); `ease` is neither. | `var(--motion-fast)` + `var(--ease-standard)` (tokens.css) or `duration-fast ease-standard` utilities. |
| P2 | `Login/index.tsx:449-468` + `Login.css:99-100,68-78` | The "mascot" is a `renderConstellation` sketch in classes named `__werner`/`__mascot` — name/render mismatch, and it is not the canonical `<Werner mood>` component the design language reserves for the four mascot slots. | Either render Werner or rename the classes to what they are (constellation orb). |
| P2 | `Login/Login.css:102` | `!important` ×3 on `.handoff-code` (margin/colour/font) — specificity debt against the card's own `h1`/`p` rules. | Raise selector specificity or restructure; drop `!important`. |
| P2 | `Map/index.tsx:55-59` | Group titled "Pricing + replay" contains only Pricing — stale heading (Replay mode exists in the tree but no route entry here). | Add the replay route or rename the group. |
| P2 | `Multimedia/index.tsx:1533,1543`, `VisualReviewPanel.tsx:399`, `KnowledgePanel.tsx:343` | Media wells improvise dark surfaces: `bg-charcoal-2 text-bright` (day mode too), raw `bg-black`, `bg-ink`, hardcoded `bg-white` iframe — four different answers to "media backdrop". | One deliberate "media well" treatment (void/ink) used consistently; document the white twin iframe as intentional or token it. |
| P2 | `Multimedia/index.tsx:986,1093,1176,1220,1319,1335,1439,1449,1459` (+ panels) | Busy-label ellipsis written as three dots ("Creating...") while the rest of the product uses the ellipsis character ("Unlocking…", "saving…"). | Sweep `...` → `…` in user-facing strings. |
| P2 | `Multimedia/index.tsx:836-849` | Spacing rhythm diverges from the index-surface siblings: `px-5 py-5 max-w-7xl` vs `px-8 py-10 max-w-3xl/4xl` in Loop3/Map/NotebooksIndex/ObjectiveCard. Justifiable for a 3-pane workbench, but the header block (mono eyebrow + serif 2xl inside a bordered card) also differs from the sibling header pattern. | Keep the grid; align the header treatment with siblings (or document the workbench exception). |
| P2 | `Multimedia/index.tsx`, `AutoNotebook.tsx`, `ObjectiveCard/index.tsx`, `NotebooksIndex/index.tsx`, `Map/index.tsx`, `Loop3/index.tsx` (passim) | Arbitrary `text-[11px]`/`text-[12px]`/`text-[13px]` everywhere (e.g. `Multimedia/index.tsx:847,879,944`, `AutoNotebook.tsx:263,286,477`, `ObjectiveCard/index.tsx:43,104,142`, `NotebooksIndex/index.tsx:176,215,228`, `Map/index.tsx:87,113`, `Loop3/index.tsx:154,228`, `NotebookLoopNav.tsx:41`). 11px and 13px are off the named scale entirely; 10/12px should be `text-xxs`/`text-xs`. | Snap to named scale (11→xxs or xs, 13→xs or sm). |
| P2 | `Notebook/index.tsx` vs `Notebook/Editor.tsx` | Two live implementations of the same surface: route renders `NotebookCanvas` (its own `BlockView` renderers), workspace panel renders the TipTap editor (`blocks/`). Block visuals, interactions, and empty-copy have already drifted (see claim/note/question rows above). | Converge: make `/notebook/:id` host `NotebookEditor`, delete `NotebookCanvas`'s duplicate renderers. |
| P2 | `Notebook/Editor.tsx:377-384` | SlashMenu is pinned `absolute left-6 bottom-6` of the editor container regardless of caret position; the menu itself is otherwise contract-conformant (`border-edge border-sun`, `shadow-z3`, `z-[120]` = the catalogued `popover` layer). | Position at the caret (`editor.view.coordsAtPos`). |
| P2 | `Notebook/Editor.tsx:189`, `Notebook/blocks/NoteBlock.tsx:16`, `blocks/QuestionCardBlock.tsx:24`, `blocks/MasterSectionBlock.tsx:32` | Serif prose at `text-[15px]` — between `sm` (14) and `base` (16). | `text-sm` or `text-base` (content is ceiling-exempt, but should still sit on the scale). |
| P2 | `NotebooksIndex/index.tsx:229` | `updated_at` rendered as the raw API string; `ObjectiveCard/index.tsx:364` formats with `toLocaleString()` — sibling inconsistency. | One shared date-format helper. |
| P2 | `Multimedia/KnowledgePanel.tsx:361` | `accent-primary` on the acknowledgement checkbox — `primary` is not a configured colour (dead class, same JIT proof); the checkbox falls back to the browser-default blue, the generic SaaS-blue §5.6 forbids. | `accent-sun` or a configured `primary` token. |
| P2 | All scoped index surfaces (`Loop3:103`, `Map:70`, `NotebooksIndex:106`, `ObjectiveCard:349`, `Notebook/index.tsx:131`, `Multimedia/index.tsx:836`) | Page background is `bg-ice-0 dark:bg-charcoal-2` (the *card face*) rather than the `page` alias (`ice-2` / `space-2`, `tokens.ts:230-256`). Sibling modes (`InvestigationsIndex:118`, `Stats:81`) do the same — systemic drift, not a per-surface bug; worth one system-level decision. | Decide once: re-point page bg to `ice-2 dark:bg-space-2` app-wide, or bless ice-0 as the page. |
| P2 | `Map/index.tsx`, `NotebooksIndex/index.tsx`, `Loop3/index.tsx` | Interactive cards/pills use bare `transition-colors`; none adopt the motion system's `press`/`cardLift` (`design/motion.ts:36-50`) — hover-lift is a FEEL-contract primitive (FEEL-S2/S4) and these surfaces skip it. | Apply `cardLift`/`press` to route cards and pills. |

Positive notes (already at standard): LinkMonster's honest leftover/empty/loading copy and reduced-motion collapse; Login's error notice (`Login.css:54`) is the best token-correct error treatment in scope; SlashMenu's chunky sun-edge chrome matches the FEEL opaque-card primitive exactly; Multimedia's state machine copy is honest and specific; Notebook's `NotebookEmpty` and AutoNotebook's empty/error states model the "honest empty states" principle; ObjectiveCard's per-section "None reported" fallbacks are exemplary.

## Verdicts

**LinkMonster — bring to standard:**
1. Port the detail modal to LemonModal (Esc, focus trap, ladder z) with an lm-skin override class (`LinkMonster.tsx:217-310`).
2. Self-host Bungee Shade / Share Tech Mono; drop the runtime Google Fonts `@import` (`LinkMonster.css:4`).
3. Replace emoji badges with lucide icons or a documented glyph set (`LinkMonster.tsx:55-59`).
4. (Waived: the `--lm-*` palette, display fonts-as-skin, and the full-screen takeover — all sanctioned feature-scoped tokens in `tokens.ts:388-417`.)

**Login — bring to standard:**
1. Focus ring `var(--aurora)` → `var(--sun)` (`Login.css:36`).
2. Move 90ms/ease transitions onto the motion tokens (`Login.css:33-35,149`).
3. Resolve the mascot name/render mismatch — render `<Werner mood>` or rename `__werner`/`__mascot` classes to constellation (`Login/index.tsx:298,336,455`).
4. Drop `!important` from `.handoff-code` (`Login.css:102`).

**Loop3 — bring to standard** (furthest from contract in scope):
1. Replace the emerald/red default palette with the state-token family (aurora/shadow-2/emperor) and add dark pairs (`index.tsx:120,156,186,217,223`).
2. Swap raw buttons/textarea for LemonButton/LemonTextarea (`index.tsx:166-191`).
3. Replace the dead `text-ink-soft` lede once the token is added (`index.tsx:109,163`); snap `text-[10px]`→`text-xxs`.
4. Adopt the shared emperor error notice (`index.tsx:120`).

**Map — bring to standard:**
1. Fix the dead dark hover (`index.tsx:108`).
2. Fix the stale "Pricing + replay" group (`index.tsx:55`).
3. `text-ink-soft` token fix (`index.tsx:76,116`); snap 11px→`text-xxs`.
4. Add `cardLift` to route cards (`index.tsx:106-119`).

**Multimedia — bring to standard:**
1. Fix the dead danger classes — error boxes currently render with zero danger styling (`index.tsx:1014,1056`, `KnowledgePanel.tsx:302,314,353`, `ReconciliationPanel.tsx:223`).
2. Add missing `dark:` pairs (`index.tsx:1154-1162`, `ActiveListeningPlayer.tsx:390,445,475,557-561`, `LocalAudiblePanel.tsx:183`).
3. Snap arbitrary type sizes to the named scale (11/12/13px passim).
4. One media-well token for player/candidate/iframe backdrops (`index.tsx:1533,1543`, `VisualReviewPanel.tsx:399`, `KnowledgePanel.tsx:343`).
5. `accent-primary` → configured token (`KnowledgePanel.tsx:361`); `...` → `…` sweep.

**Notebook — bring to standard:**
1. Converge the dual implementations — route `/notebook/:id` should host the TipTap editor; retire `NotebookCanvas`'s divergent block renderers (`index.tsx:146`, `NotebookCanvas.tsx:199-281` vs `blocks/`).
2. Replace `prompt()`/`confirm()` with LemonModal flows (`NotebookCanvas.tsx:370-425,183`).
3. Keyboard-reachable block controls: add `group-focus-within` (`NotebookCanvas.tsx:154`).
4. Token the block-kind accents (emerald/amber/blue → sun/aurora/LemonCard) (`NotebookCanvas.tsx:292,308,330`).
5. Snap `text-[10.5px]`/`text-[13.5px]`/`text-[15px]` to the scale (`Editor.tsx:189,389`, `ImageBlock.tsx:67`); caret-anchor the SlashMenu (`Editor.tsx:377-384`).
6. Resolve aurora-as-link drift in AutoNotebook/LoopNav (`AutoNotebook.tsx:263,364`, `NotebookLoopNav.tsx:63`).

**NotebooksIndex — bring to standard:**
1. Fix dead dark hover on filter pills (`index.tsx:169`).
2. `bg-ink text-white` create button → LemonButton primary (`index.tsx:153`).
3. Shared emperor error notice (`index.tsx:182`).
4. Format `updated_at` like ObjectiveCard does (`index.tsx:229`); `text-ink-soft` token fix (`index.tsx:112,119`).

**ObjectiveCard — bring to standard:**
1. `text-ink-mute`/`text-ink-soft` are dead classes — the muted metadata text renders full ink; fix at the token-system level, then this surface is correct as written (`index.tsx:65,264,292,310,363` et al.).
2. Shared emperor error notice with a dark pair (`index.tsx:370`).
3. Snap `text-[10px]`/`text-[11px]` to `text-xxs`/`text-xs` (`index.tsx:43,104,142,363`).
4. Otherwise the closest-to-standard surface in scope (LemonCard/LemonTable/LemonTag throughout, honest per-section empties).
