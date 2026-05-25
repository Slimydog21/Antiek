import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";

import { useWorkspace } from "../workspace/WorkspaceStore";
import { useViewportTier } from "../workspace/useViewportTier";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import {
  WORKFLOWS,
  WORKFLOW_ORDER,
  workflowForPath,
  type Workflow,
} from "./workflowTaxonomy";
import { ProductsLauncher } from "./ProductsLauncher";

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
 */
const PROJECT_TREE_PANEL_ID = "shortcuts:projecttree";

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
  plus: "M12 5 V19 M5 12 H19", // +
  // "More" — the single non-workflow affordance. A grid glyph reads as
  // "all products / everything else", which is exactly what it opens.
  more: "M4 4 H10 V10 H4 Z M14 4 H20 V10 H14 Z M4 14 H10 V20 H4 Z M14 14 H20 V20 H14 Z", // ⊞ grid
};

function WernerMarkInline() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" className="w-7 h-7">
      <ellipse cx="16" cy="17" rx="9" ry="11" fill="var(--werner-coat)" />
      <ellipse cx="16" cy="19" rx="5.5" ry="8" fill="var(--werner-belly)" />
      <circle cx="13" cy="13" r="1.4" fill="var(--werner-eye)" />
      <circle cx="19" cy="13" r="1.4" fill="var(--werner-eye)" />
      <path d="M14.5 16 L16 18 L17.5 16 Z" fill="var(--werner-bill)" />
      <ellipse cx="12.5" cy="29" rx="2.5" ry="1" fill="var(--werner-foot)" />
      <ellipse cx="19.5" cy="29" rx="2.5" ry="1" fill="var(--werner-foot)" />
    </svg>
  );
}

/** A rail button (workflow, util, or footer). Mirrors the prior rail's
 *  visual language: sun-yellow active fill + ink left-edge bar. */
function RailButton({
  icon,
  label,
  active,
  onClick,
  title,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick: () => void;
  title: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={
        "h-10 mx-1.5 flex items-center justify-center rounded relative " +
        (active
          ? "bg-sun text-ink"
          : "text-ice-2/70 hover:text-ice-1 hover:bg-white/10")
      }
    >
      {active && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-ink"
        />
      )}
      <span className="leading-none" aria-hidden="true">
        {icon}
      </span>
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

  // The project-tree dock toggle is preserved from the prior rail; it
  // opens the content-first tree (zone 2) as a docked-left panel, the
  // same path ⌘B uses. We expose it via the "New / tree" area.
  const treeOpen = useWorkspace((s) => Boolean(s.panels[PROJECT_TREE_PANEL_ID]));
  const openPanel = useWorkspace((s) => s.open);
  const closePanel = useWorkspace((s) => s.close);
  const toggleTree = () => {
    if (treeOpen) closePanel(PROJECT_TREE_PANEL_ID);
    else
      openPanel(
        "ProjectTree",
        {},
        { mode: "docked-left", title: "Project", id: PROJECT_TREE_PANEL_ID },
      );
  };

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
          "w-[60px] shrink-0 h-full flex flex-col bg-ink dark:bg-void border-r-edge border-sun " +
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

        {/* Werner mark — pinned to top, returns to the Research home. */}
        <button
          type="button"
          title="Antiek · Werner"
          onClick={() => navigate("/")}
          className="h-12 flex items-center justify-center border-b-edge border-sun bg-sun/95 hover:bg-sun"
        >
          <WernerMarkInline />
        </button>

        {/* Utility group — Search + New(tree). */}
        <nav className="pt-2 flex flex-col gap-1" aria-label="Utilities">
          <RailButton
            icon={<I d={UTIL_ICONS.search} />}
            label="Search"
            title="Search · ⌘K"
            onClick={openSearch}
          />
          <RailButton
            icon={<I d={UTIL_ICONS.plus} />}
            label="New / Project tree"
            title="Toggle the project tree (⌘B)"
            active={treeOpen}
            onClick={toggleTree}
          />
        </nav>

        <div className="my-2 mx-3 border-t border-white/10" aria-hidden="true" />

        {/* THE FOUR WORKFLOWS (zone 1). Read from WORKFLOW_ORDER so the
            rail can never drift from the taxonomy. */}
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
              title={`${WORKFLOWS[wf].label} — ${WORKFLOWS[wf].tagline}`}
              active={activeWorkflow === wf}
              onClick={() => selectWorkflow(wf)}
            />
          ))}
        </nav>

        {/* Footer — the SINGLE "More" affordance. Opens the
            ProductsLauncher, which carries the full mode inventory AND
            the operator surfaces (Operator / Trust / Settings + the
            shared bucket). The three separate footer buttons are gone:
            the rail now shows exactly four workflows + More. */}
        <nav
          className="border-t border-white/10 py-2 flex flex-col gap-1"
          aria-label="More"
        >
          <RailButton
            icon={<I d={UTIL_ICONS.more} />}
            label="More"
            title="More — all products, Operator, Trust, Settings"
            active={launcherOpen}
            onClick={() => setLauncherOpen(true)}
          />
        </nav>
      </aside>

      <ProductsLauncher open={launcherOpen} onClose={() => setLauncherOpen(false)} />
    </>
  );
}

export default NavRail;
