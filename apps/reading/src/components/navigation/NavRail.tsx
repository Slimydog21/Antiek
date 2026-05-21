import { NavLink } from "react-router-dom";

/**
 * NavRail — always-visible 60-px icon column on the far left.
 *
 * Sits OUTSIDE the PanelLayout dock zones so it stays put even when
 * both docks are empty. The Werner mark anchors the top; active route
 * gets the sun-yellow accent + ink left-edge bar (PostHog convention,
 * Antiek palette).
 *
 * S4 ships emoji glyphs; S11 swaps them for a tiny custom SVG icon set
 * + tooltips. Each icon's tooltip currently uses the native title attr.
 */
type Item = {
  to: string;
  icon: string;
  label: string;
  end?: boolean;
  group?: "footer";
};

const ITEMS: Item[] = [
  { to: "/", icon: "⌂", label: "Research", end: true },
  { to: "/wrestle", icon: "⏍", label: "Wrestle" },
  { to: "/create", icon: "❒", label: "Create" },
  { to: "/brainstorm", icon: "🜘", label: "Brainstorm" },
  { to: "/notebooks", icon: "❍", label: "Notebooks" },
  { to: "/sources", icon: "⚑", label: "Sources" },
  { to: "/operator", icon: "⚙", label: "Operator", group: "footer" },
  { to: "/trust", icon: "✦", label: "Trust", group: "footer" },
];

/**
 * The framed Werner mark — used at the top of the rail.
 * Inline SVG so it inherits CSS variables and renders crisply at
 * any DPR. Dark mode is automatic via prefers-color-scheme + tokens.css.
 */
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

export function NavRail() {
  const main = ITEMS.filter((i) => i.group !== "footer");
  const footer = ITEMS.filter((i) => i.group === "footer");

  return (
    <aside
      className="w-[60px] shrink-0 h-full flex flex-col bg-ink dark:bg-void border-r-edge border-sun"
      aria-label="Primary navigation"
    >
      {/* Werner mark — pinned to top */}
      <NavLink
        to="/"
        end
        title="Antiek · Werner"
        className={({ isActive }) =>
          "h-12 flex items-center justify-center border-b-edge border-sun " +
          (isActive
            ? "bg-sun"
            : "bg-sun/95 hover:bg-sun")
        }
      >
        <WernerMarkInline />
      </NavLink>

      <nav className="flex-1 py-2 flex flex-col gap-1">
        {main.map((it) => (
          <NavRailItem key={it.to} {...it} />
        ))}
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
          {/* left-edge accent bar on the active item */}
          {isActive && (
            <span
              aria-hidden="true"
              className="absolute left-0 top-1.5 bottom-1.5 w-1 rounded-r bg-ink"
            />
          )}
          <span className="text-[18px] leading-none" aria-hidden="true">
            {icon}
          </span>
          <span className="sr-only">{label}</span>
        </>
      )}
    </NavLink>
  );
}

export default NavRail;
