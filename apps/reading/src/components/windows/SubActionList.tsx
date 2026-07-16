import { useNavigate } from "react-router-dom";

import {
  MODE_TAXONOMY,
  WORKFLOWS,
  type ModeEntry,
  type Workflow,
} from "../../shell/workflowTaxonomy";
import { useWindows } from "../../workspace/windowsStore";
import { useInWindow } from "./windowHostContext";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * SubActionList — the sub-action window PAGE (SPR-04 M1, the windows-default
 * keystone). NEW page, purpose-built to be hosted in a WorkspaceWindow.
 *
 * When the operator activates a PRODUCT (Research / Read / Write / Speak) from
 * the launcher, that activation opens a floating window hosting this page over
 * the scene (M3: window is the default for a within-contract product
 * activation). The page lists that workflow's MODE_TAXONOMY entries — the
 * sub-actions/destinations of the product — as rows the operator clicks to
 * dive in. It is data-driven from MODE_TAXONOMY filtered by `workflow`, NEVER a
 * hardcoded list, so a taxonomy change (a new mode, a re-homed door) shows up
 * here automatically and the completeness test that pins MODE_TAXONOMY keeps it
 * honest.
 *
 * Why this is purpose-built for windows (not a route-hosted page under the
 * (a)+(b) contract): it has no full-page route of its own. It only ever renders
 * inside a window, so its surface is authored glass-native — it uses
 * `bg-transparent` and `h-full` directly (it does not need `useInWindow()` to
 * conditionally drop an opaque bg, because it never carries one). `useInWindow`
 * is asserted defensively so a future stray full-page mount degrades to opaque
 * rather than rendering invisibly over a white page.
 *
 * Clicking a row:
 *   - if the row has a bare route → navigate(route) and close this window
 *     (the window was the menu; the destination is the page),
 *   - if the row is a param route (e.g. /outcomes/:id) → navigate its bare
 *     index when that is itself a real route, else leave it (the row is shown
 *     so the inventory is honest, but there is no instance to open from here),
 *   - an unbuilt row is shown dimmed and does nothing (honest, not hidden).
 */

export interface SubActionListProps {
  /** Which workflow's sub-actions to list. Supplied via the window payload. */
  workflow?: Workflow;
  /** The window id, so a row click can close THIS window after navigating. */
  __windowId?: string;
}

/** Bare (param-free) routes the taxonomy declares — used to resolve a param
 *  route to its real index (mirrors ProductsLauncher.BARE_ROUTES). */
const BARE_ROUTES = new Set(
  MODE_TAXONOMY.filter((m) => m.route && !m.route.includes(":")).map(
    (m) => m.route as string,
  ),
);

/** Resolve a mode's clickable destination, or null if it isn't navigable from
 *  here (unbuilt, or a param route with no real bare index). */
function destinationFor(m: ModeEntry): string | null {
  if (!m.built || !m.route) return null;
  if (!m.route.includes(":")) return m.route;
  const index = m.route.split("/:")[0];
  return BARE_ROUTES.has(index) ? index : null;
}

export default function SubActionList({ workflow, __windowId }: SubActionListProps) {
  const navigate = useNavigate();
  const closeWindow = useWindows((s) => s.close);
  // Defensive: this page is window-only. If it is ever mounted full-page it
  // should still be readable rather than invisible over a white route body.
  const inWindow = useInWindow();

  const meta = workflow && workflow !== "shared" ? WORKFLOWS[workflow] : null;
  const modes = workflow
    ? MODE_TAXONOMY.filter((m) => m.workflow === workflow)
    : [];

  const onRow = (m: ModeEntry) => {
    const dest = destinationFor(m);
    if (!dest) return;
    navigate(dest);
    if (__windowId) closeWindow(__windowId);
  };

  return (
    <div
      data-subaction-list={workflow ?? "unknown"}
      className={`flex flex-col h-full ${inWindow ? "bg-transparent" : "bg-ice-0 dark:bg-charcoal-2"}`}
    >
      <div className="px-5 py-4 space-y-4 overflow-y-auto">
        <header>
          <h2 className="font-serif text-lg text-ink dark:text-bright">
            {meta?.label ?? "Workflow"}
          </h2>
          {meta && (
            <p className="text-[12px] text-shadow-1 dark:text-moonlight mt-0.5 leading-relaxed">
              {meta.tagline}
            </p>
          )}
          {!workflow && (
            <p className="text-[12px] text-shadow-1 dark:text-moonlight mt-0.5">
              No workflow was given to this window.
            </p>
          )}
        </header>

        {modes.length === 0 && workflow ? (
          <p className="text-sm italic text-shadow-1 dark:text-moonlight">
            No surfaces in this workflow.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {modes.map((m) => {
              const dest = destinationFor(m);
              const enabled = dest !== null;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    data-subaction-id={m.id}
                    disabled={!enabled}
                    onClick={() => { emitWernerExperience("highlight"); onRow(m); }}
                    title={m.blurb}
                    className={
                      "w-full text-left px-2.5 py-1.5 rounded flex items-center gap-2 " +
                      (enabled
                        ? "hover:bg-sun/20 dark:hover:bg-sun/10 text-ink dark:text-bright cursor-pointer"
                        : "text-ink-mute dark:text-moonlight cursor-default opacity-70")
                    }
                  >
                    <span className="flex-1 min-w-0 truncate text-[13px]">
                      {m.label}
                    </span>
                    {!m.built && (
                      <span className="shrink-0 text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                        not yet
                      </span>
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
