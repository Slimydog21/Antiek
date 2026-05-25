import { useState } from "react";
import { NavLink, useNavigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useWorkspace } from "../../workspace/WorkspaceStore";
import { useViewportTier } from "../../workspace/useViewportTier";
import { useActiveWorkflow } from "../../shell/activeWorkflow";
import type { ActiveWorkflow } from "../../shell/activeWorkflow";
import {
  WORKFLOWS,
  WORKFLOW_LABEL,
  WORKFLOW_HOME,
  workflowForRoute,
} from "../../shell/workflowTaxonomy";

/**
 * NavRail — always-visible 60-px icon column on the far left.
 *
 * Four-workflow IA (frontend-design spec, SPR-03). The rail carries exactly
 * the four workflows — Research · Read · Write · Speak — plus the chrome that
 * spans them (Search ⌘K, New, the ⊞ products launcher, the content-tree
 * toggle) and a governance footer (Trust, Settings). The ~31 other modes live
 * in the launcher + ⌘K, never the rail.
 *
 * Functional rationale: the rail answers one question — "which work?" — and
 * the product is four kinds of work, so the rail is four entries. A fifth
 * entry, or a submenu expanding a workflow into its modes, would be form
 * without a distinct function. Selecting a workflow sets the active-workflow
 * state (the content tree + scene read it) and routes to that workflow's home;
 * the active highlight is derived from the route, so a deep link (/inv/x)
 * lights Research without a click. Hard to vary: move a function off the rail
 * and the "which work" question loses its single answer.
 */
type FooterItem = { to: string; icon: ReactNode; label: string };

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

// Icon path constants — single-line SVG paths. Sized to a 24-grid.
const ICONS = {
  search:    "M11 11 m-7 0 a7 7 0 1 0 14 0 a7 7 0 1 0 -14 0 M21 21 L17 17", // magnifier
  plus:      "M12 5 V19 M5 12 H19",                                          // new
  research:  "M3 12 L8 7 L13 12 L18 7 L21 9 M3 12 V20 H21 V12",              // peaks + horizon
  read:      "M3 5 C5 4 9 4 12 6 C15 4 19 4 21 5 V19 C19 18 15 18 12 20 C9 18 5 18 3 19 Z M12 6 V20", // open book
  write:     "M4 20 H8 L19 9 L15 5 L4 16 Z M13 7 L17 11",                    // pencil
  speak:     "M9 3 h6 v8 a3 3 0 0 1 -6 0 Z M6 11 a6 6 0 0 0 12 0 M12 17 v4 M9 21 h6", // mic
  launcher:  "M3 3 H10 V10 H3 Z M14 3 H21 V10 H14 Z M3 14 H10 V21 H3 Z M14 14 H21 V21 H14 Z", // grid
  projects:  "M3 6 H10 L12 4 H21 V18 H3 Z M6 10 H18 M6 14 H15",              // folder w/ rows
  trust:     "M12 3 L21 7 V13 C21 17 17 20 12 21 C7 20 3 17 3 13 V7 Z M9 12 L11 14 L15 10", // shield+check
  settings:  "M12 8 a4 4 0 1 1 0 8 a4 4 0 1 1 0 -8 M12 2 V5 M12 19 V22 M2 12 H5 M19 12 H22 M5 5 L7 7 M17 17 L19 19 M5 19 L7 17 M17 7 L19 5", // gear
};

/** Workflow → its rail icon. */
const WORKFLOW_ICON: Record<ActiveWorkflow, ReactNode> = {
  research: <I d={ICONS.research} />,
  read: <I d={ICONS.read} />,
  write: <I d={ICONS.write} />,
  speak: <I d={ICONS.speak} />,
};

const FOOTER: FooterItem[] = [
  { to: "/trust", icon: <I d={ICONS.trust} />, label: "Trust" },
  { to: "/settings", icon: <I d={ICONS.settings} />, label: "Settings" },
];

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

/** Bare action button styled like a rail item (no route). */
function RailAction({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className="h-10 mx-1.5 flex items-center justify-center rounded relative text-ice-2/70 hover:text-ice-1 hover:bg-white/10"
    >
      {children}
    </button>
  );
}

