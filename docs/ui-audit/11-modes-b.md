# 11-modes-b :: Mode surfaces

Audit of eight mode surfaces under `apps/reading/src/modes/` against
`src/design/DESIGN_LANGUAGE.md` (Werner skin, PostHog pattern), `FEEL_CONTRACT.md`,
`tokens.ts` / `tailwind.config.js`, and `motion.ts` / `motion.css`.
`npm run lint:tokens` and `npm run lint:type` both pass (no new hex, no chrome
over 24px) — but the lints do not catch the worst problem found here: Tailwind
classes referencing colour names that **do not exist** in the config.

**Systemic context for the top finding:** `text-ink-soft`, `text-ink-mute`, and
`*-ocean` are used throughout these surfaces, yet none of `ink-soft`, `ink-mute`,
or `ocean` is defined in `tailwind.config.js` (colors: sun, sun-deep, sun-glow,
rule, bar-accent, glass, ice-*, glacial-*, shadow-*, ink, void, space-*, charcoal-*,
slate-*, moonlight, starlight, bright, aurora, emperor), `tokens.css`, or
`tokens.ts`. Tailwind v3 generates no CSS for them — they are dead classes. In day
mode the muted/lede text they were meant to tone down inherits full-strength ink,
flattening the type hierarchy on every one of these screens (night mode is saved
by the paired `dark:text-starlight`/`dark:text-moonlight`, which do exist).

## Surfaces

### DocumentsIndex
Entry: `apps/reading/src/modes/DocumentsIndex/index.tsx:31` (`DocumentsIndex`,
route-level page, `max-w-4xl` column). Operator list of substrate documents: a
serif `text-2xl` header + lede, a 5-up tier-count stat strip, a filter bar
(tier pills + free-text investigation_id input), then a `LemonTable` of documents
with `LemonTag` tier chips, linking to `/wrestle/:id`. Has loading / error /
empty states (all bare italic or banner text). Has a stories file. Uses Lemon
primitives correctly — the most Lemon-aligned of the raw indexes.

### Economics (AccrualView)
Entry: `apps/reading/src/modes/Economics/AccrualView.tsx:122`. §9 attribution /
escrow accrual card: honest-framing intro, per-contributor share list, escrow
totals, ads-explainer, and one client-gated "Try a payout" `LemonButton` that
always refuses. Loading is an italic mono line; failure renders the shared
`AIActionFailure`. Note: **no consumer mounts this component** — nothing outside
its own test imports it (checked `PanelRegistry.tsx` and the router), so it is
currently a dead surface.

### Explain
Entry: `apps/reading/src/modes/Explain/index.tsx:731` (`Explain`,
`/explain/:kind/:id`, `max-w-4xl`). Read-only provenance browser with three
panels (claim / synthesis / document): node cards, edge rows with tier +
confidence chips, chunk excerpt blocks, a `SetTierControl` disclosure (tier
select + mandatory reason + override history), and honest unresolved-pin rows.
Serif header + lede + mono id line; error banners and loading line match
DocumentsIndex. Long file (840 lines) but structurally consistent.

### Federation
Entry: `apps/reading/src/modes/Federation/index.tsx:24` (`max-w-3xl` — the
narrowest column in scope). Operator config form for cross-graph federation:
partner-substrate add/remove list, two strict-default checkboxes, dirty-state
footer with Discard/Save. Saved banner is green; error banner is red. **No
loading state** — the body is blank under the header until the fetch resolves.

### Interview (panels)
Entries: `apps/reading/src/modes/Interview/InterviewTranscript.tsx:47` and
`InterviewNotes.tsx:19`. Docked workspace panels (registered in
`workspace/PanelRegistry.tsx:101-102`), not full pages. Transcript: poll-refreshed
(10s) read-only turn list with role labels (interviewer sun-deep, informant
aurora), pending-correction inline editing. Notes: localStorage scratchpad with
debounced autosave and a privacy footer. Intentionally minimal chrome; no Lemon
primitives, no motion.

### InterviewIndex
Entry: `apps/reading/src/modes/InterviewIndex/index.tsx:40` (`max-w-5xl`,
`space-y-8` rhythm). Interview-project index: create-project form (title / topic
/ must-cover / framing), then expandable `ProjectRow` cards with must-cover
lists, invited-informant links to `/interview/:id`, and an invite form whose CTA
is a green `bg-emerald-700` button — the only green primary action in scope.

