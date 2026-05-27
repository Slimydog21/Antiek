import { useCallback, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";

import Werner from "../brand/Werner";
import { clampRectToViewport } from "../workspace/panelLayoutLogic";
import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";
import { useWorkspace } from "../workspace/WorkspaceStore";

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
 *   idle           → gentle waddle/wander (the Werner CSS `werner-idle`
 *                    sway), which COLLAPSES to a static frame under
 *                    `prefers-reduced-motion: reduce` (animations.css +
 *                    the live JS guard below, which also drops the
 *                    drift wander).
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
 */

/** The one project-tree panel id the rest of the shell already uses. */
export const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";

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

  const buttonRef = useRef<HTMLButtonElement | null>(null);
  // Position lives in a ref + is written straight to the DOM during a drag
  // (pointer-capture, like PanelHandle) so dragging doesn't thrash React.
  const pos = useRef(initialMascotPos());
  const dragStart = useRef<{ x: number; y: number } | null>(null);
  const moved = useRef(false);
  // Pending single-click float, deferred so a double-click can cancel it
  // (see onClick/onDoubleClick below). null = no float pending.
  const clickTimer = useRef<number | null>(null);

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
  }, []);

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
      {/* `wander` adds a slow positional drift on top of the breathing
          sway; gated on reduceMotion so it is fully still for those users.
          The Werner mark's own `werner-idle` keyframe is the breathing
          part and is reduced-motion-guarded in animations.css. */}
      <span
        className={reduceMotion ? "" : "penguin-mascot-wander"}
        style={{ display: "block", width: MASCOT_SIZE, height: MASCOT_SIZE }}
      >
        <Werner mood="idle" size={MASCOT_SIZE} label="Project" />
      </span>
    </button>
  );
}

export default PenguinMascot;
