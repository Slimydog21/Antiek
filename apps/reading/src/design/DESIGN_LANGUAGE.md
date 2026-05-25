# Antiek design language — Werner skin, PostHog pattern

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
a functional question we also face. We keep the **Werner skin** — sun-yellow
edge, chunky offset shadow, Charter-serif prose, the Werner penguin — because
the researcher's-notebook identity is itself functional: it tells the user,
before they read a word, what kind of work this is. Generic SaaS-blue chrome
would misreport the product. No PostHog voice, mascot, or palette.

## Five principles

| Principle | PostHog pattern borrowed | Werner rule kept |
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

- **Brand (invariant across modes):** `sun #F5DF24` (the constant edge), `sun-deep #B89A00` (day) / `#8A7300` (night), `sun-glow`.
- **Day surface ramp:** `ice-0 #FFFFFF` → `ice-4 #DCE5ED` → `glacial-1/2` → `shadow-1 #4F5F70` → `shadow-2 #384858` → `ink #0F1419`.
- **Night surface ramp:** `void #040508` → `space-1/2` → `charcoal-1/2` → `slate-1/2` → `moonlight #6B7585` → `starlight #C4CCD7` → `bright #EEF1F6`.
- **Shadows (chunky offset):** day `z1/z2/z3 = 3/5/8px 3/5/8px 0 0 ink`; night casts the same offsets in `sun-deep` (the edge glows).
- **Radius:** `sm 4px`, `hog 6px`, `hog-lg 10px`. **Edge width:** `2.5px` (`border-edge`).
- **Type:** sans `Inter`, mono `JetBrains Mono`, **serif `Charter`** (prose — the notebook register).
- **Werner mascot:** coat = ink, belly = ice-1, **bill + feet = sun** (the visual hook). Eyes = ink (day) / starlight (night).
- **Reserved accents (sparingly, never substituting for sun):** `aurora #16C2C2` (AI-thinking), `emperor #CE3623` (danger only).

### SPR-01 reconciliation (2026-05-25)
`tokens.css` lagged the a11y-darkening that `tokens.ts` + `tailwind.config.js`
already carried: `shadow-1` `#64778A → #4F5F70` (6.32:1 on white) and `emperor`
`#E33C2D → #CE3623` (4.51:1 with white text). Reconciled to the canonical
values. Both clear WCAG AA; the visual delta is ~one Munsell step.

## The token lint — "every colour is a token"

`scripts/lint_tokens.ts` (`npm run lint:tokens`) fails on any **new** hardcoded
hex outside `tokens.ts` / `tokens.css`. Existing literals (120 at mint —
mostly Werner SVG fills + Storybook swatches) are grandfathered in
`scripts/token_lint_baseline.json`. Policy:

- The baseline only ever **shrinks**. Migrate a literal to a token, the lint
  stays green; add a new literal, it goes red.
- **Never** `--update` to silence a regression — `--update` is for a deliberate,
  reviewed change (e.g. a genuine new token-source file added to `ALLOW_FILES`).
- A new token-source file is added to `ALLOW_FILES` with a comment, not slipped
  into the baseline.

## Storybook — the visual reference

- **Design / Moodboard** — palette (day + night), shadows, typography swatches.
- **Components / Lemon / ⟨Primitive⟩** — every primitive, its variants.
- **Components / Lemon / PrimitivesShowcase** — the primitives composed.

`npm run visualtest` diffs these against the committed lost-pixel baseline; a
deliberate visual change re-mints it (operator-approved), never to hide a
regression.