### InvestigationsIndex
Entry: `apps/reading/src/modes/InvestigationsIndex/index.tsx:33` (`max-w-5xl`).
Investigation list: start-new form (question / context / topic slug / max
sub-questions), status filter pills with a cost summary, then hand-rolled row
cards (question, id, status chip, cost, replay link) instead of the LemonTable
its sibling DocumentsIndex uses. Status chips use Tailwind emerald/red directly.

### Library
Entry: `apps/reading/src/modes/Library/index.tsx:43`. The Read door and the
strongest surface in scope: glass-scene landing via `GlassSurface` (a documented
`ELEVATION_EXEMPT_SURFACES` case) with an in-window adaptation, corpus filter
**tablist with full ARIA + arrow-key nav**, search form, `CorpusSearch` (typed +
file-drop bias with honest signal labels), `CuratePrompt`, meta-reading banner,
honest feed-ordering labels, `BookCard` shelf grid (`border-edge border-sun`,
`cardLift` motion — the only motion.ts consumer in scope), and accessible
pagination. Two internal search/browse surfaces split (`/library/browse` link +
inline form). `BookCard` placeholder spines use deterministic inline `hsl()`
gradients.

## Findings

| Severity | Location (file:line) | Issue | Fix direction |
|---|---|---|---|
| P0 | DocumentsIndex/index.tsx:86,176,192; Explain/index.tsx:83,101,243,355,706,790,795; Federation/index.tsx:119,147; InterviewIndex/index.tsx:116,273; InvestigationsIndex/index.tsx:124; Interview/InterviewTranscript.tsx:104,130,155,179; Interview/InterviewNotes.tsx:54,66,82; Economics/AccrualView.tsx:219,225,237,249,257,265,284,299,312,323; Library/index.tsx:235 | `text-ink-soft` / `text-ink-mute` are dead classes — neither name exists in tailwind.config.js, tokens.css, or tokens.ts, so no CSS is generated and every lede/metadata line renders at inherited full-ink in day mode, flattening the intended hierarchy on all 8 surfaces | Either add real `ink-soft` / `ink-mute` tokens (mirrored ts/css/config per the drift rule) or replace with the existing `text-shadow-1` / `text-shadow-2` (+ `dark:text-moonlight`) ramp |
| P0 | InvestigationsIndex/index.tsx:252-258 | Status chips reinvent the research-state family with off-palette Tailwind emerald/red (`bg-emerald-100 text-emerald-700`, `bg-red-50 text-emperor`); tokens.ts:319-328 already defines `state` (done=aurora, blocked=emperor, working=sun, muted=shadow-2). No `dark:` variants on the emerald chip | Map status → tokens.ts `state` colours, render via LemonTag (`aurora` / `danger` / `sun` / `muted`) |
| P0 | Explain/index.tsx:78-83, 97-101 | TierChip + ConfidenceChip use the Tailwind default emerald palette (`emerald-100/800/50/700`) — a colour family outside the Werner token set, with no `dark:` variants (light-green chips on charcoal at night) | Reband chips to token colours (aurora / sun-deep / ice-3 per band) or consolidate onto LemonTag; add dark variants |
| P1 | Library/index.tsx:296,299,406,410 | `focus-visible:ring-ocean` — `ocean` is not a token anywhere; the class generates nothing (ring falls back to currentColor). The *intent* is a SaaS-blue focus accent, which DESIGN_LANGUAGE §5.6 explicitly rejects | `focus-visible:ring-sun` (BookCard already does this at BookCard.tsx:40) or `ring-ink` |
| P1 | DocumentsIndex/index.tsx:137; Explain/index.tsx:803,810; Federation/index.tsx:130; InterviewIndex/index.tsx:125; InvestigationsIndex/index.tsx:213; Library/index.tsx:368 | The shared error banner `border-red-200 bg-red-50` uses off-token Tailwind reds and has no `dark:` variant — a near-white pink box on the night ramp | Token-based banner (`border-emperor/40 bg-emperor/5` + dark pair), ideally one shared Lemon callout component |
| P1 | Federation/index.tsx:136 | "Saved" banner is `text-emerald-700 border-emerald-200 bg-emerald-50` — off-palette green, no dark variant | Token success treatment (aurora family) or route through LemonToast |
| P1 | InterviewIndex/index.tsx:354 | Invite CTA is `bg-emerald-700 hover:bg-emerald-600` — a green primary inconsistent with every sibling primary action (`bg-ink`) and off-token | `bg-ink` pattern or `LemonButton variant="primary"` |
| P1 | Interview/InterviewTranscript.tsx:144-146 | Informant role label is `text-aurora`; tokens.ts:310 reserves aurora for AI-thinking states — but the informant is the human and the interviewer (the Loop 4 agent) gets sun-deep. Also aurora #16C2C2 on ice-0 ≈ 1.9:1, far below AA for the 10px uppercase label | Swap role colours (aurora only if the speaker is the AI); raise label contrast (aurora-deep or larger weight) |
| P1 | Economics/AccrualView.tsx:213 | Card chrome is `border-2 border-ink` — not the FEEL_CONTRACT opaque chunky card (`border-edge border-sun` + depth shadow) and not LemonCard | Adopt LemonCard, or `border-edge border-sun shadow-z1 dark:shadow-z1-night` |
| P1 | DocumentsIndex/index.tsx:120; InvestigationsIndex/index.tsx:199,233 | `hover:bg-ice-4 dark:bg-charcoal-1` (and `hover:bg-ice-1 dark:bg-charcoal-2`): the unconditional `dark:` background wins over the `hover:` rule in the cascade, so filter pills and rows give **zero hover feedback at night** | Add explicit `dark:hover:bg-slate-1` (or the token hover pair) |
| P1 | Explain/index.tsx:620 | Unresolved-pin card uses `border-red-300 dark:border-red-900` — off-token reds | `border-emperor/40 dark:border-emperor` dashed |
| P1 | Federation/index.tsx:111-141 | No loading state: while the config fetch is in flight the page renders only the header and blank space (siblings render an italic "Loading…" line) | Add the sibling-standard loading line |
| P2 | Federation/index.tsx:114 (max-w-3xl); DocumentsIndex/index.tsx:81 + Explain/index.tsx:784 (max-w-4xl); InterviewIndex/index.tsx:111 + InvestigationsIndex/index.tsx:119 + Library/index.tsx:206 (max-w-5xl) | Three different content-column widths across structurally identical index pages | Standardise one index column (max-w-4xl or 5xl) |
| P2 | DocumentsIndex/index.tsx:119; InvestigationsIndex/index.tsx:198; Library/index.tsx:271; InterviewIndex/index.tsx:167; Federation/index.tsx:198,267 | Active pills / primary buttons are `bg-ink text-white` with no `dark:` variant — near-black button on charcoal at night, and `text-white` is itself off-token (ice-0) | Add a dark pair (e.g. `dark:bg-bright dark:text-ink`) and use `text-ice-0` |
| P2 | DocumentsIndex/index.tsx:103,170,176; Explain/index.tsx:86,131,161; Economics/AccrualView.tsx:192,216,225; Interview/InterviewTranscript.tsx:104,127,139; InterviewIndex/index.tsx:278,287,299,321,331 | Pervasive arbitrary font sizes `text-[10px]/[11px]/[12px]/[13px]/[14px]` bypass the named app type scale (xxs/xs/sm) the config defines | Use `text-xxs` / `text-xs` / `text-sm` |
| P2 | DocumentsIndex/index.tsx:113; Federation/index.tsx:194,255,263; InterviewIndex/index.tsx:163,350; InvestigationsIndex/index.tsx:178 | Raw `<button>` chrome with hand-rolled padding/disabled styles while Economics and Library use LemonButton — two button dialects across sibling surfaces | Adopt LemonButton variants everywhere |
| P2 | Library/BookCard.tsx:48 | Placeholder spine is an inline `hsl()` gradient over an unrestricted 360° hue space — off-token colour generation, invisible to lint:tokens, can produce hues that clash with the sun edge | Constrain the hue set to token-derived families (glacial/sun-glow/slate) |
| P2 | DocumentsIndex/index.tsx:117; InvestigationsIndex/index.tsx:196; Federation/index.tsx:198; InterviewIndex/index.tsx:167 | No surface except BookCard uses motion.ts (`press`/`cardLift`/`enter`); interactive controls use bare `transition-colors`, so nothing in scope has the tactile press the design system pins | Apply `press` to primary buttons, `cardLift` to row cards |
| P2 | DocumentsIndex/index.tsx:147; Explain/index.tsx:422; Federation/index.tsx:154; InterviewIndex/index.tsx:181; InvestigationsIndex/index.tsx:223; Library/index.tsx:378 | Empty states are honest (contract-compliant) but bare italic lines; tokens.ts:302-303 reserves a mascot `empty` mood slot that no surface in scope uses | Optional: mascot "empty" treatment on the four main indexes |
| P2 | Interview/InterviewTranscript.tsx:166 | `border-ink-mute` on the correction textarea is a dead class (falls back to the DEFAULT rule border — benign but unintended) | `border-rule dark:border-charcoal-1` |
| P2 | InterviewIndex/index.tsx:111 | `space-y-8` vertical rhythm vs `space-y-6` on every other index | Align to `space-y-6` |
| P2 | Economics/AccrualView.tsx (whole file) | No production consumer imports AccrualView (only its test) — the surface is currently unmounted dead code | Wire it into the synthesis/backtest view it describes, or drop it |

