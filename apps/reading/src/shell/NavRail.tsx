import { useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";

import { useViewportTier } from "../workspace/useViewportTier";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import {
  WORKFLOWS,
  WORKFLOW_ORDER,
  workflowForPath,
  type Workflow,
} from "./workflowTaxonomy";
import { useInvestigationList } from "../hooks/useInvestigationList";
import { useSeenVersion } from "../hooks/useSeenVersion";
import { countSummoningGroups } from "../shared/attention";
import { isUnseen, researchStateStyle } from "../shared/researchState";
import { lastSeenAt } from "../workspace/seen";
import { ProductsLauncher } from "./ProductsLauncher";
import BrainMark from "../brand/BrainMark";
import { KeyChip } from "../components/hotkeys/KeyChip";
import {
  bindingForProduct,
  emitProductActivate,
  BUILTIN_BINDINGS,
} from "../components/hotkeys/bindings";

/**
 * NavRail (SPR-04) — the four-workflow content-first rail.
 *
 * This SUPERSEDES the pre-SPR-04 six-mode rail (Research / Wrestle /
 * Create / Brainstorm / Notebooks / Sources) AND the five-surface
 * portfolio-shell prototype. Per the unified-vision reconciliation:
 *   Wrestle + Brainstorm → Research/Read (per taxonomy)
 *   Create               → Write
 *   Interview            → Speak
 *   Notebooks/Documents/Sources → the content tree (off the rail)
 *
 *   ┌────────┐
 *   │  ⌂     │  Brain mark
 *   ├────────┤
 *   │  ⌕     │  Search (⌘K)
 *   │  ＋    │  New
 *   ├────────┤
 *   │ Resrch │  the FOUR workflows (zone 1). Clicking one switches the
 *   │ Read   │  active workflow — zones 2 (tree) + 3 (scene) follow.
 *   │ Write  │
 *   │ Speak  │
 *   ├────────┤
 *   │  ⋯     │  "More" — the SINGLE non-workflow affordance. Opens the
 *   │  More  │  ProductsLauncher, which holds the honest full inventory
 *   │        │  (every mode) AND the operator surfaces: Operator, Trust,
 *   │        │  Settings, and the shared bucket. One click reaches any
 *   │        │  of them.
 *   └────────┘
 *
 * Exactly four workflow entries — not 8, not 5. Everything else (deep
 * modes, Operator, Trust, Settings, the shared bucket) lives behind the
 * single "More" affordance + ⌘K, never on the rail. The workflow set is
 * read from the taxonomy (WORKFLOW_ORDER), so the rail can't drift from
 * the source of truth.
 *
 * Operator/Trust/Settings reachability after the demotion: each is a
 * `built: true` routed entry in the shared bucket of MODE_TAXONOMY, so
 * the ProductsLauncher renders + links it. More → click Operator / Trust
 * / Settings = one click in. ⌘K reaches them too.
 *
 * SPR-12 M3 — the old "New / Project tree" (+ project) utility button
 * that lived here (it toggled the docked-left "shortcuts:projecttree"
 * panel) is REMOVED. The project tree is now reached through the floating
 * Penguin mascot (shell/PenguinMascot.tsx, mounted at AppShell level):
 * single-click the Penguin floats the project tree, double-click opens
 * the project. Superseding that rail button is the operator's ratified
 * choice — see PenguinMascot.tsx for the full provenance comment.
 *
 * SPR-12 M1 — the top-left Werner mark now navigates to /home (the
 * unified branded home) rather than "/" (the Research door). Reversible:
 * the rejected alternative was making "/" itself the Home and moving
 * Research to /research; that was passed over for blast radius (see
 * modes/Home/Home.tsx for the recorded decision).
 *
 * SPR-06 — TWO changes, both load-bearing for the always-on ad border
 * (SPR-07), which needs all FOUR screen edges free + symmetric:
 *
 *   (1) ORIENTATION. The rail defaults to `orientation="bottom"` now: it
 *       lays out horizontally along the bottom of the window so the main
 *       working region above it can consume the full screen width with no
 *       left gutter. The original vertical `orientation="left"` is kept
 *       (stories / a rollback path), so the two layouts share ONE
 *       component + one destination set — no parallel nav abstraction. The
 *       four-door + More + Search semantics, the active accent, the chord
 *       shortcuts, and the roles/labels are identical across orientations;
 *       only the flex axis + the active-accent edge differ.
 *
 *   (2) HOME = BRAIN. The static top-left mark that was the home button is
 *       now a <BrainMark> — the brain IS the brand (mascot and logo), so the
 *       home control reads as "the brain's home". The control is unchanged
 *       otherwise: same /home
 *       route, same accessible <button> with aria-label + focus ring.
 */

/** Rail axis. `bottom` (default) is the SPR-06 shell layout — a horizontal
 *  rail along the window bottom so the working region above it is full-width
 *  and symmetric (the four edges SPR-07's border needs). `left` is the
 *  original vertical rail, kept for stories + a rollback path. */
export type Orientation = "left" | "bottom";

function I({ d, size = 18 }: { d: string; size?: number }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

// Workflow glyphs (24-grid single-path SVG, matching the prior rail's style).
const WF_ICONS: Record<Exclude<Workflow, "shared">, string> = {
  research: "M3 12 L8 7 L13 12 L18 7 L21 9 M3 12 V20 H21 V12", // peaks + horizon
  read: "M4 5 H20 V19 H4 Z M4 9 H20 M9 13 H15 M9 16 H13", // doc with lines
  write: "M5 19 L12 5 L19 19 M9 14 H15", // triangular A
  speak: "M5 4 H19 V15 H9 L5 19 Z M9 9 H15 M9 12 H13", // speech bubble
};

const UTIL_ICONS = {
  search: "M11 4 a7 7 0 1 1 0 14 a7 7 0 1 1 0 -14 M16 16 L21 21", // magnifier
  // SPR-12 M3 — the `plus` ("+ project / New / Project tree") glyph is
  // gone: that button is superseded by the floating Penguin mascot, which
  // now owns floating/opening the project tree.
  // "More" — the single non-workflow affordance. A grid glyph reads as
  // "all products / everything else", which is exactly what it opens.
  more: "M4 4 H10 V10 H4 Z M14 4 H20 V10 H14 Z M4 14 H10 V20 H4 Z M14 14 H20 V20 H14 Z", // ⊞ grid
};

/** Rail button for workflows (the four dominant doors), utilities, and More.
 *  Variant gives workflows stronger weight (visible persistent labels below
 *  glyph, taller presence, stronger inactive color using ice tokens) so the
 *  eye lands on the four doors first. Utilities and More stay muted/icon-only
 *  and read as secondary/overflow. Single extension to the existing button
 *  (no parallel component). All Lemon tokens. */
function RailButton({
  icon,
  label,
  active,
  onClick,
  title,
  variant = "utility",
  orientation = "bottom",
  productId,
  binding,
  badge,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
  title: string;
  variant?: "workflow" | "utility" | "more";
  orientation?: Orientation;
  /** SPR-08 / SPR-10 geometry contract: stamps `data-product-id` so a
   *  downstream listener (the penguin) can resolve the button's screen rect
   *  via document.querySelector(`[data-product-id="…"]`). */
  productId?: string;
  /** SPR-08: the bound hotkey spec to show as an on-bar chip — a single ⌘+key
   *  combo from the shared map (e.g. "mod+e" for Read). Post-SPR-08 there are
   *  NO vim g-chords; the prop is always fed a real `mod+` spec. */
  binding?: string;
  /** herdr transfer P0-2: attention count chip (blocked + unseen-done).
   *  Rendered only when > 0 — an absent badge is the calm state. */
  badge?: number;
}) {
  const isWorkflow = variant === "workflow";
  const color = active
    ? "bg-sun text-ink"
    : isWorkflow
    ? "text-ice-2/80 hover:text-ice-1 hover:bg-white/10"
    : "text-ice-2/50 hover:text-ice-2/70 hover:bg-white/5";
  // SPR-07 M2 — EVERY bar button now stacks a VISIBLE text caption under its
  // glyph (the v1 complaint was icon-only utilities + a caption-less igloo).
  // Workflows already had this dominant stack; Search/More now share the same
  // icon-above-label layout so the whole bar reads as named buttons, not a row
  // of mystery glyphs. The visible caption is aria-hidden (the `.sr-only` span
  // remains the single accessible name, so there is no double-announce and the
  // four-door label guards that read `.sr-only` are untouched).
  const layout = "min-h-12 py-1 flex-col items-center justify-center";
  // The active marker is a slab on the edge nearest the working region: the
  // INNER edge of the rail. Left rail → its right edge; bottom rail → its
  // top edge. Same "this door is live" read, reflected for the new axis.
  const marker =
    orientation === "left"
      ? "absolute left-0 top-2 bottom-2 w-1 rounded-r bg-ink"
      : "absolute top-0 left-2 right-2 h-1 rounded-b bg-ink";
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      data-product-id={productId}
      className={
        (orientation === "left" ? "mx-1.5 " : "mx-0.5 ") +
        "flex rounded relative " +
        layout +
        " " +
        color
      }
    >
      {active && <span aria-hidden="true" className={marker} />}
      <span className="leading-none" aria-hidden="true">
        {icon}
      </span>
      {badge !== undefined && badge > 0 && (
        <span
          aria-label={`${badge} need attention`}
          className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-emperor text-ice-1 text-[9px] font-mono font-bold flex items-center justify-center"
        >
          {badge > 99 ? "99+" : badge}
        </span>
      )}
      {/* SPR-07 M2 — the visible caption, now on EVERY bar button (was
          workflow-only). aria-hidden so the `.sr-only` span stays the single
          announced name. */}
      <span
        className="text-[10px] leading-[11px] mt-0.5 font-medium tracking-tight text-center w-full"
        aria-hidden="true"
      >
        {label}
      </span>
      {/* SPR-08 — the on-bar hotkey chip. A tiny, unobtrusive indicator under
          the door label so the shortcut is "shown on-screen" (the operator's
          headline ask). The chip is the announcer (it carries its own
          aria-keyshortcuts); the button has none, so there's no double-
          announce. */}
      {binding && (
        <KeyChip
          binding={binding}
          label={label}
          className="mt-0.5 scale-90 opacity-80"
        />
      )}
      <span className="sr-only">{label}</span>
    </button>
  );
}

type NavRailProps = {
  /** Rail axis. Defaults to "bottom" (SPR-06 shell). See {@link Orientation}. */
  orientation?: Orientation;
};

export function NavRail({ orientation = "bottom" }: NavRailProps = {}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const activeWorkflow = workflowForPath(pathname);

  const tier = useViewportTier();
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const [launcherOpen, setLauncherOpen] = useState<boolean>(false);
  const isMobile = tier === "sm" || tier === "md";
  const showRail = !isMobile || !collapsed;
  const isBottom = orientation === "bottom";

  // herdr transfer P0-2 — the rail badge: how many research FAMILIES need
  // the operator right now. Counted per family root (countSummoningGroups):
  // two blocked members of one cascade are ONE thing to look at, matching
  // the rollup dots in the sidebar/MyResearch. Polled at 60s (a badge does
  // not need the 30s cadence of the full log); an absent badge is calm.
  const { investigations } = useInvestigationList({
    limit: 200,
    pollIntervalMs: 60_000,
  });
  const researchSummons = useMemo(
    () =>
      countSummoningGroups(
        investigations.map((s) => ({
          id: s.investigation_id,
          parentId: s.parent_investigation_id,
          state: researchStateStyle(s.status).state,
          unseen: isUnseen(s, lastSeenAt(s.investigation_id)),
        })),
      ),
    [investigations],
  );
  // P0-3 — re-render when any surface marks seen (badge unread count).
  useSeenVersion();

  // SPR-12 M3 — the project-tree toggle that used to live on the rail is
  // gone; the floating Penguin mascot (shell/PenguinMascot.tsx) now floats
  // and opens the "shortcuts:projecttree" panel. The workspace store is no
  // longer touched from here.

  const openSearch = () =>
    window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PALETTE_TOGGLE));

  const selectWorkflow = (wf: Exclude<Workflow, "shared">) => {
    const route = WORKFLOWS[wf].defaultRoute;
    navigate(route);
    // SPR-08/SPR-10 — a real click emits the SAME activation event the hotkey
    // path emits (source differs only). This is the click≡hotkey parity the
    // penguin (SPR-10) depends on. Navigation is AUGMENTED, not replaced.
    emitProductActivate({ productId: wf, route, source: "click" });
    if (isMobile) setCollapsed(true);
  };

  if (isMobile && collapsed) {
    return (
      <button
        type="button"
        title="Open navigation"
        aria-label="Open navigation"
        onClick={() => setCollapsed(false)}
        className="absolute top-2 left-2 z-50 w-9 h-9 flex flex-col items-center justify-center gap-1 bg-ink text-sun border-edge border-sun rounded shadow-z2"
      >
        <span className="w-4 h-0.5 bg-sun" aria-hidden="true" />
        <span className="w-4 h-0.5 bg-sun" aria-hidden="true" />
        <span className="w-4 h-0.5 bg-sun" aria-hidden="true" />
      </button>
    );
  }

  // Brain home control — replaces the static penguin/igloo mark.
  // Same /home route + accessible <button> (aria-label + visible focus ring);
  // the mark is the only thing that changed (penguin/igloo → brain). In the bottom
  // rail its divider is on the trailing (right) edge instead of the bottom.
  //
  // SPR-07 M1 + M3 — the home mark was the LAST caption-less bar control (the
  // v1 complaint "the home mark has no label"). It now stacks a VISIBLE "Home"
  // text caption + the SPR-08 ⌘ hotkey chip (⌘O = bindingForProduct("home"),
  // read from the shared map — never a hand-typed combo, never the stale "g h"
  // chord) under the mark, matching every other bar button. The button keeps
  // its `aria-label="Antiek home"` as the single accessible name; the caption
  // is aria-hidden and the chip is DECORATIVE (aria-hidden) so the igloo
  // button announces exactly once and no role="img" leaks onto the mark
  // (the SPR-06 "no accessible name on the decorative mark" guard stays true).
  const homeBinding = bindingForProduct("home")?.spec;
  const homeButton = (
    <button
      type="button"
      title="Antiek · home"
      aria-label="Antiek home"
      data-product-id="home"
      onClick={() => {
        navigate("/home");
        // SPR-08/SPR-10 click≡hotkey parity (the ⌘O home binding).
        emitProductActivate({ productId: "home", route: "/home", source: "click" });
      }}
      className={
        "shrink-0 flex flex-col items-center justify-center gap-0.5 bg-sun/95 hover:bg-sun text-ink " +
        "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink " +
        (isBottom ? "w-16 h-full border-r-edge border-sun" : "h-16 w-full border-b-edge border-sun")
      }
    >
      <BrainMark size={24} />
      <span
        className="text-[10px] leading-[11px] font-medium tracking-tight"
        aria-hidden="true"
      >
        Home
      </span>
      {homeBinding && (
        <KeyChip
          binding={homeBinding}
          label="Home"
          decorative
          className="scale-90 opacity-80"
        />
      )}
    </button>
  );

  const searchButton = (
    <RailButton
      icon={<I d={UTIL_ICONS.search} size={15} />}
      label="Search"
      title="Search · ⌘K"
      onClick={openSearch}
      variant="utility"
      orientation={orientation}
      // SPR-07 M3 — Search opens the command palette, whose canonical binding
      // is the SPR-08 built-in `palette` (⌘K / mod+k). We read it from the
      // shared built-in table by id rather than re-typing "mod+k", so the chip
      // can never drift from shortcuts.ts.
      binding={BUILTIN_BINDINGS.find((b) => b.id === "palette")?.spec}
    />
  );

  // THE FOUR WORKFLOWS (zone 1). Read from WORKFLOW_ORDER only — the rail
  // can't drift from the source of truth. The group keeps its testid +
  // role/label across orientations so the U-01 four-door guard + the screen
  // reader both see the same nav regardless of axis.
  const workflowGroup = (
    <nav
      className={
        "flex gap-1 " + (isBottom ? "flex-row items-stretch" : "flex-1 flex-col")
      }
      aria-label="Workflows"
      data-testid="navrail-workflows"
    >
      {WORKFLOW_ORDER.map((wf) => (
        <RailButton
          key={wf}
          icon={<I d={WF_ICONS[wf]} />}
          label={WORKFLOWS[wf].label}
          title={`${WORKFLOWS[wf].label} - ${WORKFLOWS[wf].tagline}`}
          active={activeWorkflow === wf}
          onClick={() => selectWorkflow(wf)}
          variant="workflow"
          orientation={orientation}
          productId={wf}
          binding={bindingForProduct(wf)?.spec}
          badge={wf === "research" ? researchSummons : undefined}
        />
      ))}
    </nav>
  );

  const moreButton = (
    <RailButton
      icon={<I d={UTIL_ICONS.more} size={15} />}
      label="More"
      title="More - all products, Operator, Trust, Settings"
      active={launcherOpen}
      onClick={() => {
        setLauncherOpen(true);
        // SPR-08/SPR-10 — More OPENS the launcher (no nav), so it emits a
        // routeless activation, identical to the `g m` hotkey path.
        emitProductActivate({ productId: "more", source: "click" });
      }}
      variant="more"
      orientation={orientation}
      productId="more"
      binding={bindingForProduct("more")?.spec}
    />
  );

  // Bottom rail (SPR-06 default): a horizontal bar along the window bottom.
  // Home (brain mark) anchors the leading edge; the four doors sit centred so the
  // eye lands on them; Search + More cluster on the trailing edge as
  // overflow. The accent border is on TOP (its inner edge, toward the
  // working region) — symmetric with the left rail's right border.
  if (isBottom) {
    return (
      <>
        <aside
          className={
            "h-14 w-full shrink-0 flex items-stretch bg-ink dark:bg-void border-t-edge border-sun " +
            (isMobile ? "absolute bottom-0 left-0 z-40 shadow-z3" : "") +
            (showRail ? "" : " hidden")
          }
          aria-label="Primary navigation"
        >
          {homeButton}
          <nav className="flex items-center px-1.5" aria-label="Utilities">
            {searchButton}
          </nav>
          <div className="mx-1.5 my-2 border-l border-white/10" aria-hidden="true" />
          <div className="flex-1 flex items-center justify-center">
            {workflowGroup}
          </div>
          <div className="mx-1.5 my-2 border-l border-white/10" aria-hidden="true" />
          <nav className="flex items-center px-1.5" aria-label="More">
            {moreButton}
          </nav>
        </aside>

        <ProductsLauncher open={launcherOpen} onClose={() => setLauncherOpen(false)} />
      </>
    );
  }

  // Left rail (legacy / rollback / stories). Unchanged vertical layout.
  return (
    <>
      <aside
        className={
          "w-[72px] shrink-0 h-full flex flex-col bg-ink dark:bg-void border-r-edge border-sun " +
          (isMobile ? "absolute top-0 left-0 z-40 shadow-z3" : "") +
          (showRail ? "" : " hidden")
        }
        aria-label="Primary navigation"
      >
        {isMobile && (
          <button
            type="button"
            title="Close navigation"
            aria-label="Close navigation"
            onClick={() => setCollapsed(true)}
            className="absolute -right-8 top-1 w-8 h-8 flex items-center justify-center bg-ink text-sun border-edge border-sun rounded text-[13px]"
          >
            ✕
          </button>
        )}

        {homeButton}

        {/* Utility cluster (Search) — visually subordinate to the four doors. */}
        <nav className="pt-1 flex flex-col gap-0.5" aria-label="Utilities">
          {searchButton}
        </nav>

        <div className="my-2 mx-3 border-t border-white/10" aria-hidden="true" />

        {workflowGroup}

        {/* Footer: single More affordance (overflow). */}
        <nav
          className="border-t border-white/10 py-2 flex flex-col gap-1"
          aria-label="More"
        >
          {moreButton}
        </nav>
      </aside>

      <ProductsLauncher open={launcherOpen} onClose={() => setLauncherOpen(false)} />
    </>
  );
}

export default NavRail;
