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

`src/design/tokens.css` is the runtime source of truth; `tokens.ts` mirrors it
(`primitive`, `semantic`) and `tailwind.config.js` exposes it. **Every Tailwind
colour key resolves to a tokens.css variable** (never a hex), and
`scripts/check_token_parity.ts` fails the build if the three disagree.

**"Paper, ink, and one sun" (2026-09-23).** Three layers:

1. **Primitives** (theme-invariant): `--sun` `#F5DF24` (+ `--sun-hover`,
   `--sun-press`, derived by lightness), the fixed pigments `--fixed-ink`
   `#0F1419` / `--fixed-ink-2` / `--fixed-paper` (what stays dark or white in
   both themes: ink on the sun, ink buttons, the dark rail, white text on a
   danger fill), `--danger-fill`, and the night ramp `--void` … `--bright`.
2. **Semantic** (what a colour is for, per theme; day is PAPER):

   | token | day | night | job |
   |---|---|---|---|
   | `--bg-page` / `--bg-card` / `--bg-inset` | `#FBF9F4` / `#FFFEFB` / `#F4F1E8` | space-2 / charcoal-2 / charcoal-1 | canvas, bounded surfaces, wells |
   | `--border-hairline` | `#E6E0D2` | `#262C38` | decorative dividers inside a surface |
   | `--border-rule` | `#8A8473` | `#6A7689` | meaningful boundaries, >= 3:1 |
   | `--text-1` / `--text-2` / `--text-3` | ink / `#4F5F70` / `#5F6B79` | bright / `#9AA3B2` / moonlight `#858F9F` | ink, secondary, metadata |
   | `--sun-ink` | `#75620F` | the sun | the brand as TEXT (never `--sun` on paper) |
   | `--teal` | `#0B7A7A` | `#3FE0DC` | links, evidence (aurora stays the AI fill) |
   | `--danger` `--success` `--stale` `--not-run` | red / green / amber / violet | lifted for night | honesty states, always with a word + icon |
   | `--focus` | ink | sun | the one `:focus-visible` ring |
   | `--keycap-edge`, `--wash`, `--mark` | | | keycap frame, tertiary hover, highlighter |

3. **Legacy aliases**: every older name (`--ice-*`, `--ink`, `--ink-mute`,
   `--emperor`, `--rule`, Tailwind `moonlight`, `charcoal-*` …) points at a
   semantic token, so call sites keep working and follow the theme. Where one
   key had two jobs the Tailwind per-utility maps split it: `text-sun-deep` is
   `--sun-ink`, `border-sun-deep` the weathered edge; `text-aurora` is teal,
   `bg-aurora` the AI fill; `bg-emperor` the white-text-safe fill,
   `text-emperor` the theme's danger; `dark:border-charcoal-1` the night rule.

**Theme.** Light / Dark / System (Settings > Appearance; default System). The
choice lives in `<html data-theme>`, set before first paint by the inline
script in `index.html`; Tailwind's `dark:` keys on that attribute and
`useTheme()` (`src/design/useTheme.ts`) is the one reactive reader. Motion has
the same shape (`data-motion`, `useMotionPreference`, `usePrefersReducedMotion`).

**Contrast is computed, not claimed.** `tokens.contrast.test.ts` resolves every
semantic pair AND the Tailwind keys call sites use, in both themes, through the
real tokens.css and config; a comment with a ratio in it is not evidence.

**Type.** Inter (interface) and JetBrains Mono (data, provenance) ship as
self-hosted variable woff2 under `src/assets/fonts` (OFL 1.1, licences beside
them), each with a metric-matched local fallback ("Inter Fallback", "JetBrains
Mono Fallback", index.css) named second in every stack so the swap does not
re-wrap lines; Charter is the reading face. Minimum text is 11px (`text-xxs`).

### SPR-01 reconciliation (2026-05-25)
`tokens.css` lagged the a11y-darkening that `tokens.ts` + `tailwind.config.js`
already carried: `shadow-1` `#64778A → #4F5F70` (6.32:1 on white) and `emperor`
`#E33C2D → #CE3623` (4.51:1 with white text). Reconciled to the canonical
values. Both clear WCAG AA; the visual delta is ~one Munsell step.
Superseded (2026-09-23, semantic layer): day danger and the danger fill are
`#B82E1C` (`--danger-fill`), not `#CE3623`. `#CE3623` measured 4.45:1 on the
inset ground and 4.30:1 on its own 10% wash over the card, below the AA bar
the contrast test holds every semantic pair to; `#B82E1C` measures 5.79 on
the page, 6.04 on the card, 5.40 on the inset, 5.16 on its wash and 6.09 under
white text. The design spec's table still lists `#CE3623`; the value awaits
the operator's ratification.

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