## Verdicts

### DocumentsIndex — bring to standard:
1. Replace dead `text-ink-soft`/`text-ink-mute` (index.tsx:86,176,192) with real tokens.
2. Token-ise the error banner (index.tsx:137) with a dark variant.
3. Fix the dark-hover squash on filter pills (index.tsx:120) with `dark:hover:`.
4. Move arbitrary font sizes (index.tsx:103,170,176) onto the named scale.
5. Give the active pill a dark variant (index.tsx:119); adopt LemonButton + `press` for the pills.

### Economics (AccrualView) — bring to standard:
1. Fix or delete: decide whether this unmounted surface ships (wire it into the synthesis view) or goes.
2. Swap card chrome to the FEEL_CONTRACT opaque chunky card or LemonCard (AccrualView.tsx:213).
3. Replace the 14 dead `text-ink-mute` uses with `text-shadow-1`/`dark:text-moonlight`.
4. Named type scale for the arbitrary `[11px]/[12px]/[13px]` sizes.

### Explain — bring to standard:
1. Retire the emerald TierChip/ConfidenceChip palettes (index.tsx:78-83,97-101) for token colours with dark variants — this is the worst off-palette block in scope.
2. Token-ise error banners (index.tsx:803,810) and the unresolved-pin reds (index.tsx:620).
3. Replace dead soft/mute classes throughout (index.tsx:83,101,243,355,706,790,795).
4. Named type scale for the arbitrary sizes.

