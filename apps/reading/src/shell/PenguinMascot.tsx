import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { clampRectToViewport } from "../workspace/panelLayoutLogic";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { useWorkspace } from "../workspace/WorkspaceStore";
import {
  createWernerStage,
  EmoteView,
  installChoreography,
  installLivingTvAmbient,
  installReactionBus,
  installTargetChoreography,
  notifyPointerIdleEdge,
  useMouseFollow,
  useStationActivity,
  wernerIceFishingCursor,
  type EmoteKind,
  type StageHost,
  type WernerStageController,
  WernerRig,
  emitWernerExperience,
} from "../werner";
import "../werner/waddle.css";

/**
 * PenguinMascot (SPR-12 M3) — the project home, made playful.
 *
 * ─── RATIFIED UI MODEL — DO NOT "TIDY AWAY" ──────────────────────────
 * This interaction model is the operator's RATIFIED UI choice, recorded
 * in the master spec's open-questions register and re-stated in the
 * SPR-12 sprint page. A future maintainer must NOT merge it with the
 * bookmark, drop it as "noise", or collapse it back into a rail button
 * without re-opening that decision. The contract is:
 *
 *   single-click   → FLOAT the project tab (the "shortcuts:projecttree"
 *                    workspace panel) so it hovers over the surface.
 *   double-click   → OPEN the project (navigate to /home, the unified
 *                    project home, where the tree is the spine).
 *   drag           → MOVE THE STATION; its position is clamped to the
 *                    viewport (reuses panelLayoutLogic.clampRectToViewport,
 *                    the same 80px-reachable rule the floating panels use)
 *                    so it can NEVER be lost off-screen. Dragging is what
 *                    keeps "fixed" from meaning "stuck in one corner" — the
 *                    operator can re-station Werner anywhere.
 *
 * It SUPERSEDES the left-rail "+ project / New / Project tree" utility
 * button (NavRail.tsx). The project tree is now reached THROUGH the
 * Penguin, not that button.
 *
 * It is explicitly NOT the in-book bookmark (owned by SPR-08). Do not
 * unify the two — they answer different questions ("where is my project?"
 * vs "where was I in this book?").
 * ─────────────────────────────────────────────────────────────────────
 *
 * Many-projects rule: there is exactly ONE Penguin, always representing the
 * ACTIVE project. Penguins do not stack or collide. Mounted at AppShell
 * level so it floats over the whole app, not inside any one route.
 *
 * ─── THE FIXED STATION (2026-07-02 operator ratification) ────────────────
 * Werner stands at a STATION and NEVER chases the cursor. This SUPERSEDES the
 * old WERNER-ICE reel (SPR-15), where Werner's position was driven toward the
 * ~0.5s-lagged cursor every frame, and the SPR-06 autonomous roam, where he
 * walked himself around the viewport. Both are gone. The design + the honest
 * supersession of the reel's signed acceptance criterion #3 live in
 * docs/htmlspec/werner-fixed-station/DESIGN.md.
 *
 * The model, stated once: THE CURSOR IS THE BAIT ON WERNER'S LINE. He is the
 * fisherman fixed at his station; the cursor is his bait. Two ambient states,
 * split by the EXISTING pointer-idle signal (useMouseFollow.pointerIdle) — the
 * same XOR the reel/gag already used, with the station swapped onto the
 * pointer-active side:
 *   - pointer ACTIVE (moving): Werner stays put; a fishing line hangs from his
 *     rod tip to the cursor-bait (WernerFishingLayer + WernerIceBait, mounted
 *     by WernerIceCursorShell). The cursor IS the bait.
 *   - pointer IDLE (still ≥ POINTER_IDLE_MS): no live bait to cast to, so Werner
 *     runs the never-catch gag at his OWN ice-hole — the `werner-fishing` CSS
 *     cartoon (FISHING_BEATS / waddle.css), unchanged. This is his "cool
 *     animation" and it still NEVER lands a catch (a ratified, test-pinned
 *     invariant).
 * The gag is a pure CSS keyframe loop; the ONLY JS it needs is the class
 * toggle in the tiny station rAF below (no position writes, no spring, no
 * roam). Under reduced motion the rAF early-returns and the class is never
 * added — Werner is fully still but clickable, the same floor the roam honoured.
 *
 * Directed choreography (SPR-10) still WALKS Werner to an activated control,
 * bumps it, and RETURNS HIM TO HIS STATION — click-driven, not cursor-driven.
 * The station is home; excursions come home. This reuses the SAME stroll
 * primitive (strollTo / restGait) the roam used to publish; it is re-homed to
 * component scope so WernerStage.walkTo does not silently no-op.
 * ───────────────────────────────────────────────────────────────────────
 */

