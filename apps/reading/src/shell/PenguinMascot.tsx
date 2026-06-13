import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { clampRectToViewport } from "../workspace/panelLayoutLogic";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { moodKey, useSceneMood, type SceneMood } from "../scene/mood";
import { wernerMoodForScene } from "../brand/wernerSceneMap";
import { momentForTransition } from "../brand/wernerMoments";
import type { WernerMood } from "../design/tokens";
import {
  centerLaggedTarget,
  createWernerStage,
  EmoteView,
  installChoreography,
  installTargetChoreography,
  isReelSettled,
  reelStateStep,
  ROAM_REST_MAX_MS,
  ROAM_REST_MIN_MS,
  ROAM_STROLL_MS,
  useMouseFollow,
  wernerIceFishingCursor,
  type EmoteKind,
  type StageHost,
  type WernerStageController,
  WernerRig,
} from "../werner";
import "../werner/waddle.css";

/**
 * PenguinMascot (SPR-12 M3) — the project home, made playful.
 *
 * ─── RATIFIED UI MODEL — DO NOT "TIDY AWAY" ──────────────────────────
 * This interaction model is the operator's RATIFIED UI choice, recorded
 * in the master spec's open-questions register and re-stated in the
 * SPR-12 sprint page. A future maintainer must NOT merge it with the
 * bookmark, drop the waddle as "noise", or collapse it back into a rail
 * button without re-opening that decision. The contract is:
 *
 *   single-click   → FLOAT the project tab (the "shortcuts:projecttree"
 *                    workspace panel) so it hovers over the surface.
 *   double-click   → OPEN the project (navigate to /home, the unified
 *                    project home, where the tree is the spine).
 *   drag           → MOVE the mascot; its position is clamped to the
 *                    viewport (reuses panelLayoutLogic.clampRectToViewport,
 *                    the same 80px-reachable rule the floating panels use)
 *                    so it can NEVER be lost off-screen.
 *   idle           → AUTONOMOUS WADDLE (SPR-06 M5). Werner walks himself
 *                    around the viewport: every few seconds he picks a new
 *                    random spot (clamped on-screen), then strolls there via
 *                    a CSS left/top transition while the `werner-waddle` bob
 *                    plays on the mark, so he reads as actually walking — not
 *                    sliding. Between strolls he rests with the Werner
 *                    breathing sway. The roam is driven by a single chained
 *                    setTimeout (NOT a rAF loop / busy-loop): the main thread
 *                    is idle except for the one re-arm at the end of each
 *                    leg. It COLLAPSES to a static frame under
 *                    `prefers-reduced-motion: reduce` (animations.css + the
 *                    live JS guard below, which disables both the roam timer
 *                    and the drift wander — he stays put, still clickable).
 *
 * It SUPERSEDES the left-rail "+ project / New / Project tree" utility
 * button (NavRail.tsx — the RailButton labelled "New / Project tree",
 * onClick={toggleTree}, ~lines 252-259 of the pre-SPR-12 file). The
 * project tree is now reached THROUGH the Penguin, not that button.
 *
 * It is explicitly NOT the in-book bookmark. The bookmark is a SEPARATE
 * element owned by SPR-08 (the in-book reading pivot); this mascot is the
 * PROJECT home only. Do not unify the two — they answer different
 * questions ("where is my project?" vs "where was I in this book?").
 * ─────────────────────────────────────────────────────────────────────
 *
 * Many-projects rule: there is exactly ONE Penguin. It always represents
 * the ACTIVE project (the project the workspace is currently scoped to —
 * the single "shortcuts:projecttree" panel the rest of the shell already
 * treats as the one project tree). Penguins do not stack or collide; a
 * second project becomes active by switching scope, and the same single
 * Penguin then floats THAT project's tree. This mirrors the single-writer
 * / single-tree invariant the shell already holds.
 *
 * Mounted at AppShell level so it floats over the whole app, not inside
 * any one route.
 *
 * ─── SPR-05 / SPR-10 EXTENSION (steering + emote layer, additive) ───────
 * The ratified model above is UNCHANGED. This component additionally hosts
 * the Werner steering engine (src/werner/), which RIDES the same machinery
 * — one penguin, one `pos` ref, one chained-timeout roam, one reduced-motion
 * guard:
 *   - the roam's hop target is now BIASED toward the ~0.5s-lagged cursor
 *     (useMouseFollow) instead of a pure random hop; when the pointer is idle
 *     it keeps the original bounded wander. Same loop, same clamp, same
 *     class-swap, same reduced-motion early-return.
 *   - a WernerStage controller (src/werner/WernerStage.ts) exposes the
 *     imperative seam (moveTo / waddleToEl / emote / follow / idle / freeze)
 *     by driving THIS component's roam + position through a StageHost adapter
 *     — it never owns a second position.
 *   - the SPR-10 choreography listener (PRODUCT_ACTIVATE → waddle-to-control
 *     → hit emote → idle) is mounted here ONCE and torn down on unmount.
 *   - under prefers-reduced-motion the stage is frozen: no follow, no
 *     directed waddle (a small in-place acknowledgment emote instead) — the
 *     same still floor the roam already honours.
 * ───────────────────────────────────────────────────────────────────────
 */

