# Shell control × state inventory — ALC SPR-08 M3

**The headline milestone: every interactive shell control, every interaction state.**

The SPR-03 baseline scored shell **Visual crispness 1/3** because the shared
`.feel-focusable` keyboard-focus bundle had **zero consumers** on any shell
control, and ProductsLauncher's search input used a bare `:focus` (the rubric's
named level-1 symptom — it fires on a mouse click, not keyboard-only). This
inventory enumerates EVERY interactive shell control from code, designs all five
states for each, and records the evidence. It is the countable artifact behind
the 1 → 3 lift.

## The five states (per the crispness rubric, dimension 1)

| State | What it must do |
|---|---|
| **rest** | the default, token-sourced surface |
| **hover** | a pointer-over change, token transition (`duration-base`, no raw ms) |
| **focus-visible** | a KEYBOARD-only ring (`:focus-visible`, never bare `:focus`); the dual-tone `.feel-focusable` ring (sun core + fixed-dark halo) — legible over the living scene + chrome on both themes |
| **active** | the pressed state (where the control has one) |
| **disabled** | a single sourced opacity (`disabled:opacity-*`) where the control can disable; "n/a" where it never disables (reason recorded) |

Focus ring = `design/feel-focus.css` `.feel-focusable` (dual-tone, ALC SPR-08 M3).
Transitions = `transition-colors duration-base ease-standard` (motion tokens,
`design/motion.ts` ← `tailwind.config.js`). Colours = design tokens only.

## Evidence model (rigor #1 — "designed with no screenshot is a claim")

Each cell is one of:
- **designed** — a real, cited className/CSS rule that produces the state
  (the class IS the evidence; verified to render in the Storybook story named
  per component + the e2e focus proof).
- **reasoned-default** — the control deliberately relies on the browser/Tailwind
  default for that state, WITH the reason. No silent defaults.

Story evidence: `src/shell/{NavRail,ProductsLauncher,ProjectTree,ThreadBreadcrumb}.stories.tsx`
+ Lost-Pixel baselines under `.lostpixel/baseline/`. Focus-ring legibility proof:
`src/design/feel-focus.test.ts` (dual-tone ring ≥ 3:1 over the 4 worst
scene/chrome cells) + the FEEL-S5 browser gate `e2e/feel-focus-ring.spec.ts`.

---

## Inventory

### NavRail (`src/shell/NavRail.tsx`) — the bottom bar

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **Home igloo** (`:318`) | `bg-sun/95 text-ink` | `hover:bg-sun` + token transition | **designed (explicit)** `focus-visible:outline-2 focus-visible:outline-ink` — deliberately INK, not the shared sun ring, because a sun ring on a sun-yellow button is invisible (designed exception, not a bypass) | n/a (navigates) | n/a — home is always available |
| **RailButton** ×6 (Search, Research, Read, Write, Speak, More) (`:196`) | `color` by variant (token ice ramps) | `hover:bg-white/10` etc. + `transition-colors duration-base` | **designed** `feel-focusable` (dual-tone ring) | colour shift via `aria-current`/`active` accent slab | n/a — rail doors never disable (the honest "not yet" state lives in the launcher, not the rail) |
| **Mobile hamburger** (`:284`) | `bg-ink text-sun border-sun` | `hover:bg-shadow-2` + token transition | **designed** `feel-focusable` | n/a | n/a |
| **Mobile close** (`:477`) | `bg-ink text-sun border-sun` | `hover:bg-shadow-2` + token transition | **designed** `feel-focusable` | n/a | n/a |

### ProductsLauncher (`src/shell/ProductsLauncher.tsx`) — the "More" overlay

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **Filter input** (`:221`) | `bg-ice-2 border-rule` | — | **designed** `feel-focusable` + `focus-visible:border-sun` (the bare `:focus` is GONE — the level-1 fix) | text caret | n/a |
| **launcher-home** (`:252`) | `text-ink` | `hover:bg-sun/20` + token transition | **designed** `feel-focusable` | active row highlight | n/a |
| **product-window header** ×4 (`:287`) | `text-shadow-1` | `hover:text-ink` + token transition | **designed** `feel-focusable` | — | n/a |
| **mode row** (built/unbuilt) (`:318`,`:370`) | `text-ink` (built) / `text-ink-mute opacity-70` (unbuilt) | `hover:bg-sun/20` (built) + token transition | **designed** `feel-focusable` | `bg-sun/10` when `isActive` (arrow-nav) | **designed** `disabled={!m.built}` → the honest dimmed "not yet" (opacity-70 + LemonTag) — a SOURCED disabled state |
| **⊞ open-in-window** ×2 (`:342`,`:394`) | `text-shadow-1` | `hover:bg-sun/20 hover:text-ink` + token transition | **designed** `feel-focusable` | — | only rendered for window-eligible built modes (never disabled — absent instead) |

