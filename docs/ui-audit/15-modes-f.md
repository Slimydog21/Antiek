# 15-modes-f — Mode surfaces: SpeakIndex, SpeakInvite, SpeakPublicBrowse, Stats, TrustCenter, WrestleApp, Write

Audited against `apps/reading/src/design/DESIGN_LANGUAGE.md` + `FEEL_CONTRACT.md` first, general craftsmanship second. Read-only; verified with `npm run lint:tokens` (green: 80 grandfathered, baseline 120 — no new hex in scope; the only hex literal in `src/modes/` is out-of-scope `ResearchWorkstation/ChatInputArea.tsx:138`).

**Cross-cutting discovery (drives most P0/P1s):** three colour tokens used throughout these surfaces — `ink-soft`, `ink-mute`, `ocean` — are **defined nowhere**: not in `tailwind.config.js` `colors`, not in `tokens.ts`, not in `tokens.css`. `--ink-soft`/`--ink-mute` exist only in the static mock `public/redesign.html:27,46`; `--ocean` exists nowhere. Tailwind therefore emits no CSS for `text-ink-soft`, `text-ink-mute`, `text-ocean`, `border-ocean`, `bg-ocean/*`, `ring-ocean/*` — they are dead classes. Effect: in day mode every "muted" line renders full-strength inherited ink (the day/night pairs like `text-ink-mute dark:text-moonlight` only half-work), and every ocean accent (selected chips, block-row left borders/tints, drop-hover rings, hover borders) renders nothing in either mode. The Write mode's entire selection/provenance accent language is currently invisible.

## Surfaces

### SpeakIndex
Entry: `src/modes/SpeakIndex/index.tsx:48` (`export default function SpeakIndex`). The Speak door: centred `max-w-2xl` column on `bg-ice-0 dark:bg-charcoal-2`, header with `BrainMascot` (44px) + serif `text-2xl` question "Who do you want to remember?", a name-input create form (chunky `border-2 border-ink shadow-z1` card) with a `LemonButton` primary submit, a private-defaults econ notice, then a three-tab `role="tablist"` (Yours / Public / Pushes) whose bodies are delegated to `Speak/lanes/*`. Create failure uses the shared `AIActionFailure`; list/feed failure is a bare mono line.

### SpeakInvite
Entry: `src/modes/SpeakInvite/index.tsx:51`. Unauthenticated invitee landing (`max-w-md`, phone-first). Full phase machine: loading / invalid / error / declined / consent / recording / done — the strongest honest-states coverage in this batch. Serif header with sun-deep mono eyebrow, private-vs-public economics asides (emperor-bordered for private), warm two-button consent (record-only primary, publish opt-in secondary, decline tertiary), then voice-first capture via `InterviewVoiceCapture` with typed fallback, transcript history in a `<details>`, and a calm footer. Buttons are hand-rolled, not Lemon.

### SpeakPublicBrowse
Entry: `src/modes/SpeakPublicBrowse/index.tsx:22`. Logged-out browse page (`max-w-2xl`): mono eyebrow "Antiek Speak", serif heading from `PUBLIC_LANE_LABELS`, live/gated subhead, sign-in + trust links, a G7 open-contribution banner (`role="note"`), the shared `PublicLane` in `visitorMode`, and an opportunities section listing ranked public projects. No mascot; error is a bare mono line.

### Stats
Entry: `src/modes/Stats/index.tsx:48`. Operator dashboard over `GET /stats`: header with raw Refresh button, then six `TABLE_GROUPS` each rendered as a `LemonCard elevation="z2"` containing a grid of nested `LemonCard elevation="z1" colour="glacial"` metric tiles (serif `text-2xl` count + mono uppercase label). Handles the window-hosted case (`useInWindow`, transparent bg) correctly. Warnings and errors use raw Tailwind palette strips (`amber-*`, `red-*`) with no dark variants; loading is an italic line.

### TrustCenter
Entry: `src/modes/TrustCenter/index.tsx:76`. Public transparency page over `GET /trust-center`: `text-3xl` serif title, live-pulled sections (ε budgets vs the §16.2 cap, deletion SLA, substrate controls, compliance, website-ads honesty, Speak economics gates, Loop-3 unlock criteria with MET/NOT-MET chips). `Section` helper with rule-top dividers. No loading state (blank page until data or error); error strip and MET chips use raw `red-*`/`emerald-*` palette with no dark variants.