/** One of the four workflows. Highlights when the route derives to it. */
function WorkflowRailItem({ workflow }: { workflow: ActiveWorkflow }) {
  const navigate = useNavigate();
  const setActive = useActiveWorkflow((s) => s.set);
  const { pathname } = useLocation();
  const isActive = workflowForRoute(pathname) === workflow;
  const label = WORKFLOW_LABEL[workflow];
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      aria-current={isActive ? "page" : undefined}
      onClick={() => {
        setActive(workflow);
        navigate(WORKFLOW_HOME[workflow]);
      }}
      className={
        "h-10 mx-1.5 flex items-center justify-center rounded relative " +
        (isActive ? "bg-sun text-ink" : "text-ice-2/70 hover:text-ice-1 hover:bg-white/10")
      }
    >
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-ink"
        />
      )}
      <span className="leading-none" aria-hidden="true">
        {WORKFLOW_ICON[workflow]}
      </span>
      <span className="sr-only">{label}</span>
    </button>
  );
}

/**
 * ProjectTree toggle — opens/closes the docked-left content column.
 * Same path ⌘B uses (workspace store, panel id shortcuts:projecttree).
 */
function ProjectTreeToggleItem() {
  const isOpen = useWorkspace((s) => Boolean(s.panels[PROJECT_TREE_PANEL_ID]));
  const open = useWorkspace((s) => s.open);
  const close = useWorkspace((s) => s.close);
  return (
    <button
      type="button"
      title="Toggle Project tree (⌘B)"
      onClick={() => {
        if (isOpen) close(PROJECT_TREE_PANEL_ID);
        else
          open(
            "ProjectTree",
            {},
            { mode: "docked-left", title: "Project", id: PROJECT_TREE_PANEL_ID },
          );
      }}
      className={
        "h-10 mx-1.5 flex items-center justify-center rounded relative " +
        (isOpen
          ? "bg-sun text-ink"
          : "text-ice-2/70 hover:text-ice-1 hover:bg-white/10")
      }
    >
      {isOpen && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-ink"
        />
      )}
      <I d={ICONS.projects} />
      <span className="sr-only">Project tree</span>
    </button>
  );
}

/** New — scoped to the active workflow (never a blind "/" route). */
function NewItem() {
  const navigate = useNavigate();
  const active = useActiveWorkflow((s) => s.active);
  return (
    <RailAction
      title={`New in ${WORKFLOW_LABEL[active]} · ⌘N`}
      onClick={() => navigate(WORKFLOW_HOME[active])}
    >
      <I d={ICONS.plus} size={20} />
    </RailAction>
  );
}

export function NavRail() {
  const tier = useViewportTier();
  const [collapsed, setCollapsed] = useState<boolean>(false);
  const isMobile = tier === "sm" || tier === "md";
  const showRail = !isMobile || !collapsed;

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
      {/* Werner mark — pinned to top, links home (Research) */}
      <NavLink
        to="/"
        end
        title="Antiek · Werner"
        className={({ isActive }) =>
          "h-12 flex items-center justify-center border-b-edge border-sun " +
          (isActive ? "bg-sun" : "bg-sun/95 hover:bg-sun")
        }
      >
        <WernerMarkInline />
      </NavLink>

      {/* Search + New — chrome that spans every workflow */}
      <div className="pt-2 flex flex-col gap-1">
        <RailAction
          title="Search · ⌘K"
          onClick={() => window.dispatchEvent(new Event("antiek:palette:toggle"))}
        >
          <I d={ICONS.search} />
        </RailAction>
        <NewItem />
      </div>

      <div className="my-2 mx-3 border-t border-white/10" aria-hidden="true" />

      {/* The four workflows */}
      <nav className="flex flex-col gap-1" aria-label="Workflows">
        {WORKFLOWS.map((w) => (
          <WorkflowRailItem key={w} workflow={w} />
        ))}
      </nav>

      <div className="my-2 mx-3 border-t border-white/10" aria-hidden="true" />

      {/* Products launcher + content-tree toggle */}
      <div className="flex flex-col gap-1">
        <RailAction
          title="All products…"
          onClick={() => window.dispatchEvent(new Event("antiek:launcher:toggle"))}
        >
          <I d={ICONS.launcher} />
        </RailAction>
        <ProjectTreeToggleItem />
      </div>

      <div className="flex-1" />

      <nav className="border-t border-white/10 py-2 flex flex-col gap-1" aria-label="Governance">
        {FOOTER.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            title={it.label}
            className={({ isActive }) =>
              "h-10 mx-1.5 flex items-center justify-center rounded relative " +
              (isActive
                ? "bg-sun text-ink"
                : "text-ice-2/70 hover:text-ice-1 hover:bg-white/10")
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span
                    aria-hidden="true"
                    className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-ink"
                  />
                )}
                <span className="leading-none" aria-hidden="true">
                  {it.icon}
                </span>
                <span className="sr-only">{it.label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

export default NavRail;