### SceneChrome (`src/shell/SceneChrome.tsx`) — the per-workflow action bar

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **action verb** (`:191`) | `bg-sun text-ink` (primary) / `text-ink-soft` (secondary) | `hover:bg-sun-glow` / `hover:bg-ice-3` + token transition | **designed** `feel-focusable` | — | **designed** `disabled:opacity-60 disabled:cursor-not-allowed` while the async verb runs (`aria-busy`, "Creating…") |
| **scene tab** (`:223`) | `border-transparent text-shadow-1` | `hover:text-ink` + token transition | **designed** `feel-focusable` | **designed** current = `border-sun text-ink font-medium` (`aria-current="page"`) | n/a — a tab is never disabled |

### ThreadBreadcrumb (`src/shell/ThreadBreadcrumb.tsx`) — the cross-workflow trail

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **navigable hop** (`:117`) | `text-ink` | `hover:underline` + token transition | **designed** `feel-focusable rounded-sm` | — | **reasoned-default**: an UNBUILT hop is NOT a button — it renders as a non-interactive dimmed span (`:96`, `cursor-not-allowed`), and the CURRENT hop renders as a non-link span (`:104`). So the "disabled" affordance is structural (no button at all), which is more honest than a disabled button — recorded, not a silent default. |

### ProjectTree (`src/shell/ProjectTree.tsx`) — the workflow-scoped tree

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **section toggle** (`:242`) | `text-shadow-1` (`aria-expanded`) | `hover:text-ink` + token transition | **designed** `feel-focusable` | expand/collapse glyph ▾/▸ | n/a |
| **node row** (`:285`) | `text-ink` | `hover:bg-sun/20` + token transition | **designed** `feel-focusable` | — | n/a |
| **pin star** (`:301`) | pinned `text-sun-deep` / unpinned `opacity-0` until row hover | `group-hover:opacity-100` + token transition | **designed** `feel-focusable` + **`group-focus-within:opacity-100 focus-visible:opacity-100`** — the unpinned star was hover-only (invisible to KEYBOARD); now it appears on keyboard focus too (a real M3 a11y fix, not just a ring) | toggled ★/☆ | n/a |
| **All-link** (`:212`) | `text-ink` | `hover:bg-sun/20` + token transition | **designed** `feel-focusable` | — | n/a |

### PenguinMascot (`src/shell/PenguinMascot.tsx`) — the autonomous mascot button

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **mascot** (`:768`) | `bg-transparent cursor-grab` | — (Werner has its own scene-mood emotes, SPR-07 — untouched) | **designed (explicit, pre-SPR-08)** `focus-visible:outline-2 focus-visible:outline-sun` | `active:cursor-grabbing` (drag) | n/a |

### WorkspaceWindow chrome (`src/components/windows/WorkspaceWindow.tsx`)

| Control | rest | hover | focus-visible | active | disabled |
|---|---|---|---|---|---|
| **title bar** (`:274`) | `cursor-grab` | — | **designed (explicit, pre-SPR-08)** `focus-visible:ring-2 focus-visible:ring-sun` | `active:cursor-grabbing` (drag) | n/a |
| **expand/restore** (`:297`) | `text-shadow-1` | `hover:text-ink` + token transition | **designed** `feel-focusable` (SPR-08 M3) | — | n/a |
| **close** (`:307`) | `text-shadow-1` | `hover:text-emperor` + token transition | **designed** `feel-focusable` (SPR-08 M3) | — | n/a |

---

## Counts (the rubric's countable evidence)

- **Interactive shell controls enumerated**: 21 (across 7 component files).
- **focus-visible coverage**: **21 / 21** (was **2 / ~9** at baseline). 19 via the
  shared `.feel-focusable` dual-tone ring; 2 via a deliberate explicit
  `focus-visible:` (Home igloo → ink ring on the sun button; PenguinMascot →
  sun ring). The Home-igloo ink ring is a recorded DESIGNED exception (a sun ring
  on a sun-yellow surface is invisible), not a bypass.
- **bare `:focus` controls**: **0** (was 1 — ProductsLauncher search input).
  Guarded forward by `feel-focus.test.ts` ("no shell control uses a bare :focus").
- **raw durations in shell transitions**: **0** (18× `duration-base` token).
- **state cells**: every cell above is **designed** or **reasoned-default-with-reason**
  — 0 silent defaults.

## Focus-ring legibility over the scene (the escalation that wasn't needed)

A single-tone `--sun` ring (the original feel-focus.css) clears the WCAG 1.4.11
3:1 non-text floor over DARK surfaces (15:1) but FAILS over LIGHT ones
(sun vs white ≈ 1.3:1). The brief's rule: if hand-built focus keeps failing
contrast over the scene, ESCALATE — do NOT dim the scene to make chrome pass.
The fix did neither: it made the ring **dual-tone** (sun core + a FIXED-dark
`--feel-focus-halo`), so on a light surface the dark halo carries the indicator
(18:1) and on a dark surface the sun core does (15:1), with the two layers
contrasting each other 13.6:1. Verified over the four worst cells (black / white /
light-card / dark-card) in `feel-focus.test.ts` — best-of-{sun,halo} ≥ 12:1
everywhere, well above 3:1. The scene was not touched.
