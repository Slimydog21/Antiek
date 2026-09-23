import { Link, useLocation, useNavigate } from "react-router-dom";

import { LemonDropdown, LemonMenuItem } from "../lemon/LemonDropdown";
import LemonButton from "../lemon/LemonButton";
import { toast } from "../lemon/LemonToast";
import { useAuth } from "../../lib/auth";

/**
 * Topbar — slim (44 px) horizontal bar that sits above the dock row.
 *
 * Two regions:
 *   left   breadcrumbs (route-derived; modes can extend via useBreadcrumbs)
 *   right  account dropdown
 *
 * Search is NOT here — it has one canonical home, the NavRail ⌕ button
 * (⌘K), which opens the CommandPalette. A second Topbar search box read
 * as two search affordances; removed.
 *
 * Breadcrumb extension API: a route renders
 *   <BreadcrumbScope crumbs={[…]} />
 * inside its component to override the default route-segment crumbs.
 * S4 ships the default-derived crumbs only; per-route overrides come
 * online as S5+ mode ports happen.
 */
export type Crumb = { label: string; to?: string; id?: boolean };

/** Generate breadcrumbs from the current pathname. */
function defaultBreadcrumbsFor(pathname: string): Crumb[] {
  if (pathname === "/" || pathname === "")
    return [{ label: "Research" }];

  const segments = pathname.split("/").filter(Boolean);
  const known: Record<string, string> = {
    wrestle: "Wrestle",
    sources: "Sources",
    create: "Create",
    brainstorm: "Brainstorm",
    notebooks: "Notebooks",
    notebook: "Notebook",
    documents: "Documents",
    billing: "Billing",
    stats: "Stats",
    map: "Map",
    backtest: "Backtest",
    privacy: "Privacy",
    pricing: "Pricing",
    operator: "Operator",
    outcomes: "Outcomes",
    replay: "Replay",
    interview: "Interview",
    interviews: "Interviews",
    "loop-3": "Loop 3",
    "skill-rules": "Skill Rules",
    federation: "Federation",
    "cross-graph": "Cross-graph",
    citations: "Citations",
    investigations: "Investigations",
    payouts: "Payouts",
    trust: "Trust Center",
    inv: "Investigation",
    // Own Your Mind P0 — the three read-only surfaces (10-p0-implementation-brief.md).
    explain: "Explain",
    objective: "Objective",
    signals: "Signals",
  };
  const crumbs: Crumb[] = [];
  let acc = "";
  for (const seg of segments) {
    acc += "/" + seg;
    // A route word reads as a sentence-case label ("my-research" → "My
    // research"); a segment carrying digits is a record id and stays
    // verbatim, set as data.
    const id = !known[seg] && /\d/.test(seg);
    const label = known[seg] ?? (id ? seg : seg[0].toUpperCase() + seg.slice(1).replace(/-/g, " "));
    crumbs.push({ label, to: acc, id });
  }
  return crumbs;
}

export function Topbar() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { state, signOut } = useAuth();
  const crumbs = defaultBreadcrumbsFor(pathname);
  // The account shows the first letter of the signed-in email; with no
  // email, a drawn person glyph. Never an emoji (they render per-OS).
  const email = state.status === "authenticated" ? state.identity.email : null;
  const initial = email?.trim()[0]?.toUpperCase();

  return (
    <header
      className="h-11 shrink-0 flex items-center gap-3 px-4 bg-card border-b border-hairline"
      role="banner"
    >
      {/* breadcrumbs: the page named in words (sans); ids stay data (mono) */}
      <nav aria-label="Breadcrumb" className="flex-1 min-w-0">
        <ol className="flex items-center gap-1.5 text-sm text-2 overflow-x-auto whitespace-nowrap">
          {crumbs.map((c, i) => (
            <li key={i} className="flex items-center gap-1.5">
              {i > 0 && (
                <span aria-hidden="true" className="text-3">
                  ›
                </span>
              )}
              {c.to && i < crumbs.length - 1 ? (
                <Link to={c.to} className={`hover:text-1 hover:underline ${c.id ? "font-mono text-xs" : ""}`}>
                  {c.label}
                </Link>
              ) : (
                <span className={`text-1 font-medium ${c.id ? "font-mono text-xs" : ""}`}>{c.label}</span>
              )}
            </li>
          ))}
        </ol>
      </nav>

      {/* Search lives on the NavRail (⌕ · ⌘K), the single canonical
          entry to the CommandPalette. The Topbar no longer carries a
          second search box — one door, not two. */}

      {/* account — every item here does something real. "Profile" was cut:
          no profile route exists, and a menu item that only closes the
          menu is a dead control (Q7 honesty sweep). */}
      <LemonDropdown
        align="below-right"
        trigger={
          <LemonButton variant="tertiary" size="sm" aria-label="Account" className="!px-1">
            {initial ? (
              <span className="grid h-6 w-6 place-items-center rounded-full bg-inset font-sans text-xs font-semibold text-1">
                {initial}
              </span>
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                <circle cx="8" cy="5.5" r="2.75" />
                <path d="M2.75 14c.6-2.75 2.7-4.25 5.25-4.25s4.65 1.5 5.25 4.25" strokeLinecap="round" />
              </svg>
            )}
          </LemonButton>
        }
      >
        {({ close }) => (
          <>
            <LemonMenuItem
              onClick={() => {
                navigate("/settings");
                close();
              }}
            >
              Settings
            </LemonMenuItem>
            <div className="my-1 border-t border-rule dark:border-charcoal-1" />
            <LemonMenuItem
              onClick={() => {
                close();
                signOut().catch(() => {
                  // Honest failure: the session may still be live — say so
                  // instead of pretending the logout landed.
                  toast.err("Sign out failed — the session may still be active. Try again.");
                });
              }}
            >
              Sign out
            </LemonMenuItem>
          </>
        )}
      </LemonDropdown>
    </header>
  );
}

export default Topbar;
