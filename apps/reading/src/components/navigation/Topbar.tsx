import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import type { NavigateFunction } from "react-router-dom";

import { LemonInput } from "../lemon/LemonInput";
import { LemonDropdown, LemonMenuItem } from "../lemon/LemonDropdown";
import LemonButton from "../lemon/LemonButton";
import { SHORTCUT_EVENTS } from "../../workspace/shortcuts";
import { workflowForRoute } from "../../shell/workflowTaxonomy";
import {
  sceneForWorkflow,
  type SceneAction,
  type SceneTab,
} from "../../shell/sceneRegistry";

/**
 * Topbar — the scene chrome (SPR-05) hosted in a single header.
 *
 * On a WORKFLOW route (`workflowForRoute(pathname)` non-null) the Topbar IS the
 * scene chrome: two rows.
 *   row 1   breadcrumbs · action bar (the active workflow's verbs) · search · account
 *   row 2   in-scene tab strip (the views of the workflow's primary object)
 * On a SHARED/operator route (billing, settings, trust …) the Topbar renders
 * exactly as it did before SPR-05 — bare: breadcrumbs · search · account, no
 * second row.
 *
 * The load-bearing call: the chrome lives HERE, not in a second bar wrapping
 * every route. The modes already render their own HeaderBar inside the scene
 * body — a separate zone — so a second chrome bar would double-stack. The
 * Topbar absorbing the chrome keeps one header.
 *
 * Tabs are ROUTE-LINKED, not body-swappers: the scene body is route-rendered
 * into PanelLayout's mainSlot, so a tab that swapped the body would fight that
 * architecture. Each `built` tab is a NavLink to its sub-view route; the active
 * tab reflects the current URL. A `soon` tab is disabled with a small badge —
 * an honest affordance, never a link to a surface that doesn't exist.
 *
 * Breadcrumb extension API: a route renders <BreadcrumbScope crumbs={[…]} />
 * inside its component to override the default route-segment crumbs. S4 ships
 * the default-derived crumbs only; per-route overrides come online as S5+ mode
 * ports happen.
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

/** Fire a scene action's intent: navigate via the router, or dispatch a window
 *  event the shell already listens for (palette/launcher toggles in
 *  shortcuts.ts + ProductsLauncher.tsx). No dead handlers — every intent
 *  resolves to a real shell behavior. */
function runIntent(action: SceneAction, navigate: NavigateFunction): void {
  if (action.intent.kind === "navigate") {
    navigate(action.intent.to);
  } else {
    window.dispatchEvent(new CustomEvent(action.intent.event));
  }
}

/** The contextual action bar — the active workflow's verbs as Lemon buttons.
 *  The first verb is primary (sun fill); the rest are secondary. */
function ActionBar({ actions }: { actions: SceneAction[] }) {
  const navigate = useNavigate();
  if (actions.length === 0) return null;
  return (
    <div className="flex items-center gap-1.5 shrink-0">
      {actions.map((a, i) => (
        <LemonButton
          key={a.id}
          variant={i === 0 ? "primary" : "secondary"}
          size="sm"
          onClick={() => runIntent(a, navigate)}
        >
          {a.label}
        </LemonButton>
      ))}
    </div>
  );
}

/** A `soon` tab: disabled, with a small badge. Never a link. */
function SoonTab({ tab }: { tab: SceneTab }) {
  return (
    <span
      aria-disabled="true"
      className="inline-flex items-center gap-1.5 px-2 py-2 text-[12.5px] font-mono text-shadow-1 dark:text-moonlight/60 cursor-default border-b-2 border-transparent"
    >
      <span>{tab.label}</span>
      <span className="px-1.5 py-0.5 rounded-full text-[9px] uppercase tracking-[0.1em] font-semibold bg-ice-3 dark:bg-charcoal-1 text-shadow-2 dark:text-moonlight">
        soon
      </span>
    </span>
  );
}

/** A `built` tab: a NavLink to its sub-view route. Active tab gets the
 *  sun-yellow underline (Werner skin); the URL is the single source of truth
 *  for which tab is active. */
function BuiltTab({ tab }: { tab: SceneTab }) {
  return (
    <NavLink
      to={tab.to as string}
      end={tab.to === "/"}
      className={({ isActive }) =>
        "inline-flex items-center px-2 py-2 text-[12.5px] font-mono border-b-2 transition-colors " +
        (isActive
          ? "border-sun text-ink dark:text-bright font-semibold"
          : "border-transparent text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright")
      }
    >
      {tab.label}
    </NavLink>
  );
}

/** The in-scene tab strip — the second row. The workflow's primary object has
 *  several views; each is a route-linked tab. */
function TabStrip({ tabs }: { tabs: SceneTab[] }) {
  if (tabs.length === 0) return null;
  return (
    <nav
      aria-label="Scene views"
      className="h-9 shrink-0 flex items-center gap-4 px-4 bg-ice-1 dark:bg-charcoal-2 border-b border-ice-4 dark:border-charcoal-1"
    >
      {tabs.map((tab) =>
        tab.builtState === "built" && tab.to ? (
          <BuiltTab key={tab.id} tab={tab} />
        ) : (
          <SoonTab key={tab.id} tab={tab} />
        ),
      )}
    </nav>
  );
}

export function Topbar() {
  const { pathname } = useLocation();
  const crumbs = defaultBreadcrumbsFor(pathname);

  // The scene chrome renders only on workflow routes. On a shared/operator
  // route (workflowForRoute → null) `scene` is null and both the action bar +
  // tab strip drop out, leaving the bare Topbar.
  const workflow = workflowForRoute(pathname);
  const scene = sceneForWorkflow(workflow);

  return (
    <div className="shrink-0">
      <header
        className="h-11 flex items-center gap-3 px-4 bg-ice-1 dark:bg-charcoal-2 border-b-edge border-sun"
        role="banner"
      >
        {/* breadcrumbs */}
        <nav aria-label="Breadcrumb" className="flex-1 min-w-0">
          <ol className="flex items-center gap-1.5 text-[12.5px] font-mono text-shadow-1 dark:text-moonlight overflow-x-auto whitespace-nowrap">
            {crumbs.map((c, i) => (
              <li key={i} className="flex items-center gap-1.5">
                {i > 0 && (
                  <span aria-hidden="true" className="text-shadow-1 dark:text-moonlight/60">
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

        {/* scene action bar — the active workflow's verbs (workflow routes only) */}
        {scene && <ActionBar actions={scene.actions} />}

        {/* search · palette trigger */}
        <LemonInput
          sizing="sm"
          wrapperClassName="w-[260px] cursor-pointer"
          placeholder="search · ⌘K"
          kbdHint="⌘K"
          iconLeft={<span aria-hidden="true">⌕</span>}
          readOnly
          onClick={() => {
            window.dispatchEvent(new CustomEvent(SHORTCUT_EVENTS.PALETTE_TOGGLE));
          }}
        />

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
              <div className="my-1 border-t border-ice-4 dark:border-charcoal-1" />
              <LemonMenuItem onClick={close}>Sign out</LemonMenuItem>
            </>
          )}
        </LemonDropdown>
      </header>

      {/* scene tab strip — second row (workflow routes only) */}
      {scene && <TabStrip tabs={scene.tabs} />}
    </div>
  );
}

export default Topbar;