/** The one project-tree panel id the rest of the shell already uses. */
export const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";

/** The mascot's own footprint, used to clamp its position so it stays
 *  reachable. A square a touch larger than the rendered art. */
const MASCOT_SIZE = 64;

/** How long a directed excursion / the return-home stroll eases, in ms. Brisk
 *  enough to read as deliberate walking, short enough that Werner is back on
 *  station promptly after a bump. */
const STATION_RETURN_MS = 900;

/** Where the Penguin's station is when first shown — lower-left, out of the way
 *  of the main composer but clearly in reach. Recomputed against the live
 *  viewport on mount so it is never seeded off-screen on a small window. */
function initialMascotPos(): { x: number; y: number } {
  const vw = typeof window !== "undefined" ? window.innerWidth : 1440;
  const vh = typeof window !== "undefined" ? window.innerHeight : 900;
  return clampRectToViewport(
    {
      x: 88,
      y: vh - MASCOT_SIZE - 96,
      width: MASCOT_SIZE,
      height: MASCOT_SIZE,
    },
    { width: vw, height: vh },
  );
}

export function PenguinMascot() {
  const navigate = useNavigate();
  const reduceMotion = usePrefersReducedMotion();

  // The active (default) station activity. With one registered activity
  // (ice-fishing) this is always it; SPR-03 will make "active" switchable. The
  // mascot renders THIS activity's ambient class instead of a hard-coded string
  // — an activity can toggle CSS + mount a cursor-instrument, but has no access
  // to Werner's position (see src/werner/activities/types.ts). Stable identity
  // (the frozen registry singleton), so it is safe in effect deps.
  const activeActivity = useStationActivity();

  const buttonRef = useRef<HTMLButtonElement | null>(null);
  // The bob wrapper (the span carrying the idle wander + the walk animation
  // during a directed excursion). The `werner-waddle` foot-bob is toggled on it
  // only while Werner is mid-stroll to a button.
  const bobRef = useRef<HTMLSpanElement | null>(null);
  // The STATION: Werner's home coordinate. Seeded on mount, updated when the
  // operator drags him, re-clamped on resize. This is where he lives and where
  // a directed excursion returns him to.
  const stationPos = useRef(initialMascotPos());
  // The LIVE rendered position (the one source of record). Equal to the station
  // at rest; equals the target button during a choreography excursion; written
  // straight to the DOM during a drag (pointer-capture, like PanelHandle) so
  // dragging doesn't thrash React.
  const pos = useRef({ ...stationPos.current });
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(false);
  // Pending single-click float, deferred so a double-click can cancel it. null = none.
  const clickTimer = useRef<number | null>(null);
  // The station idle-gag scheduler (a single rAF; auto-pauses on a hidden tab).
  // Its ONLY job is to toggle the `werner-fishing` class — no position work.
  const gagRaf = useRef<number | null>(null);
  // Cleanup timer for the return-home stroll after a directed excursion.
  const returnTimer = useRef<number | null>(null);

  // The lagged/live cursor read seam. Under the station it is used ONLY to read
  // pointerIdle (does the own-hole gag own Werner right now?) — the bait + line
  // layers own their own instances. Disabled (frozen) under reduced motion so
  // there is zero involuntary behaviour.
  const follow = useMouseFollow({ disabled: reduceMotion });
  // A ref mirror of reduceMotion the once-created StageHost can read without a
  // stale closure. The stage's freeze() calls host.setRoamPaused(false) to reset
  // the pause flag; that path must NOT trigger a return-home glide under reduced
  // motion (the still floor), so setRoamPaused reads this.
  const reduceMotionRef = useRef(reduceMotion);
  reduceMotionRef.current = reduceMotion;
  // The active emote mark, rendered over the Werner mark.
  const [emote, setEmote] = useState<EmoteKind | null>(null);
  // Directed-walk flag: TRUE while the stage is walking Werner OUT to a button.
  // The stage clears it (setRoamPaused(false)) the instant the button is reached
  // — the return-home leg runs with this already false, so it is NOT enough on
  // its own to keep the gag off during the walk home (see returningHome).
  const roamPaused = useRef(false);
  // TRUE during the return-home leg (after a directed excursion, before Werner is
  // back on station). The gag stands down for this window too, so an idle pointer
  // can't stack the own-hole fishing cartoon onto the walk-home gait.
  const returningHome = useRef(false);
  // The imperative controller (the SPR-10 seam). Created once; its StageHost
  // reuses THIS component's position + stroll rather than forking a second one.
  const stageRef = useRef<WernerStageController | null>(null);
  // The stroll primitives, handed to the StageHost so a directed walkTo reuses
  // the EXACT same position write + gait swap as the return-home leg (one
  // position source). Populated from the useCallbacks below.
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
  // during a stroll, and after a viewport resize re-clamp).
  const applyPos = useCallback(() => {
    const el = buttonRef.current;
    if (!el) return;
    el.style.left = `${pos.current.x}px`;
    el.style.top = `${pos.current.y}px`;
  }, []);

  useEffect(() => {
    applyPos();
  }, [applyPos]);

  // Re-clamp on viewport resize so a window shrink can never strand the station
  // past the edge (rigor #3: off-screen recovery, asserted). Both the station
  // home and the live position are re-clamped; if Werner is resting (not mid-
  // excursion) the live position tracks the station.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const onResize = () => {
      const bounds = { width: window.innerWidth, height: window.innerHeight };
      stationPos.current = clampRectToViewport(
        { ...stationPos.current, width: MASCOT_SIZE, height: MASCOT_SIZE },
        bounds,
      );
      if (!roamPaused.current && !dragStart.current) {
        pos.current = { ...stationPos.current };
      } else {
        pos.current = clampRectToViewport(
          { ...pos.current, width: MASCOT_SIZE, height: MASCOT_SIZE },
          bounds,
        );
      }
      applyPos();
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [applyPos]);

  // ── The stroll primitive (shared by directed excursions + return-home). ──
  // Walk Werner to (x,y) over `durationMs`, gait on, position eased. The SINGLE
  // place a stroll happens, so there is exactly one position write + one bob-
  // class swap, never a forked second walker. The target is clamped on-screen
  // here so no caller can strand him.
  const strollTo = useCallback(
    (x: number, y: number, durationMs: number) => {
      const el = buttonRef.current;
      const bob = bobRef.current;
      if (!el) return;
      const target = clampRectToViewport(
        { x, y, width: MASCOT_SIZE, height: MASCOT_SIZE },
        {
          width: typeof window !== "undefined" ? window.innerWidth : 1440,
          height: typeof window !== "undefined" ? window.innerHeight : 900,
        },
      );
      pos.current = { x: target.x, y: target.y };
      el.style.transition = `left ${durationMs}ms ease-in-out, top ${durationMs}ms ease-in-out`;
      if (bob) {
        // The at-rest `penguin-mascot-wander` and the walking `werner-waddle`
        // both set `animation` on this one node — stacking them means the later
        // rule wins and the walk bob is silently suppressed. Swap them so the
        // feet actually bob while strolling; restore wander at rest (restGait).
        bob.classList.remove("penguin-mascot-wander");
        bob.classList.add("werner-waddle");
        // The directed gait (a fuller waddle than the ambient drift) rides
        // alongside the body bob so an excursion reads as deliberate walking.
        bob.classList.add("werner-step");
      }
      applyPos();
    },
    [applyPos],
  );

  // Drop the walk gait + transition and restore the at-rest wander. Shared
  // end-of-leg cleanup so the walk/wander invariant holds for both callers.
  const restGait = useCallback(() => {
    if (bobRef.current) {
      bobRef.current.classList.remove("werner-waddle");
      bobRef.current.classList.remove("werner-step");
      if (!reduceMotion) bobRef.current.classList.add("penguin-mascot-wander");
    }
    if (buttonRef.current) buttonRef.current.style.transition = "";
  }, [reduceMotion]);

  // Publish the stroll primitives to the once-created StageHost via refs, so a
  // preference flip re-derives the callbacks without re-creating the controller.
  useEffect(() => {
    strollRef.current = strollTo;
    restGaitRef.current = restGait;
    return () => {
      strollRef.current = null;
      restGaitRef.current = null;
    };
  }, [strollTo, restGait]);

  // ── The station idle-gag driver. ──
  // Toggles the `werner-fishing` class on the bob span: ON while the pointer is
  // idle on a visible tab and Werner is neither being dragged nor on a directed
  // excursion (his own-hole never-catch cartoon owns the scene); OFF otherwise
  // (the cursor is the live bait, and WernerFishingLayer draws the line to it).
  // No position writes — a fixed station only *decides* which ambient plays.
  // Disabled entirely under reduced motion (the class is never added), matching
  // the CSS reduced-motion guard's paired JS line of defence, and when the
  // WERNER-ICE flag is off (no ice-fishing experience at all — no bait, no line,
  // so nothing to fish).
  useEffect(() => {
    const idleClass = activeActivity.ambient.idleClass;
    if (
      reduceMotion ||
      !wernerIceFishingCursor ||
      !idleClass ||
      typeof window === "undefined"
    )
      return;

    // The idle-gag class comes from the active activity (ice-fishing's
    // idleClass is the `werner-fishing` gag), not a hard-coded literal — so an
    // activity owns its own ambient, and adding one is a registration, not a
    // mascot edit.
    let fishing = false;
    const setFishingLoop = (on: boolean) => {
      if (on === fishing) return;
      fishing = on;
      bobRef.current?.classList.toggle(idleClass, on);
    };

    const tick = () => {
      const reading = follow.read();
      setFishingLoop(
        !dragStart.current &&
          !roamPaused.current &&
          !returningHome.current &&
          reading.pointerIdle &&
          !reading.tabHidden,
      );
      gagRaf.current = window.requestAnimationFrame(tick);
    };
    gagRaf.current = window.requestAnimationFrame(tick);

    return () => {
      if (gagRaf.current !== null) {
        window.cancelAnimationFrame(gagRaf.current);
        gagRaf.current = null;
      }
      // Drop the gag class on teardown so a no-rAF state (unmount, or a flip
      // into reduced motion where this effect early-returns) never strands
      // Werner mid-cast with the loop class on.
      bobRef.current?.classList.remove(idleClass);
    };
  }, [reduceMotion, follow, activeActivity]);

  // Product-experience idle is independent of the selected station activity:
  // the lens, nib, and resonance modes can all let Werner fall asleep. This
  // loop reads the existing pointer seam and emits only the active→idle edge;
  // it owns no position or cursor writes and does not run under reduced motion.
  useEffect(() => {
    if (reduceMotion || typeof window === "undefined") return;
    const canReactToIdle = (reading: ReturnType<typeof follow.read>) =>
      !dragStart.current &&
      !roamPaused.current &&
      !returningHome.current &&
      !reading.tabHidden;
    // Pointer history is the edge authority. Drag/excursion/visibility are
    // eligibility gates only: reopening one while an already-idle pointer is
    // unchanged must never impersonate a fresh active→idle transition.
    let wasPointerIdle = follow.read().pointerIdle;
    let raf = 0;
    const tick = () => {
      const reading = follow.read();
      notifyPointerIdleEdge(
        wasPointerIdle,
        reading.pointerIdle,
        canReactToIdle(reading),
      );
      wasPointerIdle = reading.pointerIdle;
      raf = window.requestAnimationFrame(tick);
    };
    // Browsers pause rAF in hidden tabs. Re-baseline on each visibility edge
    // so time elapsed while asleep cannot surface as an active→idle edge on
    // the first frame after the tab returns.
    const onVisibilityChange = () => {
      wasPointerIdle = follow.read().pointerIdle;
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    // Baseline from reality. No movement history reads idle, but that is a
    // level, not an active→idle edge, and must not animate on mount or after a
    // reduced-motion preference flip clears pointer history.
    raf = window.requestAnimationFrame(tick);
    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.cancelAnimationFrame(raf);
    };
  }, [reduceMotion, follow]);

  // ── SPR-05/10: the WernerStage controller + SPR-10 choreography listener. ──
  // Created ONCE (empty deps). Its StageHost reuses this component's stroll /
  // position machinery via the refs above — no second position. The
  // choreography listener (PRODUCT_ACTIVATE → waddle-to-control → hit → return
  // home) is mounted here once and torn down on unmount. Reduced-motion
  // freeze/unfreeze is a SEPARATE effect (below) so a preference flip doesn't
  // tear down + re-create the controller.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const host: StageHost = {
      walkTo: (x, y, durationMs) => {
        // Reuse the stroll primitive if it's live (motion allowed); under
        // reduced motion the stage is frozen and never calls this.
        strollRef.current?.(x, y, durationMs);
      },
      getPos: () => ({ x: pos.current.x, y: pos.current.y }),
      setEmote: (kind) => setEmote(kind),
      // The station model has NO ambient cursor-follow, so this is a documented
      // no-op: the mascot never calls stage.follow(true), and stage.freeze()'s
      // defensive setFollowing(false) is a no-op here. The follow capability
      // stays in the reusable WernerStage/reducer (a general controller), unused
      // by this one client. Werner does not chase the cursor. See DESIGN.md.
      setFollowing: () => {},
      setRoamPaused: (paused) => {
        roamPaused.current = paused;
        if (paused) return;
        // A directed excursion just ended (the stage walked Werner to a button
        // and bumped it), OR the stage froze (freeze() calls this to reset the
        // pause flag). Guarded so a drag/new excursion that began mid-return wins.
        if (returnTimer.current !== null) {
          window.clearTimeout(returnTimer.current);
          returnTimer.current = null;
        }
        if (dragStart.current) {
          restGaitRef.current?.();
          return;
        }
        if (reduceMotionRef.current) {
          // Reduced-motion STILL FLOOR: no return-home glide. This path is
          // reached when reduced motion is enabled mid-excursion (freeze() →
          // setRoamPaused(false)); the stage never STARTS a directed walk while
          // frozen, so Werner is already home or a stale excursion is being
          // cancelled. Snap to the station instantly — no transition, no walk
          // gait, no involuntary motion — and rest.
          returningHome.current = false;
          pos.current = { ...stationPos.current };
          if (buttonRef.current) buttonRef.current.style.transition = "";
          applyPos();
          restGaitRef.current?.();
          return;
        }
        // Motion allowed: walk him HOME to his station, then rest — the station
        // is home; excursions come home. The gag stands down for this leg too
        // (returningHome) so an idle pointer can't stack the own-hole cartoon
        // onto the walk-home gait.
        returningHome.current = true;
        const home = stationPos.current;
        strollRef.current?.(home.x, home.y, STATION_RETURN_MS);
        returnTimer.current = window.setTimeout(() => {
          returnTimer.current = null;
          returningHome.current = false;
          if (!dragStart.current && !roamPaused.current) {
            restGaitRef.current?.();
          }
        }, STATION_RETURN_MS);
      },
    };
    const stage = createWernerStage(host);
    stageRef.current = stage;
    // Two activation paths feed the one stage: product activations (click OR
    // hotkey, via the shared event) and any opt-in `data-werner-target` button.
    const teardownChoreo = installChoreography(stage);
    const teardownTarget = installTargetChoreography(stage);
    const teardownReactions = installReactionBus(stage);
    // Living-TV ambient: after a long quiet, soft idle/sleeping beat.
    // Disabled under reduced motion (still floor — no ambient TV glance).
    const teardownAmbient = reduceMotion
      ? () => {}
      : installLivingTvAmbient();
    return () => {
      teardownChoreo();
      teardownTarget();
      teardownReactions();
      teardownAmbient();
      stage.dispose();
      stageRef.current = null;
      if (returnTimer.current !== null) {
        window.clearTimeout(returnTimer.current);
        returnTimer.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduceMotion]);

  // Reduced-motion wiring for the stage. Freeze on reduced motion (no directed
  // waddle — the still floor); unfreeze otherwise. Re-runs only when the
  // preference flips. NOTE: there is no `stage.follow()` call — Werner never
  // follows the cursor; the station model has no ambient follow to enable.
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (reduceMotion) {
      stage.freeze();
      setEmote(null);
    } else {
      stage.unfreeze();
    }
  }, [reduceMotion]);

  // ── Single-click: float the project tab. ──
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
    emitWernerExperience("highlight");
    navigate("/home");
  }, [navigate]);

  // ── Drag (pointer-capture, clamped — reuses the panel clamp rule). ──
  // A drag RE-STATIONS Werner: the station home moves to where he is dropped.
  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.currentTarget.setPointerCapture(e.pointerId);
      dragStart.current = { x: e.clientX, y: e.clientY };
      moved.current = false;
      // Hand the position to the pointer: kill any in-flight stroll transition +
      // gait so the drag tracks the cursor 1:1 instead of easing behind it.
      if (buttonRef.current) buttonRef.current.style.transition = "";
      if (bobRef.current) {
        // Invariant: `werner-waddle` ⟺ actively strolling; otherwise the idle
        // `penguin-mascot-wander`. A drag ends any stroll, so swap back to the
        // wander (gated on reduceMotion so a reduced-motion drag stays still).
        bobRef.current.classList.remove("werner-waddle");
        bobRef.current.classList.remove("werner-step");
        if (!reduceMotion)
          bobRef.current.classList.add("penguin-mascot-wander");
      }
      if (returnTimer.current !== null) {
        window.clearTimeout(returnTimer.current);
        returnTimer.current = null;
      }
      returningHome.current = false;
    },
    [reduceMotion],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!dragStart.current) return;
      const dx = e.clientX - dragStart.current.x;
      const dy = e.clientY - dragStart.current.y;
      if (Math.abs(dx) > 3 || Math.abs(dy) > 3) moved.current = true;
      dragStart.current = { x: e.clientX, y: e.clientY };
      const vw = typeof window !== "undefined" ? window.innerWidth : 1440;
      const vh = typeof window !== "undefined" ? window.innerHeight : 900;
      // Same clamp the floating panels use — at least 80px of the mascot stays
      // reachable on every side, so it can't be dragged into oblivion.
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
    if (dragStart.current) {
      // Commit the drop as the new STATION home (re-station), so Werner lives
      // where the operator put him and future excursions return there.
      stationPos.current = { ...pos.current };
    }
    dragStart.current = null;
  }, []);

  // Single vs. double-click. Two distinct gates:
  //  (1) drag gate — a click that ended a drag must NOT float the tab
  //      (`moved`, set in pointer-move, swallows it).
  //  (2) click-vs-doubleclick gate — a real double-click dispatches
  //      click + click + dblclick, so we DEFER the float behind a ~250ms timer;
  //      onDoubleClick cancels it, opening the project with no stray float.
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
      data-werner-emote={emote ?? "none"}
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
        left: pos.current.x,
        top: pos.current.y,
      }}
    >
      {/* The bob wrapper. At rest it carries `penguin-mascot-wander` (a small
          IN-PLACE drift on top of Werner's breathing sway — ambient life, not
          locomotion); while Werner is on a directed excursion the stroll adds
          `werner-waddle`/`werner-step` here so his feet bob as he walks; while
          the pointer is idle the station gag adds `werner-fishing` here so the
          own-hole cartoon plays. All are gated/cleared under reduced motion so
          he is fully still for those users. */}
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
        {/* The base Werner mark — the SPR-06 walk-cycle RIG (feet + flippers
            animate off the `werner-waddle`/`werner-step` walk signal during an
            excursion) plus the SPR-04 rod + the SPR-05 own-hole line/fish the
            `werner-fishing` gag animates. The rig owns no motion source; it
            consumes the class signals this bob span carries. Hidden behind the
            emote overlay when one is playing so we don't stack penguins. */}
        <span style={{ visibility: emote ? "hidden" : "visible" }}>
          <WernerRig size={MASCOT_SIZE} label="Project" />
        </span>
        {/* The active emote (SPR-05) — an existing animated Werner mark mapped to
            the emote kind, overlaid on the mascot. Keyed by kind so a one-shot
            mark remounts (restarts) per fire. EmoteView renders a STILL pose
            when reduceMotion, so the overlay is a quiet acknowledgment. */}
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