/** The one project-tree panel id the rest of the shell already uses. */
export const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";

/**
 * The randomness source for the autonomous-roam bounded wander. Defaults to
 * Math.random; tests inject a deterministic source via __setRoamRandom so the
 * roam is reproducible.
 *
 * WHY THIS EXISTS (SPR-05): the bounded wander hops by `(random()*2 - 1) * reach`
 * on each axis. With Math.random, a hop where both axes happen to draw ≈0.5
 * lands ≈0px away — and after clamping is INDISTINGUISHABLE from the start
 * position. The pre-existing roam acceptance test ("strolls to a new on-screen
 * spot by itself") asserts the mascot MOVED, so it failed ~1/4 of runs on that
 * unlucky draw. Seeding the RNG here makes the hop deterministic (a known
 * non-zero displacement) so the test is stable, WITHOUT weakening the assertion
 * — it still proves Werner actually walks somewhere new. Production is unchanged
 * (Math.random by default).
 */
let roamRandom: () => number = Math.random;

/** TEST SEAM: install a deterministic RNG for the roam's bounded wander, and
 *  return a restore fn. Not used in production (Math.random is the default). */
export function __setRoamRandom(fn: (() => number) | null): () => void {
  const prev = roamRandom;
  roamRandom = fn ?? Math.random;
  return () => {
    roamRandom = prev;
  };
}

/** The mascot's own footprint, used to clamp its position so it stays
 *  reachable. A square a touch larger than the rendered art. */
const MASCOT_SIZE = 64;

/** Where the Penguin parks when first shown — lower-left, out of the way
 *  of the main composer but clearly in reach. Recomputed against the live
 *  viewport on mount so it is never seeded off-screen on a small window. */
function initialMascotPos(): { x: number; y: number } {
  const vw = typeof window !== "undefined" ? window.innerWidth : 1440;
  const vh = typeof window !== "undefined" ? window.innerHeight : 900;
  return clampRectToViewport(
    { x: 88, y: vh - MASCOT_SIZE - 96, width: MASCOT_SIZE, height: MASCOT_SIZE },
    { width: vw, height: vh },
  );
}

