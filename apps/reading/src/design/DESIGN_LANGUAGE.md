# Antiek design language — sun-yellow skin, PostHog pattern

The operating manual for every interface decision in `apps/reading/`. Read it
before adding a component, a colour, or a screen. It is the human-readable
companion to the machine-readable enforcers: `tokens.ts` (source of truth),
`tokens.css` (CSS sibling), `tailwind.config.js` (utilities), and
`scripts/lint_tokens.ts` (the "no decoration" gate).

## The standard: function, not taste

Every element earns its place by the work it does toward the product's
constitutive purpose — research, read, write, speak on one substrate, the
flywheel turning one graph entity through all four. The only admissible
justification for an element is the work it does. "It looks considered,"
"other tools do it," "I prefer it" are not justifications. Form follows
function tightly enough that the design is *hard to vary*: change a function
and its form must change; keep a function and you could not have done it much
otherwise. Decoration is what is left when an element does no work.

## §5.6 — the rule we never break

> PostHog's design pattern transfers; its tone does not.

We borrow PostHog's *forms* (content-first navigation, keyboard-first density,
scene-as-object-with-views, honest empty states) because each is the answer to
a functional question we also face. We keep the **Antiek skin** — sun-yellow
edge, chunky offset shadow, Charter-serif prose, the coral brain mascot —
because the researcher's-notebook identity is itself functional: it tells the
user, before they read a word, what kind of work this is. Generic SaaS-blue
chrome would misreport the product. No PostHog voice, mascot, or palette.

## Five principles

| Principle | PostHog pattern borrowed | Antiek rule kept |
|---|---|---|
| **Content over tools** | navigate a tree of what you made; pin a few; push the rest to a launcher + ⌘K | the "things" are insight nodes, books, deliverables, interviews — substrate entities with provenance, not generic files |
| **Keyboard-first** | ⌘K indexes everything; dense, fast; trackpad optional | the palette searches the graph (claims, notes, investigations), with serif previews |
| **Scene = object + its views** | one object, tabbed views | a Research investigation = Synthesis / Trajectory / Sources / Notebook; synthesis renders in Charter serif, claim spans inline |
| **Honest empty states** | unbuilt sections say so; no fake data | "not yet — shipping in ⟨sprint⟩," keyed to real build presence; researcher's-notebook calm, no marketing |
| **Density with restraint** | information-dense list/table surfaces | sun-yellow edge + chunky offset shadow as the brand mark; whitespace where prose lives |

## Canonical tokens

`src/design/tokens.ts` is the source of truth. `tokens.css` mirrors it as CSS
variables (for Storybook + raw CSS); `tailwind.config.js` exposes it as
utilities. **These three must agree** — drift is a bug.

- **Brand (invariant across modes):** `sun #F5DF24` (the constant edge + bottom-bar day accent — never softened), `sun-deep #9C8636` (day) / `#84722F` (night) (weathered SPR-09 hover/depth; night also casts the offset shadows), `sun-glow #F1E08F` (day) / `#F2DE9A` (night) (weathered highlight peaks).
- **Weathered sun-light family (SPR-09):** `sun-light #E8D98C` (calm straw the chrome leans on), `sun-light-soft #F0E6B8`, `sun-light-deep #9C8636`. Theme-invariant by design.
- **Chrome border + bar accent (SPR-01):** `rule #788596` (day) / `#606C7E` (night) — the default border is a calm neutral blue-grey, *not* yellow (adjudication D6: `border-sun` survives only on the ratified LemonCard primitive); `bar-accent` keeps the yellow loud on the bottom bar (`sun` day, pinned `#FFEC5F` night).
- **Glass (scene panels):** `glass` — translucent panel fill/hairline/12px blur per mode, with an opaque `glass-solid` fallback; body text over glass must keep WCAG AA 4.5:1 (scrim contract in tokens.ts).
- **Day surface ramp:** `ice-0 #FFFFFF` → `ice-4 #DCE5ED` → `glacial-1/2` → `shadow-1 #4F5F70` → `shadow-2 #384858` → `ink #0F1419`.
- **Night surface ramp:** `void #040508` → `space-1/2` → `charcoal-1/2` → `slate-1/2` → `moonlight #6B7585` → `starlight #C4CCD7` → `bright #EEF1F6`.
- **Muted-text hierarchy (Q1):** `ink-soft` (lede/secondary; day `#2A3441`, night `starlight #C4CCD7`) → `ink-mute` (metadata/tertiary; day `#647380`, night `#828C9C` — the AA-cleared steps; both clear WCAG AA 4.5:1 on their usual card/page surfaces in both modes).
- **Shadows (chunky offset):** day `z1/z2/z3 = 3/5/8px 3/5/8px 0 0 ink`; night casts the same offsets in `sun-deep #84722F` (the edge glows, weathered).
- **Radius:** `sm/md/lg = 4/6/10px` in tokens.ts; Tailwind exposes the two larger steps as `rounded-hog` (6px) / `rounded-hog-lg` (10px). **Edge width:** `2.5px` (`border-edge`).
- **Type:** sans `Inter`, mono `JetBrains Mono`, **serif `Charter`** (prose — the notebook register).
- **Brain mascot (shipped):** the mark is the coral brain — warm coral-pink body, soft-black eyes/stick limbs, rosy cheeks; full palette + hard rules in `src/brand/mascot-brain/PROFILE.md` (the Krea character bible). `BrainMascot.tsx` renders the four moods (`idle`/`thinking`/`empty`/`celebrate`); `BrainMark.tsx` is the geometric line-brain rail mark. The `mascot` palette still exported from tokens.ts is legacy mascot chrome, pending the batch rename pass.
- **Reserved accents (sparingly, never substituting for sun):** `aurora #16C2C2` (day) / `#3FE0DC` (night) (AI cognition only — thinking AND emergent outputs such as questions and insights, one role per adjudication D11 widening D8; components telling questions from insights do so by label/icon, never a second colour), `emperor #CE3623` (day) / `#FF6155` (night) (danger only — also exposed under its semantic alias `danger`, same values day + night).
- **State colours (Q3, adjudication D2):** `success #237242` (day) / `#6ECB8F` (night) — the done/met/passed green, AA-cleared as text on ice-0/ice-2 and space-2/charcoal-2 (aurora fails that floor and stays reserved for AI cognition, D8/D11); the research-state family aliases it (`--state-done` = `var(--success)`), with `working` = sun, `blocked` = emperor, `stopped/muted` = shadow-2.