### WrestleApp
Entry: `src/modes/WrestleApp/index.tsx:33`. Mode-B document wrestler: the route is now pure composition — `PanelHost` with Notes (docked-left) + CrossDocs (docked-right) starter panels once a document is loaded, `PdfViewer` in the main slot. Until then an `EmptyState` prompts PDF upload (serif `text-2xl`, LemonButton wrapping a hidden file input, load error, and a mono line showing the raw investigation id). No page chrome, no mascot — clean, near-minimal.

### Write
Entry: `src/modes/Write/WriteHome.tsx:47` (routed `/write` + `/write/:deliverableId`); the open piece composes `Outline.tsx:90` (section cards: blocks list, ModelPicker, Generate, `VoiceToDraft`, `Xray`, `WriteEditor` + shared `FloatMenu`, debounced honest autosave indicator) with a right-rail `BlockRepository.tsx:41` (search-first tap-to-add picker). Home view renders through `GlassSurface` (landing-glass) with title input, `ProjectTypeField` presets, `ConnectResearch` (auto-spawn backing investigation), piece list, and an `IdeaDump` brainstorm on-ramp; the piece view is deliberately opaque (`GlassSurface variant="solid"`). `Repository/Repository.tsx` is a shipped-but-orphaned duplicate of the picker (per BlockRepository's own docstring, line 28-31).

## Findings

| Severity | Location | Issue | Fix direction |
|---|---|---|---|
| P0 | global — e.g. `SpeakIndex/index.tsx:127,158,188,201,214`; `SpeakInvite/index.tsx:187,201,223,245,275,303,313,322,332,371,387,395,418,426,432,461,476`; `SpeakPublicBrowse/index.tsx:67,73,113,116,120,130`; `Stats/index.tsx:89`; `TrustCenter/index.tsx:139,197,291,353`; `Write/*` (~60 instances) | Phantom token family `ink-soft` / `ink-mute` / `ocean`: defined in no token source (not `tailwind.config.js`, `tokens.ts`, or `tokens.css`; only in the static mock `public/redesign.html`). All utilities are dead — day-mode muted text renders as full ink; ocean accents (selected chips, block-row borders/tints, drop rings, hover borders) never render. The Write accent language is currently invisible. | Decide the canonical names, add them to `tokens.ts` + `tokens.css` + `tailwind.config.js` together (the parity guard enforces the trio), then sweep-rename consumers. Alternatively map to existing tokens (`shadow-1`, `glacial-2`) and delete the phantom names. |
| P0 | `Stats/index.tsx:106` | Error strip `border-red-200 bg-red-50 text-emperor` — raw Tailwind palette (violates "every colour is a token") and **no dark variants**: light-pink panel on the night ramp. | One shared error-callout component (or `AIActionFailure`) on emperor/ice tokens with night variants; reuse everywhere this exact string is copy-pasted (Stats, TrustCenter, and 12+ sibling modes carry the identical line). |
| P0 | `TrustCenter/index.tsx:131` | Same off-palette, dark-broken error strip as Stats. | Same fix. |
| P0 | `Stats/index.tsx:116-120` | Warnings section mixes token (`bg-sun/10`) with raw palette (`border-amber-200`, `text-amber-900`), no dark variants — invisible/illegible at night. | Token the warning strip (sun family border + ink text, night variants) or extend `AIActionFailure` with a warning tone. |
| P0 | `TrustCenter/index.tsx:371-375` | MET/NOT-MET chips `bg-emerald-100 text-emerald-700` — off-palette, no dark variants; MET chip stays a light-green lozenge on `charcoal-2`. | Token pair for success/met states (or `bg-ice-3` + `text-ink` with an aurora edge — aurora is the sanctioned "done" per `tokens.ts` statusDot). |
| P1 | `TrustCenter/index.tsx:101` | `text-3xl` (30px) page title breaks the 24px chrome ceiling (`type-scale.test.ts` pins 2xl as the ceiling; the lint's known residual leaves named >2xl unscanned). | `text-2xl` — matches every sibling surface's h1. |
| P1 | `SpeakInvite/index.tsx:284,299,410` | Hand-rolled primary/secondary buttons (`bg-sun border-2 border-ink shadow-z1 hover:-translate-y-0.5`) duplicate `LemonButton` but miss its motion (`press`: no transition duration, no active-press, no shadow-grow) and its disabled/token discipline. | Use `LemonButton variant="primary" size="lg"` / `secondary`; the visual is already Lemon's, so this is a swap, not a redesign. |
| P1 | `SpeakInvite/index.tsx:236` | `border-emperor` on the private "No earnings" notice — emperor is reserved "danger only" (`tokens.ts:313`); a neutral-honesty notice is not danger, and it reads as alarm on the warmest page in the product. | Ink/rule border like its public sibling (line 253), keeping the emperor only on the small "No earnings" mono label if emphasis is truly needed. |
| P1 | `Write/WriteHome.tsx:103,114,120`; `Write/Outline.tsx:392` | Four `window.alert` system dialogs for trace/rewrite failures — off-system chrome (the FEEL contract puts `LemonToast` at z=200 for exactly this). | Route through `LemonToast` (or inline `AIActionFailure` where retry applies). |
| P1 | `Write/Outline.tsx:543,781`; `Write/Brainstorm/IdeaDump.tsx:119`; `Write/ContextWindow/ContextWindow.tsx:141`; `Write/SubAgentProposal.tsx:129` | Raw `bg-ink text-white` buttons instead of `LemonButton` — no press motion, ad-hoc disabled styles; inconsistent with SpeakIndex/VoiceToDraft/WrestleApp which use Lemon. | Swap to `LemonButton` (tertiary/secondary variants cover these). |
| P1 | `WrestleApp/index.tsx:173-186` | Upload affordance is a `LemonButton` with `tabIndex={-1}` wrapping a `className="hidden"` file input — keyboard/screen-reader users cannot reach the file picker at all (hidden input + unfocusable button). | Visually-hidden-but-focusable input pattern, or a real button calling `inputRef.click()`. |
| P1 | `Stats/index.tsx:99` | Refresh button `hover:bg-ice-1 dark:bg-charcoal-2` — missing `dark:hover:*`; night hover flashes the light ice-1. Also raw button where Lemon exists. | `LemonButton variant="tertiary" size="sm"`, or add the dark hover pair. |
| P1 | `SpeakIndex/index.tsx:140` | Create-form card: `border-2 border-ink` + `rounded-md` — neither the `border-edge` (2.5px) width nor the card border norm (`rule`/glass per AMS-SPR-01); a one-off chrome recipe beside LemonCard-based Stats. | Render through `LemonCard` (or match its border recipe exactly). |
| P1 | `TrustCenter/index.tsx:77-94` | No loading state: `data` starts null and only `error` is handled — the page is a blank white `h-screen` shell while fetching. Violates the honest-states principle. | Add a loading beat (skeleton sections or the shared `Thinking`). |
| P1 | `SpeakInvite/index.tsx:184,187,201,217,220(*),223,245,275,303,313,322,332,342,351,371,387,395,404,426,432,461,476` | Off-scale arbitrary type sizes throughout: `text-[10px]` (→ xxs), `text-[12px]` (→ xs), `text-[13px]`/`text-[15px]`/`text-[16px]`/`text-[18px]` (no scale rung), plus arbitrary `tracking-[0.18em]`/`[0.14em]`. Most prolific offender in the batch. | Snap each to the named scale (xxs/xs/sm/base/lg); 13px → sm or xs by role. |
| P1 | `SpeakPublicBrowse/index.tsx:67,70,73,78,94,113,116,120,127,130` | Same off-scale pattern: `text-[24px]` duplicates the `text-2xl` token (70), `text-[10/11/12/13/14/15px]` elsewhere. | `text-2xl` + named rungs. |
| P1 | `SpeakIndex/index.tsx:147,158,185,198,211` | `text-[15px]`, `text-[12px]`, tab labels `text-[11px]` — off-scale (11px is neither xxs nor xs). | `text-sm`/`text-xs`; tab labels to `text-xxs` or `text-xs`. |
| P1 | `Write/Xray.tsx:148,205,207,215,234,247` | Off-scale `text-[10/11/12/13px]` inside the provenance view. | Named rungs. |
| P1 | `Write/Outline.tsx:479,500,503` | `text-[11px]` busy note + `text-[10px]` provenance labels off-scale; block rows rely on the dead `border-ocean/50 bg-ocean/5` so the lego-block accent currently doesn't render (see P0 row 1). | Named rungs + real token once the ocean question is settled. |
| P2 | `SpeakIndex/index.tsx:174-176` | List/feed load error is a bare `font-mono text-emperor` line while create failure gets `AIActionFailure` with retry — two error dialects on one screen; no retry for the list. | `AIActionFailure` (or the shared error callout) with `onRetry={reload}`. |
| P2 | `SpeakPublicBrowse/index.tsx:89-99` vs `110` | Two card recipes on one page: the G7 banner is `rounded border-2` (no shadow), the opportunities section is `rounded-md border-2 shadow-z1`. | One card recipe for sibling asides. |
| P2 | `SpeakPublicBrowse/index.tsx:101-105` | Bare mono error line, no retry (same dialect gap as SpeakIndex). | Shared error callout + retry. |
| P2 | `Stats/index.tsx:111-113` | Loading is an italic text line; Write uses the shared `Thinking` beat. Sibling inconsistency. | `Thinking` or a skeleton grid matching the card layout. |
| P2 | `Stats/index.tsx:131-153` | Nested `LemonCard z2 → z1` is good, but metric tiles are `text-center` while everything else on the page is left-aligned — minor rhythm break. | Left-align values/labels or make centering a deliberate LemonCard variant. |
| P2 | `TrustCenter/index.tsx:352-383` | Loop-3 criteria rows duplicate the ε-budget row pattern but with different value treatment (chip vs plain mono) — fine — yet the section headers (`text-xl`, line 398) sit under a `text-3xl` title with no mascot or eyebrow, so the page reads flatter than sibling public surfaces (SpeakPublicBrowse has the eyebrow pattern). | `text-2xl` title + mono eyebrow ("Antiek · Trust") for sibling coherence. |
| P2 | `WrestleApp/index.tsx:190-193` | Raw investigation id rendered on the empty state — Speak and Write explicitly ban rendered ids ("No engineering string is shown", "NO id is ever rendered"); Wrestle breaks the house no-id posture. | Drop it, or move behind a debug `<details>`. |
| P2 | `WrestleApp/index.tsx:167` | `Load a PDF to wrestle.` h1 with no mascot/art — every other door in this batch either has the BrainMascot (SpeakIndex) or an eyebrow; the one true empty state is also the barest. | Small BrainMascot or the mono-eyebrow pattern. |
| P2 | `Write/WriteHome.tsx:186` vs `SpeakIndex/index.tsx:122` | Write home (a mode door) has no BrainMascot where SpeakIndex's door does — door-header treatment diverges. | Add the mascot + eyebrow pattern to the Write home header. |
| P2 | `Write/WriteHome.tsx:237`; `Write/ConnectResearch.tsx:179,200` | `text-ocean` "Starting your piece…" and `text-aurora`/border-aurora pre-select: ocean is dead (P0 row 1); aurora is reserved for AI-thinking, not selection state. | Token the status line; use rule/ink for pre-select or reserve aurora honestly. |
| P2 | `Write/Outline.tsx:470` | `transition-colors` on the section card with no duration token — the one raw transition in a file that otherwise imports the system's beats; `motion.ts` pins `duration-base ease-standard`. | Add `duration-base ease-standard` (or use a motion.ts primitive). |
| P2 | `Write/Repository/Repository.tsx` (whole file) | Orphaned duplicate of `BlockRepository` (its own docstring at `BlockRepository.tsx:28-31` says so) — drag-only, phantom tokens, no tap. Dead weight that will drift. | Delete once no route imports it (verify imports first). |
| P2 | `Write/Brainstorm/IdeaDump.tsx:103` | `grid-cols-3` driver columns with no responsive collapse — three textareas squeezed on phone widths (SpeakInvite is phone-first; Write should degrade as gracefully). | `grid-cols-1 sm:grid-cols-3`. |
| P2 | `Write/Brainstorm/IdeaDump.tsx:67,79,124,153,161`; `Write/ContextWindow/ContextWindow.tsx:105,153,160` | Several muted texts carry **only** the dead `text-ink-mute` with no `dark:` pair and no working day colour — they inherit ink, so the label/hint hierarchy silently flattens. | Covered by the P0 token fix; verify each instance gets its dark pair. |

## Verdicts

### SpeakIndex — bring to standard:
1. Fix the phantom `text-ink-soft`/`text-ink-mute` instances (127, 158, 188, 201, 214) once the token lands.
2. Snap off-scale sizes (147, 158, 185, 198, 211) to named rungs.
3. Unify errors: give list/feed failure the `AIActionFailure` + retry treatment (174).
4. Put the create form on the standard card recipe (140).
5. Keep — mascot header, tablist semantics, sun tab underline are the reference pattern for the other doors.

### SpeakInvite — bring to standard:
1. Replace hand-rolled buttons (284, 299, 410) with `LemonButton` to inherit the press motion and disabled tokens.
2. De-escalate the emperor border on the no-earnings notice (236).
3. Snap ~20 off-scale `text-[NNpx]` classes to the named scale.
4. Fix the 16 dead `text-ink-mute` instances with the token repair.
5. Keep — the phase machine and consent copy are the batch's best honest-states work.

### SpeakPublicBrowse — bring to standard:
1. `text-[24px]` → `text-2xl` (70); snap the other seven arbitrary sizes.
2. One card recipe for banner vs opportunities (89 vs 110).
3. Shared error callout + retry (101).
4. Consider the BrainMascot or eyebrow pattern so the public door matches the authed one.

### Stats — bring to standard:
1. Token + dark-variant the error strip (106) and warnings section (116-120); ideally one shared callout component replacing the copy-pasted `red-200/red-50` line across all modes.
2. Fix the Refresh button's missing `dark:hover` (99); use LemonButton.
3. Shared `Thinking` loading beat (111).
4. Fix `text-ink-soft` (89) with the token repair.
5. Keep — nested LemonCard usage and the `useInWindow` adaptation are exactly right.

### TrustCenter — bring to standard:
1. `text-3xl` → `text-2xl` (101): the 24px chrome ceiling.
2. Token + dark-variant the error strip (131) and MET chips (371-375).
3. Add a loading state (77-94) — currently a blank shell.
4. Fix the four `text-ink-soft` instances (139, 197, 291, 353).
5. Add the mono eyebrow for sibling coherence (optional).

### WrestleApp — bring to standard:
1. Make the upload control keyboard/screen-reader reachable (173-186): real button + ref click, or focusable hidden input.
2. Remove or hide the raw investigation id (190-193) per the house no-id posture.
3. Add a mascot/eyebrow to the empty state (167) — it's the barest door in the batch.
4. Keep — PanelHost composition and panel starters are clean.

### Write — bring to standard:
1. The phantom-token repair lands hardest here (~60 dead `ocean`/`ink-soft`/`ink-mute` instances across WriteHome, Outline, BlockRepository, Xray, SubAgentProposal, ConnectResearch, IdeaDump, ContextWindow, ProjectType, Repository) — the block-row and selection accent system is invisible until it lands.
2. Replace the four `window.alert` calls (WriteHome 103/114/120, Outline 392) with LemonToast.
3. Swap raw `bg-ink` buttons to LemonButton (Outline 543/781, IdeaDump 119, ContextWindow 141, SubAgentProposal 129).
4. Snap off-scale sizes in Xray/Outline to named rungs.
5. Resolve `Repository/Repository.tsx` (orphaned duplicate — delete after import check).
6. Mascot/eyebrow on the home header (186); aurora pre-select → a non-reserved token (ConnectResearch 200); `duration-base` on Outline's transition (470); responsive IdeaDump grid (103).
7. Keep — GlassSurface landing-vs-solid split, honest autosave indicator, and FloatMenu/Xray reuse are the strongest contract alignment in the batch.
