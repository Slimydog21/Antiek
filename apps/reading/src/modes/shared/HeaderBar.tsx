import { NavLink } from "react-router-dom";

/**
 * Shared header bar across both modes. Carries the Antiek wordmark,
 * the mode toggle (Research / Wrestle), and optional right-aligned
 * children for mode-specific affordances (e.g. PDF upload button in
 * Wrestle mode, investigation-id chip in Research mode).
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
        </nav>
      </div>
      <div className="flex items-center gap-3">{children}</div>
    </header>
  );
}