### SPR-01 reconciliation (2026-05-25)
`tokens.css` lagged the a11y-darkening that `tokens.ts` + `tailwind.config.js`
already carried: `shadow-1` `#64778A → #4F5F70` (6.32:1 on white) and `emperor`
`#E33C2D → #CE3623` (4.51:1 with white text). Reconciled to the canonical
values. Both clear WCAG AA; the visual delta is ~one Munsell step.

### SPR-09 re-tone (weathered sun)
`sun-deep`/`sun-glow`/`sun-highlight` were re-toned from the loud lemon depths
to weathered ochre/straw (`sun-deep` `#B89A00/#8A7300 → #9C8636/#84722F`);
`sun.base` and the bottom-bar accent stay loud by operator decision.
`tailwind.config.js` resolves `sun-deep`/`sun-glow` and the night shadow keys
through `var(--sun-deep)`/`var(--sun-glow)`, so the three sources cannot drift
on this family again — `scripts/check_token_parity.ts` asserts it.

## The token lint — "every colour is a token"

`scripts/lint_tokens.ts` (`npm run lint:tokens`) fails on any **new** hardcoded
hex outside `tokens.ts` / `tokens.css`. Existing literals (120 at mint, 80 live
at the 2026-09-20 audit and only shrinking since — the dead entries are
mascot-era SVG fills migrated to tokens, and re-minting the baseline down is
a deliberate reviewed pass, not a silencing) are grandfathered in
`scripts/token_lint_baseline.json`. Policy:

- The baseline only ever **shrinks**. Migrate a literal to a token, the lint
  stays green; add a new literal, it goes red.
- **Never** `--update` to silence a regression — `--update` is for a deliberate,
  reviewed change (e.g. a genuine new token-source file added to `ALLOW_FILES`).
- A new token-source file is added to `ALLOW_FILES` with a comment, not slipped
  into the baseline.

The same `npm run lint:tokens` also runs the **referenced-token-resolution
guard** (`scripts/lint_token_refs.ts`, Q1): any `text-/bg-/border-/ring-`
utility that names a design-token family (a custom Tailwind colour key or a
tokens.css colour var, including numbered-ramp stems) but resolves to nothing
fails the lint — the structural fix for the ~630 unstyled `ink-soft`/`ink-mute`/
`danger` references this queue item closed.

## Storybook — the visual reference

- **Design / Moodboard** — palette (day + night), shadows, typography swatches.
- **Components / Lemon / ⟨Primitive⟩** — every primitive, its variants.
- **Components / Lemon / PrimitivesShowcase** — the primitives composed.

`npm run visualtest` diffs these against the committed lost-pixel baseline; a
deliberate visual change re-mints it (operator-approved), never to hide a
regression.