### Federation — bring to standard:
1. Add a loading state (index.tsx:111-141).
2. Token-ise the saved banner (index.tsx:136) and error banner (index.tsx:130).
3. Replace dead `text-ink-soft` (index.tsx:119,147); adopt LemonButton for the four raw buttons.
4. Align column width (index.tsx:114) with the sibling indexes.

### Interview (panels) — bring to standard:
1. Fix the role-colour inversion/reservation: aurora on the human informant violates tokens.ts:310 and fails contrast at 10px (InterviewTranscript.tsx:144-146).
2. Replace dead `text-ink-mute`/`border-ink-mute` (InterviewTranscript.tsx:104,130,155,166,179; InterviewNotes.tsx:54,66,82).
3. Low priority otherwise — docked-panel minimalism is intentional.

### InterviewIndex — bring to standard:
1. De-emerald the Invite CTA (index.tsx:354) to the `bg-ink`/LemonButton primary pattern.
2. Token-ise the error banner (index.tsx:125); replace dead `text-ink-soft` (index.tsx:116,273).
3. Align rhythm (`space-y-8` → `space-y-6`, index.tsx:111) and add dark variants to the create button (index.tsx:167).

### InvestigationsIndex — bring to standard:
1. Map status chips to the tokens.ts `state` family via LemonTag (index.tsx:252-258) — direct contract violation today.
2. Fix dark-hover squash on filter pills and rows (index.tsx:199,233).
3. Token-ise the error banner (index.tsx:213); replace dead lede class (index.tsx:124).
4. Consider LemonTable for the row list (DocumentsIndex precedent) and `press` on buttons.

### Library — bring to standard:
1. Replace the four dead `ring-ocean` focus rings with `ring-sun` (index.tsx:296,299,406,410).
2. Constrain BookCard's placeholder-spine hue space to token-derived colours (BookCard.tsx:48).
3. Token-ise the error banner (index.tsx:368); dark variant for the active tab pill (index.tsx:271).
4. Otherwise the reference surface in scope: glass landing, tablist ARIA, cardLift motion, honest ordering labels — siblings should converge on it.
