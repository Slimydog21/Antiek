# Werner the Fixed Station — cursor is the bait, penguin doesn't chase it

**Status:** design ratified by the operator 2026-07-02 (fourth `/infinite` addendum, session
`a49bc81b`); implemented on branch `feat/werner-fixed-station`.
**Supersedes:** `docs/htmlspec/werner-ice-fishing-cursor/operator-acceptance.md` **criterion #3**
("Werner reels toward the lagged hook") — PR #54, 2026-06-02. See §5.

---

## 1. The one wrong thing

The WERNER-ICE work (SPR-13–16, PR #54) built two things at once:

1. **The cursor is the bait** — the system cursor is hidden and replaced by a worm-and-hook
   (`WernerIceBait`), and a fishing line hangs from Werner's rod tip to that bait
   (`WernerFishingLayer`). This is *right* and the operator re-affirms it verbatim ("the bait of
   it fishing").
2. **Werner reels toward the cursor** — a critically-damped spring (`reelPursuit.ts`) drove
   Werner's own position toward the ~0.5 s-lagged cursor every animation frame
   (`PenguinMascot.tsx`, the SPR-15 reel effect). This is the thing the operator is now
   reversing: *"fix the cursor … to not let the penguin follow the cursor."*

The reel is the **only** load-bearing element that must die. It is hard-to-vary in the Deutsch
sense: once you fix Werner in place, every other piece — the bait, the line, the gag, the click
contract, the reduced-motion floor — keeps its exact reason for existing. Nothing else has to
change to make "the penguin doesn't chase the cursor" true, and nothing else *can* change without
losing something the operator explicitly wants.

## 2. The model, stated once

Werner stands at a **station** — a fixed point (seeded lower-left, drag-repositionable,
re-clamped on resize). He never travels to the cursor. Instead:

> **The cursor is the end of Werner's fishing line.** He is the fisherman; the cursor is his bait.

Two ambient states, split by the existing pointer-idle signal (`useMouseFollow.pointerIdle`,
`POINTER_IDLE_MS = 2000`). This is the *same XOR* the reel/gag already used — we only swap what
sits on the "pointer active" side of it:

| Pointer | Before (reel) | After (station) |
|---|---|---|
| **Active** (moving) | Werner *reels toward* the lagged cursor | Werner stays put; a line hangs from his rod tip to the cursor-bait (`WernerFishingLayer` + `WernerIceBait`). The cursor **is** the bait. |
| **Idle** (still ≥ 2 s) | Werner runs the never-catch gag at his own ice-hole | *Unchanged* — Werner runs the never-catch gag at his own ice-hole (`FISHING_BEATS`). |

The idle behaviour is **untouched**: it was already "what Werner does when nobody moves the
mouse" (the SPR-05 decision log). Only the active behaviour inverts — from *chase* to *cast a
line to where you are*.

## 3. Why the line must be gated on pointer-active (a non-obvious consequence)

Under the reel, when the pointer went idle Werner had *already reeled onto the bait*, so his rod
tip coincided with the cursor and the viewport line collapsed to zero length — invisible. With a
**fixed** Werner that coincidence never happens: his rod tip is far from the idle cursor, so the
viewport line would draw a long strand to the stale cursor **at the same time** as the own-hole
gag plays its own short line — two lines from one rod, visually broken.

So `WernerFishingLayer` gains one term: it hides the rod-tip→cursor line when `pointerIdle`. This
restores the exclusivity the reel used to provide for free (line ⊕ gag), and it is *required* by
the fixed rod tip, not a stylistic choice. The rod-swing gag animates its own line inside the
rod's rotating coordinate frame (`.werner-rig-line`, a child of `[data-werner-rod]`); the viewport
line is computed from the *geometric* tip (`rodTipFromMascotRect`, which ignores the CSS rotation)
— so the two lines must never be on together, exactly as the gag/reel were never on together.

## 4. What is preserved, and why each earns its place

- **Cursor-as-bait substrate** (`WernerIceBait`, `WernerIceCursorShell`, `ice-fishing.css`,
  `html.werner-ice-cursor-hidden`): the operator's affirmed model. The bait is the user's *only*
  cursor (system cursor is `none`), so it is always shown while the flag is on and motion is
  allowed — never hidden on idle, or the user would lose their pointer.
- **Fishing-line geometry** (`fishingLineGeometry.ts` — catenary, shared `ROD_TIP_LOCAL`): now
  anchored to a *stationary* tip, so the line is steadier, not different. Gains importance as the
  primary active visual.
- **The never-catch gag** (`FISHING_BEATS` in `wernerState.ts`, `waddle.css` `.werner-fishing`
  tracks, the rig's rod/own-fish/own-line in `WernerRig.tsx`): the "cool animation." Its ratified
  invariant — *there is no "caught" beat, it loops forever* — is unchanged and still test-pinned.
- **Click / double-click / drag contract** (SPR-12): single-click floats the project tree,
  double-click opens `/home`, drag repositions **the station** (clamped 80 px-reachable). Drag
  staying is what makes "fixed" not mean "stuck in one operator-chosen corner."
- **Reduced-motion floors** (three CSS guards + the JS `usePrefersReducedMotion` guards): Werner
  is fully still but clickable. The station's ambient gag collapses to a static frame the same way
  the roam did.
- **Directed choreography** (`choreography.ts`, `WernerStage`): a click on an activated control
  still makes Werner waddle to it, bump it, and **return to his station**. This is click-driven,
  not cursor-following, and it is the seed of the "other UI instances / mini-game feel" the
  operator wants. Return-to-station is new and small: the station is home; excursions come home.

## 5. What dies, and the honest supersession

Deleted (each was *only* ever the reel's machinery):

- `reelPursuit.ts` + `reelPursuit.test.ts` (the spring/exponential pursuit integrator + its suite)
- The SPR-15 reel effect and `reelVel` ref in `PenguinMascot.tsx`
- The autonomous-roam *wander* (Werner no longer walks himself around — he is fixed) and the
  legacy roam cursor-bias
- The `following` default-on ref + `stage.follow(true)` call (the "track the mouse" enable)
- `PenguinMascot.iceFishing.test.tsx` + `PenguinMascot.iceFishing.integration.test.tsx` (the
  950 ms/24 px synthetic reel handoff-budget suites; the mounted "a bare pointermove moves the
  penguin" pin — which is precisely the behaviour we are removing)
- The reel/roam re-exports and constants (`iceFishingConstants.ts` reel+roam values, `index.ts`
  reel surface)

**Supersession, stated in the open:** WERNER-ICE operator-acceptance **criterion #3** — *"Werner
reels toward the lagged hook (~0.5 s behind), not the live cursor"* — is **retired**. It was a
genuine, signed acceptance criterion; the operator has re-opened that decision on 2026-07-02. The
old acceptance doc is annotated with a pointer to this file rather than edited away, so the
history stays legible. Criteria #1, #2, #6, #7 (cursor hidden, bait tracks pointer, line from rod
tip, drag repositions, reduced-motion no involuntary follow) survive unchanged; #4/#5 (handoff-lag
/ idle-hop-roam) are moot because there is no reel handoff and no roam.

## 6. The StageHost seam hazard (implementation note, not design)

`strollTo` / `restGait` — the single position-write + gait-swap primitive — were defined *inside*
the now-deleted roam effect and published via `strollRef` / `restGaitRef`. `WernerStage.walkTo`
silently no-ops if they are null. So the rework **re-homes** these primitives to a stable scope
(they are still needed for directed waddles), rather than deleting them with the roam. Deleting
the roam without re-homing them would make every waddle-to-button a dead no-op — the exact trap
this note exists to prevent.

## 7. Roadmap (out of scope this session, seeds for a Fable-5 spec)

The operator gestured at more than fishing: *"other UI instances that connect to the club-penguin
mini-game feel, easter eggs like Black Ops Zombies arcade."* This session ships the **fishing**
activity correctly and leaves the station **extensible**: a station can host *N* ambient
activities, each expressing the cursor as an extension of that activity. A follow-up spec (to be
authored on Fable 5 when credits return) should define the activity registry, the easter-egg
trigger surface, and at least one non-fishing activity — built on this same "Werner fixed, cursor
is the instrument" spine.
