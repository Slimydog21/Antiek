# Motion — the allowed slots (U-05)

One motion system, applied consistently, with delight reserved for the
moments that matter — and a guard so it can't sprawl into noise. Motion is
**additive and bounded, never load-bearing**: no interaction may require an
animation to finish before the user can act, and everything degrades to an
instant state change under `prefers-reduced-motion: reduce`. If removing all
motion breaks a flow, the flow is wrong, not the motion.

## Where motion lives

- **Tokens** — `src/design/tokens.ts` (`motion`: durations `fast`/`base`/
  `slow` + easings `standard`/`enter`), mirrored in `tokens.css` (`--motion-*`,
  `--ease-*`) and `tailwind.config.js` (`duration-fast/base/slow`,
  `ease-standard/ease-enter`). No magic motion numbers in components.
- **Base primitives** — `src/design/motion.ts`: `press` (the offset-shadow
  hover-lift + active snap on a fill-variant Lemon surface), `cardLift` (the
  gentler group-hover nudge for a card), `enter` (a panel/modal fade-rise).
  These systematize what LemonButton + BookCard already did; they are the
  canonical vocabulary, not re-improvised per surface.
- **Signature beats** — `src/shared/delight/` (`useCelebrate` + `CelebrateBurst`):
  one reusable one-shot built on Werner's `celebrate` mood.
- **Werner poses** — `src/brand/werner/animated/animations.css`: the pose
  keyframes (U-02), with their own reduced-motion fallbacks.
- **Reduced-motion catch-all** — `src/design/motion.css`: collapses every
  transition/animation to instant under the OS reduce-motion setting.

## The allowed slots

Motion is permitted in exactly these slots and nowhere else:

1. **Base interactions** — any button / card / panel may carry the shared
   `press`, `cardLift`, or `enter` primitive. These are the always-on,
   barely-noticed tactility. Use the primitive; don't hand-roll the
   transform/shadow/duration.
2. **The four signature beats** — one per product's core payoff, all built
   on `useCelebrate` + `CelebrateBurst` (so they're one mechanism, not four).
   A beat is brief (≤ the `slow` token, 800 ms), fires once at the payoff,
   and is non-blocking:
   - `research-starts` (Research) — **wired**: `StartResearch.tsx`, fired at
     the transition into the started-and-not-failed state.
   - `draft-generates` (Write) — **filed**: adopt at the first token of a
     generated draft.
   - `biography-assembles` (Speak) — **filed**: adopt when an assembled
     biography first renders.
   - `book-opens` (Read) — **filed**: adopt on a freshly added book's first
     open.

   Only Research has a wired surface in this codebase today; the other three
   are owned by their product experience-specs and adopt this primitive at
   the trigger above when their surface lands. Resist a fifth beat — these
   four are the product's emotional high points.
3. **Werner's four mood slots** — rail `idle`, AI-working `thinking`, blank
   `empty`, completed-action `celebrate`. This is the same restraint rule as
   [`src/brand/README.md`](../../brand/README.md): never mid-content, never
   over controls, never more than one on screen. The signature beats are the
   `celebrate` slot's product-facing application.

Anything else — a list that "would look cool animated," a decorative
transition on a panel that isn't an enter — is **not** a slot. Add it to this
discussion before animating it.

## The anti-noise guard (and its honest limits)

`motion.guard.test.ts` (in this folder) is the mechanical half. It flags a
**new raw `@keyframes`** declared outside the motion system's homes
(Werner's `animations.css`, `motion.css`, `motion.ts`). A hand-rolled
keyframe is the high-signal marker that someone is improvising a new motion
vocabulary instead of reaching for the tokens/primitives.

It is baselined exactly like `scripts/lint_tokens.ts` and
`src/shared/copyLint.test.ts`: existing keyframes are grandfathered in
`motion_guard_baseline.json`, the test fails only on a NEW keyframe, and it
is green on the current tree. The baseline only ever shrinks.

```
# check (part of the normal vitest run)
npx vitest run src/design/motion/motion.guard.test.ts
# re-mint deliberately, after a keyframe is removed (the count shrinks)
MOTION_GUARD_UPDATE=1 npx vitest run src/design/motion/motion.guard.test.ts
```

**What the guard does not catch** (so review still matters): it does not flag
raw `transition:` declarations — those are pervasive, legitimate base
interactions (the Tailwind `transition-*` utilities), and flagging them would
be noise rather than signal. Nor can it judge *which* beat is appropriate, or
that a beat is brief and non-blocking. Those are the review checklist:

- Is this a base interaction (use a primitive), a signature beat (use
  `useCelebrate`), or a Werner slot? If none, it doesn't get motion.
- Does any flourish gate input or a result? It must not.
- Does it survive reduced-motion as an instant, fully-functional state?
- Is there more than one Werner on screen, or a fifth beat? Reject it.
