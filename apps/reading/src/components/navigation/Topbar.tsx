import { Link, useLocation } from "react-router-dom";

import { LemonDropdown, LemonMenuItem } from "../lemon/LemonDropdown";
import LemonButton from "../lemon/LemonButton";

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
export type Crumb = { label: string; to?: string };

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
    const label = known[seg] ?? seg;
    crumbs.push({ label, to: acc });
  }
  return crumbs;
}

export function Topbar() {
  const { pathname } = useLocation();
  const crumbs = defaultBreadcrumbsFor(pathname);

  return (
    <header
      className="h-11 shrink-0 flex items-center gap-3 px-4 bg-ice-1 dark:bg-charcoal-2 border-b-edge border-sun"
      role="banner"
    >
      {/* breadcrumbs */}
      <nav aria-label="Breadcrumb" className="flex-1 min-w-0">
        <ol className="flex items-center gap-1.5 text-[12.5px] font-mono text-ink-soft dark:text-moonlight overflow-x-auto whitespace-nowrap">
          {crumbs.map((c, i) => (
            <li key={i} className="flex items-center gap-1.5">
              {i > 0 && (
                <span aria-hidden="true" className="text-ink-mute dark:text-moonlight/60">
                  ›
                </span>
              )}
              {c.to && i < crumbs.length - 1 ? (
                <Link
                  to={c.to}
                  className="text-ink dark:text-bright hover:underline"
                >
                  {c.label}
                </Link>
              ) : (
                <span className="text-ink dark:text-bright font-semibold">
                  {c.label}
                </span>
              )}
            </li>
          ))}
        </ol>
      </nav>

      {/* Search lives on the NavRail (⌕ · ⌘K), the single canonical
          entry to the CommandPalette. The Topbar no longer carries a
          second search box — one door, not two. */}

      {/* account */}
      <LemonDropdown
        align="below-right"
        trigger={
          <LemonButton variant="tertiary" size="sm" aria-label="Account">
            👤
          </LemonButton>
        }
      >
        {({ close }) => (
          <>
            <LemonMenuItem onClick={close}>Profile</LemonMenuItem>
            <LemonMenuItem onClick={close}>Settings</LemonMenuItem>
            <div className="my-1 border-t border-rule dark:border-charcoal-1" />
            <LemonMenuItem onClick={close}>Sign out</LemonMenuItem>
          </>
        )}
      </LemonDropdown>
    </header>
  );
}

export default Topbar;
