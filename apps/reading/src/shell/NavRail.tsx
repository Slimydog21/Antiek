import { useState } from "react";
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
import { ProductsLauncher } from "./ProductsLauncher";
import Werner from "../brand/Werner";

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
 *   │  ⌂     │  Werner mark
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
 */

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
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
  title: string;
  variant?: "workflow" | "utility" | "more";
}) {
  const isWorkflow = variant === "workflow";
  const color = active
    ? "bg-sun text-ink"
    : isWorkflow
    ? "text-ice-2/80 hover:text-ice-1 hover:bg-white/10"
    : "text-ice-2/50 hover:text-ice-2/70 hover:bg-white/5";
  const layout = isWorkflow
    ? "min-h-12 py-1 flex-col items-center justify-center"
    : "h-10 items-center justify-center";
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={
        "mx-1.5 flex rounded relative " +
        layout +
        " " +
        color
      }
    >
      {active && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-2 bottom-2 w-1 rounded-r bg-ink"
        />
      )}
      <span className="leading-none" aria-hidden="true">
        {icon}
      </span>
      {isWorkflow && (
        <span
          className="text-[10px] leading-[11px] mt-0.5 font-medium tracking-tight text-center w-full"
          aria-hidden="true"
        >
          {label}
        </span>
      )}
      <span className="sr-only">{label}</span>
    </button>
  );
}

export function NavRail() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const activeWorkflow = workflowForPath(pathname);

  const tier = useViewportTier();
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const [launcherOpen, setLauncherOpen] = useState<boolean>(false);
  const isMobile = tier === "sm" || tier === "md";
  const showRail = !isMobile || !collapsed;

  // SPR-12 M3 — the project-tree toggle that used to live on the rail is
  // gone; the floating Penguin mascot (shell/PenguinMascot.tsx) now floats
  // and opens the "shortcuts:projecttree" panel. The workspace store is no
  // longer touched from here.

  const openSearch = () =>
    window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PALETTE_TOGGLE));

  const selectWorkflow = (wf: Exclude<Workflow, "shared">) => {
    navigate(WORKFLOWS[wf].defaultRoute);
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

        {/* Werner mark pinned to top. SPR-12 M1 — now opens the unified
            branded home (/home), the product's front door, rather than the
            Research door ("/"). The white box that used to sit behind this
            mark is fixed in M4 (the idle pose is now an alpha-cut PNG), so
            it blends into the sun-yellow button. */}
        <button
          type="button"
          title="Antiek · home"
          aria-label="Antiek home"
          onClick={() => navigate("/home")}
          className="h-12 flex items-center justify-center border-b-edge border-sun bg-sun/95 hover:bg-sun"
        >
          <Werner mood="idle" size={28} />
        </button>

        {/* Utility cluster (Search) — visually subordinate to the four
            doors: smaller icon, muted tokens, grouped above the divider.
            Not a workflow destination. (SPR-12 M3 removed the "+ project /
            Project tree" toggle that used to sit here; the Penguin mascot
            owns the project tree now.) */}
        <nav className="pt-1 flex flex-col gap-0.5" aria-label="Utilities">
          <RailButton
            icon={<I d={UTIL_ICONS.search} size={15} />}
            label="Search"
            title="Search · ⌘K"
            onClick={openSearch}
            variant="utility"
          />
        </nav>

        <div className="my-2 mx-3 border-t border-white/10" aria-hidden="true" />

        {/* THE FOUR WORKFLOWS (zone 1). Read from WORKFLOW_ORDER only.
            Variant + visible labels + stronger weight make doors dominant. */}
        <nav
          className="flex-1 flex flex-col gap-1"
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
            />
          ))}
        </nav>

        {/* Footer: single More affordance (overflow). Distinct from doors
            because icon-only + muted + footer position. Opens launcher with
            Operator/Trust/Settings + all deep modes. One click reachability. */}
        <nav
          className="border-t border-white/10 py-2 flex flex-col gap-1"
          aria-label="More"
        >
          <RailButton
            icon={<I d={UTIL_ICONS.more} size={15} />}
            label="More"
            title="More - all products, Operator, Trust, Settings"
            active={launcherOpen}
            onClick={() => setLauncherOpen(true)}
            variant="more"
          />
        </nav>
      </aside>

      <ProductsLauncher open={launcherOpen} onClose={() => setLauncherOpen(false)} />
    </>
  );
}

export default NavRail;
