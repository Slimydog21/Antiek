import { NavLink } from "react-router-dom";

/**
 * @deprecated Superseded by `AppShell` (S4 of the UI redesign).
 *
 * `AppShell` (`src/AppShell.tsx`) renders the new global chrome:
 *   - `NavRail` — always-visible 60px icon column
 *   - `Topbar`  — breadcrumbs + ⌘K + account
 *   - `PanelLayout` — left/right docks + floating layer + main slot
 *
 * This file stays in the tree as a fallback during the mid-migration
 * window. Per `docs/ui_redesign_posthog/sprint_12_visual_regression_release.html`
 * WP-12.4 it is deleted after one zero-rollback sprint following the
 * `VITE_ANTIEK_UI=v2` cutover.
 *
 * Do NOT use this in new code. New routes wrap their content in
 * `<PanelHost>` (from `src/workspace/PanelHost.tsx`) and let AppShell
 * provide the chrome.
 */
export default function HeaderBar({
  children,
}: {
  children?: React.ReactNode;
}) {
  return (
    <header className="px-4 py-3 bg-white border-b border-stone-200 flex items-center justify-between gap-4 shrink-0">
      <div className="flex items-center gap-4">
        <span className="text-base font-semibold tracking-tight">Antiek</span>
        <nav className="flex items-center bg-stone-100 rounded-md p-0.5 text-xs">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `px-2.5 py-1 rounded transition-colors ${
                isActive
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-900"
              }`
            }
          >
            Research
          </NavLink>
          <NavLink
            to="/wrestle"
            className={({ isActive }) =>
              `px-2.5 py-1 rounded transition-colors ${
                isActive
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-900"
              }`
            }
          >
            Wrestle
          </NavLink>
          <NavLink
            to="/sources"
            className={({ isActive }) =>
              `px-2.5 py-1 rounded transition-colors ${
                isActive
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-900"
              }`
            }
          >
            Sources
          </NavLink>
          <NavLink
            to="/create"
            className={({ isActive }) =>
              `px-2.5 py-1 rounded transition-colors ${
                isActive
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-900"
              }`
            }
          >
            Create
          </NavLink>
          <NavLink
            to="/brainstorm"
            className={({ isActive }) =>
              `px-2.5 py-1 rounded transition-colors ${
                isActive
                  ? "bg-white text-stone-900 shadow-sm font-medium"
                  : "text-stone-500 hover:text-stone-900"
              }`
            }
          >
            Brainstorm
          </NavLink>
        </nav>
        <nav className="flex items-center gap-3 text-xs text-stone-500">
          <NavLink
            to="/privacy"
            className={({ isActive }) =>
              isActive ? "text-stone-900 underline" : "hover:text-stone-900"
            }
          >
            Privacy
          </NavLink>
          <NavLink
            to="/pricing"
            className={({ isActive }) =>
              isActive ? "text-stone-900 underline" : "hover:text-stone-900"
            }
          >
            Pricing
          </NavLink>
          <NavLink
            to="/operator"
            className={({ isActive }) =>
              isActive ? "text-stone-900 underline" : "hover:text-stone-900"
            }
          >
            Operator
          </NavLink>
          <NavLink
            to="/trust"
            className={({ isActive }) =>
              isActive ? "text-stone-900 underline" : "hover:text-stone-900"
            }
          >
            Trust
          </NavLink>
        </nav>
      </div>
      <div className="flex items-center gap-3">{children}</div>
    </header>
  );
}
