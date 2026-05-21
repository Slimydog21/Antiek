import { useState } from "react";
import { NavLink } from "react-router-dom";
import type { ReactNode } from "react";

import { useWorkspace } from "../../workspace/WorkspaceStore";
import { useViewportTier } from "../../workspace/useViewportTier";

/**
 * NavRail — always-visible 60-px icon column on the far left.
 *
 * Top:    primary modes (Research, Wrestle, Create, Brainstorm,
 *         Notebooks, Sources).
 * Middle: ProjectTree toggle — opens the docked-left ProjectTree
 *         panel via the workspace store, mirroring ⌘B.
 * Footer: Privacy, Pricing, Operator, Trust, Settings (per master
 *         spec §4 NavRail layout table).
 *
 * Icons are inline SVG (S11 replaced the S4 emoji glyphs). Tooltips
 * use the native title attr for hover + screen-reader nav. Active
 * route gets the sun-yellow accent + ink left-edge bar.
 */
type Item = {
  to: string;
  icon: ReactNode;
  label: string;
  end?: boolean;
  group: "main" | "middle" | "footer";
};

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
  research: "M3 12 L8 7 L13 12 L18 7 L21 9 M3 12 V20 H21 V12",        // peaks + horizon
  wrestle:  "M4 5 H20 V19 H4 Z M4 9 H20 M9 13 H15 M9 16 H13",         // doc with lines
  create:   "M5 19 L12 5 L19 19 M9 14 H15",                            // triangular A
  brainstorm: "M6 14 a6 6 0 1 1 12 0 M9 14 V18 H15 V14 M11 21 H13",   // lightbulb
  notebook: "M4 4 H18 V20 H4 Z M4 4 V20 H6 V4 M9 9 H15 M9 13 H14",    // bound notebook
  sources:  "M3 7 H21 M3 12 H21 M3 17 H21 M7 4 V20 M17 4 V20",        // grid
  projects: "M3 6 H10 L12 4 H21 V18 H3 Z M6 10 H18 M6 14 H15",        // folder w/ rows
  privacy:  "M12 3 L5 6 V12 C5 16 8 19 12 21 C16 19 19 16 19 12 V6 Z", // shield
  pricing:  "M3 8 H21 V18 H3 Z M3 8 L5 4 H19 L21 8 M9 13 H15",        // wallet
  operator: "M6 4 H18 V20 H6 Z M9 8 H15 M9 12 H15 M9 16 H13",         // device
  trust:    "M12 3 L21 7 V13 C21 17 17 20 12 21 C7 20 3 17 3 13 V7 Z M9 12 L11 14 L15 10", // shield+check
  settings: "M12 8 a4 4 0 1 1 0 8 a4 4 0 1 1 0 -8 M12 2 V5 M12 19 V22 M2 12 H5 M19 12 H22 M5 5 L7 7 M17 17 L19 19 M5 19 L7 17 M17 7 L19 5", // gear
};

const ITEMS: Item[] = [
  { to: "/",             icon: <I d={ICONS.research} />,   label: "Research",   end: true,  group: "main" },
  { to: "/wrestle",      icon: <I d={ICONS.wrestle} />,    label: "Wrestle",                group: "main" },
  { to: "/create",       icon: <I d={ICONS.create} />,     label: "Create",                 group: "main" },
  { to: "/brainstorm",   icon: <I d={ICONS.brainstorm} />, label: "Brainstorm",             group: "main" },
  { to: "/notebooks",    icon: <I d={ICONS.notebook} />,   label: "Notebooks",              group: "main" },
  { to: "/sources",      icon: <I d={ICONS.sources} />,    label: "Sources",                group: "main" },

  // Footer (governance + meta routes).
  { to: "/privacy",      icon: <I d={ICONS.privacy} />,    label: "Privacy",                group: "footer" },
  { to: "/pricing",      icon: <I d={ICONS.pricing} />,    label: "Pricing",                group: "footer" },
  { to: "/operator",     icon: <I d={ICONS.operator} />,   label: "Operator",               group: "footer" },
  { to: "/trust",        icon: <I d={ICONS.trust} />,      label: "Trust",                  group: "footer" },
  { to: "/settings",     icon: <I d={ICONS.settings} />,   label: "Settings",               group: "footer" },
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

/**
 * Middle group — ProjectTree toggle. Lives between the primary modes
 * and the footer per master spec §4 NavRail layout. Toggling the panel
 * goes through the workspace store (same path ⌘B uses).
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
            {
              mode: "docked-left",
              title: "Project",
              id: PROJECT_TREE_PANEL_ID,
            },
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

export function NavRail() {
  const main = ITEMS.filter((i) => i.group === "main");
  const footer = ITEMS.filter((i) => i.group === "footer");
  const tier = useViewportTier();
  // S11 acceptance: below md tier the NavRail collapses to a hamburger.
  // The operator can pop the rail open for navigation, and any nav
  // click auto-closes it. At md+ the rail is always visible.
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
      {/* Werner mark — pinned to top */}
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

      <nav className="flex-1 py-2 flex flex-col gap-1">
        {main.map((it) => (
          <NavRailItem key={it.to} {...it} />
        ))}

        {/* Middle group — ProjectTree toggle, separated by a thin rule. */}
        <div className="my-2 mx-3 border-t border-white/10" aria-hidden="true" />
        <ProjectTreeToggleItem />
      </nav>

      <nav className="border-t border-white/10 py-2 flex flex-col gap-1">
        {footer.map((it) => (
          <NavRailItem key={it.to} {...it} />
        ))}
      </nav>
    </aside>
  );
}

function NavRailItem({ to, icon, label, end }: Item) {
  return (
    <NavLink
      to={to}
      end={end}
      title={label}
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
            {icon}
          </span>
          <span className="sr-only">{label}</span>
        </>
      )}
    </NavLink>
  );
}

export default NavRail;