export function PenguinMascot() {
  const navigate = useNavigate();
  const reduceMotion = usePrefersReducedMotion();

  // ── ALC SPR-07 M1: the floating mascot belongs to the scene's weather. ──
  // The live scene mood (the SAME OS day/night signal the sky paints from). The
  // mascot's RESTING pose is derived from it via the pure wernerSceneMap, so
  // Werner is calmly present in his weather instead of ignoring it. (Honest
  // ceiling: the four-pose set has no daypart-distinct art — POSE_GAPS — so the
  // resting pose is `idle` in both day and night today; the OBSERVABLE
  // scene-reactivity is the one-shot MOMENT below at the day↔night transition.)
  const sceneMood = useSceneMood();
  const restingPose = wernerMoodForScene(sceneMood);
  // The transient one-shot pose a transition MOMENT flashes (nightfall/daybreak),
  // overriding the resting pose for the beat's duration, then clearing back. Null
  // = no moment playing (the steady resting pose shows). This is the ONLY
  // scene-driven motion; it does NOT touch position/roam/cursor/choreography.
  const [momentPose, setMomentPose] = useState<WernerMood | null>(null);
  // The previous scene_key, to detect a TRANSITION purely (prev→next). A ref so
  // the detector effect re-runs only on a real mood change, not every render.
  const prevSceneKey = useRef<string>(moodKey(sceneMood));
  const prevSceneMood = useRef<SceneMood>(sceneMood);
  // The single in-flight moment timer (latest-wins; cleared on a new moment +
  // unmount). One token, never a loop.
  const momentTimer = useRef<number | null>(null);

  const buttonRef = useRef<HTMLButtonElement | null>(null);
  // The bob wrapper (the span carrying the walk animation + idle wander). The
  // `werner-waddle` foot-bob is toggled on it only while Werner is mid-stroll.
  const bobRef = useRef<HTMLSpanElement | null>(null);
  // Position lives in a ref + is written straight to the DOM during a drag
  // (pointer-capture, like PanelHandle) so dragging doesn't thrash React.
  const pos = useRef(initialMascotPos());
  // SPR-03: the reel SPRING's velocity (vx/vy only — NOT a second position
  // source; `pos.current` stays the one position of record). The spring's mass
  // lives in this velocity: it ramps up off the mark and bleeds off as Werner
  // settles. Reset to rest whenever the reel disengages so re-engaging (incl.
  // after a tab-return stall) starts from zero — no carried-over lurch (M4).
  const reelVel = useRef({ vx: 0, vy: 0 });
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(false);
  // Pending single-click float, deferred so a double-click can cancel it
  // (see onClick/onDoubleClick below). null = no float pending.
  const clickTimer = useRef<number | null>(null);
  // The autonomous-roam scheduler. A single chained timeout (re-armed at the
  // end of each leg) — never a rAF loop, so the main thread stays idle
  // between strolls. Cleared on drag start, unmount, and reduced-motion.
  const roamTimer = useRef<number | null>(null);
  // Lets non-effect handlers (pointer-up) restart the roam after a drag
  // paused it, without re-running the whole effect. null under reduced motion.
  const roamRearm = useRef<((delay?: number) => void) | null>(null);

  // ── SPR-05/10 steering layer (additive). ──
  // The ~0.5s-lagged cursor pursuit. Disabled (frozen) under reduced motion so
  // there is zero involuntary follow. Read by the roam at the top of each leg.
  const follow = useMouseFollow({ disabled: reduceMotion });
  // The active emote mark, rendered over the Werner mark. Only changes when an
  // emote starts/ends (not per roam leg), so it doesn't thrash the roam.
  const [emote, setEmote] = useState<EmoteKind | null>(null);
  // Directed-walk pause flag for the roam: while the stage is walking Werner to
  // a button, the ambient roam stands down so the two don't fight the position.
  const roamPaused = useRef(false);
  // Whether the ambient roam should bias toward the cursor. Toggled via the
  // stage's follow(); on by default (the operator's "track the mouse" ask).
  const following = useRef(!reduceMotion);
  // The imperative controller (the SPR-10 seam). Created once; its StageHost
  // reuses THIS component's position + roam rather than forking a second one.
  const stageRef = useRef<WernerStageController | null>(null);
  // The roam effect's stroll primitives, handed to the StageHost so a directed
  // walkTo reuses the EXACT same position write + gait swap as the ambient
  // roam (one position source). null while reduced-motion (roam effect off).
  const strollRef = useRef<
    ((x: number, y: number, durationMs: number) => void) | null
  >(null);
  const restGaitRef = useRef<(() => void) | null>(null);

  const openTree = useWorkspace((s) => s.open);
  const setMode = useWorkspace((s) => s.setMode);
  const treeExists = useWorkspace((s) =>
    Boolean(s.panels[PROJECT_TREE_PANEL_ID]),
  );

  // Apply the current ref position to the element (used on mount, on drag,
  // and after a viewport resize re-clamp).
  const applyPos = useCallback(() => {
    const el = buttonRef.current;
    if (!el) return;
    el.style.left = `${pos.current.x}px`;
    el.style.top = `${pos.current.y}px`;
  }, []);

  useEffect(() => {
    applyPos();
  }, [applyPos]);

  // Re-clamp on viewport resize so a window shrink can never strand the
  // mascot past the edge (rigor #3: off-screen recovery, asserted).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onResize = () => {
      pos.current = clampRectToViewport(
        { ...pos.current, width: MASCOT_SIZE, height: MASCOT_SIZE },
        { width: window.innerWidth, height: window.innerHeight },
      );
      applyPos();
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [applyPos]);

  // ── Autonomous roam (SPR-06 M5). ──
  // Werner strolls to a new random on-screen spot every few seconds. One
  // chained timeout, no rAF loop. Disabled entirely under reduced motion
  // (he stays put, still clickable) and while a drag is in flight (the drag
  // owns the position). The walk itself is a CSS left/top transition; the
  // foot-bob `werner-waddle` class rides on the bob span for the duration of
  // the leg, then is removed so the resting sway takes over.
  useEffect(() => {
    if (reduceMotion || typeof window === "undefined") return;

    const STROLL_MS = wernerIceFishingCursor ? ROAM_STROLL_MS : 800;
    const REST_MIN_MS = wernerIceFishingCursor ? ROAM_REST_MIN_MS : 300;
    const REST_MAX_MS = wernerIceFishingCursor ? ROAM_REST_MAX_MS : 800;

    roamRearm.current = (delay = REST_MIN_MS) => {
      if (roamTimer.current !== null) window.clearTimeout(roamTimer.current);
      roamTimer.current = window.setTimeout(stepOnce, delay);
    };

    // Walk Werner to (x,y) over `durationMs`, gait on, position eased. The
    // SINGLE place a stroll happens — both the ambient roam (stepOnce) and the
    // stage's directed walkTo route through here, so there is exactly one
    // position write + one bob-class swap, never a forked second walker. The
    // target is clamped on-screen here so neither caller can strand him.
    const strollTo = (x: number, y: number, durationMs: number) => {
      const el = buttonRef.current;
      const bob = bobRef.current;
      if (!el) return;
      const target = clampRectToViewport(
        { x, y, width: MASCOT_SIZE, height: MASCOT_SIZE },
        { width: window.innerWidth, height: window.innerHeight },
      );
      pos.current = { x: target.x, y: target.y };
      el.style.transition = `left ${durationMs}ms ease-in-out, top ${durationMs}ms ease-in-out`;
      if (bob) {
        // The at-rest `penguin-mascot-wander` and the walking `werner-waddle`
        // both set `animation` on this one node — stacking them means the
        // later rule wins and the walk bob is silently suppressed. Swap them
        // so the feet actually bob while strolling; restore wander at rest.
        bob.classList.remove("penguin-mascot-wander");
        bob.classList.add("werner-waddle");
        // The directed gait (a fuller waddle than the ambient drift) rides
        // alongside the body bob so a waddle-to-button reads as deliberate
        // walking. Cleared at end-of-leg with the rest.
        bob.classList.add("werner-step");
      }
      applyPos();
    };

    // Drop the walk gait + transition and restore the at-rest wander. Shared
    // end-of-leg cleanup so the walk/wander invariant holds for both callers.
    const restGait = () => {
      if (bobRef.current) {
        bobRef.current.classList.remove("werner-waddle");
        bobRef.current.classList.remove("werner-step");
        bobRef.current.classList.add("penguin-mascot-wander");
      }
      if (buttonRef.current) buttonRef.current.style.transition = "";
    };
    // Expose the stroll primitives to the stage's StageHost (defined once,
    // below) without re-creating the controller per roam re-render.
    strollRef.current = strollTo;
    restGaitRef.current = restGait;

    // Bounded random wander when pointer idle or follow off. WERNER-ICE reel
    // mode handles active follow separately (no hop-biased pursuit).
    const nextHopTarget = (vw: number, vh: number) => {
      const reach = Math.max(120, Math.min(vw, vh) * 0.22);
      const reading = follow.read();
      if (
        !wernerIceFishingCursor &&
        following.current &&
        reading.target &&
        !reading.pointerIdle
      ) {
        const dx = reading.target.x - pos.current.x;
        const dy = reading.target.y - pos.current.y;
        const ease = reading.ease ?? 0.75;
        return clampRectToViewport(
          {
            x: pos.current.x + dx * ease,
            y: pos.current.y + dy * ease,
            width: MASCOT_SIZE,
            height: MASCOT_SIZE,
          },
          { width: vw, height: vh },
        );
      }
      // Idle pointer (or follow off): the original bounded wander. The RNG is
      // injectable (roamRandom) so tests get a deterministic, non-zero hop —
      // see __setRoamRandom. Production uses Math.random unchanged.
      return clampRectToViewport(
        {
          x: pos.current.x + (roamRandom() * 2 - 1) * reach,
          y: pos.current.y + (roamRandom() * 2 - 1) * reach,
          width: MASCOT_SIZE,
          height: MASCOT_SIZE,
        },
        { width: vw, height: vh },
      );
    };

    const stepOnce = () => {
      const el = buttonRef.current;
      // Don't wander mid-drag (the pointer owns position) or while the stage is
      // driving a directed walk (it owns position then) — just re-check soon.
      if (
        !el ||
        dragStart.current ||
        roamPaused.current ||
        (wernerIceFishingCursor &&
          following.current &&
          !follow.read().pointerIdle)
      ) {
        roamTimer.current = window.setTimeout(stepOnce, REST_MIN_MS);
        return;
      }
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const target = nextHopTarget(vw, vh);
      // Walk: ease the position over STROLL_MS + bob the feet while moving.
      strollTo(target.x, target.y, STROLL_MS);
      // End-of-leg: stop the bob, drop the transition (so a drag stays
      // instant), and re-arm after a randomised rest. The timer chain IS the
      // loop — no continuous work between these wake-ups.
      roamTimer.current = window.setTimeout(() => {
        // Don't fight a drag/directed-walk that began mid-leg.
        if (!dragStart.current && !roamPaused.current) restGait();
        // roamRandom (injectable) so the rest cadence is deterministic under a
        // seeded test, same as the hop above — production uses Math.random.
        const rest = REST_MIN_MS + roamRandom() * (REST_MAX_MS - REST_MIN_MS);
        roamTimer.current = window.setTimeout(stepOnce, rest);
      }, STROLL_MS);
    };

    // First hop after a short settle so the mascot doesn't lurch on mount.
    roamTimer.current = window.setTimeout(stepOnce, REST_MIN_MS);
    return () => {
      if (roamTimer.current !== null) {
        window.clearTimeout(roamTimer.current);
        roamTimer.current = null;
      }
      roamRearm.current = null;
      strollRef.current = null;
      restGaitRef.current = null;
      if (buttonRef.current) buttonRef.current.style.transition = "";
      if (bobRef.current) {
        bobRef.current.classList.remove("werner-waddle");
        bobRef.current.classList.remove("werner-step");
      }
    };
  }, [reduceMotion, applyPos, follow]);

  // ── WERNER-ICE SPR-15: reel-mode pursuit toward centered lagged hook. ──
  useEffect(() => {
    if (
      reduceMotion ||
      !wernerIceFishingCursor ||
      typeof window === "undefined"
    ) {
      return;
    }

    let raf = 0;
    let last = performance.now();
    // The reel starts from rest each time this effect (re)mounts.
    reelVel.current = { vx: 0, vy: 0 };

    // ── SPR-05: the endless fishing loop (the Scrat / Tom-&-Jerry gag). ──
    // The loop is Werner's POINTER-IDLE behaviour (master decision log: SPR-05
    // sprint page — "what Werner does when nobody is moving the mouse"). It is a
    // pure CSS keyframe cartoon (waddle.css) gated by the `werner-fishing` class
    // on the bob span; this toggle is the ONLY JS the loop needs. It rides the
    // EXISTING reel rAF below — NO second rAF, NO new timer, NO idle re-detection
    // (it reuses `reelActive`, which already folds in the existing pointer-idle
    // signal). When the reel owns Werner (pointer moving), the class is OFF; when
    // the reel stands down (pointer idle), the class is ON — exactly the
    // shouldFish() XOR: the loop and the reel never run at once (M2). Removing
    // this toggle makes Werner idle without the gag; flipping its sense would
    // make the loop fight the reel — the mutation the gating tests guard.
    const setFishingLoop = (on: boolean) => {
      bobRef.current?.classList.toggle("werner-fishing", on);
    };

    const setReelGait = (walking: boolean) => {
      const bob = bobRef.current;
      const el = buttonRef.current;
      if (!bob || !el) return;
      if (walking) {
        bob.classList.remove("penguin-mascot-wander");
        bob.classList.add("werner-waddle");
        el.style.transition = "";
      } else {
        bob.classList.remove("werner-waddle");
        bob.classList.remove("werner-step");
        bob.classList.add("penguin-mascot-wander");
      }
    };

    const tick = (now: number) => {
      // M4: clamp the per-frame gap. A tab-return / debugger-pause hands us one
      // enormous (now - last); without this clamp the spring would integrate the
      // whole stall and lurch in a straight line to catch up. (The pure spring
      // step ALSO clamps dt internally — belt + braces — but clamping here keeps
      // `last` honest for the next frame too.)
      const dt = Math.min(48, now - last);
      last = now;
      const reading = follow.read();
      const reelActive =
        following.current &&
        !reading.pointerIdle &&
        !roamPaused.current &&
        !dragStart.current &&
        reading.target;

      if (!reelActive) {
        setReelGait(false);
        // SPR-05: the reel stands down ⇒ the idle gag MAY own Werner. But the
        // reel also disengages during a drag and a directed waddle (roamPaused /
        // dragStart are folded into `reelActive` above), and the never-catch gag
        // must NOT run then — that is not the ambient-idle/pointer-idle condition
        // shouldFish() gates on. So fish only when the stand-down is genuinely
        // idle / follow-off, never during a drag or a directed walk.
        setFishingLoop(!roamPaused.current && !dragStart.current);
        // Disengaging: drop the spring's momentum so the next pull starts from
        // rest (no carried velocity to lurch with on re-engage — M4).
        reelVel.current = { vx: 0, vy: 0 };
        if (roamRearm.current && roamTimer.current === null) {
          roamRearm.current(ROAM_REST_MIN_MS);
        }
        raf = window.requestAnimationFrame(tick);
        return;
      }

      // SPR-05: the reel is engaging (pointer moving) ⇒ the loop hands Werner
      // back to reel-follow. Drop the gag within this one leg (M2: a pointer
      // move cancels the loop immediately — the class is gone before the reel
      // moves him this frame).
      setFishingLoop(false);

      if (roamTimer.current !== null) {
        window.clearTimeout(roamTimer.current);
        roamTimer.current = null;
      }

      const hook = centerLaggedTarget(reading.target, MASCOT_SIZE);
      if (!hook) {
        raf = window.requestAnimationFrame(tick);
        return;
      }

      const vw = window.innerWidth;
      const vh = window.innerHeight;
      const clamped = clampRectToViewport(
        { ...hook, width: MASCOT_SIZE, height: MASCOT_SIZE },
        { width: vw, height: vh },
      );
      // SPR-03: one critically-damped spring step. `pos.current` stays the one
      // position of record; reelVel carries only the spring's velocity. The
      // exponential fallback is one DEFAULT_REEL_CONFIG.mode flip away.
      const next = reelStateStep(
        { x: pos.current.x, y: pos.current.y, ...reelVel.current },
        { x: clamped.x, y: clamped.y },
        dt,
      );
      pos.current = { x: next.x, y: next.y };
      reelVel.current = { vx: next.vx, vy: next.vy };
      applyPos();
      setReelGait(!isReelSettled(pos.current, { x: clamped.x, y: clamped.y }));
      raf = window.requestAnimationFrame(tick);
    };

    raf = window.requestAnimationFrame(tick);
    return () => {
      window.cancelAnimationFrame(raf);
      // SPR-05: drop the gag class on teardown so a no-rAF state (unmount, or a
      // flip into reduced motion where this effect early-returns) never strands
      // Werner mid-cast with the loop class on.
      bobRef.current?.classList.remove("werner-fishing");
    };
  }, [reduceMotion, applyPos, follow]);

  // ── SPR-05/10: the WernerStage controller + SPR-10 choreography listener. ──
  // Created ONCE (empty deps). Its StageHost reuses this component's stroll /
  // position / roam-pause / follow machinery via the refs above — no second
  // position, no second roam. The choreography listener (PRODUCT_ACTIVATE →
  // waddle-to-control → hit → idle) is mounted here once and torn down on
  // unmount. Reduced-motion freeze/unfreeze is a SEPARATE effect (below) so a
  // preference flip doesn't tear down + re-create the controller.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const host: StageHost = {
      walkTo: (x, y, durationMs) => {
        // Reuse the roam's stroll primitive if it's live (motion allowed);
        // otherwise (reduced motion) the stage is frozen and never calls this.
        strollRef.current?.(x, y, durationMs);
      },
      getPos: () => ({ x: pos.current.x, y: pos.current.y }),
      setEmote: (kind) => setEmote(kind),
      setFollowing: (on) => {
        following.current = on;
      },
      setRoamPaused: (paused) => {
        roamPaused.current = paused;
        // When a directed walk ends, hand the gait back to rest so we don't
        // leave the walk classes on (the dead-frame failure mode).
        if (!paused) restGaitRef.current?.();
      },
    };
    const stage = createWernerStage(host);
    stageRef.current = stage;
    // Two activation paths feed the one stage: product activations (click OR
    // hotkey, via the shared event) and any opt-in `data-werner-target` button.
    const teardownChoreo = installChoreography(stage);
    const teardownTarget = installTargetChoreography(stage);
    return () => {
      teardownChoreo();
      teardownTarget();
      stage.dispose();
      stageRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reduced-motion / pointer-follow wiring for the stage. Freeze on reduced
  // motion (no follow, no directed waddle — the still floor); otherwise enable
  // ambient cursor-follow. Re-runs only when the preference flips.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (reduceMotion) {
      stage.freeze();
      setEmote(null);
    } else {
      stage.unfreeze();
      stage.follow(true);
    }
  }, [reduceMotion]);

  // ── ALC SPR-07 M1: fire a one-shot MOMENT on the live day↔night transition. ──
  // PURE trigger: the moment is `momentForTransition(prev, next)` of two scene
  // moods — NO Math.random, NO Date.now. When the OS day/night signal flips
  // (nightfall: day→night, daybreak: night→day), this plays the moment's
  // sanctioned pose as a brief one-shot override on the visible mascot, then
  // collapses back to the resting pose. It does NOT touch position / roam /
  // cursor / choreography (those own movement; this owns only the base POSE), so
  // it never fights them and the single-mascot model is preserved. Under
  // reduced-motion it uses the moment's designed `reducedPose` (a quiet pose, no
  // motion). Re-runs only when the scene_key changes (the prev-ref guard below).
  useEffect(() => {
    const nextKey = moodKey(sceneMood);
    if (nextKey === prevSceneKey.current) return; // no change ⇒ no beat
    const prev = prevSceneMood.current;
    prevSceneKey.current = nextKey;
    prevSceneMood.current = sceneMood;

    const moment = momentForTransition(prev, sceneMood);
    if (!moment) return; // a change that earns no beat settles quietly

    // Reduced motion: the moment is a quiet pose (reducedPose), shown for the
    // beat then cleared — no animation, the designed reduced-state.
    const pose = reduceMotion ? moment.reducedPose : moment.pose;
    setMomentPose(pose);
    if (momentTimer.current !== null) window.clearTimeout(momentTimer.current);
    momentTimer.current = window.setTimeout(() => {
      momentTimer.current = null;
      setMomentPose(null); // settle back to the resting (scene-derived) pose
    }, moment.durationMs);
  }, [sceneMood, reduceMotion]);

  // Clear any in-flight moment timer on unmount so it can't fire after teardown.
  useEffect(() => {
    return () => {
      if (momentTimer.current !== null) {
        window.clearTimeout(momentTimer.current);
        momentTimer.current = null;
      }
    };
  }, []);

  // ── Single-click: float the project tab. ──
  // Open the one project-tree panel in floating mode; if it already exists,
  // flip it to floating (the store's `open` focuses an existing id rather
  // than duplicating, so we explicitly setMode to guarantee it floats).
  const floatProjectTab = useCallback(() => {
    if (treeExists) {
      setMode(PROJECT_TREE_PANEL_ID, "floating");
    } else {
      openTree(
        "ProjectTree",
        {},
        { mode: "floating", title: "Project", id: PROJECT_TREE_PANEL_ID },
      );
    }
  }, [treeExists, setMode, openTree]);

  // ── Double-click: open the project (the unified project home). ──
  const openProject = useCallback(() => {
    navigate("/home");
  }, [navigate]);

  // ── Drag (pointer-capture, clamped — reuses the panel clamp rule). ──
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragStart.current = { x: e.clientX, y: e.clientY };
    moved.current = false;
    // Hand the position to the pointer: kill any in-flight stroll transition
    // + bob so the drag tracks the cursor 1:1 instead of easing behind it.
    if (buttonRef.current) buttonRef.current.style.transition = "";
    if (bobRef.current) {
      // Invariant: `werner-waddle` ⟺ actively strolling; otherwise the idle
      // `penguin-mascot-wander`. A drag ends the stroll, so swap back to the
      // wander (gated on reduceMotion so a reduced-motion drag stays still).
      bobRef.current.classList.remove("werner-waddle");
      if (!reduceMotion) bobRef.current.classList.add("penguin-mascot-wander");
    }
    if (roamTimer.current !== null) {
      window.clearTimeout(roamTimer.current);
      roamTimer.current = null;
    }
  }, [reduceMotion]);

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragStart.current) return;
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved.current = true;
      dragStart.current = { x: e.clientX, y: e.clientY };
      const vw = typeof window !== "undefined" ? window.innerWidth : 1440;
      const vh = typeof window !== "undefined" ? window.innerHeight : 900;
      // Same clamp the floating panels use — at least 80px of the mascot
      // stays reachable on every side, so it can't be dragged into oblivion.
      const clamped = clampRectToViewport(
        {
          x: pos.current.x + dx,
          y: pos.current.y + dy,
          width: MASCOT_SIZE,
          height: MASCOT_SIZE,
        },
        { width: vw, height: vh },
      );
      pos.current = { x: clamped.x, y: clamped.y };
      applyPos();
    },
    [applyPos],
  );

  const onPointerUp = useCallback((e: React.PointerEvent) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId);
    }
    dragStart.current = null;
    // Resume roaming from wherever the operator dropped him (no-op under
    // reduced motion — roamRearm is null then).
    roamRearm.current?.();
  }, []);

  // Single vs. double-click. Two distinct gates:
  //
  //  (1) drag gate — a click that ended a drag must NOT float the tab.
  //      `moved` (set in pointer-move) swallows it.
  //
  //  (2) click-vs-doubleclick gate — in a REAL browser a double-click
  //      dispatches click + click + dblclick, so without this the single
  //      click float would ALSO fire on every double-click, leaving a
  //      stray floating project-tree panel open after we navigate to
  //      /home. We DEFER the float behind a ~250ms timer; onDoubleClick
  //      cancels that pending timer before it fires, so a double-click
  //      opens the project cleanly with no stray float. A lone single
  //      click lets the timer elapse and floats the tab.
  const onClick = useCallback(() => {
    if (moved.current) {
      moved.current = false;
      return;
    }
    if (clickTimer.current !== null) {
      window.clearTimeout(clickTimer.current);
    }
    clickTimer.current = window.setTimeout(() => {
      clickTimer.current = null;
      floatProjectTab();
    }, 250);
  }, [floatProjectTab]);

  const onDoubleClick = useCallback(() => {
    if (clickTimer.current !== null) {
      window.clearTimeout(clickTimer.current);
      clickTimer.current = null;
    }
    openProject();
  }, [openProject]);

  // Cancel any pending single-click float if the mascot unmounts, so the
  // deferred timer can't fire after teardown.
  useEffect(() => {
    return () => {
      if (clickTimer.current !== null) {
        window.clearTimeout(clickTimer.current);
        clickTimer.current = null;
      }
    };
  }, []);

  return (
    <button
      ref={buttonRef}
      type="button"
      data-testid="penguin-mascot"
      aria-label="Project — click to float the project tree, double-click to open"
      title="Project · click to float · double-click to open · drag to move"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      // Fixed so it floats over the whole app regardless of scroll/route.
      // z below modals (100) + toasts (200) but above docked panels.
      className={
        "fixed z-[60] select-none touch-none cursor-grab active:cursor-grabbing " +
        "rounded-full p-0 border-0 bg-transparent " +
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sun"
      }
      style={{
        width: MASCOT_SIZE,
        height: MASCOT_SIZE,
        // The idle waddle/wander. The CSS `werner-idle` sway rides on the
        // mark itself (animations.css) and collapses under
        // prefers-reduced-motion there; we ALSO drop the JS-driven wander
        // class below so reduced-motion is honoured on both paths.
        left: pos.current.x,
        top: pos.current.y,
      }}
    >
      {/* The bob wrapper. At rest it carries `penguin-mascot-wander` (a small
          in-place drift on top of Werner's breathing sway); while Werner is
          mid-stroll the roam effect adds `werner-waddle` here so his feet bob
          as he walks. Both are gated/cleared under reduced motion so he is
          fully still for those users (the roam effect early-returns, and the
          wander class is dropped). The Werner mark's own `werner-idle`
          breathing keyframe is reduced-motion-guarded in animations.css. */}
      <span
        ref={bobRef}
        className={reduceMotion ? "" : "penguin-mascot-wander"}
        style={{
          display: "block",
          width: MASCOT_SIZE,
          height: MASCOT_SIZE,
          position: "relative",
        }}
      >
        {/* The base Werner mark, now the WALK-CYCLE RIG (SPR-06 M1): the
            transparent Werner art plus vector feet + flippers that animate off
            the `werner-waddle` / `werner-step` walk signal this very bob span
            carries while strolling — so his feet visibly STEP as he walks
            rather than the whole sprite sliding. The rig owns no motion source;
            it consumes the existing roam signal. When an emote is playing the
            rig is hidden behind the emote overlay so we don't stack penguins. */}
        <span style={{ visibility: emote ? "hidden" : "visible" }}>
          {/* The base pose is scene-driven (ALC SPR-07 M1): the resting pose
              derived from the live scene mood, briefly overridden by a one-shot
              transition MOMENT's pose (nightfall/daybreak) when one fires. Always
              one of the four sanctioned moods (the moment + map both guarantee
              it), so Werner.tsx's restraint guard still holds. */}
          <WernerRig
            size={MASCOT_SIZE}
            label="Project"
            mood={momentPose ?? restingPose}
          />
        </span>
        {/* The active emote (SPR-05) — an existing animated Werner mark mapped
            to the emote kind, overlaid on the mascot. Keyed by kind so a
            one-shot mark (fish / hit) remounts (restarts) per fire. The
            `werner-hit-bump` rides on the wrapper for SPR-10's Tom-&-Jerry
            button bump (still under reduced motion via waddle.css). EmoteView
            renders a STILL pose when reduceMotion, so the overlay is a quiet
            acknowledgment with no involuntary motion. */}
        {emote ? (
          <span
            key={emote}
            aria-hidden="true"
            className={
              !reduceMotion && emote === "hit" ? "werner-hit-bump" : undefined
            }
            style={{
              position: "absolute",
              inset: 0,
              display: "block",
              width: MASCOT_SIZE,
              height: MASCOT_SIZE,
            }}
          >
            <EmoteView kind={emote} size={MASCOT_SIZE} reduced={reduceMotion} />
          </span>
        ) : null}
      </span>
    </button>
  );
}

export default PenguinMascot;
